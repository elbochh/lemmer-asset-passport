# Lemmer Asset Passport: Handover Guide

Capstone project, SAIT Integrated Artificial Intelligence, Fall 2026.
Team: Alain Claude Ebanda, Changyao Liu. Instructor: Jaspreet Gill. Client: Lemmer Spray Systems.

## 1. What this system does

Lemmer Asset Passport gives every vehicle and piece of equipment a lasting service record (a "passport"). It has two sides in one application:

- **Lemmer team (technicians, reception, super-user):** see and edit everything: service requests, asset passports, vehicle bay visits, parts requests, the knowledge library, and the vehicle rust inspection.
- **Customers:** create an account from a QR code and see, read-only, the work the technician completed on their vehicle or equipment.

Main features:

1. **Service workflow:** reception records a request with the original paper; the technician works it from a queue with AI-prepared guidance grounded in approved sources; the finished repair becomes part of the asset's history.
2. **Vehicle rust inspection:** the technician adds a photo of a vehicle, a YOLO11 detector (ONNX, runs inside the server) marks possible rust regions with a confidence, and the technician confirms, rejects or flags the result.
3. **AI-suggested wording (Gemini):** the AI suggests findings, treatment and verification. These appear in a separate block from the technician's own fields. The technician decides; nothing from the AI is published without technician review.
4. **Customer work QR:** the technician generates a QR code per asset ("Customer work QR"). The customer scans it, creates an account (no invitation) and sees the completed work: review, findings, treatment, verification, for vehicles and equipment repairs. Customers cannot change anything; AI suggestions, internal notes and unreviewed scans are never shown to them.
5. **Separate entrances:** the home page has "Lemmer team sign in" (sign-in only) and "Customer sign in / create account".

## 2. What is in the delivery

| Item | Location |
|---|---|
| Front end (React, TypeScript, Vite) | `src/` |
| Back end (FastAPI, SQLAlchemy, PostgreSQL) | `server/` |
| Rust detector model (ONNX) | `server/models/rust_detector.onnx` |
| Optional separate detector service | `rust-service/` |
| Model training and evaluation scripts | `ml/rust/` |
| Automated tests | `tests/` |
| Deployment files | `Dockerfile`, `render.yaml` |
| Documentation | `README.md`, `docs/` (this file, `ARCHITECTURE.md`, `RUST_SCAN.md`, `BEGINNER_GUIDE.md`) |
| Conference poster | provided separately (PDF, 24 x 36 in) |

## 3. Install and run locally

Requirements: Node 20+, Python 3.12+, PostgreSQL 16+ (no SQLite fallback).

```sh
createdb lemmer_demo
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then edit .env (see section 5)
npm ci
npm run build
.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Tables are created automatically on first start. Run the tests against a separate, empty database:

```sh
createdb lemmer_test
DATABASE_URL=postgresql+psycopg://localhost/lemmer_test AUTO_GUIDANCE_WORKER=0 .venv/bin/python -m pytest -q
```

## 4. Deploy (hosting)

The `Dockerfile` builds the front end and serves everything from one FastAPI container. `render.yaml` describes the Render setup (a web service plus a PostgreSQL database). Any host that runs Docker and provides PostgreSQL works.

`render.production.yaml` is a ready blueprint for Lemmer's own Render account (paid web service and database, `main` branch). `scripts/backup_db.sh` makes a database backup with `pg_dump`; schedule it regularly and keep copies off the host.

For continuous production use, do not use free plans: free web services sleep when idle (the first request can take 30 to 60 seconds) and free PostgreSQL databases expire. Use paid plans for both and enable database backups.

## 5. Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+psycopg://...`). Required. |
| `SESSION_SECRET` | Long random secret that signs sessions and QR tokens. Required. Changing it invalidates existing sessions and issued customer QR codes. |
| `GEMINI_API_KEY` | Key for the AI features. Create your own; usage is billed to the key's owner. Without it, AI-suggested wording falls back to a template and guidance is unavailable. |
| `RUST_DETECTOR` | `local` (recommended: runs the ONNX model in the server), `http` (separate service via `RUST_DETECTOR_URL`), or `simulated` (not real detection). |
| `RUST_DETECTOR_URL`, `RUST_DETECTOR_TOKEN` | Only for `http` mode. |
| `RUST_DETECTOR_THREADS` | CPU threads for local detection (default 2). |
| `ENVIRONMENT` | `production` or `development`. |
| `AUTO_GUIDANCE_WORKER` | `0` disables background AI calls (useful in development and tests). |
| `AI_DAILY_LIMIT` and related `AI_*` limits | Caps on daily AI usage. |

Never commit real keys. Regenerate any key that has been shared in a chat or an email.

## 6. How to operate it

**Lemmer team**
1. Open the site and choose "Lemmer team sign in" (or use the demo buttons in the demonstration build).
2. Reception: record a service request and send it to a technician.
3. Technician: open the request from "My work queue", review the guidance, add a vehicle visit with a before photo, open "Vehicle rust inspection", run the scan, and confirm, reject or flag the result. Use the AI suggestions only as a starting point; fill in and confirm the technician fields yourself.
4. Open the asset's passport and choose "Customer work QR" to display or print the QR code for that asset. Give it to the customer.

**Customer**
1. Scan the QR code.
2. Create an account (name, email, password of at least 10 characters).
3. Read the completed work. The customer cannot edit anything.

## 7. Current limits (please review)

- This is a working prototype built on synthetic customers and sample cases. No real Lemmer repair history or approved service library has been loaded or validated.
- The rust detector is a small YOLO11n model trained on public car-body photos, not on Lemmer vehicles. It locates rust with boxes and is indicative only; the technician must review every result. Measured accuracy is in `docs/RUST_SCAN.md`. Undercarriage photos from Lemmer would be needed to improve it.
- AI output is a suggestion and is never a substitute for the technician's judgement.
- The demonstration build includes no-signup demo workspaces with synthetic data. For real use, disable the demo entry points and create real staff accounts (an open decision for Lemmer).
- Photos are stored in PostgreSQL in this version. A larger deployment should use object storage.
- Email notifications are previews only.

## 8. Suggested final adjustments to discuss

1. Hosting account and ownership (Lemmer's own Render or other hosting, paid database, backups).
2. Real staff accounts and removal of the demo mode.
3. Real service forms and procedures to load into the knowledge library.
4. Lemmer undercarriage photos to retrain and re-measure the rust model.
5. A named contact at Lemmer responsible for keys, costs and redeployment.

## 9. Credits

Rust model: YOLO11 trained on the "Rusted_Cars v3" dataset (szymon-pgasw, Roboflow Universe, CC BY 4.0). See `docs/SOURCES.md` for all sources.
