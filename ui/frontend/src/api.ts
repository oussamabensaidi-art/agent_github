// Client de l'API de suivi. Session par cookie ; en-tête anti-CSRF sur toute écriture.
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string>) };
  if (method !== "GET") {
    headers["X-Requested-With"] = "calipso-ui";
    if (init.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`/ui/api${path}`, { ...init, method, headers, credentials: "same-origin" });
  if (res.status === 401 && path !== "/login") onUnauthorized();
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // corps non JSON
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const jsonBody = (body: unknown) => JSON.stringify(body);

export function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}
