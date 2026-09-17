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
                if (slot.dataset.fragment.endsWith("/figures")) relocateFigures();
            })
            .catch(() => {
                slot.innerHTML = '<div class="fragment-decline">Unavailable.</div>';
            })
            .finally(settle);
    });
});

// Figures carry the heading of the section they illustrate (mobile-html
// mapping). Hoist each into its expander so the figure appears when the
// section opens; figures with no matching heading stay in the strip.
const relocateFigures = () => {
    const summaries = [...document.querySelectorAll(".section-expander > summary")];
    document.querySelectorAll(".section-figure[data-section]").forEach((fig) => {
        const want = fig.dataset.section.trim().toLowerCase();
        const summary = summaries.find((s) => s.textContent.trim().toLowerCase() === want);
        const body = summary?.parentElement?.querySelector(":scope > .section-body");
        if (body) {
            body.prepend(fig);
            fig.classList.add("in-section");
        }
    });
    document.querySelectorAll(".figure-strip:not(:has(.section-figure))").forEach((el) => el.remove());
    document.querySelectorAll(".figures:not(:has(figure))").forEach((el) => el.remove());
};
