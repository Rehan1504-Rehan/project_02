import base64
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from ecommerce.startup import run_startup_tasks

from .admin import ProductAdminForm
from .models import CartItem, Category, MediaFile, Order, OrderItem, Product


User = get_user_model()


class StoreFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="shopper",
            email="shopper@example.com",
            password="Strong-password-123",
            first_name="Shop",
            last_name="Per",
        )
        self.category = Category.objects.create(name="Electronics", description="Useful tech")
        self.product = Product.objects.create(
            name="Desk Light",
            description="A bright and useful desk light.",
            price=Decimal("50.00"),
            discount_price=Decimal("40.00"),
            category=self.category,
            stock_quantity=3,
            available=True,
        )

    def login(self):
        self.assertTrue(self.client.login(username="shopper", password="Strong-password-123"))

    def test_registration_hashes_password_and_persists_user(self):
        response = self.client.post(
            reverse("store:register"),
            {
                "username": "new-customer",
                "email": "new@example.com",
                "first_name": "New",
                "last_name": "Customer",
                "password1": "Another-strong-password-123",
                "password2": "Another-strong-password-123",
            },
        )
        self.assertRedirects(response, reverse("store:login"))
        created = User.objects.get(username="new-customer")
        self.assertNotEqual(created.password, "Another-strong-password-123")
        self.assertTrue(created.check_password("Another-strong-password-123"))

    def test_login_accepts_username_and_email_and_logout(self):
        response = self.client.post(
            reverse("store:login"),
            {"identifier": "shopper@example.com", "password": "Strong-password-123"},
        )
        self.assertRedirects(response, reverse("store:home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        response = self.client.post(reverse("store:logout"))
        self.assertRedirects(response, reverse("store:home"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_left_navigation_drawer_uses_clean_category_names(self):
        Category.objects.create(name="Gaming", description="Games and consoles")
        Product.objects.create(
            name="Arcade Pad",
            description="A wired game controller.",
            price=Decimal("20.00"),
            category=Category.objects.get(name="Gaming"),
            stock_quantity=2,
            available=True,
        )
        response = self.client.get(reverse("store:home"))
        self.assertContains(response, 'id="navDrawer"')
        self.assertContains(response, "nav-drawer")
        self.assertContains(response, "data-nav-open")
        self.assertContains(response, "Electronics")
        self.assertContains(response, "Gaming")
        self.assertNotContains(response, "Electronics1")
        self.assertNotContains(response, "Gaming1")
        self.assertContains(response, reverse("store:product_list"))
        self.assertContains(response, reverse("store:deals"))
        self.assertContains(response, reverse("store:cart"))
        self.assertContains(response, reverse("store:login"))

    def test_search_and_category_filter(self):
        other = Product.objects.create(
            name="Canvas Shoes",
            description="Comfortable everyday wear.",
            price=Decimal("65.00"),
            stock_quantity=4,
            available=True,
        )
        response = self.client.get(reverse("store:product_list"), {"q": "desk"})
        self.assertContains(response, "Desk Light")
        self.assertNotContains(response, "Canvas Shoes")
        response = self.client.get(self.category.get_absolute_url())
        self.assertContains(response, "Desk Light")
        self.assertNotContains(response, other.name)

    def test_cart_checkout_reduces_stock_and_keeps_historical_price(self):
        self.login()
        response = self.client.post(
            reverse("store:add_to_cart", args=[self.product.pk]), {"quantity": 2}
        )
        self.assertRedirects(response, reverse("store:cart"))
        self.assertEqual(CartItem.objects.get(product=self.product).quantity, 2)

        response = self.client.post(
            reverse("store:checkout"),
            {"shipping_address": "123 Main Street, Example City 12345", "phone_number": "+1 555 123 4567"},
        )
        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, order.get_absolute_url())
        self.assertEqual(order.total_amount, Decimal("80.00"))
        self.assertEqual(Product.objects.get(pk=self.product.pk).stock_quantity, 1)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

        line = order.items.get()
        self.product.price = Decimal("99.00")
        self.product.discount_price = None
        self.product.save()
        line.refresh_from_db()
        self.assertEqual(line.price, Decimal("40.00"))
        self.assertEqual(line.price_at_purchase, Decimal("40.00"))

    def test_cart_rejects_quantity_above_stock(self):
        self.login()
        response = self.client.post(
            reverse("store:add_to_cart", args=[self.product.pk]), {"quantity": 4}
        )
        self.assertRedirects(response, self.product.get_absolute_url())
        self.assertFalse(CartItem.objects.filter(product=self.product).exists())

    def test_order_history_is_private(self):
        self.login()
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("1.00"),
            shipping_address="123 Main Street",
            phone_number="5555555",
        )
        other_user = User.objects.create_user(username="other", password="Other-pass-123")
        self.client.force_login(other_user)
        response = self.client.get(order.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_media_served_with_debug_false(self):
        media_file = settings.MEDIA_ROOT / "test_image.png"
        settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"dummy-image-data")
        try:
            with override_settings(DEBUG=False, SERVE_MEDIA=True):
                response = self.client.get("/media/test_image.png")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"dummy-image-data")
        finally:
            if media_file.exists():
                media_file.unlink()


# A tiny but genuine 1x1 PNG, so ImageField validation is exercised for real.
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="
)


