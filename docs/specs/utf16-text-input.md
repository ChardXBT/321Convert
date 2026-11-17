# Spec: UTF-16 text, CSV, HTML and Markdown uploads

Status: not built. Recorded by the 2026-11-17 readiness audit; under the project's scope
rule, missing features are written up here rather than built during an audit.

## Problem

Text-family uploads (`.txt`, `.csv`, `.html`, `.htm`, `.md`, `.markdown`) are decoded as
UTF-8 (with or without BOM) or cp1252 (`core/uploads.py:read_text`). Before that,
`core/uploads.py:sniff` rejects any text upload whose first 8 KiB contain a NUL byte, with
"The file does not look like a text file."

UTF-16 files contain a NUL byte in almost every ASCII character, so they are always
rejected. Common sources:

- Windows Notepad's "UTF-16 LE" save option (called "Unicode" in older versions).
- Excel's "Unicode Text (*.txt)" export: tab-separated UTF-16 LE with a BOM.
- Some database and PowerShell exports (`Out-File` on Windows PowerShell 5.1 defaults to
  UTF-16 LE).

## Proposed behaviour

1. In `sniff`, if a text upload starts with a UTF-16 BOM (`FF FE` or `FE FF`), skip the
   NUL-byte check. Files without a BOM keep the current check: guessing UTF-16 without a
   BOM is unreliable, and binary files must still be rejected.
2. In `read_text`, decode BOM-prefixed data with `utf-16` (the codec uses the BOM to pick
   the byte order). If decoding fails, raise `ConversionError("The text file could not be
   decoded.")` rather than falling back to cp1252.
3. After decoding, reject text that still contains U+0000, with the existing "does not look
   like a text file" message, so a binary file with a fake BOM fails cleanly.
4. Size limits apply to the raw upload as they do now. `MAX_HTML_BYTES` keeps measuring the
   UTF-8 re-encoding (`documents.html_to_pdf`), so UTF-16 HTML is not given double the
   budget.
5. Outputs are unchanged: text-derived outputs stay UTF-8 (CSV with BOM, as today).

## Tests to add

- UTF-16 LE and BE `.txt` with BOM → PDF and HTML keep non-ASCII text (`café`, `日本`).
- Excel-style UTF-16 LE tab-separated `.txt` → PDF keeps every column's text; a
  UTF-16 `.csv` with tabs → XLSX detects the tab delimiter.
- UTF-16 BOM followed by random binary → 400/422 with the text-file message.
- A NUL-containing file without a BOM is still rejected (regression guard for today's check).

## Docs to update when built

README "Privacy and security" (NUL-byte rule) and docs/ARCHITECTURE.md request flow step 2.
