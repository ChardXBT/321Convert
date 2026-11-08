"use strict";

/* Invalid-combo tests for the declared per-file lifecycle in
 * static/file-states.js: every invalid-but-representable combination from the
 * audit must be unrepresentable (construction or transition raises). */

import assert from "node:assert/strict";
import {createRequire} from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const {ROW_STATUS, newFileRow, transitionRow} = require("../../static/file-states.js");

const FAMILY = {id: "image", outputs: [{ext: "jpg", label: "JPG"}]};

const makeRow = (fields = {}) => newFileRow({id: 1, family: FAMILY, target: "jpg", ...fields});
const makeUnsupported = () =>
    newFileRow({id: 2, family: null, status: "unsupported", error: "nope"});

const uploadingRow = () => {
    const row = makeRow();
    transitionRow(row, ROW_STATUS.UPLOADING);
    return row;
};

test("done requires a resultUrl and resultName", () => {
    const row = uploadingRow();
    assert.throws(() => transitionRow(row, ROW_STATUS.DONE), /done/);
    assert.throws(() => transitionRow(row, ROW_STATUS.DONE, {resultUrl: "blob:x"}), /done/);
    assert.throws(
        () => transitionRow(row, ROW_STATUS.DONE, {resultUrl: "blob:x", resultName: ""}),
        /done/,
    );
    transitionRow(row, ROW_STATUS.DONE, {resultUrl: "blob:x", resultName: "a.jpg"});
    assert.equal(row.status, "done");
});

test("error requires a non-empty message", () => {
    const row = uploadingRow();
    assert.throws(() => transitionRow(row, ROW_STATUS.ERROR), /error/);
    assert.throws(() => transitionRow(row, ROW_STATUS.ERROR, {error: ""}), /error/);
    transitionRow(row, ROW_STATUS.ERROR, {error: "boom"});
    assert.equal(row.status, "error");
    assert.equal(row.error, "boom");
});

test("family null forces unsupported and nothing else", () => {
    assert.throws(() => makeRow({family: null}), /ready|status/);
    assert.throws(() => makeRow({status: "unsupported", error: "x"}), /unsupported/);

    const unsupported = makeUnsupported();
    assert.equal(unsupported.status, "unsupported");
    assert.throws(() => transitionRow(unsupported, ROW_STATUS.UPLOADING), /unsupported/);
    assert.throws(() => transitionRow(unsupported, ROW_STATUS.READY), /unsupported/);

    const row = makeRow();
    row.family = null;
    assert.throws(() => transitionRow(row, ROW_STATUS.UPLOADING), /uploading/);
});

test("only declared transitions are allowed", () => {
    const row = makeRow();
    assert.throws(
        () => transitionRow(row, ROW_STATUS.DONE, {resultUrl: "u", resultName: "n"}),
        /"ready" -> "done"/,
    );
    assert.throws(
        () => transitionRow(row, ROW_STATUS.CONVERTING),
        /"ready" -> "converting"/,
    );

    const converting = uploadingRow();
    transitionRow(converting, ROW_STATUS.CONVERTING);
    assert.throws(
        () => transitionRow(converting, ROW_STATUS.UPLOADING),
        /"converting" -> "uploading"/,
    );

    const done = uploadingRow();
    transitionRow(done, ROW_STATUS.DONE, {resultUrl: "blob:x", resultName: "a.jpg"});
    assert.throws(
        () => transitionRow(done, ROW_STATUS.ERROR, {error: "x"}),
        /"done" -> "error"/,
    );
    transitionRow(done, ROW_STATUS.READY);
    assert.equal(done.status, "ready");
});

test("error rows are re-tryable and target changes reset to ready", () => {
    const row = uploadingRow();
    transitionRow(row, ROW_STATUS.ERROR, {error: "boom"});
    transitionRow(row, ROW_STATUS.READY);
    assert.equal(row.status, "ready");
    transitionRow(row, ROW_STATUS.UPLOADING);
    transitionRow(row, ROW_STATUS.ERROR, {error: "again"});
    transitionRow(row, ROW_STATUS.UPLOADING);
    assert.equal(row.status, "uploading");
});

test("entry resets companion fields for the target state", () => {
    const row = makeRow();
    transitionRow(row, ROW_STATUS.UPLOADING);
    transitionRow(row, ROW_STATUS.ERROR, {error: "boom"});
    transitionRow(row, ROW_STATUS.READY);
    assert.equal(row.error, "");
    assert.deepEqual(row.notes, []);
    assert.equal(row.resultUrl, null);

    row.progress = 55;
    transitionRow(row, ROW_STATUS.UPLOADING);
    assert.equal(row.progress, 0);
});

test("unknown status values fail loudly", () => {
    const row = makeRow();
    assert.throws(() => transitionRow(row, "bogus"), /unknown/);
    assert.throws(() => makeRow({status: "bogus"}), /unknown|status/);
    row.status = "bogus";
    assert.throws(() => transitionRow(row, ROW_STATUS.READY), /unknown/);
});

test("construction cannot create invalid combos", () => {
    assert.throws(() => makeRow({error: "x"}), /ready/);
    assert.throws(() => makeRow({resultUrl: "blob:y"}), /ready/);
    assert.throws(() => newFileRow({status: "unsupported", family: null}), /unsupported/);
});
