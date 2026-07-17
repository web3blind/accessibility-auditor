import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from site_discovery import (
    discover_homepage_links,
    discover_site_urls,
    is_same_domain,
    normalize_url,
    parse_sitemap_xml,
    should_skip_url,
)


def test_normalize_url_strips_fragment_tracking_and_default_port():
    assert normalize_url("HTTPS://Example.com:443/a/?utm_source=x&ok=1#main") == "https://example.com/a/?ok=1"


def test_same_domain_accepts_www_variant_only():
    assert is_same_domain("https://www.example.com/about", "https://example.com")
    assert not is_same_domain("https://evil-example.com", "https://example.com")
    assert not is_same_domain("https://blog.example.com", "https://example.com")


def test_skip_rules_block_external_private_and_assets():
    root = "https://example.com"
    assert should_skip_url("https://other.com/page", root) == "external_domain"
    assert should_skip_url("https://example.com/logout", root) == "dangerous_or_private_path"
    assert should_skip_url("https://example.com/report.pdf", root) == "non_html_resource"
    assert should_skip_url("https://example.com/about", root) is None


def test_parse_sitemap_filters_and_caps_urls():
    xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/</loc></url>
      <url><loc>https://example.com/about</loc></url>
      <url><loc>https://example.com/admin</loc></url>
      <url><loc>https://other.com/page</loc></url>
    </urlset>
    """
    result = parse_sitemap_xml(xml, "https://example.com", max_pages=2)
    assert result.method == "sitemap"
    assert result.selected_urls == ["https://example.com/", "https://example.com/about"]


def test_homepage_link_discovery_keeps_root_and_safe_internal_links():
    html = """
    <a href="/about#team">About</a>
    <a href="https://example.com/checkout">Checkout</a>
    <a href="https://other.com/">Other</a>
    <a href="/image.png">Image</a>
    """
    result = discover_homepage_links(html, "https://example.com", max_pages=5)
    assert result.selected_urls == ["https://example.com/", "https://example.com/about"]
    reasons = {item["reason"] for item in result.skipped_urls}
    assert {"dangerous_or_private_path", "external_domain", "non_html_resource"} <= reasons


def test_discover_site_urls_uses_sitemap_then_homepage_fallback():
    def fetch(url: str) -> str:
        if url.endswith("/sitemap.xml"):
            raise OSError("no sitemap")
        return '<a href="/pricing">Pricing</a><a href="/delete">Delete</a>'

    result = discover_site_urls("https://example.com", max_pages=3, fetch_text=fetch)
    assert result.method == "sitemap_then_homepage_links"
    assert result.selected_urls == ["https://example.com/", "https://example.com/pricing"]
