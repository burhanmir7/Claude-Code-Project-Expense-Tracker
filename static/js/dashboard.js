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

(function () {
    var SVG_NS = "http://www.w3.org/2000/svg";
    var CATEGORY_ORDER = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"];

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
        var MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        var parts = ym.split("-");
        var monthIndex = parseInt(parts[1], 10) - 1;
        return MONTH_LABELS[monthIndex] + " '" + parts[0].slice(2);
    }

    function categoryColor(name) {
        var root = document.documentElement;
        var value = getComputedStyle(root).getPropertyValue("--cat-" + name.toLowerCase());
        return value ? value.trim() : "#999999";
    }

    function formatRupees(amount) {
        return "₹" + amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function svgEl(tag, attrs) {
        var el = document.createElementNS(SVG_NS, tag);
        for (var key in attrs) {
            if (Object.prototype.hasOwnProperty.call(attrs, key)) {
                el.setAttribute(key, attrs[key]);
            }
        }
        return el;
    }

    function renderMonthlyChart(container, data) {
        if (!data || data.length === 0) {
            return;
        }
        var width = 620;
        var height = 190;
        var maxTotal = Math.max.apply(null, data.map(function (row) { return row.total; })) || 1;
        var barWidth = Math.min(62, (width / data.length) * 0.6);
        var gap = width / data.length;

        var svg = svgEl("svg", { viewBox: "0 0 " + width + " " + height, role: "img", "aria-label": "Monthly spending" });

        for (var g = 1; g <= 4; g++) {
            var y = 160 - (g * 160 / 4);
            svg.appendChild(svgEl("line", { x1: 0, x2: width, y1: y, y2: y, class: "chart-grid-line" }));
        }

        var meta = document.getElementById("monthly-chart-meta");
        var originalMetaText = meta ? meta.textContent : "";

        data.forEach(function (row, i) {
            var barHeight = (row.total / maxTotal) * 150;
            var x = i * gap + (gap - barWidth) / 2;
            var y = 160 - barHeight;
            var rect = svgEl("rect", {
                x: x, y: y, width: barWidth, height: barHeight, rx: 4,
                class: "chart-bar",
            });
            rect.addEventListener("mouseenter", function () {
                if (meta) {
                    meta.textContent = monthLabel(row.month) + " · " + formatRupees(row.total);
                }
            });
            rect.addEventListener("mouseleave", function () {
                if (meta) {
                    meta.textContent = originalMetaText;
                }
            });
            svg.appendChild(rect);
            svg.appendChild(svgEl("text", { x: x + barWidth / 2, y: 184, "text-anchor": "middle", class: "chart-bar-label" })).textContent = monthLabel(row.month);
        });

        container.appendChild(svg);
    }

    function renderCategoryChart(container, data) {
        if (!data || data.length === 0) {
            return;
        }
        var ordered = CATEGORY_ORDER.filter(function (name) {
            return data.some(function (row) { return row.name === name; });
        }).map(function (name) {
            return data.filter(function (row) { return row.name === name; })[0];
        });

        var wrap = document.createElement("div");
        wrap.className = "donut-wrap";

        var size = 116;
        var outerR = 52;
        var innerR = 34;
        var cx = size / 2;
        var cy = size / 2;
        var svg = svgEl("svg", { viewBox: "0 0 " + size + " " + size, role: "img", "aria-label": "Category breakdown" });

        var total = ordered.reduce(function (sum, row) { return sum + row.amount; }, 0);
        var angle = -90;
        var slices = [];

        ordered.forEach(function (row) {
            var sweep = Math.min((row.amount / total) * 360, 359.99);
            var startAngle = angle;
            var endAngle = angle + sweep;
            angle = endAngle;

            var path = svgEl("path", {
                d: donutArcPath(cx, cy, outerR, innerR, startAngle, endAngle),
                fill: categoryColor(row.name),
                class: "donut-slice",
            });
            svg.appendChild(path);
            slices.push({ path: path, row: row });
        });

        var centerLabel = svgEl("text", { x: cx, y: cy - 3, "text-anchor": "middle", class: "donut-center-text" });
        centerLabel.textContent = formatRupees(total);
        var centerSub = svgEl("text", { x: cx, y: cy + 11, "text-anchor": "middle", class: "donut-center-label" });
        centerSub.textContent = "Total out";
        svg.appendChild(centerLabel);
        svg.appendChild(centerSub);

        var legend = document.createElement("div");
        legend.className = "donut-legend";

        function setFocus(focusedRow) {
            slices.forEach(function (slice) {
                slice.path.classList.toggle("donut-slice-dimmed", focusedRow && slice.row.name !== focusedRow.name);
            });
            legend.querySelectorAll(".donut-legend-row").forEach(function (rowEl) {
                rowEl.classList.toggle("donut-legend-row-dimmed", focusedRow && rowEl.getAttribute("data-category") !== focusedRow.name);
            });
            if (focusedRow) {
                centerLabel.textContent = formatRupees(focusedRow.amount);
                centerSub.textContent = focusedRow.name;
            } else {
                centerLabel.textContent = formatRupees(total);
                centerSub.textContent = "Total out";
            }
        }

        function navigateToCategory(name) {
            var url = new URL(window.location.href);
            var current = url.searchParams.get("category");
            if (current === name) {
                url.searchParams.delete("category");
            } else {
                url.searchParams.set("category", name);
            }
            window.location.href = url.toString();
        }

        ordered.forEach(function (row, i) {
            var rowEl = document.createElement("button");
            rowEl.type = "button";
            rowEl.className = "donut-legend-row";
            rowEl.setAttribute("data-category", row.name);

            var swatch = document.createElement("span");
            swatch.className = "donut-legend-swatch";
            swatch.style.background = categoryColor(row.name);

            var name = document.createElement("span");
            name.className = "donut-legend-name";
            name.textContent = row.name;

            var pct = document.createElement("span");
            pct.className = "donut-legend-pct";
            pct.textContent = row.pct + "%";

            rowEl.appendChild(swatch);
            rowEl.appendChild(name);
            rowEl.appendChild(pct);
            rowEl.addEventListener("mouseenter", function () { setFocus(row); });
            rowEl.addEventListener("mouseleave", function () { setFocus(null); });
            rowEl.addEventListener("click", function () { navigateToCategory(row.name); });
            legend.appendChild(rowEl);

            slices[i].path.addEventListener("mouseenter", function () { setFocus(row); });
            slices[i].path.addEventListener("mouseleave", function () { setFocus(null); });
            slices[i].path.addEventListener("click", function () { navigateToCategory(row.name); });
        });

        wrap.appendChild(svg);
        wrap.appendChild(legend);
        container.appendChild(wrap);
    }

    function donutArcPath(cx, cy, outerR, innerR, startAngle, endAngle) {
        function point(radius, angleDeg) {
            var rad = (angleDeg * Math.PI) / 180;
            return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
        }
        var largeArc = endAngle - startAngle > 180 ? 1 : 0;
        var outerStart = point(outerR, startAngle);
        var outerEnd = point(outerR, endAngle);
        var innerStart = point(innerR, endAngle);
        var innerEnd = point(innerR, startAngle);
        return [
            "M", outerStart.x, outerStart.y,
            "A", outerR, outerR, 0, largeArc, 1, outerEnd.x, outerEnd.y,
            "L", innerStart.x, innerStart.y,
            "A", innerR, innerR, 0, largeArc, 0, innerEnd.x, innerEnd.y,
            "Z",
        ].join(" ");
    }

    var monthlyContainer = document.getElementById("monthly-chart");
    renderMonthlyChart(monthlyContainer, readJSON(monthlyContainer, "data-monthly"));

    var categoryContainer = document.getElementById("category-chart");
    renderCategoryChart(categoryContainer, readJSON(categoryContainer, "data-categories"));
})();

