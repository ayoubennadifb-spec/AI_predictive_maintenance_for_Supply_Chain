import { useEffect, useMemo, useState } from "react";
import { UserPlus, Trash2 } from "lucide-react";
import { Hero } from "../Hero";
import { Table } from "../Table";
import { Button } from "../Button";
import { Modal } from "../Modal";
import { Input, Select } from "../Input";
import { Chip } from "../Chip";
import { useToast } from "../Toast";
import { PillFilter } from "../Tabs";
import { api } from "../../utils/api";

export function AdminUsers() {
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterRole, setFilterRole] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const { showToast } = useToast();

  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkRole, setBulkRole] = useState("student");
  const [bulkLoading, setBulkLoading] = useState(false);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const [newUser, setNewUser] = useState({
    name: "",
    email: "",
    password: "",
    role: "student",
    school: "",
    country: "",
  });

  const fetchUsers = async () => {
    try {
      const data = await api<{ users: any[] }>('/api/users');
      setUsers(data.users || []);
    } catch (err: any) {
      showToast(err?.message || "Failed to load users", "error");
    } finally {
      setLoading(false);
    }
  };

  const fetchAuditLogs = async () => {
    setAuditLoading(true);
    try {
      const data = await api<{ logs: any[] }>("/api/audit?limit=6");
      setAuditLogs(data.logs || []);
    } catch {
      setAuditLogs([]);
    } finally {
      setAuditLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
    fetchAuditLogs();
  }, []);

  const handleAddUser = () => {
    if (!newUser.name || !newUser.email || !newUser.password) {
      showToast("Please fill in all required fields", "error");
      return;
    }

    api('/api/users', {
      method: 'POST',
      body: JSON.stringify({
        full_name: newUser.name,
        email: newUser.email,
        password: newUser.password,
        role: newUser.role,
        school: newUser.school,
        country: newUser.country,
      }),
    })
      .then(() => {
        showToast("User added successfully", "success");
        setShowAddModal(false);
        setNewUser({ name: "", email: "", password: "", role: "student", school: "", country: "" });
        fetchUsers();
      })
      .catch((err) => showToast(err?.message || "Failed to add user", "error"));
    
  };

  const handleDeleteUser = (userId: string) => {
    api(`/api/users/${userId}`, { method: 'DELETE' })
      .then(() => {
        showToast("User deleted", "info");
        fetchUsers();
        fetchAuditLogs();
      })
      .catch((err) => showToast(err?.message || "Failed to delete", "error"));
  };

  const filteredUsers = Array.isArray(users)
    ? users
        .map((u) => ({
          ...u,
          name: u.name || u.full_name || u.fullName || u.email || "Unknown",
          email: u.email || "",
        }))
        .filter((user) => {
          const matchesRole = filterRole === "all" || user.role === filterRole;
          const q = searchQuery.toLowerCase();
          const name = (user.name || "").toLowerCase();
          const email = (user.email || "").toLowerCase();
          const matchesSearch = name.includes(q) || email.includes(q);
          return matchesRole && matchesSearch;
        })
    : [];

  const handleRoleChange = (userId: string, role: string) => {
    api(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ role }),
    })
      .then(() => {
        showToast("Role updated", "success");
        fetchUsers();
        fetchAuditLogs();
      })
      .catch((err: any) => showToast(err?.message || "Failed to update role", "error"));
  };

  const handleStatusChange = (userId: string, status: string) => {
    api(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    })
      .then(() => {
        showToast("Status updated", "success");
        fetchUsers();
        fetchAuditLogs();
      })
      .catch((err: any) => showToast(err?.message || "Failed to update status", "error"));
  };

  const allIds = useMemo(() => filteredUsers.map((u) => String(u.id)), [filteredUsers]);
  const allSelected = allIds.length > 0 && allIds.every((id) => selectedIds.includes(id));

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds([]);
    } else {
      setSelectedIds(allIds);
    }
  };

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const runBulkAction = async (action: string) => {
    if (selectedIds.length === 0) {
      showToast("Select at least one user", "error");
      return;
    }
    setBulkLoading(true);
    try {
      const payload: any = { action, user_ids: selectedIds };
      if (action === "role") payload.role = bulkRole;
      await api("/api/users/bulk", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Bulk action applied", "success");
      setSelectedIds([]);
      fetchUsers();
      fetchAuditLogs();
    } catch (err: any) {
      showToast(err?.message || "Bulk action failed", "error");
    } finally {
      setBulkLoading(false);
    }
  };

  const formatDate = (value?: string) => {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString();
  };

  const renderRisk = (user: any) => {
    if (user.role !== "student") return <span className="text-xs text-[#9CA3AF]">—</span>;
    if (!user.risk) return <Chip variant="default" size="sm">Unknown</Chip>;
    const label = String(user.risk.label || "unknown");
    const score = user.risk.score != null ? `${user.risk.score}` : "--";
    const variant =
      label === "high" ? "error" : label === "medium" ? "warning" : label === "low" ? "success" : "default";
    return (
      <Chip variant={variant} size="sm">
        {label.toUpperCase()} · {score}
      </Chip>
    );
  };

  const columns = [
    {
      key: "select",
      label: (
        <input
          type="checkbox"
          checked={allSelected}
          onChange={toggleSelectAll}
          onClick={(e) => e.stopPropagation()}
        />
      ),
      render: (user: any) => (
        <input
          type="checkbox"
          checked={selectedIds.includes(String(user.id))}
          onChange={() => toggleSelected(String(user.id))}
          onClick={(e) => e.stopPropagation()}
        />
      ),
    },
    { key: "name", label: "Name" },
    { key: "email", label: "Email" },
    {
      key: "role",
      label: "Role",
      render: (user: any) => (
        <div className="flex items-center gap-2">
          <Chip
            variant={
              user.role === "admin" ? "error" :
              user.role === "teacher" ? "secondary" : "primary"
            }
            size="sm"
          >
            {user.role}
          </Chip>
          <select
            className="glass rounded-lg px-2 py-1 text-sm outline-none"
            value={user.role}
            onChange={(e) => handleRoleChange(user.id, e.target.value)}
          >
            <option value="student">Student</option>
            <option value="teacher">Teacher</option>
            <option value="admin">Admin</option>
          </select>
        </div>
      ),
    },
    {
      key: "status",
      label: "Status",
      render: (user: any) => (
        <div className="flex items-center gap-2">
          <Chip
            variant={
              user.status === "suspended"
                ? "error"
                : user.status === "invited"
                ? "warning"
                : "success"
            }
            size="sm"
          >
            {user.status || "active"}
          </Chip>
          <select
            className="glass rounded-lg px-2 py-1 text-sm outline-none"
            value={user.status || "active"}
            onChange={(e) => handleStatusChange(user.id, e.target.value)}
          >
            <option value="active">Active</option>
            <option value="invited">Invited</option>
            <option value="suspended">Suspended</option>
          </select>
        </div>
      ),
    },
    { key: "risk", label: "Risk", render: (user: any) => renderRisk(user) },
    { key: "school", label: "School" },
    { key: "last_active_at", label: "Last Active", render: (user: any) => formatDate(user.last_active_at) },
    {
      key: "actions",
      label: "Actions",
      render: (user: any) => (
        <Button
          variant="destructive"
          size="sm"
          icon={Trash2}
          onClick={(e) => {
            e.stopPropagation();
            handleDeleteUser(user.id);
          }}
        >
          Delete
        </Button>
      ),
    },
  ];

  const roleFilters = [
    { id: "all", label: "All Users" },
    { id: "student", label: "Students" },
    { id: "teacher", label: "Teachers" },
    { id: "admin", label: "Admins" },
  ];

  return (
    <div>
      <Hero
        title="User Management"
        description="Add, edit, and manage all platform users across roles"
        primaryAction={{
          label: "Add User",
          icon: UserPlus,
          onClick: () => setShowAddModal(true),
        }}
      />

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-4 mb-6">
        <div className="flex-1">
          <PillFilter
            filters={roleFilters}
            activeFilter={filterRole}
            onChange={setFilterRole}
          />
        </div>
        <div className="w-full md:w-80">
          <Input
            type="text"
            placeholder="Search users..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {selectedIds.length > 0 && (
        <div className="glass rounded-2xl p-4 mb-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold">Bulk actions</p>
            <p className="text-xs text-[#9CA3AF]">{selectedIds.length} users selected</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" disabled={bulkLoading} onClick={() => runBulkAction("activate")}>
              Activate
            </Button>
            <Button variant="secondary" size="sm" disabled={bulkLoading} onClick={() => runBulkAction("invite")}>
              Invite
            </Button>
            <Button variant="destructive" size="sm" disabled={bulkLoading} onClick={() => runBulkAction("suspend")}>
              Suspend
            </Button>
            <Button variant="tertiary" size="sm" disabled={bulkLoading} onClick={() => runBulkAction("delete")}>
              Delete
            </Button>
            <div className="flex items-center gap-2">
              <select
                className="glass rounded-lg px-2 py-1 text-sm outline-none"
                value={bulkRole}
                onChange={(e) => setBulkRole(e.target.value)}
              >
                <option value="student">Student</option>
                <option value="teacher">Teacher</option>
                <option value="admin">Admin</option>
              </select>
              <Button variant="primary" size="sm" disabled={bulkLoading} onClick={() => runBulkAction("role")}>
                Change Role
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Users Table */}
      <Table data={filteredUsers} columns={columns} loading={loading} />

      {/* Audit Log */}
      <div className="glass rounded-2xl p-6 mt-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg">Role & Status Audit</h3>
            <p className="text-xs text-[#9CA3AF]">Recent changes across the platform.</p>
          </div>
          <Button variant="tertiary" size="sm" onClick={fetchAuditLogs} disabled={auditLoading}>
            {auditLoading ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
        {auditLogs.length === 0 ? (
          <p className="text-sm text-[#9CA3AF]">No audit events yet.</p>
        ) : (
          <div className="space-y-3">
            {auditLogs.map((entry) => (
              <div key={entry.id} className="flex items-center justify-between p-3 rounded-xl bg-[#E3EBFF]/30">
                <div>
                  <p className="text-sm">
                    <span className="font-medium">{entry.actor_name || "System"}</span>{" "}
                    <span className="text-[#9CA3AF]">{entry.action?.replace(/_/g, " ")}</span>
                  </p>
                  <p className="text-xs text-[#9CA3AF]">{entry.created_at}</p>
                </div>
                <Chip variant="info" size="sm">
                  {entry.target_type}
                </Chip>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add User Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Add New User"
        description="Create a new user account"
        footer={
          <>
            <Button variant="tertiary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleAddUser}>
              Add User
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Full Name *"
            value={newUser.name}
            onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
            placeholder="John Doe"
          />
          <Input
            label="Email *"
            type="email"
            value={newUser.email}
            onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
            placeholder="john@example.com"
          />
          <Input
            label="Password *"
            type="password"
            value={newUser.password}
            onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
            placeholder="••••••••"
          />
          <Select
            label="Role *"
            options={[
              { value: "student", label: "Student" },
              { value: "teacher", label: "Teacher" },
              { value: "admin", label: "Administrator" },
            ]}
            value={newUser.role}
            onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
          />
          <Input
            label="School / Institution"
            value={newUser.school}
            onChange={(e) => setNewUser({ ...newUser, school: e.target.value })}
            placeholder="Stanford University"
          />
          <Input
            label="Country"
            value={newUser.country}
            onChange={(e) => setNewUser({ ...newUser, country: e.target.value })}
            placeholder="United States"
          />
        </div>
      </Modal>
    </div>
  );
}
