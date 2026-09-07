from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.static import serve as static_serve
from django.utils.cache import get_conditional_response
from django.utils.http import http_date, url_has_allowed_host_and_scheme

from .forms import CheckoutForm, LoginForm, RegistrationForm
from .models import Cart, CartItem, Category, MediaFile, Order, OrderItem, Product
from .storage import normalize_name


class OutOfStockError(Exception):
    """Raised inside the checkout transaction when inventory is not sufficient."""


def home(request: HttpRequest) -> HttpResponse:
    featured_products = Product.objects.filter(available=True, stock_quantity__gt=0).select_related(
        "category"
    )[:8]
    categories = Category.objects.filter(
        products__available=True, products__stock_quantity__gt=0
    ).distinct()[:8]
    return render(
        request,
        "store/home.html",
        {"featured_products": featured_products, "categories": categories},
    )


def product_list(request: HttpRequest) -> HttpResponse:
    products = Product.objects.filter(available=True, stock_quantity__gt=0).select_related(
        "category"
    )
    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )
    selected_category = None
    if category_slug:
        selected_category = Category.objects.filter(slug=category_slug).first()
        if selected_category:
            products = products.filter(category=selected_category)

    context = {
        "products": products,
        "query": query,
        "categories": Category.objects.all(),
        "selected_category": selected_category,
    }
    return render(request, "store/product_list.html", context)


def category_products(request: HttpRequest, slug: str) -> HttpResponse:
    category = get_object_or_404(Category, slug=slug)
    products = Product.objects.filter(
        category=category,
        available=True,
        stock_quantity__gt=0,
    ).select_related("category")
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )
    return render(
        request,
        "store/product_list.html",
        {
            "products": products,
            "query": query,
            "categories": Category.objects.all(),
            "selected_category": category,
        },
    )


def product_detail(request: HttpRequest, slug: str) -> HttpResponse:
    product = get_object_or_404(
        Product.objects.select_related("category"),
        slug=slug,
        available=True,
    )
    related_products = Product.objects.filter(
        category=product.category,
        available=True,
        stock_quantity__gt=0,
    ).exclude(pk=product.pk)[:4]
    return render(
        request,
        "store/product_detail.html",
        {"product": product, "related_products": related_products},
    )


@require_http_methods(["GET", "POST"])
def register_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("store:home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your account was created. You can now sign in.")
        return redirect("store:login")
    return render(request, "store/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("store:home")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, f"Welcome back, {form.get_user().get_username()}!")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("store:home")
    return render(request, "store/login.html", {"form": form, "next": next_url})


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    """Sign out through a CSRF-protected POST form."""
    logout(request)
    messages.info(request, "You have been signed out safely.")
    return redirect("store:home")


@login_required
def _get_user_cart(request: HttpRequest) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=request.user)
    return cart


@login_required
def cart_view(request: HttpRequest) -> HttpResponse:
    cart = _get_user_cart(request)
    items = list(cart.items.select_related("product").all())
    total = sum((item.subtotal for item in items), Decimal("0.00"))
    return render(request, "store/cart.html", {"cart": cart, "items": items, "cart_total": total})


@require_POST
@login_required
def add_to_cart(request: HttpRequest, product_id: int) -> HttpResponse:
    product = get_object_or_404(Product, pk=product_id, available=True)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 0

    if quantity < 1:
        messages.error(request, "Choose a quantity of at least one.")
        return redirect(product.get_absolute_url())
    if quantity > product.stock_quantity:
        messages.error(request, f"Only {product.stock_quantity} item(s) are currently in stock.")
        return redirect(product.get_absolute_url())

    cart = _get_user_cart(request)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": quantity},
    )
    if not created:
        new_quantity = item.quantity + quantity
        if new_quantity > product.stock_quantity:
            messages.error(
                request,
                f"Your cart cannot contain more than {product.stock_quantity} of this product.",
            )
            return redirect(product.get_absolute_url())
        item.quantity = new_quantity
        item.save(update_fields=["quantity"])
    cart.save(update_fields=["updated_at"])
    messages.success(request, f"{product.name} was added to your cart.")
    return redirect("store:cart")


@require_POST
@login_required
def update_cart(request: HttpRequest, item_id: int) -> HttpResponse:
    item = get_object_or_404(
        CartItem.objects.select_related("product"),
        pk=item_id,
        cart__user=request.user,
    )
    try:
        quantity = int(request.POST.get("quantity", 0))
    except (TypeError, ValueError):
        quantity = 0

    if quantity <= 0:
        item.delete()
        messages.info(request, f"{item.product.name} was removed from your cart.")
    elif not item.product.available:
        messages.error(request, f"{item.product.name} is no longer available.")
    elif quantity > item.product.stock_quantity:
        messages.error(
            request,
            f"Only {item.product.stock_quantity} item(s) of {item.product.name} are in stock.",
        )
    else:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        item.cart.save(update_fields=["updated_at"])
        messages.success(request, "Your cart was updated.")
    return redirect("store:cart")


