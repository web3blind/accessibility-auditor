#!/usr/bin/env python3
"""
Standalone script: fetches a URL with headless Chromium and prints rendered HTML to stdout.
Called as a subprocess from auditor.py to avoid event loop conflicts.
Usage: python3 fetch_page.py <url> <timeout_seconds>
Exit code: 0 = success (HTML on stdout), 1 = error (message on stderr)
"""
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

def main():
    if len(sys.argv) < 3:
        sys.stderr.write("Usage: fetch_page.py <url> <timeout>\n")
        sys.exit(1)

    url = sys.argv[1]
    timeout_ms = int(sys.argv[2]) * 1000

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800}
            )
            page = context.new_page()
            try:
                response = page.goto(url, timeout=timeout_ms, wait_until='networkidle')
                if response and response.status >= 400:
                    sys.stderr.write(f"HTTP {response.status}: Unable to fetch page\n")
                    browser.close()
                    sys.exit(1)
                html = page.content()
                browser.close()
                sys.stdout.write(html)
                sys.exit(0)
            except PlaywrightTimeout:
                sys.stderr.write(f"Timeout: page took longer than {sys.argv[2]}s to load\n")
                browser.close()
                sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Connection Error: {e}\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
