import { ProcedurePanel } from "./operations";
import { PartCandidates } from "./guidance-ui";
import { OriginalPaper } from "./intake";
import { useState, useEffect, useRef, FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Wrench,
  History,
  MapPin,
  Check,
  CheckCheck,
  CheckCircle2,
  CheckSquare2,
  Info,
  FileText,
  BookOpen,
  Sparkles,
  Loader2,
  ShieldCheck,
  ShieldQuestion,
  AlertCircle,
  Package,
  X,
} from "lucide-react";
import { api, post, patch, date, ServiceRequest } from "./api";
import {
  useApp,
  useData,
  PageHeader,
  Loading,
  ErrorBox,
  Badge,
  Field,
  AssetImage,
  IconLabel,
  SourceCard,
} from "./shared";
export function AIResult({ result }: { result: any }) {
  const [view, setView] = useState("Recommendation");
  const rec = result.recommendation;
  return (
    <div className="ai-result">
      <div className={"review-banner " + result.verdict}>
        {result.verdict === "supported" ? (
          <ShieldCheck size={20} />
        ) : (
          <ShieldQuestion size={20} />
        )}
        <div>
          <strong>
            {result.verdict === "supported"
              ? "AI evidence review complete"
              : result.verdict === "needs_information"
                ? "More information would help"
                : "Recommendation withheld"}
          </strong>
          <span>
            {result.verdict === "supported"
              ? "Suggestions are supported by the supplied demo evidence."
              : "The evidence does not yet establish a suitable repair."}
          </span>
        </div>
      </div>
      <div className="ai-tabs">
        {["Recommendation", "Sources", "AI evidence review"].map((t) => (
          <button
            className={view === t ? "active" : ""}
            key={t}
            onClick={() => setView(t)}
          >
            {t}
            {t === "Sources" && <span>{result.evidence.length}</span>}
          </button>
        ))}
      </div>
      {view === "Recommendation" ? (
        <div className="recommendation-body">
          <p className="ai-summary">{rec.summary}</p>
          {rec.procedure_ids?.length > 0 && (
            <p>
              AI found a potentially relevant approved checklist. Review its
              applicability and follow the unchanged steps in Approved
              troubleshooting above; matching wording does not confirm a
              diagnosis.
            </p>
          )}
          {rec.causes?.length > 0 && (
            <>
              <h4>POSSIBLE CAUSES</h4>
              {rec.causes.map((c: any, i: number) => (
                <div className="cause" key={i}>
                  <span className="number-circle">{i + 1}</span>
                  <div>
                    <strong>{c.title}</strong>
                    <p>{c.reason}</p>
                    <div className="citation-chips">
                      {c.source_ids.map((s: string) => (
                        <button key={s} onClick={() => setView("Sources")}>
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </>
          )}
          {rec.checks?.length > 0 && (
            <>
              <h4>SUGGESTED CHECKS</h4>
              {rec.checks.map((c: any, i: number) => (
                <div className="check-row" key={i}>
                  <CheckSquare2 size={17} />
                  <div>
                    <p>{c.text}</p>
                    <div className="citation-chips">
                      {c.source_ids.map((s: string) => (
                        <button key={s} onClick={() => setView("Sources")}>
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </>
          )}
          <PartCandidates candidates={result.part_candidates} />
          {rec.parts?.length > 0 && (
            <>
              <h4>PARTS TO VERIFY</h4>
              <div className="part-chips">
                {rec.parts.map((p: string) => (
                  <span key={p}>
                    <Package size={13} />
                    {p}
                  </span>
                ))}
              </div>
              <small className="muted">
                Candidate components, subject to technician diagnosis and
                variant confirmation.
              </small>
            </>
          )}
          {rec.questions?.length > 0 && (
            <div className="questions-box">
              <h4>BEFORE DECIDING</h4>
              {rec.questions.map((q: string, i: number) => (
                <p key={i}>
                  <span>{i + 1}.</span>
                  {q}
                </p>
              ))}
            </div>
          )}
          <div className="ai-footnote">
            <Info size={14} />
            <span>
              AI assists. The technician confirms the diagnosis and records the
              actual outcome.
            </span>
          </div>
        </div>
      ) : view === "Sources" ? (
        <div className="sources-body">
          <p className="small muted">Supporting records and documents</p>
          {result.evidence.map((s: any) => (
            <SourceCard source={s} key={s.id} />
          ))}
        </div>
      ) : (
        <div className="judge-body">
          <div className="judge-heading">
            <ShieldCheck size={22} />
            <div>
              <strong>A separate model reviewed this draft</strong>
              <span>{result.models.judge}</span>
            </div>
          </div>
          <details>
            <summary>
              {result.verdict === "unsupported"
                ? "Rejected AI content · audit only, not repair instructions"
                : "AI reviewer explanation · not Lemmer human approval"}
            </summary>
            <p>{result.judge.reason}</p>
          </details>
          <p className="small muted">
            Technical evidence, customer privacy and communication quality are
            checked separately. A wording failure blocks customer wording; it
            does not by itself reject supported technical evidence.
          </p>
          {result.judge.checks.map((c: any, i: number) => (
            <div className="judge-check" key={i}>
              {c.status === "pass" ? (
                <CheckCircle2 size={17} className="green" />
              ) : (
                <AlertCircle size={17} className="orange" />
              )}
              <div>
                <strong>
                  {c.criterion === "Parts"
                    ? "Part reference match · not replacement justification"
                    : c.criterion}{" "}
                  · {c.domain || "technical"}
                </strong>
                <details>
                  <summary>
                    {c.status === "fail"
                      ? "Rejected content / failed check · explanation only"
                      : "Review explanation"}
                  </summary>
                  <p>{c.reason}</p>
                </details>
              </div>
              <span className="tag">{c.status}</span>
            </div>
          ))}
          {result.validation_issues.map((s: string) => (
            <ErrorBox key={s} message={s} />
          ))}
          <p className="small muted">
            This checks evidence support and suitability. It is not a guarantee
            of diagnostic accuracy.
          </p>
          <div className="model-meta">
            <span>Generator: {result.models.generator}</span>
            <span>
              Prompt v{result.prompt_version} ·{" "}
              {(result.duration_ms / 1000).toFixed(1)}s
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
export function ServiceWorkspace() {
  const { id } = useParams();
  const { session, refresh, toast } = useApp();
  const { data, error, setData } = useData("/requests/" + id);
  const [tab, setTab] = useState("AI assistance"),
    [problem, setProblem] = useState(""),
    [result, setResult] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [aiError, setAiError] = useState(""),
    [progress, setProgress] = useState(0);
  const [guidance, setGuidance] = useState<any>(null);
  const [refining, setRefining] = useState(false);
  const [form, setForm] = useState<any>({
    diagnosis: "",
    work: "",
    parts: [],
    parts_replaced: false,
    test: "",
    outcome: "",
    notes: "",
    inspection_date: new Date().toISOString().slice(0, 10),
    close_request: false,
    part_lines: [],
  });
  const [dirty, setDirty] = useState(false),
    [saveState, setSaveState] = useState(""),
    [finalizing, setFinalizing] = useState(false),
    [reportError, setReportError] = useState("");
  const editVersion = useRef(0),
    saving = useRef(false);
  const init = useRef(""),
    subId = useRef(crypto.randomUUID());
  const reportRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (data && init.current !== id) {
      init.current = id || "";
      setProblem(data.request.description);
      setForm((f: any) => ({
        ...f,
        ...data.request.draft,
        close_request: false,
      }));
      const last = data.runs.find(
        (r: any) => r.result.recommendation && r.mode === "C",
      );
      setResult(last?.result || null);
    }
  }, [data, id]);
  useEffect(() => {
    if (!id || !["technician", "superuser"].includes(session.role)) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api("/requests/" + id + "/guidance");
        if (stopped) return;
        setGuidance(next.guidance);
        if (next.result) setResult(next.result);
        if (
          ["ready", "unavailable", "procedure", "completed"].includes(
            next.guidance?.status,
          )
        )
          return;
      } catch {
        if (!stopped)
          setGuidance({
            status: "queued",
            message: "Reconnecting to guidance preparation…",
          });
      }
      if (!stopped) timer = setTimeout(poll, 3000);
    }
    post("/requests/" + id + "/guidance")
      .then(() => {
        if (!stopped) poll();
      })
      .catch((e) => {
        if (!stopped)
          setGuidance({ status: "unavailable", message: e.message });
      });
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id, session.role]);
  useEffect(() => {
    if (!busy) return;
    setProgress(0);
    const t = setInterval(() => setProgress((p) => Math.min(p + 1, 2)), 6500);
    return () => clearInterval(t);
  }, [busy]);
  useEffect(() => {
    if (!dirty || !data || saving.current) return;
    const t = setTimeout(async () => {
      saving.current = true;
      const snapshot = editVersion.current;
      setSaveState("Saving…");
      try {
        const r = await patch("/requests/" + id, {
          draft: form,
          version: data.request.version,
        });
        setData((d: any) => ({ ...d, request: r }));
        if (snapshot === editVersion.current) {
          setDirty(false);
          setSaveState("Draft saved");
        } else {
          setSaveState("Unsaved changes");
        }
        setReportError("");
      } catch (e: any) {
        setSaveState("Save failed");
        setReportError(e.message);
      } finally {
        saving.current = false;
      }
    }, 1200);
    return () => clearTimeout(t);
  }, [form, dirty, data?.request.version, id]);
  useEffect(() => {
    const f = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", f);
    return () => window.removeEventListener("beforeunload", f);
  }, [dirty]);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const r: ServiceRequest = data.request;
  const update = async (body: any) => {
    try {
      const next = await patch("/requests/" + id, {
        ...body,
        version: r.version,
      });
      setData({ ...data, request: next });
      toast("Request updated.");
    } catch (e: any) {
      toast(e.message);
    }
  };
  const change = (k: string, v: any) => {
    editVersion.current += 1;
    setForm((f: any) => ({ ...f, [k]: v }));
    setDirty(true);
    setSaveState("Unsaved changes");
  };
  async function runAI() {
    setBusy(true);
    setAiError("");
    try {
      setResult(
        await post("/requests/" + id + "/recommend", { problem, mode: "C" }),
      );
      toast(
        "AI evidence review complete. Technician confirmation is still required.",
      );
      const fresh = await api("/requests/" + id);
      setData(fresh);
    } catch (e: any) {
      setAiError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function finalize(e: FormEvent) {
    e.preventDefault();
    if (dirty || saveState === "Saving…") {
      setReportError("Please wait for the draft to finish saving.");
      return;
    }
    setFinalizing(true);
    setReportError("");
    try {
      await post("/requests/" + id + "/reports", {
        ...form,
        part_lines: form.parts.map(
          (part: string) =>
            form.part_lines?.find((x: any) => x.part === part) || {
              part,
              quantity: 1,
              action: form.parts_replaced ? "Replaced" : "Used",
            },
        ),
        version: r.version,
        submission_id: subId.current,
      });
      subId.current = crypto.randomUUID();
      setDirty(false);
      toast(
        "Service report recorded. Reusable knowledge requires human approval.",
      );
      refresh();
    } catch (e: any) {
      setReportError(e.message);
    } finally {
      setFinalizing(false);
    }
  }
  return (
    <>
      <Link to="/requests" className="back-link">
        <ArrowLeft size={15} />
        All service requests
      </Link>
      <PageHeader
        eyebrow={r.code + " / SERVICE WORKSPACE"}
        title={r.title}
        subtitle={`${r.asset.customer} · Received ${date(r.created_at)}`}
        actions={
          <>
            <Badge value={r.status} />
            {session.role === "reception" ? (
              <Link to="/reception" className="button primary">
                Back to reception <ArrowRight size={16} />
              </Link>
            ) : (
              <button
                className="button primary"
                onClick={() =>
                  reportRef.current?.scrollIntoView({ behavior: "smooth" })
                }
              >
                <Wrench size={16} />
                Record service
              </button>
            )}
          </>
        }
      />
      <div className="workspace-asset-strip">
        <AssetImage asset={r.asset} />
        <div>
          <Link to={"/assets/" + r.asset.id}>
            {r.asset.model} · Product {r.asset.product_number || "unknown"}{" "}
            <ArrowUpRight size={13} />
          </Link>
          <span>
            {r.asset.code} <b>·</b> {r.asset.serial}
          </span>
        </div>
        <div className="strip-spacer" />
        <IconLabel icon={MapPin}>{r.asset.location}</IconLabel>
        <Link to={"/assets/" + r.asset.id} className="text-link">
          Open passport <ArrowRight size={15} />
        </Link>
      </div>
      <div className="service-layout">
        <div className="service-left">
          {(data.request.documents || []).map((d: any) => (
            <section className="panel" key={d.id}>
              <div className="panel-header">
                <h2>
                  <FileText size={17} />
                  Original service paper
                </h2>
                <span className="tag">FROM RECEPTION</span>
              </div>
              <OriginalPaper document={d} />
              {["reception", "superuser"].includes(session.role) && (
                <button
                  className="text-link panel-body"
                  onClick={async () => {
                    try {
                      await post("/intake/documents/" + d.id + "/share", {
                        reviewed_for_customer: true,
                      });
                      toast("Document released to this equipment owner.");
                    } catch (e: any) {
                      toast(e.message);
                    }
                  }}
                >
                  I reviewed this document for the owner · release to their
                  passport
                </button>
              )}
            </section>
          ))}
          {data.events
            .filter((e: any) => e.kind === "intake" && e.request_id === r.id)
            .map((e: any) => (
              <section className="panel" key={e.id}>
                <div className="panel-header">
                  <h2>Reception handoff</h2>
                </div>
                <div className="panel-body">
                  <p>{e.title}</p>
                  <p>
                    Owner: {e.body.owner || r.asset.customer} · Drop-off role:{" "}
                    {e.body.dropoff_role || "Not specified"}
                  </p>
                  <p>Accessories: {e.body.accessories || "Not recorded"}</p>
                  <p>
                    Visible damage: {e.body.visible_damage || "Not assessed"}
                  </p>
                  <p>
                    Customer instructions:{" "}
                    {e.body.customer_instructions || "Not recorded"}
                  </p>
                  <p className="muted">
                    {e.body.notes || "No additional reception notes."}
                  </p>
                  <span className="small muted">
                    Reviewed by {e.actor} · {date(e.created_at)}
                  </span>
                  <div className="problem-meta">
                    <div>
                      <span>Contact</span>
                      <strong>{r.contact.name}</strong>
                    </div>
                    <div>
                      <span>Phone</span>
                      <strong>{r.contact.phone || "Not provided"}</strong>
                    </div>
                  </div>
                  {r.contact.email && (
                    <p className="small muted">{r.contact.email}</p>
                  )}
                </div>
              </section>
            ))}
          <section className="panel">
            <div className="panel-header">
              <h2>Reported problem</h2>
              <span className={"priority " + r.priority.toLowerCase()}>
                <i />
                {r.priority}
              </span>
            </div>
            <div className="panel-body">
              <p className="problem-description">{r.description}</p>
              <div className="problem-meta">
                <div>
                  <span>Issue category</span>
                  <strong>{r.category}</strong>
                </div>
                <div>
                  <span>Can operate?</span>
                  <strong>{r.operating}</strong>
                </div>
              </div>
              <div className="form-grid compact-fields">
                <Field label="Request status">
                  <select
                    disabled={dirty || saveState === "Saving…"}
                    value={r.status}
                    onChange={(e) => update({ status: e.target.value })}
                  >
                    {[
                      "New",
                      "In progress",
                      "Awaiting diagnosis",
                      "Awaiting approval",
                      "Awaiting parts",
                      "Awaiting customer",
                      ...(r.status === "Closed" ? ["Closed"] : []),
                    ].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Assigned technician">
                  <select
                    disabled={dirty || saveState === "Saving…"}
                    value={r.technician}
                    onChange={(e) => update({ technician: e.target.value })}
                  >
                    <option>Unassigned</option>
                    {session.technicians.map((t: string) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                </Field>
              </div>
            </div>
          </section>
          <Link
            className="button secondary"
            to={"/requests/" + id + "/receipt"}
          >
            Print customer receipt & equipment tag
          </Link>
          <section className="panel history-panel">
            <div className="panel-header">
              <h2>
                <History size={17} />
                This asset’s history
              </h2>
              <span className="count">
                {data.events.filter((e: any) => e.kind === "service").length}
              </span>
            </div>
            <div className="mini-history">
              {data.events
                .filter((e: any) => e.kind === "service")
                .slice(0, 4)
                .map((e: any) => (
                  <div key={e.id}>
                    <div>
                      <span className="history-dot" />
                      <time>{date(e.created_at)}</time>
                    </div>
                    <strong>{e.title}</strong>
                    <p>{e.body.work}</p>
                    <small>{e.actor}</small>
                  </div>
                ))}
            </div>
            <Link className="panel-bottom-link" to={"/assets/" + r.asset.id}>
              View complete history <ArrowUpRight size={15} />
            </Link>
          </section>
          {session.role !== "reception" && (
            <section className="panel report-panel" ref={reportRef}>
              <div className="panel-header">
                <h2>
                  <Wrench size={18} />
                  Confirmed technician findings
                </h2>
                <span className="save-state">
                  {saveState === "Draft saved" && <Check size={13} />}{" "}
                  {saveState}
                </span>
              </div>
              {r.status === "Closed" ? (
                <div className="closed-report">
                  <CheckCircle2 size={35} />
                  <h3>Service report recorded</h3>
                  <p>
                    The outcome is saved to {r.asset.code} and available for
                    future retrieval.
                  </p>
                  <Link
                    to={"/assets/" + r.asset.id}
                    className="button secondary"
                  >
                    View updated passport <ArrowRight size={15} />
                  </Link>
                  <button
                    className="text-link"
                    onClick={() => update({ status: "In progress" })}
                  >
                    Reopen this request
                  </button>
                </div>
              ) : (
                <form className="panel-body" onSubmit={finalize}>
                  <div className="report-intro">
                    <Info size={15} />
                    <span>
                      Record what you actually found and did. It stays in this
                      asset’s history. Shared procedures require a separate
                      human review.
                    </span>
                  </div>
                  <Field label="Inspection date">
                    <input
                      type="date"
                      value={form.inspection_date}
                      onChange={(e) =>
                        change("inspection_date", e.target.value)
                      }
                      required
                      max={new Date().toISOString().slice(0, 10)}
                    />
                  </Field>
                  <Field label="Actual diagnosis">
                    <textarea
                      value={form.diagnosis}
                      onChange={(e) => change("diagnosis", e.target.value)}
                      required
                      minLength={5}
                      rows={2}
                      placeholder="What did you confirm?"
                    />
                  </Field>
                  <Field label="Work performed">
                    <textarea
                      value={form.work}
                      onChange={(e) => change("work", e.target.value)}
                      required
                      minLength={5}
                      rows={3}
                      placeholder="Describe the repair or investigation…"
                    />
                  </Field>
                  {Object.keys(data.parts).length === 0 && (
                    <Field label="Parts used · technician-entered reference">
                      <input
                        aria-label="Manually recorded parts"
                        placeholder="Part number or name; separate entries with commas"
                        onBlur={(e) =>
                          change(
                            "parts",
                            e.target.value
                              .split(",")
                              .map((x) => x.trim())
                              .filter(Boolean),
                          )
                        }
                        defaultValue={form.parts.join(", ")}
                      />
                      <small>
                        No verified manufacturer parts reference is loaded for
                        this equipment. Record the actual parts used.
                      </small>
                    </Field>
                  )}
                  <Field label="Parts used (optional)">
                    <select
                      value=""
                      onChange={(e) => {
                        if (
                          e.target.value &&
                          !form.parts.includes(e.target.value)
                        )
                          change("parts", [...form.parts, e.target.value]);
                      }}
                    >
                      <option value="">Add a verified part…</option>
                      {Object.entries(data.parts).map(([p, n]) => (
                        <option key={p} value={p}>
                          {p} — {String(n)}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <div className="part-chips removable">
                    {form.parts.map((p: string) => (
                      <button
                        type="button"
                        key={p}
                        onClick={() =>
                          change(
                            "parts",
                            form.parts.filter((x: string) => x !== p),
                          )
                        }
                      >
                        {p}
                        <X size={12} />
                      </button>
                    ))}
                  </div>
                  {form.parts.length > 0 && (
                    <label className="checkbox-field">
                      <input
                        type="checkbox"
                        checked={!!form.parts_replaced}
                        onChange={(e) =>
                          change("parts_replaced", e.target.checked)
                        }
                      />
                      <span>
                        These parts were installed or replaced during this
                        service. Update their installation dates.
                      </span>
                    </label>
                  )}
                  {form.parts.map((part: string) => (
                    <div className="part-line-grid" key={part}>
                      <strong>{part}</strong>
                      <Field label="Quantity">
                        <input
                          type="number"
                          min={1}
                          max={1000}
                          required
                          value={
                            form.part_lines?.find((x: any) => x.part === part)
                              ?.quantity ?? 1
                          }
                          onChange={(e) =>
                            change("part_lines", [
                              ...(form.part_lines || []).filter(
                                (x: any) => x.part !== part,
                              ),
                              {
                                part,
                                quantity: Number(e.target.value),
                                action:
                                  form.part_lines?.find(
                                    (x: any) => x.part === part,
                                  )?.action || "Used",
                              },
                            ])
                          }
                        />
                      </Field>
                      <Field label="Action">
                        <select
                          value={
                            form.part_lines?.find((x: any) => x.part === part)
                              ?.action || "Used"
                          }
                          onChange={(e) =>
                            change("part_lines", [
                              ...(form.part_lines || []).filter(
                                (x: any) => x.part !== part,
                              ),
                              {
                                part,
                                quantity:
                                  form.part_lines?.find(
                                    (x: any) => x.part === part,
                                  )?.quantity || 1,
                                action: e.target.value,
                              },
                            ])
                          }
                        >
                          <option>Used</option>
                          <option>Replaced</option>
                          <option>Requested</option>
                        </select>
                      </Field>
                    </div>
                  ))}
                  <Field label="Test performed & result">
                    <textarea
                      value={form.test}
                      onChange={(e) => change("test", e.target.value)}
                      required
                      minLength={5}
                      rows={2}
                      placeholder="How was the outcome verified?"
                    />
                  </Field>
                  <Field label="Final outcome">
                    <select
                      required
                      value={form.outcome}
                      onChange={(e) => change("outcome", e.target.value)}
                    >
                      <option value="" disabled>
                        Select the actual outcome…
                      </option>
                      {[
                        "Repaired",
                        "Partially repaired",
                        "Unresolved",
                        "Not repaired",
                        "No fault found",
                      ].map((o) => (
                        <option key={o}>{o}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Additional notes (optional)">
                    <textarea
                      value={form.notes}
                      onChange={(e) => change("notes", e.target.value)}
                      rows={2}
                    />
                  </Field>
                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={form.close_request}
                      onChange={(e) =>
                        change("close_request", e.target.checked)
                      }
                    />
                    Close this request after recording the report
                  </label>
                  {reportError && <ErrorBox message={reportError} />}
                  <button
                    className="button primary full"
                    disabled={finalizing || dirty || saveState === "Saving…"}
                  >
                    {finalizing ? (
                      <Loader2 size={17} className="spin" />
                    ) : (
                      <CheckCheck size={17} />
                    )}
                    Finalize service report
                  </button>
                  <p className="small muted centered">
                    Recorded as {session.technician} · Linked to {r.asset.code}
                  </p>
                </form>
              )}
            </section>
          )}
        </div>
        {session.role !== "reception" ? (
          <section className="panel intelligence-panel">
            <ProcedurePanel requestId={r.id} />
            <div className="intelligence-header">
              <div className="sparkle-tile">
                <Sparkles size={23} />
              </div>
              <div>
                <h2>Service intelligence</h2>
                <p>Product knowledge. Past repairs. This asset’s story.</p>
              </div>
              <span className="ai-label">AI ASSISTED</span>
            </div>
            <div className="tabs">
              <button
                className={tab === "AI assistance" ? "active" : ""}
                onClick={() => setTab("AI assistance")}
              >
                AI assistance
              </button>
              <button
                className={tab === "Related cases" ? "active" : ""}
                onClick={() => setTab("Related cases")}
              >
                Related cases
              </button>
            </div>
            {tab === "Related cases" ? (
              <RelatedCases model={r.asset.product_number || r.asset.model} />
            ) : (
              <>
                <div
                  className="panel-body auto-guidance-note"
                  role="status"
                  aria-live="polite"
                >
                  <ShieldCheck size={19} />
                  <div>
                    <strong>
                      {guidance?.status === "procedure"
                        ? "Approved checklist available above"
                        : guidance?.status === "completed"
                          ? "Service recorded"
                          : result
                            ? "Guidance delivered with this request"
                            : guidance?.status === "unavailable"
                              ? "Guidance unavailable"
                              : "Preparing guidance automatically"}
                    </strong>
                    <p className="small muted">
                      {guidance?.status === "procedure"
                        ? guidance.message
                        : guidance?.status === "completed"
                          ? guidance.message
                          : result
                            ? "Based on the reported problem, product documents and service history. Reviewed by a separate model; confirm findings before repair."
                            : guidance?.status === "unavailable"
                              ? guidance.message
                              : guidance?.message?.includes("Retrying")
                                ? guidance.message
                                : "The report is ready to read. Guidance will appear here after the evidence review—no action needed."}
                    </p>
                  </div>
                  {!result &&
                    !["unavailable", "procedure", "completed"].includes(
                      guidance?.status,
                    ) && <Loader2 className="spin" size={18} />}
                </div>
                {(result ||
                  ["unavailable", "procedure"].includes(guidance?.status)) && (
                  <button
                    className="text-link guidance-refine"
                    onClick={() => setRefining(!refining)}
                  >
                    {refining
                      ? "Close additional question"
                      : result
                        ? "Add findings or ask a follow-up"
                        : "Retry guidance"}
                  </button>
                )}
                {refining && (
                  <div className="ai-input-area">
                    <label htmlFor="problem">
                      What would you like help troubleshooting?
                    </label>
                    <textarea
                      id="problem"
                      value={problem}
                      onChange={(e) => setProblem(e.target.value)}
                      rows={3}
                      maxLength={4000}
                    />
                    <div className="context-pills">
                      <span>
                        <FileText size={13} />
                        Product documents
                      </span>
                      <span>
                        <BookOpen size={13} />
                        Repair cases
                      </span>
                      <span>
                        <History size={13} />
                        Asset history
                      </span>
                    </div>
                    <button
                      className="button dark full"
                      disabled={
                        busy ||
                        problem.length < 10 ||
                        ["queued", "running"].includes(guidance?.status)
                      }
                      onClick={runAI}
                    >
                      {busy ? (
                        <Loader2 size={17} className="spin" />
                      ) : (
                        <Sparkles size={17} />
                      )}{" "}
                      {busy
                        ? "Reviewing the evidence…"
                        : result
                          ? "Review updated findings"
                          : "Retry guidance"}
                    </button>
                  </div>
                )}
                {busy && (
                  <div className="ai-progress">
                    <div className="progress-orb">
                      <Sparkles size={23} />
                    </div>
                    <h3>
                      {
                        [
                          "Finding relevant service knowledge",
                          "Preparing possible causes and checks",
                          "Checking evidence with a separate model",
                        ][progress]
                      }
                    </h3>
                    <p>Your result will appear after the evidence review.</p>
                    <div className="progress-stages">
                      {["Retrieve", "Recommend", "Review"].map((s, i) => (
                        <span className={i <= progress ? "active" : ""} key={s}>
                          {i < progress ? <Check size={13} /> : <i />}
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {aiError && (
                  <div className="panel-body">
                    <ErrorBox message={aiError} />
                  </div>
                )}
                {!busy && result && <AIResult result={result} />}
                <details className="panel-body assessment-log">
                  <summary>
                    Previous AI assessments ({data.runs.length})
                  </summary>
                  {data.runs.map((run: any) => (
                    <details key={run.id}>
                      <summary>
                        {new Date(run.created_at).toLocaleString()} ·{" "}
                        {run.result.verdict ||
                          run.result.status ||
                          "Unavailable"}
                      </summary>
                      <p>
                        <strong>Input:</strong>{" "}
                        {run.result.problem || "Original request"}
                      </p>
                      {run.result.recommendation ? (
                        <AIResult result={run.result} />
                      ) : (
                        <p>{run.result.error || "Assessment not released."}</p>
                      )}
                    </details>
                  ))}
                </details>
              </>
            )}
          </section>
        ) : (
          <section className="panel reception-status-card">
            <CheckCircle2 size={35} />
            <h2>With the service team</h2>
            <p>
              Assigned to <strong>{r.technician}</strong>. The technician can
              read your notes and original scan here, then record the actual
              diagnosis and repair.
            </p>
            <Badge value={r.status} />
            <Link to="/reception" className="button secondary">
              Back to reception <ArrowRight size={16} />
            </Link>
          </section>
        )}
      </div>
    </>
  );
}
function RelatedCases({ model }: { model: string }) {
  const { data, error } = useData("/knowledge");
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <div className="sources-body">
      <p className="small muted">
        Model-matched cases. These are synthetic demo records, not confirmed
        diagnoses for the current request.
      </p>
      {data.cases
        .filter((c: any) => (c.product_number || c.model) === model)
        .map((c: any) => (
          <SourceCard
            key={c.id}
            source={{
              id: c.code,
              kind: "case",
              title: c.symptom,
              outcome: c.outcome,
              source: c.source,
              content: `Diagnosis: ${c.diagnosis}\nWork: ${c.repair}\nTest: ${c.test}\nOutcome: ${c.outcome}`,
            }}
          />
        ))}
    </div>
  );
}
