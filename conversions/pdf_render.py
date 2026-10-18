"""Shared HTML -> PDF rendering via xhtml2pdf.

Bundled DejaVu Sans fonts give generated PDFs real Unicode coverage. The
resource policy locks the renderer to the font directory: no network, no other
local files. There is no bundled monospace face, so pre/code deliberately use
the same DejaVu Sans family rather than a font we do not ship.
"""

import dataclasses
import html
import logging
import re
from pathlib import Path

import nh3
from xhtml2pdf import pisa
from xhtml2pdf.config.resources import ResourceAccessPolicy

from core import config
from core.errors import ConversionError

for name in ("xhtml2pdf", "xhtml2pdf.parser", "reportlab"):
    logging.getLogger(name).setLevel(logging.ERROR)

FONT_DIR = Path(__file__).resolve().with_name("fonts")
_FONT_URL = FONT_DIR.as_posix()

_BASE_POLICY = ResourceAccessPolicy.server(base_dir=FONT_DIR, allow_remote=False)


def _policy() -> ResourceAccessPolicy:
    # Bound a single render to just under the whole-conversion timeout.
    return dataclasses.replace(_BASE_POLICY, max_render_seconds=max(config.CONVERSION_TIMEOUT - 10, 5))


def _base_css(
    landscape: bool,
    page_size: tuple[float, float] | None = None,
    margins: tuple[float, float, float, float] | None = None,
) -> str:
    if page_size:
        size = f"{page_size[0]:g}pt {page_size[1]:g}pt"
    else:
        size = f"a4{' landscape' if landscape else ''}"
    if margins:
        margin = " ".join(f"{value:g}pt" for value in margins)
    else:
        margin = "1.8cm"
    return f"""
@font-face {{ font-family: "DejaVu Sans"; src: url("{_FONT_URL}/DejaVuSans.ttf"); }}
@font-face {{ font-family: "DejaVu Sans"; font-weight: bold;
    src: url("{_FONT_URL}/DejaVuSans-Bold.ttf"); }}
@font-face {{ font-family: "DejaVu Sans"; font-style: italic;
    src: url("{_FONT_URL}/DejaVuSans-Oblique.ttf"); }}
@font-face {{ font-family: "DejaVu Sans"; font-weight: bold; font-style: italic;
    src: url("{_FONT_URL}/DejaVuSans-BoldOblique.ttf"); }}
@font-face {{ font-family: "Droid Sans Fallback";
    src: url("{_FONT_URL}/DroidSansFallbackFull.ttf"); }}
@font-face {{ font-family: "Noto Sans KR"; src: url("{_FONT_URL}/NotoSansKR-Regular.ttf"); }}
.x-cjk {{ font-family: "Droid Sans Fallback"; }}
.x-hangul {{ font-family: "Noto Sans KR"; }}
@page {{ size: {size}; margin: {margin}; }}
body {{ font-family: "DejaVu Sans"; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a; }}
h1 {{ font-size: 20pt; }} h2 {{ font-size: 16pt; }} h3 {{ font-size: 13.5pt; }} h4 {{ font-size: 12pt; }}
p {{ margin: 0 0 7pt 0; }}
pre, code {{ font-family: "DejaVu Sans"; }}
pre {{ white-space: pre-wrap; background: #f4f4f4; padding: 6pt; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #999; padding: 3pt 4pt; vertical-align: top; }}
th {{ background: #eee; }}
img {{ max-width: 100%; }}
blockquote {{ border-left: 2pt solid #ccc; padding-left: 8pt; color: #444; }}
hr {{ border: 0; border-top: 1px solid #bbb; }}
.docx-header, .docx-footer {{ color: #777; font-size: 9pt; white-space: pre-wrap; }}
"""


_CJK_RUN = re.compile(r"[　-ヿ㐀-䶿一-鿿豈-﫿＀-￯]+")
_HANGUL_RUN = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]+")


def apply_script_fonts(body_html: str) -> str:
    """Wrap Han/Kana/fullwidth runs in ``x-cjk`` spans and Hangul runs in
    ``x-hangul`` spans so generated PDFs use the bundled script fonts.

    Only text nodes are touched: the wrapping ``<div>`` lets the
    ``>text<`` pattern see the ends of the document, and the span names
    are ASCII so a second pass cannot re-wrap its own output.
    """

    def wrap(match: re.Match) -> str:
        text = _CJK_RUN.sub(r'<span class="x-cjk">\g<0></span>', match.group(1))
        text = _HANGUL_RUN.sub(r'<span class="x-hangul">\g<0></span>', text)
        return f">{text}<"

    wrapped = re.sub(r">([^<]*)<", wrap, f"<div>{body_html}</div>")
    return wrapped[len("<div>") : -len("</div>")]


def render_pdf(
    body_html: str,
    output_path: Path,
    *,
    title: str = "",
    landscape: bool = False,
    extra_css: str = "",
    page_size: tuple[float, float] | None = None,
    margins: tuple[float, float, float, float] | None = None,
) -> None:
    document = (
        '<html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        f"<style>{_base_css(landscape, page_size, margins)}{extra_css}</style>"
        f"</head><body>{apply_script_fonts(body_html)}</body></html>"
    )
    try:
        with open(output_path, "wb") as handle:
            status = pisa.CreatePDF(
                document,
                dest=handle,
                encoding="utf-8",
                resource_policy=_policy(),
            )
        if status.err:
            raise ConversionError("The PDF could not be generated from this document.")
    except ConversionError:
        raise
    # RenderLimitError / ResourceAccessError included: a refused resource or
    # an exhausted render budget is a failed render either way.
    except Exception as exc:
        raise ConversionError("The PDF could not be generated from this document.") from exc