@require_POST
@login_required
def remove_from_cart(request: HttpRequest, item_id: int) -> HttpResponse:
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    name = item.product.name
    item.delete()
    messages.info(request, f"{name} was removed from your cart.")
    return redirect("store:cart")


@login_required
def checkout(request: HttpRequest) -> HttpResponse:
    cart = _get_user_cart(request)
    current_items = list(cart.items.select_related("product").all())
    if not current_items:
        messages.info(request, "Your cart is empty. Add a product before checking out.")
        return redirect("store:product_list")

    form = CheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                # Lock both the cart rows and each product row. This prevents two
                # simultaneous checkouts from selling the same inventory.
                locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
                locked_items = list(
                    CartItem.objects.select_for_update()
                    .filter(cart=locked_cart)
                    .select_related("product")
                )
                if not locked_items:
                    raise OutOfStockError("Your cart is empty. Please add an item and try again.")

                order_lines = []
                order_total = Decimal("0.00")
                for cart_item in locked_items:
                    product = Product.objects.select_for_update().get(pk=cart_item.product_id)
                    if not product.available:
                        raise OutOfStockError(f"{product.name} is no longer available.")
                    if cart_item.quantity > product.stock_quantity:
                        raise OutOfStockError(
                            f"Only {product.stock_quantity} of {product.name} remain in stock."
                        )
                    purchase_price = product.get_price()
                    order_lines.append((product, cart_item.quantity, purchase_price))
                    order_total += purchase_price * cart_item.quantity

                order = Order.objects.create(
                    user=request.user,
                    total_amount=order_total,
                    shipping_address=form.cleaned_data["shipping_address"],
                    phone_number=form.cleaned_data["phone_number"],
                )
                for product, quantity, purchase_price in order_lines:
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=quantity,
                        price=purchase_price,
                    )
                    product.stock_quantity -= quantity
                    if product.stock_quantity == 0:
                        product.available = False
                    product.save(update_fields=["stock_quantity", "available", "updated_at"])
                CartItem.objects.filter(cart=locked_cart).delete()
                locked_cart.save(update_fields=["updated_at"])
        except OutOfStockError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Order {order.order_number} was placed successfully.")
            return redirect("store:order_detail", order_number=order.order_number)

    # Re-read items after a validation error so the order summary is current.
    items = list(cart.items.select_related("product").all())
    cart_total = sum((item.subtotal for item in items), Decimal("0.00"))
    return render(
        request,
        "store/checkout.html",
        {"form": form, "cart": cart, "items": items, "cart_total": cart_total},
    )


@login_required
def order_list(request: HttpRequest) -> HttpResponse:
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "store/order_list.html", {"orders": orders})


@login_required
def order_detail(request: HttpRequest, order_number: str) -> HttpResponse:
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"),
        order_number=order_number,
        user=request.user,
    )
    return render(request, "store/order_detail.html", {"order": order})


@require_http_methods(["GET", "HEAD"])
def serve_media(request: HttpRequest, path: str) -> HttpResponse:
    """Serve an uploaded file at ``/media/<path>``.

    Uploads live in the database (see ``store.storage.DatabaseStorage``) so they
    survive the ephemeral container filesystems used by Render and similar
    hosts. Files that predate that change - or that were written to disk in
    local development - are still served from ``MEDIA_ROOT`` as a fallback.
    """
    try:
        name = normalize_name(path)
    except SuspiciousFileOperation:
        raise Http404("Invalid media path.")

    record = MediaFile.objects.filter(name=name).first()
    if record is None:
        return _serve_media_from_disk(request, name)

    etag = f'"{record.checksum}"' if record.checksum else None
    last_modified = int(record.updated_at.timestamp())
    conditional = get_conditional_response(request, etag=etag, last_modified=last_modified)
    if conditional is not None:
        return conditional

    response = HttpResponse(
        record.data, content_type=record.content_type or "application/octet-stream"
    )
    response["Content-Length"] = str(record.size)
    response["Last-Modified"] = http_date(last_modified)
    if etag:
        response["ETag"] = etag
    # Uploads get a fresh, unique name, so they can be cached for a while; the
    # ETag still lets browsers revalidate cheaply once the max-age expires.
    response["Cache-Control"] = f"public, max-age={settings.MEDIA_CACHE_SECONDS}"
    return response


def _serve_media_from_disk(request: HttpRequest, name: str) -> HttpResponse:
    """Fallback for legacy files that were saved to ``MEDIA_ROOT``."""
    try:
        return static_serve(request, name, document_root=settings.MEDIA_ROOT)
    except (SuspiciousFileOperation, ValueError):
        raise Http404("Invalid media path.")


# These handlers are referenced by ecommerce.urls and keep production errors
# friendly when DEBUG=False.
def permission_denied(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "403.html", status=403)


def page_not_found(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "404.html", status=404)


def server_error(request: HttpRequest) -> HttpResponse:
    return render(request, "500.html", status=500)
