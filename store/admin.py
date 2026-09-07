from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BuiltInUserAdmin
from django.utils.html import format_html

from .models import Cart, CartItem, Category, MediaFile, Order, OrderItem, Product


class StockStatusFilter(admin.SimpleListFilter):
    title = "stock status"
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return (("in", "In stock"), ("out", "Out of stock"))

    def queryset(self, request, queryset):
        if self.value() == "in":
            return queryset.filter(stock_quantity__gt=0)
        if self.value() == "out":
            return queryset.filter(stock_quantity=0)
        return queryset


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "product_count")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


class ProductAdminForm(forms.ModelForm):
    """Adds an upload size guard to the product form."""

    class Meta:
        model = Product
        fields = "__all__"

    def clean_image(self):
        image = self.cleaned_data.get("image")
        # Only a freshly uploaded file has a size to check; an unchanged field
        # returns the existing stored file.
        size = getattr(image, "size", None)
        if size and size > settings.MAX_IMAGE_UPLOAD_BYTES:
            raise forms.ValidationError(
                "This image is %(actual).1f MB. Please upload a file of %(limit).0f MB or less."
                % {
                    "actual": size / (1024 * 1024),
                    "limit": settings.MAX_IMAGE_UPLOAD_MB,
                }
            )
        return image


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = (
        "image_preview",
        "name",
        "category",
        "price",
        "discount_price",
        "stock_quantity",
        "available",
        "created_at",
    )
    list_display_links = ("image_preview", "name")
    list_editable = ("price", "discount_price", "stock_quantity", "available")
    list_filter = ("available", StockStatusFilter, "category", "created_at", "updated_at")
    search_fields = ("name", "description", "category__name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("image_preview", "created_at", "updated_at")
    fieldsets = (
        (
            "Product information",
            {"fields": ("name", "slug", "description", "category", "image", "image_preview")},
        ),
        ("Pricing and inventory", {"fields": ("price", "discount_price", "stock_quantity", "available")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Image")
    def image_preview(self, obj):
        if not obj.image:
            return format_html('<span style="color:#9ca3af;">No image</span>')
        # A row can still point at a file that is gone (for example an upload
        # made before media moved into the database, which the host wiped on
        # the next deploy). Say so plainly instead of showing a broken image.
        try:
            missing = not obj.image.storage.exists(obj.image.name)
        except Exception:  # pragma: no cover - never block the changelist
            missing = False
        if missing:
            return format_html(
                '<span style="color:#b91c1c;" title="{}">Missing file — re-upload</span>',
                obj.image.name,
            )
        return format_html(
            '<img src="{}" alt="{}" style="height:48px;width:48px;object-fit:cover;border-radius:8px;" />',
            obj.image.url,
            obj.name,
        )


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    """Read-only view of the uploads stored in the database."""

    list_display = ("name", "preview", "content_type", "size_display", "updated_at")
    search_fields = ("name", "content_type")
    list_filter = ("content_type", "updated_at")
    readonly_fields = ("name", "preview", "content_type", "size_display", "checksum", "created_at", "updated_at")
    fields = readonly_fields
    ordering = ("-updated_at",)

    def has_add_permission(self, request):
        # Files arrive through product uploads, never by hand.
        return False

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.content_type.startswith("image/"):
            return format_html(
                '<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:8px;" />',
                f"{settings.MEDIA_URL}{obj.name}",
            )
        return "—"

    @admin.display(description="Size", ordering="size")
    def size_display(self, obj):
        return f"{obj.size / 1024:.1f} KB"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "product_name", "quantity", "price", "line_total")
    fields = ("product", "product_name", "quantity", "price", "line_total")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "total_amount", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at", "updated_at")
    search_fields = ("order_number", "user__username", "user__email", "phone_number", "shipping_address")
    readonly_fields = ("order_number", "user", "total_amount", "created_at", "updated_at")
    date_hierarchy = "created_at"
    list_editable = ("status",)
    inlines = (OrderItemInline,)
    fieldsets = (
        ("Order", {"fields": ("order_number", "user", "total_amount", "status")}),
        ("Delivery", {"fields": ("shipping_address", "phone_number")}),
        ("Dates", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "quantity", "price", "line_total")
    search_fields = ("order__order_number", "product_name")
    readonly_fields = ("order", "product", "product_name", "quantity", "price", "line_total")


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "quantity", "date_added")
    readonly_fields = ("date_added",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count_display", "updated_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("user", "created_at", "updated_at")
    inlines = (CartItemInline,)

    @admin.display(description="Items")
    def item_count_display(self, obj):
        return obj.item_count()


# Django registers the built-in User model by default. Re-register it with
# useful store-management search and list columns.
User = get_user_model()
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class StoreUserAdmin(BuiltInUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    list_filter = ("is_staff", "is_active", "date_joined")
    date_hierarchy = "date_joined"


admin.site.site_header = "Northstar Store Administration"
admin.site.site_title = "Northstar Store Admin"
admin.site.index_title = "Store management"
