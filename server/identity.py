"""Display model and catalogue product number are separate from physical IDs."""

import re
from .catalog import BY_SKU


def model_name(sku, fallback=""):
    p = BY_SKU.get(sku)
    if not p:
        return fallback or "Unknown"
    match = re.search(r"\b(?:RP-[A-Z]*\d+[A-Z]*|F-\d+|LX-?\d+)\b", p["name"], re.I)
    return match.group(0).upper() if match else p["name"]


def reference_key(a):
    return getattr(a, "product_number", "") or a.model
