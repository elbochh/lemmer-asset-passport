import { useState, useRef, useEffect, FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ScanLine,
  Upload,
  FileText,
  ArrowRight,
  CheckCircle2,
  Send,
  Loader2,
  Info,
  ClipboardList,
  User,
  RefreshCw,
  Plus,
  ExternalLink,
} from "lucide-react";
import { api, post, Asset, ServiceRequest, date } from "./api";
import {
  useApp,
  useData,
  PageHeader,
  Field,
  ErrorBox,
  Loading,
  Empty,
  Badge,
  Modal,
} from "./shared";
import { RequestTable } from "./dashboard";

async function readablePhoto(file: File): Promise<File> {
  if (!["image/jpeg", "image/png"].includes(file.type)) return file;
  const bitmap = await createImageBitmap(file);
  try {
    if (file.size <= 2500000 && bitmap.width * bitmap.height <= 16000000)
      return file;
    const scale = Math.min(1, 2200 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw Error("Could not resize this photo.");
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(Error("Could not prepare photo."))),
        "image/jpeg",
        0.88,
      ),
    );
    return new File(
      [blob],
      file.name.replace(/\.[^.]+$/, "") + "-resized.jpg",
      { type: "image/jpeg" },
    );
  } finally {
    bitmap.close();
  }
}

export function OriginalPaper({ document }: { document: any }) {
  return (
    <div className="original-paper">
      <div className="paper-toolbar">
        <span>
          <FileText size={16} />
          {document.filename}
        </span>
        <a
          className="text-link"
          href={document.url}
          target="_blank"
          rel="noreferrer"
        >
          Open original <ExternalLink size={14} />
        </a>
      </div>
      {document.content_type.startsWith("image/") ? (
        <a href={document.url} target="_blank" rel="noreferrer">
          <img src={document.url} alt="Original scanned service intake paper" />
        </a>
      ) : (
        <a
          className="pdf-preview"
          href={document.url}
          target="_blank"
          rel="noreferrer"
        >
          <FileText size={48} />
          <strong>Original PDF service paper</strong>
          <span>Open the full document in a new tab</span>
        </a>
      )}
    </div>
  );
}