# --- HTML sanitising ---------------------------------------------------------

ALLOWED_TAGS = set(nh3.ALLOWED_TAGS) | {
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "colgroup",
    "col",
    "img",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "hr",
    "pre",
    "code",
    "blockquote",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "b",
    "strong",
    "i",
    "em",
    "u",
    "s",
    "del",
    "ins",
    "sub",
    "sup",
    "span",
    "div",
    "a",
    "small",
    "mark",
    "figure",
    "figcaption",
    "section",
    "article",
    "header",
    "footer",
    "main",
    "address",
    "cite",
    "q",
    "abbr",
    "kbd",
    "samp",
    "var",
    "time",
    "big",
    "center",
}

ALLOWED_ATTRIBUTES = {
    "*": {"style", "title", "align", "valign", "width", "height", "dir", "lang", "class", "id"},
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "ol": {"start", "type"},
    "table": {"border", "cellpadding", "cellspacing"},
}

_UNSAFE_CSS = ("url(", "expression(", "@import", "javascript:", "-moz-binding", "behavior:", "\\")
_BLOCKED_PROPERTIES = {"font-family", "font"}


def _filter_style(value: str):
    """Drop only the forbidden declarations from an inline ``style`` value."""
    lowered = value.lower()
    if any(token in lowered for token in _UNSAFE_CSS):
        return None
    kept = [
        declaration.strip()
        for declaration in value.split(";")
        if declaration.strip() and declaration.split(":", 1)[0].strip().lower() not in _BLOCKED_PROPERTIES
    ]
    return "; ".join(kept) or None


def _make_attribute_filter(allow_remote_images: bool):
    def attribute_filter(element: str, attribute: str, value: str):
        if attribute == "style":
            return _filter_style(value)
        # Remote images are dropped even though http(s) is an allowed scheme
        # for links: the renderer must never have a reason to go to the
        # network. Only HTML output (never rendered here) may keep them.
        if element == "img" and attribute == "src":
            lowered = value.lower()
            if lowered.startswith("data:image/"):
                return value
            if allow_remote_images and lowered.startswith(("http://", "https://")):
                return value
            return None
        return value

    return attribute_filter


def sanitize_html(raw: str, *, allow_remote_images: bool = False) -> str:
    """Allow-list sanitising for user HTML.

    nh3 drops <style>/<script> blocks entirely (clean-content tags), removes
    every attribute not in the allow-list and enforces the URL scheme list.
    ``img src`` is limited to data URIs unless ``allow_remote_images`` is
    true, which is only ever used for HTML output — never PDF rendering.
    """
    return nh3.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "data"},
        strip_comments=True,
        # nh3 removes these tags' contents too — otherwise <title> text
        # would leak into the document body.
        clean_content_tags={"script", "style", "title"},
        attribute_filter=_make_attribute_filter(allow_remote_images),
        link_rel=None,
    )


# --- Author stylesheet passthrough -------------------------------------------

_STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# A declaration ends at ';', at the closing '}' of its block, or at end of
# input -- matching all three keeps a final `url(...)` from slipping through.
_DECLARATION = re.compile(r"([\w-]+)\s*:\s*([^;{}]*)(;|(?=\})|$)")
_FORBIDDEN_VALUE = ("url(", "expression(", "javascript:", "-moz-binding", "behavior", "\\")
_FORBIDDEN_AT_STATEMENT = {"import", "namespace", "charset"}
_FORBIDDEN_AT_BLOCK = {"font-face", "keyframes"}


def extract_styles(raw: str) -> str:
    """Concatenate every ``<style>`` block in *raw* HTML."""
    css = "\n".join(_STYLE_BLOCK.findall(raw))
    return re.sub(r"<!--|-->", "", css)


def _drop_at_rule(css: str, start: int, block: bool) -> int:
    """Return the index just past the at-rule beginning at ``start``."""
    if not block:
        end = css.find(";", start)
        return len(css) if end < 0 else end + 1
    brace = css.find("{", start)
    if brace < 0:
        return len(css)
    depth = 0
    for index in range(brace, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(css)


def _drop_forbidden_at_rules(css: str) -> str:
    kept = []
    index = 0
    while index < len(css):
        if css[index] == "@":
            match = re.match(r"@([\w-]+)", css[index:])
            name = match.group(1).lower() if match else ""
            if name in _FORBIDDEN_AT_STATEMENT:
                index = _drop_at_rule(css, index, block=False)
                continue
            if name in _FORBIDDEN_AT_BLOCK:
                index = _drop_at_rule(css, index, block=True)
                continue
        kept.append(css[index])
        index += 1
    return "".join(kept)


def sanitize_css(css: str) -> str:
    """Allow the presentation layer of author CSS while removing anything
    that could reach the network, a local file or a non-bundled font."""

    def keep(match: re.Match) -> str:
        prop, value = match.group(1).strip().lower(), match.group(2).strip().lower()
        if prop in _BLOCKED_PROPERTIES or any(token in value for token in _FORBIDDEN_VALUE):
            return ""
        return match.group(0)

    cleaned = _CSS_COMMENT.sub("", css)
    cleaned = _DECLARATION.sub(keep, cleaned)
    cleaned = _drop_forbidden_at_rules(cleaned)
    return cleaned[: config.MAX_CSS_BYTES]
