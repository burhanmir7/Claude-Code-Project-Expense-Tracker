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

    if (typeof Chart === "undefined") {
        return;
    }

    var monthlyCanvas = document.getElementById("monthly-chart");
    var monthlyData = readJSON(monthlyCanvas, "data-monthly");
    if (monthlyCanvas && monthlyData) {
        new Chart(monthlyCanvas, {
            type: "bar",
            data: {
                labels: monthlyData.map(function (row) { return monthLabel(row.month); }),
                datasets: [{
                    label: "Spending",
                    data: monthlyData.map(function (row) { return row.total; }),
                    backgroundColor: categoryColor("Food")
                }]
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } }
            }
        });
    }

    var categoryCanvas = document.getElementById("category-chart");
    var categoryData = readJSON(categoryCanvas, "data-categories");
    if (categoryCanvas && categoryData && categoryData.length > 0) {
        var ordered = CATEGORY_ORDER.filter(function (name) {
            return categoryData.some(function (row) { return row.name === name; });
        });
        var amounts = ordered.map(function (name) {
            var match = categoryData.filter(function (row) { return row.name === name; })[0];
            return match ? match.amount : 0;
        });

        new Chart(categoryCanvas, {
            type: "doughnut",
            data: {
                labels: ordered,
                datasets: [{
                    data: amounts,
                    backgroundColor: ordered.map(categoryColor)
                }]
            },
            options: {
                plugins: { legend: { position: "bottom" } }
            }
        });
    }
})();
