import React, { useEffect, useState } from "react";
import { api, setAuthToken } from "./api";

type Role = "SUPER_ADMIN" | "MANAGER" | "LOGISTIQUE" | "APPROVISIONNEUR";

interface UserSummary {
  id: string;
  email: string;
  role: Role;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

type View = "login" | "dashboard";

export const App: React.FC = () => {
  const [view, setView] = useState<View>("login");
  const [email, setEmail] = useState("superadmin@example.com");
  const [password, setPassword] = useState("SuperAdmin123!");
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>("MANAGER");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (token) {
      setAuthToken(token);
      setView("dashboard");
      void fetchUsers();
    } else {
      setAuthToken(null);
      setView("login");
    }
  }, [token]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.post<{ accessToken: string; refreshToken: string }>(
        "/auth/login",
        { email, password },
      );
      setToken(res.data.accessToken);
    } catch (err: any) {
      setError(err?.response?.data?.message ?? "Login failed");
    }
  }

  async function fetchUsers() {
    setLoadingUsers(true);
    try {
      const res = await api.get<UserSummary[]>("/admin/users");
      setUsers(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.message ?? "Failed to load users");
    } finally {
      setLoadingUsers(false);
    }
  }

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/admin/users", {
        email: newEmail,
        password: newPassword,
        role: newRole,
      });
      setNewEmail("");
      setNewPassword("");
      await fetchUsers();
    } catch (err: any) {
      setError(err?.response?.data?.message ?? "Failed to create user");
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(user: UserSummary) {
    setBusy(true);
    setError(null);
    try {
      const path = user.isActive
        ? `/admin/users/${user.id}/deactivate`
        : `/admin/users/${user.id}/activate`;
      await api.patch(path);
      await fetchUsers();
    } catch (err: any) {
      setError(err?.response?.data?.message ?? "Failed to update user");
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(user: UserSummary) {
    const pwd = prompt(`Enter new password for ${user.email}`);
    if (!pwd) return;
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/admin/users/${user.id}/reset-password`, {
        password: pwd,
      });
    } catch (err: any) {
      setError(err?.response?.data?.message ?? "Failed to reset password");
    } finally {
      setBusy(false);
    }
  }

  if (view === "login") {
    return (
      <div style={{ maxWidth: 420, margin: "4rem auto", fontFamily: "system-ui" }}>
        <h1>Super Admin Login</h1>
        <p style={{ color: "#666" }}>Connect with your SUPER_ADMIN account.</p>
        {error && <p style={{ color: "red" }}>{error}</p>}
        <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{ width: "100%" }}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{ width: "100%" }}
            />
          </label>
          <button type="submit" style={{ marginTop: 8 }}>
            Login
          </button>
        </form>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 960, margin: "2rem auto", fontFamily: "system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Super Admin – User Management</h1>
        <button onClick={() => setToken(null)}>Logout</button>
      </header>
      {error && <p style={{ color: "red" }}>{error}</p>}

      <section style={{ marginTop: 24, padding: 16, border: "1px solid #ddd" }}>
        <h2>Create User</h2>
        <form onSubmit={handleCreateUser} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            type="email"
            placeholder="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as Role)}
          >
            <option value="MANAGER">Manager</option>
            <option value="LOGISTIQUE">Logistique</option>
            <option value="APPROVISIONNEUR">Approvisionneur</option>
          </select>
          <button type="submit" disabled={busy}>
            {busy ? "Saving..." : "Create"}
          </button>
        </form>
      </section>

      <section style={{ marginTop: 24 }}>
        <h2>Users</h2>
        <button onClick={() => fetchUsers()} disabled={loadingUsers}>
          {loadingUsers ? "Refreshing..." : "Refresh"}
        </button>
        <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>Email</th>
              <th style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>Role</th>
              <th style={{ borderBottom: "1px solid #ccc" }}>Active</th>
              <th style={{ borderBottom: "1px solid #ccc" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td style={{ padding: 4 }}>{u.email}</td>
                <td style={{ padding: 4 }}>{u.role}</td>
                <td style={{ padding: 4, textAlign: "center" }}>
                  {u.isActive ? "✅" : "❌"}
                </td>
                <td style={{ padding: 4 }}>
                  <button onClick={() => toggleActive(u)} disabled={busy}>
                    {u.isActive ? "Deactivate" : "Activate"}
                  </button>{" "}
                  <button onClick={() => resetPassword(u)} disabled={busy}>
                    Reset password
                  </button>
                </td>
              </tr>
            ))}
            {users.length === 0 && !loadingUsers && (
              <tr>
                <td colSpan={4} style={{ padding: 8, textAlign: "center", color: "#666" }}>
                  No users yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
};


