(function () {
    var form = document.getElementById("receipt-form");
    var dropzone = document.getElementById("receipt-dropzone");
    var input = document.getElementById("receipt");
    var filenameEl = document.getElementById("receipt-filename");

    if (!form || !dropzone || !input) {
        return;
    }

    var submitButton = form.querySelector(".receipt-submit");

    function showFilename(file) {
        if (filenameEl && file) {
            filenameEl.textContent = file.name;
        }
    }

    dropzone.addEventListener("dragover", function (event) {
        event.preventDefault();
        dropzone.classList.add("receipt-dropzone-active");
    });

    dropzone.addEventListener("dragleave", function () {
        dropzone.classList.remove("receipt-dropzone-active");
    });

    dropzone.addEventListener("drop", function (event) {
        event.preventDefault();
        dropzone.classList.remove("receipt-dropzone-active");
        if (event.dataTransfer && event.dataTransfer.files.length) {
            input.files = event.dataTransfer.files;
            showFilename(input.files[0]);
            form.submit();
        }
    });

    input.addEventListener("change", function () {
        if (input.files.length) {
            showFilename(input.files[0]);
            form.submit();
        }
    });

    form.addEventListener("submit", function () {
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = "Reading receipt…";
        }
    });
})();
