document.addEventListener("DOMContentLoaded", () => {
    const mount = document.querySelector("[data-sdf]");
    if (!mount || typeof $3Dmol === "undefined") return;

    fetch(mount.dataset.sdf)
        .then((resp) => (resp.ok ? resp.text() : ""))
        .then((sdf) => {
            if (!sdf.trim()) return;
            mount.textContent = "";
            const viewer = $3Dmol.createViewer(mount, {
                backgroundColor: "#101215",
            });
            viewer.addModel(sdf, "sdf");
            viewer.setStyle({}, { stick: { radius: 0.14 }, sphere: { scale: 0.26 } });
            viewer.zoomTo();
            viewer.render();
        })
        .catch(() => {});
});
