from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    value = value.replace("https://doi.org/", "").replace("http://doi.org/", "")
    value = value.replace("https://dx.doi.org/", "").replace("http://dx.doi.org/", "")
    m = DOI_RE.search(value)
    return m.group(0).lower() if m else None


def extract_doi_from_text(text: str | None) -> str | None:
    if not text:
        return None
    m = DOI_RE.search(text)
    return m.group(0).lower() if m else None


def extract_doi_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.endswith("doi.org"):
        return normalize_doi(unquote(parsed.path.lstrip("/")))
    return extract_doi_from_text(unquote(url))
