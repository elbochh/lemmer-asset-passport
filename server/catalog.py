"""Source-backed rustproofing sales catalogue, separate from physical assets."""

import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads(
    (ROOT / "knowledge/research/rustproofing/manifest.json").read_text()
)["products"]
BY_SKU = {x["sku"]: x for x in CATALOG}
RP_PARTS = {
    "L015-288": "Packing spring",
    "L015-289": "Packing washer",
    "L015-291": "Packing",
    "L015-292": "Packing nut",
    "L015-258": "Needle",
    "L015-259": "Needle spring",
    "L015-295": "Seal kit",
    "L015-296": "Overhaul kit",
}
RP_SKUS = {"L015-201", "L015-203", "L015-210"}


def image_for(sku):
    p = ROOT / "public/images/catalog" / f"{sku}.webp"
    return f"/images/catalog/{sku}.webp" if p.exists() else "/images/equipment.svg"


def catalog_out():
    return [
        {
            **{k: x[k] for k in ["sku", "name", "url"]},
            "image": image_for(x["sku"]),
            "kind": (
                "Equipment"
                if re.search(r"\b(kit|pump|gun|tank)\b", x["name"], re.I)
                else "Accessories & parts"
            ),
        }
        for x in CATALOG
    ]


def product_docs(model):
    matches = (
        [BY_SKU[model]]
        if model in BY_SKU
        else ([BY_SKU["L015-201"]] if model == "RP-460HD" else [])
    )
    docs = []
    for p in matches:
        md = (ROOT / "knowledge/research/rustproofing" / p["file"]).read_text()
        # Public descriptions establish catalogue facts only, not a repair diagnosis.
        docs.append(
            {
                "id": "CAT-" + p["sku"],
                "model": model,
                "title": p["name"],
                "kind": "catalogue",
                "content": md,
                "url": p["url"],
                "revision": "Captured September 2026",
                "hash": p["source_sha256"],
            }
        )
    if model in RP_SKUS or model == "RP-460HD":
        md = (ROOT / "knowledge/products/lemmer/rp-460hd/parts.md").read_text()
        docs.append(
            {
                "id": "DOC-RP460-parts",
                "model": model,
                "title": "RP-460HD verified selected parts",
                "kind": "manual",
                "content": md,
                "url": "https://lemmer.com/wp-content/uploads/2026/01/Parts-Book-Complete-43-1.pdf",
                "revision": "September 2018",
                "hash": __import__("hashlib").sha256(md.encode()).hexdigest(),
            }
        )
    if model in {"L033-207", "L033-208"}:
        md = (ROOT / "knowledge/operations/lemmer/rp-1202.md").read_text()
        docs.append(
            {
                "id": "DOC-RP1202-operations",
                "model": model,
                "title": "RP-1202 operator manual and component identification",
                "kind": "manual",
                "content": md,
                "url": "https://lemmer.com/wp-content/uploads/2026/01/Manual-RP-1202-L033-207814-L500-006.pdf",
                "revision": "L500-006",
                "hash": __import__("hashlib").sha256(md.encode()).hexdigest(),
            }
        )
    product = BY_SKU.get(model)
    if product:
        name = product["name"].upper()
        families = []
        if "RP-1115" in name:
            families.append("rp-1115")
        if "RP-1202" in name:
            families.append("rp-1202")
        if "F-1001" in name:
            families.append("f-1001")
        if "RP-LX17" in name:
            families.append("lx-17")
        # Only equipment/kit descriptions, not accessories merely mentioning a pump.
        if not any(x in name for x in ["KIT", "PUMP ONLY", "GUN,"]):
            families = []
        for family in families:
            p = ROOT / "knowledge/components/lemmer" / f"{family}.md"
            md = p.read_text()
            source = re.search(r"^Source: (.+)$", md, re.M).group(1)
            revision = re.search(r"^Revision: (.+)$", md, re.M).group(1)
            docs.append(
                {
                    "id": "PARTS-" + family,
                    "model": model,
                    "title": family.upper() + " component reference",
                    "kind": "manual",
                    "content": md,
                    "url": source,
                    "revision": revision,
                    "hash": __import__("hashlib").sha256(md.encode()).hexdigest(),
                }
            )
    return docs
