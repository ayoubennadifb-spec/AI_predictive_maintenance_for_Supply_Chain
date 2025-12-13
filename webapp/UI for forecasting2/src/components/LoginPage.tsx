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
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!username || !password) {
      setError('Veuillez saisir vos identifiants');
      return;
    }

    setSubmitting(true);
    try {
      const success = await login(username, password);
      if (!success) setError("Identifiants incorrects. Veuillez réessayer.");
    } catch (err: any) {
      setError(err?.message || 'Connexion impossible.');
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
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <Alert variant="destructive" className="animate-slide-up">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

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

            <Button
              type="submit"
              disabled={submitting}
              className="w-full h-11 gradient-ocp hover:opacity-90 transition-all duration-200 shadow-md hover:shadow-lg"
            >
              {submitting ? 'Connexion...' : 'Se connecter'}
            </Button>
          </form>

          {onGoToSignup && (
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
