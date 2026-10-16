import { Operations, Procedures, Receipt } from "./operations";
import { useState, useEffect, useRef } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  ArrowUpRight,
  ArrowRight,
  Search,
  LayoutDashboard,
  PanelsTopLeft,
  BookOpen,
  FlaskConical,
  Wrench,
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  X,
  Loader2,
  ScanLine,
  ShieldCheck,
  Sparkles,
  History,
  LogOut,
  Menu,
  Settings2,
  Info,
  LifeBuoy,
} from "lucide-react";
import { api, post, Asset, ServiceRequest } from "./api";
import {
  AppContext,
  useApp,
  useData,
  Modal,
  Empty,
  Loading,
  ErrorBox,
} from "./shared";
import { Dashboard, Requests } from "./dashboard";
import { Assets, Passport } from "./passports";
import { ServiceWorkspace } from "./service";
import { Reception, TechnicianInbox } from "./intake";
import { Knowledge, Evaluation, Settings } from "./knowledge";
import {
  AccountAccess,
  QRAccess,
  Catalog,
  Customers,
  Registry,
  MyAssets,
  OwnerPassport,
  PartsRequests,
  Vehicles,
} from "./expansion";

function Welcome({ onStart }: { onStart: (s: any) => void }) {
  const [account, setAccount] = useState(
    !!new URLSearchParams(location.search).get("invite"),
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <main className="welcome">
      <div className="welcome-top">
        <img src="/images/lemmer-logo.svg" alt="Lemmer" />
        <span>ASSET PASSPORT</span>
      </div>
      <button
        className="button secondary customer-login"
        onClick={() => setAccount(true)}
      >
        Staff / customer sign in
      </button>
      {account && <AccountAccess onClose={() => setAccount(false)} />}
      <div className="welcome-grid">
        <section>
          <div className="eyebrow orange">SERVICE KNOWLEDGE, CONNECTED</div>
          <h1>
            Every asset.
            <br />
            Every repair.
            <br />
            <em>One lasting record.</em>
          </h1>
          <p>
            Meet your equipment’s service memory. Identify an asset, find
            relevant repair knowledge, and make the next service decision with
            better context.
          </p>
          <button
            className="button primary big"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await post("/demo/start");
                onStart(await api("/session"));
              } catch (e: any) {
                setError(e.message);
                setBusy(false);
              }
            }}
          >
            {busy ? (
              <Loader2 className="spin" size={18} />
            ) : (
              <ArrowRight size={18} />
            )}
            Open technician workspace
          </button>
          <button
            className="button secondary welcome-reception"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await post("/demo/start");
                await post("/session/technician", { name: "Taylor Brooks" });
                onStart(await api("/session"));
              } catch (e: any) {
                setError(e.message);
                setBusy(false);
              }
            }}
          >
            <ScanLine size={18} />
            Try reception
          </button>
          <p className="small muted">
            No signup required · Your own persistent sample workspace
          </p>
          {error && <ErrorBox message={error} />}
          <div className="welcome-points">
            <span>
              <ScanLine size={18} />
              Equipment-specific QR
            </span>
            <span>
              <Sparkles size={18} />
              Evidence-backed assistance
            </span>
            <span>
              <History size={18} />
              History that grows
            </span>
          </div>
        </section>
        <div className="welcome-product">
          <div className="product-halo" />
          <img
            src="/images/catalog/L015-201.webp"
            alt="Lemmer RP-460HD rustproofing gun"
          />
          <div className="floating-passport">
            <div className="tiny-icon">
              <ShieldCheck size={20} />
            </div>
            <div>
              <strong>RP-460HD · Asset LM-1042</strong>
              <span>Service history connected</span>
            </div>
            <CheckCircle2 size={20} className="green" />
          </div>
          <span className="product-caption">
            LEMMER RP-460HD / RUSTPROOFING GUN
          </span>
        </div>
      </div>
      <footer>
        <span>Built for the people who keep equipment running.</span>
        <span>Demo only · Synthetic customers and repair cases</span>
      </footer>
    </main>
  );
}
function Shell() {
  const { session, setSession, refresh } = useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const [menu, setMenu] = useState(false),
    [search, setSearch] = useState(false),
    [help, setHelp] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setMenu(false);
    window.scrollTo(0, 0);
  }, [location.pathname]);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1025px)");
    const closeOnDesktop = () => {
      if (desktop.matches) setMenu(false);
    };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);
  useEffect(() => {
    if (!menu) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const drawer = sidebarRef.current;
    drawer?.querySelector<HTMLButtonElement>(".mobile-nav-close")?.focus();
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        setMenu(false);
      }
      if (e.key !== "Tab" || !drawer) return;
      const controls = Array.from(
        drawer.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), select, [tabindex="0"]',
        ),
      ).filter((element) => element.getClientRects().length);
      const first = controls[0],
        last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKey);
      menuButtonRef.current?.focus();
    };
  }, [menu]);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (
        (e.metaKey || e.ctrlKey) &&
        e.key === "k" &&
        session.role !== "customer"
      ) {
        e.preventDefault();
        setSearch(true);
      }
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [session.role]);
  const reception = session.role === "reception";
  const external = session.role === "customer";
  const [pendingParts, setPendingParts] = useState(0);
  useEffect(() => {
    let active = true;
    const load = () =>
      api("/parts-requests")
        .then((xs) => {
          if (active)
            setPendingParts(
              xs.filter((x: any) => x.status === "Requested").length,
            );
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [session.role]);
  const nav = external
    ? ([
        ["/my-assets", "My passports", PanelsTopLeft],
        ["/catalog", "Rustproofing products", BookOpen],
        ["/parts-requests", "My parts requests", Wrench],
      ] as const)
    : reception
      ? ([
          ["/reception", "New intake", ScanLine],
          ["/requests", "Open jobs", Wrench],
          ["/customers", "Customers", PanelsTopLeft],
          ["/registry", "Register equipment", PanelsTopLeft],
          ["/parts-requests", "Parts inbox", Wrench],

          ["/catalog", "Rustproofing products", BookOpen],

          ["/assets", "Asset passports", PanelsTopLeft],
        ] as const)
      : ([
          ["/", "Overview", LayoutDashboard],
          ["/my-work", "My work queue", Wrench],

          ["/catalog", "Rustproofing products", BookOpen],
          ["/requests", "Service requests", Wrench],
          ["/assets", "Asset passports", PanelsTopLeft],
          ["/procedures", "Approved procedures", BookOpen],
          ["/knowledge", "Records & documents", BookOpen],
          ...(session.role === "superuser"
            ? [
                ["/operations", "Administration", Settings2] as const,
                ["/reception", "New intake", ScanLine] as const,
                ["/customers", "Customers", PanelsTopLeft] as const,
                ["/registry", "Register equipment", PanelsTopLeft] as const,
              ]
            : []),
          ["/evaluation", "AI evaluation", FlaskConical],
        ] as const);
  return (
    <div className="app-shell">
      <aside
        ref={sidebarRef}
        id="workspace-navigation"
        className={"sidebar " + (menu ? "open" : "")}
        role={menu ? "dialog" : undefined}
        aria-modal={menu || undefined}
        aria-label="Workspace navigation"
      >
        <button
          className="icon-button mobile-nav-close"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        >
          <X size={20} />
        </button>
        <Link to="/" className="brand">
          <img src="/images/lemmer-logo.svg" alt="Lemmer" />
          <span>ASSET PASSPORT</span>
        </Link>
        <div className="workspace-label">
          <span className="workspace-monogram">L</span>
          <div>
            <strong>Lemmer Service</strong>
            <small>
              {session.role === "reception"
                ? "Reception workspace"
                : external
                  ? "Customer workspace"
                  : session.role === "superuser"
                    ? "Calgary super-user"
                    : "Calgary technician"}
            </small>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map(([path, label, Icon]) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={() =>
                location.pathname === path ||
                (path !== "/" && location.pathname.startsWith(path + "/"))
                  ? "active"
                  : ""
              }
            >
              <Icon size={19} />
              <span>{label}</span>
              {path === "/parts-requests" && reception && pendingParts > 0 && (
                <span className="parts-notification">{pendingParts}</span>
              )}
              {path === "/requests" && <span className="nav-dot" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="demo-note">
            <FlaskConical size={18} />
            <strong>A space to explore</strong>
            <p>
              Sample equipment. Real workflow.
              <br />
              Your changes stay in this demo.
            </p>
            <button onClick={() => setHelp(true)}>
              How to try the demo <ArrowUpRight size={14} />
            </button>
          </div>
          {!external && (
            <NavLink to="/settings" className="settings-link">
              <Settings2 size={18} />
              Workspace & activity
            </NavLink>
          )}
          <div className="user-card">
            <div className="avatar">
              {session.technician
                .split(" ")
                .map((x: string) => x[0])
                .join("")}
            </div>
            <div>
              <strong>{session.technician}</strong>
              <span>
                {session.role === "reception"
                  ? "Receptionist"
                  : external
                    ? "Customer"
                    : session.role === "superuser"
                      ? "Super-user"
                      : "Service technician"}
              </span>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={async () => {
                await post("/session/logout");
                setSession(null);
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      {menu && (
        <button
          className="mobile-backdrop"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <div className="main-shell" inert={menu}>
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              ref={menuButtonRef}
              aria-label="Open navigation"
              aria-expanded={menu}
              aria-controls="workspace-navigation"
              onClick={() => setMenu(true)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {nav.find(([p]) =>
                p === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(p),
              )?.[1] || "Settings"}
            </strong>
          </div>
          <div className="topbar-actions">
            {session.demo && (
              <select
                className="demo-account-switch"
                aria-label="Demo account"
                value={session.account_value || session.technician}
                onChange={async (e) => {
                  await post("/accounts/switch", {
                    name: e.target.value,
                  });
                  const next = await api("/session");
                  setSession(next);
                  refresh();
                  navigate(
                    next.role === "superuser"
                      ? "/operations"
                      : next.role === "reception"
                        ? "/reception"
                        : next.role === "customer"
                          ? "/my-assets"
                          : "/my-work",
                  );
                }}
              >
                {(
                  session.accounts ||
                  session.technicians.map((name: string) => ({
                    name,
                    role: "technician",
                  }))
                ).map((a: any) => (
                  <option key={a.name} value={a.name}>
                    {a.label || a.name} ·{" "}
                    {a.role === "reception"
                      ? "Reception"
                      : a.role === "customer"
                        ? "Customer"
                        : a.role === "superuser"
                          ? "Super-user"
                          : "Technician"}
                  </option>
                ))}
              </select>
            )}
            {!external && (
              <button
                className="search-trigger"
                aria-label="Search equipment or requests"
                onClick={() => setSearch(true)}
              >
                <Search size={16} />
                <span>Search equipment or requests</span>
                <kbd>⌘ K</kbd>
              </button>
            )}
            <span className="environment">
              <i />
              Demo
            </span>
            <button
              className="icon-button"
              aria-label="Demo help"
              onClick={() => setHelp(true)}
            >
              <LifeBuoy size={19} />
            </button>
          </div>
        </header>
        <main className="page-content">
          {external ? (
            <Routes>
              <Route path="/my-assets" element={<MyAssets />} />
              <Route path="/my-assets/:id" element={<OwnerPassport />} />
              <Route path="/parts-requests" element={<PartsRequests />} />
              <Route path="/catalog" element={<Catalog />} />
              <Route path="*" element={<Navigate to="/my-assets" replace />} />
            </Routes>
          ) : (
            <Routes>
              <Route
                path="/"
                element={
                  reception ? (
                    <Navigate to="/reception" replace />
                  ) : (
                    <Dashboard />
                  )
                }
              />
              <Route
                path="/reception"
                element={
                  ["reception", "superuser"].includes(session.role) ? (
                    <Reception />
                  ) : (
                    <Navigate to="/my-work" replace />
                  )
                }
              />
              <Route
                path="/my-work"
                element={
                  reception ? (
                    <Navigate to="/reception" replace />
                  ) : (
                    <TechnicianInbox />
                  )
                }
              />
              <Route
                path="/operations"
                element={
                  session.role === "superuser" ? (
                    <Operations />
                  ) : (
                    <Navigate to="/" replace />
                  )
                }
              />
              <Route path="/procedures" element={<Procedures />} />
              <Route path="/requests/:id/receipt" element={<Receipt />} />
              <Route path="/requests" element={<Requests />} />
              <Route
                path="/requests/:id"
                element={<ServiceWorkspace key={location.pathname} />}
              />
              <Route path="/assets" element={<Assets />} />
              <Route path="/assets/:id" element={<Passport />} />
              <Route
                path="/knowledge"
                element={
                  reception ? (
                    <Navigate to="/reception" replace />
                  ) : (
                    <Knowledge />
                  )
                }
              />
              <Route
                path="/evaluation"
                element={
                  reception ? (
                    <Navigate to="/reception" replace />
                  ) : (
                    <Evaluation />
                  )
                }
              />
              <Route path="/settings" element={<Settings />} />
              <Route path="/catalog" element={<Catalog />} />
              <Route path="/customers" element={<Customers />} />
              <Route
                path="/registry"
                element={
                  ["reception", "superuser"].includes(session.role) ? (
                    <Registry />
                  ) : (
                    <Navigate to="/assets" replace />
                  )
                }
              />
              <Route path="/parts-requests" element={<PartsRequests />} />
              <Route path="/vehicles" element={<Vehicles />} />
              <Route path="/my-assets/:id" element={<OwnerPassport />} />
              <Route
                path="*"
                element={
                  <Empty title="This page could not be found">
                    <Link to="/">Return to overview</Link>
                  </Empty>
                }
              />
            </Routes>
          )}
        </main>
        <footer className="app-footer">
          <span>
            LEMMER <b> / </b> ASSET PASSPORT
          </span>
          <span>Every service adds to the story.</span>
        </footer>
      </div>
      {search && <SearchModal onClose={() => setSearch(false)} />}{" "}
      {help && (
        <Modal
          title="One complete service journey"
          subtitle="Try the demo in about five minutes."
          onClose={() => setHelp(false)}
        >
          <ol className="demo-steps">
            <li>
              <strong>Open LM-1042’s request</strong>
              <p>
                Start with “Pump runs, but will not prime” in Service requests.
              </p>
            </li>
            <li>
              <strong>Receive service assistance automatically</strong>
              <p>
                Guidance prepares automatically. Review possible causes, source
                cases and the separate evidence review.
              </p>
            </li>
            <li>
              <strong>Record the actual repair</strong>
              <p>
                Complete diagnosis, work, parts, test and outcome. Finalize the
                report.
              </p>
            </li>
            <li>
              <strong>See the history grow</strong>
              <p>
                Open the Asset Passport to see the recorded repair. Submit
                reusable knowledge for human review before it becomes a shared
                procedure.
              </p>
            </li>
            <li>
              <strong>Compare a second asset</strong>
              <p>
                LM-1043 is another rustproofing variant, with its own serial and
                service history.
              </p>
            </li>
          </ol>
          <div className="note-box">
            <Info size={18} />
            <p>
              Seeded repair cases are synthetic. Emails are previews. Computer
              vision is reserved for a later phase.
            </p>
          </div>
        </Modal>
      )}
    </div>
  );
}
function SearchModal({ onClose }: { onClose: () => void }) {
  const { data } = useData("/dashboard");
  const [q, setQ] = useState("");
  return (
    <Modal title="Find it in your workspace" onClose={onClose}>
      <div className="search-modal-body">
        <div className="input-with-icon">
          <Search size={19} />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Asset ID, serial, customer or request…"
            aria-label="Search workspace"
          />
        </div>
        {q && data ? (
          <div className="search-results">
            {data.assets
              .filter((a: Asset) =>
                `${a.code} ${a.serial} ${a.model} ${a.customer}`
                  .toLowerCase()
                  .includes(q.toLowerCase()),
              )
              .slice(0, 5)
              .map((a: Asset) => (
                <Link to={"/assets/" + a.id} key={a.id} onClick={onClose}>
                  <PanelsTopLeft size={18} />
                  <div>
                    <strong>
                      {a.code} · {a.model}
                    </strong>
                    <span>
                      {a.serial} · {a.customer}
                    </span>
                  </div>
                  <ChevronRight size={16} />
                </Link>
              ))}
            {data.requests
              .filter((r: ServiceRequest) =>
                `${r.code} ${r.title}`.toLowerCase().includes(q.toLowerCase()),
              )
              .slice(0, 5)
              .map((r: ServiceRequest) => (
                <Link to={"/requests/" + r.id} key={r.id} onClick={onClose}>
                  <Wrench size={18} />
                  <div>
                    <strong>{r.title}</strong>
                    <span>{r.code}</span>
                  </div>
                  <ChevronRight size={16} />
                </Link>
              ))}
          </div>
        ) : (
          <p className="muted small">
            Search all equipment and service requests in this demo.
          </p>
        )}
      </div>
    </Modal>
  );
}
function Root() {
  const [session, setSession] = useState<any>(undefined),
    [revision, setRevision] = useState(0),
    [message, setMessage] = useState("");
  const location = useLocation();
  const isPublic = location.pathname.startsWith("/passport/");
  useEffect(() => {
    api("/session")
      .then(setSession)
      .catch(() => setSession(null));
  }, [isPublic]);
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(""), 4500);
    return () => clearTimeout(t);
  }, [message]);
  return (
    <AppContext.Provider
      value={{
        session,
        setSession,
        revision,
        refresh: () => setRevision((r) => r + 1),
        toast: setMessage,
      }}
    >
      {isPublic ? (
        <Routes>
          <Route path="/passport/:share/:code" element={<QRAccess />} />
        </Routes>
      ) : session === undefined ? (
        <Loading />
      ) : session && !session.legacy_workspace ? (
        <Shell />
      ) : (
        <Welcome onStart={setSession} />
      )}{" "}
      {message && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {message}
          <button
            onClick={() => setMessage("")}
            aria-label="Dismiss notification"
          >
            <X size={16} />
          </button>
        </div>
      )}
    </AppContext.Provider>
  );
}
export default function App() {
  return (
    <BrowserRouter>
      <Root />
    </BrowserRouter>
  );
}
