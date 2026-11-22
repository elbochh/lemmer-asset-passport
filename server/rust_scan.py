"""Vehicle rust scan: detector adapters and result normalisation.

The scan result is a *suggestion* that a technician must review. Three detectors,
selected with the ``RUST_DETECTOR`` environment variable:

* ``local`` (default when ``server/models/rust_detector.onnx`` exists): a YOLO11
  rust detector trained on the Rusted_Cars dataset (see ``ml/rust``), run on the
  CPU with onnxruntime. No network call and no cloud cost.
* ``http``: forwards the image to a rust detection service configured with
  ``RUST_DETECTOR_URL`` (for example ``rust-service/``, a full URL or a bare
  ``host:port``). The service must answer with the contract described in
  ``parse_service_response``.
* ``simulated`` (fallback when no model file is present): deterministic demo
  regions derived from a hash of the image bytes. It does NOT analyse the
  picture and is always labelled as a simulation.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCHEMA_VERSION = "2"
MAX_FINDINGS = 12

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "rust_detector.onnx"
CARD_PATH = MODEL_DIR / "rust_detector.json"

# Indicative only: share of the picture inside detected regions. Not a standard.
SEVERITY_LOW_MAX_PCT = 20.0
SEVERITY_MEDIUM_MAX_PCT = 35.0
AREA_GRID = 200  # cells per side used to measure the union of regions


class DetectorError(RuntimeError):
    """The detector is unavailable or returned an unusable answer."""


def mode() -> str:
    configured = os.environ.get("RUST_DETECTOR", "").strip().lower()
    if configured:
        return configured
    if MODEL_PATH.exists():
        return "local"
    return "http" if os.environ.get("RUST_DETECTOR_URL") else "simulated"


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


def union_area_pct(polygons: list[list[list[float]]]) -> float:
    """Share of the image covered by at least one region, in percent.

    Overlapping regions are counted once (sampled on a fixed grid of cell
    centres), so two overlapping boxes cannot exceed the area they cover.
    """
    if not polygons:
        return 0.0
    centres = (np.arange(AREA_GRID) + 0.5) / AREA_GRID
    px, py = np.meshgrid(centres, centres)
    covered = np.zeros(px.shape, dtype=bool)
    for poly in polygons:
        inside = np.zeros(px.shape, dtype=bool)
        for i, (x1, y1) in enumerate(poly):
            x2, y2 = poly[(i + 1) % len(poly)]
            if y1 == y2:
                continue
            crosses = (y1 > py) != (y2 > py)
            inside ^= crosses & (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1)
        covered |= inside
    return float(covered.mean() * 100)


def _clip(value) -> float:
    return min(1.0, max(0.0, float(value)))


def _summarise(findings: list[dict], model: dict, simulated: bool) -> dict:
    area_pct = union_area_pct([f["polygon"] for f in findings])
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


# --------------------------------------------------------------------------
# Simulated detector (no model available)
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Local ONNX detector (trained with ml/rust/train.py)
# --------------------------------------------------------------------------


def load_card() -> dict:
    try:
        return json.loads(CARD_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    order = scores.argsort()[::-1]
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        overlap = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[overlap < iou]
    return keep


class LocalDetector:
    """YOLO11 detection model exported to ONNX (single class: rust)."""

    def __init__(self, path: Path = MODEL_PATH, card: dict | None = None):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = int(os.environ.get("RUST_DETECTOR_THREADS", "2"))
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(path), options, providers=["CPUExecutionProvider"]
        )
        model_input = self.session.get_inputs()[0]
        self.input_name = model_input.name
        self.size = int(model_input.shape[2])
        self.card = card if card is not None else load_card()
        self.threshold = float(self.card.get("threshold", 0.25))
        self.nms_iou = float(self.card.get("nms_iou", 0.5))
        self.version = self.card.get("version") or hashlib.sha256(
            path.read_bytes()
        ).hexdigest()[:12]

    def _prepare(self, raw: bytes):
        from PIL import Image, ImageOps

        try:
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        except Exception as exc:
            raise DetectorError("The image could not be read.") from exc
        width, height = image.size
        scale = min(self.size / width, self.size / height)
        new_w, new_h = max(1, round(width * scale)), max(1, round(height * scale))
        pad_x, pad_y = (self.size - new_w) // 2, (self.size - new_h) // 2
        canvas = Image.new("RGB", (self.size, self.size), (114, 114, 114))
        canvas.paste(image.resize((new_w, new_h), Image.BILINEAR), (pad_x, pad_y))
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        return tensor, (width, height, scale, pad_x, pad_y)

    def predict(self, raw: bytes, threshold: float | None = None) -> list[dict]:
        """Rust boxes as fractions of the original image, highest confidence first."""
        tensor, (width, height, scale, pad_x, pad_y) = self._prepare(raw)
        output = self.session.run(None, {self.input_name: tensor})[0][0]  # (5, N)
        scores = output[4]
        keep = scores >= (self.threshold if threshold is None else threshold)
        if not keep.any():
            return []
        cx, cy, w, h = output[:4, keep]
        scores = scores[keep]
        boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_x) / scale / width
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_y) / scale / height
        boxes = np.clip(boxes, 0.0, 1.0)
        results = []
        for i in _nms(boxes, scores, self.nms_iou):
            x1, y1, x2, y2 = (float(v) for v in boxes[i])
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                continue
            results.append({"box": [x1, y1, x2, y2], "confidence": float(scores[i])})
        return results

    def detect(self, raw: bytes) -> dict:
        findings = []
        for item in self.predict(raw)[:MAX_FINDINGS]:
            x1, y1, x2, y2 = (round(v, 4) for v in item["box"])
            findings.append(
                {
                    "classification": "rust",
                    "confidence": round(item["confidence"], 2),
                    "box": [x1, y1, x2, y2],
                    "polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                }
            )
        model = {
            "name": self.card.get("name", "Local rust detector"),
            "version": self.version,
            "threshold": round(self.threshold, 3),
        }
        return _summarise(findings, model, simulated=False)


_local: LocalDetector | None = None
_local_lock = threading.Lock()


def local_detector() -> LocalDetector:
    global _local
    with _local_lock:
        if _local is None:
            if not MODEL_PATH.exists():
                raise DetectorError(
                    "The rust model file is missing. Train it with ml/rust/train.py."
                )
            try:
                _local = LocalDetector()
            except DetectorError:
                raise
            except Exception as exc:  # missing onnxruntime, corrupt file
                raise DetectorError("The rust model could not be loaded.") from exc
        return _local


# --------------------------------------------------------------------------
# HTTP detector service
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def detect(raw: bytes, content_type: str) -> dict:
    current = mode()
    if current == "local":
        return local_detector().detect(raw)
    if current == "simulated":
        return simulate(raw)
    if current == "http":
        url = os.environ.get("RUST_DETECTOR_URL", "")
        if not url:
            raise DetectorError("RUST_DETECTOR_URL is not configured.")
        return parse_service_response(_post_to_service(raw, content_type, url))
    raise DetectorError("Unknown RUST_DETECTOR mode.")


def model_info() -> dict:
    """What the inspection screen tells technicians about the active detector."""
    current = mode()
    if current == "local":
        card = load_card()
        return {
            "mode": "local",
            "available": MODEL_PATH.exists(),
            "simulated": False,
            **{k: card[k] for k in ["name", "version", "threshold", "metrics",
                                     "dataset", "limitations", "evaluated_at"]
               if k in card},
        }
    if current == "http":
        return {
            "mode": "http",
            "available": bool(os.environ.get("RUST_DETECTOR_URL")),
            "simulated": False,
            "name": "External rust detection service",
        }
    return {
        "mode": current,
        "available": current == "simulated",
        "simulated": True,
        "name": "Simulation (no model installed)",
        "limitations": [
            "Regions are generated from the image bytes. No picture analysis is performed."
        ],
    }
