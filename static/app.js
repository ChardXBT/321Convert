"use strict";

(() => {
    const REGISTRY = JSON.parse(document.getElementById("registry").textContent);
    const MAX_BYTES = REGISTRY.max_upload_mb * 1024 * 1024;

    const elements = {
        workspace: document.querySelector(".workspace"),
        notice: document.getElementById("notice"),
        noticeText: document.getElementById("noticeText"),
        dropZone: document.getElementById("dropZone"),
        fileInput: document.getElementById("fileInput"),
        fileList: document.getElementById("fileList"),
        addMore: document.getElementById("addMore"),
        options: document.getElementById("options"),
        fields: {
            quality: document.getElementById("fieldQuality"),
            max_dimension: document.getElementById("fieldMaxDimension"),
            sheet_name: document.getElementById("fieldSheetName"),
            title: document.getElementById("fieldTitle"),
        },
        inputs: {
            quality: document.getElementById("optQuality"),
            qualityValue: document.getElementById("optQualityValue"),
            max_dimension: document.getElementById("optMaxDimension"),
            sheet_name: document.getElementById("optSheetName"),
            title: document.getElementById("optTitle"),
        },
        summary: document.getElementById("summary"),
        clearAll: document.getElementById("clearAll"),
        downloadAll: document.getElementById("downloadAll"),
        convertAll: document.getElementById("convertAll"),
        themeToggle: document.getElementById("themeToggle"),
    };

    const state = { rows: [], running: false };
    const lastTarget = {};
    let nextId = 1;
    let dragDepth = 0;

    /* --- helpers ------------------------------------------------------------ */

    const el = (tag, className, text) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    };

    const icon = (id) => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("class", "icon");
        svg.setAttribute("aria-hidden", "true");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttribute("href", `#${id}`);
        svg.appendChild(use);
        return svg;
    };

    const extOf = (name) => {
        const dot = name.lastIndexOf(".");
        return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
    };

    const stemOf = (name) => {
        const dot = name.lastIndexOf(".");
        return dot <= 0 ? name : name.slice(0, dot);
    };

    const familyFor = (ext) =>
        REGISTRY.families.find((family) => family.extensions.includes(ext)) || null;

    const formatBytes = (n) => {
        if (n < 1024) return `${n} B`;
        if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
        return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    };

    const optionAppliesTo = (option, familyId, target) => {
        if (option.outputs !== null && !option.outputs.includes(target)) return false;
        if (option.families !== null && !option.families.includes(familyId)) return false;
        return true;
    };

    const optionsForRow = (row) =>
        Object.keys(REGISTRY.options).filter((id) =>
            optionAppliesTo(REGISTRY.options[id], row.family.id, row.target),
        );

    const convertibleRows = () => state.rows.filter((row) => row.status !== "unsupported");

    const pendingRows = () =>
        state.rows.filter((row) => row.status === "ready" || row.status === "error");

    /* --- notice / summary / buttons ------------------------------------------ */

    const showNotice = (text) => {
        elements.noticeText.textContent = text;
        elements.notice.hidden = false;
    };

    const hideNotice = () => {
        elements.notice.hidden = true;
    };

    const updateSummary = (current, total) => {
        let text = "";
        if (state.running && total) {
            text = `Converting ${current} of ${total}…`;
        } else if (state.rows.length) {
            const parts = [];
            const count = (status) => state.rows.filter((r) => r.status === status).length;
            const ready = count("ready");
            const done = count("done");
            const failed = count("error");
            const unsupported = count("unsupported");
            if (ready) parts.push(ready === 1 ? "1 file ready" : `${ready} files ready`);
            if (done) parts.push(`${done} converted`);
            if (failed) parts.push(`${failed} failed`);
            if (unsupported) parts.push(`${unsupported} unsupported`);
            text = parts.join(" · ");
        }
        elements.summary.textContent = text;

        const pending = pendingRows().length;
        elements.convertAll.disabled = state.running || pending === 0;
        elements.convertAll.textContent = state.running
            ? "Converting…"
            : pending > 1
              ? `Convert ${pending} files`
              : "Convert";
        elements.clearAll.hidden = state.rows.length === 0;
        elements.downloadAll.hidden =
            state.rows.filter((r) => r.status === "done").length < 2;
        document
            .querySelectorAll(".file-row[data-status='error'] .retry-button")
            .forEach((button) => {
                button.disabled = state.running;
            });
    };

    const updateOptions = () => {
        const applicable = {};
        convertibleRows().forEach((row) => {
            optionsForRow(row).forEach((id) => {
                applicable[id] = true;
            });
        });
        let any = false;
        Object.keys(elements.fields).forEach((id) => {
            const show = Boolean(applicable[id]);
            elements.fields[id].hidden = !show;
            any = any || show;
        });
        elements.options.hidden = !any;
    };

    const refreshLayout = () => {
        const hasRows = state.rows.length > 0;
        elements.dropZone.hidden = hasRows;
        elements.addMore.hidden = !hasRows;
        updateOptions();
        updateSummary();
    };

    /* --- row DOM -------------------------------------------------------------- */

    const statusContent = (row) => {
        const box = row.elements.status;
        box.replaceChildren();
        if (row.status === "uploading") {
            const progress = el("div", "progress");
            progress.setAttribute("role", "progressbar");
            progress.setAttribute("aria-valuenow", String(row.progress));
            const bar = el("span", "bar");
            bar.style.width = `${row.progress}%`;
            progress.appendChild(bar);
            box.appendChild(progress);
            box.appendChild(el("span", "status-text", `Uploading ${row.progress}%`));
        } else if (row.status === "converting") {
            const indeterminate = el("div", "progress indeterminate");
            indeterminate.appendChild(el("span", "bar"));
            box.appendChild(indeterminate);
            box.appendChild(el("span", "status-text", "Converting…"));
        } else if (row.status === "done") {
            const link = el("a", "download-button");
            link.href = row.resultUrl;
            link.setAttribute("download", row.resultName);
            link.appendChild(icon("i-download"));
            link.appendChild(document.createTextNode("Download"));
            box.appendChild(link);
        } else if (row.status === "error") {
            const retry = el("button", "retry-button");
            retry.type = "button";
            retry.disabled = state.running;
            retry.appendChild(icon("i-retry"));
            retry.appendChild(document.createTextNode("Retry"));
            retry.addEventListener("click", () => {
                if (state.running) return;
                state.running = true;
                updateSummary();
                convertRow(row).then(() => {
                    state.running = false;
                    updateSummary();
                });
            });
            box.appendChild(retry);
        }
    };

    const renderRow = (row) => {
        row.elements.item.dataset.status = row.status;
        row.elements.notes.textContent = row.notes.join(" ");
        row.elements.notes.hidden = row.notes.length === 0;
        row.elements.error.textContent = row.error || "";
        row.elements.error.hidden = !row.error;
        statusContent(row);
    };

    const buildRow = (row) => {
        const item = el("li", "file-row");
        item.dataset.id = String(row.id);
        item.dataset.status = row.status;

        const badge = el("span", "badge", row.badge);
        const main = el("div", "file-main");
        const name = el("span", "file-name", row.file.name);
        name.title = row.file.name;
        const meta = el("span", "file-meta", row.meta);
        const notes = el("p", "file-notes");
        notes.hidden = true;
        const error = el("p", "file-error");
        error.setAttribute("role", "status");
        error.hidden = true;
        main.appendChild(name);
        main.appendChild(meta);
        main.appendChild(notes);
        main.appendChild(error);

        item.appendChild(badge);
        item.appendChild(main);

        const toField = el("label", "to-field");
        if (row.family) {
            const to = el("span", null, "to");
            to.setAttribute("aria-hidden", "true");
            toField.appendChild(to);
            const select = document.createElement("select");
            select.setAttribute("aria-label", `Convert ${row.file.name} to`);
            row.family.outputs.forEach((output) => {
                const option = document.createElement("option");
                option.value = output.ext;
                option.textContent = output.label;
                select.appendChild(option);
            });
            select.value = row.target;
            select.addEventListener("change", () => {
                if (row.resultUrl) {
                    URL.revokeObjectURL(row.resultUrl);
                    row.resultUrl = null;
                }
                row.target = select.value;
                lastTarget[row.family.id] = select.value;
                row.status = "ready";
                row.error = "";
                row.notes = [];
                updateOptions();
                updateSummary();
                renderRow(row);
            });
            row.elements.select = select;
            toField.appendChild(select);
        } else {
            toField.hidden = true;
        }
        item.appendChild(toField);

        const status = el("div", "file-status");
        item.appendChild(status);

        const remove = el("button", "icon-button remove");
        remove.type = "button";
        remove.setAttribute("aria-label", `Remove ${row.file.name}`);
        remove.appendChild(icon("i-x"));
        remove.addEventListener("click", () => removeRow(row));
        item.appendChild(remove);

        row.elements.item = item;
        row.elements.status = status;
        row.elements.notes = notes;
        row.elements.error = error;
        renderRow(row);
        return item;
    };

    /* --- file intake ------------------------------------------------------------ */

    const defaultTarget = (family, ext) => {
        const remembered = lastTarget[family.id];
        if (
            remembered &&
            remembered !== ext &&
            family.outputs.some((output) => output.ext === remembered)
        ) {
            return remembered;
        }
        const first = family.outputs.find((output) => output.ext !== ext);
        return (first || family.outputs[0]).ext;
    };

    const addFiles = (fileList) => {
        let added = false;
        Array.from(fileList).forEach((file) => {
            const duplicate = state.rows.some(
                (row) =>
                    row.file &&
                    row.file.name === file.name &&
                    row.file.size === file.size &&
                    row.file.lastModified === file.lastModified,
            );
            if (duplicate) return;

            const ext = extOf(file.name);
            const family = familyFor(ext);
            const row = {
                id: nextId++,
                file,
                ext,
                family,
                target: family ? defaultTarget(family, ext) : "",
                status: "ready",
                progress: 0,
                resultUrl: null,
                resultName: "",
                notes: [],
                error: "",
                badge: ext ? ext.toUpperCase().slice(0, 5) : "?",
                meta: family
                    ? `${formatBytes(file.size)} · ${family.label}`
                    : "Unsupported file type",
                elements: {},
            };
            if (file.size > MAX_BYTES) {
                row.family = null;
                row.status = "unsupported";
                row.error = `Larger than ${REGISTRY.max_upload_mb} MB.`;
                row.meta = `${formatBytes(file.size)} · Unsupported file type`;
            } else if (!family) {
                row.status = "unsupported";
                row.badge = "?";
                row.error = `.${ext || "?"} files can't be converted here.`;
            }
            state.rows.push(row);
            elements.fileList.appendChild(buildRow(row));
            added = true;
        });
        if (added) refreshLayout();
    };

    const removeRow = (row) => {
        if (row.resultUrl) URL.revokeObjectURL(row.resultUrl);
        state.rows = state.rows.filter((r) => r !== row);
        row.elements.item.remove();
        refreshLayout();
    };

    /* --- conversion ------------------------------------------------------------- */

    const downloadName = (xhr, fallback) => {
        const header = xhr.getResponseHeader("Content-Disposition") || "";
        const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
        if (star) {
            try {
                return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
            } catch (error) {
                return fallback;
            }
        }
        const plain = /filename="?([^";]+)"?/i.exec(header);
        return plain ? plain[1] : fallback;
    };

    const convertRow = (row) =>
        new Promise((resolve) => {
            row.status = "uploading";
            row.progress = 0;
            row.error = "";
            row.notes = [];
            renderRow(row);

            const data = new FormData();
            data.append("file", row.file);
            data.append("target", row.target);
            optionsForRow(row).forEach((id) => {
                const input = elements.inputs[id];
                if (input && input.value !== "") data.append(id, input.value);
            });

            const xhr = new XMLHttpRequest();
            xhr.open("POST", "/api/convert");
            xhr.responseType = "blob";
            xhr.timeout = 180000;

            xhr.upload.onprogress = (event) => {
                if (!event.lengthComputable) return;
                row.progress = Math.max(1, Math.round((event.loaded / event.total) * 100));
                if (event.loaded >= event.total) row.status = "converting";
                renderRow(row);
            };
            xhr.upload.onload = () => {
                row.status = "converting";
                renderRow(row);
            };

            xhr.onload = () => {
                const blob = xhr.response;
                if (xhr.status === 200) {
                    if (row.resultUrl) URL.revokeObjectURL(row.resultUrl);
                    row.resultUrl = URL.createObjectURL(blob);
                    row.resultName = downloadName(xhr, `${stemOf(row.file.name)}.${row.target}`);
                    try {
                        row.notes = JSON.parse(xhr.getResponseHeader("X-Conversion-Notes") || "[]");
                    } catch (error) {
                        row.notes = [];
                    }
                    row.status = "done";
                    renderRow(row);
                    resolve();
                    return;
                }
                Promise.resolve(blob.text()).then((text) => {
                    let message = `Conversion failed (HTTP ${xhr.status}).`;
                    try {
                        const parsed = JSON.parse(text);
                        if (parsed && parsed.error) message = parsed.error;
                    } catch (error) {
                        /* keep generic message */
                    }
                    row.error = message;
                    row.status = "error";
                    if (xhr.status === 429 || xhr.status === 503) showNotice(message);
                    renderRow(row);
                    resolve();
                });
            };

            xhr.onerror = () => {
                row.error = "Couldn't reach the server. Check your connection and try again.";
                row.status = "error";
                renderRow(row);
                resolve();
            };
            xhr.ontimeout = () => {
                row.error = "The conversion timed out.";
                row.status = "error";
                renderRow(row);
                resolve();
            };

            xhr.send(data);
        });

    const convertAll = () => {
        if (state.running) return;
        // fieldset.checkValidity() is always true (fieldsets are never
        // validation candidates), so check each visible option input.
        if (!elements.options.hidden) {
            const invalid = Object.keys(elements.fields)
                .filter((id) => !elements.fields[id].hidden)
                .map((id) => elements.inputs[id])
                .find((input) => input && !input.checkValidity());
            if (invalid) {
                invalid.reportValidity();
                return;
            }
        }
        const queue = pendingRows();
        if (!queue.length) return;
        state.running = true;
        hideNotice();
        let index = 0;
        updateSummary(index + 1, queue.length);
        const step = () => {
            if (index >= queue.length) {
                state.running = false;
                updateSummary();
                return;
            }
            index += 1;
            updateSummary(index, queue.length);
            convertRow(queue[index - 1]).then(step);
        };
        step();
    };

    /* --- events ----------------------------------------------------------------- */

    elements.dropZone.addEventListener("click", () => elements.fileInput.click());
    elements.addMore.addEventListener("click", () => elements.fileInput.click());
    elements.fileInput.addEventListener("change", () => {
        addFiles(elements.fileInput.files);
        elements.fileInput.value = "";
    });

    elements.workspace.addEventListener("dragenter", (event) => {
        event.preventDefault();
        dragDepth += 1;
        elements.workspace.classList.add("dragging");
    });
    elements.workspace.addEventListener("dragover", (event) => {
        event.preventDefault();
    });
    elements.workspace.addEventListener("dragleave", (event) => {
        event.preventDefault();
        dragDepth = Math.max(0, dragDepth - 1);
        if (dragDepth === 0) elements.workspace.classList.remove("dragging");
    });
    elements.workspace.addEventListener("drop", (event) => {
        event.preventDefault();
        dragDepth = 0;
        elements.workspace.classList.remove("dragging");
        addFiles(event.dataTransfer.files);
    });

    elements.inputs.quality.addEventListener("input", () => {
        elements.inputs.qualityValue.value = elements.inputs.quality.value;
    });

    elements.convertAll.addEventListener("click", convertAll);

    elements.clearAll.addEventListener("click", () => {
        state.rows.forEach((row) => {
            if (row.resultUrl) URL.revokeObjectURL(row.resultUrl);
        });
        state.rows = [];
        elements.fileList.replaceChildren();
        refreshLayout();
    });

    elements.downloadAll.addEventListener("click", () => {
        const links = state.rows
            .filter((row) => row.status === "done")
            .map((row) => row.elements.status.querySelector("a.download-button"));
        links.forEach((link, index) => {
            setTimeout(() => {
                if (link) link.click();
            }, index * 350);
        });
    });

    window.addEventListener("beforeunload", (event) => {
        if (state.running) {
            event.preventDefault();
            event.returnValue = "";
        }
    });

    /* --- theme -------------------------------------------------------------------- */

    const applyTheme = (theme) => {
        document.documentElement.setAttribute("data-theme", theme);
        const dark = theme === "dark";
        elements.themeToggle.setAttribute("aria-pressed", String(dark));
        elements.themeToggle.setAttribute(
            "aria-label",
            dark ? "Switch to light theme" : "Switch to dark theme",
        );
        elements.themeToggle.querySelector(".icon-sun").hidden = dark;
        elements.themeToggle.querySelector(".icon-moon").hidden = !dark;
    };

    applyTheme(document.documentElement.getAttribute("data-theme") || "light");

    elements.themeToggle.addEventListener("click", () => {
        const next =
            document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        applyTheme(next);
        try {
            localStorage.setItem("theme", next);
        } catch (error) {
            /* private mode: theme still applies for this session */
        }
    });

    /* --- dialogs -------------------------------------------------------------------- */

    document.querySelectorAll("[data-dialog-open]").forEach((trigger) => {
        trigger.addEventListener("click", (event) => {
            event.preventDefault();
            const dialog = document.getElementById(trigger.dataset.dialogOpen);
            if (dialog) dialog.showModal();
        });
    });
    document.querySelectorAll("[data-dialog-close]").forEach((button) => {
        button.addEventListener("click", () => {
            button.closest("dialog").close();
        });
    });
    document.querySelectorAll("dialog").forEach((dialog) => {
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) dialog.close();
        });
    });

    updateSummary();
})();
