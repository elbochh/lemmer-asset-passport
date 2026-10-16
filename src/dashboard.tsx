import { useState, FormEvent } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  ArrowUpRight,
  ArrowRight,
  Plus,
  Search,
  Wrench,
  PanelsTopLeft,
  BookOpen,
  CheckCheck,
  Activity,
  History,
  Check,
  ShieldCheck,
  ChevronRight,
  User,
  Send,
  Loader2,
} from "lucide-react";
import { post, relative, Asset, ServiceRequest } from "./api";
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
} from "./shared";
export function RequestTable({
  requests,
  compact = false,
}: {
  requests: ServiceRequest[];
  compact?: boolean;
}) {
  const navigate = useNavigate();
  return (
    <div className="table-scroll">
      <table className="request-table">
        <thead>
          <tr>
            <th>REQUEST / EQUIPMENT</th>
            {!compact && <th>CUSTOMER</th>}
            <th>PRIORITY</th>
            <th>STATUS</th>
            <th>ASSIGNED TO</th>
            <th>RECEIVED</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id} onClick={() => navigate("/requests/" + r.id)}>
              <td>
                <Link
                  to={"/requests/" + r.id}
                  className="request-title"
                  onClick={(e) => e.stopPropagation()}
                >
                  {r.title}
                </Link>
                <div className="request-sub">
                  <span>{r.code}</span>
                  <span>·</span>
                  <span>{r.asset.model}</span>
                  <span className="asset-code">{r.asset.code}</span>
                </div>
              </td>
              {!compact && (
                <td className="customer-cell" data-label="Customer">
                  {r.asset.customer}
                </td>
              )}
              <td data-label="Priority">
                <span className={"priority " + r.priority.toLowerCase()}>
                  <i />
                  {r.priority}
                </span>
              </td>
              <td data-label="Status">
                <Badge value={r.status} />
                {r.guidance && (
                  <div className={"guidance-status " + r.guidance.status}>
                    {r.guidance.status === "ready"
                      ? "AI review ready"
                      : r.guidance.status === "unavailable"
                        ? "AI unavailable"
                        : "AI preparing…"}
                  </div>
                )}
              </td>
              <td data-label="Assigned to">
                <span className="assigned">
                  {r.technician === "Unassigned" ? (
                    <span className="unassigned-icon">
                      <User size={13} />
                    </span>
                  ) : (
                    <span className="avatar tiny">
                      {r.technician
                        .split(" ")
                        .map((x) => x[0])
                        .join("")}
                    </span>
                  )}
                  {r.technician === "Unassigned"
                    ? "Unassigned"
                    : r.technician.split(" ")[0]}
                </span>
              </td>
              <td className="muted nowrap" data-label="Received">
                {relative(r.created_at)}
              </td>
              <td>
                <ChevronRight size={16} className="muted" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!requests.length && (
        <Empty title="No requests here">
          Try a different filter, or create a service request.
        </Empty>
      )}
    </div>
  );
}
export function Dashboard() {
  const { session } = useApp();
  const { data, error } = useData("/dashboard");
  const [create, setCreate] = useState(false);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const open = data.requests.filter(
    (r: ServiceRequest) => r.status !== "Closed",
  );
  return (
    <>
      <PageHeader
        eyebrow="YOUR SERVICE DAY, AT A GLANCE"
        title={`Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, ${session.technician.split(" ")[0]}.`}
        subtitle="Let’s get equipment back to work."
        actions={
          <button className="button primary" onClick={() => setCreate(true)}>
            <Plus size={17} />
            New service request
          </button>
        }
      />
      <div className="overview-grid">
        <section className="hero-card">
          <div>
            <span className="hero-kicker">
              <span className="live-dot" />
              CONNECTED SERVICE KNOWLEDGE
            </span>
            <h2>
              A history for every asset.
              <br />A head start on every repair.
            </h2>
            <p>
              Bring past repairs, product knowledge and this equipment’s story
              into your next service decision.
            </p>
            <Link
              className="hero-link"
              to={
                "/requests/" +
                data.requests.find(
                  (r: ServiceRequest) => r.asset.code === "LM-1042",
                )?.id
              }
            >
              Explore a service request <ArrowRight size={17} />
            </Link>
          </div>
          <div className="hero-visual">
            <div className="orbit o1" />
            <div className="orbit o2" />
            <div className="hero-product">
              <img
                src="/images/catalog/L015-201.webp"
                alt="Lemmer RP-460HD rustproofing gun"
              />
            </div>
            <span className="hero-asset-tag">
              <span className="live-dot" />
              LM-1042 · RP-460HD
            </span>
          </div>
        </section>
        <section className="focus-card">
          <div className="card-title">
            <span className="orange-square">
              <Activity size={18} />
            </span>
            <h3>Today’s focus</h3>
          </div>
          <div className="focus-count">
            {
              open.filter(
                (r: ServiceRequest) =>
                  r.priority === "Urgent" || r.priority === "High",
              ).length
            }
            <span>requests need attention</span>
          </div>
          <p>
            A good place to start: equipment that’s keeping a customer from
            working.
          </p>
          <Link to="/requests?filter=attention" className="text-link">
            Review priority requests <ArrowUpRight size={16} />
          </Link>
        </section>
      </div>
      <div className="stats-grid">
        {[
          {
            label: "Open requests",
            value: open.length,
            icon: Wrench,
            note: `${data.requests.filter((r: ServiceRequest) => r.status === "New").length} awaiting first review`,
          },
          {
            label: "Registered assets",
            value: data.assets.length,
            icon: PanelsTopLeft,
            note: "Individual, persistent passports",
          },
          {
            label: "Repair knowledge",
            value: data.knowledge_count,
            icon: BookOpen,
            note: "Searchable service cases",
          },
          {
            label: "Completed requests",
            value: data.requests.filter(
              (r: ServiceRequest) => r.status === "Closed",
            ).length,
            icon: CheckCheck,
            note: "Outcomes recorded",
          },
        ].map((x) => (
          <div className="stat-card" key={x.label}>
            <div>
              <span>{x.label}</span>
              <x.icon size={18} />
            </div>
            <strong>{x.value.toString().padStart(2, "0")}</strong>
            <small>{x.note}</small>
          </div>
        ))}
      </div>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>
              Service requests <span className="count">{open.length}</span>
            </h2>
            <p>The next repair starts here.</p>
          </div>
          <Link to="/requests" className="button secondary small-button">
            View all requests <ArrowUpRight size={15} />
          </Link>
        </div>
        <RequestTable requests={open.slice(0, 5)} compact />
      </section>
      <div className="bottom-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Recent passport activity</h2>
            <History size={18} className="muted" />
          </div>
          <div className="activity-list">
            {data.activity.slice(0, 4).map((e: any) => (
              <Link key={e.id} to={"/assets/" + e.asset_id}>
                <span className="activity-icon">
                  <Check size={17} />
                </span>
                <div>
                  <strong>{e.title}</strong>
                  <span>
                    {e.asset_code} <b>·</b> {e.actor}
                  </span>
                </div>
                <time>{relative(e.created_at)}</time>
              </Link>
            ))}
          </div>
        </section>
        <section className="knowledge-callout">
          <div className="icon-tile">
            <BookOpen size={22} />
          </div>
          <h3>
            Good repairs shouldn’t
            <br />
            be forgotten.
          </h3>
          <p>
            Completed service reports become searchable knowledge for the next
            technician.
          </p>
          <Link to="/knowledge" className="text-link">
            Open knowledge library <ArrowRight size={16} />
          </Link>
          <div className="source-tag">
            <ShieldCheck size={14} />
            Product sources + recorded outcomes
          </div>
        </section>
      </div>
      {create && (
        <NewRequestModal
          assets={data.assets}
          onClose={() => setCreate(false)}
        />
      )}
    </>
  );
}
export function Requests() {
  const { data, error } = useData("/dashboard");
  const loc = useLocation();
  const [search, setSearch] = useState(""),
    [tab, setTab] = useState(
      new URLSearchParams(loc.search).get("filter") === "attention"
        ? "Priority"
        : "All requests",
    ),
    [create, setCreate] = useState(false);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const filtered = data.requests.filter(
    (r: ServiceRequest) =>
      (tab === "All requests" ||
        (tab === "Priority"
          ? ["Urgent", "High"].includes(r.priority) && r.status !== "Closed"
          : r.status === tab)) &&
      `${r.title} ${r.code} ${r.asset.code} ${r.asset.customer} ${r.asset.model}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        title="Service requests"
        subtitle="From the first symptom to the final test. Keep every step connected."
        actions={
          <button className="button primary" onClick={() => setCreate(true)}>
            <Plus size={17} />
            New request
          </button>
        }
      />
      <section className="panel">
        <div className="tabs">
          {[
            "All requests",
            "New",
            "In progress",
            "Awaiting parts",
            "Closed",
            "Priority",
          ].map((t) => (
            <button
              className={tab === t ? "active" : ""}
              key={t}
              onClick={() => setTab(t)}
            >
              {t}
              {t === "All requests" && <span>{data.requests.length}</span>}
            </button>
          ))}
        </div>
        <div className="table-toolbar">
          <div className="input-with-icon">
            <Search size={17} />
            <input
              aria-label="Search service requests"
              placeholder="Search requests, equipment or customers…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <span className="muted small">{filtered.length} requests</span>
        </div>
        <RequestTable requests={filtered} />
      </section>
      {create && (
        <NewRequestModal
          assets={data.assets}
          onClose={() => setCreate(false)}
        />
      )}
    </>
  );
}
export function NewRequestModal({
  assets,
  onClose,
  selected,
  publicPath,
  onCreated,
}: {
  assets: Asset[];
  onClose: () => void;
  selected?: string;
  publicPath?: string;
  onCreated?: (r: any) => void;
}) {
  const { refresh, toast } = useApp();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    try {
      const r = await post(publicPath || "/requests", body);
      refresh();
      toast("Service request received.");
      onClose();
      if (onCreated) onCreated(r);
      else navigate("/requests/" + r.id);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Get me running"
      subtitle="Tell us what’s happening. We’ll keep this request connected to the right asset."
      onClose={onClose}
      wide
    >
      <form onSubmit={submit} className="form-body">
        <div className="form-grid">
          <Field label="Equipment">
            <select name="asset_id" defaultValue={selected || assets[0]?.id}>
              {assets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.code} · {a.model} · {a.serial}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Issue category">
            <select name="category">
              {[
                "Priming issue",
                "Low pressure",
                "Leak",
                "Will not start",
                "Spray pattern",
                "Maintenance",
                "Other",
              ].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Short description">
          <input
            name="title"
            placeholder="e.g. Pump runs, but will not prime"
            required
            minLength={4}
            maxLength={140}
          />
        </Field>
        <Field
          label="What happened?"
          hint="Include when it started, what changed, and anything you’ve already checked."
        >
          <textarea
            name="description"
            placeholder="Describe the symptoms in your own words…"
            rows={4}
            required
            minLength={10}
            maxLength={4000}
          />
        </Field>
        <div className="form-grid">
          <Field label="Can the equipment still operate?">
            <select name="operating">
              <option>No</option>
              <option>Intermittently</option>
              <option>Yes</option>
            </select>
          </Field>
          <Field label="Priority">
            <select name="priority">
              <option>Normal</option>
              <option>Low</option>
              <option>High</option>
              <option>Urgent</option>
            </select>
          </Field>
        </div>
        <div className="form-section-label">CONTACT DETAILS</div>
        <div className="form-grid">
          <Field label="Name">
            <input
              name="name"
              required
              minLength={2}
              maxLength={100}
              placeholder="Your name"
            />
          </Field>
          <Field label="Email">
            <input
              name="email"
              type="email"
              required
              maxLength={150}
              placeholder="name@example.com"
            />
          </Field>
        </div>
        <Field label="Phone (optional)">
          <input
            name="phone"
            type="tel"
            maxLength={40}
            placeholder="403-555-0100"
          />
        </Field>
        <p className="small muted">
          Use sample contact details. Confirmation emails appear in Workspace &
          activity as previews.
        </p>
        {error && <ErrorBox message={error} />}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
            Send to Lemmer
          </button>
        </div>
      </form>
    </Modal>
  );
}
