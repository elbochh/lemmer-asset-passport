"""Vehicle rust scan: detector adapters and result normalisation.

The scan result is a *suggestion* that a technician must review. Two detectors:

* ``simulated`` (default): deterministic demo regions derived from a hash of the
  image bytes. It does NOT analyse the picture and is always labelled as a
  simulation in the result.
* ``http``: forwards the image to a rust-segmentation service (for example the
  Streamlit/YOLO11 prototype wrapped in a small API) configured with
  ``RUST_DETECTOR_URL``. The service must answer with the contract described in
  ``parse_service_response``. Nothing is simulated in this mode.

Select with the ``RUST_DETECTOR`` environment variable (``simulated`` or ``http``).
"""

from __future__ import annotations

import hashlib
import io
import os
from datetime import datetime, timezone

SCHEMA_VERSION = "1"
MAX_FINDINGS = 12

# Indicative only: share of the picture covered by detected rust. Not a standard.
SEVERITY_LOW_MAX_PCT = 20.0
SEVERITY_MEDIUM_MAX_PCT = 35.0


class DetectorError(RuntimeError):
    """The detector is unavailable or returned an unusable answer."""


def severity(area_pct: float, has_findings: bool) -> str:
    if not has_findings:
        return "None"
    if area_pct < SEVERITY_LOW_MAX_PCT:
        return "Low"
    if area_pct < SEVERITY_MEDIUM_MAX_PCT:
        return "Medium"
    return "High"


def polygon_area(points: list[list[float]]) -> float:
    """Shoelace area of a normalised polygon (0..1 coordinates)."""
    total = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def _clip(value) -> float:
    return min(1.0, max(0.0, float(value)))


def _summarise(findings: list[dict], model: dict, simulated: bool) -> dict:
    # Sum of region areas, capped at 100 %. Overlaps are not merged here; the
    # real service should send non-overlapping masks or its own area figure.
    area_pct = min(100.0, sum(polygon_area(f["polygon"]) for f in findings) * 100)
    return {
        "schema_version": SCHEMA_VERSION,
        "simulated": simulated,
        "model": model,
        "findings": findings,
        "area_pct": round(area_pct, 2),
        "severity": severity(area_pct, bool(findings)),
        "review_status": "Pending",
        "reviewed_by": None,
        "reviewed_at": None,
        "review_notes": "",
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def simulate(raw: bytes) -> dict:
    """Deterministic demo regions. This is a SIMULATION, not computer vision."""
    digest = hashlib.sha256(raw).digest()
    count = digest[0] % 4  # 0..3 regions
    findings = []
    for i in range(count):
        b = digest[1 + i * 6 : 7 + i * 6]
        cx = 0.15 + (b[0] / 255) * 0.7
        cy = 0.15 + (b[1] / 255) * 0.7
        w = 0.08 + (b[2] / 255) * 0.14
        h = 0.06 + (b[3] / 255) * 0.12
        skew = (b[4] / 255 - 0.5) * 0.05
        polygon = [
            [_clip(cx - w), _clip(cy - h + skew)],
            [_clip(cx), _clip(cy - h * 1.2)],
            [_clip(cx + w), _clip(cy - h - skew)],
            [_clip(cx + w * 1.1), _clip(cy + h)],
            [_clip(cx), _clip(cy + h * 1.15)],
            [_clip(cx - w * 1.1), _clip(cy + h + skew)],
        ]
        findings.append(
            {
                "classification": "rust",
                "confidence": round(0.55 + (b[5] / 255) * 0.4, 2),
                "polygon": [[round(x, 4), round(y, 4)] for x, y in polygon],
            }
        )
    return _summarise(
        findings, {"name": "simulation", "version": "demo"}, simulated=True
    )


def parse_service_response(data: dict) -> dict:
    """Validate a detector-service answer.

    Expected JSON::

        {"model": {"name": "yolo11n-seg", "version": "..."},
         "findings": [{"classification": "rust", "confidence": 0.87,
                       "polygon": [[x, y], ...]}]}   # x, y in 0..1 of image size
    """
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise DetectorError("The detector returned an unexpected answer.")
    findings = []
    for item in data["findings"][:MAX_FINDINGS]:
        try:
            polygon = [[_clip(x), _clip(y)] for x, y in item["polygon"]]
            confidence = _clip(item["confidence"])
        except (KeyError, TypeError, ValueError):
            raise DetectorError("The detector returned an invalid region.")
        if len(polygon) < 3:
            raise DetectorError("The detector returned an invalid region.")
        findings.append(
            {
                "classification": str(item.get("classification", "rust"))[:40],
                "confidence": round(confidence, 2),
                "polygon": [[round(x, 4), round(y, 4)] for x, y in polygon],
            }
        )
    model = data.get("model") if isinstance(data.get("model"), dict) else {}
    return _summarise(
        findings,
        {
            "name": str(model.get("name", "unknown"))[:60],
            "version": str(model.get("version", ""))[:60],
        },
        simulated=False,
    )


def _service_url(url: str) -> str:
    """Accept a full URL or a bare internal "host:port" (as Render provides)."""
    if "://" not in url:
        url = "http://" + url
    if url.rstrip("/").count("/") < 3:  # no path given
        url = url.rstrip("/") + "/detect"
    return url


def _post_to_service(raw: bytes, content_type: str, url: str) -> dict:
    import httpx

    url = _service_url(url)

    try:
        response = httpx.post(
            url,
            files={"file": ("inspection", io.BytesIO(raw), content_type)},
            headers=(
                {"Authorization": "Bearer " + os.environ["RUST_DETECTOR_TOKEN"]}
                if os.environ.get("RUST_DETECTOR_TOKEN")
                else {}
            ),
            timeout=90,  # a sleeping free-tier service needs time to wake up
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # network, status or JSON errors
        raise DetectorError("The rust detector is unavailable. Try again later.") from exc


def detect(raw: bytes, content_type: str) -> dict:
    default = "http" if os.environ.get("RUST_DETECTOR_URL") else "simulated"
    mode = os.environ.get("RUST_DETECTOR", default).lower()
    if mode == "simulated":
        return simulate(raw)
    if mode == "http":
        url = os.environ.get("RUST_DETECTOR_URL", "")
        if not url:
            raise DetectorError("RUST_DETECTOR_URL is not configured.")
        return parse_service_response(_post_to_service(raw, content_type, url))
    raise DetectorError("Unknown RUST_DETECTOR mode.")
