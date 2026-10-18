"""Document conversions: docx -> pdf/txt/html and html/md/txt -> pdf/html.

DOCX reading builds one intermediate list of blocks; HTML, text and PDF
renderings share it. All generated HTML is escaped; user HTML for html->pdf is
sanitised with nh3 before xhtml2pdf sees it.
"""

import base64
import html
import re
from io import BytesIO
from pathlib import Path

import conversions
from core import config
from core.errors import ConversionError
from core.runner import ConversionResult
from core.uploads import read_text

_HEADING_RE = re.compile(r"^Heading (\d)$")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DOCX_IMAGE_FORMATS = ["JPEG", "PNG", "GIF", "BMP", "TIFF", "WEBP"]

_HTML_PAGE_CSS = (
    "body{font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
    "max-width:800px;margin:40px auto;padding:0 20px;color:#1a1a1a}"
    "table{border-collapse:collapse;width:100%}"
    "th,td{border:1px solid #bbb;padding:6px 8px;vertical-align:top;text-align:left}"
    "th{background:#f3f3f3}"
    "img{max-width:100%}pre{white-space:pre-wrap}"
    "blockquote{border-left:3px solid #ddd;margin-left:0;padding-left:12px;color:#555}"
)

_IMAGE_SKIP_NOTE = "Some images could not be converted."


def _run_html(run) -> str:
    text = html.escape(run.text or "").replace("\n", "<br>")
    if not text:
        return ""
    if run.bold:
        text = f"<b>{text}</b>"
    if run.italic:
        text = f"<i>{text}</i>"
    if run.underline:
        text = f"<u>{text}</u>"
    if run.font.strike:
        text = f"<s>{text}</s>"
    return text


def _link_ok(url: str) -> bool:
    return url.lower().startswith(("http://", "https://", "mailto:"))


def _image_embed(run, document, budget, notes) -> str:
    """Inline a run's embedded images as data URIs; empty string when none."""
    Image = conversions._pillow()

    out = []
    rels = run._r.xpath(".//a:blip/@r:embed")
    for rel_id in rels:
        if budget[0] <= 0:
            break
        try:
            part = document.part.related_parts[rel_id]
            data = part.blob
        except Exception:  # noqa: S112 -- a missing relationship is skipped
            continue
        if not data or len(data) > config.MAX_EMBEDDED_IMAGE_BYTES:
            continue
        try:
            image = Image.open(BytesIO(data), formats=_DOCX_IMAGE_FORMATS)
            image.load()
            if image.format == "JPEG":
                mime, payload = "image/jpeg", data
            else:
                buffer = BytesIO()
                mode = "RGBA" if image.mode in {"RGBA", "LA", "PA"} else "RGB"
                image.convert(mode).save(buffer, "PNG")
                mime, payload = "image/png", buffer.getvalue()
        except Exception:  # noqa: S112 -- unconvertible images are skipped
            if _IMAGE_SKIP_NOTE not in notes:
                notes.append(_IMAGE_SKIP_NOTE)
            continue
        budget[0] -= 1
        encoded = base64.b64encode(payload).decode("ascii")
        out.append(f'<img src="data:{mime};base64,{encoded}" style="max-width:100%">')
    return "".join(out)


def _inline_html(item, document, budget, notes) -> str:
    from docx.text.hyperlink import Hyperlink

    if isinstance(item, Hyperlink):
        inner = "".join(_run_html(run) + _image_embed(run, document, budget, notes) for run in item.runs)
        url = item.url or ""
        if inner and _link_ok(url):
            return f'<a href="{html.escape(url, quote=True)}">{inner}</a>'
        return inner or html.escape(item.text or "")
    parts = [_run_html(item)]
    if item._r.xpath('.//w:br[@w:type="page"]'):
        parts.append("\x00PAGEBREAK\x00")
    parts.append(_image_embed(item, document, budget, notes))
    return "".join(parts)


def _table_html(table) -> list[list[str]]:
    rows = []
    for row in table.rows:
        cells = []
        previous_tc = None
        colspan = 0
        for cell in row.cells:
            if cell._tc is previous_tc:
                colspan += 1
                continue
            if colspan:
                cells[-1] = (cells[-1][0], colspan)
            previous_tc = cell._tc
            colspan = 1
            text = "<br>".join(html.escape(paragraph.text) for paragraph in cell.paragraphs)
            cells.append((text, 1))
        if colspan:
            cells[-1] = (cells[-1][0], colspan)
        rows.append(cells)
    return rows


