document.addEventListener("DOMContentLoaded", () => {
    const slots = document.querySelectorAll("[data-fragment]");
    let pending = slots.length;
    if (!pending) {
        document.body.dataset.panelsSettled = "1";
        return;
    }
    const settle = () => {
        pending -= 1;
        if (pending === 0) document.body.dataset.panelsSettled = "1";
    };
    slots.forEach((slot) => {
        fetch(slot.dataset.fragment)
            .then(async (resp) => {
                const html = resp.ok ? await resp.text() : "";
                if (!html.trim()) {
                    slot.remove();
                    return;
                }
                slot.outerHTML = html;
            })
            .catch(() => {
                slot.innerHTML = '<div class="fragment-decline">Unavailable.</div>';
            })
            .finally(settle);
    });
});
