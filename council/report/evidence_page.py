"""evidence_page.py - the full evidence document as one web page (owner ruling AC40(2b)).

In the reviewed mode the owner approves the WHOLE evidence before any seat is paid (owner rulings
AC15 P6 and AC3). The system writes that document as Markdown, EVIDENCE-FULL.md, which he cannot
open. This module turns those exact Markdown bytes into the page he reads: the same text, the
report's look (dark by default, the theme toggle, a light printed copy, the section menu), one
self-contained file that opens from disk and fetches nothing (ruling Y2). Nothing is folded: the
document a person approves shows everything.

A PURE FUNCTION OF THE MARKDOWN. `render_page(markdown_text)` reads nothing else - not the pack,
not a clock - so the Markdown's sha256, which the go is recorded against, pins the page's content.
The page prints that sha256 at its foot. `python -m council.evidence.brief ... --full` writes the
page beside the Markdown from the bytes it just wrote, and `host init`, in the reviewed mode,
refuses a page whose bytes are not `render_page` of the approved Markdown.

THE CONVERTER reads exactly the Markdown `council.evidence.brief.render_full` writes, which is
"HTML-safe Markdown": every model-written string went through `brief._escape`. The reading is the
inverse of that escaping, in one left-to-right scan: a back-slash before an ASCII punctuation mark
is that mark (the CommonMark rule; `_escape` doubles every back-slash, so this undoes it exactly),
and `&amp;`, `&lt;`, `&gt;` are the characters they stand for. The renderer's own marks are
structure only where they are not escaped: `**` pairs into bold, a back-tick pair is a code span
(its inside is literal, never unescaped), `|` separates table cells, `- ` begins a list item and
`#` a heading. Everything else - any other character, an unpaired mark, a shape this module does
not know - renders as its own text, escaped once for HTML. The converter never makes a link, an
image or raw HTML out of the document's text.

The blocks it knows: headings `#` to `######`; `- ` list items, nested by two spaces a level; the
document's own separator; a pipe table (a row of cells, then a `| --- |` row, then body rows); and
paragraphs, consecutive lines of one paragraph kept on their own lines. A blank line ends any block.

ONE RULE ON THE PAGE. The only horizontal rule is the document's own separator: the `---` line
`render_full` writes between the one-page summary and the full evidence, known by what follows it -
a blank line, then the full evidence's own `#` heading (`FULL_HEADING`), a line no capture text can
write because `_escape` escapes a leading `#`. Every other line, a passage made only of dashes
included, prints as its text.

HOVER HELP AND SECTION TITLES (unit READ-B2, the owner's findings 2 and 5 of 2026-09-25). The page
carries the report's own hover note on every term its glossary data holds, wherever the term stands
in a name: a table row's name, a heading below the section titles, and the label before a colon in
a list item or a table cell. The notes and the section numbers are the page's; the Markdown, and so
the hash the go is recorded against, carries neither. The page also reads the report's glossary
data, so it is a pure function of the Markdown and of the code that renders it.

Stdlib only (ruling X). The shell - head, style, menu, toggle, script - is the report's own, read
from `render_report` and never changed there (its `markdown()` is not used: it escapes an escaped
`&amp;` a second time, shows the back-slashes and has no tables).
"""
import hashlib
import os
import re
import string
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.evidence.trace import MARKER  # noqa: E402
from council.report.render_report import (  # noqa: E402
    CSS, NAV_ICON, PREAMBLE, SCRIPT, Page, _TERM_NOTES, _TERM_PATTERN,
    _note_span, esc)

# The page's own name for itself, printed in its foot. The brief command's overwrite guard reads
# it back: an existing file at the page's path is replaced only when it opens with the report's
# preamble and carries this name, as the report's own guard does with its renderer's name.
RENDERER_SIGNATURE = "council/report/evidence_page.py"
DOCUMENT_NAME = "EVIDENCE-FULL.md"
TITLE = "Investment Council - the full evidence, for approval"

# A few rules of this page's own, after the report's style: nested lists sit close under their
# item, and a table is as wide as its cells (long unbroken lines wrap by the report's own rule).
PAGE_CSS = """
.wrap li>ul{margin:3px 0}
.wrap>table{width:auto;min-width:40%}
"""

