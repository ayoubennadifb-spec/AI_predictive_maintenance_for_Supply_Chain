import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from 'react';

export type UserRole = 'manager' | 'approvisionnement' | 'logistique';

export interface User {
  id: string;
  nom: string;
  email: string;
  role: UserRole;
}

interface AuthContextType {
  user: User | null;
  login: (usernameOrEmail: string, password: string) => Promise<boolean>;
  signup: (payload: { nom: string; email: string; username: string; password: string; role: UserRole }) => Promise<boolean>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE =
  ((import.meta as any).env?.VITE_API_BASE as string | undefined)?.trim() ||
  (typeof window !== 'undefined' ? window.location.origin : '');
const API_TOKEN = (import.meta as any).env?.VITE_API_TOKEN || '';

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_TOKEN) headers['X-API-KEY'] = API_TOKEN;
  return headers;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  if (!API_BASE) throw new Error('API_BASE requis');
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text();
    let message = txt || `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(txt) as { error?: unknown; code?: unknown; details?: unknown };
      const code = (parsed?.code ?? '').toString();
      if (code === 'username_exists') message = "Nom d'utilisateur déjà utilisé. Essayez un autre (ex: manager2).";
      else if (code === 'missing_fields') message = 'Champs manquants. Vérifiez le formulaire.';
      else if (code === 'password_too_short') message = 'Mot de passe trop court (min 4 caractères).';
      else if (code === 'invalid_credentials') message = 'Identifiants incorrects.';
      else if (code === 'invalid_json') message = 'Requête invalide.';
      else if (code === 'unauthorized') message = 'Accès refusé.';
      else if (parsed?.error) message = String(parsed.error);
      else if (parsed?.details) message = String(parsed.details);
    } catch {
      // txt n'est pas du JSON : on garde le texte brut
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    if (typeof localStorage === 'undefined') return null;
    try {
      const raw = localStorage.getItem('ocp-auth-user');
      return raw ? (JSON.parse(raw) as User) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (typeof localStorage === 'undefined') return;
    try {
      if (user) localStorage.setItem('ocp-auth-user', JSON.stringify(user));
      else localStorage.removeItem('ocp-auth-user');
    } catch {
      // ignore storage errors
    }
  }, [user]);

  const login = async (usernameOrEmail: string, password: string): Promise<boolean> => {
    const json = await postJson<{ ok: boolean; user: User }>('/api/auth/login/', {
      usernameOrEmail,
      password,
    });
    if (!json?.ok || !json.user) return false;
    setUser(json.user);
    return true;
  };

  const signup = async (payload: { nom: string; email: string; username: string; password: string; role: UserRole }): Promise<boolean> => {
    const json = await postJson<{ ok: boolean; user: User }>('/api/auth/signup/', payload);
    if (!json?.ok || !json.user) return false;
    setUser(json.user);
    return true;
  };

  const logout = () => {
    setUser(null);
  };

  const value = useMemo(
    () => ({
      user,
      login,
      signup,
      logout,
      isAuthenticated: !!user,
    }),
    [user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
