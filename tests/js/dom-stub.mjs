"use strict";

/* Minimal DOM stub: just enough browser surface to run static/app.js under
 * Node's vm, so tests can drive the real UI logic without a browser.
 * APP_REPO_ROOT overrides which checkout's static files are loaded. */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

export const REPO_ROOT = path.resolve(
    process.env.APP_REPO_ROOT || path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".."),
);

export const REGISTRY = {
    max_upload_mb: 25,
    accept: ".png,.jpg",
    families: [
        {
            id: "image",
            label: "Image",
            extensions: ["png", "jpg"],
            outputs: [
                {ext: "jpg", label: "JPG"},
                {ext: "png", label: "PNG"},
            ],
            options: [],
        },
    ],
    options: {},
};

const dataKey = (name) => name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());

const parseCompound = (compound) => {
    const simple = {tag: null, id: null, classes: [], attrs: []};
    let rest = compound;
    const tag = /^[a-zA-Z][\w-]*/.exec(rest);
    if (tag) {
        simple.tag = tag[0].toUpperCase();
        rest = rest.slice(tag[0].length);
    }
    const token = /[.#][\w-]+|\[[^\]]+\]/g;
    let m;
    while ((m = token.exec(rest))) {
        const t = m[0];
        if (t[0] === ".") simple.classes.push(t.slice(1));
        else if (t[0] === "#") simple.id = t.slice(1);
        else {
            const inner = t.slice(1, -1);
            const eq = inner.indexOf("=");
            if (eq < 0) {
                simple.attrs.push({name: inner.trim()});
            } else {
                const name = inner.slice(0, eq).trim();
                const value = inner
                    .slice(eq + 1)
                    .trim()
                    .replace(/^['"]|['"]$/g, "");
                simple.attrs.push({name, value});
            }
        }
    }
    return simple;
};

const attrValue = (el, name) => {
    if (name.startsWith("data-")) {
        const v = el.dataset[dataKey(name)];
        return v === undefined ? null : String(v);
    }
    return el.getAttribute(name);
};

const matchesCompound = (el, compound) => {
    if (el.isText || !el.tagName) return false;
    const s = parseCompound(compound);
    if (s.tag && el.tagName !== s.tag) return false;
    if (s.id && el.getAttribute("id") !== s.id) return false;
    const classes = el.className.split(/\s+/).filter(Boolean);
    if (s.classes.some((c) => !classes.includes(c))) return false;
    return s.attrs.every((a) => {
        const v = attrValue(el, a.name);
        if (v === null || v === undefined) return false;
        return a.value === undefined || v === a.value;
    });
};

const matchesChain = (el, selector) => {
    const compounds = selector.trim().split(/\s+/);
    if (!matchesCompound(el, compounds[compounds.length - 1])) return false;
    let node = el.parentNode;
    for (let i = compounds.length - 2; i >= 0; i -= 1) {
        while (node && !matchesCompound(node, compounds[i])) node = node.parentNode;
        if (!node) return false;
        node = node.parentNode;
    }
    return true;
};

class StubElement {
    constructor(tagName) {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.attributes = Object.create(null);
        this.dataset = {};
        this.style = {};
        this.listeners = Object.create(null);
        this.hidden = false;
        this.disabled = false;
        this.isText = false;
        this.files = [];
        this._className = "";
        this._text = "";
        this._value = "";
    }

    get className() {
        return this._className;
    }
    set className(v) {
        this._className = String(v);
    }
    get textContent() {
        return this._text + this.children.map((c) => c.textContent).join("");
    }
    set textContent(v) {
        this.children = [];
        this._text = String(v);
    }
    get id() {
        return this.getAttribute("id") || "";
    }
    set id(v) {
        this.setAttribute("id", v);
    }
    get href() {
        return this.attributes.href || "";
    }
    set href(v) {
        this.attributes.href = String(v);
    }
    get value() {
        return this._value;
    }
    set value(v) {
        this._value = String(v);
    }
    get classList() {
        const self = this;
        const read = () => self._className.split(/\s+/).filter(Boolean);
        const write = (tokens) => {
            self._className = tokens.join(" ");
        };
        return {
            add: (...cs) => write([...new Set([...read(), ...cs])]),
            remove: (...cs) => write(read().filter((c) => !cs.includes(c))),
            contains: (c) => read().includes(c),
        };
    }

    setAttribute(name, value) {
        if (name === "class") {
            this.className = value;
            return;
        }
        this.attributes[name] = String(value);
    }
    getAttribute(name) {
        return name in this.attributes ? this.attributes[name] : null;
    }
    appendChild(node) {
        node.remove();
        node.parentNode = this;
        this.children.push(node);
        return node;
    }
    replaceChildren(...nodes) {
        this.children.forEach((c) => {
            c.parentNode = null;
        });
        this.children = [];
        nodes.forEach((n) => this.appendChild(n));
    }
    remove() {
        if (this.parentNode) {
            const i = this.parentNode.children.indexOf(this);
            if (i >= 0) this.parentNode.children.splice(i, 1);
            this.parentNode = null;
        }
    }
    addEventListener(type, fn) {
        (this.listeners[type] ||= []).push(fn);
    }
    dispatch(type, event = {}) {
        if (event.target === undefined) event.target = this;
        (this.listeners[type] || []).slice().forEach((fn) => fn.call(this, event));
    }
    click() {
        this.dispatch("click", {preventDefault() {}});
    }
    closest(sel) {
        let node = this;
        while (node) {
            if (matchesChain(node, sel)) return node;
            node = node.parentNode;
        }
        return null;
    }
    querySelector(sel) {
        return this.querySelectorAll(sel)[0] || null;
    }
    querySelectorAll(sel) {
        const out = [];
        const walk = (node) => {
            node.children.forEach((child) => {
                if (matchesChain(child, sel)) out.push(child);
                walk(child);
            });
        };
        walk(this);
        return out;
    }
    checkValidity() {
        return true;
    }
    reportValidity() {}
    showModal() {}
    close() {}
}

class StubDocument {
    constructor() {
        this.root = new StubElement("root");
        this.documentElement = new StubElement("html");
        this.documentElement.setAttribute("data-theme", "light");
        this.byId = Object.create(null);
    }
    register(id, el) {
        el.setAttribute("id", id);
        this.byId[id] = el;
        this.root.appendChild(el);
        return el;
    }
    getElementById(id) {
        return this.byId[id] || null;
    }
    querySelector(sel) {
        return this.root.querySelector(sel);
    }
    querySelectorAll(sel) {
        return this.root.querySelectorAll(sel);
    }
    createElement(tag) {
        return new StubElement(tag);
    }
    createElementNS(_ns, tag) {
        return new StubElement(tag);
    }
    createTextNode(text) {
        const node = new StubElement("#text");
        node.isText = true;
        node._text = String(text);
        return node;
    }
}

const ELEMENT_IDS = [
    "registry",
    "notice",
    "noticeText",
    "dropZone",
    "fileInput",
    "fileList",
    "addMore",
    "options",
    "fieldQuality",
    "fieldMaxDimension",
    "fieldSheetName",
    "fieldTitle",
    "optQuality",
    "optQualityValue",
    "optMaxDimension",
    "optSheetName",
    "optTitle",
    "summary",
    "clearAll",
    "downloadAll",
    "convertAll",
    "themeToggle",
];

/* Builds the DOM, loads static/file-states.js (when present) and
 * static/app.js into a vm context, and returns handles a test needs. */
export const createHarness = ({registry = REGISTRY, xhrSend = null} = {}) => {
    const document = new StubDocument();
    const elements = {};
    ELEMENT_IDS.forEach((id) => {
        elements[id] = document.register(id, new StubElement("div"));
    });
    elements.registry.textContent = JSON.stringify(registry);
    const workspace = new StubElement("section");
    workspace.className = "workspace";
    document.root.appendChild(workspace);
    const sun = new StubElement("svg");
    sun.className = "icon icon-sun";
    const moon = new StubElement("svg");
    moon.className = "icon icon-moon";
    moon.hidden = true;
    elements.themeToggle.appendChild(sun);
    elements.themeToggle.appendChild(moon);
    elements.convertAll.disabled = true;
    elements.optQuality.value = "82";

    const xhrs = [];
    class FakeXHR {
        constructor() {
            this.upload = {};
            xhrs.push(this);
        }
        open() {}
        send(data) {
            this.data = data;
            if (xhrSend) xhrSend(this);
        }
        getResponseHeader() {
            return null;
        }
    }

    const windowListeners = {};
    const consoleErrors = [];
    const context = {
        console: {
            log() {},
            info() {},
            warn() {},
            debug() {},
            error: (...args) => consoleErrors.push(args.map(String).join(" ")),
        },
        document,
        window: {
            addEventListener: (type, fn) => {
                (windowListeners[type] ||= []).push(fn);
            },
        },
        localStorage: {getItem: () => null, setItem() {}},
        URL: {
            createObjectURL: () => `blob:fake-${xhrs.length}`,
            revokeObjectURL() {},
        },
        FormData: class {
            constructor() {
                this.fields = {};
            }
            append(k, v) {
                this.fields[k] = v;
            }
        },
        XMLHttpRequest: FakeXHR,
        setTimeout,
        clearTimeout,
        __windowListeners: windowListeners,
    };
    vm.createContext(context);
    for (const file of ["static/file-states.js", "static/app.js"]) {
        const p = path.join(REPO_ROOT, file);
        if (fs.existsSync(p)) {
            vm.runInContext(fs.readFileSync(p, "utf8"), context, {filename: file});
        }
    }
    return {context, document, elements, xhrs, windowListeners, consoleErrors};
};

export const addFile = (elements, file) => {
    elements.fileInput.files = [file];
    elements.fileInput.dispatch("change", {});
};

export const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
