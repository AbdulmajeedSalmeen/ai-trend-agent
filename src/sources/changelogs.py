"""Vendors' own changelogs, read as the vendor publishes them.

OpenAI's deprecations page is its official record of what it is shutting down: a
heading per announcement ("2025-09-26: Legacy GPT model snapshots") and under it
a table of shutdown dates, the model or system going away, every alias it
prints beside the snapshot, and the replacement it recommends. This reads that
page row by row, so the dates the agent reports are OpenAI's, fetched on the day
of the scan, not copied by hand.
"""
import re
from datetime import date, datetime
from html.parser import HTMLParser

import requests

DEPRECATIONS_URL = "https://developers.openai.com/api/docs/deprecations"
HEADERS = {"User-Agent": "ai-trend-agent/1.0 (SDA bootcamp capstone)"}
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%b. %d, %Y")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class Tables(HTMLParser):
    """Every table on a page, each with the heading above it, and every cell with its
    text and the code elements in it (model ids are written as code)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading, self.heading_text, self.in_heading = None, "", False
        self.tables, self.row, self.cell, self.code = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3"):
            self.in_heading, self.heading_text = True, ""
        elif tag == "table":
            self.tables.append((self.heading, []))
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = {"text": "", "codes": []}
        elif tag == "code" and self.cell is not None:
            self.code = ""

    def handle_endtag(self, tag):
        if tag in ("h2", "h3") and self.in_heading:
            self.in_heading, self.heading = False, clean(self.heading_text)
        elif tag == "code" and self.code is not None:
            self.cell["codes"].append(clean(self.code))
            self.code = None
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append({**self.cell, "text": clean(self.cell["text"])})
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.tables[-1][1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_heading:
            self.heading_text += data
        if self.cell is not None:
            self.cell["text"] += data
        if self.code is not None:
            self.code += data


def parse_date(text: str) -> str | None:
    """2026-09-28, Oct 1, 2026 or October 23, 2026, as an ISO date; None otherwise."""
    text = clean(text).replace("Sept ", "Sep ")
    found = ISO_RE.search(text)

    if found:
        return found.group()

    for pattern in DATE_FORMATS:
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue

    return None


def column(header: list[str], *words: str, avoid: tuple[str, ...] = ()) -> int | None:
    for index, name in enumerate(header):
        if any(word in name for word in words) and not any(word in name for word in avoid):
            return index

    return None


def openai_deprecations(page: str) -> list[dict]:
    """Every row with a shutdown date, newest announcement first, as OpenAI orders them.
    An id listed again under an older announcement keeps the newest row."""
    parser = Tables()
    parser.feed(page)
    found, seen = [], set()

    for heading, rows in parser.tables:
        if len(rows) < 2:
            continue

        header = [cell["text"].lower() for cell in rows[0]]
        when = column(header, "shutdown")
        what = column(header, "model", "system", "snapshot", avoid=("price", "replacement", "substitute"))
        instead = column(header, "replacement", "substitute")

        if when is None or what is None:
            continue

        announced = parse_date(heading.split(":", 1)[0]) if heading and ":" in heading else None

        for row in rows[1:]:
            if len(row) <= max(when, what):
                continue

            shutdown = parse_date(row[when]["text"])
            ids = [code for code in row[what]["codes"] if code] or [row[what]["text"]]
            ids = [model for model in ids if model and model not in seen]
            replacement = None

            if instead is not None and len(row) > instead:
                replacement = (row[instead]["codes"] or [row[instead]["text"]])[0] or None

            if not shutdown or not ids:
                continue

            seen.update(ids)
            found.append({"shutdown": shutdown, "announced": announced, "section": heading,
                          "ids": ids, "replacement": replacement})

    return found


def fetch(url: str = DEPRECATIONS_URL) -> str:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def today() -> str:
    return date.today().isoformat()
