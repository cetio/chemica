document.addEventListener("DOMContentLoaded", () => {
    const mount = document.querySelector("[data-sdf]");
    if (!mount) return;

    const wrap = mount.closest(".structure-views");
    const image = wrap.querySelector(".structure-image");
    const toggle = wrap.querySelector(".view-toggle");

    const baseStyle = { stick: { radius: 0.14 }, sphere: { scale: 0.26 } };
    const flatStyle = { stick: { radius: 0.07 } };
    const hoverStyle = { stick: { radius: 0.2 }, sphere: { scale: 0.44 } };
    const flatHoverStyle = { stick: { radius: 0.12 } };

    const sdfs = {};
    let viewer = null;
    let current = null;

    const fetchSdf = (view) => {
        if (sdfs[view]) return Promise.resolve(sdfs[view]);
        const url = view === "2d" ? `${mount.dataset.sdf}?flat=1` : mount.dataset.sdf;
        return fetch(url)
            .then((resp) => (resp.ok ? resp.text() : Promise.reject(resp.status)))
            .then((sdf) => {
                if (!sdf.trim()) throw new Error("empty sdf");
                sdfs[view] = sdf;
                return sdf;
            });
    };

    const wireHover = (style, hover) => {
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
                    backgroundColor: "#101215",
                    backgroundOpacity: 0.85,
                    borderColor: "#5ee0a0",
                    borderThickness: 1,
                    padding: 3,
                });
                viewer.setStyle({ serial: atom.serial }, hover);
                viewer.render();
            },
            (atom) => {
                if (atom.hoverLabel) {
                    viewer.removeLabel(atom.hoverLabel);
                    atom.hoverLabel = null;
                }
                viewer.setStyle({ serial: atom.serial }, style);
                viewer.render();
            },
        );
        viewer.setHoverDuration(150);
    };

    const build = (sdf, flat) => {
        mount.textContent = "";
        viewer = $3Dmol.createViewer(mount, {
            backgroundColor: "#101215",
            projection: flat ? "orthographic" : "perspective",
        });
        viewer.addModel(sdf, "sdf");
        viewer.setStyle({}, flat ? flatStyle : baseStyle);
        wireHover(flat ? flatStyle : baseStyle, flat ? flatHoverStyle : hoverStyle);
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
        fetchSdf(view)
            .then((sdf) => {
                current = view;
                mount.hidden = false;
                image.hidden = true;
                build(sdf, view === "2d");
            })
            .catch(() => {
                if (view === "3d") {
                    // No conformer (or transient upstream failure): degrade to the
                    // flat depiction on the same dark canvas, not the white PNG.
                    show("2d");
                    return;
                }
                // The PubChem PNG remains the no-WebGL / no-SDF fallback.
                mount.hidden = true;
                image.hidden = false;
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
