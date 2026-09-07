document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-quantity-action]").forEach((button) => {
        button.addEventListener("click", () => {
            const control = button.closest(".quantity-control");
            const input = control && control.querySelector("input");
            if (!input) return;
            const minimum = Number(input.min || 1);
            const maximum = Number(input.max || Number.MAX_SAFE_INTEGER);
            const current = Number(input.value || minimum);
            const direction = button.dataset.quantityAction === "increase" ? 1 : -1;
            input.value = Math.min(maximum, Math.max(minimum, current + direction));
        });
    });

    // Give temporary alerts a gentle close without hiding them from screen readers.
    window.setTimeout(() => {
        document.querySelectorAll(".alert-dismissible").forEach((alert) => {
            if (window.bootstrap) {
                bootstrap.Alert.getOrCreateInstance(alert).close();
            }
        });
    }, 6500);
});
