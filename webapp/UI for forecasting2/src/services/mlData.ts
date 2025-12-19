type MLRawItem = {
  code: string;
  designation: string;
  criticite: string;
  stockActuel: number;
  moyenneM3: number;
  previsionM1: number;
  ecartPourcent: number;
  prixUnitaire: number;
  fournisseur: string;
  delai: number;
  n_ac_2025: number;
};

const mapCriticite = (value: string | undefined): 'urgent' | 'moyen' | 'normal' => {
  const v = (value || '').toString().trim().toLowerCase();
  if (v === 'a' || v === 'urgent') return 'urgent';
  if (v === 'b' || v === 'moyen') return 'moyen';
  return 'normal';
};

let cache: MLRawItem[] | null = null;
let stockSecuriteMap: Record<string, number> | null = null;

// Default to same-origin API when VITE_API_BASE is not provided (fixes 404 on dashboard)
const API_BASE =
  ((import.meta as any).env?.VITE_API_BASE as string | undefined)?.trim() ||
  (typeof window !== "undefined" ? window.location.origin : "");
const API_TOKEN = (import.meta as any).env?.VITE_API_TOKEN || "";

export interface ApiIdentity {
  user?: string;
  role?: string;
}

function buildJsonHeaders(identity?: ApiIdentity): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (identity?.user) headers["X-User"] = identity.user;
  if (identity?.role) headers["X-Role"] = identity.role;
  if (API_TOKEN) headers["X-API-KEY"] = API_TOKEN;
  return headers;
}

async function fetchOrNull<T>(path: string, enforceApi = false): Promise<T | null> {
  if (!API_BASE) {
    if (enforceApi) throw new Error("API_BASE non défini");
    return null;
  }
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      headers: API_TOKEN ? { "X-API-KEY": API_TOKEN } : undefined,
      credentials: "include",
    });
    if (!res.ok) {
      if (enforceApi) throw new Error(`API ${path} status ${res.status}`);
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    if (enforceApi) throw err;
    return null;
  }
}

async function loadRaw(options?: { forceApi?: boolean }): Promise<MLRawItem[]> {
  if (cache && !options?.forceApi) return cache;
  const apiData = await fetchOrNull<MLRawItem[]>("/api/previsions/", true);
  cache = apiData;
  return apiData;
}

async function loadStockSecuriteMap(): Promise<Record<string, number>> {
  if (stockSecuriteMap) return stockSecuriteMap;
  if (!API_BASE) {
    try {
      stockSecuriteMap = (await import("../assets/stock_securite.json")).default as Record<string, number>;
    } catch {
      stockSecuriteMap = {};
    }
    return stockSecuriteMap;
  }
  // If API is present, rely on backend data only (no fallback file)
  stockSecuriteMap = {};
  return stockSecuriteMap;
}

export async function loadPrevisions(): Promise<{
  code: string;
  designation: string;
  type: string;
  criticite: string;
  stockActuel: number;
  moyenneM3: number;
  stockSecurite: number;
  previsionM1: number;
  n_ac_2025: number;
  ecartPourcent: number;
  prixUnitaire: number;
  fournisseur: string;
  delai: number;
  approved?: boolean;
  historique: { mois: string; valeur: number }[];
}[]> {
  if (!API_BASE) throw new Error("API_BASE requis pour loadPrevisions");
  const [raw, stockMap, approved] = await Promise.all([
    loadRaw(),
    loadStockSecuriteMap(),
    fetchOrNull<{ approved: string[] }>("/api/approvals/", true),
  ]);
  const approvedSet = new Set(approved?.approved || []);
  return raw.map((r) => ({
    code: r.code,
    designation: r.designation,
    type: "Accouplement",
    criticite: mapCriticite(r.criticite),
    stockActuel: r.stockActuel,
    moyenneM3: r.moyenneM3,
    // Stock de sécurité prioritaire depuis le mapping, sinon fallback sur moyenne M-3
    stockSecurite: stockMap[r.code] ?? r.moyenneM3,
    previsionM1: r.previsionM1,
    n_ac_2025: typeof r.n_ac_2025 === "number" ? r.n_ac_2025 : r.previsionM1,
    ecartPourcent: r.ecartPourcent,
    prixUnitaire: r.prixUnitaire,
    fournisseur: r.fournisseur,
    delai: r.delai,
    historique: [],
    approved: approvedSet.has(r.code),
  }));
}

export async function loadConsommations(date?: string): Promise<{ code: string; prevision: number; consommationReelle: number | null }[]> {
  if (!API_BASE) throw new Error("API_BASE requis pour loadConsommations");
  const raw = await loadRaw({ forceApi: true });
  const query = date ? `?month=${date.slice(0, 7)}` : "";
  const apiExisting = await fetchOrNull<
    { code: string; date: string; valeur: number }[]
  >("/api/consommations/" + query, true);
  const existingByCode = new Map<string, number>();
  // Certains historiques peuvent contenir plusieurs lignes par code/mois : on cumule.
  (apiExisting || []).forEach((r) => {
    const prev = existingByCode.get(r.code) ?? 0;
    existingByCode.set(r.code, prev + Number(r.valeur ?? 0));
  });

  return raw.map((r) => ({
    code: r.code,
    // Prévision pour la saisie : quantité à commander/prévoir pour le mois suivant (n_ac_2025 si dispo, sinon prévisionM1).
    prevision: r.n_ac_2025 ?? r.previsionM1,
    consommationReelle: existingByCode.get(r.code) ?? null,
  }));
}