class MediaPersistenceTests(TestCase):
    """Uploads must outlive the container filesystem.

    Hosts such as Render wipe the filesystem on every deploy, which used to
    leave products pointing at a /media/ URL that answered 404.
    """

    def setUp(self):
        self.product = Product.objects.create(
            name="Desk Lamp",
            description="A warm desk lamp.",
            price=Decimal("40.00"),
            stock_quantity=3,
        )

    def upload(self, filename="lamp.png", payload=ONE_PIXEL_PNG):
        self.product.image = SimpleUploadedFile(filename, payload, content_type="image/png")
        self.product.save()
        self.product.refresh_from_db()
        return self.product.image.name

    def test_upload_is_stored_in_the_database_not_on_disk(self):
        name = self.upload()
        self.assertTrue(MediaFile.objects.filter(name=name).exists())
        self.assertEqual(MediaFile.objects.get(name=name).data, ONE_PIXEL_PNG)
        self.assertFalse((Path(settings.MEDIA_ROOT) / name).exists())

    def test_image_url_serves_the_uploaded_bytes(self):
        self.upload()
        url = self.product.image.url
        self.assertTrue(url.startswith("/media/products/"))
        with override_settings(DEBUG=False, SERVE_MEDIA=True):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, ONE_PIXEL_PNG)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("max-age", response["Cache-Control"])

    def test_image_survives_a_wiped_container_filesystem(self):
        """Simulate a redeploy: the disk is empty, the database is not."""
        self.upload()
        url = self.product.image.url
        with override_settings(DEBUG=False, MEDIA_ROOT=Path(tempfile.mkdtemp())):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, ONE_PIXEL_PNG)

    def test_storefront_renders_the_working_image_url(self):
        self.upload()
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, self.product.image.url)
        image_response = self.client.get(self.product.image.url)
        self.assertEqual(image_response.status_code, 200)

    def test_repeat_upload_of_same_filename_keeps_both_products_working(self):
        first = self.upload()
        other = Product.objects.create(
            name="Floor Lamp",
            description="A tall lamp.",
            price=Decimal("60.00"),
            stock_quantity=2,
            image=SimpleUploadedFile("lamp.png", b"", content_type="image/png"),
        )
        other.image = SimpleUploadedFile("lamp.png", ONE_PIXEL_PNG, content_type="image/png")
        other.save()
        other.refresh_from_db()
        self.assertNotEqual(first, other.image.name)
        self.assertEqual(self.client.get(other.image.url).status_code, 200)

    def test_replacing_an_image_removes_the_previous_file(self):
        original = self.upload()
        replacement = self.upload(filename="lamp-v2.png")
        self.assertNotEqual(original, replacement)
        self.assertFalse(MediaFile.objects.filter(name=original).exists())
        self.assertTrue(MediaFile.objects.filter(name=replacement).exists())

    def test_deleting_a_product_removes_its_file(self):
        name = self.upload()
        self.product.delete()
        self.assertFalse(MediaFile.objects.filter(name=name).exists())

    def test_unknown_media_path_returns_404(self):
        with override_settings(DEBUG=False):
            self.assertEqual(self.client.get("/media/products/nope.png").status_code, 404)

    def test_media_path_traversal_is_rejected(self):
        with override_settings(DEBUG=False):
            response = self.client.get("/media/../ecommerce/settings.py")
        self.assertIn(response.status_code, {404, 400})

    def test_conditional_request_returns_304(self):
        self.upload()
        url = self.product.image.url
        first = self.client.get(url)
        second = self.client.get(url, headers={"if-none-match": first["ETag"]})
        self.assertEqual(second.status_code, 304)

    def test_import_command_moves_disk_files_into_the_database(self):
        media_root = Path(tempfile.mkdtemp())
        legacy = media_root / "products" / "2026" / "09" / "legacy.png"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(ONE_PIXEL_PNG)
        with override_settings(MEDIA_ROOT=media_root):
            call_command("import_media_to_db", verbosity=0)
        record = MediaFile.objects.get(name="products/2026/09/legacy.png")
        self.assertEqual(record.data, ONE_PIXEL_PNG)
        self.assertEqual(record.content_type, "image/png")

    def test_check_media_clears_references_to_lost_files(self):
        Product.objects.filter(pk=self.product.pk).update(image="products/2026/09/gone.png")
        call_command("check_media", "--clear-missing", verbosity=0)
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)

    def test_oversized_upload_is_rejected_by_the_admin_form(self):
        big = SimpleUploadedFile("big.png", ONE_PIXEL_PNG, content_type="image/png")
        big.size = settings.MAX_IMAGE_UPLOAD_BYTES + 1
        form = ProductAdminForm(
            data={
                "name": "Huge",
                "slug": "huge",
                "description": "Too big",
                "price": "10.00",
                "stock_quantity": "1",
                "available": "on",
            },
            files={"image": big},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)


