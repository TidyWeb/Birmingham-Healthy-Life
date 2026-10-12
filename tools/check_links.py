"""Check every link and image on the built site.

    python tools/check_links.py            internal links, anchors and images only
    python tools/check_links.py --web      also asks every external site whether its page is there

Internal links must point at a file that exists, and a #anchor must exist on that page.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin

SITE = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "tools", "content"}


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("href"):
            self.links.append(("link", attrs["href"]))
        if tag in ("img", "script") and attrs.get("src"):
            self.links.append(("src", attrs["src"]))
        if tag == "link" and attrs.get("href") and attrs.get("rel") != "preconnect":
            self.links.append(("css", attrs["href"]))
        for key in ("data-embed",):
            if attrs.get(key):
                self.links.append(("embed", attrs[key]))


def parse(path: Path) -> Collector:
    collector = Collector()
    collector.feed(path.read_text(encoding="utf-8", errors="replace"))
    return collector


def site_pages() -> list[Path]:
    return [p for p in SITE.rglob("*.html") if not SKIP_DIRS & set(p.relative_to(SITE).parts)]


def resolve(page: Path, href: str) -> tuple[Path, str]:
    target, anchor = urldefrag(href)
    if not target:
        return page, anchor
    path = (page.parent / unquote(target.split("?")[0])).resolve()   # ignore ?v= version tags
    if path.is_dir():
        path = path / "index.html"
    return path, anchor


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (link check)"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return str(response.status)
    except urllib.error.HTTPError as error:
        return str(error.code)
    except Exception as error:  # timeouts, DNS failures and the like
        return type(error).__name__


def main() -> None:
    check_web = "--web" in sys.argv
    pages = site_pages()
    parsed = {p: parse(p) for p in pages}
    problems, external = [], {}
    checked = 0
    for page, info in parsed.items():
        for kind, href in info.links:
            if href.startswith(("mailto:", "javascript:", "data:")):
                continue
            if re.match(r"^https?://", href):
                external.setdefault(urldefrag(href)[0], set()).add(page.relative_to(SITE).as_posix())
                continue
            checked += 1
            path, anchor = resolve(page, href)
            if not path.exists():
                problems.append(f"MISSING  {page.relative_to(SITE)} -> {href}")
                continue
            if anchor and path.suffix == ".html":
                ids = parsed[path].ids if path in parsed else parse(path).ids
                if anchor not in ids:
                    problems.append(f"NO ANCHOR {page.relative_to(SITE)} -> {href}")
    print(f"Internal: {checked} links checked on {len(pages)} pages, {len(problems)} problems.")
    for line in problems:
        print("  " + line)
    if check_web:
        urls = sorted(external)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = dict(zip(urls, pool.map(fetch, urls)))
        bad = {u: r for u, r in results.items() if not r.startswith(("2", "3"))}
        print(f"External: {len(urls)} addresses checked, {len(bad)} not answering with a page.")
        for url, result in bad.items():
            print(f"  {result}  {url}  (on {', '.join(sorted(external[url]))[:120]})")


if __name__ == "__main__":
    main()
