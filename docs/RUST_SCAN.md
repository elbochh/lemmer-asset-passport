# Vehicle rust scan (technician-reviewed)

Where: vehicle bay visit (`/vehicles` → *Open bay visit*) → **Rust detection** panel.

Flow: upload a "before" image → **Run rust scan** → regions are drawn over the image →
a technician marks the result **Confirmed / Rejected / Needs Review** (name and time are
stored). Only *Confirmed* results are added to the asset passport timeline (visible to
the owner). Unreviewed or rejected output stays on the visit.

## API
- `POST /api/visits/{id}/rust-scan` (technician) – scans the visit's "before" image.
- `PATCH /api/visits/{id}/rust-scan/review` – body `{status, notes, version}`.
The result is stored in `vehicle_visits.report["rust_scan"]` (no schema migration).

## Detector modes (`RUST_DETECTOR`)
- `simulated` (default): deterministic demo regions from a hash of the image. **Not computer
  vision**; the UI and timeline say so.
- `http`: set `RUST_DETECTOR_URL` (and optionally `RUST_DETECTOR_TOKEN`). The service receives
  the image as multipart field `file` and must return:

```json
{"model": {"name": "yolo11n-seg", "version": "best.pt"},
 "findings": [{"classification": "rust", "confidence": 0.87,
               "polygon": [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]]}]}
```
Polygon points are fractions (0–1) of image width/height. The YOLO11 segmentation
prototype (Streamlit project) can be wrapped to answer this contract.

Severity (Low/Medium/High at 20 % / 35 % of image area) is indicative only, not a Lemmer standard.
