import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ScanLine,
  Loader2,
  Car,
  ImagePlus,
  Info,
  ShieldCheck,
  TriangleAlert,
  ArrowRight,
  ClipboardList,
} from "lucide-react";
import { api, post, patch, date } from "./api";
import {
  Badge,
  Field,
  PageHeader,
  Loading,
  ErrorBox,
  Empty,
  useApp,
  useData,
} from "./shared";

export type RustFinding = {
  classification: string;
  confidence: number;
  polygon: number[][];
  box?: number[];
};

export type RustScan = {
  simulated: boolean;
  model: { name: string; version: string; threshold?: number };
  findings: RustFinding[];
  area_pct: number;
  severity: string;
  review_status: "Pending" | "Confirmed" | "Rejected" | "Needs Review";
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string;
  scanned_at: string;
  source_media_id?: string;
};

const CLOSED = ["Completed", "Cancelled", "Failed"];

/** Public test-split photos (Rusted_Cars v3, CC BY 4.0) the model never trained on. */
const SAMPLES = [
  { file: "rust-sample-1.jpg", label: "Sample A" },
  { file: "rust-sample-2.jpg", label: "Sample B" },
  { file: "rust-sample-3.jpg", label: "Sample C" },
];

/** The image a scan was run on (never a newer upload). */
export function scanImage(scan: RustScan, fallback?: string) {
  return scan.source_media_id
    ? "/api/visit-media/" + scan.source_media_id
    : fallback;
}

/** The scanned picture with detected rust regions drawn over it. */
export function RustOverlay({
  src,
  scan,
  compact = false,
}: {
  src: string;
  scan: RustScan;
  compact?: boolean;
}) {
  return (
    <figure className={"rust-overlay" + (compact ? " compact" : "")}>
      <div className="rust-overlay-frame">
        <img src={src} alt="Inspection photo with detected rust regions" />
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
          {scan.findings.map((f, i) => (
            <polygon
              key={i}
              points={f.polygon.map(([x, y]) => `${x},${y}`).join(" ")}
            />
          ))}
        </svg>
        {!compact &&
          scan.findings.map((f, i) => {
            const xs = f.polygon.map((p) => p[0]),
              ys = f.polygon.map((p) => p[1]);
            return (
              <span
                key={i}
                className="rust-label"
                style={{
                  left: `${Math.min(...xs) * 100}%`,
                  top: `${Math.min(...ys) * 100}%`,
                }}
              >
                {i + 1} · {Math.round(f.confidence * 100)}%
              </span>
            );
          })}
      </div>
    </figure>
  );
}

function RustStats({ scan }: { scan: RustScan }) {
  return (
    <dl className="rust-stats">
      <div>
        <dt>Rust regions</dt>
        <dd>{scan.findings.length}</dd>
      </div>
      <div>
        <dt>Photo area flagged</dt>
        <dd>{scan.area_pct.toFixed(1)}%</dd>
      </div>
      <div>
        <dt>Indicative severity</dt>
        <dd>
          <span className={"rust-severity " + scan.severity.toLowerCase()}>
            {scan.severity}
          </span>
        </dd>
      </div>
      <div>
        <dt>Top confidence</dt>
        <dd>
          {scan.findings.length
            ? Math.round(
                Math.max(...scan.findings.map((f) => f.confidence)) * 100,
              ) + "%"
            : "—"}
        </dd>
      </div>
    </dl>
  );
}

/** Compact record of a confirmed scan, used in passport timelines. */
export function RustScanSummary({ scan }: { scan: RustScan }) {
  const src = scanImage(scan);
  return (
    <div className="rust-record">
      {src && <RustOverlay src={src} scan={scan} compact />}
      <div>
        <RustStats scan={scan} />
        <p className="small">
          Confirmed by <strong>{scan.reviewed_by}</strong>
          {scan.reviewed_at ? ` on ${date(scan.reviewed_at)}` : ""}.
          {scan.review_notes ? ` “${scan.review_notes}”` : ""}
        </p>
        <small className="muted">
          {scan.simulated
            ? "Simulated detector (demo data, not computer vision)."
            : `Detected by ${scan.model.name}; severity is indicative, not a Lemmer standard.`}
        </small>
      </div>
    </div>
  );
}

