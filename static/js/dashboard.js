(function () {
    var CATEGORY_ORDER = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"];
    var MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    function readJSON(el, attr) {
        if (!el) {
            return null;
        }
        var raw = el.getAttribute(attr);
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (e) {
            return null;
        }
    }

    function monthLabel(ym) {
        var parts = ym.split("-");
        var monthIndex = parseInt(parts[1], 10) - 1;
        return MONTH_LABELS[monthIndex] + " '" + parts[0].slice(2);
    }

    function categoryColor(name) {
        var root = document.documentElement;
        var varName = "--cat-" + name.toLowerCase();
        var value = getComputedStyle(root).getPropertyValue(varName);
        return value ? value.trim() : "#999999";
    }

    function formatRupees(amount) {
        return "₹" + amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function closeDropdown(toggle, dropdown) {
        dropdown.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
    }

    function wireTile(tile) {
        var accounts = readJSON(tile, "data-accounts");
        var toggle = tile.querySelector(".tile-caret");
        var dropdown = tile.querySelector(".tile-dropdown");
        var figure = tile.querySelector(".tile-figure");
        if (!accounts || !toggle || !dropdown || !figure) {
            return;
        }

        toggle.addEventListener("click", function (event) {
            event.stopPropagation();
            var isOpen = !dropdown.hidden;
            if (isOpen) {
                closeDropdown(toggle, dropdown);
            } else {
                dropdown.hidden = false;
                toggle.setAttribute("aria-expanded", "true");
            }
        });

        document.addEventListener("click", function () {
            closeDropdown(toggle, dropdown);
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeDropdown(toggle, dropdown);
            }
        });

        var options = dropdown.querySelectorAll(".tile-dropdown-option");
        for (var i = 0; i < options.length; i++) {
            options[i].addEventListener("click", function (event) {
                event.stopPropagation();
                var id = event.currentTarget.getAttribute("data-account-id");
                if (id === "all") {
                    var total = accounts.reduce(function (sum, a) { return sum + a.balance; }, 0);
                    figure.textContent = formatRupees(total);
                } else {
                    var selected = accounts.filter(function (a) { return String(a.id) === id; })[0];
                    figure.textContent = formatRupees(selected ? selected.balance : 0);
                }
                closeDropdown(toggle, dropdown);
            });
        }
    }

    var tiles = document.querySelectorAll(".tile[data-accounts]");
    for (var i = 0; i < tiles.length; i++) {
        wireTile(tiles[i]);
    }
})();
