"""Download linked official product PDFs and retain their provenance for review."""

from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
import json, hashlib
import httpx
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "knowledge/research/manuals"
RAW = ROOT / ".local/research/manuals"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            self.current = [a.get("href", ""), ""]

    def handle_data(self, s):
        if self.current:
            self.current[1] += s

    def handle_endtag(self, t):
        if t == "a" and self.current:
            self.links.append(self.current)
            self.current = None


def collect(p):
    try:
        cache = RAW / (p["sku"] + ".html")
        if cache.exists():
            html = cache.read_text()
            base = p["url"]
        else:
            r = httpx.get(p["url"], follow_redirects=True, timeout=15)
            r.raise_for_status()
            html = r.text
            base = str(r.url)
            cache.write_text(html)
        parser = Links()
        parser.feed(html)
        links = [
            {"url": urljoin(base, u), "label": label.strip()}
            for u, label in parser.links
            if ".pdf" in u.lower()
            and urlparse(urljoin(base, u)).hostname in ["lemmer.com", "www.lemmer.com"]
        ]
        print("Reviewed links:", p["sku"], len(links), flush=True)
        return {"sku": p["sku"], "product_url": p["url"], "documents": links}
    except Exception as e:
        return {"sku": p["sku"], "error": type(e).__name__, "documents": []}


def download(url):
    name = hashlib.sha256(url.encode()).hexdigest()[:16]
    try:
        path = RAW / (name + ".pdf")
        if not path.exists():
            r = httpx.get(url, follow_redirects=True, timeout=45)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError("not PDF")
            path.write_bytes(r.content)
        pdf = PdfReader(path)
        pages = [p.extract_text() or "" for p in pdf.pages]
        (OUT / (name + ".md")).write_text(
            "# Official document text extraction\nSource: "
            + url
            + "\n\nReview status: extracted, not yet verified for model applicability or table alignment. Not active repair evidence.\n\n"
            + "\n\n".join(f"## Page {i+1}\n\n{text}" for i, text in enumerate(pages))
        )
        return {
            "url": url,
            "file": name + ".md",
            "pages": len(pages),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    except Exception as e:
        return {"url": url, "error": type(e).__name__}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    products = json.loads(
        (ROOT / "knowledge/research/rustproofing/manifest.json").read_text()
    )["products"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        entries = list(pool.map(collect, products))
    urls = sorted({d["url"] for x in entries for d in x["documents"]})
    with ThreadPoolExecutor(max_workers=4) as pool:
        documents = list(pool.map(download, urls))
    (OUT / "manifest.json").write_text(
        json.dumps({"products": entries, "documents": documents}, indent=2)
    )
    print(
        "Product pages",
        len(entries),
        "unique PDFs",
        len(urls),
        "downloaded",
        sum("file" in x for x in documents),
        "errors",
        sum("error" in x for x in entries + documents),
    )


if __name__ == "__main__":
    main()
