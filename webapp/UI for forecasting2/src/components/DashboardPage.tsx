import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { Wallet, AlertTriangle, TrendingUp, Package, RefreshCw, Lock, ChevronRight } from "lucide-react";
import { toast } from "sonner@2.0.3";

import { useAuth } from "./AuthContext";
import { KPICard } from "./KPICard";
import { InteractiveChart } from "./InteractiveChart";
import { LiveStatsWidget } from "./LiveStatsWidget";
import { ActivityFeed } from "./ActivityFeed";
import { CriticalityBadge } from "./CriticalityBadge";
import { PageHeader } from "./PageHeader";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Badge } from "./ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "./ui/sheet";

import { loadPrevisions, loadPurchases, loadConsommations } from "../services/mlData";

type Prevision = Awaited<ReturnType<typeof loadPrevisions>>[number];
type Purchase = Awaited<ReturnType<typeof loadPurchases>>[number];
type Consommation = Awaited<ReturnType<typeof loadConsommations>>[number];

export function DashboardPage() {
  const { user } = useAuth();
  const isManager = user?.role === "manager";

  const [previsions, setPrevisions] = useState<Prevision[]>([]);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [consommations, setConsommations] = useState<Consommation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedPurchase, setSelectedPurchase] = useState<Purchase | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    const loadAll = async () => {
      try {
        const today = new Date().toISOString().slice(0, 10);
        const [prev, purch, consos] = await Promise.all([
          loadPrevisions(),
          loadPurchases(),
          loadConsommations(today),
        ]);
        setPrevisions(prev);
        setPurchases(purch);
        setConsommations(consos);
      } catch {
        setError("Erreur de chargement des données du tableau de bord");
      } finally {
        setLoading(false);
      }
    };
    loadAll();
  }, []);

  const consommationMap = useMemo(() => {
    const map = new Map<string, number>();
    consommations.forEach((c) => {
      const val = typeof c.consommationReelle === "number" ? c.consommationReelle : 0;
      map.set(c.code, val);
    });
    return map;
  }, [consommations]);

  const previsionMap = useMemo(() => {
    const map = new Map<string, Prevision>();
    previsions.forEach((p) => map.set(p.code, p));
    return map;
  }, [previsions]);

  const stats = useMemo(() => {
    const totalPrevision = previsions.reduce((s, p) => s + p.previsionM1, 0);
    // Valeur "Stock total" = somme des consommations actuelles accumulées (page Saisie consommations)
    const totalStock = consommations.reduce((s, c) => s + (c.consommationReelle ?? 0), 0);
    const criticalCount = previsions.filter((p) => p.criticite === "urgent").length;
    const budgetTotal = purchases.reduce((s, p) => s + p.total, 0);
    return { totalPrevision, totalStock, criticalCount, budgetTotal };
  }, [previsions, purchases, consommations]);

  const chartPrevisionStock = previsions.slice(0, 8).map((p) => {
    const cons = consommationMap.get(p.code);
    return {
      code: p.code,
      prevision: p.previsionM1,
      consommation: cons ?? 0,
    };
  });

  const criticityAgg = previsions.reduce(
    (acc, p) => {
      const key = p.criticite || "normal";
      acc[key] = acc[key] || { criticite: key, stock: 0, aCommander: 0 };
      acc[key].stock += p.stockActuel;
      return acc;
    },
    {} as Record<string, { criticite: string; stock: number; aCommander: number }>,
  );
  purchases.forEach((p) => {
    const key = p.criticite || "normal";
    criticityAgg[key] = criticityAgg[key] || { criticite: key, stock: 0, aCommander: 0 };
    criticityAgg[key].aCommander += p.quantite;
  });
  const chartCriticite = Object.values(criticityAgg);

  const criticalParts = purchases
    .filter((p) => Math.round(p.quantite) > 0)
    .sort((a, b) => (a.criticite === b.criticite ? b.quantite - a.quantite : a.criticite === "urgent" ? -1 : 1))
    .slice(0, 8);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    toast.loading("Actualisation des données en cours...");
    try {
      const today = new Date().toISOString().slice(0, 10);
      const [prev, purch, consos] = await Promise.all([
        loadPrevisions(),
        loadPurchases(),
        loadConsommations(today),
      ]);
      setPrevisions(prev);
      setPurchases(purch);
      setConsommations(consos);
      toast.success("Données actualisées");
    } catch {
      toast.error("Erreur lors de l’actualisation");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleViewDetails = (purchase: Purchase) => {
    setSelectedPurchase(purchase);
    setDetailOpen(true);
  };

  if (loading) return <div className="p-6 text-neutral-700">Chargement du tableau de bord...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-6 page-transition">
      <PageHeader
        title="Tableau de bord principal"
        description="Vue d'ensemble des prévisions et besoins calculés"
        breadcrumbs={[
          { label: "Accueil", href: "#" },
          { label: "Tableau de bord" },
        ]}
        actions={
          <Button
            variant="outline"
            size="sm"
            className="gap-2 hover:bg-ocp-green/5 hover:text-ocp-green hover:border-ocp-green transition-all"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Actualiser</span>
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-slide-in-bottom">
        {isManager ? (
          <KPICard
            title="Budget prévisionnel"
            value={`${(stats.budgetTotal / 1000).toFixed(1)}k MAD`}
            subtitle="Σ (n_ac_2025 × PU)"
            icon={Wallet}
            isLoading={isRefreshing}
          />
        ) : (
          <KPICard
            title="Budget prévisionnel"
            value="—"
            subtitle="Accès restreint aux managers"
            icon={Lock}
            variant="locked"
          />
        )}

        <KPICard
          title="Pièces critiques"
          value={stats.criticalCount.toString()}
          subtitle="Criticité urgente"
          icon={AlertTriangle}
          isLoading={isRefreshing}
        />

        <KPICard
          title="Prévision mois suivant"
          value={stats.totalPrevision.toFixed(1)}
          subtitle="Consommation mensuelle totale (n_pm)"
          icon={TrendingUp}
          isLoading={isRefreshing}
        />

        <KPICard
          title="Stock total"
          value={stats.totalStock.toFixed(0)}
          subtitle="Accouplements en inventaire"
          icon={Package}
          isLoading={isRefreshing}
        />
      </div>

      <div className="animate-fade-in">
        <LiveStatsWidget />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6 animate-slide-in-left">
        <InteractiveChart
          title="Prévision vs consommation"
          description="Top pièces (prévision ML vs consommation actuelle cumulée)"
          isLoading={isRefreshing}
        >
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartPrevisionStock}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="code" tick={{ fontSize: 12, fill: "#6B7280" }} axisLine={{ stroke: "#E5E7EB" }} />
              <YAxis tick={{ fontSize: 12, fill: "#6B7280" }} axisLine={{ stroke: "#E5E7EB" }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#ffffff",
                  border: "1px solid #E5E7EB",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "12px" }} iconType="circle" />
              <Line
                type="monotone"
                dataKey="prevision"
                stroke="#6BA539"
                strokeWidth={2.5}
                dot={{ r: 3 }}
                name="Prévision ML (n_pm)"
              />
              <Line
                type="monotone"
                dataKey="consommation"
                stroke="#0B3D91"
                strokeWidth={2.5}
                dot={{ r: 3 }}
                name="Consommation actuelle cumulée"
              />
            </LineChart>
          </ResponsiveContainer>
        </InteractiveChart>

        <InteractiveChart
          title="Répartition par criticité"
          description="Stocks et besoins à commander"
          isLoading={isRefreshing}
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartCriticite}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="criticite" tick={{ fontSize: 12, fill: "#6B7280" }} axisLine={{ stroke: "#E5E7EB" }} />
              <YAxis tick={{ fontSize: 12, fill: "#6B7280" }} axisLine={{ stroke: "#E5E7EB" }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#ffffff",
                  border: "1px solid #E5E7EB",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "12px" }} iconType="circle" />
              <Bar dataKey="stock" stackId="a" fill="#6BA539" name="En stock" />
              <Bar dataKey="aCommander" stackId="a" fill="#DC2626" name="À commander (NAC)" />
            </BarChart>
          </ResponsiveContainer>
        </InteractiveChart>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6 animate-slide-in-bottom">
        <LiveStatsWidget />
        <ActivityFeed />
      </div>

      <Card className="shadow-sm border-neutral-200 hover-lift animate-slide-in-right">
        <CardHeader className="flex flex-row items-start justify-between pb-4">
          <div className="space-y-1">
            <CardTitle className="text-h3">Pièces prioritaires à commander</CardTitle>
            <p className="text-small text-neutral-500">Issues des prévisions ML et de n_ac_2025</p>
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto -mx-6 px-6 md:mx-0 md:px-0">
          <Table className="min-w-[900px]">
            <TableHeader>
              <TableRow className="bg-neutral-50 hover:bg-neutral-50">
                <TableHead className="text-small font-semibold text-neutral-700">Code</TableHead>
                <TableHead className="text-small font-semibold text-neutral-700">Désignation</TableHead>
                <TableHead className="text-small font-semibold text-neutral-700">Criticité</TableHead>
                <TableHead className="text-small font-semibold text-neutral-700 text-right">Qté à commander</TableHead>
                {isManager && (
                  <TableHead className="text-small font-semibold text-neutral-700 text-right">Budget (MAD)</TableHead>
                )}
                <TableHead className="text-small font-semibold text-neutral-700 text-right">Délai (j)</TableHead>
                <TableHead className="text-small font-semibold text-neutral-700" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {criticalParts.map((part) => {
                const pv = previsionMap.get(part.code);
                const delayDays = pv?.delai ?? 0;
                return (
                  <TableRow key={part.id} className="hover:bg-neutral-50 transition-colors">
                    <TableCell className="font-mono text-small font-medium text-neutral-900">{part.code}</TableCell>
                    <TableCell className="text-small text-neutral-700">{part.designation}</TableCell>
                    <TableCell>
                      <CriticalityBadge level={part.criticite as any} />
                    </TableCell>
                    <TableCell className="text-right text-small font-medium text-neutral-900">
                      {Math.round(part.quantite).toString()}
                    </TableCell>
                    {isManager && (
                      <TableCell className="text-right text-small font-medium text-neutral-900">
                        {part.total.toLocaleString()}
                      </TableCell>
                    )}
                    <TableCell className="text-right text-small text-neutral-600">
                      {delayDays > 0 ? Math.round(delayDays) : "—"}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        onClick={() => handleViewDetails(part)}
                      >
                        <ChevronRight className="h-4 w-4 text-neutral-500" />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
        <SheetContent className="sm:max-w-lg">
          {selectedPurchase && (
            <>
              <SheetHeader>
                <SheetTitle>{selectedPurchase.code}</SheetTitle>
                <SheetDescription>{selectedPurchase.designation}</SheetDescription>
              </SheetHeader>
              <div className="space-y-4 py-4">
                <div className="flex gap-2 items-center">
                  <CriticalityBadge level={selectedPurchase.criticite as any} />
                  <Badge variant="secondary">Accouplement</Badge>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-small text-neutral-600">Qté à commander (n_ac)</p>
                    <p className="text-h4 text-neutral-900">{selectedPurchase.quantite.toFixed(2)}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-small text-neutral-600">Budget</p>
                    <p className="text-h4 text-primary">{selectedPurchase.total.toLocaleString()} MAD</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4 text-small text-neutral-700">
                  <div>
                    <p className="text-neutral-500">Prix unitaire</p>
                    <p>{selectedPurchase.prixUnitaire.toLocaleString()} MAD</p>
                  </div>
                  <div>
                    <p className="text-neutral-500">Délai (j)</p>
                    <p>
                      {(() => {
                        const pv = previsionMap.get(selectedPurchase.code);
                        const dl = pv?.delai ?? 0;
                        return dl > 0 ? Math.round(dl) : "—";
                      })()}
                    </p>
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
