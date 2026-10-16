"""Capture public Lemmer catalogue evidence; does not change the running app.

Run with the project's Python environment. Raw responses are private local
research artifacts; generated Markdown remains explicitly unreviewed evidence.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = "https://lemmer.com/en/wp-json/wc/store/v1/products"
OUT = ROOT / "knowledge/research/rustproofing"
CACHE = ROOT / ".local/research"


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "div", "li", "br", "tr", "h2", "h3", "h4"):
            self.items.append("\n")

    def handle_endtag(self, tag):
        if tag in ("p", "div", "li", "tr", "h2", "h3", "h4"):
            self.items.append("\n")

    def handle_data(self, data):
        self.items.append(data)


def plain(html):
    parser = Text()
    parser.feed(html or "")
    return "\n\n".join(
        x.strip() for x in "".join(parser.items).splitlines() if x.strip()
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    records = []
    captured = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=55, follow_redirects=True) as client:
        page = 1
        while True:
            response = client.get(
                API, params={"category": 126, "per_page": 100, "page": page}
            )
            response.raise_for_status()
            batch = response.json()
            records.extend(batch)
            if page >= int(response.headers["x-wp-totalpages"]):
                assert len(records) == int(response.headers["x-wp-total"])
                break
            page += 1
    assert len({x["id"] for x in records}) == len(records)
    (CACHE / "rustproofing-products.json").write_text(json.dumps(records, indent=2))
    index = []
    for item in sorted(records, key=lambda x: x["sku"].upper()):
        sku = item["sku"].upper()
        filename = re.sub(r"[^a-z0-9-]", "-", sku.lower()) or str(item["id"])
        filename += "-" + str(item["id"]) + ".md"
        digest = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
        body = plain(item["description"])
        short = plain(item["short_description"])
        links = sorted(
            set(
                unescape(x)
                for x in re.findall(
                    r'https?://[^\s"<>]+\.pdf(?:\?[^\s"<>]*)?',
                    item["description"] + item["short_description"],
                )
            )
        )
        md = "\n".join(
            [
                "# " + unescape(item["name"]),
                "",
                "Source: " + item["permalink"],
                "Captured: " + captured,
                "Manufacturer: Lemmer",
                "Sales SKU: " + sku,
                "Website ID: " + str(item["id"]),
                "Source SHA256: " + digest,
                "Review status: captured public catalogue evidence; technical review pending",
                "",
                "## Applicability and limitations",
                "",
                "This is one sales item or variant, not a complete component bill of materials. "
                "The sales SKU is not evidence that this item fits every similarly named model. "
                "Website descriptions may contain translation or unit errors. Verify operating "
                "limits and replacement compatibility against the exact manual and equipment. "
                "No stock, price, lifetime or repair diagnosis is inferred. This file is not "
                "loaded by the current recommendation engine.",
                "",
                "## Catalogue description",
                "",
                body or short or "No description provided.",
                "",
                "## Linked PDF sources in catalogue description",
                "",
                "\n".join("- " + x for x in links)
                or "None in the public API description. Product-page document buttons require separate review.",
                "",
            ]
        )
        (OUT / filename).write_text(md)
        index.append(
            {
                "id": item["id"],
                "sku": sku,
                "name": unescape(item["name"]),
                "url": item["permalink"],
                "file": filename,
                "categories": item["categories"],
                "images": [{"url": x["src"], "alt": x["alt"]} for x in item["images"]],
                "pdf_links": links,
                "source_sha256": digest,
            }
        )
    manifest = {
        "captured_at": captured,
        "source": API + "?category=126",
        "count": len(index),
        "review_status": "unreviewed",
        "products": index,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )
    lines = [
        "# Rustproofing catalogue research",
        "",
        f"{len(index)} unique public sales entries captured at {captured}.",
        "",
        "Scope: all entries returned by the official rustproofing category (126), "
        "including accessories and kits. This is catalogue coverage, not a claim "
        "of complete internal parts or troubleshooting coverage. Original API "
        "responses are retained under `.local/research/`.",
        "",
        "These files are staged research and are not active agent knowledge. "
        "Review product identities, manuals and compatibility before enabling them.",
        "",
        "| SKU | Item |",
        "| --- | --- |",
    ]
    lines += [
        f"| {x['sku']} | [{x['name'].replace('|', '/')} ]({x['file']}) |" for x in index
    ]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    print(
        f"Captured {len(index)} unique products; wrote {len(index)} Markdown evidence files."
    )


if __name__ == "__main__":
    main()
