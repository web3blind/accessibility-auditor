"""Safe same-site page discovery for public multi-page audits.

This module deliberately stays small and conservative: sitemap first, homepage
links as fallback, same-domain only, dangerous paths and non-HTML assets skipped.
It is not a broad crawler and it never clicks or submits anything.
"""

from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse, parse_qsl, urlencode

from bs4 import BeautifulSoup

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}
NON_HTML_EXTENSIONS = {
    ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp4", ".mov", ".avi", ".webm", ".mp3", ".wav", ".ogg",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".css", ".js", ".json", ".xml", ".txt", ".woff", ".woff2", ".ttf",
}
DANGEROUS_PATH_RE = re.compile(
    r"/(logout|signout|delete|remove|cart|checkout|payment|pay|admin|wp-admin|account|profile|settings|download)(/|$)",
    re.IGNORECASE,
)


@dataclass
class DiscoveryResult:
    root_url: str
    method: str
    candidate_urls: int
    selected_urls: list[str]
    skipped_urls: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "root_url": self.root_url,
            "method": self.method,
            "candidate_urls": self.candidate_urls,
            "selected_urls": self.selected_urls,
            "skipped_urls": self.skipped_urls,
        }


def normalize_url(url: str, base_url: str | None = None) -> str:
    """Normalize a URL for dedupe and same-site comparison."""
    joined = urljoin(base_url, url.strip()) if base_url else url.strip()
    joined, _fragment = urldefrag(joined)
    parsed = urlparse(joined)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parsed.path or "/"
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower = key.lower()
        if lower in TRACKING_QUERY_KEYS or lower.startswith(TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(query_items, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def host_key(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_same_domain(candidate_url: str, root_url: str) -> bool:
    return host_key(candidate_url) == host_key(root_url)


def should_skip_url(candidate_url: str, root_url: str) -> str | None:
    parsed = urlparse(candidate_url)
    if parsed.scheme not in {"http", "https"}:
        return "unsupported_scheme"
    if not is_same_domain(candidate_url, root_url):
        return "external_domain"
    path = parsed.path.lower()
    if DANGEROUS_PATH_RE.search(path):
        return "dangerous_or_private_path"
    for ext in NON_HTML_EXTENSIONS:
        if path.endswith(ext):
            return "non_html_resource"
    return None


def parse_sitemap_xml(xml_text: str, root_url: str, max_pages: int) -> DiscoveryResult:
    selected: list[str] = []
    skipped: list[dict[str, str]] = []
    candidates: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return DiscoveryResult(root_url=root_url, method="sitemap_xml_invalid", candidate_urls=0, selected_urls=[], skipped_urls=[])

    for loc in root.findall(".//{*}loc"):
        if loc.text:
            candidates.append(loc.text.strip())

    seen: set[str] = set()
    for raw in candidates:
        normalized = normalize_url(raw, root_url)
        if normalized in seen:
            continue
        seen.add(normalized)
        reason = should_skip_url(normalized, root_url)
        if reason:
            skipped.append({"url": normalized, "reason": reason})
            continue
        selected.append(normalized)
        if len(selected) >= max_pages:
            break

    return DiscoveryResult(
        root_url=root_url,
        method="sitemap",
        candidate_urls=len(candidates),
        selected_urls=selected,
        skipped_urls=skipped,
    )


def discover_homepage_links(html: str, root_url: str, max_pages: int) -> DiscoveryResult:
    soup = BeautifulSoup(html, "html.parser")
    raw_urls = [a.get("href") for a in soup.find_all("a", href=True)]
    selected: list[str] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()

    root = normalize_url(root_url)
    for raw in [root, *raw_urls]:
        if not raw:
            continue
        normalized = normalize_url(raw, root)
        if normalized in seen:
            continue
        seen.add(normalized)
        reason = should_skip_url(normalized, root)
        if reason:
            skipped.append({"url": normalized, "reason": reason})
            continue
        selected.append(normalized)
        if len(selected) >= max_pages:
            break

    return DiscoveryResult(
        root_url=root,
        method="homepage_links",
        candidate_urls=len(raw_urls) + 1,
        selected_urls=selected,
        skipped_urls=skipped,
    )


def default_fetch_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "AccessibilityAuditor/1.0 (+https://hexdrive.tech)"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
            return ""
        return response.read(2_000_000).decode("utf-8", errors="replace")


def discover_site_urls(
    root_url: str,
    max_pages: int,
    fetch_text: Callable[[str], str] | None = None,
) -> DiscoveryResult:
    """Discover a capped URL list, preferring sitemap.xml then homepage links."""
    fetch = fetch_text or default_fetch_text
    root = normalize_url(root_url)
    sitemap_url = urljoin(root, "/sitemap.xml")
    errors: list[dict[str, str]] = []

    try:
        sitemap_text = fetch(sitemap_url)
        sitemap_result = parse_sitemap_xml(sitemap_text, root, max_pages)
        if sitemap_result.selected_urls:
            return sitemap_result
        errors.extend(sitemap_result.skipped_urls)
    except Exception as exc:  # network/read errors are not fatal; fallback to homepage
        errors.append({"url": sitemap_url, "reason": f"sitemap_fetch_failed:{type(exc).__name__}"})

    try:
        homepage_html = fetch(root)
        result = discover_homepage_links(homepage_html, root, max_pages)
        result.method = "sitemap_then_homepage_links"
        result.skipped_urls = errors + result.skipped_urls
        return result
    except Exception as exc:
        return DiscoveryResult(
            root_url=root,
            method="discovery_failed",
            candidate_urls=0,
            selected_urls=[root] if should_skip_url(root, root) is None else [],
            skipped_urls=errors + [{"url": root, "reason": f"homepage_fetch_failed:{type(exc).__name__}"}],
        )
