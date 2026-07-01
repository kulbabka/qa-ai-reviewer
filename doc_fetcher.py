"""
doc_fetcher.py

Fetches one or more documentation URLs and extracts their readable text content.

Each result contains:
    {
        "url":       str,          # original URL
        "title":     str,          # page <title>
        "content":   str,          # cleaned text, truncated if needed
        "truncated": bool,         # True if content was cut
        "error":     str | None,   # error message if fetch/parse failed
    }

Supports: HTML pages, plain-text / Markdown pages.
Does NOT support: PDFs, login-protected pages, JS-rendered SPAs.
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Maximum characters kept per page (to keep prompts manageable).
# ~6 000 chars ≈ ~1 500 words — enough for a dense docs page.
MAX_CONTENT_CHARS = 6_000

FETCH_TIMEOUT = 15  # seconds

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Tags that contain no useful reading content
_NOISE_TAGS = [
    "script", "style", "nav", "header", "footer", "aside",
    "iframe", "noscript", "figure", "form", "button",
]

# CSS class / id fragments that typically wrap navigation noise
_NOISE_CLASS_PATTERNS = re.compile(
    r"(sidebar|toc|breadcrumb|menu|cookie|banner|ad-|promo|related|share|social)",
    re.I,
)


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

def _is_noise_element(tag: Tag) -> bool:
    """Return True if a tag looks like navigation / chrome noise."""
    for attr in ("class", "id", "role"):
        value = " ".join(tag.get(attr, [])) if isinstance(tag.get(attr), list) else tag.get(attr, "")
        if _NOISE_CLASS_PATTERNS.search(value):
            return True
    if tag.get("role") in ("navigation", "banner", "complementary", "contentinfo"):
        return True
    return False


def _extract_main_content(soup: BeautifulSoup) -> str:
    """Remove noise, find the main reading area, return clean text."""
    # Remove obvious noise tags
    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    # Remove noise-looking elements by class/id/role
    for tag in soup.find_all(True):
        if _is_noise_element(tag):
            tag.decompose()

    # Find main reading area — try semantic containers first
    main: Optional[Tag] = (
        soup.find("article")
        or soup.find("main")
        or soup.find(role="main")
        or soup.find(id=re.compile(r"(content|main|body|article)", re.I))
        or soup.find(class_=re.compile(r"(content|main|prose|markdown|docs)", re.I))
        or soup.body
    )

    if main is None:
        return soup.get_text(" ", strip=True)

    # Convert to plain text, one logical line per block element
    lines = [line.strip() for line in main.get_text("\n", strip=True).splitlines() if line.strip()]
    return "\n".join(lines)


def _clean_html(html: str) -> tuple[str, str]:
    """Return (title, content) from an HTML string."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    # Strip site name suffix from title (e.g. "Page — Site Name")
    title = re.split(r"\s[|·—–-]\s", title)[0].strip()
    content = _extract_main_content(soup)
    return title, content


# ---------------------------------------------------------------------------
# Plain-text / Markdown pages
# ---------------------------------------------------------------------------

def _clean_plaintext(text: str) -> tuple[str, str]:
    """
    For responses that are already plain text or Markdown.
    Title = first non-empty line (stripped of leading #).
    """
    lines = [l for l in text.splitlines() if l.strip()]
    title = re.sub(r"^#+\s*", "", lines[0]).strip() if lines else ""
    content = "\n".join(lines)
    return title, content


# ---------------------------------------------------------------------------
# Single URL fetcher
# ---------------------------------------------------------------------------

def _fetch_one(url: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "url": url,
        "title": "",
        "content": "",
        "truncated": False,
        "error": None,
    }

    # Basic URL validation
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        result["error"] = "Only http/https URLs are supported."
        return result

    try:
        response = httpx.get(
            url,
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        result["error"] = f"Request timed out after {FETCH_TIMEOUT}s."
        return result
    except httpx.HTTPStatusError as exc:
        result["error"] = f"HTTP {exc.response.status_code} — {exc.response.reason_phrase}"
        return result
    except httpx.RequestError as exc:
        result["error"] = f"Network error: {exc}"
        return result

    content_type = response.headers.get("content-type", "").lower()

    if "html" in content_type:
        title, content = _clean_html(response.text)
    elif "markdown" in content_type or "plain" in content_type or url.endswith(".md"):
        title, content = _clean_plaintext(response.text)
    elif "pdf" in content_type:
        result["error"] = "PDF files are not supported. Link to the HTML version instead."
        return result
    else:
        # Try HTML parsing as a fallback
        try:
            title, content = _clean_html(response.text)
        except Exception:
            title, content = "", response.text[:MAX_CONTENT_CHARS]

    # Truncate if needed
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS]
        result["truncated"] = True

    result["title"] = title or url
    result["content"] = content
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_doc_urls(urls: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch and clean content from a list of documentation URLs.

    Args:
        urls: List of URL strings. Empty strings are skipped.

    Returns:
        List of result dicts, one per non-empty URL:
        {url, title, content, truncated, error}
    """
    results = []
    for raw in urls:
        url = raw.strip()
        if url:
            results.append(_fetch_one(url))
    return results


def format_docs_for_prompt(fetch_results: List[Dict[str, Any]]) -> str:
    """
    Format fetched documentation results into a prompt-ready string.

    Failed fetches are noted but not omitted, so the model is aware
    of what documentation was attempted.
    """
    if not fetch_results:
        return ""

    parts = []
    for i, r in enumerate(fetch_results, start=1):
        header = f"[Doc {i}] {r['title'] or r['url']}\nSource: {r['url']}"
        if r["error"]:
            parts.append(f"{header}\nStatus: FAILED — {r['error']}")
        else:
            truncation_note = "\n[Content truncated — first 6 000 chars shown]" if r["truncated"] else ""
            parts.append(f"{header}{truncation_note}\n\n{r['content']}")

    return "\n\n" + ("─" * 60) + "\n\n".join(parts)
