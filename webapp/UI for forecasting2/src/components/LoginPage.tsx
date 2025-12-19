import { useState } from 'react';
import { AlertCircle } from 'lucide-react';
import ocpLogo from 'figma:asset/ea0333669458322a030507607d5724be95c62222.png';
import { useAuth } from './AuthContext';
import { Alert, AlertDescription } from './ui/alert';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';

export function LoginPage({ onGoToSignup }: { onGoToSignup?: () => void }) {
  const [view, setView] = useState<'login' | 'forgot' | 'reset'>('login');

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const [resetUsernameOrEmail, setResetUsernameOrEmail] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [debugCode, setDebugCode] = useState<string | null>(null);

  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const { login, requestPasswordReset, resetPassword } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setInfo('');

    if (!username || !password) {
      setError('Veuillez saisir vos identifiants');
      return;
    }

    setSubmitting(true);
    try {
      const success = await login(username, password);
      if (!success) setError('Identifiants incorrects. Veuillez réessayer.');
    } catch (err: any) {
      setError(err?.message || 'Connexion impossible.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setInfo('');
    setDebugCode(null);

    if (!resetUsernameOrEmail) {
      setError("Veuillez saisir votre email ou nom d'utilisateur.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await requestPasswordReset(resetUsernameOrEmail);
      setInfo('Si le compte existe, un code de réinitialisation a été envoyé.');
      setDebugCode(res?.debugCode ?? null);
      setView('reset');
    } catch (err: any) {
      setError(err?.message || 'Demande impossible.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setInfo('');

    if (!resetUsernameOrEmail || !resetCode || !newPassword) {
      setError('Veuillez remplir tous les champs.');
      return;
    }
    if (newPassword.length < 4) {
      setError('Mot de passe trop court (min 4 caractères).');
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setError('Les mots de passe ne correspondent pas.');
      return;
    }

    setSubmitting(true);
    try {
      const ok = await resetPassword({ usernameOrEmail: resetUsernameOrEmail, code: resetCode, newPassword });
      if (!ok) {
        setError('Réinitialisation échouée.');
        return;
      }
      await login(resetUsernameOrEmail, newPassword);
      setInfo('Mot de passe mis à jour.');
    } catch (err: any) {
      setError(err?.message || 'Réinitialisation impossible.');
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
          <div className="flex justify-center animate-fade-in">
            <div className="relative">
              <img src={ocpLogo} alt="OCP Group" className="h-16 w-auto object-contain" />
              <div className="absolute -inset-4 bg-ocp-green/10 blur-2xl -z-10 rounded-full" />
            </div>
          </div>

          <div className="text-center space-y-2">
            <CardTitle className="text-h1 text-neutral-900">Système de Prévision</CardTitle>
            <CardDescription className="text-body text-neutral-600">Anticiper. Gérer. Optimiser.</CardDescription>
            <p className="text-small text-neutral-500">Gestion des accouplements et pièces détachées</p>
          </div>
        </CardHeader>

        <CardContent>
          {(error || info) && (
            <Alert variant={error ? 'destructive' : 'default'} className="animate-slide-up mb-6">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error || info}</AlertDescription>
            </Alert>
          )}

          {view === 'login' && (
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username" className="text-small font-semibold text-neutral-700">
                    Nom d&apos;utilisateur
                  </Label>
                  <Input
                    id="username"
                    type="text"
                    placeholder="Entrez votre nom d'utilisateur"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                    autoComplete="username"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-small font-semibold text-neutral-700">
                    Mot de passe
                  </Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="Entrez votre mot de passe"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                    autoComplete="current-password"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end">
                <Button
                  type="button"
                  variant="link"
                  className="px-0 h-auto text-ocp-green"
                  onClick={() => {
                    setError('');
                    setInfo('');
                    setDebugCode(null);
                    setResetCode('');
                    setNewPassword('');
                    setConfirmNewPassword('');
                    setResetUsernameOrEmail(username || '');
                    setView('forgot');
                  }}
                >
                  Mot de passe oublié ?
                </Button>
              </div>

              <Button
                type="submit"
                disabled={submitting}
                className="w-full h-11 gradient-ocp hover:opacity-90 transition-all duration-200 shadow-md hover:shadow-lg"
              >
                {submitting ? 'Connexion...' : 'Se connecter'}
              </Button>
            </form>
          )}

          {view === 'forgot' && (
            <form onSubmit={handleForgot} className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="reset-user" className="text-small font-semibold text-neutral-700">
                  Email ou nom d&apos;utilisateur
                </Label>
                <Input
                  id="reset-user"
                  type="text"
                  placeholder="ex: prenom.nom@ocp.ma"
                  value={resetUsernameOrEmail}
                  onChange={(e) => setResetUsernameOrEmail(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="username"
                />
              </div>

              <div className="flex items-center gap-3">
                <Button type="button" variant="outline" onClick={() => setView('login')} className="h-11 flex-1">
                  Retour
                </Button>
                <Button type="submit" disabled={submitting} className="h-11 flex-1 gradient-ocp hover:opacity-90">
                  {submitting ? 'Envoi...' : 'Envoyer le code'}
                </Button>
              </div>
            </form>
          )}

          {view === 'reset' && (
            <form onSubmit={handleReset} className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="reset-user-2" className="text-small font-semibold text-neutral-700">
                  Email ou nom d&apos;utilisateur
                </Label>
                <Input
                  id="reset-user-2"
                  type="text"
                  value={resetUsernameOrEmail}
                  onChange={(e) => setResetUsernameOrEmail(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="username"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="reset-code" className="text-small font-semibold text-neutral-700">
                  Code de réinitialisation
                </Label>
                <Input
                  id="reset-code"
                  type="text"
                  placeholder="000000"
                  value={resetCode}
                  onChange={(e) => setResetCode(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  inputMode="numeric"
                />
                {debugCode && (
                  <p className="text-xs text-neutral-500">
                    Code (debug): <span className="font-mono">{debugCode}</span>
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-password" className="text-small font-semibold text-neutral-700">
                  Nouveau mot de passe
                </Label>
                <Input
                  id="new-password"
                  type="password"
                  placeholder="Min. 4 caractères"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="new-password"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-new-password" className="text-small font-semibold text-neutral-700">
                  Confirmer le mot de passe
                </Label>
                <Input
                  id="confirm-new-password"
                  type="password"
                  value={confirmNewPassword}
                  onChange={(e) => setConfirmNewPassword(e.target.value)}
                  className="h-11 rounded-input border-neutral-300 focus:border-ocp-green focus:ring-ocp-green/20"
                  autoComplete="new-password"
                />
              </div>

              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setError('');
                    setInfo('');
                    setDebugCode(null);
                    setView('login');
                  }}
                  className="h-11 flex-1"
                >
                  Retour
                </Button>
                <Button type="submit" disabled={submitting} className="h-11 flex-1 gradient-ocp hover:opacity-90">
                  {submitting ? 'Mise à jour...' : 'Mettre à jour'}
                </Button>
              </div>
            </form>
          )}

          {view === 'login' && onGoToSignup && (
            <div className="mt-6 pt-6 border-t border-neutral-200">
              <div className="text-center">
                <Button type="button" variant="outline" onClick={onGoToSignup} className="w-full h-11">
                  Créer un compte
                </Button>
              </div>
            </div>
          )}

          <div className="mt-6 text-center">
            <p className="text-xs text-neutral-500">© 2025 Groupe OCP. Tous droits réservés.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