_ASCII_PUNCTUATION = frozenset(string.punctuation)
_ENTITIES = (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"))
_HEADING = re.compile(r"^(#{1,6}) (.*)$")
# The full evidence's own heading, the line `render_full` writes after its separator.
FULL_HEADING = "# The full evidence - the document approved in reviewed mode"
_ITEM = re.compile(r"^( *)- (.*)$")
_DELIMITER_ROW = re.compile(r"^\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*$")


def page_path(markdown_path):
    """Where the page goes: beside the Markdown, `.md` replaced by `.html` (or `.html` added)."""
    root, extension = os.path.splitext(markdown_path)
    return (root if extension.lower() == ".md" else markdown_path) + ".html"


def is_own_page(path):
    """True when the file at `path` is a page this module wrote: the report's preamble first and
    this renderer's name inside. The brief command overwrites nothing else."""
    try:
        with open(path, "rb") as handle:
            existing = handle.read()
    except OSError:
        return False
    return (existing.startswith(PREAMBLE)
            and RENDERER_SIGNATURE.encode("ascii") in existing)


# --------------------------------------------------------------------------------- inline text

def _tokens(text):
    """One line's text as ("text", s) / ("code", s) / ("strong", "**") tokens, read left to right.
    A `**` without a partner later on the line is its own text."""
    tokens = []
    plain = []
    i, n = 0, len(text)

    def flush():
        if plain:
            tokens.append(("text", "".join(plain)))
            del plain[:]

    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and text[i + 1] in _ASCII_PUNCTUATION:
            plain.append(text[i + 1])
            i += 2
        elif c == "&":
            for entity, character in _ENTITIES:
                if text.startswith(entity, i):
                    plain.append(character)
                    i += len(entity)
                    break
            else:
                plain.append(c)
                i += 1
        elif c == "`" and text.find("`", i + 1) != -1:
            close = text.find("`", i + 1)
            flush()
            tokens.append(("code", text[i + 1:close]))
            i = close + 1
        elif text.startswith("**", i):
            flush()
            tokens.append(("strong", "**"))
            i += 2
        else:
            plain.append(c)
            i += 1
    flush()
    marks = [index for index, token in enumerate(tokens) if token[0] == "strong"]
    if len(marks) % 2:
        tokens[marks[-1]] = ("text", "**")
    return tokens


# A label before a colon is short and one phrase; a longer stretch is prose, left unmarked.
LABEL_MAX = 90

# The untraced-figure marker as the document writes it, after a number (owner ruling AC19).
_MARK = " " + MARKER


def _glossed(text):
    """A name as HTML with the report's hover note on each glossary term in it, read as if the
    untraced-figure marker were not there: "200 [not traced ...]-day average" is still the term
    "200-day average" (audit UPGRADE2-READ-B2 r3-1). The marker prints where the document put it,
    inside the term's note where it splits the term. Without a marker this is the report's own
    `_glossed`, byte for byte."""
    text = "" if text is None else str(text)
    lead = ""
    while text.startswith(_MARK):
        lead, text = lead + _MARK, text[len(_MARK):]
    plain, cuts = "", []
    for index, part in enumerate(text.split(_MARK)):
        if index:
            cuts.append(len(plain))
        plain += part

    def shown(start, end):
        # The plain stretch [start, end) with each marker after its number put back.
        out, at = [], start
        for cut in cuts:
            if start < cut <= end:
                out.append(plain[at:cut] + _MARK)
                at = cut
        return "".join(out) + plain[at:end]

    out, last, seen = [esc(lead)], 0, set()
    for match in _TERM_PATTERN.finditer(plain):
        key = match.group(1).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(esc(shown(last, match.start()))
                   + _note_span(shown(match.start(), match.end()), _TERM_NOTES[key]))
        last = match.end()
    return "".join(out) + esc(shown(last, len(plain)))


def _labels(text):
    """Plain text as HTML, the label before each colon carrying the report's hover notes: the
    text is read in "; "-separated pieces, and a piece's label is what stands before its first
    ": "."""
    out = []
    for piece in re.split(r"(; )", text):
        at = piece.find(": ")
        label = piece[:at]
        if 0 < at <= LABEL_MAX and ". " not in label:
            out.append(_glossed(label) + esc(piece[at:]))
        else:
            out.append(esc(piece))
    return "".join(out)


def _inline(text, names=None):
    """One line's text as HTML. `names` is None for text read as it stands, "whole" where the
    whole text is a name (a table row's name, a heading) and "labels" where the labels before
    its colons are names; a name carries the report's hover note on each glossary term in it."""
    out = []
    bold = False
    for kind, value in _tokens(text):
        if kind == "strong":
            out.append("</strong>" if bold else "<strong>")
            bold = not bold
        elif kind == "code":
            out.append("<code>%s</code>" % esc(value))
        elif names == "whole":
            out.append(_glossed(value))
        elif names == "labels":
            out.append(_labels(value))
        else:
            out.append(esc(value))
    return "".join(out)


def _plain(text):
    """One line's text as a reader sees it, without its marks (the section menu's labels)."""
    return "".join(value for kind, value in _tokens(text) if kind != "strong")


def _cells(row):
    """A table row's cells, split on the pipes that are not escaped. An escaped pipe stays in its
    cell as `\\|`, for the inline reading to turn into the character."""
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    cells, current = [], []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            current.append(body[i:i + 2])
            i += 2
        elif body[i] == "|":
            cells.append("".join(current))
            current = []
            i += 1
        else:
            current.append(body[i])
            i += 1
    tail = "".join(current)
    if tail.strip():
        cells.append(tail)
    return [cell.strip() for cell in cells]


# --------------------------------------------------------------------------------------- blocks

def _body(page, lines):
    """Every block of the document, in order, added to `page`. `##` headings open the menu's
    sections."""
    paragraph = []
    lists = []          # one entry per open <ul>
    sections = [0]
    i = 0

    def close_paragraph():
        if paragraph:
            page.add("<p>%s</p>\n" % "<br>".join(_inline(line) for line in paragraph))
            del paragraph[:]

    def close_lists(depth=0):
        while len(lists) > depth:
            lists.pop()
            page.add("</li></ul>\n")

    def close_blocks():
        close_paragraph()
        close_lists()

    while i < len(lines):
        line = lines[i]
        heading = _HEADING.match(line)
        item = _ITEM.match(line)
        if not line.strip():
            close_blocks()
        elif heading:
            close_blocks()
            level, text = len(heading.group(1)), heading.group(2).strip()
            if level == 2:
                # Numbered, at the report's section size (unit READ-B2).
                sections[0] += 1
                page.numbered("s%d" % sections[0], str(sections[0]), _plain(text))
            else:
                page.add("<h%d>%s</h%d>\n" % (level, _inline(
                    text, "whole" if level > 2 else None), level))
        elif (line == "---" and lines[i + 1:i + 3] == ["", FULL_HEADING]):
            close_blocks()
            page.add("<hr>\n")
        elif item:
            close_paragraph()
            depth = min(len(item.group(1)) // 2, len(lists))
            if len(lists) > depth:
                close_lists(depth + 1)
                page.add("</li>\n<li>")
            else:
                page.add("<ul>\n<li>")
                lists.append(depth)
            page.add(_inline(item.group(2), "labels"))
        elif (line.startswith("|") and i + 1 < len(lines)
              and _DELIMITER_ROW.match(lines[i + 1])):
            close_blocks()
            rows = ["<tr>%s</tr>" % "".join("<th>%s</th>" % _inline(cell)
                                            for cell in _cells(line))]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                # The first cell is the row's name; the others read their labels.
                rows.append("<tr>%s</tr>" % "".join(
                    "<td>%s</td>" % _inline(cell, "labels" if column else "whole")
                    for column, cell in enumerate(_cells(lines[i]))))
                i += 1
            page.add("<table>\n%s\n</table>\n" % "\n".join(rows))
            continue
        else:
            close_lists()
            paragraph.append(line.strip())
        i += 1
    close_blocks()


def render_page(markdown_text):
    """The page, as one string, for the full evidence document whose text is `markdown_text`."""
    digest = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()
    page = Page()
    _body(page, markdown_text.split("\n"))
    page.add('<div class="foot">This page is the reading copy of the full evidence document, '
             '<code>%s</code>, whose sha256 is <code>%s</code>; the go is recorded against that '
             'hash. It is rendered from that document\'s own bytes by <code>%s</code> and '
             'fetches nothing.</div>' % (esc(DOCUMENT_NAME), digest, RENDERER_SIGNATURE))
    return "".join([
        PREAMBLE.decode("ascii"),
        '<head>\n<meta charset="UTF-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        "<title>", esc(TITLE), "</title>\n<style>", CSS, PAGE_CSS, "</style>\n</head>\n<body>\n",
        '<nav class="dock" id="dock">',
        '<button type="button" class="dockbtn" id="navbtn" aria-haspopup="true" '
        'aria-expanded="false" aria-controls="navmenu" title="Sections">',
        '<span class="srconly">Sections</span>', NAV_ICON, "</button>",
        '<div class="menu" id="navmenu"><div class="menucard">',
        '<a href="#top">Top of the document</a>', page.menu(), "</div></div></nav>\n",
        '<button type="button" class="themebtn" id="themebtn" aria-label="Switch to light" '
        'title="Switch to light">&#x25D2;</button>\n',
        '<div class="wrap report" id="top">\n', page.body(), "\n</div>\n",
        "<script>", SCRIPT, "</script>\n</body>\n</html>\n",
    ])
