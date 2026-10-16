import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Search,
  BookOpen,
  FileText,
  ArrowUpRight,
  Info,
  Loader2,
  Download,
  FlaskConical,
  User,
  ShieldCheck,
  Mail,
} from "lucide-react";
import { post, date, ServiceRequest } from "./api";
import {
  useApp,
  useData,
  PageHeader,
  Loading,
  ErrorBox,
  Badge,
  Empty,
  Modal,
  Field,
  DocumentModal,
  SourceCard,
} from "./shared";
import { AIResult } from "./service";
export function Knowledge() {
  const { session } = useApp();
  const { data, error } = useData("/knowledge");
  const [tab, setTab] = useState("Repair cases"),
    [search, setSearch] = useState(""),
    [model, setModel] = useState("All models"),
    [doc, setDoc] = useState<any>(null),
    [imp, setImp] = useState(false);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const cases = data.cases.filter(
    (c: any) =>
      (model === "All models" || c.model === model) &&
      `${c.symptom} ${c.diagnosis} ${c.code} ${c.parts.join(" ")}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        title="Knowledge library"
        subtitle="The product facts and service experience behind better troubleshooting."
        actions={
          session.role === "superuser" && (
            <button className="button primary" onClick={() => setImp(true)}>
              <Plus size={17} />
              Import cases
            </button>
          )
        }
      />
      <div className="knowledge-banner">
        <BookOpen size={23} />
        <div>
          <strong>Private repair records and product references.</strong>
          <p>
            Finalized reports remain asset history. Wider troubleshooting uses
            the separately reviewed procedure library. These records are not
            approved general repair instructions.
          </p>
        </div>
        <span>
          {data.cases.length} cases <b>·</b> {data.documents.length} documents
        </span>
      </div>
      <section className="panel">
        <div className="tabs">
          {["Repair cases", "Product documents"].map((t) => (
            <button
              key={t}
              className={t === tab ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {t}
              <span>
                {t === "Repair cases"
                  ? data.cases.length
                  : data.documents.length}
              </span>
            </button>
          ))}
        </div>
        <div className="table-toolbar">
          <div className="input-with-icon">
            <Search size={17} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search symptoms, components or case IDs…"
              aria-label="Search knowledge"
            />
          </div>
          <select
            className="filter-select"
            aria-label="Filter by model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option>All models</option>
            {Array.from(new Set(data.cases.map((c: any) => c.model))).map(
              (m: any) => (
                <option key={m}>{m}</option>
              ),
            )}
          </select>
        </div>
        {tab === "Repair cases" ? (
          <div className="knowledge-cases">
            {cases.map((c: any) => (
              <SourceCard
                key={c.id}
                source={{
                  id: c.code,
                  kind: "case",
                  title: c.symptom,
                  outcome: c.outcome,
                  source: c.source,
                  content: `Model: ${c.model}\nDiagnosis: ${c.diagnosis}\nWork: ${c.repair}\nParts: ${c.parts.join(", ") || "None recorded"}\nTest: ${c.test}\nOutcome: ${c.outcome}\nSource: ${c.source}`,
                }}
              />
            ))}
            {!cases.length && (
              <Empty title="No matching cases">
                Try another symptom, part or model.
              </Empty>
            )}
          </div>
        ) : (
          <div className="document-grid">
            {data.documents
              .filter(
                (d: any) =>
                  (model === "All models" || d.model === model) &&
                  d.content.toLowerCase().includes(search.toLowerCase()),
              )
              .map((d: any) => (
                <button
                  className="document-card"
                  key={d.id}
                  onClick={() => setDoc(d)}
                >
                  <div>
                    <FileText size={24} />
                    <span className="tag">MARKDOWN</span>
                  </div>
                  <h3>{d.title}</h3>
                  <p>Manufacturer source · Revision {d.revision}</p>
                  <span className="text-link">
                    Read knowledge file <ArrowUpRight size={15} />
                  </span>
                </button>
              ))}
          </div>
        )}
      </section>
      <div className="note-box knowledge-note">
        <Info size={18} />
        <p>
          Public Lemmer documents provide verified product facts. Initial repair
          cases are synthetic examples. Imported records remain labeled and
          require technician review.
        </p>
      </div>
      {doc && <DocumentModal doc={doc} onClose={() => setDoc(null)} />}{" "}
      {imp && <ImportModal onClose={() => setImp(false)} />}
    </>
  );
}
function ImportModal({ onClose }: { onClose: () => void }) {
  const { refresh, toast } = useApp();
  const [content, setContent] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const sample = JSON.stringify(
    [
      {
        model: "L015-201",
        symptom: "Describe the reported equipment problem",
        diagnosis: "Technician-confirmed diagnosis",
        repair: "Actual work performed",
        parts: [],
        test: "Test performed and observed result",
        outcome: "Repaired",
      },
    ],
    null,
    2,
  );
  return (
    <Modal
      title="Import repair knowledge"
      subtitle="Add structured sample cases now. Use the same format when approved company data is available."
      onClose={onClose}
      wide
    >
      <div className="form-body">
        <div className="note-box">
          <Info size={17} />
          <p>
            The free model service is for public and synthetic demo data. Do not
            import private company records into this public demonstration.
          </p>
        </div>
        <div className="import-actions">
          <label className="button secondary">
            <FileText size={16} />
            Choose JSON file
            <input
              type="file"
              accept=".json,application/json"
              hidden
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (f) {
                  if (f.size > 200000) {
                    setError("Please use a file smaller than 200 KB.");
                    return;
                  }
                  setContent(await f.text());
                }
              }}
            />
          </label>
          <button className="text-link" onClick={() => setContent(sample)}>
            Load format example
          </button>
        </div>
        <Field label="Cases (JSON array)">
          <textarea
            className="code-input"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={13}
            placeholder={sample}
          />
        </Field>
        {error && <ErrorBox message={error} />}
        <div className="modal-actions">
          <button className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button primary"
            disabled={busy || !content}
            onClick={async () => {
              setError("");
              setBusy(true);
              try {
                const cases = JSON.parse(content);
                if (!Array.isArray(cases))
                  throw Error("Provide a JSON array of cases.");
                const result = await post("/knowledge/import", { cases });
                refresh();
                toast(`${result.imported} cases imported.`);
                onClose();
              } catch (e: any) {
                setError(e.message);
                setBusy(false);
              }
            }}
          >
            {busy ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
            Import cases
          </button>
        </div>
      </div>
    </Modal>
  );
}
export function Evaluation() {
  const { data, error } = useData("/dashboard");
  const { toast } = useApp();
  const [requestId, setRequestId] = useState(""),
    [problem, setProblem] = useState(""),
    [results, setResults] = useState<Record<string, any>>({}),
    [busy, setBusy] = useState(false),
    [evalError, setEvalError] = useState("");
  useEffect(() => {
    if (data && !requestId) {
      setRequestId(data.requests[0].id);
      setProblem(data.requests[0].description);
    }
  }, [data, requestId]);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  async function run() {
    setBusy(true);
    setEvalError("");
    setResults({});
    try {
      for (const mode of ["A", "B", "C"]) {
        const r = await post("/requests/" + requestId + "/recommend", {
          problem,
          mode,
        });
        setResults((prev) => ({ ...prev, [mode]: r }));
      }
      toast("Three-context comparison complete.");
    } catch (e: any) {
      setEvalError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="UNDERSTAND WHAT THE PASSPORT ADDS"
        title="AI evaluation"
        subtitle="Same problem. Same models. Three different sources of context."
        actions={
          <button
            className="button secondary"
            disabled={!Object.keys(results).length}
            onClick={() => {
              const blob = new Blob(
                [
                  JSON.stringify(
                    {
                      problem,
                      results,
                      note: "Exploratory demo comparison, not a held-out benchmark.",
                    },
                    null,
                    2,
                  ),
                ],
                { type: "application/json" },
              );
              const url = URL.createObjectURL(blob),
                a = document.createElement("a");
              a.href = url;
              a.download = "lemmer-evaluation.json";
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download size={16} />
            Export results
          </button>
        }
      />
      <div className="note-box evaluation-note">
        <FlaskConical size={20} />
        <p>
          <strong>An experiment, not an accuracy claim.</strong> Product
          documentation stays constant across A, B and C. Judge outputs measure
          evidence support; real accuracy requires held-out cases and technician
          assessment.
        </p>
      </div>
      <section className="panel evaluation-input">
        <div className="form-grid">
          <Field label="Service request">
            <select
              value={requestId}
              disabled={busy}
              onChange={(e) => {
                setRequestId(e.target.value);
                setProblem(
                  data.requests.find(
                    (r: ServiceRequest) => r.id === e.target.value,
                  ).description,
                );
                setResults({});
              }}
            >
              {data.requests.map((r: ServiceRequest) => (
                <option key={r.id} value={r.id}>
                  {r.code} · {r.asset.code}
                </option>
              ))}
            </select>
          </Field>
          <div className="eval-models">
            <span>GENERATOR + JUDGE</span>
            <strong>Flash-Lite + Flash</strong>
            <small>Same configuration in every condition</small>
          </div>
        </div>
        <Field label="Problem to compare">
          <textarea
            value={problem}
            disabled={busy}
            onChange={(e) => setProblem(e.target.value)}
            rows={3}
          />
        </Field>
        <button
          className="button primary"
          onClick={run}
          disabled={busy || problem.length < 10}
        >
          {busy ? (
            <Loader2 size={16} className="spin" />
          ) : (
            <FlaskConical size={16} />
          )}{" "}
          {busy
            ? `Comparing context ${Math.min(Object.keys(results).length + 1, 3)} of 3…`
            : "Run three-context comparison"}
        </button>
        {evalError && <ErrorBox message={evalError} />}
      </section>
      <div className="evaluation-grid">
        {[
          {
            id: "A",
            title: "Current problem",
            desc: "Problem + fixed product documentation",
            chips: ["Product facts"],
          },
          {
            id: "B",
            title: "Add repair knowledge",
            desc: "A + cases from other equipment",
            chips: ["Product facts", "Repair cases"],
          },
          {
            id: "C",
            title: "Add this asset’s history",
            desc: "B + this asset’s recorded experience",
            chips: ["Product facts", "Repair cases", "Asset history"],
          },
        ].map((c) => (
          <section
            className={"panel evaluation-column condition-" + c.id}
            key={c.id}
          >
            <div className="evaluation-card-header">
              <span className="condition-letter">{c.id}</span>
              <h2>{c.title}</h2>
              <p>{c.desc}</p>
              <div className="context-pills">
                {c.chips.map((x) => (
                  <span key={x}>{x}</span>
                ))}
              </div>
            </div>
            {results[c.id] ? (
              <div className="evaluation-result">
                <Badge value={results[c.id].verdict.replaceAll("_", " ")} />
                <p>{results[c.id].recommendation.summary}</p>
                <h4>WHAT THE REVIEW FOUND</h4>
                <p>{results[c.id].judge.reason}</p>
                <div className="evaluation-facts">
                  <span>{results[c.id].evidence.length} sources retrieved</span>
                  <span>
                    {(results[c.id].duration_ms / 1000).toFixed(1)} seconds
                  </span>
                </div>
                <details>
                  <summary>Inspect sources and checks</summary>
                  <AIResult result={results[c.id]} />
                </details>
              </div>
            ) : (
              <Empty icon={FlaskConical} title="Ready to compare">
                Run the comparison to see how the available context changes the
                result.
              </Empty>
            )}
          </section>
        ))}
      </div>
    </>
  );
}
export function Settings() {
  const { session, setSession, toast } = useApp();
  const { data: notes, error } = useData("/notifications");
  return (
    <>
      <PageHeader
        title="Workspace & activity"
        subtitle="Demo access, service notifications and a portable copy of your work."
      />
      <div className="settings-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Demo account</h2>
            <User size={19} />
          </div>
          <div className="panel-body">
            <p className="muted">
              Switch between approved demo technicians. Reports retain the name
              of the technician who recorded them.
            </p>
            <Field label="Active account">
              <select
                disabled={!session.demo}
                value={session.technician}
                onChange={async (e) => {
                  try {
                    const s = await post("/session/technician", {
                      name: e.target.value,
                    });
                    setSession(s);
                    toast("Technician switched.");
                  } catch (e: any) {
                    toast(e.message);
                  }
                }}
              >
                {(
                  session.accounts ||
                  session.technicians.map((name: string) => ({ name }))
                ).map((a: any) => (
                  <option key={a.name}>{a.name}</option>
                ))}
              </select>
            </Field>
            <div className="note-box">
              <ShieldCheck size={18} />
              <p>
                Each demo browser receives an isolated sample workspace. Named
                staff accounts are managed by the super-user in Calgary
                administration.
              </p>
            </div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-header">
            <h2>Take your work with you</h2>
            <Download size={19} />
          </div>
          <div className="panel-body">
            <p className="muted">
              Export assets, requests, service events, knowledge cases and AI
              runs from this workspace.
            </p>
            {session.role === "superuser" ? (
              <a className="button secondary" href="/api/export">
                <Download size={16} />
                Export workspace JSON
              </a>
            ) : (
              <p className="small muted">
                Workspace export is available to the super-user.
              </p>
            )}
            <div className="connection-status">
              <span>
                <i className="live-dot" />
                PostgreSQL persistence
              </span>
              <span>
                <i className="live-dot" />
                {session.ai_available
                  ? "Live AI connected"
                  : "AI configuration needed"}
              </span>
            </div>
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>
              Email previews <span className="count">{notes?.length || 0}</span>
            </h2>
            <p>
              Generated by service requests and completed reports. No emails are
              sent in this demo.
            </p>
          </div>
          <Mail size={21} />
        </div>
        {error ? (
          <ErrorBox message={error} />
        ) : !notes ? (
          <Loading />
        ) : notes.length ? (
          <div className="notification-list">
            {notes.map((n: any) => (
              <article key={n.id}>
                <span className="notification-icon">
                  <Mail size={19} />
                </span>
                <div>
                  <div className="notification-heading">
                    <h3>{n.subject}</h3>
                    <span className="tag">PREVIEW ONLY</span>
                  </div>
                  <span className="small muted">
                    To: {n.recipient} · {date(n.created_at)}
                  </span>
                  <p>{n.body}</p>
                  <Link to={"/requests/" + n.request_id} className="text-link">
                    Open service request <ArrowUpRight size={14} />
                  </Link>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty icon={Mail} title="No notifications yet">
            Submit a service request or finalize a report to generate an email
            preview.
          </Empty>
        )}
      </section>
    </>
  );
}
