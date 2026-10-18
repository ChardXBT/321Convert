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
    ".docx-header,.docx-footer{color:#777;font-size:.85em;white-space:pre-wrap}"
)

_IMAGE_SKIP_NOTE = "Some images could not be converted."

_HIGHLIGHT_CSS = {
    "YELLOW": "#ffff00",
    "BRIGHT_GREEN": "#00ff00",
    "TURQUOISE": "#00ffff",
    "PINK": "#ff00ff",
    "GRAY_25": "#c0c0c0",
}
_LIST_TYPES = {"lowerLetter": "a", "upperLetter": "A", "lowerRoman": "i", "upperRoman": "I"}


def _run_html(run) -> str:
    text = html.escape(run.text or "").replace("\n", "<br>")
    if not text:
        return ""
    if run.font.superscript:
        text = f"<sup>{text}</sup>"
    if run.font.subscript:
        text = f"<sub>{text}</sub>"
    if run.bold:
        text = f"<b>{text}</b>"
    if run.italic:
        text = f"<i>{text}</i>"
    if run.underline:
        text = f"<u>{text}</u>"
    if run.font.strike:
        text = f"<s>{text}</s>"
    styles = []
    if run.font.size:
        styles.append(f"font-size:{run.font.size.pt:g}pt")
    try:
        rgb = run.font.color.rgb
    except Exception:
        rgb = None
    if rgb:
        styles.append(f"color:#{str(rgb).lower()}")
    try:
        highlight = run.font.highlight_color
    except Exception:
        highlight = None
    background = _HIGHLIGHT_CSS.get(getattr(highlight, "name", ""), "") if highlight else ""
    if background:
        styles.append(f"background:{background}")
    if run.font.all_caps:
        styles.append("text-transform:uppercase")
    if run.font.small_caps:
        styles.append("font-variant:small-caps")
    if styles:
        text = f'<span style="{";".join(styles)}">{text}</span>'
    return text


def _paragraph_style(paragraph) -> str:
    styles = []
    try:
        alignment = paragraph.alignment
    except Exception:
        alignment = None
    align = {
        "LEFT": "left",
        "CENTER": "center",
        "RIGHT": "right",
        "JUSTIFY": "justify",
    }.get(getattr(alignment, "name", ""))
    if align:
        styles.append(f"text-align:{align}")
    fmt = paragraph.paragraph_format
    for attribute, css_prop in (
        ("left_indent", "margin-left"),
        ("right_indent", "margin-right"),
        ("first_line_indent", "text-indent"),
        ("space_before", "margin-top"),
        ("space_after", "margin-bottom"),
    ):
        try:
            value = getattr(fmt, attribute)
        except Exception:
            value = None
        if value:
            styles.append(f"{css_prop}:{value.pt:g}pt")
    spacing = getattr(fmt, "line_spacing", None)
    if isinstance(spacing, float) and spacing != 1.0:
        styles.append(f"line-height:{spacing:g}")
    return ";".join(styles)


def _attr(style: str) -> str:
    return f' style="{style}"' if style else ""


def _link_ok(url: str) -> bool:
    return url.lower().startswith(("http://", "https://", "mailto:"))


def _drawing_sizes(run) -> dict:
    """Map blip relationship ids to their ``wp:extent`` in points."""
    sizes = {}
    for drawing in run._r.xpath(".//w:drawing"):
        extent = drawing.xpath(".//wp:extent")
        if not extent:
            continue
        try:
            width = int(extent[0].get("cx")) / 12700
            height = int(extent[0].get("cy")) / 12700
        except (TypeError, ValueError):
            continue
        if width > 468:
            height *= 468 / width
            width = 468
        for rel in drawing.xpath(".//a:blip/@r:embed"):
            sizes[str(rel)] = (width, height)
    return sizes


def _image_embed(run, document, budget, notes) -> str:
    """Inline a run's embedded images as data URIs; empty string when none."""
    Image = conversions._pillow()

    out = []
    sizes = _drawing_sizes(run)
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
        size = sizes.get(str(rel_id))
        dims = f' width="{size[0]:.0f}" height="{size[1]:.0f}"' if size else ""
        out.append(f'<img src="data:{mime};base64,{encoded}"{dims} style="max-width:100%">')
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


