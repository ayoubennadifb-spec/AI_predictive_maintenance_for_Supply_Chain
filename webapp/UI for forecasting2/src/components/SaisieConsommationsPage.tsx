import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "./PageHeader";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { toast } from "sonner@2.0.3";
import { useAuth } from "./AuthContext";
import { importConsommationsFile, loadConsommations, resetConsommations, saveConsommations } from "../services/mlData";

type ConsommationItem = {
  code: string;
  prevision: number;
  consommationBase: number;
  consommationJour: number;
  predictedNext?: number;
};

export function SaisieConsommationsPage() {
  const [rows, setRows] = useState<ConsommationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [now, setNow] = useState<Date>(new Date());
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const { user } = useAuth();

  useEffect(() => {
    loadConsommations(selectedDate)
      .then((items) =>
        setRows(
          items.map((r) => ({
            code: r.code,
            prevision: r.prevision,
            consommationBase: r.consommationReelle ?? 0,
            consommationJour: 0,
            predictedNext: undefined,
          }))
        )
      )
      .catch(() => setError("Erreur de chargement des consommations"))
      .finally(() => setLoading(false));
  }, [selectedDate]);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const nextMonthLabel = useMemo(() => {
    const d = selectedDate ? new Date(selectedDate) : new Date(now);
    d.setMonth(d.getMonth() + 1);
    return d.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  }, [selectedDate, now]);

  const update = (code: string, value: string) => {
    const n = value.trim() === "" ? 0 : Number(value);
    if (Number.isNaN(n as any)) return;
    setRows((prev) =>
      prev.map((r) => (r.code === code ? { ...r, consommationJour: n } : r))
    );
  };

  const onImportFile = async (file: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      toast.error("Format non pris en charge", { description: "Import CSV attendu (code;valeur)." });
      return;
    }
    setImporting(true);
    try {
      const res = await importConsommationsFile(file, {
        date: selectedDate,
        identity: user ? { user: user.nom, role: user.role } : undefined,
      });
      // Mettre à jour les consommations à partir du delta renvoyé par le backend :
      // - « Consommation d’aujourd’hui » = valeur importée (delta)
      // - « Consommation actuelle accumulée » = cumul avant import + delta
      const deltas = new Map((res.saved ?? []).map((s) => [s.code, Number(s.delta ?? 0)]));
      setRows((prev) =>
        prev.map((r) => {
          const delta = deltas.get(r.code);
          if (delta === undefined) return r;
          const baseAvant = (r.consommationBase ?? 0) + (r.consommationJour ?? 0);
          return {
            ...r,
            consommationBase: baseAvant,
            consommationJour: delta,
            predictedNext: undefined,
          };
        })
      );
      const applied = res.saved?.length ?? 0;
      const errs = res.errors?.length ?? 0;
      toast.success("Import terminé", {
        description: `${applied} lignes appliquées${errs ? `, ${errs} erreurs` : ""}`,
      });
    } catch (e: any) {
      toast.error("Échec import CSV", { description: e?.message || "Import serveur impossible" });
    } finally {
      setImporting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await saveConsommations(
        rows.map((r) => ({
          code: r.code,
          date: selectedDate,
          valeur: r.consommationBase + (r.consommationJour ?? 0),
        })),
        user ? { user: user.nom, role: user.role } : undefined
      );
      const predByCode = new Map((res?.predictions ?? []).map((p) => [p.code, p.n_ac_2025] as const));
      setRows((prev) =>
        prev.map((r) => {
          const delta = r.consommationJour ?? 0;
          const nextBase = (r.consommationBase ?? 0) + delta;
          const p = predByCode.get(r.code);
          // On affiche n_ac (besoin à commander) recalculé côté backend
          return {
            ...r,
            consommationBase: nextBase,
            consommationJour: 0,
            predictedNext: p ?? r.predictedNext,
          };
        })
      );
      toast.success("Consommations enregistrées", {
        description: res?.predictions?.length ? "Prévision M+1 ajustée" : `Saisie du ${selectedDate}`,
      });
    } catch (e: any) {
      toast.error(e?.message || "Échec d'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  const resetMonth = async () => {
    const month = selectedDate.slice(0, 7);
    const ok = window.confirm(`Réinitialiser toutes les consommations accumulées (n_sa) pour ${month} ?`);
    if (!ok) return;

    setResetting(true);
    toast.loading("Réinitialisation en cours...");
    try {
      await resetConsommations({ month }, user ? { user: user.nom, role: user.role } : undefined);
      const items = await loadConsommations(selectedDate);
      setRows(
        items.map((r) => ({
          code: r.code,
          prevision: r.prevision,
          consommationBase: r.consommationReelle ?? 0,
          consommationJour: 0,
          predictedNext: undefined,
        }))
      );
      toast.success("Réinitialisation terminée", { description: `Consommations du mois ${month} remises à 0.` });
    } catch (e: any) {
      toast.error("Échec réinitialisation", { description: e?.message || "Impossible de réinitialiser." });
    } finally {
      setResetting(false);
    }
  };

  if (loading) return <div className="p-6 text-neutral-700">Chargement des consommations...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Saisie des consommations"
        description="Comparer les prévisions et saisir les consommations réelles"
        breadcrumbs={[
          { label: "Accueil", href: "#" },
          { label: "Saisie" },
        ]}
      />

      <Card className="shadow-sm border-neutral-200">
        <CardContent className="p-0">
          <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50 flex flex-wrap items-center justify-between gap-2">
            <div className="text-small text-neutral-700 flex items-center gap-2">
              <label className="text-xs text-neutral-600">Date :</label>
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="border border-neutral-200 rounded px-2 py-1 text-sm"
              />
            </div>
            <div className="text-small text-neutral-700">
              Prévision affichée : <span className="font-semibold">n_ac mois prochain ({nextMonthLabel})</span>
            </div>
            <div className="text-small text-neutral-700">
              Aujourd'hui :
              <span className="font-semibold">
                {" "}
                {now.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" })}{" "}
                {now.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-neutral-600" htmlFor="import-csv">
                Import CSV (code;valeur)
              </label>
              <input
                id="import-csv"
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                disabled={importing}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onImportFile(f);
                  e.target.value = "";
                }}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={importing}
                onClick={() => fileInputRef.current?.click()}
              >
                {importing ? "Import..." : "Importer CSV"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={resetting || saving || importing}
                onClick={resetMonth}
              >
                {resetting ? "Réinitialisation..." : "Réinitialiser"}
              </Button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader className="bg-neutral-50 sticky top-0 z-10">
                <TableRow>
                  <TableHead className="text-left">Code</TableHead>
                  <TableHead className="text-left">Consommation actuelle accumulée</TableHead>
                  <TableHead className="text-left">Consommation d’aujourd’hui (saisie/import)</TableHead>
                  <TableHead className="text-left">Prévision M+1 (n_ac)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.code}>
                    <TableCell className="font-medium">{r.code}</TableCell>
                    <TableCell>{(r.consommationBase + (r.consommationJour ?? 0)).toFixed(2)}</TableCell>
                    <TableCell>
                      <input
                        type="number"
                        value={r.consommationJour ?? 0}
                        onChange={(e) => update(r.code, e.target.value)}
                        className="border border-neutral-200 rounded px-2 py-1 w-32"
                        min="0"
                        step="0.01"
                      />
                    </TableCell>
                    <TableCell className="text-primary font-medium">
                      {r.predictedNext !== undefined ? Math.round(r.predictedNext).toString() : ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="p-4 border-t border-neutral-200 flex justify-end">
            <Button onClick={save} disabled={saving}>
              {saving ? "Calcul..." : "Prédire M+1"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
