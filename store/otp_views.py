import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import OTPVerificationForm, RegistrationForm
from .models import EmailOTP


logger = logging.getLogger(__name__)
User = get_user_model()


def send_otp_email(email: str, otp: str, user_name: str = "") -> bool:
    """Send a 6-digit OTP email using Brevo SMTP (or configured backend)."""
    expiry_minutes = getattr(settings, "OTP_EXPIRY_MINUTES", 5)
    subject = f"Your Northstar Store Verification Code: {otp}"

    # Plain text version for non-HTML email clients
    plain_message = (
        f"Hello {user_name or 'there'},\n\n"
        f"Your one-time verification code for Northstar Store is: {otp}\n\n"
        f"This code is valid for {expiry_minutes} minutes. Please enter it on the verification "
        "page to complete your registration.\n\n"
        "Tip: If you do not see our emails in your inbox, please check your Spam/Junk folder.\n\n"
        "If you did not request this code, you can safely ignore this email.\n\n"
        "— The Northstar Store Team\n"
    )

    context = {
        "otp": otp,
        "user_name": user_name,
        "expiry_minutes": expiry_minutes,
    }

    try:
        html_message = render_to_string("store/emails/otp_email.html", context)
    except Exception as exc:
        logger.warning("Failed to render OTP HTML email template: %s", exc)
        html_message = None

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.error("Failed to send OTP email to %s: %s", email, exc)
        raise


@require_http_methods(["GET", "HEAD", "POST"])
def register_view_with_otp(request: HttpRequest) -> HttpResponse:
    """Registration step 1: Validate registration details and dispatch OTP."""
    if request.user.is_authenticated:
        return redirect("store:home")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reg_data = {
            "username": form.cleaned_data["username"],
            "email": form.cleaned_data["email"],
            "first_name": form.cleaned_data["first_name"],
            "last_name": form.cleaned_data["last_name"],
            "password": form.cleaned_data["password1"],
        }

        # Save pending registration data in session
        request.session["registration_data"] = reg_data

        # Generate fresh OTP and record in database
        otp = EmailOTP.generate_otp()
        EmailOTP.objects.filter(email=reg_data["email"]).delete()
        EmailOTP.objects.create(
            email=reg_data["email"],
            otp=otp,
            created_at=timezone.now(),
            is_verified=False,
            attempts=0,
        )

        # Dispatch verification email via Brevo SMTP / configured backend
        try:
            send_otp_email(
                email=reg_data["email"],
                otp=otp,
                user_name=reg_data["first_name"],
            )
            messages.info(
                request,
                f"We've sent a 6-digit verification code to {reg_data['email']}. "
                "Please check your inbox (and spam folder) to complete your registration.",
            )
        except Exception:
            messages.warning(
                request,
                "We encountered an issue dispatching the email. "
                "If you don't receive your code, click 'Resend verification code'.",
            )

        return redirect("store:verify_otp")

    return render(request, "store/register.html", {"form": form})


@require_http_methods(["GET", "HEAD", "POST"])
def verify_otp_view(request: HttpRequest) -> HttpResponse:
    """Registration step 2: Verify 6-digit OTP, create user account, and log in."""
    if request.user.is_authenticated:
        return redirect("store:home")

    reg_data = request.session.get("registration_data")
    if not reg_data or not reg_data.get("email"):
        messages.warning(request, "Your registration session has expired. Please sign up again.")
        return redirect("store:register")

    email = reg_data["email"]
    expiry_minutes = getattr(settings, "OTP_EXPIRY_MINUTES", 5)
    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        entered_otp = form.cleaned_data["otp"]
        otp_record = EmailOTP.objects.filter(email=email).order_by("-created_at").first()

        if not otp_record:
            form.add_error(None, "No active verification code found. Please request a new OTP.")
        elif otp_record.is_expired():
            form.add_error(
                None,
                "This verification code has expired. Please click 'Resend verification code' below.",
            )
        elif otp_record.attempts >= 3:
            form.add_error(
                None,
                "Maximum verification attempts exceeded (3/3). Please request a new code.",
            )
        elif otp_record.otp != entered_otp:
            otp_record.attempts += 1
            otp_record.save(update_fields=["attempts"])
            remaining = max(0, 3 - otp_record.attempts)
            if remaining > 0:
                form.add_error(
                    "otp",
                    f"Invalid verification code. You have {remaining} attempt{'s' if remaining > 1 else ''} remaining.",
                )
            else:
                form.add_error(
                    None,
                    "Invalid verification code. Maximum attempts exceeded (3/3). Please click 'Resend verification code'.",
                )
        else:
            # OTP is valid and matches!
            # Ensure unique constraints still hold before creating
            if User.objects.filter(username=reg_data["username"]).exists():
                form.add_error(None, "An account with this username already exists.")
                return render(
                    request,
                    "store/verify_otp.html",
                    {"form": form, "email": email, "expiry_minutes": expiry_minutes},
                )
            if User.objects.filter(email__iexact=email).exists():
                form.add_error(None, "An account with this email already exists.")
                return render(
                    request,
                    "store/verify_otp.html",
                    {"form": form, "email": email, "expiry_minutes": expiry_minutes},
                )

            # Create the user
            user = User.objects.create_user(
                username=reg_data["username"],
                email=reg_data["email"],
                password=reg_data["password"],
                first_name=reg_data.get("first_name", ""),
                last_name=reg_data.get("last_name", ""),
            )

            # Cleanup OTP and session data
            EmailOTP.objects.filter(email=email).delete()
            request.session.pop("registration_data", None)

            # Authenticate and log the user in
            login(request, user)
            messages.success(
                request,
                f"Welcome to Northstar Store, {user.first_name or user.username}! "
                "Your email has been verified and your account is ready.",
            )
            return redirect(getattr(settings, "LOGIN_REDIRECT_URL", "store:home"))

    return render(
        request,
        "store/verify_otp.html",
        {"form": form, "email": email, "expiry_minutes": expiry_minutes},
    )


@require_http_methods(["GET", "HEAD", "POST"])
def resend_otp_view(request: HttpRequest) -> HttpResponse:
    """Generate and resend a new OTP for the active registration session."""
    if request.user.is_authenticated:
        return redirect("store:home")

    reg_data = request.session.get("registration_data")
    if not reg_data or not reg_data.get("email"):
        messages.warning(request, "Your registration session has expired. Please sign up again.")
        return redirect("store:register")

    email = reg_data["email"]
    otp = EmailOTP.generate_otp()

    # Reset attempts and renew OTP timestamp
    EmailOTP.objects.filter(email=email).delete()
    EmailOTP.objects.create(
        email=email,
        otp=otp,
        created_at=timezone.now(),
        is_verified=False,
        attempts=0,
    )

    try:
        send_otp_email(
            email=email,
            otp=otp,
            user_name=reg_data.get("first_name", ""),
        )
        messages.success(
            request,
            f"A fresh 6-digit verification code has been sent to {email}. "
            "Please check your inbox and spam folder.",
        )
    except Exception:
        messages.error(
            request,
            "We were unable to resend the verification email. Please try again in a few moments.",
        )

    return redirect("store:verify_otp")