def _cell_style(cell) -> str:
    from docx.oxml.ns import qn

    styles = []
    try:
        width = cell.width
    except Exception:
        width = None
    if width:
        styles.append(f"width:{width.pt:g}pt")
    tc_pr = cell._tc.tcPr
    if tc_pr is not None:
        shd = tc_pr.find(qn("w:shd"))
        if shd is not None:
            fill = shd.get(qn("w:fill"))
            if fill and fill.lower() != "auto":
                styles.append(f"background:#{fill.lstrip('#').lower()}")
        v_align = tc_pr.find(qn("w:vAlign"))
        if v_align is not None:
            value = v_align.get(qn("w:val"))
            if value in {"top", "center", "bottom"}:
                styles.append(f"vertical-align:{value}")
    return ";".join(styles)


def _table_html(table) -> list[list[dict]]:
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
                cells[-1]["span"] = colspan
            previous_tc = cell._tc
            colspan = 1
            text = "<br>".join(html.escape(paragraph.text) for paragraph in cell.paragraphs)
            cells.append(
                {
                    "text": text,
                    "span": 1,
                    "rowspan": 1,
                    "skip": False,
                    "style": _cell_style(cell),
                    "tc": cell._tc,
                }
            )
        if colspan:
            cells[-1]["span"] = colspan
        rows.append(cells)
    # Vertically merged cells resurface the same <w:tc> in later rows:
    # fold them into a rowspan on the origin cell instead.
    for index in range(1, len(rows)):
        for cell in rows[index]:
            origin = None
            for above in range(index - 1, -1, -1):
                for candidate in rows[above]:
                    if not candidate["skip"] and candidate["tc"] is cell["tc"]:
                        origin = candidate
                if origin is not None:
                    break
            if origin is not None:
                origin["rowspan"] += 1
                cell["skip"] = True
    return rows


def _num_list_kind(document, paragraph, style_name: str):
    """Return (tag, ol type) for a numbered/bulleted paragraph, else None."""
    from docx.oxml.ns import qn

    fallback = ("ol", "1") if "Number" in style_name else ("ul", "")
    p_pr = paragraph._p.pPr
    num_pr = p_pr.numPr if p_pr is not None else None
    if num_pr is None:
        return fallback if "List" in style_name else None
    try:
        num_id = num_pr.numId.val
        ilvl = num_pr.ilvl.val if num_pr.ilvl is not None else 0
    except Exception:
        return fallback
    if num_id is None:
        return fallback
    fmt = ""
    try:
        numbering = document.part.numbering_part.element
        abstract_id = None
        for num in numbering.xpath(f'./w:num[@w:numId="{num_id}"]/w:abstractNumId'):
            abstract_id = num.get(qn("w:val"))
        if abstract_id is not None:
            levels = numbering.xpath(
                f'./w:abstractNum[@w:abstractNumId="{abstract_id}"]/w:lvl[@w:ilvl="{ilvl}"]'
            ) or numbering.xpath(f'./w:abstractNum[@w:abstractNumId="{abstract_id}"]/w:lvl[@w:ilvl="0"]')
            if levels:
                fmt_nodes = levels[0].xpath("./w:numFmt")
                if fmt_nodes:
                    fmt = fmt_nodes[0].get(qn("w:val"), "")
    except Exception:
        return fallback
    if fmt == "bullet":
        return ("ul", "")
    if fmt:
        return ("ol", _LIST_TYPES.get(fmt, "1"))
    return fallback


