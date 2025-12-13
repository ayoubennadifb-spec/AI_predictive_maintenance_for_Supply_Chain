import { PageHeader } from "./PageHeader";
import { Card, CardContent } from "./ui/card";
import { Alert, AlertDescription } from "./ui/alert";
import { useAuth } from "./AuthContext";

export function AdminPage() {
  const { user } = useAuth();

  if (!user || user.role !== "manager") {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Accès réservé aux comptes <span className="font-semibold">manager</span>. Connectez-vous avec un profil autorisé.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Administration"
        description="La nouvelle interface d’administration React est en cours de construction. En attendant, utilisez la console Django."
        breadcrumbs={[
          { label: "Accueil", href: "#" },
          { label: "Administration" },
        ]}
      />

      <Card className="border-neutral-200 shadow-sm">
        <CardContent className="p-6 space-y-3 text-sm text-neutral-700">
          <p>
            Pour gérer les données avancées (pièces, consommations, utilisateurs...), utilisez encore la page Django
            admin accessible via <code>/admin/</code>.
          </p>
          <p>
            Les APIs backend et les services React nécessaires à une administration 100% React sont en place, mais
            l’interface doit encore être finalisée.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