export type SaveConsommationsResponse = {
  saved: { code: string; date: string; valeur: number }[];
  errors: any[];
  // previsionM1 = n_pm (prév. mensuelle ML), n_ac_2025 = NAC recalculé
  predictions?: { code: string; previsionM1: number; n_ac_2025: number }[];
};

export async function saveConsommations(
  payload: { code: string; date: string; valeur: number | null }[],
  identity?: ApiIdentity
): Promise<SaveConsommationsResponse | void> {
  if (!API_BASE) throw new Error("API_BASE requis pour saveConsommations");
  const res = await fetch(`${API_BASE}/api/consommations/`, {
    method: "POST",
    headers: buildJsonHeaders(identity),
    credentials: "include",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Enregistrement échoué (${res.status}): ${txt}`);
  }
  const json = (await res.json()) as SaveConsommationsResponse;
  // bust cache so next load pulls updated forecasts
  cache = null;
  return json;
}

export async function resetConsommations(
  opts: { month?: string; date?: string },
  identity?: ApiIdentity
): Promise<{ ok: boolean; month: string; deleted: number; parts_reset: number }> {
  if (!API_BASE) throw new Error("API_BASE requis pour resetConsommations");
  const res = await fetch(`${API_BASE}/api/consommations/reset/`, {
    method: "POST",
    headers: buildJsonHeaders(identity),
    credentials: "include",
    body: JSON.stringify(opts),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Réinitialisation échouée (${res.status}): ${txt}`);
  }
  const json = (await res.json()) as { ok: boolean; month: string; deleted: number; parts_reset: number };
  cache = null;
  return json;
}

export async function loadPurchases(): Promise<{
  id: number;
  code: string;
  designation: string;
  type: string;
  criticite: string;
  quantite: number;
  prixUnitaire: number;
  total: number;
  impact: string;
  selected: boolean;
}[]> {
  if (!API_BASE) throw new Error("API_BASE requis pour loadPurchases");
  const [raw, apiPurch] = await Promise.all([loadRaw(), fetchOrNull<any[]>("/api/purchases/", true)]);
  const data = apiPurch && Array.isArray(apiPurch) && apiPurch.length > 0 ? apiPurch : raw;
  const rawByCode = new Map(raw.map((r) => [r.code, r]));

    return data.map((r: any, idx: number) => {
      const rawItem = rawByCode.get(r.code);
      const nacFromRaw = rawItem && typeof rawItem.n_ac_2025 === "number" ? rawItem.n_ac_2025 : undefined;
      const qty = Math.max(0, nacFromRaw ?? r.n_ac_2025 ?? r.quantite ?? 0);
      const pu = r.prixUnitaire ?? r.prix_uni ?? 0;
      const crit = (r.criticite ?? r.criticite?.toString() ?? "normal") as string;
        const total = qty * pu;
        return {
        id: idx + 1,
        code: r.code,
        designation: r.designation,
        type: "Accouplement",
      criticite: mapCriticite(crit),
      quantite: qty,
      prixUnitaire: pu,
      total,
      impact: qty > 0 ? "Prévision ML (n_ac_2025)" : "Aucune commande",
      selected: false,
    };
  });
}

export async function loadBudgetState(): Promise<{ budget_cap: number | null; selected_codes: string[] }> {
  if (!API_BASE) throw new Error("API_BASE requis pour loadBudgetState");
  const data = await fetchOrNull<{ budget_cap: number | null; selected_codes: string[] }>("/api/budget/state/", true);
  return data ?? { budget_cap: null, selected_codes: [] };
}

export async function saveBudgetState(
  budget_cap: number | null,
  selected_codes: string[],
  identity?: ApiIdentity
) {
  if (!API_BASE) throw new Error("API_BASE requis pour saveBudgetState");
  await fetch(`${API_BASE}/api/budget/state/`, {
    method: "POST",
    headers: buildJsonHeaders(identity),
    credentials: "include",
    body: JSON.stringify({ budget_cap, selected_codes }),
  });
}

export interface ActivitiesFilters {
  module?: string;
  from?: string;
  to?: string;
  limit?: number;
}

export async function fetchActivities(
  filters?: ActivitiesFilters
): Promise<{ utilisateur: string; role: string; action: string; module: string; details?: string; date: string }[]> {
  if (!API_BASE) throw new Error("API_BASE requis pour fetchActivities");
  const params: string[] = [];
  if (filters?.module) params.push(`module=${encodeURIComponent(filters.module)}`);
  if (filters?.from) params.push(`from=${encodeURIComponent(filters.from)}`);
  if (filters?.to) params.push(`to=${encodeURIComponent(filters.to)}`);
  if (typeof filters?.limit === "number") params.push(`limit=${filters.limit}`);
  const query = params.length ? `?${params.join("&")}` : "";

  const data = await fetchOrNull<any[]>(`/api/activities/${query}`, true);
  return data ?? [];
}

