import { useState } from "react";
import { ScanLine, Loader2 } from "lucide-react";
import { post, patch, date } from "./api";
import { Badge, Field } from "./shared";

export type RustScan = {
  simulated: boolean;
  model: { name: string; version: string };
  findings: {
    classification: string;
    confidence: number;
    polygon: number[][];
  }[];
  area_pct: number;
  severity: string;
  review_status: "Pending" | "Confirmed" | "Rejected" | "Needs Review";
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string;
  scanned_at: string;
};

/** The "before" picture with detected rust regions drawn over it. */
export function RustOverlay({ src, scan }: { src: string; scan: RustScan }) {
  return (
    <div className="rust-overlay">
      <img src={src} alt="Inspection image with detected rust regions" />
      <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
        {scan.findings.map((f, i) => (
          <polygon
            key={i}
            points={f.polygon.map(([x, y]) => `${x},${y}`).join(" ")}
          />
        ))}
      </svg>
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
  const [notes, setNotes] = useState(scan?.review_notes || "");
  const hasBefore = String(visit.report?.before || "").startsWith(
    "/api/visit-media/",
  );
  const run = async (fn: () => Promise<any>, done: string) => {
    setBusy(true);
    try {
      const v = await fn();
      onChange({ ...v, asset: visit.asset });
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
            ? "Scan the “before” image for rust. The result is a suggestion that a technician must review."
            : "Upload a “before” image first, then run the rust scan."}
        </p>
      )}
      {canEdit && (
        <button
          className="button secondary"
          disabled={busy || !hasBefore}
          onClick={() =>
            run(
              () => post(`/visits/${visit.id}/rust-scan`),
              "Rust scan complete. Review the result.",
            )
          }
        >
          {busy ? <Loader2 className="spin" size={16} /> : <ScanLine size={16} />}
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
          {hasBefore && <RustOverlay src={visit.report.before} scan={scan} />}
          <dl className="rust-stats">
            <div>
              <dt>Regions</dt>
              <dd>{scan.findings.length}</dd>
            </div>
            <div>
              <dt>Area covered</dt>
              <dd>{scan.area_pct.toFixed(1)}%</dd>
            </div>
            <div>
              <dt>Indicative severity</dt>
              <dd>{scan.severity}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>
                {scan.model.name}
                {scan.model.version ? ` ${scan.model.version}` : ""}
              </dd>
            </div>
          </dl>
          <small className="muted">
            Severity is indicative only (share of image area), not a Lemmer
            standard. Scanned {date(scan.scanned_at)}.
          </small>
          {scan.reviewed_by && (
            <p className="small">
              Reviewed by <strong>{scan.reviewed_by}</strong>
              {scan.reviewed_at ? ` on ${date(scan.reviewed_at)}` : ""}.
              {scan.review_notes ? ` ${scan.review_notes}` : ""}
            </p>
          )}
          {canEdit && (
            <div className="rust-review">
              <Field label="Technician notes (optional)">
                <textarea
                  value={notes}
                  maxLength={2000}
                  rows={2}
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
                          `Rust scan marked ${status.toLowerCase()}.`,
                        )
                      }
                    >
                      {status}
                    </button>
                  ),
                )}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
