import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useApp, useData, Loading, ErrorBox } from "./shared";
import { post } from "./api";
import { AccountAccess } from "./expansion";

const fmt = (d: string) =>
  new Date(d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

/** Account-gated, read-only view of the technician's confirmed work, opened by QR code. */
export function WorkReport() {
  const { share, code } = useParams();
  const { session } = useApp();
  const [params] = useSearchParams();
  const token = params.get("t") || "";
  const [login, setLogin] = useState(false);
  const [joined, setJoined] = useState(!token);
  useEffect(() => {
    if (session && token && share && code)
      post(`/work/${share}/${code}/join?token=${encodeURIComponent(token)}`, {})
        .catch(() => {})
        .finally(() => setJoined(true));
  }, [session, token, share, code]);
  if (!session)
    return (
      <main className="qr-gate">
        <img src="/images/lemmer-logo.svg" alt="Lemmer" />
        <ShieldCheck size={40} />
        <h1>Your work report</h1>
        <p>
          Create your account or sign in to see what the technician did on{" "}
          {code}. The report is read-only: you can view the completed work, not change it.
        </p>
        <button className="button primary" onClick={() => setLogin(true)}>
          Sign in / create account
        </button>
        <Link to="/">Return to the app</Link>
        {login && (
          <AccountAccess
            onClose={() => setLogin(false)}
            qr={token ? { share: share!, code: code!, token } : undefined}
          />
        )}
      </main>
    );
  if (!joined) return <Loading />;
  return <Report share={share} code={code} />;
}

function Report({ share, code }: { share?: string; code?: string }) {
  const { data, error } = useData(`/work/${share}/${code}`);
  if (error)
    return (
      <main className="public-page">
        <ErrorBox message={error} />
      </main>
    );
  if (!data) return <Loading />;
  return (
    <main className="public-page">
      <header>
        <img src="/images/lemmer-logo.svg" alt="Lemmer" />
        <span>WORK REPORT</span>
      </header>
      <section className="public-identity">
        <span className="asset-code">{data.asset.code}</span>
        <h1>{data.asset.name}</h1>
        <p>Repairs, inspections and checks recorded by the Lemmer technician.</p>
      </section>
      {!data.work.length && (
        <p className="muted">No completed work has been recorded yet.</p>
      )}
      {data.work.map((w: any, i: number) => (
        <section className="panel record-block" key={i}>
          <strong>{w.title}</strong> <small>{fmt(w.date)}</small>
          {w.outcome && (
            <p>
              <strong>Outcome: </strong>
              {w.outcome}
            </p>
          )}
          {w.symptom && (
            <p>
              <strong>Problem reported: </strong>
              {w.symptom}
            </p>
          )}
          {w.work && (
            <p>
              <strong>Work done: </strong>
              {w.work}
            </p>
          )}
          {w.test && (
            <p>
              <strong>Checked by: </strong>
              {w.test}
            </p>
          )}
          {w.parts?.length > 0 && (
            <p>
              <strong>Parts: </strong>
              {w.parts.join(", ")}
            </p>
          )}
          {w.notes && (
            <p>
              <strong>Technician notes: </strong>
              {w.notes}
            </p>
          )}
          {w.rust_review && (
            <p>
              <strong>Rust inspection (reviewed by the technician): </strong>
              {w.rust_review.regions} area
              {w.rust_review.regions === 1 ? "" : "s"} marked, about{" "}
              {Number(w.rust_review.area_pct).toFixed(1)}% of the inspected
              image. Indicative severity: {w.rust_review.severity}.
              {w.rust_review.notes ? " Note: " + w.rust_review.notes : ""}
            </p>
          )}
          {w.findings && (
            <p>
              <strong>Findings: </strong>
              {w.findings}
            </p>
          )}
          {w.treatment && (
            <p>
              <strong>Treatment: </strong>
              {w.treatment}
            </p>
          )}
          {w.verification && (
            <p>
              <strong>Verification and advice: </strong>
              {w.verification}
            </p>
          )}
        </section>
      ))}
      <p className="muted">
        This report shows only what the technician recorded or confirmed. The
        rust scan is an indicative aid, not a certified measurement.
      </p>
    </main>
  );
}
