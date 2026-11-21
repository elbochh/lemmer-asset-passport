"""Rust detection service for the Asset Passport (ONNX runtime, no PyTorch needed).

POST /detect  (multipart field "file", optional header "Authorization: Bearer <RUST_DETECTOR_TOKEN>")
Returns {"model": {...}, "findings": [{"classification","confidence","polygon"}]}
with polygon points as fractions (0-1) of the image size.
The model is a YOLO11n bounding-box detector trained on Rusted_Cars v3 (CC BY 4.0).
"""

import io
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from PIL import Image

MODEL_PATH = Path(__file__).with_name("rust_model.onnx")
SIZE = 640
CONF = float(os.environ.get("RUST_CONF", "0.25"))
IOU = 0.45
MODEL_INFO = {"name": "yolo11n-detect", "version": "rusted_cars_v3"}

session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name
app = FastAPI()


def letterbox(image: Image.Image):
    w, h = image.size
    r = min(SIZE / w, SIZE / h)
    nw, nh = round(w * r), round(h * r)
    resized = image.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (SIZE, SIZE), (114, 114, 114))
    px, py = (SIZE - nw) // 2, (SIZE - nh) // 2
    canvas.paste(resized, (px, py))
    return canvas, r, px, py


def nms(boxes: np.ndarray, scores: np.ndarray) -> list[int]:
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_r = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        iou = inter / (area_i + area_r - inter + 1e-9)
        order = rest[iou <= IOU]
    return keep


def detect_image(image: Image.Image) -> list[dict]:
    w, h = image.size
    canvas, r, px, py = letterbox(image)
    x = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    out = session.run(None, {input_name: x})[0][0]  # (5, 8400): cx, cy, w, h, score
    scores = out[4]
    mask = scores >= CONF
    if not mask.any():
        return []
    cx, cy, bw, bh = out[0][mask], out[1][mask], out[2][mask], out[3][mask]
    s = scores[mask]
    boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
    findings = []
    for i in nms(boxes, s):
        x1, y1, x2, y2 = boxes[i]
        x1, x2 = (x1 - px) / r, (x2 - px) / r
        y1, y2 = (y1 - py) / r, (y2 - py) / r
        x1, x2 = np.clip([x1, x2], 0, w) / w
        y1, y2 = np.clip([y1, y2], 0, h) / h
        if x2 - x1 < 0.005 or y2 - y1 < 0.005:
            continue
        findings.append(
            {
                "classification": "rust",
                "confidence": round(float(s[i]), 3),
                "polygon": [
                    [float(x1), float(y1)],
                    [float(x2), float(y1)],
                    [float(x2), float(y2)],
                    [float(x1), float(y2)],
                ],
            }
        )
    return findings


@app.get("/")
def health():
    return {"status": "ok", "model": MODEL_INFO}


@app.post("/detect")
async def detect(file: UploadFile = File(...), authorization: str = Header(default="")):
    token = os.environ.get("RUST_DETECTOR_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "Unauthorized")
    raw = await file.read(5_000_000)
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(422, "Not an image")
    return {"model": MODEL_INFO, "findings": detect_image(image)}
