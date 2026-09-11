(function () {
    var STORAGE_KEY = "spendly-chat-open";

    var drawer = document.getElementById("chat-drawer");
    if (!drawer) {
        return;
    }

    var toggleButton = document.getElementById("chat-toggle");
    var closeButton = document.getElementById("chat-close");
    var clearButton = document.getElementById("chat-clear");
    var messagesEl = document.getElementById("chat-messages");
    var statusEl = document.getElementById("chat-status");
    var typingEl = document.getElementById("chat-typing");
    var formEl = document.getElementById("chat-form");
    var inputEl = document.getElementById("chat-input");

    var quickstartForm = document.getElementById("profile-chat-quickstart-form");
    var quickstartInput = document.getElementById("profile-chat-quickstart-input");
    var attachButton = document.getElementById("chat-attach-button");
    var attachInput = document.getElementById("chat-attach-input");
    var quickstartAttachButton = document.getElementById("profile-chat-quickstart-attach-button");
    var quickstartAttachInput = document.getElementById("profile-chat-quickstart-attach");

    var historyUrl = drawer.getAttribute("data-history-url");
    var sendUrl = drawer.getAttribute("data-send-url");
    var receiptUrl = drawer.getAttribute("data-receipt-url");
    var expensesUrl = drawer.getAttribute("data-expenses-url");

    function setOpen(isOpen) {
        if (isOpen) {
            drawer.classList.remove("chat-drawer-collapsed");
        } else {
            drawer.classList.add("chat-drawer-collapsed");
        }
        if (toggleButton) {
            toggleButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }
        try {
            localStorage.setItem(STORAGE_KEY, isOpen ? "open" : "closed");
        } catch (e) {
            /* localStorage unavailable */
        }
    }

    function isOpenStored() {
        try {
            return localStorage.getItem(STORAGE_KEY) === "open";
        } catch (e) {
            return false;
        }
    }

    function scrollToBottom() {
        if (messagesEl) {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }
    }

    function clearEmptyState() {
        if (!messagesEl) {
            return;
        }
        var empty = messagesEl.querySelector(".chat-empty");
        if (empty) {
            empty.remove();
        }
    }

    function resetMessages() {
        if (!messagesEl) {
            return;
        }
        while (messagesEl.firstChild) {
            messagesEl.removeChild(messagesEl.firstChild);
        }
        var empty = document.createElement("p");
        empty.className = "chat-empty";
        empty.textContent = "Ask me about your spending.";
        messagesEl.appendChild(empty);
    }

    function appendBubble(role, text) {
        if (!messagesEl) {
            return;
        }
        clearEmptyState();
        var bubble = document.createElement("div");
        if (role === "user") {
            bubble.className = "chat-bubble-user";
        } else if (role === "error") {
            bubble.className = "chat-bubble-error";
        } else {
            bubble.className = "chat-bubble-assistant";
        }
        bubble.textContent = text;
        messagesEl.appendChild(bubble);
        scrollToBottom();
    }

    function appendReceiptCard(replyText, expense, saveUrl) {
        if (!messagesEl) {
            return;
        }
        clearEmptyState();

        appendBubble("assistant", replyText);

        var card = document.createElement("div");
        card.className = "chat-receipt-card";

        var eyebrow = document.createElement("div");
        eyebrow.className = "chat-receipt-eyebrow";
        eyebrow.textContent = "Receipt found";
        card.appendChild(eyebrow);

        var fields = [
            { label: "Merchant", value: expense.description || "—" },
            { label: "Amount", value: "₹" + expense.amount, className: "chat-receipt-amount" },
            { label: "Category", value: expense.category },
            { label: "Date", value: expense.date }
        ];
        fields.forEach(function (field) {
            var row = document.createElement("div");
            row.className = "chat-receipt-row";

            var label = document.createElement("span");
            label.className = "chat-receipt-row-label";
            label.textContent = field.label;

            var value = document.createElement("span");
            value.className = "chat-receipt-row-value" + (field.className ? " " + field.className : "");
            value.textContent = field.value;

            row.appendChild(label);
            row.appendChild(value);
            card.appendChild(row);
        });

        var saveButton = document.createElement("button");
        saveButton.type = "button";
        saveButton.className = "chat-receipt-save";
        saveButton.textContent = "Save as expense";
        saveButton.addEventListener("click", function () {
            saveButton.disabled = true;
            saveButton.textContent = "Saving…";

            fetch(saveUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(expense)
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (result.ok) {
                        appendBubble("assistant", "Saved — reloading to update your totals…");
                        window.location.reload();
                    } else {
                        saveButton.disabled = false;
                        saveButton.textContent = "Save as expense";
                        appendBubble("error", result.data.error || "Something went wrong.");
                    }
                })
                .catch(function () {
                    saveButton.disabled = false;
                    saveButton.textContent = "Save as expense";
                    appendBubble("error", "Something went wrong.");
                });
        });
        card.appendChild(saveButton);

        messagesEl.appendChild(card);
        scrollToBottom();
    }

    function scanReceipt(file) {
        appendBubble("user", "📎 " + file.name);
        setInputDisabled(true);
        setStatus("Reading receipt…");

        var formData = new FormData();
        formData.append("receipt", file);

        fetch(receiptUrl, {
            method: "POST",
            body: formData
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                setInputDisabled(false);
                setStatus("");
                if (result.ok) {
                    appendReceiptCard(result.data.reply, result.data.expense, expensesUrl);
                } else {
                    appendBubble("error", result.data.error || "Something went wrong.");
                }
            })
            .catch(function () {
                setInputDisabled(false);
                setStatus("");
                appendBubble("error", "Something went wrong.");
            });
    }

    function setStatus(text) {
        if (statusEl) {
            if (text) {
                statusEl.textContent = text;
                statusEl.hidden = false;
            } else {
                statusEl.hidden = true;
                statusEl.textContent = "";
            }
        }
        if (typingEl) {
            typingEl.hidden = !text;
        }
    }

    function setInputDisabled(disabled) {
        if (inputEl) {
            inputEl.disabled = disabled;
        }
    }

    function loadHistory() {
        if (!historyUrl) {
            return;
        }
        fetch(historyUrl)
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                var messages = data && data.messages ? data.messages : [];
                if (messages.length === 0) {
                    return;
                }
                clearEmptyState();
                for (var i = 0; i < messages.length; i++) {
                    appendBubble(messages[i].role, messages[i].content);
                }
            })
            .catch(function () {
                /* history load failed; leave empty state as-is */
            });
    }

    function sendMessage(text) {
        appendBubble("user", text);
        setInputDisabled(true);
        setStatus("Thinking…");

        fetch(sendUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                setInputDisabled(false);
                setStatus("");
                if (result.ok) {
                    appendBubble("assistant", result.data.reply);
                    if (result.data.refresh) {
                        setTimeout(function () {
                            window.location.reload();
                        }, 600);
                    }
                } else {
                    appendBubble("error", result.data.error || "Something went wrong.");
                }
            })
            .catch(function () {
                setInputDisabled(false);
                setStatus("");
                appendBubble("error", "Something went wrong.");
            });
    }

    function trySend() {
        if (!inputEl) {
            return;
        }
        var text = inputEl.value.trim();
        if (!text) {
            return;
        }
        inputEl.value = "";
        sendMessage(text);
    }

    if (toggleButton) {
        toggleButton.addEventListener("click", function () {
            setOpen(drawer.classList.contains("chat-drawer-collapsed"));
        });
    }

    if (closeButton) {
        closeButton.addEventListener("click", function () {
            setOpen(false);
        });
    }

    if (clearButton) {
        clearButton.addEventListener("click", function () {
            if (!confirm("Clear this conversation?")) {
                return;
            }
            fetch(historyUrl, { method: "DELETE" })
                .then(function () {
                    resetMessages();
                })
                .catch(function () {
                    /* clear failed; leave existing messages visible */
                });
        });
    }

    if (formEl) {
        formEl.addEventListener("submit", function (event) {
            event.preventDefault();
            trySend();
        });
    }

    if (inputEl) {
        inputEl.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                trySend();
            }
        });
    }

    if (quickstartForm) {
        quickstartForm.addEventListener("submit", function (event) {
            event.preventDefault();
            if (!quickstartInput) {
                return;
            }
            var text = quickstartInput.value.trim();
            if (!text) {
                return;
            }
            quickstartInput.value = "";
            setOpen(true);
            sendMessage(text);
        });
    }

    if (attachButton && attachInput) {
        attachButton.addEventListener("click", function () {
            attachInput.click();
        });
        attachInput.addEventListener("change", function () {
            if (attachInput.files.length) {
                var file = attachInput.files[0];
                attachInput.value = "";
                setOpen(true);
                scanReceipt(file);
            }
        });
    }

    if (quickstartAttachButton && quickstartAttachInput) {
        quickstartAttachButton.addEventListener("click", function () {
            quickstartAttachInput.click();
        });
        quickstartAttachInput.addEventListener("change", function () {
            if (quickstartAttachInput.files.length) {
                var file = quickstartAttachInput.files[0];
                quickstartAttachInput.value = "";
                setOpen(true);
                scanReceipt(file);
            }
        });
    }

    var quickChips = drawer.querySelectorAll(".chat-quick-chip");
    for (var qi = 0; qi < quickChips.length; qi++) {
        quickChips[qi].addEventListener("click", function (event) {
            var question = event.currentTarget.getAttribute("data-question");
            if (!question) {
                return;
            }
            setOpen(true);
            sendMessage(question);
        });
    }

    if (isOpenStored()) {
        setOpen(true);
    }

    loadHistory();
})();
