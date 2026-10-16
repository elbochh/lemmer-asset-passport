import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, post, patch, date } from "./api";
import {
  useApp,
  useData,
  PageHeader,
  Field,
  ErrorBox,
  Loading,
  Badge,
} from "./shared";

function ActionForm({
  children,
  onSubmit,
  label = "Save",
}: {
  children: any;
  onSubmit: (f: any) => Promise<any>;
  label?: string;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <form
      className="panel-body"
      onSubmit={async (e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget));
        setBusy(true);
        setError("");
        try {
          await onSubmit(f);
        } catch (e: any) {
          setError(e.message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
      {error && <ErrorBox message={error} />}
      <button className="button primary" disabled={busy}>
        {busy ? "Saving…" : label}
      </button>
    </form>
  );
}
export function ProcedurePanel({ requestId }: { requestId: string }) {
  const { data, error } = useData("/requests/" + requestId + "/procedures");
  const { refresh, toast } = useApp();
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <section className="panel procedure-panel">
      <div className="panel-header">
        <h2>Approved troubleshooting</h2>
        <span className="tag">NO MODEL CALLS</span>
      </div>
      <div className="panel-body">
        <p>
          Choose an applicable symptom and record each observation. A similar
          complaint does not confirm the same fault.
        </p>
        {!data.procedures.length && (
          <div className="note-box">
            No approved procedure applies to this equipment yet. Record
            observations for technician investigation. AI may help interpret
            available evidence, but cannot fill this knowledge gap with a
            guessed repair.
          </div>
        )}
        {data.procedures.map((p: any) => {
          const run = data.runs.find(
            (r: any) => r.procedure_id === p.id && r.status === "In progress",
          );
          return (
            <article className="procedure-card" key={p.id}>
              <h3>{p.title}</h3>
              <p className="small muted">
                {p.model} · Product {p.product_number || "not specified"} ·
                Version {p.version} · Approved by {p.reviewer} ·{" "}
                {p.synthetic
                  ? "SYNTHETIC DEMO, not a validated Lemmer procedure"
                  : "Reviewed technical procedure"}
              </p>
              <p>{p.symptoms.join(" · ")}</p>
              {p.exact_symptom && (
                <Badge value="Exact symptom wording · confirm findings" />
              )}
              <details>
                <summary>Sources and approved sequence</summary>
                {p.references.map((r: any, i: number) => (
                  <blockquote key={i}>
                    <strong>{r.title}</strong>
                    <p>{r.passage}</p>
                    <small>
                      Page {r.page} · Revision {r.revision}
                    </small>
                    {r.url && (
                      <p>
                        <a href={r.url} target="_blank" rel="noreferrer">
                          Open source
                        </a>
                      </p>
                    )}
                  </blockquote>
                ))}
                <p>
                  <strong>Recorded solution and limits:</strong> {p.solution}
                </p>
                <ol>
                  {p.steps.map((s: any, i: number) => (
                    <li key={i}>{s.question}</li>
                  ))}
                </ol>
              </details>
              {run ? (
                <>
                  <p>
                    <strong>
                      Step {run.current_step + 1} of {p.steps.length}
                    </strong>
                  </p>
                  <p>{p.steps[run.current_step].question}</p>
                  <ActionForm
                    key={run.version}
                    label="Record answer & continue"
                    onSubmit={async (f) => {
                      await post("/procedure-runs/" + run.id + "/answer", {
                        ...f,
                        version: run.version,
                      });
                      refresh();
                    }}
                  >
                    <Field label="Observation result">
                      <select name="answer" required defaultValue="">
                        <option value="" disabled>
                          Choose an answer…
                        </option>
                        <option value="yes">Yes</option>
                        <option value="no">No</option>
                        <option value="unknown">Unknown / not assessed</option>
                      </select>
                    </Field>
                    <Field label="What did you observe?">
                      <textarea
                        name="observation"
                        required
                        minLength={3}
                        maxLength={2000}
                      />
                    </Field>
                  </ActionForm>
                </>
              ) : (
                <button
                  className="button secondary"
                  onClick={async () => {
                    try {
                      await post(
                        "/requests/" +
                          requestId +
                          "/procedures/" +
                          p.id +
                          "/start",
                      );
                      refresh();
                    } catch (e: any) {
                      toast(e.message);
                    }
                  }}
                >
                  Start approved checklist
                </button>
              )}
            </article>
          );
        })}
        {data.runs.length > 0 && (
          <details>
            <summary>Saved checklist history ({data.runs.length})</summary>
            {data.runs.map((r: any) => (
              <article key={r.id}>
                <strong>
                  {data.procedures.find((p: any) => p.id === r.procedure_id)
                    ?.title || "Retired or superseded procedure"}{" "}
                  · {r.status}
                </strong>
                <ol>
                  {r.answers.map((a: any, i: number) => (
                    <li key={i}>
                      Step {a.step + 1}: {a.answer}. {a.observation} · {a.actor}
                    </li>
                  ))}
                </ol>
                <p className="small muted">
                  Checklist completion is not a confirmed diagnosis. Record
                  actual findings and verification separately.
                </p>
              </article>
            ))}
          </details>
        )}
      </div>
    </section>
  );
}

export function Procedures() {
  const { data, error } = useData("/procedures");
  const { data: assets } = useData("/assets");
  const { session, refresh, toast } = useApp();
  const [editing, setEditing] = useState<any>(null),
    [steps, setSteps] = useState<any[]>([
      { question: "", yes: -1, no: -1, unknown: -1 },
    ]),
    [refs, setRefs] = useState<any[]>([
      { title: "", passage: "", url: "", page: "Unknown", revision: "Unknown" },
    ]),
    [asset, setAsset] = useState("");
  if (error) return <ErrorBox message={error} />;
  if (!data || !assets) return <Loading />;
  const begin = (p: any = {}) => {
    setEditing(p);
    setSteps(p.steps || [{ question: "", yes: -1, no: -1, unknown: -1 }]);
    setRefs(
      p.references || [
        {
          title: "",
          passage: "",
          url: "",
          page: "Unknown",
          revision: "Unknown",
        },
      ],
    );
    setAsset("");
  };
  return (
    <>
      <PageHeader
        title="Reviewed troubleshooting library"
        subtitle="Calgary · Versioned procedures. Human approval before wider use."
        actions={
          <div className="heading-actions">
            <button
              className="button secondary"
              onClick={() =>
                begin({
                  title: "Synthetic RP-460HD observation checklist",
                  symptoms: [
                    "Fluid seeps around the needle packing after use.",
                  ],
                  solution:
                    "Demonstration only: record the actual diagnosis and verification separately. This checklist does not authorize replacement.",
                  steps: [
                    {
                      question:
                        "Has the exact visible symptom and when it occurs been recorded without operating or disassembling the equipment?",
                      yes: -1,
                      no: -1,
                      unknown: -1,
                    },
                  ],
                  references: [
                    {
                      title: "Synthetic capstone workflow example",
                      passage:
                        "This fixture demonstrates observation capture only. It is not an approved Lemmer repair instruction.",
                      url: "",
                      page: "Unknown",
                      revision: "Demo 1",
                    },
                  ],
                  synthetic: true,
                })
              }
            >
              Try a synthetic proposal
            </button>
            <button className="button primary" onClick={() => begin()}>
              Propose a procedure
            </button>
          </div>
        }
      />
      <div className="note-box">
        Start with RP-460HD as the demo family. Actual procedures, repair
        evidence and approval criteria still need branch reviewers’s review. Public
        manuals establish product facts; they do not by themselves confirm a
        fault.
      </div>
      {editing && (
        <section className="panel">
          <div className="panel-header">
            <h2>{editing.id ? "Propose a new version" : "New proposal"}</h2>
            <button className="text-link" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
          <ActionForm
            label="Submit for human review"
            onSubmit={async (f) => {
              const a = assets.find((a: any) => a.id === asset);
              await post("/procedures", {
                title: f.title,
                manufacturer: a?.manufacturer || editing.manufacturer,
                model: a?.model || editing.model,
                product_number:
                  a?.product_number || editing.product_number || "",
                symptoms: String(f.symptoms).split("\n").filter(Boolean),
                solution: f.solution,
                steps,
                references: refs,
                synthetic: f.synthetic === "on",
                customer_visible: f.customer_visible === "on",
                previous_id: editing.id || null,
                source_case_id: editing.source_case_id || null,
              });
              setEditing(null);
              refresh();
              toast(
                "Proposal saved. It is not available for wider troubleshooting until approved.",
              );
            }}
          >
            <Field label="Title">
              <input
                name="title"
                required
                minLength={5}
                defaultValue={editing.title || ""}
              />
            </Field>
            <Field label="Applicable equipment">
              <select
                value={asset}
                onChange={(e) => setAsset(e.target.value)}
                required={!editing.id}
              >
                <option value="">
                  {editing.id
                    ? `${editing.manufacturer} ${editing.model} / ${editing.product_number}`
                    : "Choose the exact model / product…"}
                </option>
                {assets
                  .filter((a: any) => a.manufacturer !== "Ford")
                  .map((a: any) => (
                    <option key={a.id} value={a.id}>
                      {a.manufacturer} · {a.model} ·{" "}
                      {a.product_number || "No product number"} · {a.code}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="Known symptoms · one description per line">
              <textarea
                name="symptoms"
                required
                defaultValue={editing.symptoms?.join("\n") || ""}
              />
            </Field>
            <h3>Approved diagnostic sequence</h3>
            <p className="small muted">
              Each answer can move to a later step or finish the checklist.
              Finishing does not authorize a replacement.
            </p>
            {steps.map((s, i) => (
              <div className="procedure-editor-step" key={i}>
                <Field label={"Step " + (i + 1)}>
                  <textarea
                    required
                    minLength={5}
                    value={s.question}
                    onChange={(e) =>
                      setSteps(
                        steps.map((x, j) =>
                          j === i ? { ...x, question: e.target.value } : x,
                        ),
                      )
                    }
                  />
                </Field>
                <div className="form-grid">
                  {["yes", "no", "unknown"].map((k) => (
                    <Field label={"If " + k} key={k}>
                      <select
                        value={s[k]}
                        onChange={(e) =>
                          setSteps(
                            steps.map((x, j) =>
                              j === i
                                ? { ...x, [k]: Number(e.target.value) }
                                : x,
                            ),
                          )
                        }
                      >
                        <option value={-1}>Finish · record findings</option>
                        {steps.map(
                          (_, j) =>
                            j > i && (
                              <option key={j} value={j}>
                                Step {j + 1}
                              </option>
                            ),
                        )}
                      </select>
                    </Field>
                  ))}
                </div>
              </div>
            ))}
            <button
              type="button"
              className="button secondary"
              disabled={steps.length >= 30}
              onClick={() =>
                setSteps([
                  ...steps,
                  { question: "", yes: -1, no: -1, unknown: -1 },
                ])
              }
            >
              Add step
            </button>
            <Field label="Confirmed solution / investigation outcome and its limits">
              <textarea
                name="solution"
                required
                minLength={5}
                defaultValue={editing.solution || ""}
              />
            </Field>
            <h3>Source evidence</h3>
            {refs.map((r, i) => (
              <div key={i} className="procedure-editor-step">
                {["title", "passage", "url", "page", "revision"].map((k) => (
                  <Field
                    key={k}
                    label={k === "passage" ? "Exact relevant passage" : k}
                  >
                    <textarea
                      rows={k === "passage" ? 3 : 1}
                      required={k !== "url"}
                      value={r[k]}
                      onChange={(e) =>
                        setRefs(
                          refs.map((x, j) =>
                            j === i ? { ...x, [k]: e.target.value } : x,
                          ),
                        )
                      }
                    />
                  </Field>
                ))}
              </div>
            ))}
            <button
              type="button"
              className="button secondary"
              onClick={() =>
                setRefs([
                  ...refs,
                  {
                    title: "",
                    passage: "",
                    url: "",
                    page: "Unknown",
                    revision: "Unknown",
                  },
                ])
              }
            >
              Add reference
            </button>
            <label className="checkbox-field">
              <input
                type="checkbox"
                name="synthetic"
                defaultChecked={editing.synthetic ?? true}
              />
              Synthetic demonstration evidence
            </label>
            <label className="checkbox-field">
              <input
                type="checkbox"
                name="customer_visible"
                defaultChecked={editing.customer_visible || false}
              />
              Propose customer visibility (requires explicit privacy and
              suitability review)
            </label>
          </ActionForm>
        </section>
      )}
      {data.length === 0 && (
        <section className="panel panel-body">
          <h3>No approved procedures have been supplied yet</h3>
          <p>
            Propose a clearly labelled synthetic checklist to demonstrate the
            review process, or enter a real procedure once Lemmer supplies the
            source and an authorized reviewer checks it.
          </p>
        </section>
      )}
      {data.map((p: any) => (
        <article className="panel procedure-card" key={p.id}>
          <div className="heading-actions">
            <h2>{p.title}</h2>
            <Badge value={p.status} />
          </div>
          <p>
            {p.manufacturer} · {p.model} · Product{" "}
            {p.product_number || "unknown"} · Version {p.version}
          </p>
          <p>
            {p.synthetic ? "Synthetic example. " : ""}Author: {p.author}
            {p.reviewer
              ? ` · Reviewed by ${p.reviewer} · ${date(p.reviewed_at)}`
              : ""}
          </p>
          <details>
            <summary>Read complete proposal and sources</summary>
            <p>{p.symptoms.join(" · ")}</p>
            <ol>
              {p.steps.map((s: any, i: number) => (
                <li key={i}>
                  {s.question}{" "}
                  <small>
                    Yes → {s.yes < 0 ? "finish" : s.yes + 1}; No →{" "}
                    {s.no < 0 ? "finish" : s.no + 1}; Unknown →{" "}
                    {s.unknown < 0 ? "finish" : s.unknown + 1}
                  </small>
                </li>
              ))}
            </ol>
            <p>{p.solution}</p>
            {p.references.map((r: any, i: number) => (
              <blockquote key={i}>
                <strong>{r.title}</strong>
                <p>{r.passage}</p>
                <small>
                  Page {r.page} · Revision {r.revision}
                </small>
              </blockquote>
            ))}
          </details>
          <p className="muted">{p.review_reason}</p>
          <button className="button secondary" onClick={() => begin(p)}>
            Propose revised version
          </button>
          {session.role === "superuser" &&
            ["Pending review", "Approved"].includes(p.status) && (
              <ActionForm
                label="Record review decision"
                onSubmit={async (f) => {
                  await post("/procedures/" + p.id + "/review", {
                    status: f.status,
                    reason: f.reason,
                    technical_checked: f.technical_checked === "on",
                    privacy_checked: f.privacy_checked === "on",
                  });
                  refresh();
                }}
              >
                <Field label="Decision">
                  <select name="status" defaultValue="" required>
                    <option value="" disabled>
                      Choose…
                    </option>
                    {p.status === "Pending review" ? (
                      <>
                        <option>Approved</option>
                        <option>Rejected</option>
                      </>
                    ) : (
                      <option>Retired</option>
                    )}
                  </select>
                </Field>
                <label className="checkbox-field">
                  <input type="checkbox" name="technical_checked" />I checked
                  applicability, source support, diagnostic branches and limits.
                </label>
                <label className="checkbox-field">
                  <input type="checkbox" name="privacy_checked" />I removed
                  customer identities, contacts, pricing and confidential
                  details, and checked the proposed audience.
                </label>
                <Field label="Review reason">
                  <textarea name="reason" required minLength={10} />
                </Field>
              </ActionForm>
            )}
        </article>
      ))}
    </>
  );
}

export function Operations() {
  const { data, error } = useData("/operations"),
    { data: usage } = useData("/operations/usage"),
    { data: dash } = useData("/dashboard"),
    { data: customers } = useData("/customers");
  const { refresh, toast, session } = useApp();
  const [tab, setTab] = useState("Access"),
    [kind, setKind] = useState("asset"),
    [key, setKey] = useState("");
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const records =
    kind === "asset"
      ? dash?.assets || []
      : kind === "customer"
        ? customers || []
        : data.reports || [];
  const record = records.find((r: any) => r.id === key);
  const fields =
    kind === "asset"
      ? ["name", "serial", "model", "product_number", "manufacturer"]
      : kind === "customer"
        ? ["name", "email", "phone", "sap_customer_code"]
        : ["diagnosis", "work", "test", "outcome", "notes"];
  return (
    <>
      <PageHeader
        title="Calgary administration"
        subtitle="Super-user access, reviewed knowledge, corrections and AI usage."
      />
      <div className="tabs">
        {["Access", "Corrections", "Audit trail", "AI usage"].map((t) => (
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Access" ? (
        <>
          <div className="note-box">
            {session.demo
              ? "This super-user controls only this synthetic demo workspace. Existing organization customers keep their restricted customer permissions."
              : "Named staff sign-in. Disabling an account or changing its role revokes existing sessions."}{" "}
            Accounts are scoped to Lemmer Calgary.{" "}
            <Link to="/procedures">Review procedure proposals</Link>
          </div>
          <section className="panel">
            <div className="panel-header">
              <h2>Create named staff account</h2>
            </div>
            <ActionForm
              label="Create account"
              onSubmit={async (f) => {
                await post("/operations/staff", f);
                refresh();
                toast(
                  "Staff account created. Share its initial password privately; no email was sent.",
                );
              }}
            >
              <div className="form-grid">
                <Field label="Full name">
                  <input name="name" required minLength={2} />
                </Field>
                <Field label="Email">
                  <input name="email" type="email" required />
                </Field>
                <Field label="Initial password · share privately">
                  <input
                    type="password"
                    name="password"
                    autoComplete="new-password"
                    required
                    minLength={12}
                  />
                </Field>
                <Field label="Role">
                  <select name="role">
                    <option value="technician">Technician</option>
                    <option value="reception">Reception</option>
                    <option value="superuser">Super-user (manufacturer)</option>
                  </select>
                </Field>
              </div>
            </ActionForm>
          </section>
          {data.staff.map((u: any) => (
            <section className="panel" key={u.id}>
              <div className="panel-header">
                <h3>
                  {u.name} · {u.email}
                </h3>
                <Badge value={u.active ? "Active" : "Disabled"} />
              </div>
              <ActionForm
                label="Update access & revoke old sessions"
                onSubmit={async (f) => {
                  await patch("/operations/staff/" + u.id, {
                    ...f,
                    active: f.active === "yes",
                  });
                  refresh();
                }}
              >
                <div className="form-grid">
                  <Field label="Role">
                    <select name="role" defaultValue={u.role}>
                      <option value="technician">Technician</option>
                      <option value="reception">Reception</option>
                      <option value="superuser">Super-user</option>
                    </select>
                  </Field>
                  <Field label="Account access">
                    <select
                      name="active"
                      defaultValue={u.active ? "yes" : "no"}
                    >
                      <option value="yes">Active</option>
                      <option value="no">Disabled</option>
                    </select>
                  </Field>
                </div>
                <Field label="Reason for change">
                  <input name="reason" required minLength={10} />
                </Field>
              </ActionForm>
            </section>
          ))}
        </>
      ) : tab === "Corrections" ? (
        <section className="panel panel-body">
          <h2>Correct a record</h2>
          <p>
            Material corrections require a reason and retain before/after
            values. Reports receive an amendment; their original text is
            preserved.
          </p>
          <Field label="Record type">
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setKey("");
              }}
            >
              <option value="asset">Equipment identity</option>
              <option value="customer">Customer</option>
              <option value="report">Service report amendment</option>
            </select>
          </Field>
          <Field label="Record">
            <select value={key} onChange={(e) => setKey(e.target.value)}>
              <option value="">Choose…</option>
              {records.map((r: any) => (
                <option key={r.id} value={r.id}>
                  {r.code || r.name || r.title} · {r.serial || r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </Field>
          {record && (
            <ActionForm
              key={key}
              label="Record correction"
              onSubmit={async (f) => {
                const expected: any = {},
                  changes: any = {};
                for (const field of fields) {
                  const old =
                    (kind === "report" ? record.body[field] : record[field]) ||
                    "";
                  if (f[field] !== old) {
                    expected[field] = old;
                    changes[field] = f[field];
                  }
                }
                await post("/operations/corrections/" + key, {
                  kind,
                  changes,
                  expected,
                  reason: f.reason,
                });
                refresh();
                toast("Correction retained in audit trail.");
              }}
            >
              {fields.map((k) => (
                <Field key={k} label={k.replaceAll("_", " ")}>
                  <input
                    name={k}
                    defaultValue={
                      (kind === "report" ? record.body[k] : record[k]) || ""
                    }
                  />
                </Field>
              ))}
              <Field label="Why is this correction needed?">
                <textarea name="reason" required minLength={10} />
              </Field>
            </ActionForm>
          )}
        </section>
      ) : tab === "Audit trail" ? (
        <section className="panel panel-body">
          <h2>Append-only change history</h2>
          {data.audit.map((a: any) => (
            <details className="audit-row" key={a.id}>
              <summary>
                {date(a.created_at)} · {a.actor} · {a.action}
              </summary>
              <p>{a.reason}</p>
              <pre>
                {JSON.stringify(
                  { record: a.object_id, before: a.before, after: a.after },
                  null,
                  2,
                )}
              </pre>
            </details>
          ))}
        </section>
      ) : (
        <section className="panel panel-body">
          <h2>Model processing and limits</h2>
          <p>
            Database work and approved checklist steps use no model. Generation
            and AI evidence review are separate provider requests. Saving a
            report does not train a model or call AI.
          </p>
          <p>{usage?.notes}</p>
          <div className="form-grid">
            {usage &&
              Object.entries(usage.limits).map(([k, v]) => (
                <div key={k}>
                  <strong>{k.replaceAll("_", " ")}</strong>
                  <p>{String(v)}</p>
                </div>
              ))}
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Operation</th>
                  <th>Status</th>
                  <th>Input tokens</th>
                  <th>Output tokens</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {usage?.records.map((u: any) => (
                  <tr key={u.id}>
                    <td>{date(u.created_at)}</td>
                    <td>{u.operation}</td>
                    <td>{u.status}</td>
                    <td>{u.input_tokens ?? "Unknown"}</td>
                    <td>{u.output_tokens ?? "Unknown"}</td>
                    <td>{u.latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Free Azure web hosting has idle starts and limited capacity.
            PostgreSQL consumes Azure credit. Limits bound model requests; they
            are not a claim about provider billing or remaining Azure credit. No
            paid fallback or new infrastructure is enabled.
          </p>
        </section>
      )}
    </>
  );
}

export function Receipt() {
  const { id } = useParams(),
    { data, error } = useData("/requests/" + id + "/receipt");
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <div className="receipt-page">
      <div className="no-print">
        <PageHeader
          title="Customer receipt & equipment tag"
          actions={
            <button className="button primary" onClick={() => window.print()}>
              Print receipt & tag
            </button>
          }
        />
        <Link to={"/requests/" + id}>Back to request</Link>
      </div>
      <article className="receipt-sheet">
        <img src="/images/lemmer-logo.svg" alt="Lemmer" width="150" />
        <h1>Service intake receipt · Calgary</h1>
        <h2>{data.code}</h2>
        <p>Received {date(data.created_at)}</p>
        <dl>
          <dt>Equipment owner</dt>
          <dd>{data.asset.customer}</dd>
          <dt>Drop-off contact</dt>
          <dd>
            {data.contact.name} · {data.contact.phone}
          </dd>
          <dt>Model / product number</dt>
          <dd>
            {data.asset.model} / {data.asset.product_number || "Unknown"}
          </dd>
          <dt>Asset ID / serial number</dt>
          <dd>
            {data.asset.code} / {data.asset.serial}
          </dd>
          <dt>Customer’s reported problem</dt>
          <dd>{data.description}</dd>
          <dt>Operating condition</dt>
          <dd>{data.operating}</dd>
          <dt>Assigned technician</dt>
          <dd>{data.technician}</dd>
        </dl>
        <p>
          This acknowledges receipt of the service request. It is not a
          quotation, repair approval or diagnosis.
        </p>
      </article>
      <article className="equipment-tag">
        <h2>LEMMER · CALGARY</h2>
        <strong>{data.code}</strong>
        <p>Asset {data.asset.code}</p>
        <p>
          {data.asset.model} · {data.asset.product_number}
        </p>
        <p>Serial: {data.asset.serial}</p>
        <p>Assigned: {data.technician}</p>
      </article>
    </div>
  );
}
