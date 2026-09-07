from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BuiltInUserAdmin
from django.utils.html import format_html

from .models import Cart, CartItem, Category, Order, OrderItem, Product


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


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
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
        if obj.image:
            return format_html(
                '<img src="{}" alt="{}" style="height:48px;width:48px;object-fit:cover;border-radius:8px;" />',
                obj.image.url,
                obj.name,
            )
        return format_html('<span style="color:#9ca3af;">No image</span>')


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
