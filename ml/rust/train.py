"""Train the vehicle rust detector and export it for the app (local, no cloud).

The app never needs PyTorch or Ultralytics: this script exports an ONNX file
that ``server/rust_scan.py`` runs on CPU with onnxruntime.

Setup (separate from the app's .venv, training only):

    python3.13 -m venv .local/rust-train-venv
    .local/rust-train-venv/bin/pip install ultralytics onnx onnxruntime onnxslim

Usage:

    .local/rust-train-venv/bin/python ml/rust/train.py \
        --data .local/rust-training-data/rusted_cars --model yolo11s

Then evaluate the exported file with the app's own inference code:

    .venv/bin/python ml/rust/evaluate.py --data .local/rust-training-data/rusted_cars

Dataset: "Rusted_Cars v3" by szymon-pgasw, Roboflow Universe, CC BY 4.0
https://universe.roboflow.com/szymon-pgasw/rusted_cars/dataset/3
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data", required=True, help="Folder with train/valid/test")
    p.add_argument("--model", default="yolo11s", help="yolo11n or yolo11s")
    p.add_argument("--epochs", type=int, default=150)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--runs", default=str(ROOT / ".local" / "rust-runs"))
    p.add_argument("--export-to", default=str(ROOT / "server" / "models"))
    p.add_argument("--no-export", action="store_true")
    args = p.parse_args()

    import torch
    from ultralytics import YOLO

    data = Path(args.data).resolve()
    runs = Path(args.runs).resolve()
    runs.mkdir(parents=True, exist_ok=True)
    # Absolute paths, so training does not depend on the current directory.
    yaml = runs / f"{data.name}.yaml"
    yaml.write_text(
        f"path: {data}\ntrain: train/images\nval: valid/images\n"
        "test: test/images\nnc: 1\nnames: ['rust']\n"
    )
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    name = f"{args.model}-{args.imgsz}"
    YOLO(args.model + ".pt").train(
        data=str(yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=16,
        patience=40,
        device=device,
        project=str(runs),
        name=name,
        exist_ok=True,
        seed=0,
        deterministic=True,
        plots=False,
        verbose=False,
    )
    best = runs / name / "weights" / "best.pt"
    model = YOLO(str(best))
    metrics = {}
    for split in ("val", "test"):
        r = model.val(data=str(yaml), split=split, imgsz=args.imgsz, device=device,
                      plots=False, verbose=False)
        metrics[split] = {
            "precision": round(float(r.box.mp), 3),
            "recall": round(float(r.box.mr), 3),
            "map50": round(float(r.box.map50), 3),
            "map50_95": round(float(r.box.map), 3),
        }
        print(split, metrics[split])
    (runs / name / "ultralytics_metrics.json").write_text(json.dumps(metrics, indent=2))
    if args.no_export:
        return
    onnx = Path(model.export(format="onnx", imgsz=args.imgsz, opset=17,
                             simplify=True, dynamic=False, nms=False))
    out = Path(args.export_to)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(onnx, out / "rust_detector.onnx")
    print("Exported", out / "rust_detector.onnx")
    print("Next: .venv/bin/python ml/rust/evaluate.py --data", data)


if __name__ == "__main__":
    main()
