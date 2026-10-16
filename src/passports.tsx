import { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import QRCode from "qrcode";
import {
  Plus,
  Search,
  Hash,
  User,
  MapPin,
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  Wrench,
  Send,
  Activity,
  CheckSquare2,
  History,
  Info,
  FileText,
  ChevronRight,
  QrCode,
  ShieldCheck,
  ScanLine,
  Download,
  Copy,
  ExternalLink,
  Loader2,
  CheckCircle2,
  FlaskConical,
  BookOpen,
} from "lucide-react";
import { post, date, Asset } from "./api";
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
  AssetImage,
  IconLabel,
  DocumentModal,
} from "./shared";
import { ComponentForm } from "./expansion";
import { NewRequestModal } from "./dashboard";
export function Assets() {
  const { session } = useApp();
  const { data, error } = useData("/assets");
  const [search, setSearch] = useState(""),
    [add, setAdd] = useState(false);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <PageHeader
        title="Asset passports"
        subtitle="One physical asset. One identity. A service history that stays with it."
        actions={
          ["reception", "superuser"].includes(session.role) ? (
            <Link className="button primary" to="/registry">
              <Plus size={17} />
              Register asset
            </Link>
          ) : null
        }
      />
      <div className="asset-toolbar">
        <div className="input-with-icon">
          <Search size={18} />
          <input
            aria-label="Search assets"
            placeholder="Search model, serial, asset or customer…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span>{data.length} registered assets</span>
      </div>
      <div className="asset-grid">
        {data
          .filter((a: Asset) =>
            `${a.code} ${a.model} ${a.serial} ${a.customer}`
              .toLowerCase()
              .includes(search.toLowerCase()),
          )
          .map((a: Asset) => (
            <Link to={"/assets/" + a.id} className="asset-card" key={a.id}>
              <div className="asset-card-top">
                <span className="asset-code">{a.code}</span>
                <Badge value={a.condition} />
              </div>
              <AssetImage asset={a} large />
              <div className="asset-card-body">
                <span className="eyebrow">{a.manufacturer} EQUIPMENT</span>
                <h2>{a.model}</h2>
                <p>{a.name.replace(a.model + " ", "")}</p>
                <div className="asset-meta">
                  <IconLabel icon={Hash}>{a.serial}</IconLabel>
                  <IconLabel icon={User}>{a.customer}</IconLabel>
                  <IconLabel icon={MapPin}>{a.location}</IconLabel>
                </div>
                <div className="asset-card-footer">
                  <span>Open passport</span>
                  <ArrowUpRight size={18} />
                </div>
              </div>
            </Link>
          ))}
      </div>
      {add && <NewAssetModal onClose={() => setAdd(false)} />}
    </>
  );
}
function NewAssetModal({ onClose }: { onClose: () => void }) {
  const { refresh, toast } = useApp();
  const navigate = useNavigate();
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal
      title="Register an asset"
      subtitle="Create a unique passport for a physical piece of equipment."
      onClose={onClose}
    >
      <form
        className="form-body"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const a = await post(
              "/assets",
              Object.fromEntries(new FormData(e.currentTarget)),
            );
            refresh();
            toast("Asset registered. Its QR code is ready.");
            onClose();
            navigate("/assets/" + a.id);
          } catch (e: any) {
            setError(e.message);
            setBusy(false);
          }
        }}
      >
        <Field label="Equipment model">
          <input name="model" required placeholder="Manufacturer model" />
        </Field>
        <Field label="Asset name">
          <input
            name="name"
            placeholder="e.g. Rustproofing workshop unit"
            required
            minLength={3}
            maxLength={100}
          />
        </Field>
        <Field label="Serial number">
          <input
            name="serial"
            required
            minLength={2}
            maxLength={100}
            placeholder="Serial from the physical equipment"
          />
        </Field>
        <Field label="Customer / owner">
          <input name="customer" required minLength={2} maxLength={100} />
        </Field>
        <Field label="Location">
          <input
            name="location"
            required
            minLength={2}
            maxLength={100}
            placeholder="City, province"
          />
        </Field>
        {error && <ErrorBox message={error} />}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
            Register asset
          </button>
        </div>
      </form>
    </Modal>
  );
}
export function Timeline({ events }: { events: any[] }) {
  return events.length ? (
    <div className="timeline">
      {events.map((e) => (
        <div className="timeline-event" key={e.id}>
          <div className={"timeline-marker " + e.kind}>
            {e.kind === "service" ? (
              <Wrench size={15} />
            ) : e.kind === "request" ? (
              <Send size={14} />
            ) : (
              <Activity size={14} />
            )}
          </div>
          <div className="timeline-card">
            <div className="timeline-top">
              <span>
                {date(e.created_at)} <b>·</b> {e.actor}
              </span>
              {e.body.outcome && <Badge value={e.body.outcome} />}
            </div>
            <h3>{e.title}</h3>
            {e.body.work ? (
              <>
                {e.body.amendments?.length > 0 && (
                  <p>
                    <strong>Amended diagnosis:</strong> {e.body.diagnosis}.
                    Original and amendment retained below.
                  </p>
                )}
                <p>{e.body.work}</p>
                <div className="timeline-test">
                  <CheckSquare2 size={15} />
                  <span>{e.body.test}</span>
                </div>
                {e.body.parts?.length > 0 && (
                  <div className="part-chips">
                    {e.body.parts.map((p: string) => (
                      <span key={p}>{p}</span>
                    ))}
                  </div>
                )}
              </>
            ) : e.kind === "amendment" ? (
              <div>
                <p>{e.body.reason}</p>
                {Object.entries(e.body.changes || {}).map(([key, value]) => (
                  <p key={key}>
                    <strong>{key}: </strong>
                    {String(value)}
                  </p>
                ))}
                <small>
                  Original report retained · {e.body.original_event_id}
                </small>
              </div>
            ) : (
              <p>
                {e.body.description ||
                  e.body.observation ||
                  e.body.notes ||
                  (e.body.from ? `${e.body.from} → ${e.body.to}` : e.title)}
              </p>
            )}
            {e.body.source && (
              <small className="source-caption">{e.body.source}</small>
            )}
          </div>
        </div>
      ))}
    </div>
  ) : (
    <Empty icon={History} title="A new story starts here">
      Service work and inspections will appear in this asset’s timeline.
    </Empty>
  );
}
export function Passport() {
  const { id } = useParams();
  const { session } = useApp();
  const { data, error } = useData("/assets/" + id);
  const [tab, setTab] = useState("Service history"),
    [component, setComponent] = useState(false),
    [qr, setQr] = useState(false),
    [create, setCreate] = useState(false),
    [doc, setDoc] = useState<any>(null);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  const a: Asset = data.asset;
  return (
    <>
      <Link to="/assets" className="back-link">
        <ArrowLeft size={15} />
        All asset passports
      </Link>
      <PageHeader
        eyebrow={a.code + " / ASSET PASSPORT"}
        title={a.name}
        subtitle="A persistent record of this individual piece of equipment."
        actions={
          <>
            {session.role === "technician" && (
              <button
                className="button secondary"
                onClick={() => setComponent(true)}
              >
                Record component
              </button>
            )}
            <button className="button secondary" onClick={() => setQr(true)}>
              <QrCode size={17} />
              Equipment QR
            </button>
            <button className="button primary" onClick={() => setCreate(true)}>
              <Plus size={17} />
              Request service
            </button>
          </>
        }
      />
      <section className="passport-identity">
        <div className="passport-photo">
          <AssetImage asset={a} large />
        </div>
        <div className="passport-details">
          <div className="identity-title">
            <span className="eyebrow">
              {a.manufacturer} / {a.model}
            </span>
            <Badge value={a.condition} />
          </div>
          <div className="identity-fields">
            {[
              ["Asset ID", a.code],
              ["Serial number", a.serial],
              ["Manufacturer", a.manufacturer],
              ["Model", a.model],
              ["Product number", a.product_number || "Unknown"],
              ["Customer / owner", a.customer],
              ["Location", a.location],
            ].map(([k, v]) => (
              <div key={k}>
                <span>{k}</span>
                <strong>{v}</strong>
              </div>
            ))}
          </div>
          <div className="identity-bottom">
            <ShieldCheck size={16} />
            <span>
              History belongs to this serial number, across every service visit.
            </span>
          </div>
        </div>
      </section>
      <div className="passport-content">
        <section className="panel">
          <div className="tabs">
            {["Service history", "Documents", "Parts reference"].map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="panel-body">
            {tab === "Service history" ? (
              <Timeline events={data.events} />
            ) : tab === "Documents" ? (
              <div className="document-list">
                {data.documents.map((d: any) => (
                  <button key={d.id} onClick={() => setDoc(d)}>
                    <FileText size={22} />
                    <div>
                      <strong>{d.title}</strong>
                      <span>
                        Verified source · Printed revision {d.revision}
                      </span>
                    </div>
                    <ChevronRight size={18} />
                  </button>
                ))}
              </div>
            ) : (
              <>
                <div className="note-box">
                  <Info size={17} />
                  <p>
                    Selected parts from the manufacturer’s reference. Confirm
                    equipment revision and compatibility before ordering.
                  </p>
                </div>
                <table className="parts-table">
                  <thead>
                    <tr>
                      <th>PART NUMBER</th>
                      <th>COMPONENT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.parts).map(([p, n]) => (
                      <tr key={p}>
                        <td>
                          <code>{p}</code>
                        </td>
                        <td>{String(n)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </section>
        <aside className="passport-aside">
          <div className="panel">
            <div className="panel-header">
              <h2>Service requests</h2>
              <span className="count">{data.requests.length}</span>
            </div>
            <div className="mini-request-list">
              {data.requests.map((r: any) => (
                <Link to={"/requests/" + r.id} key={r.id}>
                  <span className="small muted">{r.code}</span>
                  <strong>{r.title}</strong>
                  <Badge value={r.status} />
                </Link>
              ))}
              {!data.requests.length && (
                <p className="muted">No requests yet.</p>
              )}
            </div>
          </div>
          <div className="inspection-placeholder">
            <ScanLine size={24} />
            <h3>Inspection intelligence</h3>
            <p>
              A place for future computer vision findings, linked to this exact
              asset.
            </p>
            <span className="tag">Integration planned</span>
          </div>
        </aside>
      </div>
      {component && (
        <Modal
          title="Record a replaced component"
          subtitle="Record actual installation dates. Only add an interval when you have a documented basis."
          onClose={() => setComponent(false)}
        >
          <ComponentForm assetId={a.id} />
        </Modal>
      )}
      {qr && (
        <QRModal
          asset={a}
          url={`${location.origin}/passport/${session.share}/${a.code}`}
          onClose={() => setQr(false)}
        />
      )}{" "}
      {create && (
        <NewRequestModal
          assets={[a]}
          selected={a.id}
          onClose={() => setCreate(false)}
        />
      )}{" "}
      {doc && <DocumentModal doc={doc} onClose={() => setDoc(null)} />}
    </>
  );
}
function QRModal({
  asset,
  url,
  onClose,
}: {
  asset: Asset;
  url: string;
  onClose: () => void;
}) {
  const [src, setSrc] = useState("");
  const { toast } = useApp();
  useEffect(() => {
    QRCode.toDataURL(url, {
      width: 600,
      margin: 3,
      color: { dark: "#142536" },
    }).then(setSrc);
  }, [url]);
  return (
    <Modal
      title="Equipment QR code"
      subtitle="Scan to open this asset’s customer Passport."
      onClose={onClose}
    >
      <div className="qr-body">
        {src ? (
          <img src={src} alt={`QR code for ${asset.code}`} />
        ) : (
          <Loader2 className="spin" />
        )}
        <h2>{asset.code}</h2>
        <p>
          {asset.model} · {asset.serial}
        </p>
        <div className="qr-url">{url}</div>
        <div className="qr-actions">
          <a
            className="button secondary"
            href={src}
            download={asset.code + "-qr.png"}
          >
            <Download size={16} />
            Download QR
          </a>
          <button
            className="button primary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(url);
                toast("Passport link copied.");
              } catch {
                toast("Copy the displayed Passport link.");
              }
            }}
          >
            <Copy size={16} />
            Copy link
          </button>
        </div>
        <a className="text-link" href={url} target="_blank" rel="noreferrer">
          Open customer view <ExternalLink size={14} />
        </a>
      </div>
    </Modal>
  );
}
export function PublicPassport() {
  const { share, code } = useParams();
  const { data, error } = useData(`/public/${share}/${code}`);
  const [create, setCreate] = useState(false),
    [confirmation, setConfirmation] = useState<any>(null);
  if (error)
    return (
      <main className="public-page">
        <ErrorBox message={error} />
      </main>
    );
  if (!data) return <Loading />;
  const a = data.asset;
  return (
    <main className="public-page">
      <header>
        <img src="/images/lemmer-logo.svg" alt="Lemmer" />
        <span>ASSET PASSPORT</span>
      </header>
      <div className="public-demo">
        <FlaskConical size={15} />
        Demonstration · Sample equipment and service records
      </div>
      <section className="public-identity">
        <span className="asset-code">{a.code}</span>
        <AssetImage asset={a} large />
        <div className="eyebrow">YOUR EQUIPMENT</div>
        <h1>{a.model}</h1>
        <p>{a.name}</p>
        <Badge value={a.condition} />
        <div className="public-serial">
          <span>Serial number</span>
          <strong>{a.serial}</strong>
        </div>
        <button
          className="button primary full big"
          onClick={() => setCreate(true)}
        >
          <Wrench size={18} />
          Get me running
        </button>
      </section>
      {confirmation && (
        <div className="public-confirmation">
          <CheckCircle2 size={27} />
          <h2>We’ve received your request.</h2>
          <p>
            Reference <strong>{confirmation.code}</strong>. Your request is
            connected to {a.code}.
          </p>
          <Badge value={confirmation.status} />
        </div>
      )}
      <section className="panel">
        <div className="panel-header">
          <h2>Service status</h2>
          <History size={18} />
        </div>
        <div className="mini-request-list">
          {data.requests.map((r: any) => (
            <div key={r.code}>
              <span className="small muted">
                {r.code} · {date(r.created_at)}
              </span>
              <strong>{r.title}</strong>
              <Badge value={r.status} />
            </div>
          ))}
        </div>
      </section>
      <section className="panel public-docs">
        <div className="panel-header">
          <h2>Product resources</h2>
          <BookOpen size={18} />
        </div>
        {data.documents.map((d: any) => (
          <a key={d.title} href={d.url} target="_blank" rel="noreferrer">
            <FileText size={17} />
            {d.title}
            <ExternalLink size={15} />
          </a>
        ))}
      </section>
      <footer>Lemmer Asset Passport · Service knowledge, connected.</footer>
      {create && (
        <NewRequestModal
          assets={[a]}
          selected={a.id}
          publicPath={`/public/${share}/${code}/requests`}
          onClose={() => setCreate(false)}
          onCreated={setConfirmation}
        />
      )}
    </main>
  );
}
