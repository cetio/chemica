document.addEventListener("DOMContentLoaded", () => {
    const mount = document.querySelector("[data-sdf]");
    if (!mount) return;

    const wrap = mount.closest(".structure-views");
    const image = wrap.querySelector(".structure-image");
    const toggle = wrap.querySelector(".view-toggle");

    const show = (view) => {
        mount.hidden = view !== "3d";
        image.hidden = view !== "2d";
        for (const btn of toggle.querySelectorAll("button"))
            btn.classList.toggle("active", btn.dataset.view === view);
    };

    const fallBackTo2d = () => {
        toggle.querySelector('[data-view="3d"]').disabled = true;
        show("2d");
    };

    toggle.addEventListener("click", (event) => {
        const btn = event.target.closest("button[data-view]");
        if (btn && !btn.disabled) show(btn.dataset.view);
    });

    if (typeof $3Dmol === "undefined") {
        fallBackTo2d();
        return;
    }

    fetch(mount.dataset.sdf)
        .then((resp) => (resp.ok ? resp.text() : Promise.reject(resp.status)))
        .then((sdf) => {
            if (!sdf.trim()) throw new Error("empty sdf");
            mount.textContent = "";
            const viewer = $3Dmol.createViewer(mount, {
                backgroundColor: "#101215",
            });
            viewer.addModel(sdf, "sdf");
            viewer.setStyle({}, { stick: { radius: 0.14 }, sphere: { scale: 0.26 } });
            viewer.zoomTo();
            viewer.render();
        })
        .catch(fallBackTo2d);
});
