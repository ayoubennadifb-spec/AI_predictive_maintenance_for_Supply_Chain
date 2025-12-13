import type { ApiIdentity } from "./mlData";

// Default to same-origin API when VITE_API_BASE is not provided
const API_BASE =
  ((import.meta as any).env?.VITE_API_BASE as string | undefined)?.trim() ||
  (typeof window !== "undefined" ? window.location.origin : "");
const API_TOKEN = (import.meta as any).env?.VITE_API_TOKEN || "";

function buildJsonHeaders(identity?: ApiIdentity): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (identity?.user) headers["X-User"] = identity.user;
  if (identity?.role) headers["X-Role"] = identity.role;
  if (API_TOKEN) headers["X-API-KEY"] = API_TOKEN;
  return headers;
}

async function apiRequest<T>(
  path: string,
  options?: { method?: string; body?: any; identity?: ApiIdentity }
): Promise<T> {
  if (!API_BASE) throw new Error("API_BASE requis pour les APIs admin");
  const method = options?.method || "GET";
  const init: RequestInit = {
    method,
    headers: buildJsonHeaders(options?.identity),
  };
  if (options?.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let message = `Erreur API admin (${res.status})`;
    try {
      const json = (await res.json()) as any;
      if (json?.error) message = String(json.error);
      else if (json?.details) message = String(json.details);
      else if (json?.code) message = `${message} [${json.code}]`;
    } catch {
      const txt = await res.text().catch(() => "");
      if (txt) message = txt;
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Parts (Pièces)
// ---------------------------------------------------------------------------

export type AdminPart = {
  code: string;
  designation: string;
  criticite: string;
  stock_actuel: number;
  stock_securite: number;
  moyenne_m3: number;
  prevision_m1: number;
  ecart_pourcent: number;
  prix_unitaire: number;
  fournisseur: string;
  delai: number;
  n_ac_2025: number;
  approuve: boolean;
};

export type AdminPartInput = {
  code: string;
  designation?: string;
  criticite?: string;
  stock_actuel?: number;
  stock_securite?: number;
  moyenne_m3?: number;
  prevision_m1?: number;
  ecart_pourcent?: number;
  prix_unitaire?: number;
  fournisseur?: string;
  delai?: number;
  n_ac_2025?: number;
  approuve?: boolean;
};

export type AdminPartListResponse = {
  results: AdminPart[];
  count: number;
};

export async function adminListParts(params: {
  search?: string;
  criticite?: string;
  limit?: number;
  offset?: number;
  identity: ApiIdentity;
}): Promise<AdminPartListResponse> {
  const qp: string[] = [];
  if (params.search) qp.push(`search=${encodeURIComponent(params.search)}`);
  if (params.criticite) qp.push(`criticite=${encodeURIComponent(params.criticite)}`);
  if (typeof params.limit === "number") qp.push(`limit=${params.limit}`);
  if (typeof params.offset === "number") qp.push(`offset=${params.offset}`);
  const query = qp.length ? `?${qp.join("&")}` : "";
  return apiRequest<AdminPartListResponse>(`/api/admin/parts/${query}`, {
    identity: params.identity,
  });
}

export async function adminCreatePart(
  payload: AdminPartInput,
  identity: ApiIdentity
): Promise<AdminPart> {
  return apiRequest<AdminPart>("/api/admin/parts/", {
    method: "POST",
    body: payload,
    identity,
  });
}

export async function adminUpdatePart(
  code: string,
  payload: Partial<AdminPartInput>,
  identity: ApiIdentity
): Promise<AdminPart> {
  return apiRequest<AdminPart>(`/api/admin/parts/${encodeURIComponent(code)}/`, {
    method: "PATCH",
    body: payload,
    identity,
  });
}

export async function adminDeletePart(code: string, identity: ApiIdentity): Promise<void> {
  await apiRequest<{ ok: boolean }>(`/api/admin/parts/${encodeURIComponent(code)}/`, {
    method: "DELETE",
    identity,
  });
}

// ---------------------------------------------------------------------------
// Consumptions (Consommations)
// ---------------------------------------------------------------------------

export type AdminConsumption = {
  id: number;
  part_code: string;
  date: string;
  valeur: number;
  created_at: string;
};

export type AdminConsumptionListResponse = {
  results: AdminConsumption[];
  count: number;
};

export async function adminListConsumptions(params: {
  code?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
  identity: ApiIdentity;
}): Promise<AdminConsumptionListResponse> {
  const qp: string[] = [];
  if (params.code) qp.push(`code=${encodeURIComponent(params.code)}`);
  if (params.from) qp.push(`from=${encodeURIComponent(params.from)}`);
  if (params.to) qp.push(`to=${encodeURIComponent(params.to)}`);
  if (typeof params.limit === "number") qp.push(`limit=${params.limit}`);
  if (typeof params.offset === "number") qp.push(`offset=${params.offset}`);
  const query = qp.length ? `?${qp.join("&")}` : "";
  return apiRequest<AdminConsumptionListResponse>(`/api/admin/consumptions/${query}`, {
    identity: params.identity,
  });
}

export async function adminSaveConsumption(
  payload: { code: string; date: string; valeur: number },
  identity: ApiIdentity
): Promise<AdminConsumption> {
  return apiRequest<AdminConsumption>("/api/admin/consumptions/", {
    method: "POST",
    body: payload,
    identity,
  });
}

export async function adminUpdateConsumption(
  id: number,
  payload: Partial<{ date: string; valeur: number }>,
  identity: ApiIdentity
): Promise<AdminConsumption> {
  return apiRequest<AdminConsumption>(`/api/admin/consumptions/${id}/`, {
    method: "PATCH",
    body: payload,
    identity,
  });
}

export async function adminDeleteConsumption(id: number, identity: ApiIdentity): Promise<void> {
  await apiRequest<{ ok: boolean }>(`/api/admin/consumptions/${id}/`, {
    method: "DELETE",
    identity,
  });
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export type AdminUser = {
  id: number;
  username: string;
  email: string;
  nom: string;
  role: string;
  created_at: string;
};

export type AdminUserListResponse = {
  results: AdminUser[];
  count: number;
};

export async function adminListUsers(params: {
  search?: string;
  limit?: number;
  offset?: number;
  identity: ApiIdentity;
}): Promise<AdminUserListResponse> {
  const qp: string[] = [];
  if (params.search) qp.push(`search=${encodeURIComponent(params.search)}`);
  if (typeof params.limit === "number") qp.push(`limit=${params.limit}`);
  if (typeof params.offset === "number") qp.push(`offset=${params.offset}`);
  const query = qp.length ? `?${qp.join("&")}` : "";
  return apiRequest<AdminUserListResponse>(`/api/admin/users/${query}`, {
    identity: params.identity,
  });
}

export async function adminCreateUser(
  payload: { username: string; email?: string; nom?: string; role: string; password?: string },
  identity: ApiIdentity
): Promise<AdminUser> {
  return apiRequest<AdminUser>("/api/admin/users/", {
    method: "POST",
    body: payload,
    identity,
  });
}

export async function adminUpdateUser(
  id: number,
  payload: Partial<{ username: string; email: string; nom: string; role: string; password: string }>,
  identity: ApiIdentity
): Promise<AdminUser> {
  return apiRequest<AdminUser>(`/api/admin/users/${id}/`, {
    method: "PATCH",
    body: payload,
    identity,
  });
}

export async function adminDeleteUser(id: number, identity: ApiIdentity): Promise<void> {
  await apiRequest<{ ok: boolean }>(`/api/admin/users/${id}/`, {
    method: "DELETE",
    identity,
  });
}

