// Search-box autocomplete — PubChem term suggestions via /suggest.
// Suggestions are accelerators only: free-text submit always wins, so
// research-chem slang PubChem doesn't know still reaches the full resolver.
document.addEventListener("DOMContentLoaded", () => {
    const input = document.querySelector(".search input[name=q]");
    if (!input) {
        return;
    }

    const list = document.createElement("ul");
    list.className = "suggest-list";
    list.hidden = true;
    input.parentElement.appendChild(list);

    let items = [];
    let active = -1;
    let timer = null;

    const close = () => {
        list.hidden = true;
        list.replaceChildren();
        items = [];
        active = -1;
    };

    const select = (index) => {
        const term = items[index];
        if (term) {
            window.location.href = `/compound/${encodeURIComponent(term)}`;
        }
    };

    const render = () => {
        list.replaceChildren(
            ...items.map((term, i) => {
                const li = document.createElement("li");
                li.textContent = term;
                li.className = i === active ? "active" : "";
                li.addEventListener("mousedown", (event) => {
                    event.preventDefault();
                    select(i);
                });
                return li;
            }),
        );
        list.hidden = items.length === 0;
    };

    const fetchSuggestions = async (query) => {
        try {
            const resp = await fetch(`/suggest?q=${encodeURIComponent(query)}`);
            if (!resp.ok) {
                return;
            }
            if (input.value.trim() !== query) {
                return;
            }
            items = await resp.json();
            active = -1;
            render();
        } catch {
            // suggestions are best-effort; a failed fetch just shows nothing
        }
    };

    input.addEventListener("input", () => {
        const query = input.value.trim();
        clearTimeout(timer);
        if (query.length < 2) {
            close();
            return;
        }
        timer = setTimeout(() => fetchSuggestions(query), 150);
    });

    input.addEventListener("keydown", (event) => {
        if (list.hidden) {
            return;
        }
        if (event.key === "ArrowDown") {
            event.preventDefault();
            active = (active + 1) % items.length;
            render();
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            active = (active - 1 + items.length) % items.length;
            render();
        } else if (event.key === "Enter" && active >= 0) {
            event.preventDefault();
            select(active);
        } else if (event.key === "Escape") {
            close();
        }
    });

    input.addEventListener("blur", close);
});