/**
 * Rust scan for one vehicle visit. The result is a suggestion: a technician
 * confirms or rejects it, and that decision (name + time) is stored.
 */
export function RustScanPanel({
  visit,
  canEdit,
  onChange,
  toast,
}: {
  visit: any;
  canEdit: boolean;
  onChange: (visit: any) => void;
  toast: (message: string) => void;
}) {
  const scan: RustScan | undefined = visit.report?.rust_scan;
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");
  const hasBefore = String(visit.report?.before || "").startsWith(
    "/api/visit-media/",
  );
  const final = scan?.review_status === "Confirmed";
  const run = async (fn: () => Promise<any>, done: string) => {
    setBusy(true);
    try {
      const v = await fn();
      onChange({ ...v, asset: visit.asset });
      setNotes("");
      toast(done);
    } catch (e: any) {
      toast(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="rust-scan" aria-label="Rust scan">
      <div className="rust-scan-head">
        <ScanLine size={20} />
        <strong>Rust detection</strong>
        {scan && <Badge value={scan.review_status} />}
      </div>
      {!scan && (
        <p className="muted small">
          {hasBefore
            ? "Scan the photo for visible rust. The result is a suggestion that a technician must review."
            : "Add a photo first, then run the rust scan."}
        </p>
      )}
      {canEdit && !final && (
        <button
          className={"button rust-run " + (scan ? "secondary" : "primary")}
          disabled={busy || !hasBefore}
          onClick={() =>
            run(
              () => post(`/visits/${visit.id}/rust-scan`),
              "Rust scan complete. Review the result.",
            )
          }
        >
          {busy ? (
            <Loader2 className="spin" size={16} />
          ) : (
            <ScanLine size={16} />
          )}
          {scan ? "Run scan again" : "Run rust scan"}
        </button>
      )}
      {scan && (
        <>
          {scan.simulated && (
            <p className="rust-sim-note">
              SIMULATION · these regions are demo data, not computer vision.
            </p>
          )}
          {(scanImage(scan) || hasBefore) && (
            <RustOverlay
              src={scanImage(scan, visit.report.before)!}
              scan={scan}
            />
          )}
          {scan.findings.length === 0 && (
            <p className="rust-clear">
              No rust detected above the {Math.round((scan.model.threshold ?? 0.25) * 100)}% confidence threshold.
              Small or hidden corrosion can still be missed; inspect the
              vehicle.
            </p>
          )}
          <RustStats scan={scan} />
          <small className="muted">
            {scan.model.name}
            {scan.model.version ? ` · ${scan.model.version}` : ""} · scanned{" "}
            {date(scan.scanned_at)}. Severity is the share of the photo inside
            detected regions: indicative only, not a Lemmer standard.
          </small>
          {scan.reviewed_by && (
            <p className="small">
              {scan.review_status} by <strong>{scan.reviewed_by}</strong>
              {scan.reviewed_at ? ` on ${date(scan.reviewed_at)}` : ""}.
              {scan.review_notes ? ` “${scan.review_notes}”` : ""}
            </p>
          )}
          {final && (
            <p className="rust-final">
              <ShieldCheck size={16} />
              Recorded on the vehicle passport. Upload a new photo to scan
              another area.
            </p>
          )}
          {canEdit && !final && (
            <div className="rust-review">
              <Field label="Technician notes (optional)">
                <textarea
                  value={notes}
                  maxLength={2000}
                  rows={2}
                  placeholder="e.g. Surface rust on rear arch confirmed by hand; region 2 is a shadow."
                  onChange={(e) => setNotes(e.target.value)}
                />
              </Field>
              <div className="rust-review-actions">
                {(["Confirmed", "Rejected", "Needs Review"] as const).map(
                  (status) => (
                    <button
                      key={status}
                      className={
                        status === "Confirmed"
                          ? "button primary"
                          : "button secondary"
                      }
                      disabled={busy}
                      onClick={() =>
                        run(
                          () =>
                            patch(`/visits/${visit.id}/rust-scan/review`, {
                              status,
                              notes,
                              version: visit.version,
                            }),
                          status === "Confirmed"
                            ? "Confirmed and added to the vehicle passport."
                            : `Rust scan marked ${status.toLowerCase()}.`,
                        )
                      }
                    >
                      {status === "Confirmed" ? "Confirm & record" : status}
                    </button>
                  ),
                )}
              </div>
              <small className="muted">
                Only confirmed results reach the passport the customer sees.
              </small>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function pct(v?: number) {
  return v === undefined ? "—" : Math.round(v * 100) + "%";
}

/** What the active detector is, how well it measured, and where it falls short. */
function RustModelCard({ info }: { info: any }) {
  const [open, setOpen] = useState(false);
  if (!info) return null;
  if (info.simulated || !info.available)
    return (
      <div className="rust-model warning">
        <TriangleAlert size={22} />
        <div>
          <strong>{info.name}</strong>
          <p>
            {info.available
              ? "No trained model is installed, so scans use generated demo regions. Results must not be treated as inspection findings."
              : "The configured detector is not available. Check the server configuration."}
          </p>
        </div>
      </div>
    );
  const test = info.metrics?.test;
  return (
    <div className="rust-model">
      <ShieldCheck size={22} />
      <div className="rust-model-body">
        <div className="rust-model-head">
          <div>
            <strong>{info.name}</strong>
            <p>
              {info.mode === "local"
                ? "Runs on this server; photos are not sent to any outside service."
                : "External detection service."}
            </p>
          </div>
          {test && (
            <dl className="rust-model-metrics">
              <div>
                <dt>Detections on rust</dt>
                <dd>{pct(test.located_precision)}</dd>
              </div>
              <div>
                <dt>Rust regions found</dt>
                <dd>{pct(test.located_recall)}</dd>
              </div>
              <div>
                <dt>Strict AP50</dt>
                <dd>{pct(test.ap50)}</dd>
              </div>
            </dl>
          )}
        </div>
        {test && (
          <small className="muted">
            Measured on {test.images} held-out photos ({test.rust_regions} rust
            regions) the model never trained on, at a{" "}
            {pct(info.threshold)} confidence threshold. A detection and a
            labelled region agree when half of the smaller box lies inside the
            other; strict AP50 uses the standard IoU 0.5 box match, which
            penalises one large box drawn over several small labelled spots.
          </small>
        )}
        <button className="rust-model-toggle" onClick={() => setOpen(!open)}>
          <Info size={14} />
          {open ? "Hide limitations and data source" : "Limitations and data source"}
        </button>
        {open && (
          <div className="rust-model-details">
            <ul>
              {(info.limitations || []).map((l: string) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
            {info.dataset && (
              <p className="small">
                Training data:{" "}
                <a href={info.dataset.url} target="_blank" rel="noreferrer">
                  {info.dataset.name}
                </a>{" "}
                by {info.dataset.author}, {info.dataset.license}. Model version{" "}
                {info.version}, evaluated {info.evaluated_at}.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

async function uploadBefore(visitId: string, file: Blob, name: string) {
  const body = new FormData();
  body.append("file", file, name);
  const response = await fetch(`/api/visits/${visitId}/media/before`, {
    method: "POST",
    body,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok)
    throw Error(result.detail || "The photo could not be uploaded.");
  return result;
}

/** The "Rust inspection" tab: pick a vehicle, add a photo, scan, review. */
export function RustInspection() {
  const { session, refresh, toast } = useApp();
  const { data: assets, error } = useData("/portal/assets");
  const { data: visits } = useData("/visits");
  const { data: model } = useData("/rust-scan/model");
  const [active, setActive] = useState<any>(null);
  const [busy, setBusy] = useState("");
  if (error) return <ErrorBox message={error} />;
  if (!assets || !visits) return <Loading />;
  const vehicles = assets.filter((a: any) => a.ownership.kind === "vehicle");
  const technician = ["technician", "superuser"].includes(session.role);
  const canEdit = technician && active && !CLOSED.includes(active.status);
  const scans = visits.filter((v: any) => v.report?.rust_scan);
  // Visits arrive newest first, so the first scan seen per vehicle is its latest.
  const latest: Record<string, RustScan> = {};
  for (const v of scans)
    if (!latest[v.asset_id]) latest[v.asset_id] = v.report.rust_scan;
  const latestScans = Object.values(latest);
  const openVisit = (a: any) =>
    visits.find((v: any) => v.asset_id === a.id && !CLOSED.includes(v.status));
  const update = (v: any) => {
    setActive(v);
    refresh();
  };
  const start = async (a: any) => {
    setBusy("vehicle:" + a.id);
    try {
      const v = await post("/visits", { asset_id: a.id });
      setActive({ ...v, asset: a });
      refresh();
    } catch (e: any) {
      toast(e.message);
    } finally {
      setBusy("");
    }
  };
  const addPhoto = async (file: Blob, name: string) => {
    setBusy("photo");
    try {
      const v = await uploadBefore(active.id, file, name);
      update({ ...v, asset: active.asset });
      toast("Photo added. Run the rust scan.");
    } catch (e: any) {
      toast(e.message);
    } finally {
      setBusy("");
    }
  };
  const scan: RustScan | undefined = active?.report?.rust_scan;
  const hasPhoto = String(active?.report?.before || "").startsWith(
    "/api/visit-media/",
  );
  return (
    <>
      <PageHeader
        eyebrow="VEHICLE INSPECTION"
        title="Rust inspection"
        subtitle="Scan a vehicle photo for visible rust. A technician reviews every result, and only confirmed results reach the vehicle passport."
        actions={
          <Link to="/vehicles" className="button secondary">
            <ClipboardList size={16} />
            Bay visit records
          </Link>
        }
      />
      <RustModelCard info={model} />
      <div className="rust-summary">
        <div>
          <strong>{vehicles.length}</strong>
          <span>Vehicles</span>
        </div>
        <div>
          <strong>{latestScans.length}</strong>
          <span>Rust scanned</span>
        </div>
        <div>
          <strong>
            {latestScans.filter((x) => x.review_status === "Pending").length}
          </strong>
          <span>Awaiting technician review</span>
        </div>
        <div>
          <strong>{latestScans.filter((x) => x.severity === "High").length}</strong>
          <span>High indicative severity</span>
        </div>
      </div>
      <div className="rust-layout">
        <section className="panel rust-vehicles" aria-label="Vehicles">
          <h2>
            <span className="rust-step">1</span>Choose a vehicle
          </h2>
          {vehicles.length ? (
            vehicles.map((a: any) => {
              const open = openVisit(a);
              const selected = active?.asset_id === a.id;
              return (
                <button
                  key={a.id}
                  className={"rust-vehicle" + (selected ? " selected" : "")}
                  disabled={!!busy}
                  onClick={() => start(a)}
                >
                  <Car size={22} />
                  <div>
                    <strong>{a.name}</strong>
                    <small>
                      {a.code} · {a.manufacturer} {a.model}
                      {a.ownership.profile?.year
                        ? ` · ${a.ownership.profile.year}`
                        : ""}
                    </small>
                    <small>{a.customer}</small>
                  </div>
                  {busy === "vehicle:" + a.id ? (
                    <Loader2 className="spin" size={16} />
                  ) : open ? (
                    <Badge value={open.status} />
                  ) : (
                    <ArrowRight size={16} />
                  )}
                </button>
              );
            })
          ) : (
            <p className="muted small">
              No vehicle passports yet. Reception or a super-user can register
              one under Register equipment.
            </p>
          )}
        </section>
        <section className="panel rust-workspace" aria-label="Inspection">
          {!active ? (
            <Empty icon={ScanLine} title="Choose a vehicle to inspect">
              Selecting a vehicle opens its current bay visit, or starts one.
              Photos and results stay attached to that visit.
            </Empty>
          ) : (
            <>
              <div className="rust-visit-head">
                <div>
                  <span className="eyebrow">{active.asset?.code}</span>
                  <h2>{active.asset?.name || "Vehicle visit"}</h2>
                  <small className="muted">
                    VIN {active.asset?.ownership?.profile?.vin || "not recorded"}{" "}
                    · visit opened {date(active.created_at)}
                  </small>
                </div>
                <Badge value={active.status} />
              </div>
              {!technician && (
                <p className="note-box small">
                  <Info size={16} />
                  Viewing only. A technician adds photos, runs scans and
                  confirms results.
                </p>
              )}
              {canEdit && (
                <div className="rust-photo">
                  <h3>
                    <span className="rust-step">2</span>Add a photo
                  </h3>
                  <div className="rust-photo-actions">
                    <label className="button secondary rust-upload">
                      {busy === "photo" ? (
                        <Loader2 className="spin" size={16} />
                      ) : (
                        <ImagePlus size={16} />
                      )}
                      Upload JPG or PNG
                      <input
                        type="file"
                        accept="image/jpeg,image/png"
                        disabled={!!busy}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          e.target.value = "";
                          if (file) addPhoto(file, file.name);
                        }}
                      />
                    </label>
                    <span className="muted small">or try a held-out sample:</span>
                    {SAMPLES.map((s) => (
                      <button
                        key={s.file}
                        className="rust-sample"
                        disabled={!!busy}
                        onClick={async () => {
                          const blob = await fetch(
                            "/images/rust-samples/" + s.file,
                          ).then((r) => r.blob());
                          addPhoto(blob, s.file);
                        }}
                      >
                        <img src={"/images/rust-samples/" + s.file} alt="" />
                        {s.label}
                      </button>
                    ))}
                  </div>
                  <small className="muted">
                    Up to 2.5 MB. A new photo replaces any scan that has not
                    been confirmed.
                  </small>
                  {hasPhoto && !scan && (
                    <img
                      className="rust-preview"
                      src={active.report.before}
                      alt="Photo ready to scan"
                    />
                  )}
                </div>
              )}
              <div>
                {canEdit && (
                  <h3>
                    <span className="rust-step">3</span>Scan and review
                  </h3>
                )}
                <RustScanPanel
                  key={active.id + (scan?.scanned_at || "")}
                  visit={active}
                  canEdit={!!canEdit}
                  onChange={update}
                  toast={toast}
                />
              </div>
              <div className="rust-links">
                <Link
                  to={"/vehicles?visit=" + active.id}
                  className="rust-passport-link"
                >
                  Continue the visit record (findings, treatment, AI wording){" "}
                  <ArrowRight size={14} />
                </Link>
                <Link
                  to={"/assets/" + active.asset_id}
                  className="rust-passport-link"
                >
                  Open the vehicle passport <ArrowRight size={14} />
                </Link>
              </div>
            </>
          )}
        </section>
      </div>
      <h2 className="section-heading">Recent rust scans</h2>
      {scans.length ? (
        <div className="rust-history">
          {scans.map((v: any) => {
            const s: RustScan = v.report.rust_scan;
            return (
              <button
                key={v.id}
                className="panel rust-history-row"
                onClick={async () => {
                  try {
                    const fresh = (await api("/visits")).find(
                      (x: any) => x.id === v.id,
                    );
                    setActive(fresh || v);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  } catch (e: any) {
                    toast(e.message);
                  }
                }}
              >
                <Car size={20} />
                <div>
                  <strong>{v.asset.name}</strong>
                  <small>
                    {date(s.scanned_at)} · {s.findings.length} region
                    {s.findings.length === 1 ? "" : "s"} ·{" "}
                    {s.area_pct.toFixed(1)}% flagged · {s.severity}
                    {s.simulated ? " · simulated" : ""}
                  </small>
                </div>
                <Badge value={s.review_status} />
              </button>
            );
          })}
        </div>
      ) : (
        <p className="muted">
          No scans yet. Results appear here with their review status.
        </p>
      )}
    </>
  );
}

/** Plain-text draft of the findings from a rust scan. The technician edits it. */
export function draftFindings(scan: RustScan): string {
  const n = scan.findings.length;
  const lines = [
    n
      ? `Rust scan (${scan.model.name}${scan.model.version ? " " + scan.model.version : ""}): ${n} region${n > 1 ? "s" : ""} detected, about ${scan.area_pct.toFixed(1)}% of the inspected image. Indicative severity: ${scan.severity}.`
      : `Rust scan (${scan.model.name}): no rust regions detected in the inspected image.`,
    `Technician review of the scan: ${scan.review_status}${scan.reviewed_by ? " by " + scan.reviewed_by : ""}.`,
  ];
  if (scan.review_notes) lines.push(`Review notes: ${scan.review_notes}`);
  lines.push("Location on the vehicle and observations: ");
  return lines.join("\n");
}