def _docx_blocks(document, notes, *, for_pdf=False):
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks = []
    budget = [config.MAX_EMBEDDED_IMAGES]
    list_state = None  # None | (tag, type)

    def close_list():
        nonlocal list_state
        if list_state:
            blocks.append({"kind": "list_close", "html": f"</{list_state[0]}>", "text": None})
        list_state = None

    for element in document.element.body.iterchildren():
        if element.tag == qn("w:tbl"):
            close_list()
            rows = _table_html(Table(element, document))
            table_html = ['<table style="border-collapse:collapse;width:100%">']
            for cells in rows:
                table_html.append("<tr>")
                for cell in cells:
                    if cell["skip"]:
                        continue
                    attr = f' colspan="{cell["span"]}"' if cell["span"] > 1 else ""
                    if cell["rowspan"] > 1:
                        attr += f' rowspan="{cell["rowspan"]}"'
                    attr += _attr(cell["style"])
                    table_html.append(f"<td{attr}>{cell['text']}</td>")
                table_html.append("</tr>")
            table_html.append("</table>")
            blocks.append(
                {
                    "kind": "table",
                    "html": "".join(table_html),
                    "text": ["\t".join(c["text"] for c in cells if not c["skip"]) for cells in rows],
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
        para_attr = _attr(_paragraph_style(paragraph))

        inner = "".join(
            _inline_html(item, document, budget, notes) for item in paragraph.iter_inner_content()
        )
        # A page break run splits the paragraph in place.
        pieces = inner.split("\x00PAGEBREAK\x00")

        list_kind = None if level else _num_list_kind(document, paragraph, style_name)

        for position, piece in enumerate(pieces):
            if piece or position == 0:
                if level:
                    close_list()
                    tag = f"h{level}"
                    blocks.append(
                        {
                            "kind": "para",
                            "html": f"<{tag}{para_attr}>{piece}</{tag}>",
                            "text": paragraph.text,
                        }
                    )
                elif list_kind:
                    if list_state != list_kind:
                        close_list()
                        blocks.append({"kind": "list_open", "html": list_kind, "text": None})
                        list_state = list_kind
                    blocks.append(
                        {
                            "kind": "item",
                            "html": f"<li{para_attr}>{piece}</li>",
                            "text": paragraph.text,
                        }
                    )
                elif piece:
                    close_list()
                    blocks.append(
                        {
                            "kind": "para",
                            "html": f"<p{para_attr}>{piece}</p>",
                            "text": paragraph.text,
                        }
                    )
            if position < len(pieces) - 1:
                close_list()
                blocks.append({"kind": "pagebreak", "html": "", "text": None})
    close_list()

    html_parts = []
    text_parts = []
    for block in blocks:
        if block["kind"] == "list_open":
            tag, list_type = block["html"]
            type_attr = f' type="{list_type}"' if tag == "ol" and list_type else ""
            html_parts.append(f"<{tag}{type_attr}>")
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


def _page_css(document):
    """First-section page setup -> (page_size, margins) in points, else (None, None)."""
    try:
        section = document.sections[0]
        width, height = section.page_width.pt, section.page_height.pt
        if not width or not height:
            return None, None
        margins = (
            section.top_margin.pt,
            section.right_margin.pt,
            section.bottom_margin.pt,
            section.left_margin.pt,
        )
        return (width, height), margins
    except Exception:
        return None, None


def _header_footer(document) -> tuple[str, str]:
    """First-section header/footer text, wrapped in muted divs (once per doc)."""
    top, bottom = "", ""
    try:
        section = document.sections[0]
        for container, name in ((section.header, "docx-header"), (section.footer, "docx-footer")):
            text = "\n".join(
                paragraph.text for paragraph in container.paragraphs if paragraph.text.strip()
            ).strip()
            div = f'<div class="{name}">{html.escape(text)}</div>' if text else ""
            if name == "docx-header":
                top = div
            else:
                bottom = div
    except Exception:  # noqa: S110 -- headers are best-effort
        pass
    return top, bottom


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
    top, bottom = _header_footer(document)
    body = top + body + bottom
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
    top, bottom = _header_footer(document)
    body = top + body + bottom
    page_size, margins = _page_css(document)
    pdf_render.render_pdf(
        body,
        output_path,
        title=_docx_title(document, options.get("_stem", "")),
        page_size=page_size,
        margins=margins,
    )
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
    extra_css = pdf_render.sanitize_css(pdf_render.extract_styles(raw))
    body = pdf_render.sanitize_html(raw)
    pdf_render.render_pdf(body, output_path, title=title, extra_css=extra_css)
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