def _docx_blocks(document, notes, *, for_pdf=False):
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks = []
    budget = [config.MAX_EMBEDDED_IMAGES]
    list_state = None  # None | "ul" | "ol"

    def close_list():
        nonlocal list_state
        if list_state:
            blocks.append({"kind": "list_close", "html": f"</{list_state}>", "text": None})
        list_state = None

    for element in document.element.body.iterchildren():
        if element.tag == qn("w:tbl"):
            close_list()
            rows = _table_html(Table(element, document))
            table_html = ["<table>"]
            for cells in rows:
                table_html.append("<tr>")
                for text, span in cells:
                    attr = f' colspan="{span}"' if span > 1 else ""
                    table_html.append(f"<td{attr}>{text}</td>")
                table_html.append("</tr>")
            table_html.append("</table>")
            blocks.append(
                {
                    "kind": "table",
                    "html": "".join(table_html),
                    "text": ["\t".join(c[0] for c in cells) for cells in rows],
                }
            )
            continue
        if element.tag != qn("w:p"):
            continue

        paragraph = Paragraph(element, document)
        style_name = (paragraph.style.name or "") if paragraph.style else ""
        match = _HEADING_RE.match(style_name)
        level = min(int(match.group(1)), 4) if match else 0
        if style_name == "Title":
            level = 1
        elif style_name == "Subtitle":
            level = 2

        inner = "".join(
            _inline_html(item, document, budget, notes) for item in paragraph.iter_inner_content()
        )
        # A page break run splits the paragraph in place.
        pieces = inner.split("\x00PAGEBREAK\x00")

        is_list = (
            paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None
        ) or "List" in style_name
        ordered = "Number" in style_name

        for position, piece in enumerate(pieces):
            if piece or position == 0:
                if level:
                    close_list()
                    tag = f"h{level}"
                    blocks.append({"kind": "para", "html": f"<{tag}>{piece}</{tag}>", "text": paragraph.text})
                elif is_list:
                    wanted = "ol" if ordered else "ul"
                    if list_state != wanted:
                        close_list()
                        blocks.append({"kind": "list_open", "html": wanted, "text": None})
                        list_state = wanted
                    blocks.append({"kind": "item", "html": f"<li>{piece}</li>", "text": paragraph.text})
                elif piece:
                    close_list()
                    blocks.append({"kind": "para", "html": f"<p>{piece}</p>", "text": paragraph.text})
            if position < len(pieces) - 1:
                close_list()
                blocks.append({"kind": "pagebreak", "html": "", "text": None})
    close_list()

    html_parts = []
    text_parts = []
    for block in blocks:
        if block["kind"] == "list_open":
            html_parts.append(f"<{block['html']}>")
            continue
        if block["kind"] == "list_close":
            html_parts.append(block["html"])
            continue
        if block["kind"] == "pagebreak":
            html_parts.append("<pdf:nextpage/>" if for_pdf else "<hr>")
            text_parts.append("")
            continue
        html_parts.append(block["html"])
        if block["kind"] == "item":
            text_parts.append("- " + (block["text"] or "").strip())
        elif block["kind"] == "table":
            text_parts.extend(block["text"])
        elif block["text"]:
            text_parts.append(block["text"].strip())

    return "\n".join(html_parts), "\n\n".join(part for part in text_parts if part is not None)


def _document(path: Path):
    from docx import Document

    try:
        return Document(str(path))
    except Exception as exc:
        raise ConversionError("The Word document could not be read. It may be damaged.") from exc


def _docx_title(document, stem: str) -> str:
    try:
        title = document.core_properties.title
    except Exception:
        title = None
    return (title or "").strip() or stem


def _standalone(body: str, title: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{_HTML_PAGE_CSS}</style>"
        f"</head><body>{body}</body></html>"
    )


def docx_to_html(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    notes = []
    document = _document(input_path)
    body, _text = _docx_blocks(document, notes)
    title = _docx_title(document, options.get("_stem", "Document") or "Document")
    output_path.write_text(_standalone(body, title), encoding="utf-8")
    return ConversionResult(str(output_path), "html", notes)


def docx_to_txt(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    notes = []
    document = _document(input_path)
    _body, text = _docx_blocks(document, notes)
    output_path.write_text(text, encoding="utf-8")
    return ConversionResult(str(output_path), "txt", notes)


def docx_to_pdf(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    from conversions import pdf_render

    notes = []
    document = _document(input_path)
    body, _text = _docx_blocks(document, notes, for_pdf=True)
    pdf_render.render_pdf(body, output_path, title=_docx_title(document, options.get("_stem", "")))
    return ConversionResult(str(output_path), "pdf", notes)


def _extract_title(raw: str) -> str:
    match = _TITLE_RE.search(raw)
    if match:
        return html.unescape(match.group(1)).strip()[:200]
    return ""


def html_to_pdf(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    from conversions import pdf_render

    raw = read_text(input_path)
    if len(raw.encode("utf-8")) > config.MAX_HTML_BYTES:
        raise ConversionError(f"HTML files are limited to {config.MAX_HTML_BYTES // (1024 * 1024)} MB.")
    title = _extract_title(raw)
    body = pdf_render.sanitize_html(raw)
    pdf_render.render_pdf(body, output_path, title=title)
    return ConversionResult(str(output_path), "pdf", [])


def text_to_html(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    text = read_text(input_path)
    title = options.get("title") or options.get("_stem", "Document")
    body = f"<pre>{html.escape(text)}</pre>"
    output_path.write_text(_standalone(body, title), encoding="utf-8")
    return ConversionResult(str(output_path), "html", [])


def text_to_pdf(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    from conversions import pdf_render

    text = read_text(input_path)
    body = f'<pre style="white-space: pre-wrap; font-size: 9.5pt">{html.escape(text)}</pre>'
    pdf_render.render_pdf(body, output_path, title=options.get("_stem", ""))
    return ConversionResult(str(output_path), "pdf", [])


def _markdown_title(text: str, options: dict) -> str:
    if options.get("title"):
        return options["title"]
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("#").strip()[:200]
    return options.get("_stem", "Document")


def markdown_to_html(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    import markdown as md

    from conversions import pdf_render

    text = read_text(input_path)
    rendered = md.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    body = pdf_render.sanitize_html(rendered, allow_remote_images=True)
    output_path.write_text(_standalone(body, _markdown_title(text, options)), encoding="utf-8")
    return ConversionResult(str(output_path), "html", [])


def markdown_to_pdf(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    import markdown as md

    from conversions import pdf_render

    text = read_text(input_path)
    body = pdf_render.sanitize_html(md.markdown(text, extensions=["tables", "fenced_code", "sane_lists"]))
    pdf_render.render_pdf(body, output_path, title=_markdown_title(text, options))
    return ConversionResult(str(output_path), "pdf", [])
