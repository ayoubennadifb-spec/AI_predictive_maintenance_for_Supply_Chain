import { useState } from 'react';
import { AlertCircle, ArrowLeft } from 'lucide-react';
import ocpLogo from 'figma:asset/ea0333669458322a030507607d5724be95c62222.png';
import { useAuth, UserRole } from './AuthContext';
import { Alert, AlertDescription } from './ui/alert';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

export function SignupPage({ onGoToLogin }: { onGoToLogin?: () => void }) {
  const { signup } = useAuth();
  const [nom, setNom] = useState('');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [role, setRole] = useState<UserRole>('manager');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!nom || !username || !password || !role) {
      setError('Veuillez remplir tous les champs obligatoires.');
      return;
    }
    if (password.length < 4) {
      setError('Mot de passe trop court (min 4 caractères).');
      return;
    }
    if (password !== confirmPassword) {
      setError('Les mots de passe ne correspondent pas.');
      return;
    }

    setSubmitting(true);
    try {
      const ok = await signup({ nom, email, username, password, role });
      if (!ok) setError("Inscription échouée.");
    } catch (err: any) {
      setError(err?.message || "Inscription impossible.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen gradient-ocp flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-20 left-20 w-72 h-72 bg-white rounded-full blur-3xl animate-pulse-slow" />
        <div
          className="absolute bottom-20 right-20 w-96 h-96 bg-white rounded-full blur-3xl animate-pulse-slow"
          style={{ animationDelay: '1s' }}
        />
      </div>

      <Card className="w-full max-w-md relative z-10 animate-scale shadow-elevation-24 border-0">
        <CardHeader className="space-y-6 pb-6">
          <div className="flex items-center justify-between">
            <Button type="button" variant="ghost" size="sm" onClick={onGoToLogin} className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              Retour
            </Button>
            <div className="flex justify-center flex-1">
              <div className="relative">
                <img src={ocpLogo} alt="OCP Group" className="h-12 w-auto object-contain" />
                <div className="absolute -inset-4 bg-ocp-green/10 blur-2xl -z-10 rounded-full" />
              </div>
            </div>
            <div className="w-[64px]" />
          </div>

          <div className="text-center space-y-2">
            <CardTitle className="text-h1 text-neutral-900">Créer un compte</CardTitle>
            <CardDescription className="text-body text-neutral-600">
              Choisissez votre rôle et définissez vos identifiants
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <Alert variant="destructive" className="animate-slide-up">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="nom" className="text-small font-semibold text-neutral-700">
                  Nom complet <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="nom"
                  type="text"
                  placeholder="Ex: Fatima Ziani"
                  value={nom}
                  onChange={(e) => setNom(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="name"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email" className="text-small font-semibold text-neutral-700">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="ex: prenom.nom@ocp.ma"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="email"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="username" className="text-small font-semibold text-neutral-700">
                  Nom d&apos;utilisateur <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Ex: manager"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="username"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-small font-semibold text-neutral-700">
                  Rôle <span className="text-red-500">*</span>
                </Label>
                <Select value={role} onValueChange={(v) => setRole(v as UserRole)}>
                  <SelectTrigger className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20">
                    <SelectValue placeholder="Choisir un rôle" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manager">Manager</SelectItem>
                    <SelectItem value="approvisionnement">Approvisionnement</SelectItem>
                    <SelectItem value="logistique">Logistique</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-small font-semibold text-neutral-700">
                  Mot de passe <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Min. 4 caractères"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="new-password"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-small font-semibold text-neutral-700">
                  Confirmer le mot de passe <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="Répétez le mot de passe"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="new-password"
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={submitting}
              className="w-full h-11 gradient-ocp hover:opacity-90 transition-all duration-200 shadow-md hover:shadow-lg"
            >
              {submitting ? 'Création...' : "S'inscrire"}
            </Button>
          </form>

          <div className="mt-6 text-center">
            <Button type="button" variant="link" onClick={onGoToLogin}>
              Déjà un compte ? Se connecter
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
