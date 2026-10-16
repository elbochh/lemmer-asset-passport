# Lemmer Asset Passport

A working technician demo: identify an individual machine, retrieve its history, obtain evidence-grounded AI assistance, and record a completed repair that becomes future service knowledge.

For a detailed explanation in plain language, read the [beginner’s architecture and AI guide](docs/BEGINNER_GUIDE.md).

## Run locally

Requires Node 20+, Python 3.12+, and PostgreSQL 16+. The configured database must be PostgreSQL; there is no SQLite fallback.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Set DATABASE_URL, a random SESSION_SECRET, and GEMINI_API_KEY in .env.
npm ci
npm run build
.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. For frontend development run `npm run dev` in another terminal (Vite forwards API requests to port 8000). Tables are created on first startup. Each new browser demo receives six independent assets, six requests and eight clearly labeled synthetic cases. The signed session lasts 30 days. Export before signing out: a new session creates a new workspace; there is no account recovery in this public demo.

```sh
.venv/bin/python -m pytest -q
npm run build
```

Tests create isolated sample workspaces in the configured database. Use a development database, not a database containing company data.

## Mobile and tablet checks

The app uses a navigation drawer on phones and tablets, labeled request cards on narrow screens, and larger touch controls. Forms use 16px inputs to avoid automatic zoom on iPhones, and dialogs scroll within the available screen height. Request filters can be swiped horizontally. Desktop layouts and printable receipts remain available.

`npm run test:mobile` checks the staff, reception, administrator and customer screens at widths from 320px to 1440px. It also checks navigation focus, Escape, route closing, resizing, search, short-screen dialogs, and the QR sign-in screen. Screenshots and results are saved to `.local/mobile-qa/`.

Start the backend with **an isolated local test database** and `AUTO_GUIDANCE_WORKER=0`, then start Vite with `npm run dev` in another terminal. The checks create a synthetic workspace; disabling the guidance worker prevents background model calls. The server must be local, and the database must have room below the demo's 200-workspace limit.

```sh
# Example using the local PostgreSQL port; adjust it for your development setup.
createdb -h 127.0.0.1 -p 55432 lemmer_mobile_qa
DATABASE_URL=postgresql+psycopg://localhost:55432/lemmer_mobile_qa AUTO_GUIDANCE_WORKER=0 \
  .venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000

# With backend and Vite running:
npx playwright install chromium webkit
MOBILE_TEST_CHANNEL=chromium npm run test:mobile
MOBILE_TEST_ENGINE=webkit npm run test:mobile
```

The check uses installed Chrome by default; `MOBILE_TEST_CHANNEL=chromium` selects Playwright's Chromium instead. `MOBILE_TEST_URL` can select a different local frontend port. Browser emulation checks layout and behavior; physical-device testing is still useful for on-screen keyboards, camera uploads, and device-specific browser behavior.

## Reception → technician handoff

Choose **Try reception** from the landing page, or switch to **Taylor Brooks · Reception** in an existing workspace. You can switch demo identities using the top-bar account selector.

1. Click **Try sample paper**, upload a JPG/PNG/PDF scan, or enter the customer's details directly.
2. The live model transcribes the paper into editable fields. Compare those fields with the original preview. Select the exact asset/serial and receiving technician.
3. Confirm the review checkbox and **Send to technician**. The request, source scan and reception notes are saved together. Reviewed AI guidance starts automatically in the background.
4. Click **See the technician's view**. The assigned technician sees the request in **My work queue**, which checks for handoffs every 15 seconds.
5. Open the request to view the original paper, contact details and reception notes alongside automatically delivered service assistance. No recommendation button is needed. Only a technician can finalize a repair or request troubleshooting AI.

The sample paper is explicitly fictional. Your actual service-paper template has not been supplied; extraction is currently general-purpose and requires receptionist verification, including for handwritten forms. An unreadable paper or unavailable model can still be retained and completed manually. Scans are stored in PostgreSQL for this bounded demo (20 per workspace, 200 total, 2.5 MB each; PDFs limited to five pages). Larger deployment should use object storage. Demo identities share one browser's workspace; they are not real employee credentials or a cross-device employee-login system.

