from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


def generate_order_number() -> str:
    """Generate a short, human-friendly order identifier."""
    return uuid.uuid4().hex[:12].upper()


class Category(models.Model):
    """A simple product category managed from Django Admin."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "category"
            candidate = base_slug
            counter = 2
            while Category.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:category_products", args=[self.slug])


class Product(models.Model):
    """A product that customers can browse and purchase."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    image = models.ImageField(upload_to="products/%Y/%m/", blank=True, null=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["available", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()
        if (
            self.discount_price is not None
            and self.price is not None
            and self.discount_price >= self.price
        ):
            raise ValidationError(
                {"discount_price": "The discount price must be lower than the regular price."}
            )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "product"
            candidate = base_slug
            counter = 2
            while Product.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate
        return super().save(*args, **kwargs)

    @property
    def stock(self):
        """A friendly alias for code that calls the quantity simply ``stock``."""
        return self.stock_quantity

    @stock.setter
    def stock(self, value):
        self.stock_quantity = value

    def get_price(self) -> Decimal:
        return self.discount_price or self.price

    @property
    def has_discount(self) -> bool:
        return self.discount_price is not None

    @property
    def is_in_stock(self) -> bool:
        return self.available and self.stock_quantity > 0

    def get_absolute_url(self):
        return reverse("store:product_detail", args=[self.slug])


class Cart(models.Model):
    """One persistent cart per authenticated customer."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Cart for {self.user.get_username()}"

    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.items.select_related("product")), Decimal("0.00"))

    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_added"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="unique_cart_product")
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product.name}"

    @property
    def subtotal(self) -> Decimal:
        return self.product.get_price() * self.quantity


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    order_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        default=generate_order_number,
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    shipping_address = models.TextField()
    phone_number = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Order {self.order_number}"

    def get_absolute_url(self):
        return reverse("store:order_detail", args=[self.order_number])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # SET_NULL keeps an old order readable if an admin removes the catalog item.
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=200, blank=True, default="")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    # This is intentionally a snapshot, not a live reference to Product.price.
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product_name}"

    @property
    def price_at_purchase(self) -> Decimal:
        """Readable alias documenting the historical-price behavior."""
        return self.price

    @property
    def line_total(self) -> Decimal:
        return self.price * self.quantity
