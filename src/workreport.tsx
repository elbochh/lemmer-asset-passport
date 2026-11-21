import { useParams } from "react-router-dom";
import { useData, Loading, ErrorBox } from "./shared";

const fmt = (d: string) =>
  new Date(d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

/** Read-only customer view of the technician's confirmed work, opened by QR code. */
export function WorkReport() {
  const { share, code } = useParams();
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
        <p>What the Lemmer technician found, did and checked.</p>
      </section>
      {!data.work.length && (
        <p className="muted">No completed work has been recorded yet.</p>
      )}
      {data.work.map((w: any, i: number) => (
        <section className="panel record-block" key={i}>
          <strong>{w.title}</strong> <small>{fmt(w.date)}</small>
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
