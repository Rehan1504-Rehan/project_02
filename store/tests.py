import os
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import CartItem, Category, Order, OrderItem, Product


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
