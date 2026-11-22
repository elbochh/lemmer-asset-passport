"""Evaluate the exported rust detector exactly as the app runs it, and write its model card.

The confidence threshold is chosen on the validation split only (best F1 at IoU 0.5).
The test split is then scored once with that threshold. Both results are written to
``server/models/rust_detector.json``, which the inspection screen displays.

    .venv/bin/python ml/rust/evaluate.py --data .local/rust-training-data/rusted_cars \
        --name "YOLO11s rust detector" --architecture yolo11s --epochs 150
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.rust_scan import CARD_PATH, MODEL_PATH, LocalDetector  # noqa: E402

IOU = 0.5  # strict: standard object-detection matching
LOCATED = 0.5  # loose: half of the smaller box lies inside the other


def load_split(folder: Path):
    images = sorted((folder / "images").glob("*"))
    truth = []
    for image in images:
        label = folder / "labels" / (image.stem + ".txt")
        boxes = []
        for line in label.read_text().split("\n") if label.exists() else []:
            parts = line.split()
            if len(parts) == 5:
                cx, cy, w, h = map(float, parts[1:])
                boxes.append([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
        truth.append(np.array(boxes).reshape(-1, 4))
    return images, truth


def iou(box, others):
    xx1 = np.maximum(box[0], others[:, 0])
    yy1 = np.maximum(box[1], others[:, 1])
    xx2 = np.minimum(box[2], others[:, 2])
    yy2 = np.minimum(box[3], others[:, 3])
    inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
    area = (box[2] - box[0]) * (box[3] - box[1])
    areas = (others[:, 2] - others[:, 0]) * (others[:, 3] - others[:, 1])
    return inter / (area + areas - inter + 1e-9)


def located(predictions, truth, threshold):
    """Loose agreement that tolerates different box granularity.

    A detection and a labelled region agree when at least half of the smaller
    box lies inside the other. One large detection can therefore locate several
    small labelled spots (and vice versa), unlike strict one-to-one IoU matching.
    """
    found = total_gt = good = total_pred = 0
    for preds, gt in zip(predictions, truth):
        boxes = np.array([p["box"] for p in preds if p["confidence"] >= threshold]).reshape(-1, 4)
        if len(boxes) and len(gt):
            ix1 = np.maximum(boxes[:, None, 0], gt[None, :, 0])
            iy1 = np.maximum(boxes[:, None, 1], gt[None, :, 1])
            ix2 = np.minimum(boxes[:, None, 2], gt[None, :, 2])
            iy2 = np.minimum(boxes[:, None, 3], gt[None, :, 3])
            inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
            area_p = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
            area_g = (gt[:, 2] - gt[:, 0]) * (gt[:, 3] - gt[:, 1])
            agree = inter / (np.minimum(area_p[:, None], area_g[None, :]) + 1e-9) >= LOCATED
            found += int(agree.any(axis=0).sum())
            good += int(agree.any(axis=1).sum())
        total_gt += len(gt)
        total_pred += len(boxes)
    return {
        "located_precision": round(good / total_pred, 3) if total_pred else 0.0,
        "located_recall": round(found / total_gt, 3) if total_gt else 0.0,
    }


def match(predictions, truth, iou_min=IOU):
    """(score, is_true_positive) for every prediction, greedy by confidence per image."""
    scored = []
    for preds, gt in zip(predictions, truth):
        used = np.zeros(len(gt), dtype=bool)
        for p in sorted(preds, key=lambda p: -p["confidence"]):
            hit = False
            if len(gt):
                overlaps = iou(np.array(p["box"]), gt)
                overlaps[used] = 0
                best = int(overlaps.argmax())
                if overlaps[best] >= iou_min:
                    used[best] = hit = True
            scored.append((p["confidence"], hit))
    scored.sort(key=lambda s: -s[0])
    return scored


def average_precision(scored, positives):
    if not scored or not positives:
        return 0.0
    hits = np.array([h for _, h in scored], dtype=float)
    tp = np.cumsum(hits)
    recall = tp / positives
    precision = tp / np.arange(1, len(hits) + 1)
    recall = np.concatenate([[0.0], recall, [1.0]])
    precision = np.concatenate([[1.0], precision, [0.0]])
    precision = np.maximum.accumulate(precision[::-1])[::-1]
    return float(np.sum((recall[1:] - recall[:-1]) * precision[1:]))


def at_threshold(scored, positives, threshold):
    tp = sum(1 for s, h in scored if s >= threshold and h)
    fp = sum(1 for s, h in scored if s >= threshold and not h)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positives if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3), "true_positives": tp, "false_positives": fp}


def image_level(predictions, threshold):
    """Share of photos (all of which contain labelled rust) with at least one detection."""
    flagged = sum(1 for preds in predictions if any(p["confidence"] >= threshold for p in preds))
    return round(flagged / len(predictions), 3) if predictions else 0.0


def evaluate(detector, folder):
    images, truth = load_split(folder)
    predictions = [detector.predict(p.read_bytes(), threshold=0.001) for p in images]
    positives = int(sum(len(t) for t in truth))
    return images, predictions, truth, positives


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--name", default="YOLO11 rust detector")
    p.add_argument("--architecture", default="yolo11")
    p.add_argument("--epochs", type=int, default=None)
    p.add_argument("--device", default="local Apple GPU (MPS)")
    p.add_argument("--print-only", action="store_true")
    args = p.parse_args()
    data = Path(args.data)
    detector = LocalDetector(MODEL_PATH, card={})

    _, val_pred, val_truth, val_pos = evaluate(detector, data / "valid")
    val_scored = match(val_pred, val_truth)
    candidates = np.round(np.arange(0.05, 0.9, 0.01), 2)
    threshold = float(max(candidates, key=lambda t: (at_threshold(val_scored, val_pos, t)["f1"], -t)))
    test_images, test_pred, test_truth, test_pos = evaluate(detector, data / "test")

    metrics = {}
    for split, preds, truth, positives in [
        ("validation", val_pred, val_truth, val_pos),
        ("test", test_pred, test_truth, test_pos),
    ]:
        scored = match(preds, truth)
        metrics[split] = {
            "images": len(preds),
            "rust_regions": positives,
            "ap50": round(average_precision(scored, positives), 3),
            **at_threshold(scored, positives, threshold),
            **located(preds, truth, threshold),
            "photos_flagged": image_level(preds, threshold),
        }
        print(split, metrics[split])
    print("threshold (best validation F1):", threshold)
    per_image = {
        img.name: max([p["confidence"] for p in preds], default=0)
        for img, preds in zip(test_images, test_pred)
    }
    print("test photos by top confidence:")
    for name, score in sorted(per_image.items(), key=lambda kv: -kv[1]):
        print(f"  {score:.2f}  {name}")
    if args.print_only:
        return

    train_images = len(list((data / "train" / "images").glob("*")))
    card = {
        "name": args.name,
        "architecture": args.architecture,
        "version": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:12],
        "threshold": threshold,
        "nms_iou": 0.5,
        "evaluated_at": date.today().isoformat(),
        "training": {"images": train_images, "epochs": args.epochs, "device": args.device},
        "metrics": metrics,
        "metric_notes": (
            "precision/recall/ap50: strict box matching at IoU 0.5. located_*: a detection "
            "and a labelled region agree when half of the smaller box lies inside the other, "
            "which tolerates one large box drawn where the labeller drew several small ones. Threshold chosen on "
            "validation only; test scored once."
        ),
        "dataset": {
            "name": "Rusted_Cars v3",
            "author": "szymon-pgasw (Roboflow Universe)",
            "license": "CC BY 4.0",
            "url": "https://universe.roboflow.com/szymon-pgasw/rusted_cars/dataset/3",
        },
        "limitations": [
            "Trained on public photos of car bodies (wheel arches, sills, panels), not Lemmer vehicles or undercarriages.",
            "Labels are boxes, so the flagged area includes clean paint around the rust and overstates rust extent.",
            "Severity is a share of the photo inside detected boxes. It is indicative only and is not a Lemmer standard.",
            "Every photo in the dataset contains rust, so false alarms on clean vehicles have not been measured.",
        ],
    }
    CARD_PATH.write_text(json.dumps(card, indent=2) + "\n")
    print("Wrote", CARD_PATH)


if __name__ == "__main__":
    main()
