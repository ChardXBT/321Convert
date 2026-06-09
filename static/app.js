"use strict";

const notice = document.querySelector("#notice");
const result = document.querySelector("#result");
const downloadLink = document.querySelector("#downloadLink");
const imagePreview = document.querySelector("#imagePreview");
let resultUrl = null;

function showNotice(message, kind = "error") {
  notice.textContent = message;
  notice.className = `notice ${kind}`;
  notice.hidden = false;
}

function clearResult() {
  notice.hidden = true;
  result.hidden = true;
  imagePreview.hidden = true;
  if (resultUrl) URL.revokeObjectURL(resultUrl);
  resultUrl = null;
}

function downloadName(response) {
  const disposition = response.headers.get("content-disposition") || "";
  const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  return decodeURIComponent((utfMatch?.[1] || plainMatch?.[1] || "converted-file").replaceAll("+", " "));
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    clearResult();
    document.querySelectorAll(".tab").forEach((item) => {
      const selected = item === tab;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-selected", selected.toString());
      const panel = document.querySelector(`#${item.dataset.panel}`);
      panel.hidden = !selected;
      panel.classList.toggle("active", selected);
    });
  });
});

document.querySelectorAll(".drop-zone").forEach((zone) => {
  const input = zone.querySelector("input[type=file]");
  const label = zone.querySelector(".file-name");
  ["dragenter", "dragover"].forEach((eventName) => zone.addEventListener(eventName, (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((eventName) => zone.addEventListener(eventName, (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
  }));
  zone.addEventListener("drop", (event) => {
    if (event.dataTransfer.files.length) {
      input.files = event.dataTransfer.files;
      input.dispatchEvent(new Event("change"));
    }
  });
  input.addEventListener("change", () => {
    clearResult();
    label.textContent = input.files[0]?.name || "Choose a file";
    zone.classList.toggle("has-file", Boolean(input.files.length));
  });
});

const documentConversion = document.querySelector("#documentConversion");
documentConversion.addEventListener("change", () => {
  const value = documentConversion.value;
  const selected = documentConversion.selectedOptions[0];
  document.querySelector("#documentFile").accept = selected?.dataset.accept || ".pdf,.xlsx,.html,.htm,.txt";
  document.querySelector("#sheetOption").hidden = !["excel_to_pdf", "create_csv_from_excel"].includes(value);
  document.querySelector("#titleOption").hidden = value !== "text_to_html";
});

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearResult();
    const button = form.querySelector("button[type=submit]");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Converting...";
    showNotice("Converting securely. Keep this tab open.", "working");
    try {
      const response = await fetch(form.action, { method: "POST", body: new FormData(form) });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Conversion failed.");
      }
      const blob = await response.blob();
      resultUrl = URL.createObjectURL(blob);
      downloadLink.href = resultUrl;
      downloadLink.download = downloadName(response);
      if (blob.type.startsWith("image/")) {
        imagePreview.src = resultUrl;
        imagePreview.hidden = false;
      }
      notice.hidden = true;
      result.hidden = false;
    } catch (error) {
      showNotice(error.message || "Conversion failed.");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  });
});

const themeToggle = document.querySelector("#themeToggle");
const storedTheme = localStorage.getItem("theme");
if (storedTheme === "dark" || (!storedTheme && matchMedia("(prefers-color-scheme: dark)").matches)) {
  document.body.classList.add("dark");
}

function syncThemeToggle() {
  const dark = document.body.classList.contains("dark");
  themeToggle.setAttribute("aria-pressed", dark.toString());
  themeToggle.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
}

syncThemeToggle();
themeToggle.addEventListener("click", () => {
  document.body.classList.toggle("dark");
  localStorage.setItem("theme", document.body.classList.contains("dark") ? "dark" : "light");
  syncThemeToggle();
});
