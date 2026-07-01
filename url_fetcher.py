"""
url_fetcher.py

Fetches one or more URLs and extracts readable plain text from HTML.
Uses only stdlib + requests (already in requirements.txt) — no new dependencies.

Public API:
    fetch_urls(urls, max_chars_per_url) -> List[FetchResult]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urlparse

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_MAX_CHARS = 8_000   # per URL, before truncation
REQUEST_TIMEOUT   = 15       # seconds
USER_AGENT        = (
    "Mozilla/5.0 (compatible; QAReviewer/1.0; +documentation-fetch)"
)

# Tags whose entire subtree we ignore
_SKIP_TAGS = frozenset({
    "script", "style", "noscript",
    "nav", "header", "footer", "aside",
    "svg", "canvas", "iframe", "form",
})

# Tags that act as block separators → insert a newline
_BLOCK_TAGS = frozenset({
    "p", "div", "section", "article", "main",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "dt", "dd", "tr", "td", "th",
    "blockquote", "pre", "br", "hr",
})


# ---------------------------------------------------------------------------
# HTML → plain text extractor
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth: int = 0
        self._parts: list[str] = []
        self.title: str = ""
        self._in_title: bool = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK_TAGS and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        # Collapse whitespace / blank lines
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _html_to_text(html: str) -> tuple[str, str]:
    """Return (title, body_text) from raw HTML string."""
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.title.strip(), extractor.get_text()


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    url:   str
    title: str           = ""
    text:  str           = ""
    chars: int           = 0
    truncated: bool      = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def as_context_block(self) -> str:
        """Format for inclusion in an LLM prompt."""
        if not self.ok:
            return f"[Documentation URL: {self.url}]\nFetch error: {self.error}\n"
        header = f"[Documentation: {self.title or self.url}]\nSource: {self.url}"
        if self.truncated:
            header += f"  (truncated to {self.chars} chars)"
        return f"{header}\n\n{self.text}"


# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------

def _fetch_one(url: str, max_chars: int) -> FetchResult:
    # Basic URL sanity check
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return FetchResult(url=url, error="Only http/https URLs are supported.")

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return FetchResult(url=url, error=f"Request timed out after {REQUEST_TIMEOUT}s.")
    except requests.exceptions.ConnectionError as exc:
        return FetchResult(url=url, error=f"Connection error: {exc}")
    except requests.exceptions.HTTPError as exc:
        return FetchResult(url=url, error=f"HTTP {response.status_code}: {exc}")
    except Exception as exc:
        return FetchResult(url=url, error=str(exc))

    content_type = response.headers.get("content-type", "").lower()

    if "text/html" not in content_type and "text/plain" not in content_type:
        return FetchResult(
            url=url,
            error=f"Unsupported content type: {content_type!r}. Only HTML and plain text are supported.",
        )

    if "text/plain" in content_type:
        text = response.text.strip()
        title = urlparse(url).path.split("/")[-1] or url
    else:
        try:
            title, text = _html_to_text(response.text)
        except Exception as exc:
            return FetchResult(url=url, error=f"HTML parsing failed: {exc}")

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return FetchResult(
        url=url,
        title=title,
        text=text,
        chars=len(text),
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_urls(
    urls: List[str],
    max_chars_per_url: int = DEFAULT_MAX_CHARS,
) -> List[FetchResult]:
    """
    Fetch a list of URLs and extract readable text from each.

    Args:
        urls:              List of http/https URLs to fetch.
        max_chars_per_url: Maximum characters of extracted text to keep per URL.

    Returns:
        List of FetchResult objects, one per input URL, in the same order.
        Failed fetches have result.ok == False and result.error set.
    """
    results = []
    for url in urls:
        url = url.strip()
        if url:
            results.append(_fetch_one(url, max_chars_per_url))
    return results


def results_to_context(results: List[FetchResult]) -> str:
    """
    Combine a list of FetchResult objects into a single prompt context block.
    Skips results with errors (they are logged separately in the UI).
    """
    blocks = [r.as_context_block() for r in results if r.ok]
    if not blocks:
        return ""
    separator = "\n\n" + "─" * 60 + "\n\n"
    return separator.join(blocks)
