import {
  useState,
  useEffect,
  useRef,
  createContext,
  useContext,
  ReactNode,
} from "react";
import {
  Search,
  Loader2,
  AlertCircle,
  X,
  SprayCan,
  ArrowUpRight,
  FileText,
  History,
  BookOpen,
  ChevronDown,
  ExternalLink,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, Asset } from "./api";
type Context = {
  session: any;
  refresh: () => void;
  revision: number;
  toast: (s: string) => void;
  setSession: (s: any) => void;
};
export const AppContext = createContext<Context>(null!);
export const useApp = () => useContext(AppContext);
export function useData(path: string) {
  const { revision } = useApp();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const previousPath = useRef(path);
  useEffect(() => {
    let active = true;
    if (previousPath.current !== path) {
      setData(null);
      previousPath.current = path;
    }
    setError("");
    api(path)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [path, revision]);
  return { data, error, setData };
}
export const IconLabel = ({
  icon: Icon,
  children,
}: {
  icon: any;
  children: ReactNode;
}) => (
  <span className="icon-label">
    <Icon size={15} />
    {children}
  </span>
);
export function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value.toLowerCase().replaceAll(" ", "-")}>
      <i />
      {value}
    </span>
  );
}
export function Empty({
  icon: Icon = Search,
  title,
  children,
}: {
  icon?: any;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading-page">
      <Loader2 className="spin" size={25} />
      <span>Opening your workspace…</span>
    </div>
  );
}
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={18} />
      <span>{message}</span>
    </div>
  );
}
export function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={"modal " + (wide ? "wide" : "")}
      aria-label={title}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close dialog"
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function AssetImage({
  asset,
  large = false,
}: {
  asset: Asset;
  large?: boolean;
}) {
  return (
    <div className={"asset-image " + (large ? "large" : "")}>
      {asset.model === "L-65" ? (
        <SprayCan size={large ? 110 : 36} strokeWidth={1} />
      ) : (
        <img
          src={asset.image}
          alt={`${asset.model} equipment`}
          loading="lazy"
        />
      )}
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="heading-actions">{actions}</div>
    </div>
  );
}
export function DocumentModal({
  doc,
  onClose,
}: {
  doc: any;
  onClose: () => void;
}) {
  return (
    <Modal
      title={doc.title}
      subtitle={"Product knowledge · Source revision " + doc.revision}
      onClose={onClose}
      wide
    >
      <div className="document-markdown">
        <ReactMarkdown>{doc.content}</ReactMarkdown>
      </div>
      <div className="modal-actions">
        <a
          href={doc.url}
          target="_blank"
          rel="noreferrer"
          className="button secondary"
        >
          Open manufacturer source <ExternalLink size={15} />
        </a>
      </div>
    </Modal>
  );
}
export function SourceCard({ source }: { source: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="source-card">
      <button onClick={() => setOpen(!open)}>
        <span className={"source-type " + source.kind}>
          {source.kind === "manual" ? (
            <FileText size={16} />
          ) : source.kind === "history" ? (
            <History size={16} />
          ) : (
            <BookOpen size={16} />
          )}
        </span>
        <div>
          <span className="source-id">
            {source.id} <b>·</b>{" "}
            {(
              {
                history: "This asset’s service history",
                manual: "Product manual",
                catalogue: "Product specification",
                procedure: "Human-approved procedure",
                case: "Repair record · not a general procedure",
              } as Record<string, string>
            )[source.kind] || "Source document"}
          </span>
          <strong>{source.title}</strong>
          {source.outcome && (
            <small>
              {source.outcome} · {source.source}
            </small>
          )}
        </div>
        <ChevronDown size={16} className={open ? "rotate" : ""} />
      </button>
      {open && (
        <div className="source-expanded">
          <p className="small muted">
            Applicability: {source.model || "Unknown"}
            {source.product_number
              ? ` · Product ${source.product_number}`
              : ""}{" "}
            · Revision: {source.revision || "Unknown"} · Page:{" "}
            {source.page || "See source passage"}
          </p>
          {source.source && <p className="small muted">{source.source}</p>}
          <p style={{ whiteSpace: "pre-wrap" }}>{source.content}</p>
          {source.url && (
            <a
              href={source.url}
              className="text-link"
              target="_blank"
              rel="noreferrer"
            >
              Manufacturer source <ExternalLink size={13} />
            </a>
          )}
        </div>
      )}
    </div>
  );
}
