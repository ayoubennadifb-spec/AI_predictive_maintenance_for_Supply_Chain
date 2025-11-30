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
const API_BASE = (import.meta as any).env?.VITE_API_BASE || "";

export interface ApiIdentity {
  user?: string;
  role?: string;
}

function buildJsonHeaders(identity?: ApiIdentity): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (identity?.user) headers["X-USER"] = identity.user;
  if (identity?.role) headers["X-ROLE"] = identity.role;
  return headers;
}

async function fetchOrNull<T>(path: string): Promise<T | null> {
  if (!API_BASE) return null;
  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

async function loadRaw(): Promise<MLRawItem[]> {
  if (cache) return cache;
  const apiData = await fetchOrNull<MLRawItem[]>("/api/previsions/");
  const data = apiData ?? ((await import("../assets/predictions_2025.json")).default as MLRawItem[]);
  cache = data;
  return data;
}

async function loadStockSecuriteMap(): Promise<Record<string, number>> {
  if (stockSecuriteMap) return stockSecuriteMap;
  try {
    stockSecuriteMap = (await import("../assets/stock_securite.json")).default as Record<string, number>;
  } catch {
    stockSecuriteMap = {};
  }
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
  ecartPourcent: number;
  prixUnitaire: number;
  fournisseur: string;
  delai: number;
  approved?: boolean;
  historique: { mois: string; valeur: number }[];
}[]> {
  const [raw, stockMap, approved] = await Promise.all([
    loadRaw(),
    loadStockSecuriteMap(),
    fetchOrNull<{ approved: string[] }>("/api/approvals/"),
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
    ecartPourcent: r.ecartPourcent,
    prixUnitaire: r.prixUnitaire,
    fournisseur: r.fournisseur,
    delai: r.delai,
    historique: [],
    approved: approvedSet.has(r.code),
  }));
}

export async function loadConsommations(date?: string): Promise<{ code: string; prevision: number; consommationReelle: number | null }[]> {
  const raw = await loadRaw();
  const query = date ? `?date=${date}` : "";
  const apiExisting = await fetchOrNull<
    { code: string; date: string; valeur: number }[]
  >("/api/consommations/" + query);
  const existingByCode = new Map<string, number>();
  (apiExisting || []).forEach((r) => existingByCode.set(r.code, r.valeur));

  return raw.map((r) => ({
    code: r.code,
    // Prévision pour la saisie : quantité à commander/prévoir pour le mois suivant (n_ac_2025 si dispo, sinon prévisionM1).
    prevision: r.n_ac_2025 ?? r.previsionM1,
    consommationReelle: existingByCode.get(r.code) ?? null,
  }));
}

export async function saveConsommations(
  payload: { code: string; date: string; valeur: number | null }[],
  identity?: ApiIdentity
) {
  if (!API_BASE) {
    // fallback localStorage si pas d'API
    const raw = localStorage.getItem('consommations_by_date');
    const parsed: Record<string, Record<string, number>> = raw ? JSON.parse(raw) : {};
    payload.forEach((item) => {
      if (item.valeur === null || Number.isNaN(item.valeur)) return;
      parsed[item.date] = parsed[item.date] || {};
      parsed[item.date][item.code] = item.valeur;
    });
    localStorage.setItem('consommations_by_date', JSON.stringify(parsed));
    return;
  }
  await fetch(`${API_BASE}/api/consommations/`, {
    method: "POST",
    headers: buildJsonHeaders(identity),
    body: JSON.stringify(payload),
  });
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
  const [raw, apiPurch] = await Promise.all([loadRaw(), fetchOrNull<any[]>("/api/purchases/")]);
  const data = apiPurch && Array.isArray(apiPurch) && apiPurch.length > 0 ? apiPurch : raw;

  return data.map((r: any, idx: number) => {
    const qty = Math.max(0, r.n_ac_2025 ?? r.quantite ?? 0);
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
  const data = await fetchOrNull<{ budget_cap: number | null; selected_codes: string[] }>("/api/budget/state/");
  return data ?? { budget_cap: null, selected_codes: [] };
}

export async function saveBudgetState(
  budget_cap: number | null,
  selected_codes: string[],
  identity?: ApiIdentity
) {
  if (!API_BASE) return;
  await fetch(`${API_BASE}/api/budget/state/`, {
    method: "POST",
    headers: buildJsonHeaders(identity),
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
  const params: string[] = [];
  if (filters?.module) params.push(`module=${encodeURIComponent(filters.module)}`);
  if (filters?.from) params.push(`from=${encodeURIComponent(filters.from)}`);
  if (filters?.to) params.push(`to=${encodeURIComponent(filters.to)}`);
  if (typeof filters?.limit === "number") params.push(`limit=${filters.limit}`);
  const query = params.length ? `?${params.join("&")}` : "";

  const data = await fetchOrNull<any[]>(`/api/activities/${query}`);
  return data ?? [];
}
