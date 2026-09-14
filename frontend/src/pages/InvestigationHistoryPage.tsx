import React, { useState, useEffect, useCallback } from "react";
import { NavPath } from "../components/Sidebar";
import { Investigation } from "../types";
import { getInvestigationHistory, rerunInvestigation, deleteInvestigation, restoreInvestigation } from "../services/api";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { useToast } from "../components/ToastNotification";
import {
  History,
  Search,
  Download,
  Calendar,
  RotateCcw,
  Trash2,
  FileText,
  Compass,
  ArrowRight,
  MapPin,
  ChevronLeft,
  ChevronRight,
  Archive,
  RefreshCw,
} from "lucide-react";

interface InvestigationHistoryPageProps {
  onNavigate: (path: NavPath) => void;
  onSelectInvestigation?: (id: string) => void;
}

export function InvestigationHistoryPage({ onNavigate, onSelectInvestigation }: InvestigationHistoryPageProps) {
  const [historyItems, setHistoryItems] = useState<Investigation[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [includeDeleted, setIncludeDeleted] = useState(true);
  const [page, setPage] = useState(1);
  const limit = 10;

  // Deletion modal
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [targetInvestigation, setTargetInvestigation] = useState<Investigation | null>(null);
  const [purgeChecked, setPurgeChecked] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const { showToast } = useToast();

  const loadHistory = useCallback(() => {
    setLoading(true);
    getInvestigationHistory({
      search: search || undefined,
      status: statusFilter !== "ALL" ? statusFilter : undefined,
      include_deleted: includeDeleted,
      limit: 200,
    })
      .then((items) => {
        setTotalCount(items.length);
        const startIndex = (page - 1) * limit;
        setHistoryItems(items.slice(startIndex, startIndex + limit));
      })
      .catch((err) => {
        showToast("error", "Failed to load history: " + err.message);
      })
      .finally(() => setLoading(false));
  }, [page, limit, search, statusFilter, includeDeleted, showToast]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleRerun = async (inv: Investigation) => {
    try {
      setActionLoading(true);
      const newInv = await rerunInvestigation(inv.id);
      showToast("success", `Spawned re-run investigation ${newInv.id}`);
      loadHistory();
      if (onSelectInvestigation) onSelectInvestigation(newInv.id);
      onNavigate("dashboard");
    } catch (err: any) {
      showToast("error", "Re-run failed: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!targetInvestigation) return;
    try {
      setActionLoading(true);
      await deleteInvestigation(targetInvestigation.id, purgeChecked);
      showToast("success", purgeChecked ? "Investigation permanently purged." : "Investigation moved to trash.");
      setDeleteModalOpen(false);
      setTargetInvestigation(null);
      loadHistory();
    } catch (err: any) {
      showToast("error", "Deletion failed: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRestore = async (inv: Investigation) => {
    try {
      setActionLoading(true);
      await restoreInvestigation(inv.id);
      showToast("success", `Investigation ${inv.id} restored.`);
      loadHistory();
    } catch (err: any) {
      showToast("error", "Restore failed: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const exportAuditLogJson = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(historyItems, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `OILTRACE_Audit_History_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    showToast("success", "Audit log exported as JSON.");
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / limit));

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary uppercase tracking-wider">Compliance &amp; Audit Log</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold flex items-center gap-2">
            <History className="w-6 h-6 text-primary" />
            Investigation History
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Chronological audit log of all satellite detection cases, execution states, modifications, and forked re-runs.
          </p>
        </div>

        {/* Export Button */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadHistory}
            className="flex items-center gap-1 px-3 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
          <button
            type="button"
            onClick={exportAuditLogJson}
            className="flex items-center gap-1 px-3 py-2 rounded-lg bg-surface-container-lowest border border-surface-container text-on-surface hover:bg-surface-container-low transition-colors text-xs font-semibold shadow-xs"
          >
            <Download className="w-3.5 h-3.5 text-primary" />
            <span>Export Audit Log (JSON)</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm">
        <div className="flex items-center gap-2 flex-1 max-w-md bg-surface-container-low px-3 py-2 rounded-lg border border-surface-container">
          <Search className="w-4 h-4 text-secondary" />
          <input
            type="text"
            placeholder="Search by ID, region, suspect vessel..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="bg-transparent text-xs text-on-surface w-full focus:outline-none font-mono"
          />
        </div>

        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            aria-label="Filter history by status"
            className="bg-surface-container-low text-xs text-on-surface px-2.5 py-2 rounded-lg border border-surface-container focus:outline-none font-mono"
          >
            <option value="ALL">All Statuses</option>
            <option value="Completed">Completed</option>
            <option value="Active">Active</option>
            <option value="Failed">Failed</option>
          </select>

          <label className="flex items-center gap-1.5 cursor-pointer text-xs text-secondary hover:text-on-surface whitespace-nowrap">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => {
                setIncludeDeleted(e.target.checked);
                setPage(1);
              }}
              className="accent-primary rounded"
            />
            <span>Include Deleted</span>
          </label>
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="bg-surface-container-lowest rounded-xl border border-surface-container shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-container-low border-b border-surface-container text-secondary font-mono uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3">Incident ID</th>
                <th className="px-4 py-3">Title &amp; Region</th>
                <th className="px-4 py-3">Created / Updated</th>
                <th className="px-4 py-3">Spill Area</th>
                <th className="px-4 py-3">Primary Suspect</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-low">
              {historyItems.map((inv) => {
                const isDeleted = inv.is_deleted;
                return (
                  <tr
                    key={inv.id}
                    className={`hover:bg-surface-container-low/50 transition-colors ${
                      isDeleted ? "bg-rose-50/10 text-outline-variant" : ""
                    }`}
                  >
                    {/* ID */}
                    <td className="px-4 py-3.5 font-mono font-bold text-primary whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <span>{inv.id}</span>
                        {inv.parent_investigation_id && (
                          <span
                            className="px-1.5 py-0.5 rounded bg-surface-container text-[9px] text-secondary"
                            title={`Forked from ${inv.parent_investigation_id}`}
                          >
                            fork
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Title & Region */}
                    <td className="px-4 py-3.5 max-w-xs">
                      <div className="font-semibold text-on-surface truncate">{inv.title}</div>
                      <div className="text-[11px] text-secondary flex items-center gap-1 mt-0.5 font-mono">
                        <MapPin className="w-3 h-3 text-primary" />
                        <span>{inv.region}</span>
                      </div>
                    </td>

                    {/* Timestamps */}
                    <td className="px-4 py-3.5 font-mono text-[11px] text-secondary whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        <span>{inv.created_at ? new Date(inv.created_at).toLocaleString() : "N/A"}</span>
                      </div>
                    </td>

                    {/* Spill Area */}
                    <td className="px-4 py-3.5 font-mono text-rose-600 font-bold whitespace-nowrap">
                      {inv.spill_area_km2 ? `${inv.spill_area_km2.toFixed(3)} km²` : "—"}
                    </td>

                    {/* Suspect Vessel */}
                    <td className="px-4 py-3.5 font-mono text-on-surface max-w-xs truncate">
                      {inv.suspect_vessel || <span className="text-secondary">—</span>}
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      {isDeleted ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">
                          DELETED
                        </span>
                      ) : (
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            inv.status === "Completed"
                              ? "bg-emerald-100 text-emerald-800"
                              : inv.status === "Active"
                              ? "bg-sky-100 text-sky-800"
                              : "bg-surface-container text-secondary"
                          }`}
                        >
                          {inv.status}
                        </span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3.5 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          title="Open Case"
                          onClick={() => {
                            if (onSelectInvestigation) onSelectInvestigation(inv.id);
                            onNavigate("dashboard");
                          }}
                          className="p-1.5 rounded text-secondary hover:text-primary hover:bg-surface-container"
                        >
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          title="View Report"
                          onClick={() => {
                            if (onSelectInvestigation) onSelectInvestigation(inv.id);
                            onNavigate("reports");
                          }}
                          className="p-1.5 rounded text-secondary hover:text-primary hover:bg-surface-container"
                        >
                          <FileText className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          title="Re-run Pipeline"
                          onClick={() => handleRerun(inv)}
                          className="p-1.5 rounded text-secondary hover:text-emerald-600 hover:bg-emerald-50"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                        {isDeleted ? (
                          <button
                            type="button"
                            onClick={() => handleRestore(inv)}
                            className="px-2 py-1 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold hover:bg-emerald-200"
                          >
                            Restore
                          </button>
                        ) : (
                          <button
                            type="button"
                            title="Delete"
                            onClick={() => {
                              setTargetInvestigation(inv);
                              setPurgeChecked(false);
                              setDeleteModalOpen(true);
                            }}
                            className="p-1.5 rounded text-secondary hover:text-rose-600 hover:bg-rose-50"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}

              {!loading && historyItems.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-secondary">
                    No historical investigation records match the selected criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div className="flex items-center justify-between px-4 py-3 bg-surface-container-low border-t border-surface-container text-xs text-secondary">
          <span>
            Page <strong>{page}</strong> of <strong>{totalPages}</strong> ({totalCount} total entries)
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="p-1.5 rounded bg-surface-container border border-surface-container disabled:opacity-40 hover:bg-surface-container-high transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="p-1.5 rounded bg-surface-container border border-surface-container disabled:opacity-40 hover:bg-surface-container-high transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Safe Deletion Modal */}
      <ConfirmationModal
        isOpen={deleteModalOpen}
        title="Delete Forensic Record"
        message={
          purgeChecked
            ? `Are you sure you want to PERMANENTLY PURGE "${targetInvestigation?.title}" (${targetInvestigation?.id})? This will permanently delete database records and generated incident files.`
            : `Move "${targetInvestigation?.title}" (${targetInvestigation?.id}) to trash?`
        }
        confirmLabel={purgeChecked ? "Permanently Purge" : "Move to Trash"}
        cancelLabel="Cancel"
        isDestructive={true}
        loading={actionLoading}
        onConfirm={handleConfirmDelete}
        onCancel={() => {
          setDeleteModalOpen(false);
          setTargetInvestigation(null);
        }}
      >
        <div className="mt-3 pt-3 border-t border-surface-container-low">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={purgeChecked}
              onChange={(e) => setPurgeChecked(e.target.checked)}
              className="mt-0.5 accent-rose-600 rounded"
            />
            <span className="text-xs text-rose-600 font-semibold">
              Permanent Purge (Erase incident files; strictly preserves shared satellite imagery &amp; models)
            </span>
          </label>
        </div>
      </ConfirmationModal>
    </div>
  );
}
