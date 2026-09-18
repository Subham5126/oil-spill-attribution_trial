import React, { useEffect, useState } from "react";
import {
  Shield,
  Users,
  UserPlus,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  Lock,
  Unlock,
  RefreshCw,
} from "lucide-react";

const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || "";

interface AdminUser {
  id: number;
  email: string;
  employee_id: string | null;
  full_name: string;
  role: string;
  department: string | null;
  is_active: boolean;
  failed_login_attempts: number;
  locked_until: string | null;
  last_login_at: string | null;
  last_login_ip: string | null;
  created_at: string;
}

const ROLE_COLORS: Record<string, string> = {
  ADMIN: "text-red-400 bg-red-900/30 border-red-700/40",
  ANALYST: "text-cyan-400 bg-cyan-900/30 border-cyan-700/40",
  OPERATOR: "text-amber-400 bg-amber-900/30 border-amber-700/40",
  VIEWER: "text-slate-400 bg-slate-800/50 border-slate-700/40",
};

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${API_BASE_URL}/api/admin${path}`, {
    ...opts,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...opts?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

interface AdminUsersPageProps {
  onNavigate: (path: any) => void;
}

export function AdminUsersPage({ onNavigate }: AdminUsersPageProps) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  // Create user form state
  const [newEmail, setNewEmail] = useState("");
  const [newEmployeeId, setNewEmployeeId] = useState("");
  const [newFullName, setNewFullName] = useState("");
  const [newRole, setNewRole] = useState("VIEWER");
  const [newDepartment, setNewDepartment] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiFetch("/users?page=1&page_size=100");
      setUsers(data.items);
      setTotal(data.total);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);
    setCreateLoading(true);
    try {
      await apiFetch("/users", {
        method: "POST",
        body: JSON.stringify({
          email: newEmail.trim().toLowerCase(),
          employee_id: newEmployeeId.trim() || undefined,
          full_name: newFullName.trim(),
          role: newRole,
          department: newDepartment.trim() || undefined,
          password: newPassword,
        }),
      });
      setCreateSuccess(`User ${newEmail} created.`);
      setShowCreateForm(false);
      setNewEmail(""); setNewEmployeeId(""); setNewFullName("");
      setNewRole("VIEWER"); setNewDepartment(""); setNewPassword("");
      await loadUsers();
      setTimeout(() => setCreateSuccess(null), 4000);
    } catch (e: any) {
      setCreateError(e.message);
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeactivate = async (userId: number, email: string) => {
    if (!confirm(`Deactivate user ${email}?`)) return;
    try {
      await apiFetch(`/users/${userId}`, { method: "DELETE" });
      await loadUsers();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleReactivate = async (userId: number) => {
    try {
      await apiFetch(`/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: true }),
      });
      await loadUsers();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleRoleChange = async (userId: number, role: string) => {
    try {
      await apiFetch(`/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
      await loadUsers();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-red-900/30 border border-red-700/40 flex items-center justify-center">
            <Shield className="w-5 h-5 text-red-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">User Management</h1>
            <p className="text-xs text-slate-500 font-mono">{total} registered user{total !== 1 ? "s" : ""}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadUsers}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 text-xs font-mono transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            Refresh
          </button>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-700/30 border border-cyan-600/40 text-cyan-300 hover:bg-cyan-700/50 text-xs font-mono transition-colors"
          >
            <UserPlus className="w-3.5 h-3.5" />
            Add User
          </button>
        </div>
      </div>

      {/* Success banner */}
      {createSuccess && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-green-900/30 border border-green-700/40 text-green-300 text-xs font-mono">
          <CheckCircle2 className="w-4 h-4" />
          {createSuccess}
        </div>
      )}

      {/* Create user form */}
      {showCreateForm && (
        <div className="bg-slate-900/80 border border-slate-700/60 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-cyan-400" />
            New User
          </h2>
          {createError && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-900/30 border border-red-700/40 text-red-300 text-xs font-mono">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              {createError}
            </div>
          )}
          <form onSubmit={handleCreateUser} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { label: "Official Email *", value: newEmail, set: setNewEmail, type: "email", required: true },
              { label: "Full Name *", value: newFullName, set: setNewFullName, type: "text", required: true },
              { label: "Employee ID", value: newEmployeeId, set: setNewEmployeeId, type: "text", required: false },
              { label: "Department", value: newDepartment, set: setNewDepartment, type: "text", required: false },
            ].map(({ label, value, set, type, required }) => (
              <div key={label}>
                <label className="block text-[10px] text-slate-500 font-mono mb-1 uppercase tracking-wider">{label}</label>
                <input
                  type={type}
                  required={required}
                  value={value}
                  onChange={(e) => set(e.target.value)}
                  className="w-full px-2.5 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                />
              </div>
            ))}
            <div>
              <label className="block text-[10px] text-slate-500 font-mono mb-1 uppercase tracking-wider">Role *</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full px-2.5 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
              >
                {["ADMIN", "ANALYST", "OPERATOR", "VIEWER"].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-slate-500 font-mono mb-1 uppercase tracking-wider">Password *</label>
              <div className="relative">
                <input
                  type={showNewPassword ? "text" : "password"}
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min 12 chars, mixed case, digit, symbol"
                  className="w-full px-2.5 py-2 pr-9 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                />
                <button type="button" onClick={() => setShowNewPassword((v) => !v)} tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500">
                  {showNewPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
            <div className="sm:col-span-2 flex gap-2 justify-end pt-1">
              <button type="button" onClick={() => setShowCreateForm(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 text-xs font-mono hover:text-slate-200">
                Cancel
              </button>
              <button type="submit" disabled={createLoading}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-mono disabled:opacity-50">
                {createLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UserPlus className="w-3.5 h-3.5" />}
                Create User
              </button>
            </div>
          </form>
        </div>
      )}

      {/* User list */}
      {isLoading ? (
        <div className="text-slate-500 font-mono text-sm flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading users…
        </div>
      ) : error ? (
        <div className="text-red-400 font-mono text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      ) : (
        <div className="space-y-2">
          {users.map((u) => (
            <div key={u.id}
              className={`flex items-center justify-between px-4 py-3 rounded-xl border transition-colors ${
                u.is_active
                  ? "bg-slate-900/70 border-slate-700/50"
                  : "bg-slate-900/30 border-slate-800/40 opacity-60"
              }`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0">
                  <Users className="w-4 h-4 text-slate-400" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-slate-200 truncate">{u.full_name}</span>
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${ROLE_COLORS[u.role] ?? ROLE_COLORS.VIEWER}`}>
                      {u.role}
                    </span>
                    {!u.is_active && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border text-slate-500 border-slate-700 bg-slate-900">
                        INACTIVE
                      </span>
                    )}
                    {u.locked_until && new Date(u.locked_until) > new Date() && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border text-amber-400 border-amber-700 bg-amber-900/30">
                        LOCKED
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className="text-xs text-slate-500 font-mono truncate">{u.email}</span>
                    {u.employee_id && <span className="text-xs text-slate-600 font-mono">#{u.employee_id}</span>}
                    {u.department && <span className="text-xs text-slate-600 font-mono">{u.department}</span>}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0 ml-3">
                {/* Role selector */}
                <select
                  value={u.role}
                  onChange={(e) => handleRoleChange(u.id, e.target.value)}
                  className="text-xs font-mono bg-slate-950 border border-slate-700 text-slate-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-cyan-500/40"
                >
                  {["ADMIN", "ANALYST", "OPERATOR", "VIEWER"].map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                {/* Activate / Deactivate */}
                {u.is_active ? (
                  <button
                    onClick={() => handleDeactivate(u.id, u.email)}
                    title="Deactivate user"
                    className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors"
                  >
                    <XCircle className="w-4 h-4" />
                  </button>
                ) : (
                  <button
                    onClick={() => handleReactivate(u.id)}
                    title="Reactivate user"
                    className="p-1.5 rounded-lg text-slate-500 hover:text-green-400 hover:bg-green-900/20 transition-colors"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
