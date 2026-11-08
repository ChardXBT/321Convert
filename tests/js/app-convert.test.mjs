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

test("the target select is locked while a row is in flight; a forced change is ignored", async () => {
    const {elements, xhrs} = createHarness({registry: REGISTRY});
    addFile(elements, file("pic.png"));
    const row = elements.fileList.children[0];
    const select = () => row.querySelector("select");
    assert.equal(select().disabled, false, "ready rows can change target");
    const target = select().value;

    elements.convertAll.dispatch("click", {});
    assert.equal(row.dataset.status, "uploading");
    assert.equal(select().disabled, true, "uploading rows lock their target");

    // A change event that still arrives (e.g. dispatched programmatically)
    // must neither throw nor yank the in-flight row back to ready.
    select().value = "png";
    assert.doesNotThrow(() => select().dispatch("change", {}));
    assert.equal(row.dataset.status, "uploading");
    assert.equal(select().value, target, "the select snaps back to the in-flight target");

    xhrs[0].upload.onload?.();
    assert.equal(row.dataset.status, "converting");
    assert.equal(select().disabled, true, "converting rows lock their target");
    select().value = "png";
    assert.doesNotThrow(() => select().dispatch("change", {}));
    assert.equal(row.dataset.status, "converting");

    xhrs[0].status = 200;
    xhrs[0].response = {text: async () => ""};
    xhrs[0].onload?.();
    await tick();
    assert.equal(row.dataset.status, "done");
    assert.equal(xhrs[0].data.fields.target, target, "the request kept the original target");
    assert.equal(select().disabled, false, "settled rows unlock their target");

    // Changing a done row's target still resets it to ready (base behaviour).
    select().value = "png";
    select().dispatch("change", {});
    assert.equal(row.dataset.status, "ready");
    assert.equal(row.querySelector("a.download-button"), null);
});

const fireLateEvents = (xhr) => {
    xhr.upload.onprogress?.({lengthComputable: true, loaded: 10, total: 10});
    xhr.upload.onload?.();
    xhr.onerror?.();
    xhr.ontimeout?.();
    xhr.status = 500;
    xhr.response = {text: async () => '{"error":"late"}'};
    xhr.onload?.();
};

test("late XHR events after done are ignored, not thrown", async () => {
    const {elements, xhrs, consoleErrors} = createHarness({registry: REGISTRY});
    addFile(elements, file("late.png"));
    const row = elements.fileList.children[0];

    elements.convertAll.dispatch("click", {});
    const xhr = xhrs[0];
    xhr.upload.onload?.();
    xhr.status = 200;
    xhr.response = {text: async () => ""};
    xhr.onload?.();
    await tick();
    assert.equal(row.dataset.status, "done");

    assert.doesNotThrow(() => fireLateEvents(xhr));
    await tick();
    await tick();
    assert.equal(row.dataset.status, "done", "a settled row keeps its result");
    assert.ok(row.querySelector("a.download-button"));
    assert.equal(row.querySelector(".file-error").textContent, "");
    assert.match(elements.summary.textContent, /1 converted/);
    assert.deepEqual(consoleErrors, [], "late events are not errors");
});

test("late XHR events after error are ignored, and a stale request cannot touch a retry", async () => {
    const {elements, xhrs} = createHarness({registry: REGISTRY});
    addFile(elements, file("stale.png"));
    const row = elements.fileList.children[0];

    elements.convertAll.dispatch("click", {});
    const first = xhrs[0];
    first.ontimeout?.();
    await tick();
    assert.equal(row.dataset.status, "error");
    assert.equal(row.querySelector(".file-error").textContent, "The conversion timed out.");

    first.status = 200;
    first.response = {text: async () => ""};
    assert.doesNotThrow(() => first.onload?.());
    await tick();
    assert.equal(row.dataset.status, "error", "a late success must not resurrect a failed attempt");

    row.querySelector(".retry-button").dispatch("click", {});
    assert.equal(xhrs.length, 2);
    assert.equal(row.dataset.status, "uploading");
    assert.doesNotThrow(() => fireLateEvents(first));
    await tick();
    await tick();
    assert.equal(row.dataset.status, "uploading", "the old request cannot drive the retry");
    assert.equal(row.querySelector(".file-error").textContent, "");

    xhrs[1].status = 200;
    xhrs[1].response = {text: async () => ""};
    xhrs[1].upload.onload?.();
    xhrs[1].onload?.();
    await tick();
    assert.equal(row.dataset.status, "done");
});