(function () {
    function showToast(message) {
        var existing = document.querySelector(".dashboard-toast");
        if (existing) {
            existing.remove();
        }
        var toast = document.createElement("div");
        toast.className = "dashboard-toast";
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () {
            toast.remove();
        }, 2200);
    }

    var addToggle = document.getElementById("profile-add-expense-toggle");
    var addRow = document.getElementById("profile-add-expense-row");
    if (addToggle && addRow) {
        addToggle.addEventListener("click", function () {
            addRow.hidden = !addRow.hidden;
        });
    }

    var cancelButton = document.getElementById("profile-add-expense-cancel");
    if (cancelButton && addRow) {
        cancelButton.addEventListener("click", function () {
            addRow.hidden = true;
        });
    }

    var saveButton = document.getElementById("profile-add-expense-save");
    if (saveButton) {
        saveButton.addEventListener("click", function () {
            var descriptionEl = document.getElementById("profile-add-expense-description");
            var amountEl = document.getElementById("profile-add-expense-amount");
            var categoryEl = document.getElementById("profile-add-expense-category");
            var dateEl = document.getElementById("profile-add-expense-date");

            var description = descriptionEl.value.trim();
            var amount = parseFloat(amountEl.value);

            if (!description || isNaN(amount) || amount <= 0) {
                showToast("Enter a description and a valid amount.");
                return;
            }

            fetch("/api/expenses", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    description: description,
                    amount: String(amount),
                    category: categoryEl.value,
                    date: dateEl.value || new Date().toISOString().slice(0, 10),
                }),
            })
                .then(function (response) {
                    if (!response.ok) {
                        return response
                            .json()
                            .catch(function () {
                                return null;
                            })
                            .then(function (data) {
                                throw new Error(data && data.error ? data.error : "Could not save the expense.");
                            });
                    }
                    return response;
                })
                .then(function () {
                    showToast("Expense added.");
                    setTimeout(function () {
                        window.location.reload();
                    }, 700);
                })
                .catch(function (err) {
                    showToast(err && err.message ? err.message : "Could not save the expense.");
                });
        });
    }

    var chips = document.querySelectorAll(".assistant-chip");
    var chatInput = document.getElementById("profile-chat-quickstart-input");
    var chatForm = document.getElementById("profile-chat-quickstart-form");
    for (var i = 0; i < chips.length; i++) {
        chips[i].addEventListener("click", function (event) {
            if (!chatInput || !chatForm) {
                return;
            }
            chatInput.value = event.currentTarget.getAttribute("data-question");
            if (chatForm.requestSubmit) {
                chatForm.requestSubmit();
            } else {
                chatForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
            }
        });
    }
})();

