# Vehicle rust inspection (technician-reviewed)

## Where and who

- **Vehicle rust inspection** tab (`/rust-scan`) for technicians and super-users: a guided
  page to choose a vehicle, add a photo, scan, and review. Other staff can open it read-only.
- **Vehicle bay records** (`/vehicles`, the "Vehicle bay" tab for reception): the full bay
  visit with stages, before/after photos, the same scan panel, *Draft from rust scan* and the
  AI wording suggestion. "Continue the visit record" on the rust page opens the same visit here.
- Customers never see either page. They see a scan on their vehicle passport, and on the
  QR work report, only after a technician confirms it.

## Flow

1. Choose a vehicle. This opens its current bay visit, or starts one.
2. Add a photo (JPG/PNG up to 2.5 MB) or one of three held-out sample photos.
3. **Run rust scan.** Regions are drawn over the photo with their confidence.
4. The technician marks the result **Confirm & record**, **Rejected** or **Needs Review**.
   Name, time and optional notes are stored.

Rules (enforced by the API and covered by `tests/test_rust_scan.py`):

- Only a confirmed scan becomes a passport timeline event. Pending, rejected and
  needs-review scans, and AI-suggested wording, are removed from everything a customer
  can request, including the `visits` list on the customer passport.
- A confirmed scan is final for that photo: it cannot be re-reviewed or re-scanned, so the
  passport and the visit cannot disagree, and the event is written once.
- Uploading a new photo discards the visit's current scan and any AI wording drawn from it,
  so old regions are never shown over a different picture. To inspect another area, upload
  its photo and scan again. Each confirmed photo keeps its own timeline event.
- The visit completion record does not repeat confirmed scans or AI wording.
- The public work report (`/work/{share}/{code}`, no sign-in) shows recorded and confirmed
  work only. Service reports appear with their latest amendments, and the technician's
  internal `notes` field is never included.

## Detector (`RUST_DETECTOR`)

| Mode | When | What it does |
|---|---|---|
| `local` | default when `server/models/rust_detector.onnx` exists; set in `render.yaml` | Runs the model inside the web service on CPU with onnxruntime. No network call, key or per-scan cost. |
| `http` | `RUST_DETECTOR_URL` set (optional `RUST_DETECTOR_TOKEN`) | Sends the photo to `rust-service/` (or any service with the contract below). A full URL or a bare `host:port` is accepted. |
| `simulated` | no model and no URL | Hash-based demo regions. **Not computer vision**; the UI shows a warning. |

`RUST_DETECTOR_THREADS` (default 2) limits CPU threads on small hosting plans.

HTTP contract (polygon points are fractions 0–1 of image width/height):

```json
{"model": {"name": "yolo11n-detect", "version": "rusted_cars_v3"},
 "findings": [{"classification": "rust", "confidence": 0.87,
               "polygon": [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]]}]}
```

"Photo area flagged" is the union of regions (overlaps counted once). Severity
(Low/Medium/High at 20 % / 35 % of the photo) is indicative only and is not a Lemmer standard.

## API

- `GET /api/rust-scan/model` (staff): active mode, model card, metrics, limitations.
- `POST /api/visits/{id}/rust-scan` (technician/super-user): scans the visit's current photo.
- `PATCH /api/visits/{id}/rust-scan/review`, body `{status, notes, version}`.
- `POST /api/visits/{id}/ai-suggestion`: wording suggestion. Gemini when a key is set
  (counted in the shared AI usage limit), otherwise a template. Never published.

The result is stored in `vehicle_visits.report["rust_scan"]` (no schema migration).

## Model, data and measured accuracy

`server/models/rust_detector.onnx` is the YOLO11n detector from `rust-service/` (the same
file), trained for 50 epochs on the train split of "Rusted_Cars v3" by szymon-pgasw, Roboflow
Universe, **CC BY 4.0** (attribution required). The dataset has 274 photos of car bodies
(192 train / 55 validation / 27 test, 644 boxes, one class). No photo appears in more than
one split (checked by name and by file hash).

Two YOLO11 retrains (n and s, 150 epochs, `ml/rust/train.py`) were compared on the
**validation** split with the same evaluator: validation AP50 was 0.21 and 0.23, against 0.32
for this model, so this model was kept.

`ml/rust/evaluate.py` runs the file through the same code the server uses. It chooses the
threshold on validation (best F1: **0.17**), scores the test split once, and writes
`server/models/rust_detector.json`, which the app displays. Test split, 27 held-out photos
and 70 labelled rust regions:

| Measure | Value |
|---|---|
| Detections that lie on labelled rust ("located" precision) | 93 % |
| Labelled rust regions found ("located" recall) | 67 % |
| Rusty photos with at least one detection | 25 of 27 |
| Strict precision / recall at IoU 0.5 | 44 % / 34 % |
| Strict AP50 | 0.33 |

"Located" means a detection and a labelled region agree when half of the smaller box lies
inside the other. The labels mix one large box with several small boxes for the same kind of
damage. The strict score counts a correct large box over several small labelled spots as
both a miss and a false alarm. Quote both scores together, never one alone.

The earlier service threshold (0.08) finds more regions (strict recall 41 %). On the same
test photos it also produced 80 strict false positives against 31 at 0.17, roughly three
extra boxes per photo.

### Limitations

- Public photos of car bodies, not Lemmer vehicles or undercarriages.
- Box labels: the flagged area includes clean paint around rust and overstates extent.
- Every dataset photo contains rust, so false alarms on clean vehicles are unmeasured.
- 27 test photos is a small sample; figures can move several points between training runs.
- What would improve it: a few hundred real Lemmer undercarriage photos, including clean
  ones, outlined as polygons (YOLO11-seg). Then retrain and report error in rust-area %.

### Reproduce

```sh
python3.13 -m venv .local/rust-train-venv
.local/rust-train-venv/bin/pip install ultralytics onnx onnxruntime onnxslim
.local/rust-train-venv/bin/python ml/rust/train.py --data <path>/rusted_cars --model yolo11n
.venv/bin/python ml/rust/evaluate.py --data <path>/rusted_cars --name "YOLO11n rust detector" \
    --architecture yolo11n --epochs 50 --device CPU
```

The app itself needs only `numpy` and `onnxruntime`. Note: Ultralytics and its YOLO11 weights
are AGPL-3.0. Confirm licensing with Lemmer before any commercial use of the model.

## Checks

- `tests/test_rust_scan.py`: API, privacy, review-rule, work-report and model tests.
- `node scripts/check_rust_inspection.mjs` (backend running locally): the browser journey
  from technician scan to the customer passport, plus phone width. Screenshots go to `.local/rust-qa/`.