// ---------------------------------------------------------------------------
// Import consommations (CSV -> backend)
// ---------------------------------------------------------------------------

export type ImportConsommationsResult = {
  saved: { code: string; date: string; valeur: number; delta?: number }[];
  errors: any[];
  predictions?: { code: string; previsionM1: number }[];
};

export async function importConsommationsFile(
  file: File,
  opts?: { date?: string; identity?: ApiIdentity }
): Promise<ImportConsommationsResult> {
  if (!API_BASE) throw new Error("API_BASE non défini");
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.date) fd.append("date", opts.date);

  const headers: Record<string, string> = {};
  if (API_TOKEN) headers["X-API-KEY"] = API_TOKEN;
  if (opts?.identity?.user) headers["X-User"] = opts.identity.user;
  if (opts?.identity?.role) headers["X-Role"] = opts.identity.role;

  const res = await fetch(`${API_BASE}/api/consommations/import/`, {
    method: "POST",
    headers,
    credentials: "include",
    body: fd,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Import échoué (${res.status}): ${txt}`);
  }
  const json = (await res.json()) as ImportConsommationsResult;
  cache = null; // force reload of forecasts
  return json;
}

// ---------------------------------------------------------------------------
// Paramètres (backend)
// ---------------------------------------------------------------------------

export type ParametersConfig = {
  ruptureThreshold: number;
  longLeadDays: number;
  budgetCap: number | null;
  autoSelectCritical: boolean;
  activeModel: string;
  refreshFrequency: "journalier" | "hebdomadaire" | "mensuel";
  notifyRupture: boolean;
  notifyBudget: boolean;
  notifyDigest: boolean;
  updatedAt?: string;
  updatedBy?: string;
  updatedRole?: string;
};

export const DEFAULT_PARAMETERS: ParametersConfig = {
  ruptureThreshold: 10,
  longLeadDays: 60,
  budgetCap: 1500000,
  autoSelectCritical: true,
  activeModel: "hist-gradient-boosting",
  refreshFrequency: "hebdomadaire",
  notifyRupture: true,
  notifyBudget: true,
  notifyDigest: false,
};

function normalizeParameters(data: any): ParametersConfig {
  if (!data || typeof data !== "object") return DEFAULT_PARAMETERS;
  return {
    ruptureThreshold: Number(data.ruptureThreshold ?? DEFAULT_PARAMETERS.ruptureThreshold),
    longLeadDays: Number(data.longLeadDays ?? DEFAULT_PARAMETERS.longLeadDays),
    budgetCap:
      data.budgetCap === null || data.budgetCap === undefined || data.budgetCap === ""
        ? null
        : Number(data.budgetCap),
    autoSelectCritical: Boolean(data.autoSelectCritical ?? DEFAULT_PARAMETERS.autoSelectCritical),
    activeModel: (data.activeModel ?? DEFAULT_PARAMETERS.activeModel).toString(),
    refreshFrequency: (data.refreshFrequency ?? DEFAULT_PARAMETERS.refreshFrequency) as ParametersConfig["refreshFrequency"],
    notifyRupture: Boolean(data.notifyRupture ?? DEFAULT_PARAMETERS.notifyRupture),
    notifyBudget: Boolean(data.notifyBudget ?? DEFAULT_PARAMETERS.notifyBudget),
    notifyDigest: Boolean(data.notifyDigest ?? DEFAULT_PARAMETERS.notifyDigest),
    updatedAt: data.updatedAt,
    updatedBy: data.updatedBy,
    updatedRole: data.updatedRole,
  };
}

function readLocalParameters(): ParametersConfig | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem("ocp-parameters");
    if (!raw) return null;
    return normalizeParameters(JSON.parse(raw));
  } catch {
    return null;
  }
}

export async function loadParameters(): Promise<{ data: ParametersConfig; source: "api" | "fallback" }> {
  if (!API_BASE) {
    const local = readLocalParameters();
    return { data: local ?? DEFAULT_PARAMETERS, source: "fallback" };
  }
  try {
    const res = await fetch(`${API_BASE}/api/parameters/`, {
      headers: API_TOKEN ? { "X-API-KEY": API_TOKEN } : undefined,
      credentials: "include",
    });
    if (!res.ok) throw new Error("parameters fetch failed");
    const json = await res.json();
    return { data: normalizeParameters(json), source: "api" };
  } catch {
    const local = readLocalParameters();
    return { data: local ?? DEFAULT_PARAMETERS, source: "fallback" };
  }
}

export async function saveParameters(payload: ParametersConfig, identity?: ApiIdentity): Promise<void> {
  if (!API_BASE) {
    // minimal local fallback to avoid data loss if backend absent
    localStorage.setItem("ocp-parameters", JSON.stringify(payload));
    return;
  }
  const res = await fetch(`${API_BASE}/api/parameters/`, {
    method: "POST",
    headers: buildJsonHeaders(identity),
    credentials: "include",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Save paramètres échoué (${res.status}): ${txt}`);
  }
}
