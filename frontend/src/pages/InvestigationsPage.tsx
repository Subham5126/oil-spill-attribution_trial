import React, { useState, useEffect, useCallback } from "react";
import { NavPath } from "../components/Sidebar";
import { Investigation } from "../types";
import {
  getInvestigations,
  patchInvestigation,
  deleteInvestigation,
  restoreInvestigation,
  rerunInvestigation,
} from "../services/api";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { useToast } from "../components/ToastNotification";
import {
  Folder,
  Plus,
  Search,
  ArrowRight,
  MapPin,
  Star,
  RotateCcw,
  Trash2,
  FileText,
  Compass,
  CheckCircle2,
  Radio,
  SlidersHorizontal,
  Archive,
} from "lucide-react";

interface InvestigationsPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
  onSelectInvestigation?: (id: string) => void;
}

export function InvestigationsPage({
  onNavigate,
  onOpenDossier,
  onSelectInvestigation,
}: InvestigationsPageProps) {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [starredOnly, setStarredOnly] = useState(false);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [sortBy, setSortBy] = useState<"date_desc" | "date_asc" | "area_desc" | "title">("date_desc");

  // Deletion modal state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [targetInvestigation, setTargetInvestigation] = useState<Investigation | null>(null);
  const [purgeChecked, setPurgeChecked] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const { showToast } = useToast();

  const loadData = useCallback(() => {
    setLoading(true);
    getInvestigations({
      include_deleted: includeDeleted,
    })
      .then((data) => {
        setInvestigations(data);
      })
      .catch((err) => {
        showToast("error", "Error loading investigations: " + err.message);
      })
      .finally(() => setLoading(false));
  }, [includeDeleted, showToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle Star toggle
  const handleToggleStar = async (e: React.MouseEvent, inv: Investigation) => {
    e.stopPropagation();
    try {
      const updated = await patchInvestigation(inv.id, {
        is_starred: !inv.is_starred,
      });
      setInvestigations((prev) =>
        prev.map((item) => (item.id === inv.id ? { ...item, is_starred: updated.is_starred } : item))
      );
      showToast("success", inv.is_starred ? "Removed from starred" : "Investigation starred");
    } catch (err: any) {
      showToast("error", "Failed to update star status: " + err.message);
    }
  };

  // Handle Re-run
  const handleRerun = async (e: React.MouseEvent, inv: Investigation) => {
    e.stopPropagation();
    try {
      setActionLoading(true);
      const newInv = await rerunInvestigation(inv.id);
      showToast("success", `Spawned re-run investigation ${newInv.id}`);
      loadData();
      if (onSelectInvestigation) onSelectInvestigation(newInv.id);
      onNavigate("investigation-detail");
    } catch (err: any) {
      showToast("error", "Re-run failed: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Delete Confirmation
  const openDeleteModal = (e: React.MouseEvent, inv: Investigation) => {
    e.stopPropagation();
    setTargetInvestigation(inv);
    setPurgeChecked(false);
    setDeleteModalOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!targetInvestigation) return;
    try {
      setActionLoading(true);
      await deleteInvestigation(targetInvestigation.id, purgeChecked);
      showToast(
        "success",
        purgeChecked
          ? `Investigation ${targetInvestigation.id} permanently purged.`
          : `Investigation ${targetInvestigation.id} moved to trash.`
      );
      setDeleteModalOpen(false);
      setTargetInvestigation(null);
      loadData();
    } catch (err: any) {
      showToast("error", "Deletion failed: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Restore
  const handleRestore = async (e: React.MouseEvent, inv: Investigation) => {
    e.stopPropagation();
    try {
      setActionLoading(true);
      await restoreInvestigation(inv.id);
      showToast("success", `Investigation ${inv.id} restored successfully.`);
      loadData();
    } catch (err: any) {
      showToast("error", "Restore failed: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Filter and Sort logic
  const filtered = investigations
    .filter((inv) => {
      // Search
      const q = search.toLowerCase();
      const matchQuery =
        inv.title.toLowerCase().includes(q) ||
        inv.id.toLowerCase().includes(q) ||
        inv.region.toLowerCase().includes(q) ||
        (inv.suspect_vessel && inv.suspect_vessel.toLowerCase().includes(q));
      if (!matchQuery) return false;

      // Status filter
      if (statusFilter !== "ALL" && inv.status.toUpperCase() !== statusFilter) return false;

      // Starred only
      if (starredOnly && !inv.is_starred) return false;

      // Deleted filter
      if (!includeDeleted && inv.is_deleted) return false;

      return true;
    })
    .sort((a, b) => {
      if (sortBy === "date_desc") {
        return new Date(b.created_at || "").getTime() - new Date(a.created_at || "").getTime();
      }
      if (sortBy === "date_asc") {
        return new Date(a.created_at || "").getTime() - new Date(b.created_at || "").getTime();
      }
      if (sortBy === "area_desc") {
        return (b.spill_area_km2 || 0) - (a.spill_area_km2 || 0);
      }
      if (sortBy === "title") {
        return a.title.localeCompare(b.title);
      }
      return 0;
    });

  const handleSelect = (inv: Investigation) => {
    if (onSelectInvestigation) {
      onSelectInvestigation(inv.id);
    }
    onNavigate("investigation-detail");
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary uppercase tracking-wider">Forensic Registry</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            Maritime Incident Investigations
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Full registry of satellite radar spill detections, hydrodynamic hindcasts, and AIS candidate attributions.
          </p>
        </div>

        {/* Action Button */}
        <button
          type="button"
          onClick={() => onNavigate("new-investigation")}
          className="flex items-center gap-space-xs px-space-md py-2.5 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
        >
          <Plus className="w-4 h-4" />
          <span>New Incident Investigation</span>
        </button>
      </div>

      {/* Filter, Search and Sorting Control Bar */}
      <div className="flex flex-col gap-3 bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm">
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          {/* Search Input */}
          <div className="flex items-center gap-2 flex-1 max-w-lg bg-surface-container-low px-3 py-2 rounded-lg border border-surface-container">
            <Search className="w-4 h-4 text-secondary" />
            <input
              type="text"
              placeholder="Search by incident ID, vessel, region, or keyword..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-transparent text-xs text-on-surface w-full focus:outline-none font-mono"
            />
          </div>

          {/* Status Filter Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 lg:pb-0">
            {["ALL", "COMPLETED", "ACTIVE", "FAILED"].map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-colors ${
                  statusFilter === status
                    ? "bg-primary text-on-primary shadow-xs"
                    : "bg-surface-container-low text-secondary hover:bg-surface-container"
                }`}
              >
                {status}
              </button>
            ))}
          </div>

          {/* Sorting Dropdown */}
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-3.5 h-3.5 text-secondary" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              aria-label="Sort investigations"
              className="bg-surface-container-low text-xs text-on-surface px-2.5 py-1.5 rounded-lg border border-surface-container focus:outline-none font-mono"
            >
              <option value="date_desc">Newest First</option>
              <option value="date_asc">Oldest First</option>
              <option value="area_desc">Largest Area</option>
              <option value="title">Title (A-Z)</option>
            </select>
          </div>
        </div>

        {/* Second row: Quick toggles */}
        <div className="flex items-center justify-between pt-2 border-t border-surface-container-low text-xs">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-1.5 cursor-pointer text-secondary hover:text-on-surface">
              <input
                type="checkbox"
                checked={starredOnly}
                onChange={(e) => setStarredOnly(e.target.checked)}
                className="accent-primary rounded"
              />
              <span className="flex items-center gap-1">
                <Star className={`w-3.5 h-3.5 ${starredOnly ? "text-amber-500 fill-amber-500" : ""}`} />
                Starred Only
              </span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer text-secondary hover:text-on-surface">
              <input
                type="checkbox"
                checked={includeDeleted}
                onChange={(e) => setIncludeDeleted(e.target.checked)}
                className="accent-primary rounded"
              />
              <span className="flex items-center gap-1">
                <Archive className="w-3.5 h-3.5" />
                Include Trash / Deleted
              </span>
            </label>
          </div>

          <span className="font-data-mono-sm text-xs text-secondary">
            Showing <strong>{filtered.length}</strong> of {investigations.length} Incident Cases
          </span>
        </div>
      </div>

      {/* Investigations Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        {filtered.map((inv) => {
          const isDeleted = inv.is_deleted;
          return (
            <div
              key={inv.id}
              onClick={() => handleSelect(inv)}
              className={`bg-surface-container-lowest rounded-xl p-space-md border transition-all cursor-pointer shadow-sm flex flex-col justify-between group ${
                isDeleted
                  ? "border-dashed border-rose-300 opacity-75 bg-rose-50/10"
                  : "border-surface-container hover:border-primary"
              }`}
            >
              <div>
                {/* Header Row: ID, Star, Status */}
                <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
                  <div className="flex items-center gap-2">
                    <span className="font-data-mono-sm text-xs text-primary font-bold">{inv.id}</span>
                    <button
                      type="button"
                      title={inv.is_starred ? "Unstar incident" : "Star incident"}
                      onClick={(e) => handleToggleStar(e, inv)}
                      className="text-secondary hover:text-amber-500 cursor-pointer transition-colors p-0.5"
                    >
                      <Star
                        className={`w-4 h-4 ${
                          inv.is_starred ? "text-amber-500 fill-amber-500" : "text-secondary/40"
                        }`}
                      />
                    </button>
                    {inv.parent_investigation_id && (
                      <span className="text-[10px] bg-surface-container px-1.5 py-0.5 rounded font-mono text-secondary" title={`Forked from ${inv.parent_investigation_id}`}>
                        re-run
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {isDeleted ? (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                        DELETED
                      </span>
                    ) : (
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${
                          inv.status === "Completed"
                            ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                            : inv.status === "Active"
                            ? "bg-sky-100 text-sky-800 border border-sky-300"
                            : "bg-surface-container text-secondary"
                        }`}
                      >
                        {inv.status === "Completed" && <CheckCircle2 className="w-2.5 h-2.5" />}
                        {inv.status === "Active" && <Radio className="w-2.5 h-2.5 animate-pulse" />}
                        {inv.status}
                      </span>
                    )}
                  </div>
                </div>

                {/* Title and Region */}
                <h3 className="font-headline-sm text-sm text-on-surface font-bold mt-2.5 group-hover:text-primary transition-colors">
                  {inv.title}
                </h3>
                <p className="text-xs text-secondary mt-1 flex items-center gap-1 font-mono">
                  <MapPin className="w-3.5 h-3.5 text-primary" />
                  {inv.region}
                  {inv.created_at && (
                    <span className="text-outline-variant ml-2">
                      • {new Date(inv.created_at).toLocaleDateString()}
                    </span>
                  )}
                </p>

                {/* Measurement & Suspect Stat Pills */}
                <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[11px]">
                  <div className="bg-surface-container-low p-2 rounded-lg">
                    <span className="text-secondary block text-[10px] font-semibold">SPILL AREA:</span>
                    <strong className="text-rose-600">
                      {inv.spill_area_km2 ? `${inv.spill_area_km2.toFixed(3)} km²` : "Pending Analysis"}
                    </strong>
                  </div>
                  <div className="bg-surface-container-low p-2 rounded-lg">
                    <span className="text-secondary block text-[10px] font-semibold">PRIMARY SUSPECT:</span>
                    <strong className="text-on-surface truncate block">
                      {inv.suspect_vessel || "Under Analysis"}
                    </strong>
                  </div>
                </div>
              </div>

              {/* Action Buttons Toolbar */}
              <div className="mt-4 pt-2.5 border-t border-surface-container-low flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    title="View Forensic Report"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onSelectInvestigation) onSelectInvestigation(inv.id);
                      onNavigate("reports");
                    }}
                    className="p-1.5 rounded text-secondary hover:text-primary hover:bg-surface-container cursor-pointer transition-colors"
                  >
                    <FileText className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    title="View GIS Map"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onSelectInvestigation) onSelectInvestigation(inv.id);
                      onNavigate("map-explorer");
                    }}
                    className="p-1.5 rounded text-secondary hover:text-primary hover:bg-surface-container cursor-pointer transition-colors"
                  >
                    <Compass className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    title="Re-run Pipeline Analysis"
                    onClick={(e) => handleRerun(e, inv)}
                    className="p-1.5 rounded text-secondary hover:text-emerald-600 hover:bg-emerald-50 cursor-pointer transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                  {isDeleted ? (
                    <button
                      type="button"
                      title="Restore Investigation"
                      onClick={(e) => handleRestore(e, inv)}
                      className="px-2 py-1 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold hover:bg-emerald-200 cursor-pointer transition-colors"
                    >
                      Restore
                    </button>
                  ) : (
                    <button
                      type="button"
                      title="Delete or Purge Investigation"
                      onClick={(e) => openDeleteModal(e, inv)}
                      className="p-1.5 rounded text-secondary hover:text-rose-600 hover:bg-rose-50 cursor-pointer transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-1 text-primary font-semibold text-xs group-hover:translate-x-0.5 transition-transform">
                  <span>Open Dossier</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </div>
          );
        })}

        {!loading && filtered.length === 0 && (
          <div className="col-span-2 p-12 text-center bg-surface-container-lowest rounded-xl border border-dashed border-surface-container">
            <Folder className="w-12 h-12 mx-auto text-secondary mb-3 opacity-40" />
            <h3 className="font-headline-sm text-sm font-bold text-on-surface">
              No Incident Investigations Found
            </h3>
            <p className="text-xs text-secondary mt-1 max-w-sm mx-auto">
              No oil spill incidents match your current search filters or criteria.
            </p>
            <div className="mt-4 flex items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setStatusFilter("ALL");
                  setStarredOnly(false);
                  setIncludeDeleted(false);
                }}
                className="px-3 py-1.5 rounded-lg bg-surface-container text-xs font-semibold hover:bg-surface-container-high transition-colors"
              >
                Clear Filters
              </button>
              <button
                type="button"
                onClick={() => onNavigate("new-investigation")}
                className="px-4 py-1.5 rounded-lg bg-primary text-on-primary font-bold text-xs hover:bg-primary/90 transition-colors shadow-xs"
              >
                Start New Incident
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Confirmation Modal for Safe Deletion */}
      <ConfirmationModal
        isOpen={deleteModalOpen}
        title="Delete Forensic Investigation"
        message={
          purgeChecked
            ? `You are about to PERMANENTLY PURGE investigation "${targetInvestigation?.title}" (${targetInvestigation?.id}). This will permanently erase the database record, generated GeoJSONs, AIS matrices, and markdown reports from disk. This action CANNOT be undone.`
            : `Move investigation "${targetInvestigation?.title}" (${targetInvestigation?.id}) to trash? It can be restored at any time.`
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
        <div className="mt-4 pt-3 border-t border-surface-container-low flex flex-col gap-2">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={purgeChecked}
              onChange={(e) => setPurgeChecked(e.target.checked)}
              className="mt-0.5 accent-rose-600 rounded"
            />
            <div className="flex flex-col text-xs">
              <span className="font-bold text-rose-600">
                Permanent Purge (Remove Incident Output Files)
              </span>
              <span className="text-secondary text-[11px]">
                Deletes database entry and incident-specific output files (`real_{targetInvestigation?.id}_*`). Shared Sentinel-1 TIFFs and model weights are strictly preserved.
              </span>
            </div>
          </label>
        </div>
      </ConfirmationModal>
    </div>
  );
}


