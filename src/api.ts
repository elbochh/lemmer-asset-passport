export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const data = await response.json().catch(() => ({
    detail: "The server could not respond. Please try again.",
  }));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((x: any) => x.msg).join("; ")
      : data.detail;
    throw new Error(detail || "Something went wrong. Please try again.");
  }
  return data;
}
export const post = (path: string, body: any = {}) =>
  api(path, { method: "POST", body: JSON.stringify(body) });
export const patch = (path: string, body: any) =>
  api(path, { method: "PATCH", body: JSON.stringify(body) });
export type Asset = {
  id: string;
  code: string;
  name: string;
  model: string;
  product_number?: string;
  serial: string;
  manufacturer: string;
  customer: string;
  location: string;
  condition: string;
  image: string;
  created_at: string;
};
export type ServiceRequest = {
  id: string;
  code: string;
  title: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  operating: string;
  technician: string;
  guidance?: { status: string; message: string; run_id?: string };
  asset: Asset;
  asset_id: string;
  contact: { name: string; email: string; phone: string };
  created_at: string;
  updated_at: string;
  draft: any;
  version: number;
};
export const date = (s: string) =>
  new Date(
    /^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T12:00:00` : s,
  ).toLocaleDateString("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
export const relative = (s: string) => {
  let h = Math.floor((Date.now() - new Date(s).getTime()) / 3600000);
  return h < 1
    ? "Just now"
    : h < 24
      ? `${h}h ago`
      : `${Math.floor(h / 24)}d ago`;
};
