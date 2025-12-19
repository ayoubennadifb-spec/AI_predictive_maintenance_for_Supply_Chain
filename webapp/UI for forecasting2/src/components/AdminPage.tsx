import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "./PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Alert, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { useAuth } from "./AuthContext";
import type { AdminUser } from "../services/adminData";
import {
  adminCreateUser,
  adminDeleteUser,
  adminGetUserPasswordResetCode,
  adminListUsers,
  adminUpdateUser,
} from "../services/adminData";

type RoleOption = "manager" | "approvisionnement" | "logistique" | "superadmin";

function roleLabel(role: string) {
  switch (role) {
    case "manager":
      return "Manager";
    case "approvisionnement":
      return "Approvisionneur";
    case "logistique":
      return "Logistique";
    case "superadmin":
      return "Super admin";
    default:
      return role;
  }
}

export function AdminPage() {
  const { user } = useAuth();

  // Only superadmin can manage users
  const isSuperAdmin = user?.role === "superadmin";

  const identity = useMemo(
    () => ({
      user: user?.nom || user?.email || user?.id || "superadmin",
      role: user?.role || "superadmin",
    }),
    [user]
  );

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newNom, setNewNom] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<RoleOption>("manager");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isSuperAdmin) return;
    void refreshUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperAdmin]);

  async function refreshUsers() {
    try {
      setLoading(true);
      setError(null);
      const res = await adminListUsers({
        search: search.trim() || undefined,
        identity,
      });
      setUsers(res.results);
    } catch (err: any) {
      setError(err?.message || "Impossible de charger les utilisateurs.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    if (!newUsername.trim() || !newRole) return;
    try {
      setSubmitting(true);
      setError(null);
      await adminCreateUser(
        {
          username: newUsername.trim(),
          email: newEmail.trim() || undefined,
          nom: newNom.trim() || undefined,
          role: newRole,
          password: newPassword || undefined,
        },
        identity
      );
      setNewUsername("");
      setNewEmail("");
      setNewNom("");
      setNewPassword("");
      await refreshUsers();
    } catch (err: any) {
      setError(err?.message || "Création utilisateur échouée.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleChangeRole(userRow: AdminUser, role: RoleOption) {
    if (role === userRow.role) return;
    try {
      setSubmitting(true);
      setError(null);
      await adminUpdateUser(
        userRow.id,
        { role },
        identity
      );
      await refreshUsers();
    } catch (err: any) {
      setError(err?.message || "Mise à jour du rôle échouée.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResetPassword(userRow: AdminUser) {
    const pwd = window.prompt(`Nouveau mot de passe pour ${userRow.username || userRow.email} :`);
    if (!pwd) return;
    if (pwd.length < 4) {
      setError("Le mot de passe doit contenir au moins 4 caractères.");
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      await adminUpdateUser(
        userRow.id,
        { password: pwd },
        identity
      );
    } catch (err: any) {
      setError(err?.message || "Réinitialisation du mot de passe échouée.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteUser(userRow: AdminUser) {
    const confirm = window.confirm(`Supprimer l'utilisateur ${userRow.username || userRow.email} ?`);
    if (!confirm) return;
    try {
      setSubmitting(true);
      setError(null);
      await adminDeleteUser(userRow.id, identity);
      await refreshUsers();
    } catch (err: any) {
      setError(err?.message || "Suppression utilisateur échouée.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleShowResetCode(userRow: AdminUser) {
    try {
      setError(null);
      const res = await adminGetUserPasswordResetCode(userRow.id, identity);
      if (!res.ok || !res.code) {
        window.alert("Aucun code de rÇ¸initialisation actif pour cet utilisateur.");
        return;
      }
      const exp = res.expires_at ? new Date(res.expires_at).toLocaleString() : "inconnu";
      window.alert(
        `Code de rÇ¸initialisation pour ${userRow.username || userRow.email} : ${res.code}\n\nValide jusqu'au : ${exp}.`
      );
    } catch (err: any) {
      setError(err?.message || "Impossible de rÇ¸cupÇ¸rer le code de rÇ¸initialisation.");
    }
  }

  if (!isSuperAdmin) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Accès réservé au rôle <span className="font-semibold">superadmin</span> pour la gestion des comptes
          utilisateurs. Connectez-vous avec un profil autorisé.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Administration des utilisateurs"
        description="Créer, mettre à jour et supprimer les comptes applicatifs. Seul le rôle superadmin peut accéder à cette page."
        breadcrumbs={[
          { label: "Accueil", href: "#" },
          { label: "Administration" },
        ]}
      />

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Create user */}
      <Card className="border-neutral-200 shadow-sm">
        <CardHeader>
          <CardTitle>Créer un utilisateur</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            onSubmit={handleCreateUser}
            className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end"
          >
            <div className="space-y-1">
              <Label htmlFor="username">Nom d&apos;utilisateur</Label>
              <Input
                id="username"
                placeholder="ex: manager1"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="email">Email (optionnel)</Label>
              <Input
                id="email"
                type="email"
                placeholder="prenom.nom@ocp.com"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="nom">Nom affiché (optionnel)</Label>
              <Input
                id="nom"
                placeholder="Nom complet"
                value={newNom}
                onChange={(e) => setNewNom(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="role">Rôle</Label>
              <select
                id="role"
                className="border rounded-md px-2 py-2 text-sm"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as RoleOption)}
              >
                <option value="manager">Manager</option>
                <option value="approvisionnement">Approvisionneur</option>
                <option value="logistique">Logistique</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">Mot de passe (optionnel)</Label>
              <Input
                id="password"
                type="password"
                placeholder="Min. 4 caractères"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div className="md:col-span-5">
              <Button type="submit" disabled={submitting}>
                {submitting ? "Création..." : "Créer l'utilisateur"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* User list */}
      <Card className="border-neutral-200 shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <CardTitle>Utilisateurs existants</CardTitle>
          <div className="flex items-center gap-2">
            <Input
              placeholder="Rechercher par nom ou email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-48 md:w-64"
            />
            <Button variant="outline" size="sm" onClick={() => refreshUsers()} disabled={loading}>
              {loading ? "Chargement..." : "Rechercher"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b text-xs uppercase text-neutral-500">
                <th className="py-2 text-left">Utilisateur</th>
                <th className="py-2 text-left">Email</th>
                <th className="py-2 text-left">Rôle</th>
                <th className="py-2 text-left">Créé le</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-neutral-500">
                    Aucun utilisateur trouvé.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0">
                  <td className="py-2">
                    <div className="flex flex-col">
                      <span className="font-medium text-neutral-900">{u.username || u.nom || u.email}</span>
                      {u.nom && <span className="text-xs text-neutral-500">{u.nom}</span>}
                    </div>
                  </td>
                  <td className="py-2 text-neutral-700">{u.email}</td>
                  <td className="py-2">
                    <select
                      className="border rounded-md px-2 py-1 text-xs"
                      value={u.role as RoleOption}
                      onChange={(e) => handleChangeRole(u, e.target.value as RoleOption)}
                      disabled={submitting}
                    >
                      <option value="manager">Manager</option>
                      <option value="approvisionnement">Approvisionneur</option>
                      <option value="logistique">Logistique</option>
                      <option value="superadmin">Super admin</option>
                    </select>
                  </td>
                  <td className="py-2 text-xs text-neutral-500">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : "-"}
                  </td>
                  <td className="py-2 text-right space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleShowResetCode(u)}
                      disabled={submitting}
                    >
                      Code de récupération
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleResetPassword(u)}
                      disabled={submitting}
                    >
                      Réinitialiser le mot de passe
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDeleteUser(u)}
                      disabled={submitting}
                    >
                      Supprimer
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 text-xs text-neutral-500 flex items-center justify-between">
            <span>
              {users.length} utilisateur{users.length > 1 ? "s" : ""} affiché(s)
            </span>
            <Badge variant="outline">Super admin uniquement</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
