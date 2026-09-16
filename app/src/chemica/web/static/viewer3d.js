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

    const baseStyle = { stick: { radius: 0.14 }, sphere: { scale: 0.26 } };
    const hoverStyle = { stick: { radius: 0.2 }, sphere: { scale: 0.44 } };

    fetch(mount.dataset.sdf)
        .then((resp) => (resp.ok ? resp.text() : Promise.reject(resp.status)))
        .then((sdf) => {
            if (!sdf.trim()) throw new Error("empty sdf");
            mount.textContent = "";
            const viewer = $3Dmol.createViewer(mount, {
                backgroundColor: "#101215",
            });
            viewer.addModel(sdf, "sdf");
            viewer.setStyle({}, baseStyle);

            if (mount.dataset.name) {
                const mark = document.createElement("div");
                mark.textContent = mount.dataset.name;
                mark.style.cssText =
                    "position:absolute;left:0;right:0;bottom:6px;text-align:center;" +
                    "font-size:42px;font-weight:700;color:#e8eaf0;opacity:0.07;" +
                    "white-space:nowrap;overflow:hidden;pointer-events:none;";
                mount.appendChild(mark);
            }

            viewer.setHoverable(
                {},
                true,
                (atom) => {
                    if (atom.hoverLabel) return;
                    atom.hoverLabel = viewer.addLabel(`${atom.elem}${atom.serial}`, {
                        position: atom,
                        fontSize: 11,
                        fontColor: "#e8eaf0",
                        backgroundColor: "#101215",
                        backgroundOpacity: 0.85,
                        borderColor: "#58a6ff",
                        borderThickness: 1,
                        padding: 3,
                    });
                    viewer.setStyle({ serial: atom.serial }, hoverStyle);
                    viewer.render();
                },
                (atom) => {
                    if (atom.hoverLabel) {
                        viewer.removeLabel(atom.hoverLabel);
                        atom.hoverLabel = null;
                    }
                    viewer.setStyle({ serial: atom.serial }, baseStyle);
                    viewer.render();
                },
            );
            viewer.setHoverDuration(150);

            viewer.zoomTo();
            viewer.render();
        })
        .catch(fallBackTo2d);
});