(function () {
    var trigger = document.querySelector(".dashboard-search-button");
    var root = document.getElementById("command-palette");
    if (!trigger || !root) {
        return;
    }

    var panel = root.querySelector(".command-palette-panel");
    var input = document.getElementById("command-palette-input");
    var listEl = document.getElementById("command-palette-list");
    var emptyEl = document.getElementById("command-palette-empty");
    var rows = Array.prototype.slice.call(listEl.querySelectorAll(".command-row"));
    var selectedIndex = 0;

    function visibleRows() {
        return rows.filter(function (row) { return !row.hidden; });
    }

    function highlight() {
        var visible = visibleRows();
        rows.forEach(function (row) { row.classList.remove("command-row-selected"); });
        if (visible.length) {
            selectedIndex = Math.max(0, Math.min(selectedIndex, visible.length - 1));
            visible[selectedIndex].classList.add("command-row-selected");
        }
    }

    function filterRows() {
        var q = input.value.trim().toLowerCase();
        var anyVisible = false;
        rows.forEach(function (row) {
            var label = row.querySelector(".command-row-label").textContent.toLowerCase();
            var matches = label.indexOf(q) !== -1;
            row.hidden = !matches;
            if (matches) {
                anyVisible = true;
            }
        });
        emptyEl.hidden = anyVisible;
        selectedIndex = 0;
        highlight();
    }

    function openPalette() {
        root.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
        input.value = "";
        filterRows();
        input.focus();
    }

    function closePalette() {
        root.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
    }

    trigger.addEventListener("click", function (event) {
        event.stopPropagation();
        if (root.hidden) {
            openPalette();
        } else {
            closePalette();
        }
    });

    panel.addEventListener("click", function (event) {
        event.stopPropagation();
    });

    document.addEventListener("click", function () {
        if (!root.hidden) {
            closePalette();
        }
    });

    document.addEventListener("keydown", function (event) {
        var isMeta = event.metaKey || event.ctrlKey;
        if (isMeta && event.key.toLowerCase() === "k") {
            event.preventDefault();
            if (root.hidden) {
                openPalette();
            } else {
                closePalette();
            }
            return;
        }
        if (root.hidden) {
            return;
        }
        if (event.key === "Escape") {
            closePalette();
        } else if (event.key === "ArrowDown") {
            event.preventDefault();
            selectedIndex += 1;
            highlight();
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            selectedIndex -= 1;
            highlight();
        } else if (event.key === "Enter") {
            event.preventDefault();
            var row = visibleRows()[selectedIndex];
            if (row) {
                closePalette();
                row.click();
            }
        }
    });

    input.addEventListener("input", filterRows);

    rows.forEach(function (row) {
        row.addEventListener("mouseenter", function () {
            selectedIndex = visibleRows().indexOf(row);
            highlight();
        });
    });

    var actionHandlers = {
        "add-expense": function () {
            var el = document.getElementById("profile-add-expense-toggle");
            if (el) {
                el.click();
            }
        },
        "scan-receipt": function () {
            var el = document.getElementById("profile-chat-quickstart-attach-button");
            if (el) {
                el.click();
            }
        },
        "ask-assistant": function () {
            var el = document.getElementById("profile-chat-quickstart-input");
            if (el) {
                el.focus();
            }
        },
        "toggle-theme": function () {
            var el = document.getElementById("theme-toggle");
            if (el) {
                el.click();
            }
        }
    };

    rows.forEach(function (row) {
        var action = row.getAttribute("data-command");
        if (action && actionHandlers[action]) {
            row.addEventListener("click", function () {
                actionHandlers[action]();
            });
        }
    });
})();
