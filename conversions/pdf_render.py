"""Shared HTML -> PDF rendering via xhtml2pdf.

Bundled DejaVu Sans fonts give generated PDFs real Unicode coverage. The
resource policy locks the renderer to the font directory: no network, no other
local files. There is no bundled monospace face, so pre/code deliberately use
the same DejaVu Sans family rather than a font we do not ship.
"""

import dataclasses
import html
import logging
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


def _base_css(landscape: bool) -> str:
    orientation = " landscape" if landscape else ""
    return f"""
@font-face {{ font-family: "DejaVu Sans"; src: url("{_FONT_URL}/DejaVuSans.ttf"); }}
@font-face {{ font-family: "DejaVu Sans"; font-weight: bold;
    src: url("{_FONT_URL}/DejaVuSans-Bold.ttf"); }}
@font-face {{ font-family: "DejaVu Sans"; font-style: italic;
    src: url("{_FONT_URL}/DejaVuSans-Oblique.ttf"); }}
@font-face {{ font-family: "DejaVu Sans"; font-weight: bold; font-style: italic;
    src: url("{_FONT_URL}/DejaVuSans-BoldOblique.ttf"); }}
@page {{ size: a4{orientation}; margin: 1.8cm; }}
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
"""


def render_pdf(
    body_html: str,
    output_path: Path,
    *,
    title: str = "",
    landscape: bool = False,
    extra_css: str = "",
) -> None:
    document = (
        '<html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        f"<style>{_base_css(landscape)}{extra_css}</style>"
        f"</head><body>{body_html}</body></html>"
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
    "*": {"style", "title", "align", "valign", "width", "height", "dir", "lang"},
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "ol": {"start", "type"},
    "table": {"border", "cellpadding", "cellspacing"},
}

_UNSAFE_CSS = ("url(", "expression(", "@import", "javascript:", "-moz-binding", "behavior:", "\\")


def _make_attribute_filter(allow_remote_images: bool):
    def attribute_filter(element: str, attribute: str, value: str):
        if attribute == "style":
            lowered = value.lower()
            if any(token in lowered for token in _UNSAFE_CSS):
                return None
            return value
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
