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
    var formEl = document.getElementById("chat-form");
    var inputEl = document.getElementById("chat-input");

    var quickstartForm = document.getElementById("profile-chat-quickstart-form");
    var quickstartInput = document.getElementById("profile-chat-quickstart-input");

    var historyUrl = drawer.getAttribute("data-history-url");
    var sendUrl = drawer.getAttribute("data-send-url");

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

    function setStatus(text) {
        if (!statusEl) {
            return;
        }
        if (text) {
            statusEl.textContent = text;
            statusEl.hidden = false;
        } else {
            statusEl.hidden = true;
            statusEl.textContent = "";
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

    if (isOpenStored()) {
        setOpen(true);
    }

    loadHistory();
})();