export function Reception() {
  const navigate = useNavigate();
  const { session, setSession, refresh, toast } = useApp();
  const { data, error } = useData("/dashboard");
  const [document, setDocument] = useState<any>(null),
    [reading, setReading] = useState(false),
    [saving, setSaving] = useState(false),
    [issue, setIssue] = useState(""),
    [notice, setNotice] = useState(""),
    [reviewed, setReviewed] = useState(false),
    [sent, setSent] = useState<any>(null),
    [assetModal, setAssetModal] = useState(false);
  const token = useRef(crypto.randomUUID());
  const input = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<any>({
    asset_id: "",
    name: "",
    email: "",
    phone: "",
    title: "",
    description: "",
    category: "General service",
    priority: "Normal",
    operating: "Unknown / Not assessed",
    technician: "Unassigned",
    accessories: "",
    visible_damage: "",
    customer_instructions: "",
    dropoff_role: "",
    photo_ids: [],
    acknowledge_open: false,
    intake_notes: "",
  });
  const change = (k: string, v: any) => {
    setForm((f: any) => ({ ...f, [k]: v }));
    setReviewed(false);
  };
  async function upload(file: File) {
    setReading(true);
    setIssue("");
    setNotice("");
    setSent(null);
    try {
      file = await readablePhoto(file);
      if (file.size > 2500000)
        throw Error("Please use a scan smaller than 2.5 MB.");
      const body = new FormData();
      body.append("file", file);
      const res = await fetch("/api/intake/documents", {
        method: "POST",
        body,
        credentials: "same-origin",
      });
      const d = await res.json();
      if (!res.ok) throw Error(d.detail || "The scan could not be uploaded.");
      setDocument(d);
      const facts = d.extracted || {};
      const matches = data.assets.filter(
        (a: Asset) =>
          Boolean(facts.serial || facts.asset_code) &&
          (!facts.serial ||
            a.serial.toLowerCase() === facts.serial.trim().toLowerCase()) &&
          (!facts.asset_code ||
            a.code.toLowerCase() === facts.asset_code.trim().toLowerCase()),
      );
      const match = matches.length === 1 ? matches[0] : null;
      setForm((f: any) => ({
        ...f,
        asset_id: match?.id || "",
        name: facts.contact_name || "",
        email: facts.email || "",
        phone: facts.phone || "",
        title: (facts.problem || "").split(/[.!?]\s|\n/)[0].slice(0, 100),
        description: facts.problem || "",
        intake_notes: facts.notes || "",
        operating: ["No", "Yes", "Intermittently"].includes(facts.operating)
          ? facts.operating
          : "Unknown / Not assessed",
        technician: session.technicians.includes(facts.technician)
          ? facts.technician
          : "Unassigned",
      }));
      setReviewed(false);
      setNotice(
        d.extraction_error ||
          "Paper read. Check the extracted details against the original before sending.",
      );
    } catch (e: any) {
      setIssue(e.message);
    } finally {
      setReading(false);
    }
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setIssue("");
    try {
      const result = await post("/intake/handoff", {
        ...form,
        document_id: document?.id || null,
        reviewed,
        submission_id: token.current,
      });
      setSent(result);
      refresh();
      toast("Handoff delivered to " + result.technician + "’s work queue.");
    } catch (e: any) {
      setIssue(e.message);
    } finally {
      setSaving(false);
    }
  }
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  if (!["reception", "superuser"].includes(session.role))
    return (
      <>
        <PageHeader
          title="Reception desk"
          subtitle="Turn a customer’s paper into a clear, assigned service request."
        />
        <section className="panel reception-intro">
          <ScanLine size={40} />
          <h2>Try the reception workflow</h2>
          <p>
            Scan a service paper, check its details, and deliver it with the
            original to a technician’s queue.
          </p>
          <button
            className="button primary"
            onClick={async () => {
              setSession(
                await post("/session/technician", { name: "Taylor Brooks" }),
              );
              refresh();
            }}
          >
            Switch to Taylor · Reception <ArrowRight size={16} />
          </button>
          <p className="small muted">
            Demo identity switch. Named employee sign-in will be added for
            production.
          </p>
        </section>
      </>
    );
  const openRequests = data.requests.filter(
    (r: ServiceRequest) =>
      r.asset_id === form.asset_id && r.status !== "Closed",
  );
  const selected = data.assets.find((a: Asset) => a.id === form.asset_id);
  return (
    <>
      <PageHeader
        eyebrow="FROM FRONT DESK TO WORKSHOP"
        title="Reception desk"
        subtitle="Capture it once. Give the technician the whole story."
        actions={
          <Link to="/requests" className="button secondary">
            View all requests <ArrowRight size={16} />
          </Link>
        }
      />
      <div className="intake-steps">
        <span className={!document ? "active" : ""}>
          <b>1</b>Scan or enter
        </span>
        <i />
        <span className={document && !sent ? "active" : ""}>
          <b>2</b>Review details
        </span>
        <i />
        <span className={sent ? "active" : ""}>
          <b>3</b>Send to technician
        </span>
      </div>
      {sent ? (
        <section className="panel handoff-confirmation">
          <div className="success-orb">
            <CheckCircle2 size={34} />
          </div>
          <span className="eyebrow">HANDOFF COMPLETE</span>
          <h2>Ready for {sent.technician.split(" ")[0]}.</h2>
          <p>
            <strong>{sent.code}</strong> is now in {sent.technician}’s work
            queue.{" "}
            {sent.documents.length
              ? "The original paper travels with the request. AI guidance is preparing automatically and will appear in the technician’s workspace after review."
              : "All reviewed details are included."}
          </p>
          <div className="handoff-summary">
            <div>
              <span>Equipment</span>
              <strong>
                {sent.asset.code} · {sent.asset.model}
              </strong>
            </div>
            <div>
              <span>Reported problem</span>
              <strong>{sent.title}</strong>
            </div>
            <div>
              <span>Assigned to</span>
              <strong>{sent.technician}</strong>
            </div>
          </div>
          <div className="heading-actions">
            {session.demo && sent.technician !== "Unassigned" && (
              <button
                className="button primary"
                onClick={async () => {
                  setSession(
                    await post("/session/technician", {
                      name: sent.technician,
                    }),
                  );
                  refresh();
                  navigate("/my-work");
                }}
              >
                See the technician’s view <ArrowRight size={16} />
              </button>
            )}
            <Link
              className="button secondary"
              to={"/requests/" + sent.id + "/receipt"}
            >
              Print receipt & equipment tag
            </Link>
            <Link className="button secondary" to={"/requests/" + sent.id}>
              Open request
            </Link>
            <button
              className="button secondary"
              onClick={() => {
                setSent(null);
                setDocument(null);
                setForm({
                  asset_id: "",
                  name: "",
                  email: "",
                  phone: "",
                  title: "",
                  description: "",
                  category: "General service",
                  priority: "Normal",
                  operating: "Unknown / Not assessed",
                  technician: "Unassigned",
                  accessories: "",
                  visible_damage: "",
                  customer_instructions: "",
                  dropoff_role: "",
                  photo_ids: [],
                  acknowledge_open: false,
                  intake_notes: "",
                });
                setReviewed(false);
                setNotice("");
                token.current = crypto.randomUUID();
              }}
            >
              Next customer <Plus size={16} />
            </button>
          </div>
        </section>
      ) : (
        <div className="intake-grid">
          <section className="panel intake-paper-panel">
            <div className="panel-header">
              <h2>
                <ScanLine size={19} />
                Customer’s service paper
              </h2>
              <span className="tag">OPTIONAL</span>
            </div>
            <div className="panel-body">
              {document ? (
                <>
                  <OriginalPaper document={document} />
                  <button
                    className="text-link change-scan"
                    disabled={reading}
                    onClick={() => input.current?.click()}
                  >
                    Use a different scan
                  </button>
                </>
              ) : (
                <div
                  className="scan-dropzone"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const f = e.dataTransfer.files[0];
                    if (f && !reading) upload(f);
                  }}
                >
                  <span className="scan-icon">
                    <ScanLine size={32} />
                  </span>
                  <h3>Paper in. Details filled.</h3>
                  <p>
                    Upload a scan or take a clear photo of the service paper.
                    We’ll read the details for you to check.
                  </p>
                  <button
                    className="button primary"
                    disabled={reading}
                    onClick={() => input.current?.click()}
                  >
                    <Upload size={16} />
                    Choose a scan or photo
                  </button>
                  <small>
                    JPG, PNG or PDF · PDF: up to 2.5 MB / 5 pages. Large photos
                    are resized before upload; check their readability.
                  </small>
                </div>
              )}
              <input
                ref={input}
                type="file"
                accept="image/jpeg,image/png,application/pdf"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload(f);
                  e.target.value = "";
                }}
              />
              {reading && (
                <div className="scan-progress" role="status">
                  <Loader2 size={21} className="spin" />
                  <div>
                    <strong>Reading the service paper…</strong>
                    <span>The original will stay with the request.</span>
                  </div>
                </div>
              )}
              <div className="sample-paper-box">
                <FileText size={22} />
                <div>
                  <strong>No paper handy?</strong>
                  <p>Try a fictional intake form to see the workflow.</p>
                  <button
                    className="text-link"
                    disabled={reading}
                    onClick={async () => {
                      const b = await (
                        await fetch("/images/demo-rustproofing-intake.pdf")
                      ).blob();
                      await upload(
                        new File([b], "sample-rustproofing-intake.pdf", {
                          type: "application/pdf",
                        }),
                      );
                    }}
                  >
                    Try sample paper <ArrowRight size={14} />
                  </button>
                </div>
              </div>
              <div className="note-box">
                <Info size={17} />
                <p>
                  Already talking to the customer? Enter the details directly on
                  the right and skip the paper. Use fictional data in this
                  public demo.
                </p>
              </div>
              {document?.extracted && (
                <div className="extracted-identity">
                  <h4>READ FROM THE PAPER</h4>
                  {["customer", "model", "serial", "asset_code"].map((k) => (
                    <div key={k}>
                      <span>{k.replace("_", " ")}</span>
                      <strong>{document.extracted[k] || "Not found"}</strong>
                    </div>
                  ))}
                  {document.extracted.uncertain_fields?.length > 0 && (
                    <p>
                      Check carefully:{" "}
                      {document.extracted.uncertain_fields.join(", ")}.
                    </p>
                  )}
                </div>
              )}
            </div>
          </section>
          <section className="panel intake-form-panel">
            <div className="panel-header">
              <h2>
                <ClipboardList size={19} />
                Review & assign
              </h2>
              <span className="small muted">You stay in control</span>
            </div>
            <form className="panel-body" onSubmit={submit}>
              {notice && (
                <div className="note-box">
                  <Info size={17} />
                  <p>{notice}</p>
                </div>
              )}
              {issue && <ErrorBox message={issue} />}
              <fieldset disabled={reading || saving}>
                <div className="form-section-title">
                  <span>01</span>Identify the equipment
                </div>
                <Field
                  label="Asset passport"
                  hint="Match the asset ID or serial. A model name alone cannot identify an individual machine."
                >
                  <select
                    value={form.asset_id}
                    onChange={(e) => {
                      change("asset_id", e.target.value);
                      change("acknowledge_open", false);
                    }}
                    required
                  >
                    <option value="">Select the correct equipment…</option>
                    {data.assets.map((a: Asset) => (
                      <option key={a.id} value={a.id}>
                        {a.code} · {a.model} · {a.serial}
                      </option>
                    ))}
                  </select>
                </Field>
                {selected && (
                  <div className="matched-asset">
                    <CheckCircle2 size={17} />
                    <div>
                      <strong>{selected.customer}</strong>
                      <span>
                        {selected.serial} · {selected.location}
                      </span>
                    </div>
                  </div>
                )}
                <button
                  type="button"
                  className="text-link"
                  onClick={() => navigate("/registry")}
                >
                  <Plus size={14} />
                  Register new equipment
                </button>
                <div className="form-section-title">
                  <span>02</span>Confirm customer & problem
                </div>
                <div className="form-grid">
                  <Field label="Person dropping off equipment">
                    <input
                      required
                      minLength={2}
                      maxLength={100}
                      value={form.name}
                      onChange={(e) => change("name", e.target.value)}
                    />
                  </Field>
                  <Field label="Phone (optional)">
                    <input
                      type="tel"
                      maxLength={40}
                      value={form.phone}
                      onChange={(e) => change("phone", e.target.value)}
                    />
                  </Field>
                </div>
                <Field label="Email (optional)">
                  <input
                    type="email"
                    maxLength={150}
                    value={form.email}
                    onChange={(e) => change("email", e.target.value)}
                  />
                </Field>
                <Field label="Drop-off person’s relationship to the owner">
                  <input
                    value={form.dropoff_role}
                    onChange={(e) => change("dropoff_role", e.target.value)}
                    placeholder="Owner, employee, courier, other / unknown"
                  />
                </Field>
                {openRequests.length > 0 && (
                  <div className="note-box">
                    <div>
                      <strong>
                        This equipment already has an open request.
                      </strong>
                      {openRequests.map((r: ServiceRequest) => (
                        <p key={r.id}>
                          <Link to={"/requests/" + r.id}>
                            {r.code} · {r.title} · {r.status}
                          </Link>
                        </p>
                      ))}
                      <label className="checkbox-field">
                        <input
                          type="checkbox"
                          checked={form.acknowledge_open}
                          onChange={(e) =>
                            change("acknowledge_open", e.target.checked)
                          }
                        />
                        I reviewed these requests and this is a separate service
                        visit.
                      </label>
                    </div>
                  </div>
                )}
                <Field label="Short problem title">
                  <input
                    required
                    minLength={4}
                    maxLength={140}
                    value={form.title}
                    onChange={(e) => change("title", e.target.value)}
                    placeholder="e.g. Pump runs, but will not prime"
                  />
                </Field>
                <Field label="Customer’s reported problem">
                  <textarea
                    required
                    minLength={10}
                    maxLength={4000}
                    rows={4}
                    value={form.description}
                    onChange={(e) => change("description", e.target.value)}
                    placeholder="Keep the customer’s observations in their own words…"
                  />
                </Field>
                <div className="form-grid">
                  <Field label="Priority">
                    <select
                      value={form.priority}
                      onChange={(e) => change("priority", e.target.value)}
                    >
                      {["Low", "Normal", "High", "Urgent"].map((x) => (
                        <option key={x}>{x}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Can equipment operate?">
                    <select
                      value={form.operating}
                      onChange={(e) => change("operating", e.target.value)}
                    >
                      {[
                        "Unknown / Not assessed",
                        "No",
                        "Yes",
                        "Intermittently",
                      ].map((x) => (
                        <option key={x}>{x}</option>
                      ))}
                    </select>
                  </Field>
                </div>
                <Field label="Reception notes (optional)">
                  <textarea
                    rows={2}
                    value={form.intake_notes}
                    maxLength={2000}
                    onChange={(e) => change("intake_notes", e.target.value)}
                    placeholder="Accessories received, customer instructions, anything the technician should know…"
                  />
                </Field>
                <div className="form-section-title">
                  <span>03</span>Choose the technician
                </div>
                <Field label="Send to">
                  <select
                    required
                    value={form.technician}
                    onChange={(e) => change("technician", e.target.value)}
                  >
                    <option>Unassigned</option>
                    {session.technicians.map((name: string) => (
                      <option key={name}>{name}</option>
                    ))}
                  </select>
                </Field>
                {[
                  ["accessories", "Accessories received"],
                  ["visible_damage", "Visible damage / not assessed"],
                  ["customer_instructions", "Customer instructions"],
                ].map(([key, label]) => (
                  <Field key={key} label={label}>
                    <textarea
                      value={form[key]}
                      onChange={(e) => change(key, e.target.value)}
                      maxLength={1000}
                    />
                  </Field>
                ))}
                <Field label="Intake photos · optional, up to 5">
                  <input
                    type="file"
                    accept="image/jpeg,image/png"
                    disabled={form.photo_ids.length >= 5}
                    onChange={async (e) => {
                      let file = e.target.files?.[0];
                      if (!file) return;
                      try {
                        file = await readablePhoto(file);
                        if (file.size > 2500000)
                          throw Error(
                            "Use a photo under 2.5 MB. You can reduce its size before uploading.",
                          );
                        const b = new FormData();
                        b.append("file", file);
                        const response = await fetch(
                          "/api/intake/documents?purpose=photo",
                          { method: "POST", body: b },
                        );
                        const photo = await response.json();
                        if (!response.ok) throw Error(photo.detail);
                        change("photo_ids", [...form.photo_ids, photo.id]);
                        toast(
                          "Photo saved with intake. No AI call was needed.",
                        );
                      } catch (e: any) {
                        setIssue(e.message);
                      }
                    }}
                  />
                  <small>
                    {form.photo_ids.length} photos attached. Images remain
                    staff-only until explicitly released.
                  </small>
                </Field>
                <label className="checkbox-field review-checkbox">
                  <input
                    type="checkbox"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                    required
                  />
                  <span>
                    I checked the equipment, contact details and reported
                    problem{document ? " against the original paper" : ""}.
                  </span>
                </label>
                <button
                  className="button primary full"
                  disabled={
                    !reviewed ||
                    saving ||
                    reading ||
                    (openRequests.length > 0 && !form.acknowledge_open)
                  }
                >
                  {saving ? (
                    <Loader2 className="spin" size={17} />
                  ) : (
                    <Send size={17} />
                  )}
                  Send to technician
                </button>
                <p className="small muted centered">
                  The request appears in their queue immediately. No trip to the
                  front desk needed.
                </p>
              </fieldset>
            </form>
          </section>
        </div>
      )}
      {assetModal && (
        <RegisterAsset
          onClose={() => setAssetModal(false)}
          onCreated={(a: any) => {
            refresh();
            change("asset_id", a.id);
            setAssetModal(false);
          }}
        />
      )}
    </>
  );
}

