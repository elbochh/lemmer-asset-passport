import { GuidanceStatus, PartCandidates } from "./guidance-ui";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Plus,
  Search,
  Users,
  ArrowRight,
  Car,
  Package,
  CheckCircle2,
  ShieldCheck,
  Clock,
  ScanLine,
} from "lucide-react";
import { api, post, patch, date } from "./api";
import {
  useApp,
  useData,
  PageHeader,
  Loading,
  ErrorBox,
  Modal,
  Field,
  Badge,
  Empty,
} from "./shared";

function Form({
  onSubmit,
  children,
  label = "Save",
}: {
  onSubmit: (f: any) => Promise<any>;
  children: any;
  label?: string;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <form
      className="form-body"
      onSubmit={async (e) => {
        e.preventDefault();
        const body = Object.fromEntries(new FormData(e.currentTarget));
        setBusy(true);
        setError("");
        try {
          await onSubmit(body);
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
        <ArrowRight size={16} />
      </button>
    </form>
  );
}
export function AccountAccess({ onClose }: { onClose: () => void }) {
  const { setSession } = useApp();
  const [signup, setSignup] = useState(
    !!new URLSearchParams(location.search).get("invite"),
  );
  const navigate = useNavigate();
  return (
    <Modal
      title={
        signup ? "Create or connect your account" : "Staff or customer sign in"
      }
      subtitle="Your equipment, service history and parts requests in one place."
      onClose={onClose}
    >
      <Form
        label={signup ? "Create account" : "Sign in"}
        onSubmit={async (b) => {
          await post(signup ? "/auth/signup" : "/auth/login", b);
          const signedIn = await api("/session");
          setSession(signedIn);
          onClose();
          if (!location.pathname.startsWith("/passport/"))
            navigate(
              signedIn.role === "superuser"
                ? "/operations"
                : signedIn.role === "reception"
                  ? "/reception"
                  : signedIn.role === "technician"
                    ? "/my-work"
                    : "/my-assets",
            );
        }}
      >
        {signup && (
          <Field label="Your name">
            <input name="name" required minLength={2} />
          </Field>
        )}
        <Field label="Email">
          <input name="email" type="email" required autoComplete="email" />
        </Field>
        <Field label="Password · at least 10 characters">
          <input
            name="password"
            type="password"
            required
            minLength={10}
            maxLength={128}
            autoComplete={signup ? "new-password" : "current-password"}
          />
        </Field>
        {signup && (
          <Field label="Private reception invitation (optional)">
            <input
              name="invite"
              defaultValue={
                new URLSearchParams(location.search).get("invite") || ""
              }
            />
            <small>
              An invitation links equipment already registered by reception. A
              new account alone does not claim existing equipment. Already
              signed up? Enter your existing password to accept reception’s
              invitation.
            </small>
          </Field>
        )}
        <button
          type="button"
          className="text-button"
          onClick={() => setSignup(!signup)}
        >
          {signup
            ? "Already registered? Sign in"
            : "New customer? Create an account"}
        </button>
      </Form>
    </Modal>
  );
}
export function QRAccess() {
  const { share, code } = useParams();
  const { session } = useApp();
  const [login, setLogin] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  useEffect(() => {
    if (session)
      api(`/qr/${share}/${code}`)
        .then((x) =>
          navigate(
            (session.role === "customer" ? "/my-assets/" : "/assets/") + x.id,
            { replace: true },
          ),
        )
        .catch((e) => setError(e.message));
  }, [session, share, code]);
  return (
    <main className="qr-gate">
      <img src="/images/lemmer-logo.svg" alt="Lemmer" />
      <ShieldCheck size={40} />
      <h1>Your asset passport</h1>
      <p>
        Sign in to securely open {code}. Only the assigned owner or authorized
        staff can view its history.
      </p>
      {error && <ErrorBox message={error} />}
      <button className="button primary" onClick={() => setLogin(true)}>
        Sign in / create account
      </button>
      <Link to="/">Return to the app</Link>
      {login && <AccountAccess onClose={() => setLogin(false)} />}
    </main>
  );
}
export function Catalog() {
  const { data, error } = useData("/catalog");
  const [q, setQ] = useState(""),
    [kind, setKind] = useState("All");
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const filtered = data.filter(
    (p: any) =>
      (kind === "All" || p.kind === kind) &&
      `${p.name} ${p.sku}`.toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        title="Rustproofing catalogue"
        subtitle="Lemmer equipment, application kits and accessories. Find the right starting point."
      />
      <div className="catalog-intro">
        <Package />
        <div>
          <strong>{data.length} sourced catalogue entries</strong>
          <p>
            Product information from Lemmer. Parts compatibility and
            availability are confirmed by the branch.
          </p>
        </div>
      </div>
      <div className="asset-toolbar">
        <div className="input-with-icon">
          <Search size={18} />
          <input
            aria-label="Search catalogue"
            placeholder="Search RP-460, packing, hose or product number…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select
          aria-label="Product type"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option>All</option>
          <option>Equipment</option>
          <option>Accessories &amp; parts</option>
        </select>
        <span>{filtered.length} items</span>
      </div>
      <div className="catalog-grid">
        {filtered.map((p: any) => (
          <article className="catalog-card" key={p.sku}>
            <img loading="lazy" src={p.image} alt={p.name} />
            <div>
              <span className="eyebrow">{p.sku}</span>
              <h3>{p.name}</h3>
              <span className="muted small">{p.kind}</span>
              <a href={p.url} target="_blank" rel="noreferrer">
                Product details <ArrowRight size={15} />
              </a>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
export function Customers() {
  const { data, error } = useData("/customers");
  const { session, refresh, toast } = useApp();
  const [add, setAdd] = useState(false),
    [q, setQ] = useState(""),
    [invite, setInvite] = useState("");
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <PageHeader
        title="Customers & organizations"
        subtitle="One customer account can hold several pieces of equipment and vehicles."
        actions={
          ["reception", "superuser"].includes(session.role) && (
            <button className="button primary" onClick={() => setAdd(true)}>
              <Plus size={16} />
              New customer
            </button>
          )
        }
      />
      <div className="input-with-icon">
        <Search size={18} />
        <input
          placeholder="Search SAP customer code, company name or first pump Asset ID…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="catalog-grid customer-grid">
        {data
          .filter((c: any) =>
            `${c.name} ${c.email} ${c.sap_customer_code || ""} ${(c.asset_codes || []).join(" ")}`
              .toLowerCase()
              .includes(q.toLowerCase()),
          )
          .map((c: any) => (
            <article className="panel customer-card" key={c.id}>
              <div className="customer-avatar">
                <Users size={24} />
              </div>
              <h3>{c.name}</h3>
              <Badge value="Customer" />
              <p>
                {c.email || "No email recorded"}
                <br />
                {c.phone}
              </p>
              <p>SAP customer code: {c.sap_customer_code || "Not recorded"}</p>
              <strong>{c.asset_count} assigned assets</strong>
              <div className="action-row">
                <Link
                  className="button secondary"
                  to={"/registry?customer=" + c.id}
                >
                  Add equipment / vehicle
                </Link>
                {["reception", "superuser"].includes(session.role) && (
                  <button
                    className="text-button"
                    onClick={async () => {
                      try {
                        const x = await post("/customers/" + c.id + "/invite");
                        setInvite(location.origin + x.path);
                      } catch (e: any) {
                        toast(e.message);
                      }
                    }}
                  >
                    Create private invitation
                  </button>
                )}
              </div>
            </article>
          ))}
      </div>
      {add && (
        <Modal
          title="Create a customer"
          subtitle="Check for an existing customer before adding another account."
          onClose={() => setAdd(false)}
        >
          <Form
            label="Create customer"
            onSubmit={async (b) => {
              await post("/customers", b);
              refresh();
              setAdd(false);
              toast("Customer created. You can now assign equipment.");
            }}
          >
            <Field label="Customer or organization name">
              <input name="name" required minLength={2} />
            </Field>
            <Field label="Email">
              <input name="email" type="email" />
            </Field>
            <Field label="Phone">
              <input name="phone" />
            </Field>
            <Field label="SAP B1 customer code · optional manual reference">
              <input name="sap_customer_code" maxLength={80} />
            </Field>
          </Form>
        </Modal>
      )}
      {invite && (
        <Modal
          title="Private customer invitation"
          subtitle="Give this link only to the intended customer. It can be used once. No email has been sent."
          onClose={() => setInvite("")}
        >
          <div className="form-body">
            <input readOnly value={invite} />
            <button
              className="button primary"
              onClick={() => {
                navigator.clipboard.writeText(invite);
                toast("Invitation copied");
              }}
            >
              Copy invitation
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
export function Registry() {
  const { data: customers, error } = useData("/customers");
  const { data: products } = useData("/catalog");
  const { refresh, toast } = useApp();
  const navigate = useNavigate();
  const [ownerSearch, setOwnerSearch] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [kind, setKind] = useState("equipment"),
    [sku, setSku] = useState(""),
    [customer, setCustomer] = useState(
      new URLSearchParams(location.search).get("customer") || "",
    );
  if (error) return <ErrorBox message={error} />;
  if (!customers || !products) return <Loading />;
  return (
    <>
      <PageHeader
        title="Register equipment or a vehicle"
        subtitle="Create a passport and assign it to the correct customer."
      />
      <div className="panel registry-form">
        <Form
          label="Create asset passport"
          onSubmit={async (b) => {
            const selected = products.find((x: any) => x.sku === sku);
            const a = await post("/registry", {
              ...b,
              kind,
              customer_confirmed: confirmed,
              product_sku: sku,
              name: b.name || selected?.name,
              model: sku || b.model,
            });
            refresh();
            toast("Asset assigned to customer");
            navigate(kind === "vehicle" ? "/vehicles" : "/assets/" + a.id);
          }}
        >
          <Field label="Find the owner · SAP code, company or first pump Asset ID">
            <input
              value={ownerSearch}
              onChange={(e) => setOwnerSearch(e.target.value)}
              placeholder="Search existing customer accounts…"
            />
          </Field>
          <Field label="Assign to existing customer">
            <select
              name="customer_id"
              required
              value={customer}
              onChange={(e) => {
                setCustomer(e.target.value);
                setConfirmed(false);
              }}
            >
              <option value="">Choose a customer…</option>
              {customers
                .filter(
                  (c: any) =>
                    c.id === customer ||
                    `${c.name} ${c.sap_customer_code || ""} ${(c.asset_codes || []).join(" ")}`
                      .toLowerCase()
                      .includes(ownerSearch.toLowerCase()),
                )
                .map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.asset_count} assets
                  </option>
                ))}
            </select>
            <Link to="/customers">
              New customer? Create their account first
            </Link>
          </Field>
          {customer && (
            <div className="note-box">
              <div>
                <strong>
                  {customers.find((c: any) => c.id === customer)?.name}
                </strong>
                <p>
                  SAP customer code:{" "}
                  {customers.find((c: any) => c.id === customer)
                    ?.sap_customer_code || "Not recorded"}
                </p>
                <p>
                  {customers.find((c: any) => c.id === customer)?.email} ·{" "}
                  {customers.find((c: any) => c.id === customer)?.asset_count}{" "}
                  existing assets
                </p>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    required={kind === "equipment"}
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  I confirm this is the correct owner. This item receives its
                  own new Asset ID and QR code.
                </label>
              </div>
            </div>
          )}
          <Field label="Asset type">
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setSku("");
              }}
            >
              <option value="equipment">Equipment</option>
              <option value="vehicle">Vehicle</option>
            </select>
          </Field>
          {kind === "equipment" && (
            <Field label="Lemmer rustproofing product or other equipment">
              <select value={sku} onChange={(e) => setSku(e.target.value)}>
                <option value="">
                  Other manufacturer / enter equipment manually
                </option>
                {products.map((p: any) => (
                  <option key={p.sku} value={p.sku}>
                    {p.sku} · {p.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Asset display name">
            <input
              name="name"
              required
              minLength={3}
              placeholder={
                kind === "vehicle"
                  ? "Delivery van · Unit 12"
                  : "Workshop rustproofing gun"
              }
            />
          </Field>
          {!sku && (
            <div className="form-grid">
              <Field label="Manufacturer / make">
                <input
                  name="manufacturer"
                  required
                  placeholder="Lemmer, Graco, Ford…"
                />
              </Field>
              <Field label="Model">
                <input name="model" required />
              </Field>
            </div>
          )}
          <Field
            label={
              kind === "vehicle"
                ? "Vehicle identifier / fleet number"
                : "Serial number"
            }
          >
            <input name="serial" required minLength={2} />
          </Field>
          {kind === "vehicle" && (
            <div className="form-grid">
              <Field label="VIN">
                <input name="vin" maxLength={40} />
              </Field>
              <Field label="Year">
                <input name="year" maxLength={4} />
              </Field>
              <Field label="Registration">
                <input name="registration" maxLength={30} />
              </Field>
            </div>
          )}
          {kind === "equipment" && (
            <>
              <h3>SAP B1 sale reference · optional</h3>
              <p className="small muted">
                Manually recorded references only. This app does not read or
                update SAP.
              </p>
              <div className="form-grid">
                <Field label="Document type">
                  <input
                    name="sap_document_type"
                    placeholder="Sales order, invoice…"
                    maxLength={60}
                  />
                </Field>
                <Field label="Document number">
                  <input name="sap_document_number" maxLength={80} />
                </Field>
                <Field label="Line number">
                  <input name="sap_line_number" maxLength={20} />
                </Field>
              </div>
            </>
          )}
          <Field label="Equipment location">
            <input name="location" defaultValue="Calgary, AB" required />
          </Field>
        </Form>
      </div>
    </>
  );
}
export function MyAssets() {
  const { data, error } = useData("/portal/assets");
  const { session } = useApp();
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <PageHeader
        title="Your asset passports"
        subtitle="Equipment and vehicles assigned to your account. Their history stays connected."
      />
      {!data.length && (
        <Empty title="No assets assigned yet">
          Give reception your account details so they can register your
          equipment and provide an invitation.
        </Empty>
      )}
      <div className="catalog-grid">
        {data.map((a: any) => (
          <Link className="catalog-card" to={"/my-assets/" + a.id} key={a.id}>
            <img src={a.image} alt={a.name} />
            <div>
              <span className="eyebrow">
                {a.code} · {a.ownership.kind}
              </span>
              <h3>{a.name}</h3>
              <p>
                Model {a.model} · Product {a.product_number || "Unknown"}
                <br />
                {a.manufacturer} · Serial {a.serial}
              </p>
              <Badge value={a.condition} />
              <span className="catalog-link">
                Open passport <ArrowRight size={16} />
              </span>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
export function OwnerPassport() {
  const [observationRequest, setObservationRequest] = useState<any>(null);
  const { id } = useParams();
  const { data, error, setData } = useData("/portal/assets/" + id);
  const { refresh, toast } = useApp();
  const [symptoms, setSymptoms] = useState(false),
    [order, setOrder] = useState<any>(null);
  useEffect(() => {
    const t = setInterval(() => {
      if (!document.hidden)
        api("/portal/assets/" + id)
          .then(setData)
          .catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [id]);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const a = data.asset;
  return (
    <>
      <PageHeader
        title={a.name}
        subtitle={`${a.code} · ${a.manufacturer} · ${a.serial}`}
        actions={
          <button className="button primary" onClick={() => setSymptoms(true)}>
            <Plus size={16} />
            Report a problem
          </button>
        }
      />
      <div className="passport-layout">
        <div>
          <section className="panel owner-summary">
            <img src={a.image} alt={a.name} />
            <div>
              <Badge value={a.condition} />
              <h3>{a.customer}</h3>
              <p>{a.location}</p>
              {data.ownership?.kind === "vehicle" && (
                <p>
                  VIN: {data.ownership.profile.vin || "Not recorded"}
                  <br />
                  Year: {data.ownership.profile.year || "Not recorded"}
                </p>
              )}
            </div>
          </section>
          <section className="panel expansion-panel">
            <h2>Service requests & guidance</h2>
            {!data.requests.length && (
              <p className="muted">
                Describe a symptom to send it to the service team.
              </p>
            )}
            {data.requests.map((r: any) => (
              <article className="record-block" key={r.id}>
                <div className="action-row">
                  <strong>{r.code}</strong>
                  <Badge value={r.status} />
                </div>
                <p>{r.description}</p>
                <small>
                  Assigned technician:{" "}
                  {r.technician === "Unassigned"
                    ? "Awaiting reception assignment"
                    : r.technician}
                </small>
                <GuidanceStatus
                  job={r.guidance_job}
                  requestId={r.id}
                  refresh={refresh}
                />
                <div className="guidance-note">
                  <ShieldCheck size={18} />
                  <div>
                    <strong>
                      {r.guidance ? "Guidance review" : "Automatic guidance"}
                    </strong>
                    <p>
                      {r.guidance?.summary ||
                        "The review will use applicable product references and recorded repair history. No part is confirmed from the symptom alone."}
                    </p>
                    {r.guidance?.steps?.length > 0 && (
                      <ul>
                        {r.guidance.steps.map((step: string, i: number) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                    )}
                    {r.guidance?.cache_hit && (
                      <small>
                        Reused a previous review. No new model call.
                      </small>
                    )}
                  </div>
                </div>
                {r.status !== "Closed" && (
                  <button
                    className="button secondary"
                    onClick={() => setObservationRequest(r)}
                  >
                    Add observations / answer questions
                  </button>
                )}
                {r.guidance?.questions?.length > 0 && (
                  <div className="questions-box">
                    <h4>Before choosing a part</h4>
                    {r.guidance.questions.map((q: string) => (
                      <p key={q}>{q}</p>
                    ))}
                  </div>
                )}
                <PartCandidates
                  candidates={r.guidance?.candidates}
                  parts={data.parts}
                  onPart={(part) =>
                    setOrder({
                      part,
                      request_id: r.id,
                      description: r.description,
                    })
                  }
                />
                {r.guidance?.parts.map((p: string) => (
                  <button
                    key={p}
                    className="button secondary"
                    onClick={() =>
                      setOrder({
                        part: p,
                        request_id: r.id,
                        description: r.description,
                      })
                    }
                  >
                    Request {p}
                    {data.parts[p] ? ` · ${data.parts[p]}` : ""}
                  </button>
                ))}
                <button
                  className="text-button"
                  onClick={() =>
                    setOrder({
                      request_id: r.id,
                      description: r.description,
                      part: "",
                    })
                  }
                >
                  Ask the branch for a part
                </button>
              </article>
            ))}
          </section>
          <section className="panel expansion-panel">
            <h2>Your equipment documents</h2>
            <p>
              Public product references and documents explicitly released by
              reception.
            </p>
            {[
              ...(data.references || []),
              ...(data.released_documents || []),
            ].map((d: any, i: number) => (
              <p key={i}>
                <a href={d.url} target="_blank" rel="noreferrer">
                  {d.title}
                </a>
              </p>
            ))}
          </section>
          <section className="panel expansion-panel">
            <h2>Service history</h2>
            {data.events.length ? (
              data.events.map((e: any) => (
                <article className="record-block" key={e.id}>
                  <small>{date(e.created_at)}</small>
                  <h3>{e.title}</h3>
                  {Object.entries(e.body)
                    .filter(([k]) =>
                      [
                        "diagnosis",
                        "work",
                        "parts",
                        "test",
                        "outcome",
                        "findings",
                        "treatment",
                        "verification",
                      ].includes(k),
                    )
                    .map(([k, v]) => (
                      <p key={k}>
                        <strong>{k}: </strong>
                        {Array.isArray(v) ? v.join(", ") : String(v)}
                      </p>
                    ))}
                </article>
              ))
            ) : (
              <p className="muted">
                Completed service reports will appear here.
              </p>
            )}
            {data.visits.map((v: any) => (
              <article className="record-block" key={v.id}>
                <h3>Vehicle visit · {v.status}</h3>
                <small>
                  {date(v.created_at)} ·{" "}
                  {v.simulated ? "Simulated demonstration" : "Recorded visit"}
                </small>
                <p>{v.report.findings}</p>
                <div className="before-after">
                  {["before", "after"].map(
                    (k) =>
                      v.report[k] && (
                        <figure key={k}>
                          <img
                            src={v.report[k]}
                            alt={`Simulated ${k} inspection`}
                          />
                          <figcaption>
                            {k} ·{" "}
                            {v.report[k + "_source"] ||
                              "simulated illustration"}
                          </figcaption>
                        </figure>
                      ),
                  )}
                </div>
              </article>
            ))}
          </section>
        </div>
        <aside>
          <section className="panel expansion-panel">
            <Clock size={24} />
            <h2>Maintenance outlook</h2>
            <p className="muted small">
              Inspection estimates, not guaranteed remaining part life.
            </p>
            {data.maintenance.length ? (
              data.maintenance.map((m: any) => (
                <div className="record-block" key={m.id}>
                  <strong>{m.part}</strong>
                  <p>Installed {date(m.installed)}</p>
                  {m.review_date ? (
                    <p className="maintenance-time">
                      {m.days_left >= 0
                        ? `Review in approximately ${m.days_left} days`
                        : `Review overdue by ${-m.days_left} days`}
                    </p>
                  ) : (
                    <p>No replacement interval established.</p>
                  )}
                  <small>{m.basis}</small>
                  <button
                    className="text-button"
                    onClick={() =>
                      setOrder({
                        part: m.part,
                        description: "Maintenance enquiry for " + m.part,
                      })
                    }
                  >
                    Ask about this part
                  </button>
                </div>
              ))
            ) : (
              <p>No component interval has been recorded.</p>
            )}
          </section>
          <section className="panel expansion-panel">
            <Package size={24} />
            <h2>Parts support</h2>
            {data.references?.map((d: any) => (
              <p key={d.url}>
                <a href={d.url} target="_blank" rel="noreferrer">
                  {d.title} ↗
                </a>
              </p>
            ))}
            <p>
              Request a part with your equipment details. The branch confirms
              compatibility and availability.
            </p>
            <button
              className="button secondary"
              onClick={() => setOrder({ part: "", description: "" })}
            >
              Create parts request
            </button>
          </section>
        </aside>
      </div>
      {observationRequest && (
        <Modal
          title="Add observations"
          subtitle="Your answers update this request and automatically queue a fresh evidence review."
          onClose={() => setObservationRequest(null)}
        >
          <Form
            label="Save & update guidance"
            onSubmit={async (b) => {
              await post(
                `/portal/requests/${observationRequest.id}/observations`,
                { ...b, version: observationRequest.version },
              );
              setObservationRequest(null);
              refresh();
              toast("Observations saved. Guidance is updating.");
            }}
          >
            <Field label="What else have you observed?">
              <textarea
                name="observations"
                required
                minLength={10}
                maxLength={2000}
                rows={5}
              />
            </Field>
          </Form>
        </Modal>
      )}
      {symptoms && (
        <Modal
          title="Describe the problem"
          subtitle="Your asset details are included automatically. Guidance will appear here without another click."
          onClose={() => setSymptoms(false)}
        >
          <Form
            label="Send to service team"
            onSubmit={async (b) => {
              await post("/portal/symptoms", {
                ...b,
                asset_id: id,
              });
              setSymptoms(false);
              refresh();
              toast("Symptoms sent. Reception can assign your technician.");
            }}
          >
            <Field label="What is happening?">
              <textarea name="description" required minLength={10} rows={5} />
            </Field>
          </Form>
        </Modal>
      )}
      {order && (
        <Modal
          title="Request a part"
          subtitle="No payment is taken. Reception will review your request and equipment compatibility."
          onClose={() => setOrder(null)}
        >
          <Form
            label="Send parts request"
            onSubmit={async (b) => {
              await post("/parts-requests", {
                ...b,
                asset_id: id,
                request_id: order.request_id || null,
                quantity: Number(b.quantity),
                submission_id:
                  order.submission_id ||
                  (order.submission_id = crypto.randomUUID()),
              });
              setOrder(null);
              refresh();
              toast("Parts request delivered to reception.");
            }}
          >
            <Field label="Part name or number">
              <input
                name="part"
                defaultValue={order.part}
                required
                minLength={2}
                list="verified-parts"
              />
              <datalist id="verified-parts">
                {Object.entries(data.parts).map(([k, v]) => (
                  <option key={k} value={k}>
                    {String(v)}
                  </option>
                ))}
              </datalist>
            </Field>
            <Field label="Quantity">
              <input
                name="quantity"
                type="number"
                min={1}
                max={100}
                defaultValue={1}
                required
              />
            </Field>
            <Field label="Problem or reason for the request">
              <textarea
                name="description"
                defaultValue={order.description}
                minLength={10}
                required
                rows={3}
              />
            </Field>
          </Form>
        </Modal>
      )}
    </>
  );
}
export function PartsRequests() {
  const { data, error } = useData("/parts-requests");
  const { session, refresh, toast } = useApp();
  const [edit, setEdit] = useState<any>(null);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <PageHeader
        title="Parts requests"
        subtitle={
          session.role === "reception"
            ? "Incoming customer needs, with equipment and symptoms attached."
            : "Track requests sent to your Lemmer branch."
        }
      />
      {!data.length && (
        <Empty icon={Package} title="No parts requests">
          Requests from an asset passport will appear here.
        </Empty>
      )}
      <div className="order-list">
        {data.map((o: any) => (
          <article className="panel expansion-panel" key={o.id}>
            <div className="action-row">
              <span className="eyebrow">{date(o.created_at)}</span>
              <Badge value={o.status} />
            </div>
            <h2>
              {o.quantity} × {o.part}
            </h2>
            <p>
              <strong>{o.customer.name}</strong> · {o.customer.email} ·{" "}
              {o.customer.phone}
            </p>
            <p>
              {o.asset.name} · {o.asset.code} · {o.asset.serial}
            </p>
            <p>{o.problem}</p>
            {o.request_id && (
              <p>
                Linked service request included
                {["reception", "superuser"].includes(session.role) && (
                  <>
                    {" "}
                    ·{" "}
                    <Link to={"/requests/" + o.request_id}>
                      Open technician handoff
                    </Link>
                  </>
                )}
              </p>
            )}
            <div className="guidance-note">
              <Package size={18} />
              <p>
                {o.notes ||
                  "Compatibility, price and availability need branch confirmation. No payment taken."}
              </p>
            </div>
            {["reception", "superuser"].includes(session.role) && (
              <button className="button secondary" onClick={() => setEdit(o)}>
                Review request
              </button>
            )}
          </article>
        ))}
      </div>
      {edit && (
        <Modal title="Review parts request" onClose={() => setEdit(null)}>
          <Form
            onSubmit={async (b) => {
              await patch("/parts-requests/" + edit.id, b);
              setEdit(null);
              refresh();
              toast("Customer request updated");
            }}
          >
            <Field label="Status">
              <select name="status" defaultValue={edit.status}>
                {[
                  "Requested",
                  "Reviewing compatibility",
                  "Awaiting customer",
                  "Ready",
                  "Fulfilled",
                  "Cancelled",
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Message visible to customer">
              <textarea name="notes" defaultValue={edit.notes} rows={4} />
            </Field>
          </Form>
        </Modal>
      )}
    </>
  );
}
const stages = [
  "Checked in",
  "Bay preparation",
  "Ready for inspection",
  "Inspecting",
  "Findings review",
  "Treatment recorded",
  "Verification",
  "Completed",
];
export function Vehicles() {
  const { data: assets, error } = useData("/portal/assets");
  const { data: visits } = useData("/visits");
  const { session, refresh, toast } = useApp();
  const [active, setActive] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorBox message={error} />;
  if (!assets || !visits) return <Loading />;
  return (
    <>
      <PageHeader
        title="Vehicle rustproofing bay"
        subtitle="Vehicle identity, inspection evidence and treatment history in one place."
        actions={
          ["reception", "superuser"].includes(session.role) && (
            <Link to="/registry" className="button primary">
              <Plus size={16} />
              Register vehicle
            </Link>
          )
        }
      />
      <div className="catalog-intro">
        <ScanLine />
        <div>
          <strong>Robot integration is deferred</strong>
          <p>
            This interface records a simulated workflow. Illustrations and
            status changes do not operate a lift, scanner or spray system.
          </p>
        </div>
      </div>
      <div className="catalog-grid">
        {assets
          .filter((a: any) => a.ownership.kind === "vehicle")
          .map((a: any) => (
            <article key={a.id} className="catalog-card">
              <img src={a.image} alt={a.name} />
              <div>
                <span className="eyebrow">{a.code}</span>
                <h3>{a.name}</h3>
                <p>
                  {a.manufacturer} {a.model} · {a.ownership.profile.year}
                </p>
                <p>VIN: {a.ownership.profile.vin || "Not recorded"}</p>
                <small>{a.customer}</small>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      const v = await post("/visits", { asset_id: a.id });
                      setActive({ ...v, asset: a });
                      refresh();
                    } catch (e: any) {
                      toast(e.message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Open bay visit <ArrowRight size={16} />
                </button>
                <Link to={"/my-assets/" + a.id}>
                  View passport and prior pictures
                </Link>
              </div>
            </article>
          ))}
      </div>
      <h2 className="section-heading">Visit history</h2>
      <div className="order-list">
        {visits.map((v: any) => (
          <button
            key={v.id}
            className="panel visit-row"
            onClick={() => setActive(v)}
          >
            <Car size={24} />
            <div>
              <strong>{v.asset.name}</strong>
              <small>{date(v.created_at)} · Simulated visit</small>
            </div>
            <Badge value={v.status} />
            <ArrowRight size={18} />
          </button>
        ))}
      </div>
      {active && (
        <Modal
          title={active.asset?.name || "Vehicle visit"}
          subtitle="Simulated bay workflow · no physical robot commands"
          onClose={() => setActive(null)}
          wide
        >
          <div className="form-body">
            <div className="visit-stages">
              {stages.map((s, i) => (
                <span
                  key={s}
                  className={stages.indexOf(active.status) >= i ? "done" : ""}
                >
                  {i + 1}. {s}
                </span>
              ))}
            </div>
            <div className="before-after">
              {["before", "after"].map(
                (k) =>
                  active.report[k] && (
                    <figure key={k}>
                      <img src={active.report[k]} alt={`Simulated ${k}`} />
                      <figcaption>
                        {k} ·{" "}
                        {active.report[k + "_source"] ||
                          "simulated illustration"}
                      </figcaption>
                    </figure>
                  ),
              )}
            </div>
            {session.role === "technician" &&
              !["Completed", "Cancelled", "Failed"].includes(active.status) && (
                <div className="form-grid">
                  {["before", "after"].map((kind) => (
                    <Field
                      key={kind}
                      label={`Upload ${kind} image · JPG/PNG, up to 2.5 MB`}
                    >
                      <input
                        type="file"
                        accept="image/jpeg,image/png"
                        onChange={async (e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          const body = new FormData();
                          body.append("file", file);
                          try {
                            const response = await fetch(
                              `/api/visits/${active.id}/media/${kind}`,
                              { method: "POST", body },
                            );
                            const result = await response.json();
                            if (!response.ok) throw Error(result.detail);
                            setActive({ ...result, asset: active.asset });
                            refresh();
                            toast("Inspection image saved");
                          } catch (err: any) {
                            toast(err.message);
                          }
                        }}
                      />
                    </Field>
                  ))}
                </div>
              )}
            {session.role === "technician" &&
            !["Completed", "Cancelled", "Failed"].includes(active.status) ? (
              <Form
                label="Save visit stage"
                onSubmit={async (b) => {
                  const v = await patch("/visits/" + active.id, {
                    ...b,
                    version: active.version,
                  });
                  setActive({ ...v, asset: active.asset });
                  refresh();
                  toast("Simulated visit saved");
                }}
              >
                <Field label="Visit stage">
                  <select
                    name="status"
                    defaultValue={active.status}
                    key={active.version}
                  >
                    {[...stages, "Paused", "Failed", "Cancelled"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Inspection findings">
                  <textarea
                    name="findings"
                    defaultValue={active.report.findings || ""}
                    placeholder="Record the region, condition and uncertainty. Demo observations only."
                    rows={3}
                  />
                </Field>
                <Field label="Treatment record">
                  <textarea
                    name="treatment"
                    defaultValue={active.report.treatment || ""}
                    placeholder="What was simulated, or why treatment was not performed"
                    rows={3}
                  />
                </Field>
                <Field label="Verification / outcome">
                  <textarea
                    name="verification"
                    defaultValue={active.report.verification || ""}
                    placeholder="Record verification, limitations or follow-up"
                    rows={3}
                  />
                </Field>
              </Form>
            ) : (
              <div>
                <Badge value={active.status} />
                <p>
                  <strong>Findings: </strong>
                  {active.report.findings || "Not yet recorded"}
                </p>
                <p>
                  <strong>Treatment: </strong>
                  {active.report.treatment || "Not yet recorded"}
                </p>
                <p>
                  <strong>Verification: </strong>
                  {active.report.verification || "Not yet recorded"}
                </p>
                {["reception", "superuser"].includes(session.role) && (
                  <p>
                    A technician progresses the inspection and treatment stages.
                  </p>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
export function ComponentForm({ assetId }: { assetId: string }) {
  const { toast, refresh } = useApp();
  return (
    <Form
      label="Record component installation"
      onSubmit={async (b) => {
        await post("/portal/assets/" + assetId + "/components", {
          ...b,
          interval_days: b.interval_days ? Number(b.interval_days) : null,
        });
        refresh();
        toast("Installation recorded. Customer maintenance outlook updated.");
      }}
    >
      <Field label="Part number / component">
        <input name="part" required minLength={2} />
      </Field>
      <Field label="Installed on">
        <input
          name="installed"
          type="date"
          required
          max={new Date().toISOString().slice(0, 10)}
        />
      </Field>
      <Field label="Inspection interval in days (optional)">
        <input name="interval_days" type="number" min={1} max={3650} />
      </Field>
      <Field label="Basis and source for this interval">
        <textarea
          name="basis"
          required
          minLength={10}
          placeholder="Documented manufacturer interval, or observed previous replacement dates. Leave interval blank when unknown."
        />
      </Field>
    </Form>
  );
}
