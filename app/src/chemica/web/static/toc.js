document.addEventListener("click", (event) => {
    const link = event.target.closest(".toc-rail a[href^='#']");
    if (!link) return;
    const target = document.getElementById(link.hash.slice(1));
    if (target instanceof HTMLDetailsElement) target.open = true;
});

// Scroll-spy: the toc entry matching the section in view gets .active.
// Fragment panels land after DOMContentLoaded, so observe lazily on
// first scroll rather than enumerating targets up front.
(() => {
    const links = () => document.querySelectorAll(".toc-rail a[href^='#']");
    let observer = null;

    const activate = (id) => {
        links().forEach((link) => {
            link.classList.toggle("active", link.hash.slice(1) === id);
        });
    };

    const arm = () => {
        if (observer) return;
        const visible = new Set();
        observer = new IntersectionObserver(
            (entries) => {
                // Entries only cover targets that changed this batch —
                // keep a running set so a stale .active can't linger
                // when the next section's entry lands in a later batch.
                entries.forEach((entry) => {
                    if (entry.isIntersecting) visible.add(entry.target);
                    else visible.delete(entry.target);
                });
                if (visible.size) {
                    const top = [...visible].sort(
                        (a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top
                    )[0];
                    activate(top.id);
                }
            },
            { rootMargin: "-10% 0px -70% 0px" }
        );
        links().forEach((link) => {
            const target = document.getElementById(link.hash.slice(1));
            if (target) observer.observe(target);
        });
    };

    document.addEventListener("scroll", arm, { once: true, passive: true });
    // Fragment slots resolve async — re-arm once panels settle so lazy
    // sections get observed too.
    const settled = new MutationObserver(() => {
        if (document.body.dataset.panelsSettled === "1") {
            observer?.disconnect();
            observer = null;
            arm();
            settled.disconnect();
        }
    });
    settled.observe(document.body, { attributes: true, attributeFilter: ["data-panels-settled"] });
})();

// xref hover cards: flip to the item's right edge when they'd overflow the
// rail — the rail clips horizontally, so far-right items' cards vanish
// otherwise. Delegated mouseover works for fragment-loaded content.
document.addEventListener("mouseover", (event) => {
    const item = event.target.closest(".cross-ref-item");
    if (!item) return;
    const card = item.querySelector(".xref-card");
    if (!card) return;
    const rail = item.closest(".rail");
    const bounds = rail ? rail.getBoundingClientRect() : document.documentElement.getBoundingClientRect();
    card.classList.toggle("flip", item.getBoundingClientRect().left + 160 > bounds.right - 8);
});
