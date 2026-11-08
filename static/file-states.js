"use strict";

/* Declared per-file conversion lifecycle.
 *
 * row.status is the single state field; every other per-state field is
 * written or required by the functions below. The strings are a cross-file
 * contract: they are mirrored into <li data-status>, which styles.css and
 * tests/e2e key off — do not rename them. */

const ROW_STATUS = Object.freeze({
    READY: "ready",
    UNSUPPORTED: "unsupported",
    UPLOADING: "uploading",
    CONVERTING: "converting",
    DONE: "done",
    ERROR: "error",
});

/* Allowed from -> to edges. Staying in the same state is always allowed. */
const ROW_TRANSITIONS = Object.freeze({
    ready: Object.freeze([ROW_STATUS.UPLOADING, ROW_STATUS.UNSUPPORTED]),
    unsupported: Object.freeze([]),
    uploading: Object.freeze([ROW_STATUS.CONVERTING, ROW_STATUS.DONE, ROW_STATUS.ERROR]),
    converting: Object.freeze([ROW_STATUS.DONE, ROW_STATUS.ERROR]),
    done: Object.freeze([ROW_STATUS.READY]),
    error: Object.freeze([ROW_STATUS.READY, ROW_STATUS.UPLOADING]),
});

/* Per-state field contract: `reset` is applied to the row on entry, `check`
 * must hold once it and the caller's fields are assigned. This is what makes
 * the invalid combos unrepresentable: done without a result, error without a
 * message, family === null outside "unsupported". */
const ROW_STATE_SPEC = Object.freeze({
    ready: {
        reset: {progress: 0, resultUrl: null, resultName: "", error: "", notes: []},
        check: (row) => row.family !== null && row.resultUrl === null && row.error === "",
    },
    unsupported: {
        reset: {},
        check: (row) => row.family === null && row.error !== "",
    },
    uploading: {
        reset: {progress: 0, error: "", notes: []},
        check: (row) => row.family !== null,
    },
    converting: {
        reset: {},
        check: (row) => row.family !== null,
    },
    done: {
        reset: {},
        check: (row) =>
            row.family !== null &&
            row.resultUrl !== null &&
            row.resultName !== "" &&
            row.error === "",
    },
    error: {
        reset: {},
        check: (row) => row.family !== null && row.error !== "" && row.resultUrl === null,
    },
});

const _checkSpec = (row, spec, to) => {
    if (!spec.check(row)) {
        throw new Error(`fields violate the "${to}" file-state contract`);
    }
};

/* The single writer of row.status: validates the edge, applies the state's
 * resets plus the caller's fields, then enforces the state's invariants. */
const transitionRow = (row, to, fields = {}) => {
    const spec = ROW_STATE_SPEC[to];
    if (spec === undefined) {
        throw new Error(`unknown file status "${String(to)}"`);
    }
    const from = row.status;
    const edges = ROW_TRANSITIONS[from];
    if (edges === undefined) {
        throw new Error(`row has unknown status "${String(from)}"`);
    }
    if (from !== to && !edges.includes(to)) {
        throw new Error(`invalid file status transition "${from}" -> "${to}"`);
    }
    const next = Object.assign({}, row, spec.reset, fields, {status: to});
    _checkSpec(next, spec, to);
    Object.assign(row, next);
    return row;
};

/* The single constructor: a new row must satisfy its initial state. */
const newFileRow = (fields = {}) => {
    const row = Object.assign(
        {
            status: ROW_STATUS.READY,
            family: null,
            target: "",
            progress: 0,
            resultUrl: null,
            resultName: "",
            notes: [],
            error: "",
        },
        fields,
    );
    const spec = ROW_STATE_SPEC[row.status];
    if (spec === undefined) {
        throw new Error(`unknown file status "${String(row.status)}"`);
    }
    _checkSpec(row, spec, row.status);
    return row;
};

/* Tests import this file via require(); browsers load it before app.js and
 * share the top-level bindings through the global lexical environment. */
if (typeof module !== "undefined" && module.exports) {
    module.exports = {ROW_STATUS, ROW_TRANSITIONS, newFileRow, transitionRow};
}
