document.addEventListener("DOMContentLoaded", () => {
    const mount = document.querySelector("[data-sdf]");
    if (!mount) return;

    const wrap = mount.closest(".structure-views");
    const image = wrap.querySelector(".structure-image");
    const toggle = wrap.querySelector(".view-toggle");

    const baseStyle = { stick: { radius: 0.14 }, sphere: { scale: 0.26 } };
    const hoverStyle = { stick: { radius: 0.2 }, sphere: { scale: 0.44 } };

    let viewer = null;
    let sdf = null;
    let current = null;

    const wireHover = () => {
        viewer.setHoverable(
            {},
            true,
            (atom) => {
                if (atom.hoverLabel) return;
                atom.hoverLabel = viewer.addLabel(`${atom.elem}${atom.serial}`, {
                    position: atom,
                    screenOffset: { x: 16, y: -14 },
                    fontSize: 11,
                    fontColor: "#e8eaf0",
                    backgroundColor: "#1d2128",
                    backgroundOpacity: 0.85,
                    borderColor: "#5ee0a0",
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
    };

    const build = (data) => {
        mount.textContent = "";
        viewer = $3Dmol.createViewer(mount, {
            backgroundColor: "#1d2128",
            projection: "perspective",
        });
        viewer.addModel(data, "sdf");
        viewer.setStyle({}, baseStyle);
        wireHover();
        viewer.zoomTo();
        viewer.render();
    };

    const mark = (view) => {
        for (const btn of toggle.querySelectorAll("button"))
            btn.classList.toggle("active", btn.dataset.view === view);
    };

    const show = (view) => {
        if (view === current) return;
        mark(view);
        current = view;
        if (view === "2d") {
            // The PubChem PNG on the same dark plate the xref cards use — a
            // proper 2D depiction, not a flattened conformer.
            mount.hidden = true;
            image.hidden = false;
            return;
        }
        const ready = sdf ? Promise.resolve(sdf) : fetch(mount.dataset.sdf)
            .then((resp) => (resp.ok ? resp.text() : Promise.reject(resp.status)))
            .then((data) => {
                if (!data.trim()) throw new Error("empty sdf");
                sdf = data;
                return data;
            });
        ready
            .then((data) => {
                mount.hidden = false;
                image.hidden = true;
                build(data);
            })
            .catch(() => {
                // No conformer or transient upstream failure: the static
                // depiction is the honest fallback.
                show("2d");
                toggle.querySelector('button[data-view="3d"]').disabled = true;
            });
    };

    toggle.addEventListener("click", (event) => {
        const btn = event.target.closest("button[data-view]");
        if (btn && !btn.disabled) show(btn.dataset.view);
    });

    if (typeof $3Dmol === "undefined") {
        mount.hidden = true;
        image.hidden = false;
        toggle.querySelectorAll("button").forEach((btn) => (btn.disabled = true));
        return;
    }

    show("3d");
});