function RegisterAsset({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (a: any) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title="Register customer equipment" onClose={onClose}>
      <form
        className="form-body"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            onCreated(
              await post(
                "/assets",
                Object.fromEntries(new FormData(e.currentTarget)),
              ),
            );
          } catch (e: any) {
            setError(e.message);
            setBusy(false);
          }
        }}
      >
        <Field label="Equipment name">
          <input
            name="name"
            required
            minLength={3}
            placeholder="Customer’s workshop pump"
          />
        </Field>
        <Field label="Model">
          <input name="model" required placeholder="Manufacturer model" />
        </Field>
        <Field label="Serial number">
          <input name="serial" required minLength={2} />
        </Field>
        <Field label="Customer / company">
          <input name="customer" required minLength={2} />
        </Field>
        <Field label="Location">
          <input name="location" required minLength={2} />
        </Field>
        {error && <ErrorBox message={error} />}
        <div className="modal-actions">
          <button className="button secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            Register equipment
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function TechnicianInbox() {
  const { session, setSession, refresh } = useApp();
  const { data, error, setData } = useData("/dashboard");
  useEffect(() => {
    const t = setInterval(() => {
      if (document.visibilityState === "visible")
        api("/dashboard")
          .then(setData)
          .catch(() => {});
    }, 15000);
    return () => clearInterval(t);
  }, []);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const mine = data.requests.filter(
    (r: ServiceRequest) =>
      (r.technician === session.technician || r.technician === "Unassigned") &&
      r.status !== "Closed",
  );
  return (
    <>
      <PageHeader
        eyebrow="YOUR WORK, READY WHEN YOU ARE"
        title="My work queue"
        subtitle={`Assigned to ${session.technician}. Reports, original papers and automatic AI guidance, together.`}
        actions={
          <button className="button secondary" onClick={refresh}>
            <RefreshCw size={16} />
            Refresh
          </button>
        }
      />
      <div className="inbox-summary">
        <div className="orange-square">
          <ClipboardList size={23} />
        </div>
        <div>
          <strong>
            {mine.length} active {mine.length === 1 ? "request" : "requests"}
          </strong>
          <p>
            New handoffs appear here automatically. Open a request to start
            troubleshooting.
          </p>
        </div>
        <span className="environment">
          <i />
          Updates every 15s
        </span>
      </div>
      <section className="panel">
        <RequestTable requests={mine} />
      </section>
      <div className="note-box">
        <Info size={17} />
        <p>
          New handoffs arrive with the original paper and automatically prepared
          guidance. Use the account selector to try the receptionist’s separate
          workspace. Demo accounts share this browser’s sample workspace; real
          employee accounts use their own credentials.
        </p>
      </div>
    </>
  );
}
