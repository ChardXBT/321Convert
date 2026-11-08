"use strict";

/* Drives the real static/app.js through the DOM stub. The wedge test is the
 * regression for the audit finding: a convertRow() rejection must not leave
 * state.running stuck — the row lands in "error" and stays re-tryable. */

import assert from "node:assert/strict";
import test from "node:test";

import {addFile, createHarness, REGISTRY, tick} from "./dom-stub.mjs";

const file = (name) => ({name, size: 10, lastModified: Date.now()});

test("a convertRow failure lands the row in error and frees the batch", async () => {
    const {context, elements, windowListeners, xhrs} = createHarness({
        registry: REGISTRY,
        xhrSend: () => {
            throw new Error("send blew up");
        },
    });
    addFile(elements, file("a.png"));
    addFile(elements, file("b.png"));
    const rows = elements.fileList.children;
    assert.equal(rows.length, 2);
    assert.equal(rows[0].dataset.status, "ready");

    elements.convertAll.dispatch("click", {});
    await tick();
    await tick();

    for (const row of rows) {
        assert.equal(row.dataset.status, "error", "row must not be stranded mid-flight");
        const retry = row.querySelector(".retry-button");
        assert.ok(retry, "failed rows must offer a retry button");
        assert.equal(retry.disabled, false, "failed rows must be re-tryable");
        assert.ok(row.querySelector(".file-error").textContent.length > 0);
    }
    assert.equal(elements.convertAll.disabled, false, "Convert must not stay disabled");
    assert.match(elements.summary.textContent, /2 failed/);

    let prevented = false;
    (windowListeners.beforeunload || []).forEach((fn) =>
        fn.call(context, {
            preventDefault: () => {
                prevented = true;
            },
        }),
    );
    assert.equal(prevented, false, "beforeunload must not nag once nothing is in flight");

    rows[0].querySelector(".retry-button").dispatch("click", {});
    await tick();
    await tick();
    assert.equal(rows[0].dataset.status, "error", "retry hits the same failing path");
    assert.ok(xhrs.length >= 3, "retry issues a new request");
});

test("a successful conversion lands in done with a download link", async () => {
    const {elements, xhrs} = createHarness({registry: REGISTRY});
    addFile(elements, file("sample.png"));
    const row = elements.fileList.children[0];

    elements.convertAll.dispatch("click", {});
    assert.equal(xhrs.length, 1);
    const xhr = xhrs[0];

    xhr.upload.onload?.();
    assert.equal(row.dataset.status, "converting");
    xhr.status = 200;
    xhr.response = {text: async () => ""};
    xhr.onload?.();
    await tick();

    assert.equal(row.dataset.status, "done");
    const link = row.querySelector("a.download-button");
    assert.ok(link);
    assert.equal(link.getAttribute("download"), "sample.jpg");
    assert.match(elements.summary.textContent, /1 converted/);
    assert.equal(elements.convertAll.disabled, true, "nothing left to convert");
});

test("a server error lands in error with the server's message", async () => {
    const {elements, xhrs} = createHarness({registry: REGISTRY});
    addFile(elements, file("bad.png"));
    const row = elements.fileList.children[0];

    elements.convertAll.dispatch("click", {});
    const xhr = xhrs[0];
    xhr.status = 422;
    xhr.response = {text: async () => '{"error":"not readable"}'};
    xhr.onload?.();
    await tick();
    await tick();

    assert.equal(row.dataset.status, "error");
    assert.equal(row.querySelector(".file-error").textContent, "not readable");
    assert.match(elements.summary.textContent, /1 failed/);
    assert.equal(elements.convertAll.disabled, false);
});

test("a failed row retries to done through its retry button", async () => {
    const {elements, xhrs} = createHarness({registry: REGISTRY});
    addFile(elements, file("x.png"));
    const row = elements.fileList.children[0];

    elements.convertAll.dispatch("click", {});
    xhrs[0].status = 500;
    xhrs[0].response = {text: async () => "oops"};
    xhrs[0].onload?.();
    await tick();
    await tick();
    assert.equal(row.dataset.status, "error");

    row.querySelector(".retry-button").dispatch("click", {});
    assert.equal(xhrs.length, 2, "retry issues a new request");
    xhrs[1].status = 200;
    xhrs[1].response = {text: async () => ""};
    xhrs[1].upload.onload?.();
    xhrs[1].onload?.();
    await tick();

    assert.equal(row.dataset.status, "done");
    assert.ok(row.querySelector("a.download-button"));
});

test("unsupported files never enter the conversion queue", () => {
    const {elements, xhrs} = createHarness({registry: REGISTRY});
    addFile(elements, file("tool.exe"));
    const row = elements.fileList.children[0];
    assert.equal(row.dataset.status, "unsupported");
    assert.equal(elements.convertAll.disabled, true);
    elements.convertAll.dispatch("click", {});
    assert.equal(xhrs.length, 0);
});
