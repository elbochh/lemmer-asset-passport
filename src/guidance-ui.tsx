import { useState } from "react";
import { post } from "./api";
import { ErrorBox } from "./shared";

export function GuidanceStatus({
  job,
  requestId,
  refresh,
}: {
  job: any;
  requestId: string;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const status = job?.status || "not_started";
  return (
    <div className="guidance-status" aria-live="polite">
      <strong>
        {{
          queued: "Queued for AI review",
          procedure: "Approved checklist available to your technician",
          completed: "Repair completed",
          running: "Reviewing symptoms and evidence…",
          ready: "AI evidence review complete",
          unavailable: "AI review unavailable",
          not_started: "AI review has not started",
        }[status as string] || status}
      </strong>
      <p>
        {job?.message || "Start the evidence review for this existing request."}
      </p>
      {["unavailable", "not_started"].includes(status) && (
        <button
          className="button secondary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await post(`/portal/requests/${requestId}/retry`, {});
              refresh();
            } catch (e: any) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Requesting…" : "Retry AI review"}
        </button>
      )}
      {error && <ErrorBox message={error} />}
    </div>
  );
}

export function PartCandidates({
  candidates = [],
  parts = {},
  onPart,
}: {
  candidates?: any[];
  parts?: Record<string, string>;
  onPart?: (p: string) => void;
}) {
  if (!candidates.length) return null;
  return (
    <section className="part-candidates">
      <h3>Parts to investigate</h3>
      <p className="muted">
        Evidence-backed alternatives. Confirm the cause before replacing a part.
      </p>
      {candidates.slice(0, 3).map((c: any) => (
        <article className="candidate-card" key={c.part}>
          <strong>
            {c.part}
            {parts[c.part] ? ` · ${parts[c.part]}` : ""}
          </strong>
          <p>{c.reason}</p>
          <p>
            <b>What would distinguish it:</b> {c.confirm_with}
          </p>
          <small>Evidence: {c.source_ids.join(", ")}</small>
          <p className="candidate-uncertainty">
            Probability / confidence interval: not yet validated.
          </p>
          {onPart && (
            <button className="button secondary" onClick={() => onPart(c.part)}>
              Ask about this part
            </button>
          )}
        </article>
      ))}
      <small>
        Repair-outcome data is needed to measure reliable probabilities.
        Percentages are not guessed by the language model.
      </small>
    </section>
  );
}
