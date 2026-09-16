document.addEventListener("click", (event) => {
    const link = event.target.closest(".toc-rail a[href^='#']");
    if (!link) return;
    const target = document.getElementById(link.hash.slice(1));
    if (target instanceof HTMLDetailsElement) target.open = true;
});
