import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "./PageHeader";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Badge } from "./ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { toast } from "sonner@2.0.3";
import { Wallet, ShoppingCart, AlertCircle, CheckCircle2, ChevronRight } from "lucide-react";
import { loadPurchases, loadBudgetState, saveBudgetState } from "../services/mlData";
import { CriticalityBadge } from "./CriticalityBadge";
import { useAuth } from "./AuthContext";

type Purchase = {
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
};

export function GestionBudgetPage() {
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Purchase | null>(null);
  const [simulatorOpen, setSimulatorOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCriticite, setSelectedCriticite] = useState<"tous" | "urgent" | "moyen" | "normal">("tous");
  const [budgetCap, setBudgetCap] = useState<number | null>(null);
  const [initialLoaded, setInitialLoaded] = useState(false);
  const [sortBy, setSortBy] = useState<"code" | "criticite" | "total">("code");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const { user } = useAuth();

  useEffect(() => {
    const loadAll = async () => {
      try {
        const [purch, budgetState] = await Promise.all([loadPurchases(), loadBudgetState()]);
        const selectedCodes = new Set(budgetState.selected_codes || []);
        setBudgetCap(budgetState.budget_cap ?? null);
        setPurchases(purch.map((p) => ({ ...p, selected: selectedCodes.has(p.code) })));
      } catch {
        setError("Erreur de chargement des recommandations d'achat");
      } finally {
        setLoading(false);
        setInitialLoaded(true);
      }
    };
    loadAll();
  }, []);

  const filtered = useMemo(() => {
    const byFilter = purchases.filter((p) => {
      const matchSearch =
        p.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (p.designation || "").toLowerCase().includes(searchQuery.toLowerCase());
      const matchCriticite = selectedCriticite === "tous" || p.criticite === selectedCriticite;
      const matchNonZero = Math.round(p.quantite) > 0;
      return matchSearch && matchCriticite && matchNonZero;
    });
    const sorted = [...byFilter].sort((a, b) => {
      let va: number | string;
      let vb: number | string;
      if (sortBy === "total") {
        va = a.total;
        vb = b.total;
      } else if (sortBy === "criticite") {
        va = a.criticite;
        vb = b.criticite;
      } else {
        va = a.code;
        vb = b.code;
      }
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return sorted;
  }, [purchases, searchQuery, selectedCriticite, sortBy, sortDir]);

  const totals = useMemo(() => {
    const total = filtered.reduce((sum, p) => sum + p.total, 0);
    const selectedTotal = filtered.filter((p) => p.selected).reduce((sum, p) => sum + p.total, 0);
    return { total, selectedTotal };
  }, [filtered]);

  const persistSelection = (list: Purchase[], cap: number | null, showToast = false) => {
    if (!initialLoaded) return;
    const selectedCodes = list.filter((p) => p.selected).map((p) => p.code);
    saveBudgetState(cap, selectedCodes, user ? { user: user.nom, role: user.role } : undefined)
      .then(() => {
        if (showToast) toast.success("Budget/sélection sauvegardés");
      })
      .catch(() => showToast && toast.error("Erreur de sauvegarde budget"));
  };

  const optimizeSelectionByBudget = () => {
    if (budgetCap === null || Number.isNaN(budgetCap)) {
      toast.warning("Veuillez saisir un budget disponible avant l'optimisation.");
      return;
    }

    const criticityWeight: Record<string, number> = {
      urgent: 3,
      moyen: 2,
      normal: 1,
    };

    // On n'optimise que sur les pièces qui ont une quantité à commander > 0
    const positives = purchases.filter((p) => Math.round(p.quantite) > 0 && p.total > 0);
    if (!positives.length) {
      const next = purchases.map((p) => ({ ...p, selected: false }));
      setPurchases(next);
      persistSelection(next, budgetCap, false);
      toast.info("Aucune pièce avec quantité à commander > 0 pour ce budget.");
      return;
    }

    const sorted = [...positives].sort((a, b) => {
      const wa = criticityWeight[a.criticite] ?? 0;
      const wb = criticityWeight[b.criticite] ?? 0;
      if (wa !== wb) return wb - wa; // urgent > moyen > normal
      // À criticité égale, on privilégie les plus petits PU pour maximiser la quantité achetée
      if (a.prixUnitaire !== b.prixUnitaire) return a.prixUnitaire - b.prixUnitaire;
      // en dernier recours, on tranche sur le total
      return a.total - b.total;
    });

    const fullTotal = sorted.reduce((sum, p) => sum + p.total, 0);
    let remaining = budgetCap;
    let used = 0;
    const selectedIds = new Set<number>();

    if (budgetCap >= fullTotal) {
      // Budget suffisant : on commande toutes les pièces qui ont un besoin > 0
      sorted.forEach((p) => selectedIds.add(p.id));
      used = fullTotal;
    } else {
      // Budget limité : on remplit en priorité les pièces les plus critiques
      for (const p of sorted) {
        if (p.total <= remaining) {
          selectedIds.add(p.id);
          remaining -= p.total;
          used += p.total;
        }
      }
    }

    const next = purchases.map((p) => ({
      ...p,
      // On sélectionne uniquement les pièces avec n_ac_2025 > 0 qui sont dans la sélection optimisée
      selected: Math.round(p.quantite) > 0 && selectedIds.has(p.id),
    }));

    setPurchases(next);
    persistSelection(next, budgetCap, true);

    if (budgetCap >= fullTotal) {
      toast.success("Budget suffisant : toutes les quantités prédites (n_ac > 0) sont sélectionnées.", {
        description: `Budget dispo ${budgetCap.toLocaleString()} MAD ≥ besoin total ${fullTotal.toLocaleString()} MAD.`,
      });
    } else {
      const selectedCount = next.filter((p) => p.selected).length;
      toast.success("Sélection optimisée selon le budget et la criticité.", {
        description: `${selectedCount} pièce(s) sélectionnée(s), ${used.toLocaleString()} MAD utilisés sur ${budgetCap.toLocaleString()} MAD.`,
      });
    }
  };

  const toggleOne = (id: number) => {
    setPurchases((prev) => {
      const next = prev.map((p) => (p.id === id ? { ...p, selected: !p.selected } : p));
      persistSelection(next, budgetCap, false);
      return next;
    });
  };

  const toggleAll = () => {
    const visibleIds = new Set(filtered.map((p) => p.id));
    const allSelected = filtered.every((p) => p.selected);
    setPurchases((prev) => {
      const next = prev.map((p) =>
        visibleIds.has(p.id)
          ? {
              ...p,
              selected: !allSelected,
            }
          : p,
      );
      persistSelection(next, budgetCap, false);
      return next;
    });
  };

  if (loading) return <div className="p-6 text-neutral-700">Chargement budget...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Gestion du budget"
        description="Planifier les commandes à partir des prévisions ML et des stocks cibles"
        breadcrumbs={[
          { label: "Accueil", href: "#" },
          { label: "Budget" },
        ]}
        actions={
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" size="sm" onClick={toggleAll}>
              Tout basculer
            </Button>
            <Button variant="outline" size="sm" onClick={optimizeSelectionByBudget}>
              Optimiser selon le budget
            </Button>
          </div>
        }
      />

      <Card className="shadow-sm border-neutral-200">
        <CardContent className="p-0">
          <div className="p-4 border-b border-neutral-200 bg-neutral-50 flex flex-wrap gap-3 items-center">
            <input
              type="text"
              placeholder="Rechercher code ou désignation"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="border border-neutral-200 rounded px-3 py-2 text-sm w-full sm:w-64"
            />
            <select
              value={selectedCriticite}
              onChange={(e) => setSelectedCriticite(e.target.value as any)}
              className="border border-neutral-200 rounded px-3 py-2 text-sm"
            >
              <option value="tous">Toutes criticités</option>
              <option value="urgent">Urgent</option>
              <option value="moyen">Moyen</option>
              <option value="normal">Normal</option>
            </select>
            <div className="flex items-center gap-2 text-sm">
              <span>Budget cible (MAD) :</span>
              <input
                type="number"
                value={budgetCap ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  const nextCap = v === "" ? null : Number(v);
                  setBudgetCap(nextCap);
                  persistSelection(purchases, nextCap, true);
                }}
                className="border border-neutral-200 rounded px-2 py-1 w-32"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table className="min-w-[1100px]">
              <TableHeader className="bg-neutral-50">
                <TableRow>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => {
                      setSortBy("code");
                      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
                    }}
                  >
                    Code
                  </TableHead>
                  <TableHead>Désignation</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => {
                      setSortBy("criticite");
                      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
                    }}
                  >
                    Criticité
                  </TableHead>
                  <TableHead className="text-right">Quantité</TableHead>
                  <TableHead className="text-right">PU</TableHead>
                  <TableHead
                    className="text-right cursor-pointer select-none"
                    onClick={() => {
                      setSortBy("total");
                      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
                    }}
                  >
                    Total
                  </TableHead>
                  <TableHead>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((p) => (
                  <TableRow key={p.id} className="hover:bg-neutral-50">
                    <TableCell className="font-medium">{p.code}</TableCell>
                    <TableCell>{p.designation}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{p.type}</Badge>
                    </TableCell>
                    <TableCell>
                      <CriticalityBadge level={p.criticite as any} />
                    </TableCell>
                    <TableCell className="text-right">
                      {Math.round(p.quantite).toString()}
                    </TableCell>
                    <TableCell className="text-right">{p.prixUnitaire.toLocaleString()} MAD</TableCell>
                    <TableCell className="text-right font-semibold">{p.total.toLocaleString()} MAD</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={p.selected}
                          onChange={() => toggleOne(p.id)}
                          className="w-4 h-4"
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-neutral-600 gap-1"
                          onClick={() => {
                            setSelected(p);
                            setSimulatorOpen(true);
                          }}
                        >
                          Voir <ChevronRight className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="p-4 border-t border-neutral-200 bg-neutral-50">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <Wallet className="w-4 h-4 text-neutral-500" />
                  <span className="text-small text-neutral-600">Total</span>
                </div>
                <span className="text-body font-semibold text-neutral-900">
                  {totals.total.toLocaleString()} MAD
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <ShoppingCart className="w-4 h-4 text-primary" />
                  <span className="text-small text-neutral-600">Sélectionné</span>
                </div>
                <span className="text-body font-semibold text-primary">
                  {totals.selectedTotal.toLocaleString()} MAD
                </span>
              </div>
              {budgetCap !== null && (
                <div className="flex items-center gap-2 text-small">
                  <span>Reste budget :</span>
                  <span
                    className={`text-body font-semibold ${
                      totals.selectedTotal > budgetCap ? "text-danger-600" : "text-success-700"
                    }`}
                  >
                    {(budgetCap - totals.selectedTotal).toLocaleString()} MAD
                  </span>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Sheet open={simulatorOpen} onOpenChange={setSimulatorOpen}>
        <SheetContent className="sm:max-w-lg">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle>{selected.code}</SheetTitle>
                <SheetDescription>{selected.designation}</SheetDescription>
              </SheetHeader>
              <div className="space-y-4 py-4">
                <div className="flex gap-2 items-center">
                  <CriticalityBadge level={selected.criticite as any} />
                  <Badge variant="secondary">{selected.type}</Badge>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-small text-neutral-600">Quantité à commander</p>
                    <p className="text-h4 text-neutral-900">{selected.quantite.toFixed(2)}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-small text-neutral-600">Budget</p>
                    <p className="text-h4 text-primary">{selected.total.toLocaleString()} MAD</p>
                  </div>
                </div>
                <div className="space-y-2 border-t border-neutral-200 pt-2">
                  <div className="flex items-start gap-2 text-sm text-neutral-700">
                    <CheckCircle2 className="w-4 h-4 text-primary mt-0.5" />
                    <span>Prévision ML + stock de sécurité + délai de livraison pris en compte.</span>
                  </div>
                  <div className="flex items-start gap-2 text-sm text-neutral-700">
                    <AlertCircle className="w-4 h-4 text-warning-500 mt-0.5" />
                    <span>{selected.impact}</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