## Demo journey

1. Open the demo workspace and choose the request **Pump runs, but will not prime** for **LM-1042**.
2. Guidance starts automatically for an older sample request when opened; reception handoffs start it at submission. Inspect Recommendation, Sources and Evidence review. A live result usually takes tens of seconds because retrieval, generation and judging are sequential.
3. Complete the technician report with an actual simulated diagnosis, work, parts, test and outcome. Wait for **Draft saved**, then finalize.
4. Open LM-1042's Passport and the Knowledge library. The new event and its corresponding case are persisted together.
5. Run assistance again with a relevant symptom. The new case is eligible for retrieval without retraining.
6. Compare **LM-1043**, another L-1095 with its own serial/history. Each QR opens its own public passport and linked request form.
7. Use **AI evaluation** to compare the same input under three context conditions. Export the result for technician review.

This is a demonstrable application, not a production deployment. It uses synthetic customers and cases. Email notifications are previews, CV is deferred, and the product reference contains the cited parts sheets for L-1095 and L-65, not the full Lemmer catalog. No historical company data has been received or validated.

## AI configuration

- Generator: `gemini-3.1-flash-lite`
- Separate judge: `gemini-2.5-flash`
- Embeddings: `gemini-embedding-001`, 768 dimensions, cached in PostgreSQL
- Hybrid retrieval: model filtering, semantic cosine ranking and PostgreSQL full-text ranking, combined using reciprocal rank fusion
- If embeddings fail, the reported retrieval method changes to full-text/keyword retrieval. No fabricated AI fallback is shown when generation/judging fails.
- Every cause/check must cite a retrieved source. Part identifiers are checked against that model's sourced Markdown. A failed deterministic check or judge criterion withholds the repair recommendation. Uncertain results also withhold causes, repair checks and parts, showing clarification questions only.
- A judge assesses evidence support; it does **not** prove a repair is correct. Unknown problems may produce questions or an abstention.
- Global limit: 30 attempts in a rolling 24 hours, including failures and evaluation calls. One A/B/C comparison consumes three attempts. There is no automatic paid upgrade or alternate provider.

Use the configured models with a free-tier Google project. This application does not change Google billing settings. Quota errors are shown directly. Google's free-tier data handling must be reviewed before using private company information.

## Team development

Clone this public repository and create your own `.env` from `.env.example`. Use a dedicated local PostgreSQL database and your own credentials. Generate a session secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. The model key is needed for live AI features; set `AUTO_GUIDANCE_WORKER=0` for development without background model calls.

Create the database before starting the backend, for example `createdb lemmer_demo` using your local PostgreSQL installation. Set `DATABASE_URL` to match its user, password, host, port, and database. For isolated backend tests, create a separate database and run:

```sh
createdb lemmer_test
DATABASE_URL=postgresql+psycopg://localhost/lemmer_test AUTO_GUIDANCE_WORKER=0 .venv/bin/python -m pytest -q
```

Create a branch for each change and open a pull request against `main`. Teammates with repository write access can push branches directly; others can fork the public repository and open a pull request from their fork. See [CONTRIBUTING.md](CONTRIBUTING.md).

See [architecture](docs/ARCHITECTURE.md), [Calgary workflow](docs/V3_CALGARY.md), [source attribution](docs/SOURCES.md), and [knowledge rules](knowledge/README.md).

This repository contains a clean source snapshot. Private deployment configuration, company correspondence, database contents, backups, internal reports, generated build files, and earlier local Git history are excluded. Local setup does not require the project owner's cloud account.

Reception has its own menu: Reception desk, Service tracking and Asset passports. Technicians have Overview, My work queue, Service requests, Asset passports, Knowledge library and AI evaluation. Role-specific routes redirect to the appropriate workspace. Account switching is for demonstration only.
