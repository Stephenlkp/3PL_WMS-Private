import type { User } from "./types";

const configuredApi = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** The browser always calls this site. Next proxies /api to the local API, including from https pages. */
export function apiBase(): string {
  if (typeof window === "undefined") return configuredApi;
  try {
    const api = new URL(configuredApi);
    const apiIsLocal = api.hostname === "localhost" || api.hostname === "127.0.0.1";
    if (apiIsLocal) return "";
  } catch {
    return configuredApi;
  }
  return configuredApi;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function errorMessage(body: { detail?: unknown; code?: string } | null, status: number) {
  if (!body) return `Request failed (${status})`;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((item) => (typeof item?.msg === "string" ? item.msg : "Invalid value")).join(", ");
  }
  return `Request failed (${status})`;
}

let refreshing: Promise<string> | null = null;

async function refreshAccess(): Promise<string> {
  const refresh = localStorage.getItem("wms_refresh");
  if (!refresh) throw new ApiError(401, "Session expired");
  const response = await fetch(`${apiBase()}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!response.ok) {
    localStorage.removeItem("wms_access");
    localStorage.removeItem("wms_refresh");
    localStorage.removeItem("wms_user");
    throw new ApiError(401, "Session expired");
  }
  const data = await response.json();
  localStorage.setItem("wms_access", data.access_token);
  localStorage.setItem("wms_refresh", data.refresh_token);
  localStorage.setItem("wms_user", JSON.stringify(data.user));
  return data.access_token as string;
}

export function currentUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("wms_user");
  return raw ? (JSON.parse(raw) as User) : null;
}

export function saveSession(data: { access_token: string; refresh_token: string; user: User }) {
  localStorage.setItem("wms_access", data.access_token);
  localStorage.setItem("wms_refresh", data.refresh_token);
  localStorage.setItem("wms_user", JSON.stringify(data.user));
}

export function clearSession() {
  localStorage.removeItem("wms_access");
  localStorage.removeItem("wms_refresh");
  localStorage.removeItem("wms_user");
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = typeof window !== "undefined" ? localStorage.getItem("wms_access") : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiBase()}${path}`, { ...options, headers });
  if (response.status === 401 && retry && !path.includes("/auth/login") && !path.includes("/auth/refresh")) {
    try {
      refreshing = refreshing || refreshAccess();
      const access = await refreshing;
      refreshing = null;
      headers.set("Authorization", `Bearer ${access}`);
      return api<T>(path, { ...options, headers }, false);
    } catch (error) {
      refreshing = null;
      if (typeof window !== "undefined") window.location.href = "/login";
      throw error;
    }
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, errorMessage(body, response.status), body?.code);
  }
  const type = response.headers.get("content-type") || "";
  if (!type.includes("application/json")) return (await response.blob()) as T;
  return response.json();
}

export function fileUrl(id: string) {
  const token = localStorage.getItem("wms_access") || "";
  return `${apiBase()}/api/v1/files/${id}/content?access_token=${encodeURIComponent(token)}`;
}

export function barcodeUrl(productId: string, style: "code128" | "qr" = "code128", revision?: string) {
  const token = localStorage.getItem("wms_access") || "";
  const version = revision ? `&v=${encodeURIComponent(revision)}` : "";
  return `${apiBase()}/api/v1/products/${productId}/barcode?style=${style}${version}&access_token=${encodeURIComponent(token)}`;
}

export function locationBarcodeUrl(locationId: string) {
  const token = localStorage.getItem("wms_access") || "";
  return `${apiBase()}/api/v1/locations/${locationId}/barcode?style=qr&access_token=${encodeURIComponent(token)}`;
}

export async function downloadReport(path: string, filename: string) {
  const blob = await api<Blob>(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function isStaff(role?: string) {
  return !!role && role !== "customer";
}

export function isManager(role?: string) {
  return role === "admin" || role === "warehouse_supervisor";
}
