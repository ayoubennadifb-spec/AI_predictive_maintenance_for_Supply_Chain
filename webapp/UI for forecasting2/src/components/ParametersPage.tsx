import { useEffect, useMemo, useState } from 'react';
import { PageHeader } from './PageHeader';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Slider } from './ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { toast } from 'sonner@2.0.3';
import { AlertTriangle, Bell, Gauge, RefreshCcw, Save, Settings, Shield } from 'lucide-react';
import { DEFAULT_PARAMETERS, loadParameters, saveParameters, ParametersConfig } from '../services/mlData';
import { useAuth } from './AuthContext';

type ParametersPageProps = {
  onBack?: () => void;
};

export function ParametersPage({ onBack }: ParametersPageProps) {
  const { user } = useAuth();
  const [params, setParams] = useState<ParametersConfig>(DEFAULT_PARAMETERS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [source, setSource] = useState<'api' | 'fallback'>('api');

  useEffect(() => {
    const load = async () => {
      try {
        const { data, source } = await loadParameters();
        setParams(data);
        setSource(source);
        if (data.updatedAt) {
          setLastSavedAt(new Date(data.updatedAt));
        }
      } catch (err) {
        toast.error('Impossible de charger les paramètres', { description: (err as Error)?.message });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const formatCurrency = (value: number) => value.toLocaleString('fr-FR', { style: 'currency', currency: 'MAD' });

  const updateParam = <K extends keyof ParametersConfig>(key: K, value: ParametersConfig[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveParameters(params, { user: user?.nom, role: user?.role });
      setLastSavedAt(new Date());
      setSource('api');
      toast.success('Paramètres enregistrés', {
        description: 'Sauvegarde côté backend effectuée.',
      });
    } catch (err) {
      toast.error('Échec de sauvegarde', { description: (err as Error)?.message || 'Backend non joignable' });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setParams(DEFAULT_PARAMETERS);
    toast.info('Valeurs par défaut rétablies', { description: 'Retour aux seuils recommandés.' });
    await handleSave();
  };

  const lastSavedLabel = useMemo(() => {
    if (!lastSavedAt) return source === 'api' ? 'Jamais' : 'Local uniquement';
    return lastSavedAt.toLocaleString('fr-FR', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
  }, [lastSavedAt, source]);

  if (loading) {
    return <div className="p-6 text-neutral-700">Chargement des paramètres...</div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Paramètres"
        description="Ajustez les seuils d'alerte, le modèle actif et les préférences de notification."
        breadcrumbs={[
          { label: 'Accueil', href: '#' },
          { label: 'Administration', href: '#' },
          { label: 'Paramètres' },
        ]}
        actions={
          <>
            {onBack && (
              <Button variant="outline" size="sm" onClick={onBack} className="gap-2">
                <Shield className="w-4 h-4" />
                Retour admin
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={handleReset} className="gap-2" disabled={saving}>
              <RefreshCcw className="w-4 h-4" />
              Réinitialiser
            </Button>
            <Button size="sm" onClick={handleSave} className="gap-2 gradient-ocp hover:opacity-90 shadow-md" disabled={saving}>
              <Save className="w-4 h-4" />
              {saving ? 'Enregistrement…' : 'Enregistrer'}
            </Button>
          </>
        }
      />

      <div className="flex items-center gap-3 text-sm text-neutral-600">
        <Badge variant="outline" className={`border ${source === 'api' ? 'bg-primary/5 text-primary border-primary/30' : 'bg-warning-50 text-warning-700 border-warning-200'}`}>
          <Settings className="w-4 h-4 mr-1" />
          {source === 'api' ? 'Connecté backend' : 'Mode local (fallback)'}
        </Badge>
        <span>Dernier enregistrement : {lastSavedLabel}</span>
      </div>

      <Tabs defaultValue="seuils" className="space-y-4">
        <TabsList className="bg-white border border-neutral-200 p-1 shadow-elevation-1">
          <TabsTrigger value="seuils" className="data-[state=active]:gradient-ocp data-[state=active]:text-white rounded-lg">
            Seuils
          </TabsTrigger>
          <TabsTrigger value="modele" className="data-[state=active]:gradient-ocp data-[state=active]:text-white rounded-lg">
            Modèle & refresh
          </TabsTrigger>
          <TabsTrigger value="notifications" className="data-[state=active]:gradient-ocp data-[state=active]:text-white rounded-lg">
            Notifications
          </TabsTrigger>
        </TabsList>

        <TabsContent value="seuils" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="shadow-sm border-neutral-200">
              <CardHeader>
                <CardTitle className="text-h3 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-warning-600" />
                  Seuils d'alerte
                </CardTitle>
                <CardDescription>Déclenchement des alertes rupture et délais longs.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="rupture">Seuil rupture (écart %)</Label>
                    <Badge variant="outline" className="bg-warning-50 text-warning-700 border-warning-200">
                      {params.ruptureThreshold}%
                    </Badge>
                  </div>
                  <Slider
                    id="rupture"
                    value={[params.ruptureThreshold]}
                    min={0}
                    max={100}
                    step={1}
                    onValueChange={(value) => updateParam('ruptureThreshold', value[0] ?? 0)}
                  />
                  <p className="text-xs text-neutral-500">
                    Une alerte est levée si la prévision M+1 dépasse le stock actuel de plus de ce pourcentage.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="lead">Délai long (jours)</Label>
                    <Input
                      id="lead"
                      type="number"
                      value={params.longLeadDays}
                      onChange={(e) => updateParam('longLeadDays', Math.max(0, Number(e.target.value) || 0))}
                    />
                    <p className="text-xs text-neutral-500">Au-delà de ce délai, la pièce est marquée en vigilance.</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="budget">Plafond budget (MAD)</Label>
                    <Input
                      id="budget"
                      type="number"
                      value={params.budgetCap ?? ''}
                      onChange={(e) => {
                        const val = e.target.value;
                        updateParam('budgetCap', val === '' ? null : Math.max(0, Number(val) || 0));
                      }}
                    />
                    <p className="text-xs text-neutral-500">Utilisé pour les simulations et la sélection automatique.</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-sm border-neutral-200">
              <CardHeader>
                <CardTitle className="text-h3 flex items-center gap-2">
                  <Shield className="w-5 h-5 text-primary" />
                  Gouvernance
                </CardTitle>
                <CardDescription>Logique métier appliquée aux recommandations.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-neutral-900">Favoriser les pièces critiques</p>
                    <p className="text-xs text-neutral-500">Sélection automatique des pièces haute criticité dans les priorités.</p>
                  </div>
                  <Switch checked={params.autoSelectCritical} onCheckedChange={(checked) => updateParam('autoSelectCritical', checked)} />
                </div>

                <Separator />

                <div className="space-y-2">
                  <Label>Résumé des seuils</Label>
                  <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-sm text-neutral-700 space-y-1">
                    <p>
                      • Rupture : alerte dès que prévision &gt; stock + <strong>{params.ruptureThreshold}%</strong>
                    </p>
                    <p>
                      • Délai long : &gt; <strong>{params.longLeadDays} jours</strong>
                    </p>
                    <p>
                      • Plafond budget : <strong>{formatCurrency(params.budgetCap ?? 0)}</strong>
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="modele" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="shadow-sm border-neutral-200">
              <CardHeader>
                <CardTitle className="text-h3 flex items-center gap-2">
                  <Gauge className="w-5 h-5 text-primary" />
                  Modèle actif
                </CardTitle>
                <CardDescription>Choix du modèle ML utilisé pour les prévisions.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="modele">Modèle</Label>
                  <Select value={params.activeModel} onValueChange={(value) => updateParam('activeModel', value)}>
                    <SelectTrigger id="modele" className="rounded-input">
                      <SelectValue placeholder="Choisir un modèle" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hist-gradient-boosting">HistGradientBoosting (recommandé)</SelectItem>
                      <SelectItem value="random-forest">RandomForest (robuste)</SelectItem>
                      <SelectItem value="ridge-reg">Ridge Regression (rapide)</SelectItem>
                      <SelectItem value="baseline">Baseline moyenne mobile</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Fréquence de rafraîchissement</Label>
                  <Select
                    value={params.refreshFrequency}
                    onValueChange={(value) => updateParam('refreshFrequency', value as ParametersConfig['refreshFrequency'])}
                  >
                    <SelectTrigger className="rounded-input">
                      <SelectValue placeholder="Sélectionner la fréquence" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="journalier">Journalier</SelectItem>
                      <SelectItem value="hebdomadaire">Hebdomadaire</SelectItem>
                      <SelectItem value="mensuel">Mensuel</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-neutral-500">Contrôle la cadence des recalculs et de l'actualisation des données.</p>
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-sm border-neutral-200">
              <CardHeader>
                <CardTitle className="text-h3 flex items-center gap-2">
                  <RefreshCcw className="w-5 h-5 text-info-600" />
                  Impact
                </CardTitle>
                <CardDescription>Vue synthétique des changements appliqués.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-neutral-700">
                <div className="flex items-center justify-between rounded-lg border border-neutral-200 p-3 bg-neutral-50">
                  <div>
                    <p className="font-medium">Modèle</p>
                    <p className="text-xs text-neutral-500">{params.activeModel}</p>
                  </div>
                  <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20">
                    Actif
                  </Badge>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-neutral-200 p-3 bg-neutral-50">
                  <div>
                    <p className="font-medium">Rafraîchissement</p>
                    <p className="text-xs text-neutral-500">Cadence {params.refreshFrequency}</p>
                  </div>
                  <Badge variant="outline" className="bg-info-50 text-info-700 border-info-200">
                    Planning
                  </Badge>
                </div>
                <p className="text-xs text-neutral-500">
                  Ces réglages sont persistés côté backend et peuvent être consommés par vos jobs de recalcul.
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="notifications" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="shadow-sm border-neutral-200">
              <CardHeader>
                <CardTitle className="text-h3 flex items-center gap-2">
                  <Bell className="w-5 h-5 text-primary" />
                  Notifications
                </CardTitle>
                <CardDescription>Choisissez les alertes à recevoir dans le tableau de bord.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-neutral-900">Alertes rupture</p>
                    <p className="text-xs text-neutral-500">Signaler les pièces proches de la rupture.</p>
                  </div>
                  <Switch checked={params.notifyRupture} onCheckedChange={(checked) => updateParam('notifyRupture', checked)} />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-neutral-900">Alertes budget</p>
                    <p className="text-xs text-neutral-500">Informer des dépassements vs plafond budget.</p>
                  </div>
                  <Switch checked={params.notifyBudget} onCheckedChange={(checked) => updateParam('notifyBudget', checked)} />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-neutral-900">Digest hebdomadaire</p>
                    <p className="text-xs text-neutral-500">Résumé des mouvements et ajustements.</p>
                  </div>
                  <Switch checked={params.notifyDigest} onCheckedChange={(checked) => updateParam('notifyDigest', checked)} />
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-sm border-neutral-200">
              <CardHeader>
                <CardTitle className="text-h3 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-warning-600" />
                  Synthèse
                </CardTitle>
                <CardDescription>Récapitulatif des paramètres de notification.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="rounded-lg border border-neutral-200 p-3 bg-neutral-50 space-y-2 text-sm text-neutral-700">
                  <p>• Rupture : {params.notifyRupture ? 'activées' : 'désactivées'}</p>
                  <p>• Budget : {params.notifyBudget ? 'activées' : 'désactivées'}</p>
                  <p>• Digest : {params.notifyDigest ? 'activé' : 'désactivé'}</p>
                </div>
                <p className="text-xs text-neutral-500">
                  Les choix sont stockés côté backend. Branchez votre service de notification pour les exploiter.
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
