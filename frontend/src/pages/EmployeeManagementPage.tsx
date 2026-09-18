import React, { useEffect, useState } from "react";
import {
  ShieldCheck,
  UserPlus,
  Edit2,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  RefreshCw,
  X,
  Users,
  Send,
  KeyRound,
  Mail,
} from "lucide-react";
import {
  EmployeeItem,
  listEmployees,
  createEmployee,
  updateEmployee,
  activateEmployee,
  deactivateEmployee,
  resendInvitation,
  triggerPasswordReset,
} from "../services/api";

const ROLE_BADGES: Record<string, string> = {
  TECH_ADMIN: "text-purple-400 bg-purple-950/40 border-purple-700/50",
  ADMIN: "text-red-400 bg-red-950/40 border-red-700/50",
  ANALYST: "text-cyan-400 bg-cyan-950/40 border-cyan-700/50",
  OPERATOR: "text-amber-400 bg-amber-950/40 border-amber-700/50",
  VIEWER: "text-slate-400 bg-slate-900/60 border-slate-700/50",
};

interface Props {
  onNavigate: (path: any) => void;
}

export function EmployeeManagementPage({ onNavigate }: Props) {
  const [employees, setEmployees] = useState<EmployeeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createdSummary, setCreatedSummary] = useState<EmployeeItem | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSubmitting, setCreateSubmitting] = useState(false);

  // Create form fields (NO passwords)
  const [empId, setEmpId] = useState("");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [department, setDepartment] = useState("");
  const [role, setRole] = useState<"ADMIN" | "ANALYST" | "OPERATOR" | "VIEWER">("ANALYST");

  // Edit modal
  const [editingEmp, setEditingEmp] = useState<EmployeeItem | null>(null);
  const [editName, setEditName] = useState("");
  const [editDept, setEditDept] = useState("");
  const [editRole, setEditRole] = useState<any>("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Action status banner & reset confirm modal
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [resendingId, setResendingId] = useState<number | null>(null);
  const [resetConfirmEmp, setResetConfirmEmp] = useState<EmployeeItem | null>(null);
  const [resetSending, setResetSending] = useState(false);

  const fetchEmployees = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await listEmployees(1, 100);
      setEmployees(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err.message || "Failed to load employees");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchEmployees();
  }, []);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);
    setCreateSubmitting(true);
    try {
      const created = await createEmployee({
        employee_id: empId.trim(),
        official_email: email.trim().toLowerCase(),
        full_name: fullName.trim(),
        department: department.trim() || undefined,
        role,
      });
      setCreatedSummary(created);
      setShowCreateModal(false);
      // Reset form
      setEmpId("");
      setEmail("");
      setFullName("");
      setDepartment("");
      setRole("ANALYST");
      await fetchEmployees();
    } catch (err: any) {
      setCreateError(err.message || "Failed to provision employee.");
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingEmp) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      await updateEmployee(editingEmp.id, {
        full_name: editName.trim(),
        department: editDept.trim() || undefined,
        role: editRole,
      });
      setEditingEmp(null);
      await fetchEmployees();
      setActionMessage({ type: "success", text: `Updated employee ${editingEmp.employee_id} details successfully.` });
    } catch (err: any) {
      setEditError(err.message || "Failed to update employee.");
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleToggleActive = async (emp: EmployeeItem) => {
    const isActivating = !emp.is_active || emp.account_status === "DEACTIVATED";
    const actionName = isActivating ? "activate" : "deactivate";
    if (!confirm(`Are you sure you want to ${actionName} employee ${emp.employee_id} (${emp.full_name})?`)) {
      return;
    }
    try {
      if (isActivating) {
        await activateEmployee(emp.id);
        setActionMessage({ type: "success", text: `Employee ${emp.employee_id} activated successfully.` });
      } else {
        await deactivateEmployee(emp.id);
        setActionMessage({ type: "success", text: `Employee ${emp.employee_id} deactivated successfully.` });
      }
      await fetchEmployees();
    } catch (err: any) {
      setActionMessage({ type: "error", text: `Error: ${err.message}` });
    }
  };

  const handleResendInvitation = async (emp: EmployeeItem) => {
    setResendingId(emp.id);
    setActionMessage(null);
    try {
      const res = await resendInvitation(emp.id);
      setActionMessage({
        type: "success",
        text: res.detail || `Activation invitation email resent to ${emp.official_email}.`,
      });
      await fetchEmployees();
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err.message || `Failed to resend invitation to ${emp.official_email}.`,
      });
    } finally {
      setResendingId(null);
    }
  };

  const handleConfirmResetPassword = async () => {
    if (!resetConfirmEmp) return;
    setResetSending(true);
    try {
      const res = await triggerPasswordReset(resetConfirmEmp.id);
      setActionMessage({
        type: "success",
        text: res.detail || `Password reset link sent to ${resetConfirmEmp.official_email}.`,
      });
      setResetConfirmEmp(null);
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err.message || `Failed to send password reset email to ${resetConfirmEmp.official_email}.`,
      });
    } finally {
      setResetSending(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 tracking-wider uppercase mb-1">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            <span>TECH ADMIN — GOVERNANCE</span>
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">Employee Account Provisioning</h1>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Organization-governed employee directory &amp; invitation management
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={fetchEmployees}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 hover:text-white hover:border-slate-600 text-xs font-mono transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={() => {
              setShowCreateModal(true);
              setCreatedSummary(null);
              setCreateError(null);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold font-mono tracking-wider transition-colors shadow-lg shadow-cyan-950/50"
          >
            <UserPlus className="w-4 h-4" />
            <span>+ CREATE EMPLOYEE</span>
          </button>
        </div>
      </div>

      {/* Action status message toast/banner */}
      {actionMessage && (
        <div
          className={`rounded-xl p-4 flex items-start justify-between gap-3 text-xs font-mono border ${
            actionMessage.type === "success"
              ? "bg-emerald-950/40 border-emerald-700/60 text-emerald-200"
              : "bg-red-950/40 border-red-800/60 text-red-200"
          }`}
        >
          <div className="flex items-start gap-2.5">
            {actionMessage.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            )}
            <span>{actionMessage.text}</span>
          </div>
          <button
            onClick={() => setActionMessage(null)}
            className="text-slate-400 hover:text-white p-0.5"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Success banner after employee creation */}
      {createdSummary && (
        <div className="bg-emerald-950/40 border border-emerald-700/60 rounded-xl p-4 flex items-start justify-between gap-3 text-emerald-200">
          <div className="flex items-start gap-3">
            <Mail className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div className="space-y-1 text-xs font-mono">
              <p className="font-bold text-emerald-300 text-sm">
                Employee account created. An activation invitation link has been sent to {createdSummary.official_email}.
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-1 pt-1 text-slate-300">
                <div>
                  <span className="text-slate-500">Employee ID:</span>{" "}
                  <span className="font-bold text-white">{createdSummary.employee_id}</span>
                </div>
                <div>
                  <span className="text-slate-500">Official Email:</span>{" "}
                  <span className="text-white">{createdSummary.official_email}</span>
                </div>
                <div>
                  <span className="text-slate-500">Role:</span>{" "}
                  <span className="text-cyan-300 font-bold">{createdSummary.role}</span>
                </div>
                <div>
                  <span className="text-slate-500">Status:</span>{" "}
                  <span className="text-amber-400 font-bold">PENDING ACTIVATION</span>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 pt-1">
                The employee will set their own password securely through the single-use email invitation link.
              </p>
            </div>
          </div>
          <button
            onClick={() => setCreatedSummary(null)}
            className="text-emerald-400 hover:text-white p-1 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Main Table */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="px-5 py-3.5 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-slate-400" />
            <h2 className="text-xs font-mono font-bold tracking-wider uppercase text-slate-200">
              Personnel Directory ({total} registered)
            </h2>
          </div>
          <span className="text-[11px] font-mono text-slate-500">
            Source: PostgreSQL / auth_users
          </span>
        </div>

        {isLoading && employees.length === 0 ? (
          <div className="py-16 text-center text-slate-500 font-mono text-xs flex flex-col items-center justify-center gap-2">
            <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
            <span>Loading registered personnel...</span>
          </div>
        ) : error ? (
          <div className="py-12 text-center text-red-400 font-mono text-xs flex flex-col items-center justify-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-400" />
            <span>{error}</span>
          </div>
        ) : employees.length === 0 ? (
          <div className="py-16 text-center text-slate-500 font-mono text-xs">
            No employees found. Use [ + CREATE EMPLOYEE ] to provision the first account.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Employee ID</th>
                  <th className="py-3 px-4">Official Email</th>
                  <th className="py-3 px-4">Name</th>
                  <th className="py-3 px-4">Department</th>
                  <th className="py-3 px-4">Role</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Last Login</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {employees.map((emp) => {
                  const isPending = emp.account_status === "PENDING_ACTIVATION";
                  const isDeactivated = emp.account_status === "DEACTIVATED" || !emp.is_active;
                  const isActive = emp.account_status === "ACTIVE" && emp.is_active;

                  return (
                    <tr
                      key={emp.id}
                      className={`hover:bg-slate-800/30 transition-colors ${
                        isDeactivated ? "opacity-50 bg-slate-950/30" : ""
                      }`}
                    >
                      <td className="py-3 px-4 font-bold text-white whitespace-nowrap">
                        {emp.employee_id}
                      </td>
                      <td className="py-3 px-4 text-slate-200 whitespace-nowrap">
                        {emp.official_email}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        {emp.full_name}
                      </td>
                      <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                        {emp.department || "—"}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span
                          className={`inline-block px-2 py-0.5 rounded border text-[10px] font-bold ${
                            ROLE_BADGES[emp.role] || ROLE_BADGES.VIEWER
                          }`}
                        >
                          {emp.role}
                        </span>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        {isPending ? (
                          <span className="inline-flex items-center gap-1.5 text-amber-400 font-bold text-[11px] bg-amber-950/30 border border-amber-800/40 px-2 py-0.5 rounded">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                            PENDING ACTIVATION
                          </span>
                        ) : isActive ? (
                          <span className="inline-flex items-center gap-1.5 text-emerald-400 font-bold text-[11px] bg-emerald-950/30 border border-emerald-800/40 px-2 py-0.5 rounded">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                            ACTIVE
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-rose-400 font-bold text-[11px] bg-rose-950/30 border border-rose-800/40 px-2 py-0.5 rounded">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                            DEACTIVATED
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-500 whitespace-nowrap text-[11px]">
                        {emp.last_login_at
                          ? new Date(emp.last_login_at).toLocaleString([], {
                              dateStyle: "short",
                              timeStyle: "short",
                            })
                          : isPending
                          ? "Pending Setup"
                          : "Never"}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        <div className="inline-flex items-center gap-1.5">
                          {isPending && (
                            <button
                              onClick={() => handleResendInvitation(emp)}
                              disabled={resendingId === emp.id}
                              title="Resend Activation Invitation Email"
                              className="px-2.5 py-1 rounded bg-cyan-950/40 border border-cyan-800/40 text-cyan-300 hover:bg-cyan-900/60 text-[11px] font-medium transition-colors flex items-center gap-1"
                            >
                              {resendingId === emp.id ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Send className="w-3 h-3" />
                              )}
                              <span>Resend Invitation</span>
                            </button>
                          )}

                          {!isDeactivated && (
                            <button
                              onClick={() => {
                                setEditingEmp(emp);
                                setEditName(emp.full_name);
                                setEditDept(emp.department || "");
                                setEditRole(emp.role);
                                setEditError(null);
                              }}
                              title="Edit Details"
                              className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] transition-colors"
                            >
                              Edit
                            </button>
                          )}

                          {isActive && (
                            <button
                              onClick={() => setResetConfirmEmp(emp)}
                              title="Send Password Reset Email Link"
                              className="px-2.5 py-1 rounded bg-amber-950/40 border border-amber-800/40 text-amber-300 hover:bg-amber-900/60 text-[11px] font-medium transition-colors flex items-center gap-1"
                            >
                              <KeyRound className="w-3 h-3" />
                              <span>Reset Password</span>
                            </button>
                          )}

                          {isDeactivated ? (
                            <button
                              onClick={() => handleToggleActive(emp)}
                              title="Activate Account"
                              className="px-2.5 py-1 rounded bg-emerald-950/40 border border-emerald-800/40 text-emerald-300 hover:bg-emerald-900/60 text-[11px] transition-colors"
                            >
                              Activate
                            </button>
                          ) : (
                            <button
                              onClick={() => handleToggleActive(emp)}
                              title="Deactivate Account"
                              className="px-2 py-1 rounded bg-rose-950/40 border border-rose-800/40 text-rose-300 hover:bg-rose-900/60 text-[11px] transition-colors"
                            >
                              Deactivate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* CREATE EMPLOYEE MODAL (NO PASSWORDS) */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl space-y-4">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-cyan-400" />
                <h3 className="font-bold text-white text-base">CREATE EMPLOYEE</h3>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {createError && (
              <div className="mx-6 p-3 rounded-lg bg-red-950/50 border border-red-800/60 text-red-300 text-xs font-mono flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{createError}</span>
              </div>
            )}

            <div className="mx-6 p-3 rounded-lg bg-cyan-950/30 border border-cyan-800/40 text-cyan-300 text-xs font-mono flex items-start gap-2">
              <Mail className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                TECH_ADMIN does not set employee passwords. An account invitation email will be sent with a secure link for the employee to establish their credentials.
              </span>
            </div>

            <form onSubmit={handleCreateSubmit} className="px-6 pb-6 space-y-3.5 text-xs font-mono">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Employee ID *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. EMP-002"
                    value={empId}
                    onChange={(e) => setEmpId(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Official Email *</label>
                  <input
                    type="email"
                    required
                    placeholder="e.g. analyst@oiltrace.gov"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Full Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Capt. Rajesh Sharma"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Department</label>
                  <input
                    type="text"
                    placeholder="e.g. Marine Surveillance"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Role *</label>
                  <select
                    value={role}
                    onChange={(e: any) => setRole(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  >
                    <option value="ADMIN">ADMIN</option>
                    <option value="ANALYST">ANALYST</option>
                    <option value="OPERATOR">OPERATOR</option>
                    <option value="VIEWER">VIEWER</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-lg border border-slate-700 text-slate-400 hover:text-white cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {createSubmitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Provisioning...</span>
                    </>
                  ) : (
                    <span>CREATE EMPLOYEE</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {editingEmp && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl space-y-4">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-white text-sm">
                Edit Employee: {editingEmp.employee_id}
              </h3>
              <button onClick={() => setEditingEmp(null)} className="text-slate-400 hover:text-white cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>

            {editError && (
              <div className="mx-6 p-3 rounded-lg bg-red-950/50 border border-red-800/60 text-red-300 text-xs font-mono">
                {editError}
              </div>
            )}

            <form onSubmit={handleEditSubmit} className="px-6 pb-6 space-y-3.5 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Department</label>
                <input
                  type="text"
                  value={editDept}
                  onChange={(e) => setEditDept(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Assigned Role</label>
                <select
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value)}
                  disabled={editingEmp.role === "TECH_ADMIN"}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200"
                >
                  <option value="ADMIN">ADMIN</option>
                  <option value="ANALYST">ANALYST</option>
                  <option value="OPERATOR">OPERATOR</option>
                  <option value="VIEWER">VIEWER</option>
                  {editingEmp.role === "TECH_ADMIN" && <option value="TECH_ADMIN">TECH_ADMIN</option>}
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditingEmp(null)}
                  className="px-4 py-2 rounded-lg border border-slate-700 text-slate-400 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting}
                  className="px-5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer"
                >
                  {editSubmitting ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CONFIRM PASSWORD RESET MODAL */}
      {resetConfirmEmp && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl space-y-4">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-400">
                <KeyRound className="w-5 h-5" />
                <h3 className="font-bold text-white text-sm">
                  Send Password Reset Link
                </h3>
              </div>
              <button
                onClick={() => setResetConfirmEmp(null)}
                className="text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-6 space-y-3 text-xs font-mono text-slate-300">
              <p>
                Are you sure you want to send a secure password reset link to:
              </p>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
                <div className="text-white font-bold">{resetConfirmEmp.full_name}</div>
                <div className="text-cyan-400">{resetConfirmEmp.official_email}</div>
                <div className="text-slate-500 text-[11px]">ID: {resetConfirmEmp.employee_id}</div>
              </div>
              <p className="text-slate-400 text-[11px]">
                The employee will receive a one-time link valid for 24 hours to set their new password.
                You will not see or handle their password.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 px-6 pb-6 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setResetConfirmEmp(null)}
                className="px-4 py-2 rounded-lg border border-slate-700 text-slate-400 hover:text-white cursor-pointer text-xs font-mono"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={resetSending}
                onClick={handleConfirmResetPassword}
                className="flex items-center gap-2 px-5 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs font-mono transition-colors cursor-pointer"
              >
                {resetSending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Sending Link...</span>
                  </>
                ) : (
                  <>
                    <Mail className="w-4 h-4" />
                    <span>Send Reset Email</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
