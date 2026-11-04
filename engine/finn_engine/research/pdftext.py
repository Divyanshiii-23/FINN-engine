"""PDF text layer: cleaned lines per page, with page numbers kept for citation."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pymupdf

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
DASHES = re.compile(r"[‒–—−]")
QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"'}
PAGE_NO = re.compile(r"^(page\s*)?\d{1,3}(\s*(of|/)\s*\d{1,3})?$", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    for a, b in {**LIGATURES, **QUOTES}.items():
        s = s.replace(a, b)
    s = DASHES.sub("-", s).replace(" ", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


@dataclass
class Line:
    page: int
    text: str
    y: float


@dataclass
class PdfText:
    pages: int
    lines: list[Line]
    scanned_pages: list[int]

    def page_text(self, page: int) -> str:
        return "\n".join(l.text for l in self.lines if l.page == page)


def read(pdf_bytes: bytes) -> PdfText:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    raw: list[Line] = []
    scanned: list[int] = []
    for pno, page in enumerate(doc, start=1):
        txt = page.get_text("text")
        if len(txt.strip()) < 200 and page.get_images():
            area = page.rect.width * page.rect.height
            img = sum(r.width * r.height for x in page.get_images() for r in page.get_image_rects(x[0]))
            if area and img / area > 0.5:
                scanned.append(pno)
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = norm("".join(sp["text"] for sp in ln["spans"]))
                if t:
                    raw.append(Line(page=pno, text=t, y=ln["bbox"][1]))
    n = len(doc)
    # Running headers and footers: the same text in the same vertical band on more than half the pages.
    if n >= 2:
        counts = Counter((l.text, round(l.y / 10)) for l in raw)
        repeated = {k for k, c in counts.items() if c > n / 2 and c >= 2}
        raw = [l for l in raw if (l.text, round(l.y / 10)) not in repeated]
    raw = [l for l in raw if not PAGE_NO.match(l.text)]
    # Repair hyphenation at line ends within a page.
    out: list[Line] = []
    for l in raw:
        if out and out[-1].page == l.page and re.search(r"[a-z]-$", out[-1].text) and l.text[:1].islower():
            out[-1].text = out[-1].text[:-1] + l.text
        else:
            out.append(l)
    return PdfText(pages=n, lines=out, scanned_pages=scanned)


SENT = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z₹\"(])")


def sentences(text: str) -> list[str]:
    """Sentence split that keeps decimals, 'Rs.', 'Mr.' and 'No.' intact."""
    protected = re.sub(r"\b(Rs|Mr|Mrs|Ms|Dr|No|vs|approx|Ltd|Co|Inc|i\.e|e\.g)\.", lambda m: m.group(1) + "\x00", text)
    parts = [p.replace("\x00", ".").strip() for p in SENT.split(protected)]
    return [p for p in parts if p]