class StartupTaskTests(TestCase):
    """The web process repairs itself on boot, with no dashboard steps."""

    def test_startup_clears_references_to_files_lost_with_the_old_disk(self):
        product = Product.objects.create(
            name="Smart Plug",
            description="A useful plug.",
            price=Decimal("12.00"),
            stock_quantity=5,
        )
        # Exactly the situation on the live site: the row survived in the
        # database, the file did not survive the redeploy.
        Product.objects.filter(pk=product.pk).update(
            image="products/2026/09/standard_smart_plug.webp"
        )

        run_startup_tasks()

        product.refresh_from_db()
        self.assertFalse(product.image)
        # The storefront now shows the placeholder instead of a broken image.
        response = self.client.get(product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "placeholder-image")

    def test_startup_keeps_images_that_are_present(self):
        product = Product.objects.create(
            name="Desk Lamp",
            description="A warm lamp.",
            price=Decimal("40.00"),
            stock_quantity=2,
            image=SimpleUploadedFile("lamp.png", ONE_PIXEL_PNG, content_type="image/png"),
        )
        run_startup_tasks()
        product.refresh_from_db()
        self.assertTrue(product.image)
        self.assertEqual(self.client.get(product.image.url).status_code, 200)

    def test_startup_is_a_no_op_for_disk_backed_media(self):
        """A slow disk mount must never cause a reference to be discarded."""
        product = Product.objects.create(
            name="Mug",
            description="A mug.",
            price=Decimal("9.00"),
            stock_quantity=1,
        )
        Product.objects.filter(pk=product.pk).update(image="products/2026/09/mug.jpg")
        with override_settings(MEDIA_STORAGE="filesystem"):
            run_startup_tasks()
        product.refresh_from_db()
        self.assertEqual(product.image.name, "products/2026/09/mug.jpg")

    def test_startup_can_be_disabled(self):
        product = Product.objects.create(
            name="Kettle",
            description="A kettle.",
            price=Decimal("30.00"),
            stock_quantity=1,
        )
        Product.objects.filter(pk=product.pk).update(image="products/2026/09/gone.jpg")
        with override_settings(RUN_STARTUP_TASKS=False):
            run_startup_tasks()
        product.refresh_from_db()
        self.assertEqual(product.image.name, "products/2026/09/gone.jpg")

    def test_startup_survives_a_broken_database(self):
        with patch("ecommerce.startup._apply_pending_migrations", side_effect=OSError("boom")):
            run_startup_tasks()  # must not raise: the site still has to boot


class AdminSetupCommandTests(TestCase):
    def test_create_admin_uses_environment_and_is_idempotent(self):
        env = {
            "ADMIN_USERNAME": "ADMIN",
            "ADMIN_PASSWORD": "Very-strong-admin-password-123",
            "ADMIN_EMAIL": "admin@example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            call_command("create_admin")
            call_command("create_admin")
        admin = User.objects.get(username="ADMIN")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password(env["ADMIN_PASSWORD"]))
        self.assertEqual(User.objects.filter(username="ADMIN").count(), 1)
