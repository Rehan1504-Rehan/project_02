from django.db import DatabaseError
from django.db.models import Sum

from .models import Cart


def cart_context(request):
    """Expose a small cart badge count to every page for signed-in users."""
    cart_count = 0
    if request.user.is_authenticated:
        try:
            cart_count = (
                Cart.objects.filter(user=request.user)
                .aggregate(total=Sum("items__quantity"))
                .get("total")
                or 0
            )
        except DatabaseError:
            # Do not turn a friendly 500/maintenance page into another error
            # when the database is temporarily unavailable.
            cart_count = 0
    return {"cart_count": cart_count}
