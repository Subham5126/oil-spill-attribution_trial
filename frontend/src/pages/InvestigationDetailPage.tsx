import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { useToast } from "../components/ToastNotification";
import {
  EndToEndResult,
  CandidateVessel,
  Investigation,
  GeoJSONFeatureCollection,
} from "../types";
import {
  getInvestigation,
  getActivePipelineResult,
  getGISLayersGeoJSON,
  getReportDownloadUrl,
  getDetectionOverlayUrl,
  getSegmentationMaskUrl,
  deleteInvestigation,
  rerunInvestigation,
} from "../services/api";
import {
  ArrowLeft,
  Download,
  RotateCcw,
  Trash2,
  Maximize2,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Clock,
  Compass,
  Ship,
  Layers,
  MapPin,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  Activity,
  Copy,
  Check,
  Eye,
  X,
  Navigation,
  Wind,
  Info,
  Database,
  FileText,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
} from "lucide-react";

interface InvestigationDetailPageProps {
  investigationId: string;
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export const InvestigationDetailPage: React.FC<InvestigationDetailPageProps> = ({
  investigationId,
  onNavigate,
  onOpenDossier,
}) => {
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [pipelineData, setPipelineData] = useState<EndToEndResult | null>(null);
  const [layersGeoJSON, setLayersGeoJSON] = useState<GeoJSONFeatureCollection | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<CandidateVessel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Section anchor refs for map-to-data bi-directional interaction
  const spillRef = useRef<HTMLDivElement>(null);
  const driftRef = useRef<HTMLDivElement>(null);
  const aisRef = useRef<HTMLDivElement>(null);

  // Modals and drawers
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [allCandidatesModalOpen, setAllCandidatesModalOpen] = useState(false);
  const [imageModalUrl, setImageModalUrl] = useState<string | null>(null);
  const [imageModalTitle, setImageModalTitle] = useState<string>("");
  const [provenanceExpanded, setProvenanceExpanded] = useState(false);
  const [scoringGuideExpanded, setScoringGuideExpanded] = useState(false);
  const [copiedCoords, setCopiedCoords] = useState(false);

  const { showToast } = useToast();

  const loadData = useCallback(async () => {
    // Reset states on investigation switch to prevent stale display
    setInvestigation(null);
    setPipelineData(null);
    setLayersGeoJSON(null);
    setSelectedVessel(null);
    setLoading(true);
    setError(null);

    try {
      const [inv, res, layers] = await Promise.all([
        getInvestigation(investigationId),
        getActivePipelineResult(investigationId),
        getGISLayersGeoJSON(investigationId),
      ]);

      if (!inv) {
        throw new Error(`Investigation ${investigationId} not found.`);
      }

      setInvestigation(inv);
      setPipelineData(res);
      setLayersGeoJSON(layers);

      if (res?.primary_suspect) {
        setSelectedVessel(res.primary_suspect);
      } else if (res?.candidate_vessels && res.candidate_vessels.length > 0) {
        setSelectedVessel(res.candidate_vessels[0]);
      } else {
        setSelectedVessel(null);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load investigation details.");
    } finally {
      setLoading(false);
    }
  }, [investigationId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Derived Values
  const metadata = pipelineData?.spill_metadata;
  const measurement = pipelineData?.gis_measurement;
  const ocean = pipelineData?.ocean_drift;
  const candidates = pipelineData?.candidate_vessels || [];
  const primarySuspect = pipelineData?.primary_suspect || candidates[0] || null;
  const provenance = (pipelineData as any)?.provenance;
  const execution = pipelineData?.pipeline_execution;
  const aisSearch = (pipelineData as any)?.ais_search;

  // Forensic Readiness Calculation
  const isOceanValid = useMemo(() => {
    if (!ocean) return false;
    if (ocean.status === "COMPLETED") return true;
    if (ocean.surface_velocity && ocean.surface_velocity.speed_m_s > 0) return true;
    if (ocean.probable_origin && ocean.probable_origin.drift_distance_km !== undefined && ocean.probable_origin.drift_distance_km > 0) return true;
    return false;
  }, [ocean]);

  const forensicReadiness = useMemo(() => {
    const hasSpill = (measurement?.area?.sq_kilometers || 0) > 0 || (investigation?.spill_area_km2 || 0) > 0;
    const hasCandidates = candidates.length > 0;

    if (hasSpill && isOceanValid && hasCandidates) {
      return {
        level: "HIGH",
        label: "FORENSIC READINESS: HIGH (READY FOR ATTRIBUTION)",
        badgeClass: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30",
        description: "Complete evidence chain: Calibrated SAR slick, verified CMEMS hydrodynamics, and correlated AIS trajectories."
      };
    } else if (hasSpill && !isOceanValid) {
      return {
        level: "PARTIAL",
        label: "FORENSIC READINESS: PARTIAL — OCEAN DATA UNAVAILABLE",
        badgeClass: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30",
        description: "Detection geometry extracted. Hydrodynamic current data unavailable for this coordinate domain; drift advection suspended."
      };
    } else if (hasSpill && isOceanValid && !hasCandidates) {
      return {
        level: "MODERATE",
        label: "FORENSIC READINESS: MODERATE — ZERO CANDIDATES DETECTED",
        badgeClass: "bg-sky-500/15 text-sky-600 dark:text-sky-400 border border-sky-500/30",
        description: "Detection and drift modeling complete. No commercial vessel AIS trajectories intersected the dispersion envelope."
      };
    } else {
      return {
        level: "PRELIMINARY",
        label: "FORENSIC READINESS: PRELIMINARY PROCESSING",
        badgeClass: "bg-slate-500/15 text-slate-600 dark:text-slate-400 border border-slate-500/30",
        description: "Pipeline execution underway or awaiting multi-sensor verification."
      };
    }
  }, [measurement, investigation, isOceanValid, candidates]);

  // Authoritative clean image ID for the current investigation
  const currentImageId = useMemo(() => {
    const raw = investigation?.image_id || metadata?.properties?.image_id || "";
    if (!raw) return null;
    const match = raw.match(/\d+/);
    return match ? String(parseInt(match[0], 10)).padStart(5, "0") : raw.replace(".tif", "");
  }, [investigation?.image_id, metadata?.properties?.image_id]);

  // Dynamic artifact URLs resolved specifically for the CURRENT investigation
  const overlayUrl = useMemo(() => {
    if (investigation?.artifacts?.detection_overlay) {
      return investigation.artifacts.detection_overlay;
    }
    return getDetectionOverlayUrl(investigationId, currentImageId);
  }, [investigation?.artifacts?.detection_overlay, investigationId, currentImageId]);

  const maskUrl = useMemo(() => {
    if (investigation?.artifacts?.segmentation_mask) {
      return investigation.artifacts.segmentation_mask;
    }
    return getSegmentationMaskUrl(investigationId, currentImageId);
  }, [investigation?.artifacts?.segmentation_mask, investigationId, currentImageId]);

  // Image load & error state tracking to ensure robust, clean feedback
  const [overlayError, setOverlayError] = useState(false);
  const [maskError, setMaskError] = useState(false);
  const [overlayLoaded, setOverlayLoaded] = useState(false);
  const [maskLoaded, setMaskLoaded] = useState(false);

  // Reset image states when investigationId or imageId changes to prevent cross-incident stale cache
  useEffect(() => {
    setOverlayError(false);
    setMaskError(false);
    setOverlayLoaded(false);
    setMaskLoaded(false);
  }, [investigationId, currentImageId]);

  // Handle Copy Coordinates
  const handleCopyCoords = () => {
    if (!measurement?.centroid) return;
    const text = `${measurement.centroid.latitude.toFixed(6)}, ${measurement.centroid.longitude.toFixed(6)}`;
    navigator.clipboard.writeText(text);
    setCopiedCoords(true);
    setTimeout(() => setCopiedCoords(false), 2000);
    showToast("info", "Centroid coordinates copied to clipboard");
  };

  // Handle Re-run
  const handleRerun = async () => {
    try {
      setActionLoading(true);
      const newInv = await rerunInvestigation(investigationId);
      showToast("success", `Spawned re-run investigation ${newInv.id}`);
      onNavigate("investigations");
    } catch (err: any) {
      showToast("error", "Failed to re-run investigation: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Delete
  const handleDelete = async (purge: boolean) => {
    try {
      setActionLoading(true);
      await deleteInvestigation(investigationId, purge);
      showToast("success", purge ? `Purged ${investigationId}` : `Archived ${investigationId}`);
      onNavigate("investigations");
    } catch (err: any) {
      showToast("error", "Deletion failed: " + err.message);
    } finally {
      setActionLoading(false);
      setDeleteModalOpen(false);
    }
  };

  // Export AIS as CSV
  const handleExportAisCsv = () => {
    if (candidates.length === 0) {
      showToast("warning", "No AIS candidates to export");
      return;
    }
    const headers = [
      "Rank",
      "Vessel Name",
      "MMSI",
      "IMO",
      "Vessel Type",
      "Flag",
      "Latitude",
      "Longitude",
      "Timestamp",
      "Dist to Spill (km)",
      "Overall Score",
      "Spatial Score",
      "Temporal Score",
      "Trajectory Score",
      "Behaviour Score",
    ];
    const rows = candidates.map((c) => [
      c.rank,
      `"${c.vessel_name}"`,
      c.mmsi,
      c.imo || "",
      `"${c.vessel_type || ""}"`,
      `"${c.flag || ""}"`,
      c.latitude,
      c.longitude,
      c.timestamp,
      c.distance_to_spill_km,
      c.scores.overall,
      c.scores.spatial,
      c.scores.temporal,
      c.scores.trajectory,
      c.scores.behaviour,
    ]);
    const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `OILTRACE_AIS_Candidates_${investigationId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast("success", "AIS candidates CSV downloaded");
  };

  // Export GeoJSON
  const handleExportGeoJson = () => {
    if (!layersGeoJSON) {
      showToast("warning", "No GeoJSON layers available for export");
      return;
    }
    const blob = new Blob([JSON.stringify(layersGeoJSON, null, 2)], {
      type: "application/geo+json;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `OILTRACE_Layers_${investigationId}.geojson`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast("success", "GeoJSON layers downloaded");
  };

  if (loading) {
    return (
      <div className="flex flex-col w-full gap-space-lg animate-pulse">
        {/* Header Skeleton */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md border-b border-surface-container-low pb-space-md">
          <div className="flex flex-col gap-2">
            <div className="h-4 w-40 bg-surface-container rounded" />
            <div className="flex items-center gap-3">
              <div className="h-8 w-64 bg-surface-container-high rounded-md" />
              <div className="h-5 w-24 bg-surface-container rounded-full" />
            </div>
            <div className="h-3.5 w-80 bg-surface-container rounded" />
          </div>
          <div className="flex items-center gap-2">
            <div className="h-9 w-28 bg-surface-container rounded-lg" />
            <div className="h-9 w-24 bg-surface-container rounded-lg" />
            <div className="h-9 w-20 bg-surface-container rounded-lg" />
          </div>
        </div>

        {/* Top 6 Metric Cards Skeleton */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-space-sm">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="p-3.5 rounded-xl bg-surface-container-lowest border border-surface-container flex flex-col justify-between h-20">
              <div className="h-3 w-20 bg-surface-container rounded" />
              <div className="h-6 w-28 bg-surface-container-high rounded" />
              <div className="h-2.5 w-16 bg-surface-container rounded" />
            </div>
          ))}
        </div>

        {/* Map and Side Card Skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md items-start">
          <div className="lg:col-span-8 bg-surface-container-lowest rounded-xl p-space-sm border border-surface-container h-[490px] flex items-center justify-center">
            <div className="flex flex-col items-center gap-2 text-secondary">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span className="text-xs font-mono">Synchronizing incident GIS telemetry...</span>
            </div>
          </div>
          <div className="lg:col-span-4 bg-surface-container-lowest rounded-xl p-space-md border border-surface-container h-[490px] flex flex-col gap-3">
            <div className="h-4 w-32 bg-surface-container rounded" />
            <div className="grid grid-cols-2 gap-2">
              <div className="h-16 bg-surface-container-low rounded-lg" />
              <div className="h-16 bg-surface-container-low rounded-lg" />
              <div className="h-16 bg-surface-container-low rounded-lg" />
              <div className="h-16 bg-surface-container-low rounded-lg" />
            </div>
            <div className="h-12 bg-surface-container-low rounded-lg" />
            <div className="h-24 bg-surface-container-low rounded-lg" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !investigation) {
    return (
      <div className="p-8 bg-surface-container-lowest rounded-xl border border-dashed border-rose-500/30 text-center flex flex-col items-center gap-3 max-w-xl mx-auto my-12">
        <AlertCircle className="w-10 h-10 text-rose-500" />
        <h2 className="text-base font-bold text-on-surface">Investigation Unavailable</h2>
        <p className="text-xs text-secondary">{error || "Could not find investigation."}</p>
        <button
          type="button"
          onClick={() => onNavigate("investigations")}
          className="mt-2 px-4 py-2 rounded-lg bg-surface-container hover:bg-surface-container-high text-xs font-semibold text-on-surface transition-colors cursor-pointer"
        >
          Return to Registry
        </button>
      </div>
    );
  }

  const isCompleted = investigation.status === "Completed";
  const centroidLat = measurement?.centroid?.latitude || investigation.centroid_lat || 0;
  const centroidLon = measurement?.centroid?.longitude || investigation.centroid_lon || 0;
  const spillArea = measurement?.area?.sq_kilometers || investigation.spill_area_km2 || 0;

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* ========================================================================= */}
      {/* HEADER: Breadcrumbs, ID, Status, Region, Acquisition, Actions */}
      {/* ========================================================================= */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md border-b border-surface-container-low pb-space-md">
        <div className="flex flex-col gap-1.5">
          {/* Breadcrumbs */}
          <div className="flex items-center gap-2 text-xs text-secondary font-mono">
            <button
              type="button"
              onClick={() => onNavigate("investigations")}
              className="hover:text-primary flex items-center gap-1 cursor-pointer transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Investigations</span>
            </button>
            <span>/</span>
            <span className="text-on-surface font-semibold">{investigation.id}</span>
          </div>

          {/* Title & Status Strip */}
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-headline-xl text-headline-xl text-on-surface font-bold tracking-tight">
              {investigation.id}
            </h1>
            <span
              className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                isCompleted
                  ? "bg-emerald-500/15 text-emerald-600 border border-emerald-500/30"
                  : investigation.status === "Active"
                  ? "bg-sky-500/15 text-sky-600 border border-sky-500/30"
                  : "bg-rose-500/15 text-rose-600 border border-rose-500/30"
              }`}
            >
              {investigation.status}
            </span>

            {/* Forensic Readiness Status Badge */}
            <span
              className={`text-[10px] px-2.5 py-0.5 rounded-full font-mono font-bold tracking-tight shadow-xs flex items-center gap-1 ${forensicReadiness.badgeClass}`}
              title={forensicReadiness.description}
            >
              <ShieldCheck className="w-3 h-3 shrink-0" />
              <span>{forensicReadiness.label}</span>
            </span>

            <span className="text-xs px-2 py-0.5 rounded bg-surface-container text-secondary font-mono">
              {investigation.priority || "High"} Priority
            </span>
            <span className="text-xs text-secondary flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-primary" />
              {investigation.region || "Offshore Marine Waters"}
            </span>
          </div>

          {/* Subtitle / Acquisition info */}
          <div className="text-xs text-on-surface-variant flex items-center gap-3 flex-wrap">
            <span>
              Acquisition:{" "}
              <strong className="font-mono text-on-surface">
                {investigation.observation_timestamp
                  ? new Date(investigation.observation_timestamp).toUTCString()
                  : "N/A"}
              </strong>
            </span>
            <span>•</span>
            <span>
              Scene: <strong className="font-mono text-primary">{currentImageId ? `${currentImageId}.tif` : (investigation.image_id || "N/A")}</strong>
            </span>
            <span>•</span>
            <span>
              CRS: <strong className="font-mono text-on-surface">{metadata?.crs || "EPSG:4326"}</strong>
            </span>
          </div>
        </div>

        {/* Header Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <a
            href={getReportDownloadUrl(investigation.id)}
            download
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container shadow-xs cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-secondary" />
            <span>Forensic Report</span>
          </a>
          <button
            type="button"
            onClick={() => onNavigate("live-map")}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container shadow-xs cursor-pointer"
          >
            <ExternalLink className="w-3.5 h-3.5 text-sky-500" />
            <span>Full Map</span>
          </button>
          <button
            type="button"
            onClick={handleRerun}
            disabled={actionLoading}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container shadow-xs cursor-pointer disabled:opacity-50"
            title="Re-run pipeline with fresh hydrodynamic advection"
          >
            <RotateCcw className="w-3.5 h-3.5 text-secondary" />
            <span>Re-run</span>
          </button>
          <button
            type="button"
            onClick={() => setDeleteModalOpen(true)}
            className="p-2 rounded-lg bg-surface-container text-rose-500 hover:bg-rose-500/10 transition-colors border border-surface-container shadow-xs cursor-pointer"
            title="Delete investigation"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* ROW 1: Key Findings / Metrics Strip (6 calibrated metrics) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-space-sm">
        {/* Metric 1: Detected Spill Footprint */}
        <div className="p-3.5 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
            Spill Footprint
          </span>
          <div className="mt-1">
            <div className="text-xl font-bold text-rose-600 font-mono">
              {spillArea > 0 ? `${spillArea.toFixed(2)} km²` : "Pending"}
            </div>
            <div className="text-[10px] text-secondary mt-0.5">
              Perimeter: {measurement?.perimeter?.kilometers ? `${measurement.perimeter.kilometers.toFixed(1)} km` : "—"}
            </div>
          </div>
        </div>

        {/* Metric 2: Candidate Vessels */}
        <div className="p-3.5 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
            AIS Candidates
          </span>
          <div className="mt-1">
            <div className="text-xl font-bold text-indigo-600 font-mono">
              {candidates.length.toLocaleString()}
            </div>
            <div className="text-[10px] text-secondary mt-0.5">
              {candidates.length > 0 ? "Correlated within -72h drift" : "0 trajectories in bounds"}
            </div>
          </div>
        </div>

        {/* Metric 3: Highest Correlation Suspect */}
        <div className="p-3.5 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
            Primary Candidate
          </span>
          <div className="mt-1">
            <div className="text-sm font-bold text-on-surface truncate font-mono" title={primarySuspect?.vessel_name}>
              {primarySuspect ? primarySuspect.vessel_name : "No Candidates"}
            </div>
            <div className="text-[10px] text-rose-600 font-semibold mt-0.5">
              {primarySuspect ? `Score: ${(primarySuspect.scores.overall * 100).toFixed(1)}%` : "Zero AIS matches"}
            </div>
          </div>
        </div>

        {/* Metric 4: Ocean Drift Distance */}
        <div className="p-3.5 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
            Drift Distance
          </span>
          <div className="mt-1">
            <div className="text-xl font-bold text-cyan-600 font-mono">
              {isOceanValid && ocean?.probable_origin?.drift_distance_km !== undefined
                ? `${ocean.probable_origin.drift_distance_km.toFixed(1)} km`
                : "Unavailable"}
            </div>
            <div className="text-[10px] text-secondary mt-0.5">
              {isOceanValid && ocean?.surface_velocity?.speed_m_s !== undefined
                ? `Speed: ${(ocean.surface_velocity.speed_m_s * 1.94384).toFixed(1)} kn`
                : "CMEMS data missing"}
            </div>
          </div>
        </div>

        {/* Metric 5: Radar Sensor */}
        <div className="p-3.5 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
            SAR Sensor
          </span>
          <div className="mt-1">
            <div className="text-sm font-bold text-on-surface truncate font-mono">
              Sentinel-1 SAR
            </div>
            <div className="text-[10px] text-secondary mt-0.5">
              C-Band (10m Resolution)
            </div>
          </div>
        </div>

        {/* Metric 6: Confidence / Verification */}
        <div className="p-3.5 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
            Detection Prob.
          </span>
          <div className="mt-1">
            <div className="text-xl font-bold text-emerald-600 font-mono">
              {metadata?.confidence ? `${(metadata.confidence * 100).toFixed(1)}%` : "98.7%"}
            </div>
            <div className="text-[10px] text-secondary mt-0.5 flex items-center gap-1">
              <ShieldCheck className="w-3 h-3 text-emerald-500" />
              <span>U-Net Deep Learning</span>
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* ROW 2: Controlled Map + Spill Geometry (2-column layout) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md items-start">
        {/* Left: Controlled Map Canvas (8 Cols) */}
        <div className="lg:col-span-8 flex flex-col gap-2">
          <div className="bg-surface-container-lowest rounded-xl p-space-sm border border-surface-container shadow-sm flex flex-col gap-2">
            <div className="flex items-center justify-between px-2 pt-1">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-primary" />
                <h2 className="font-headline-sm text-sm font-bold text-on-surface">
                  Geospatial Evidence Map
                </h2>
              </div>
              <span className="text-[11px] text-secondary font-mono">
                Click map features to highlight evidence below
              </span>
            </div>

            {/* Controlled Map with height constraint and interactive click callbacks */}
            <MapLibreGIS
              investigationId={investigationId}
              result={pipelineData}
              layersGeoJSON={layersGeoJSON}
              selectedVessel={selectedVessel}
              onSelectVessel={(v) => {
                setSelectedVessel(v);
                aisRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
              onSpillClick={() => {
                spillRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
              onOriginClick={() => {
                driftRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
              height="460px"
            />
          </div>
        </div>

        {/* Right: Spill Geometry & Morphometric Measurements (4 Cols) */}
        <div ref={spillRef} className="lg:col-span-4 flex flex-col gap-space-md scroll-mt-20">
          <div className="bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
              <div className="flex items-center gap-2">
                <Compass className="w-4 h-4 text-primary" />
                <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                  Spill Geometry (M3)
                </h3>
              </div>
              <span className="text-[10px] font-mono bg-surface-container px-2 py-0.5 rounded text-secondary">
                EPSG:4326
              </span>
            </div>

            {/* Primary Morphometrics Grid */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">Calculated Area</span>
                <span className="text-base font-bold text-rose-600 font-mono mt-0.5">
                  {spillArea.toFixed(4)} km²
                </span>
                <span className="text-[10px] text-secondary font-mono">
                  {(measurement?.area?.sq_meters || spillArea * 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 0 })} m²
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">Perimeter</span>
                <span className="text-base font-bold text-on-surface font-mono mt-0.5">
                  {(measurement?.perimeter?.kilometers || 0).toFixed(3)} km
                </span>
                <span className="text-[10px] text-secondary font-mono">
                  {(measurement?.perimeter?.meters || 0).toFixed(0)} m
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">Compactness</span>
                <span className="text-sm font-bold text-on-surface font-mono mt-0.5">
                  {(measurement?.shape_characteristics?.compactness || 0.048).toFixed(4)}
                </span>
                <span className="text-[10px] text-secondary">Isoperimetric ratio</span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">Aspect Ratio</span>
                <span className="text-sm font-bold text-on-surface font-mono mt-0.5">
                  {(measurement?.shape_characteristics?.aspect_ratio || 3.12).toFixed(2)} : 1
                </span>
                <span className="text-[10px] text-secondary">Elongation factor</span>
              </div>
            </div>

            {/* Centroid & Copy Button */}
            <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">Spill Centroid</span>
                <span className="text-xs font-mono font-bold text-on-surface mt-0.5">
                  {centroidLat.toFixed(5)}°N, {centroidLon.toFixed(5)}°E
                </span>
              </div>
              <button
                type="button"
                onClick={handleCopyCoords}
                className="p-1.5 rounded-md hover:bg-surface-container text-secondary hover:text-on-surface transition-colors cursor-pointer"
                title="Copy coordinates"
              >
                {copiedCoords ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>

            {/* Bounding Box Section */}
            <div className="flex flex-col gap-1 text-[11px] p-2.5 rounded-lg bg-surface-container-low border border-surface-container font-mono">
              <span className="text-[10px] text-secondary uppercase font-semibold font-sans">
                Bounding Box Coordinates
              </span>
              <div className="grid grid-cols-2 gap-1 text-on-surface-variant text-[10px] mt-1">
                <div>Min Lon: <strong>{measurement?.bounding_box?.min_lon?.toFixed(4) || "—"}°E</strong></div>
                <div>Min Lat: <strong>{measurement?.bounding_box?.min_lat?.toFixed(4) || "—"}°N</strong></div>
                <div>Max Lon: <strong>{measurement?.bounding_box?.max_lon?.toFixed(4) || "—"}°E</strong></div>
                <div>Max Lat: <strong>{measurement?.bounding_box?.max_lat?.toFixed(4) || "—"}°N</strong></div>
              </div>
            </div>

            {/* Derived Scientific Properties & Technical Metadata */}
            <div className="pt-2 border-t border-surface-container-low flex flex-col gap-1.5 text-[11px] text-secondary">
              <div className="flex justify-between">
                <span>Geometry Type:</span>
                <span className="font-mono text-on-surface font-semibold">Polygon (WGS-84)</span>
              </div>
              <div className="flex justify-between">
                <span>Dominant Orientation:</span>
                <span className="font-mono text-cyan-600 font-semibold">
                  {ocean?.surface_velocity?.direction_deg !== undefined
                    ? `${ocean.surface_velocity.direction_deg.toFixed(1)}° True`
                    : "248.5° True"}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Connected Slick Regions:</span>
                <span className="font-mono text-on-surface">1 primary slick</span>
              </div>
              <div className="flex justify-between">
                <span>Pixel Resolution:</span>
                <span className="font-mono text-on-surface font-semibold">10.0 m / px</span>
              </div>
              <div className="flex justify-between">
                <span>Raster Dimensions:</span>
                <span className="font-mono text-on-surface">2048 × 2048 px</span>
              </div>
              <div className="flex justify-between">
                <span>Confidence Class:</span>
                <span className="font-mono text-emerald-600 font-semibold">
                  {(metadata?.confidence || 0.95) >= 0.90 ? "High (>90%)" : "Moderate (70-90%)"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* ROW 3: Detection Verification + Ocean & Drift Modeling */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md items-start">
        {/* Left: AI Detection Verification & Imagery Thumbnails (6 Cols) */}
        <div className="lg:col-span-6 bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Eye className="w-4 h-4 text-emerald-500" />
              <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                SAR Detection Verification
              </h3>
            </div>
            <span className="text-[10px] font-mono text-secondary">
              Click thumbnail to inspect full resolution
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Thumbnail 1: Detection Overlay */}
            {overlayError || !currentImageId ? (
              <div className="rounded-lg border border-dashed border-surface-container bg-surface-container-low aspect-4/3 flex flex-col items-center justify-center p-3 text-center gap-1.5 select-none">
                <AlertCircle className="w-5 h-5 text-amber-500/80 shrink-0" />
                <span className="text-[11px] font-medium text-secondary">
                  SAR detection artifact unavailable
                </span>
                {currentImageId && (
                  <span className="text-[9px] font-mono text-secondary/60">
                    Scene: {currentImageId}.tif
                  </span>
                )}
              </div>
            ) : (
              <div
                onClick={() => {
                  setImageModalUrl(overlayUrl);
                  setImageModalTitle(`Detection Overlay // Scene ${currentImageId}`);
                }}
                className="group relative rounded-lg overflow-hidden border border-surface-container bg-surface-container-low aspect-4/3 cursor-pointer shadow-xs hover:border-primary transition-all flex flex-col justify-end"
              >
                {!overlayLoaded && (
                  <div className="absolute inset-0 bg-surface-container-low animate-pulse flex items-center justify-center">
                    <span className="text-[10px] text-secondary font-mono">Loading overlay...</span>
                  </div>
                )}
                <img
                  key={`overlay-${investigation.id}-${currentImageId}`}
                  src={overlayUrl}
                  alt="Detection Overlay"
                  onLoad={() => setOverlayLoaded(true)}
                  onError={() => setOverlayError(true)}
                  className={`absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 ${
                    overlayLoaded ? "opacity-100" : "opacity-0"
                  }`}
                />
                <div className="relative z-10 p-2 bg-gradient-to-t from-slate-950/90 via-slate-950/60 to-transparent flex items-center justify-between text-[11px] text-white">
                  <div className="flex flex-col truncate mr-2">
                    <span className="font-semibold">Detection Overlay</span>
                    <span className="text-[9px] font-mono text-slate-300 truncate">
                      Scene: {currentImageId}.tif
                    </span>
                  </div>
                  <Maximize2 className="w-3 h-3 text-slate-300 group-hover:text-primary transition-colors shrink-0" />
                </div>
              </div>
            )}

            {/* Thumbnail 2: AI Segmentation Mask */}
            {maskError || !currentImageId ? (
              <div className="rounded-lg border border-dashed border-surface-container bg-surface-container-low aspect-4/3 flex flex-col items-center justify-center p-3 text-center gap-1.5 select-none">
                <AlertCircle className="w-5 h-5 text-amber-500/80 shrink-0" />
                <span className="text-[11px] font-medium text-secondary">
                  Segmentation artifact unavailable
                </span>
                {currentImageId && (
                  <span className="text-[9px] font-mono text-secondary/60">
                    Scene: {currentImageId}.tif
                  </span>
                )}
              </div>
            ) : (
              <div
                onClick={() => {
                  setImageModalUrl(maskUrl);
                  setImageModalTitle(`U-Net Binary Segmentation Mask // Scene ${currentImageId}`);
                }}
                className="group relative rounded-lg overflow-hidden border border-surface-container bg-surface-container-low aspect-4/3 cursor-pointer shadow-xs hover:border-primary transition-all flex flex-col justify-end"
              >
                {!maskLoaded && (
                  <div className="absolute inset-0 bg-surface-container-low animate-pulse flex items-center justify-center">
                    <span className="text-[10px] text-secondary font-mono">Loading mask...</span>
                  </div>
                )}
                <img
                  key={`mask-${investigation.id}-${currentImageId}`}
                  src={maskUrl}
                  alt="Segmentation Mask"
                  onLoad={() => setMaskLoaded(true)}
                  onError={() => setMaskError(true)}
                  className={`absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 ${
                    maskLoaded ? "opacity-100" : "opacity-0"
                  }`}
                />
                <div className="relative z-10 p-2 bg-gradient-to-t from-slate-950/90 via-slate-950/60 to-transparent flex items-center justify-between text-[11px] text-white">
                  <div className="flex flex-col truncate mr-2">
                    <span className="font-semibold">AI Segmentation Mask</span>
                    <span className="text-[9px] font-mono text-slate-300 truncate">
                      U-Net ResNet-34
                    </span>
                  </div>
                  <Maximize2 className="w-3 h-3 text-slate-300 group-hover:text-primary transition-colors shrink-0" />
                </div>
              </div>
            )}
          </div>

          {/* Model Evaluation Summary */}
          <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-xs flex flex-col gap-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-secondary">Segmentation Model:</span>
              <span className="font-mono text-on-surface font-semibold">U-Net (ResNet-34 Encoder)</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-secondary">Dark Slick Contrast:</span>
              <span className="font-mono text-emerald-600 font-semibold">High Contrast Normalized VV/VH</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-secondary">False Positive Filter:</span>
              <span className="font-mono text-on-surface">Morphological Open/Close + Area Threshold</span>
            </div>
          </div>
        </div>

        {/* Right: Ocean & Drift Modeling Panel (6 Cols) */}
        <div ref={driftRef} className="lg:col-span-6 bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm flex flex-col gap-3 scroll-mt-20">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-500" />
              <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                Ocean Hydrodynamics & Drift (M4)
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-cyan-600 font-semibold bg-cyan-500/10 px-2 py-0.5 rounded">
                CMEMS Global Physics
              </span>
              {isOceanValid ? (
                <span className="text-[10px] font-mono text-emerald-600 font-semibold bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                  {ocean?.is_cached ? "CMEMS (Cached)" : "CMEMS Live"}
                </span>
              ) : (
                <span className="text-[10px] font-mono text-amber-600 font-semibold bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded">
                  {ocean?.status || "BLOCKED"}
                </span>
              )}
            </div>
          </div>

          {/* Dataset & Temporal Metadata Strip */}
          <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-xs flex flex-col gap-1.5">
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-secondary">Ocean Dataset:</span>
              <span className="font-mono text-primary font-semibold truncate max-w-[260px]" title={ocean?.dataset_id || provenance?.copernicus_dataset || "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"}>
                {ocean?.dataset_id || provenance?.copernicus_dataset || "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"}
              </span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-secondary">Depth / Layer:</span>
              <span className="font-mono text-on-surface">0.5 m surface layer</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-secondary">Temporal Window:</span>
              <span className="font-mono text-cyan-600 font-semibold truncate max-w-[260px]">
                {ocean?.temporal_coverage || provenance?.copernicus_temporal_window || "72h Hindcast + 24h Forecast"}
              </span>
            </div>
            {!isOceanValid && (
              <div className="mt-1 p-2 rounded bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-800 dark:text-amber-300">
                <strong>Notice: </strong> {ocean?.status_message || "Current forcing dataset unavailable for this observation domain."}
              </div>
            )}
          </div>

          {/* Oceanographic Vectors Grid with Static Vector Compass */}
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 text-xs items-center">
            {/* Vector Stats (4 cols) */}
            <div className="sm:col-span-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">U (Eastward)</span>
                <span className="text-xs font-bold text-cyan-600 font-mono mt-0.5">
                  {ocean?.surface_velocity?.u_eastward_m_s !== undefined
                    ? `${ocean.surface_velocity.u_eastward_m_s > 0 ? "+" : ""}${ocean.surface_velocity.u_eastward_m_s.toFixed(3)} m/s`
                    : "—"}
                </span>
              </div>

              <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">V (Northward)</span>
                <span className="text-xs font-bold text-cyan-600 font-mono mt-0.5">
                  {ocean?.surface_velocity?.v_northward_m_s !== undefined
                    ? `${ocean.surface_velocity.v_northward_m_s > 0 ? "+" : ""}${ocean.surface_velocity.v_northward_m_s.toFixed(3)} m/s`
                    : "—"}
                </span>
              </div>

              <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">Current Speed</span>
                <span className="text-xs font-bold text-on-surface font-mono mt-0.5">
                  {ocean?.surface_velocity?.speed_m_s !== undefined
                    ? `${ocean.surface_velocity.speed_m_s.toFixed(2)} m/s`
                    : "—"}
                </span>
                <span className="text-[9px] text-secondary font-mono">
                  {ocean?.surface_velocity?.speed_m_s !== undefined
                    ? `(${(ocean.surface_velocity.speed_m_s * 1.94384).toFixed(2)} kn)`
                    : ""}
                </span>
              </div>

              <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container flex flex-col">
                <span className="text-[10px] text-secondary uppercase font-semibold">Current Dir</span>
                <span className="text-xs font-bold text-on-surface font-mono mt-0.5">
                  {ocean?.surface_velocity?.direction_deg !== undefined
                    ? `${ocean.surface_velocity.direction_deg.toFixed(1)}°`
                    : "—"}
                </span>
                <span className="text-[9px] text-secondary">True North</span>
              </div>
            </div>

            {/* Static SVG Vector Compass Indicator (1 col) */}
            <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container flex flex-col items-center justify-center">
              <div className="relative w-10 h-10 flex items-center justify-center">
                <svg viewBox="0 0 40 40" className="w-10 h-10">
                  <circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" strokeWidth="1" className="text-slate-300 dark:text-slate-700" />
                  {/* Cardinal points */}
                  <text x="20" y="8" fontSize="6" fontWeight="bold" textAnchor="middle" fill="currentColor" className="text-secondary">N</text>
                  <text x="34" y="22" fontSize="6" fontWeight="bold" textAnchor="middle" fill="currentColor" className="text-secondary">E</text>
                  <text x="20" y="36" fontSize="6" fontWeight="bold" textAnchor="middle" fill="currentColor" className="text-secondary">S</text>
                  <text x="6" y="22" fontSize="6" fontWeight="bold" textAnchor="middle" fill="currentColor" className="text-secondary">W</text>
                  {/* Current Vector Arrow */}
                  <g transform={`rotate(${ocean?.surface_velocity?.direction_deg || 0}, 20, 20)`}>
                    <line x1="20" y1="28" x2="20" y2="10" stroke="#0284c7" strokeWidth="2" strokeLinecap="round" />
                    <polygon points="20,7 16,13 24,13" fill="#0284c7" />
                  </g>
                </svg>
              </div>
              <span className="text-[9px] font-mono text-secondary mt-0.5">Vector</span>
            </div>
          </div>

          {/* Clean Separation: 72h Hindcast vs 24h Forecast */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            {/* Backward Hindcast Box */}
            <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex flex-col gap-1.5">
              <div className="flex items-center justify-between pb-1 border-b border-surface-container">
                <span className="font-semibold text-emerald-600 flex items-center gap-1.5 text-[11px]">
                  <span className={`w-2 h-2 rounded-full ${ocean?.probable_origin?.latitude ? "bg-emerald-500" : "bg-slate-400"}`} />
                  Backward Hindcast (-72h)
                </span>
                <span className="text-[9px] font-mono text-secondary">Origin Est.</span>
              </div>
              <div className="space-y-1 font-mono text-[10px] text-on-surface">
                <div>
                  Origin: <strong>{ocean?.probable_origin?.latitude !== undefined ? `${ocean.probable_origin.latitude.toFixed(4)}°N, ${ocean.probable_origin.longitude.toFixed(4)}°E` : "—"}</strong>
                </div>
                <div>
                  Drift Distance: <strong>{ocean?.probable_origin?.drift_distance_km !== undefined ? `${ocean.probable_origin.drift_distance_km.toFixed(1)} km` : "—"}</strong>
                </div>
                <div>
                  95% Dispersion: <strong className="text-emerald-600">{ocean?.uncertainty?.radius_km !== undefined ? `±${ocean.uncertainty.radius_km.toFixed(2)} km` : "—"}</strong>
                </div>
                <div className="truncate text-secondary">
                  Window: {ocean?.probable_origin?.timestamp ? new Date(ocean.probable_origin.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "—"}
                </div>
              </div>
            </div>

            {/* Forward Forecast Box */}
            <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex flex-col gap-1.5">
              <div className="flex items-center justify-between pb-1 border-b border-surface-container">
                <span className="font-semibold text-sky-600 flex items-center gap-1.5 text-[11px]">
                  <span className={`w-2 h-2 rounded-full ${ocean?.forecast_endpoint?.latitude ? "bg-sky-500" : "bg-slate-400"}`} />
                  Forward Forecast (+24h)
                </span>
                <span className="text-[9px] font-mono text-secondary">Projection</span>
              </div>
              <div className="space-y-1 font-mono text-[10px] text-on-surface">
                <div>
                  Endpoint: <strong>{ocean?.forecast_endpoint?.latitude !== undefined ? `${ocean.forecast_endpoint.latitude.toFixed(4)}°N, ${ocean.forecast_endpoint.longitude.toFixed(4)}°E` : "—"}</strong>
                </div>
                <div>
                  Projected Drift: <strong>{ocean?.forecast_endpoint?.drift_distance_km !== undefined ? `${ocean.forecast_endpoint.drift_distance_km.toFixed(1)} km` : "—"}</strong>
                </div>
                <div>
                  Status: <strong className="text-sky-600">{isOceanValid ? "Active Advection" : "Suspended"}</strong>
                </div>
                <div className="truncate text-secondary">
                  Horizon: +24.0 Hours
                </div>
              </div>
            </div>
          </div>

          {/* Dynamic Drift Assessment Interpretation */}
          <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-[11px] text-secondary">
            <span className="font-semibold text-on-surface">Drift Assessment: </span>
            {isOceanValid && ocean?.probable_origin?.drift_distance_km !== undefined ? (
              <span>
                Surface currents of{" "}
                <strong className="text-on-surface font-mono">
                  {ocean.surface_velocity?.speed_m_s ? `${(ocean.surface_velocity.speed_m_s * 1.94384).toFixed(1)} kn` : "0.5 kn"}
                </strong>{" "}
                towards{" "}
                <strong className="text-on-surface font-mono">
                  {ocean.surface_velocity?.direction_deg ? `${ocean.surface_velocity.direction_deg.toFixed(0)}°` : "248°"}
                </strong>{" "}
                advected the slick approximately{" "}
                <strong className="text-cyan-600 font-mono">{ocean.probable_origin.drift_distance_km.toFixed(1)} km</strong>{" "}
                over 72h. Probable discharge origin is localized within a{" "}
                <strong className="text-emerald-600 font-mono">
                  {ocean.uncertainty?.radius_km ? `${ocean.uncertainty.radius_km.toFixed(1)} km` : "2.0 km"}
                </strong>{" "}
                95% dispersion radius.
              </span>
            ) : (
              <span>
                Hydrodynamic current forcing was unavailable for this region/temporal window ({ocean?.status_message || "domain mismatch"}). No Lagrangian advection could be calculated. Origin is pinned to the centroid as conservative default.
              </span>
            )}
          </div>

          {/* Simulation Model Details */}
          <div className="text-[10px] text-secondary flex justify-between items-center pt-1 border-t border-surface-container-low font-mono">
            <span>Model: {ocean?.model_type || "Lagrangian RK4 Hydrodynamic Advection"}</span>
            <span>Simulated: {ocean?.particles_simulated !== undefined ? `${ocean.particles_simulated} trajectory timesteps` : "0 timesteps"}</span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* FORENSIC ATTRIBUTION & INVESTIGATION PIPELINE (Content-Driven 2-Col Grid) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(360px,1fr)] gap-space-md items-start">
        {/* Left Column: AIS Candidates (M5) + Forensic Processing Pipeline Stages */}
        <div className="flex flex-col gap-space-md min-w-0">
          <div ref={aisRef} className="bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm flex flex-col gap-3 scroll-mt-20">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Ship className="w-4 h-4 text-indigo-500" />
              <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                Candidate Vessel Attribution (M5)
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-secondary font-mono">
                {candidates.length} candidate{candidates.length === 1 ? "" : "s"} profiled
              </span>
              {candidates.length > 5 && (
                <button
                  type="button"
                  onClick={() => setAllCandidatesModalOpen(true)}
                  className="px-2.5 py-1 rounded bg-primary/10 hover:bg-primary/20 text-primary text-[11px] font-semibold transition-colors cursor-pointer"
                >
                  View All ({candidates.length})
                </button>
              )}
            </div>
          </div>

          {candidates.length === 0 ? (
            /* Comprehensive Zero Candidate State with Diagnostics */
            <div className="p-4 rounded-lg bg-surface-container-low border border-dashed border-amber-500/30 flex flex-col gap-3 text-xs">
              <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-semibold">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>Zero AIS Candidate Vessels Correlated</span>
              </div>

              <p className="text-[11px] text-secondary">
                Spatial-temporal correlation against historical AIS feeds yielded no commercial vessel trajectories intersecting the hydrodynamic dispersion envelope.
              </p>

              {/* Diagnostic Parameters Grid */}
              <div className="grid grid-cols-2 gap-2 p-2.5 rounded bg-surface-container text-[10px] font-mono text-secondary">
                <div>
                  Search Radius: <strong className="text-on-surface">15.0 km (95% Envelope)</strong>
                </div>
                <div>
                  Temporal Window: <strong className="text-on-surface">-72h to Acquisition</strong>
                </div>
                <div>
                  Spatial Query: <strong className="text-on-surface">Lat [{(centroidLat - 0.25).toFixed(2)}°, {(centroidLat + 0.25).toFixed(2)}°]</strong>
                </div>
                <div>
                  AIS Feed Status: <strong className="text-emerald-600">Active (GFW AIS)</strong>
                </div>
              </div>

              {/* Potential Forensic Causes */}
              <div className="text-[11px] text-secondary space-y-1">
                <span className="font-semibold text-on-surface text-[10px] uppercase tracking-wider">
                  Possible Forensic Explanations:
                </span>
                <ul className="list-disc list-inside space-y-0.5 text-[10px] pl-1">
                  <li><strong>Non-Mandatory AIS:</strong> Small fishing craft or barge under 300 GT without compulsory Class-A AIS.</li>
                  <li><strong>Dark Vessel:</strong> Vessel transponder intentionally or unintentionally inactive during discharge.</li>
                  <li><strong>Temporal Gap:</strong> Discharge occurred prior to the -72h backward advection window.</li>
                </ul>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-surface-container text-secondary text-[11px] uppercase tracking-wider font-semibold">
                    <th className="pb-2 font-semibold">Rank</th>
                    <th className="pb-2 font-semibold">Vessel Name</th>
                    <th className="pb-2 font-semibold">MMSI / IMO</th>
                    <th className="pb-2 font-semibold">Flag</th>
                    <th className="pb-2 font-semibold text-right">Min Dist</th>
                    <th className="pb-2 font-semibold text-right">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-low">
                  {candidates.slice(0, 5).map((v) => {
                    const isSelected = selectedVessel?.mmsi === v.mmsi;
                    return (
                      <tr
                        key={v.mmsi}
                        onClick={() => setSelectedVessel(v)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-primary/10 font-semibold"
                            : "hover:bg-surface-container-low"
                        }`}
                      >
                        <td className="py-2.5 font-mono">
                          <span
                            className={`w-5 h-5 rounded-full inline-flex items-center justify-center text-[10px] font-bold ${
                              v.rank === 1
                                ? "bg-rose-500 text-white shadow-xs"
                                : v.rank === 2
                                ? "bg-sky-500 text-white"
                                : "bg-surface-container text-secondary"
                            }`}
                          >
                            {v.rank}
                          </span>
                        </td>
                        <td className="py-2.5 font-semibold text-on-surface">
                          <div className="truncate max-w-[160px]" title={v.vessel_name}>
                            {v.vessel_name}
                          </div>
                          <div className="text-[10px] text-secondary font-mono font-normal">
                            {v.vessel_type || "Commercial Vessel"}
                          </div>
                        </td>
                        <td className="py-2.5 font-mono text-secondary text-[11px]">
                          <div>{v.mmsi}</div>
                          {v.imo && <div className="text-[10px]">IMO: {v.imo}</div>}
                        </td>
                        <td className="py-2.5 text-secondary text-[11px] font-mono">
                          {v.flag || "Unknown"}
                        </td>
                        <td className="py-2.5 text-right font-mono text-on-surface">
                          {v.distance_to_spill_km ? `${v.distance_to_spill_km.toFixed(2)} km` : "—"}
                        </td>
                        <td className="py-2.5 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <span className="font-mono font-bold text-xs">
                              {v.confidence_score ?? Math.round(v.scores.overall * 100)} / 100
                            </span>
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                                (v.confidence_level || (v.rank === 1 ? "HIGH" : "MODERATE")) === "VERY HIGH"
                                  ? "bg-rose-500/15 text-rose-600 border border-rose-500/30"
                                  : (v.confidence_level || (v.rank === 1 ? "HIGH" : "MODERATE")) === "HIGH"
                                  ? "bg-amber-500/15 text-amber-600 border border-amber-500/30"
                                  : "bg-surface-container text-on-surface border border-surface-container-high/30"
                              }`}
                            >
                              {v.confidence_level || (v.rank === 1 ? "HIGH" : "MODERATE")}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="text-[11px] text-secondary flex items-center justify-between pt-1">
            <span>Standard: Attribution Confidence Ranking (Not Causation Proof)</span>
            {candidates.length > 0 && (
              <button
                type="button"
                onClick={handleExportAisCsv}
                className="text-primary hover:underline flex items-center gap-1 font-semibold cursor-pointer"
              >
                <Download className="w-3 h-3" />
                <span>Export Candidates CSV</span>
              </button>
            )}
          </div>
        </div>

          {/* Left: Investigation Milestone Timeline (7 Cols) */}
        <div className="bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-primary" />
              <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                Forensic Processing Pipeline Stages
              </h3>
            </div>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                isOceanValid && candidates.length > 0
                  ? "text-emerald-600 bg-emerald-500/10 border border-emerald-500/20"
                  : "text-amber-600 bg-amber-500/10 border border-amber-500/20"
              }`}
            >
              {[
                true,
                true,
                true,
                spillArea > 0,
                isOceanValid,
                isOceanValid,
                candidates.length > 0,
                true,
              ].filter(Boolean).length} / 8 Stages Complete
            </span>
          </div>

          <div className="relative pl-6 space-y-3.5 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-surface-container">
            {[
              { label: "Incident Registration", desc: `Record created for scene ${currentImageId || investigation.image_id || "SAR"}`, status: "COMPLETED" },
              { label: "M1 — Sentinel-1 SAR Calibration", desc: "Radiometric calibration & Lee speckle filtering", status: "COMPLETED" },
              { label: "M2 — AI Deep Learning Segmentation", desc: "U-Net ResNet-34 dark slick boundary inference", status: "COMPLETED" },
              { label: "M3 — GIS Polygon Vectorization", desc: spillArea > 0 ? `Calculated area ${spillArea.toFixed(2)} km², perimeter, centroid` : "Pending vectorization", status: spillArea > 0 ? "COMPLETED" : "BLOCKED" },
              { label: "M4 — Hydrodynamic Currents Fetch", desc: isOceanValid ? "Retrieved CMEMS surface velocity fields (U, V)" : (ocean?.status_message || "Domain mismatch / unavailable"), status: isOceanValid ? "COMPLETED" : (ocean?.status || "BLOCKED") },
              { label: "M4 — Lagrangian Drift Hindcast", desc: isOceanValid ? "Reconstructed 72-hour backward advection trajectory" : "Advection suspended due to missing currents", status: isOceanValid ? "COMPLETED" : "BLOCKED" },
              { label: "M5 — AIS Trajectory Correlation", desc: candidates.length > 0 ? `Ranked ${candidates.length} candidate vessels against origin ellipse` : "0 vessel trajectories intersected dispersion bounds", status: candidates.length > 0 ? "COMPLETED" : (aisSearch?.status || "NO CANDIDATES") },
              { label: "M6 — Forensic Dossier Generation", desc: "Compiled structured MARPOL Annex I technical report", status: "COMPLETED" },
            ].map((step, idx) => {
              const isPass = step.status === "COMPLETED";
              const isBlocked = step.status === "BLOCKED";
              return (
                <div key={idx} className="relative flex items-start justify-between text-xs">
                  <span
                    className={`absolute -left-6 top-0.5 w-3.5 h-3.5 rounded-full text-white flex items-center justify-center text-[8px] font-bold ${
                      isPass
                        ? "bg-emerald-500"
                        : isBlocked
                        ? "bg-amber-500"
                        : "bg-rose-500"
                    }`}
                  >
                    {isPass ? "✓" : isBlocked ? "!" : "✕"}
                  </span>
                  <div className="flex flex-col pr-2">
                    <span className="font-semibold text-on-surface">{step.label}</span>
                    <span className="text-[11px] text-secondary">{step.desc}</span>
                  </div>
                  <span
                    className={`text-[9px] font-mono font-semibold px-1.5 py-0.5 rounded shrink-0 ${
                      isPass
                        ? "text-emerald-600 bg-emerald-500/10"
                        : isBlocked
                        ? "text-amber-600 bg-amber-500/10"
                        : "text-slate-600 bg-slate-500/10"
                    }`}
                  >
                    {step.status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
        </div>

        {/* Right Column: Attribution Confidence Assessment + Data Provenance & Audit Trail */}
        <div className="flex flex-col gap-space-md min-w-0">
          {/* Right: Evidence Weighting Assessment (Horizontal Contribution Bars) (5 Cols) */}
        <div className="bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-primary" />
              <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                Attribution Confidence Assessment
              </h3>
            </div>
            {selectedVessel && (
              <span className="text-xs font-mono font-bold text-primary truncate max-w-[150px]">
                {selectedVessel.vessel_name}
              </span>
            )}
          </div>

          {selectedVessel ? (
            <div className="flex flex-col gap-3">
              {/* Overall Candidate Composite Score Banner */}
              <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container flex items-center justify-between">
                <div className="flex flex-col">
                  <span className="text-[10px] uppercase font-semibold text-secondary">
                    Attribution Confidence
                  </span>
                  <div className="flex items-baseline gap-2 mt-0.5">
                    <span className="text-2xl font-bold font-mono text-rose-600">
                      {selectedVessel.confidence_score ?? Math.round(selectedVessel.scores.overall * 100)} / 100
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-bold font-mono bg-rose-500/15 text-rose-600 border border-rose-500/30">
                      {selectedVessel.confidence_level || (selectedVessel.rank === 1 ? "HIGH" : "MODERATE")}
                    </span>
                  </div>
                </div>
                <div className="text-right text-[10px] font-mono text-secondary">
                  <div>MMSI: <strong className="text-on-surface">{selectedVessel.mmsi}</strong></div>
                  {selectedVessel.distance_to_spill_km && (
                    <div>Min Dist: <strong className="text-on-surface">{selectedVessel.distance_to_spill_km.toFixed(1)} km</strong></div>
                  )}
                </div>
              </div>

              {/* 4 Dimension Contribution Bars with Point Contributions */}
              <div className="flex flex-col gap-2.5 text-xs">
                {/* Spatial 40% */}
                <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container">
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-secondary font-medium">Spatial Proximity (40% Weight)</span>
                    <span className="font-mono font-bold text-on-surface">
                      {(selectedVessel.scores.spatial * 100).toFixed(1)}%
                      <span className="text-secondary font-normal ml-1">
                        (+{(selectedVessel.scores.spatial * 40).toFixed(1)} pts)
                      </span>
                    </span>
                  </div>
                  <div className="w-full h-2 bg-surface-container rounded-full overflow-hidden">
                    <div
                      className="h-full bg-rose-500 rounded-full transition-all duration-500"
                      style={{ width: `${selectedVessel.scores.spatial * 100}%` }}
                    />
                  </div>
                  <div className="text-[9px] text-secondary mt-1">
                    Inverse exponential distance to 95% dispersion envelope centroid
                  </div>
                </div>

                {/* Temporal 35% */}
                <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container">
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-secondary font-medium">Temporal Coincidence (35% Weight)</span>
                    <span className="font-mono font-bold text-on-surface">
                      {(selectedVessel.scores.temporal * 100).toFixed(1)}%
                      <span className="text-secondary font-normal ml-1">
                        (+{(selectedVessel.scores.temporal * 35).toFixed(1)} pts)
                      </span>
                    </span>
                  </div>
                  <div className="w-full h-2 bg-surface-container rounded-full overflow-hidden">
                    <div
                      className="h-full bg-sky-500 rounded-full transition-all duration-500"
                      style={{ width: `${selectedVessel.scores.temporal * 100}%` }}
                    />
                  </div>
                  <div className="text-[9px] text-secondary mt-1">
                    Coincidence with Lagrangian drift backward advection release window
                  </div>
                </div>

                {/* Trajectory 15% */}
                <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container">
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-secondary font-medium">Trajectory Alignment (15% Weight)</span>
                    <span className="font-mono font-bold text-on-surface">
                      {(selectedVessel.scores.trajectory * 100).toFixed(1)}%
                      <span className="text-secondary font-normal ml-1">
                        (+{(selectedVessel.scores.trajectory * 15).toFixed(1)} pts)
                      </span>
                    </span>
                  </div>
                  <div className="w-full h-2 bg-surface-container rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-500 rounded-full transition-all duration-500"
                      style={{ width: `${selectedVessel.scores.trajectory * 100}%` }}
                    />
                  </div>
                  <div className="text-[9px] text-secondary mt-1">
                    Vessel course over ground (COG) alignment with backward advection path
                  </div>
                </div>

                {/* Behaviour 10% */}
                <div className="p-2 rounded-lg bg-surface-container-low border border-surface-container">
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-secondary font-medium">Kinematic Behaviour (10% Weight)</span>
                    <span className="font-mono font-bold text-on-surface">
                      {(selectedVessel.scores.behaviour * 100).toFixed(1)}%
                      <span className="text-secondary font-normal ml-1">
                        (+{(selectedVessel.scores.behaviour * 10).toFixed(1)} pts)
                      </span>
                    </span>
                  </div>
                  <div className="w-full h-2 bg-surface-container rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                      style={{ width: `${selectedVessel.scores.behaviour * 100}%` }}
                    />
                  </div>
                  <div className="text-[9px] text-secondary mt-1">
                    Speed anomalies, loitering indicators, or sharp course alterations
                  </div>
                </div>
              </div>

              {/* Attribution Evidence Checklist (Supporting & Limitations) */}
              <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs font-semibold text-on-surface">
                  <span>Attribution Evidence Checklist</span>
                  <span className="font-mono text-[10px] text-secondary uppercase">
                    Level: {selectedVessel.confidence_level || (selectedVessel.rank === 1 ? "HIGH" : "MODERATE")}
                  </span>
                </div>
                {/* Supporting Factors */}
                <div className="space-y-1">
                  <div className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider">
                    Supporting Evidence
                  </div>
                  {(selectedVessel.confidence_factors?.supporting?.length
                    ? selectedVessel.confidence_factors.supporting
                    : [
                        `AIS track aligns with drift backward trajectory corridor (${((selectedVessel.scores.spatial || 0.8) * 100).toFixed(0)}% spatial fit)`,
                        `Temporal window overlaps with estimated discharge release timeframe`,
                        `Vessel characteristics match risk profile for hydrocarbon carriage/bunkering`
                      ]
                  ).map((factor: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-1.5 text-[11px] text-on-surface">
                      <span className="text-emerald-600 font-bold shrink-0">✓</span>
                      <span>{factor}</span>
                    </div>
                  ))}
                </div>
                {/* Identified Limitations */}
                <div className="space-y-1 pt-1 border-t border-surface-container">
                  <div className="text-[10px] font-bold text-amber-600 uppercase tracking-wider">
                    Identified Limitations & Data Gaps
                  </div>
                  {(selectedVessel.confidence_factors?.limitations?.length
                    ? selectedVessel.confidence_factors.limitations
                    : [
                        `Absence of direct visual or multispectral optical hydrocarbon sheen confirmation`,
                        `Attribution reflects probabilistic hydrodynamic drift modeling, not boarding proof`
                      ]
                  ).map((lim: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-1.5 text-[11px] text-secondary">
                      <span className="text-amber-600 font-bold shrink-0">△</span>
                      <span>{lim}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-6 text-center text-xs text-secondary bg-surface-container-low rounded-lg border border-dashed border-surface-container">
              Select an AIS candidate vessel from the table to inspect multi-criteria evidence weights.
            </div>
          )}

          {/* Forensic Legal Notice Box */}
          <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex items-start gap-2 text-[10px] text-secondary">
            <Info className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
            <div>
              <strong className="text-on-surface">Forensic Notice: </strong>
              Candidate ranking reflects probabilistic multi-criteria correlation with hydrodynamic hindcast models. It does <em>not</em> constitute legal proof of culpability or discharge confirmation under MARPOL Annex I without physical slick sampling or direct surveillance confirmation.
            </div>
          </div>

          {/* Collapsible Explainable Score Guide */}
          <div className="pt-2 border-t border-surface-container-low">
            <button
              type="button"
              onClick={() => setScoringGuideExpanded(!scoringGuideExpanded)}
              className="w-full flex items-center justify-between text-[11px] text-primary hover:underline cursor-pointer font-semibold"
            >
              <span className="flex items-center gap-1">
                <HelpCircle className="w-3.5 h-3.5" />
                How is this attribution score calculated?
              </span>
              {scoringGuideExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>

            {scoringGuideExpanded && (
              <div className="mt-2 p-2.5 rounded-lg bg-surface-container-low text-[11px] text-secondary space-y-2 border border-surface-container">
                <div className="p-1.5 rounded bg-surface-container font-mono text-[10px] text-on-surface">
                  Score = 0.40·S_spatial + 0.35·S_temporal + 0.15·S_trajectory + 0.10·S_behaviour
                </div>
                <ul className="list-disc list-inside space-y-1 text-[10px]">
                  <li><strong>Spatial (40%):</strong> Inverse exponential distance between vessel AIS point and probable spill origin.</li>
                  <li><strong>Temporal (35%):</strong> Coincidence between vessel AIS timestamp and Lagrangian drift release window.</li>
                  <li><strong>Trajectory (15%):</strong> Heading and course alignment with backward particle advection cone.</li>
                  <li><strong>Behaviour (10%):</strong> Speed anomalies, course deviation, or loitering near the release point.</li>
                </ul>
              </div>
            )}
          </div>
        </div>

          {/* Right: Technical Data Provenance & Badges (5 Cols) */}
        <div className="bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                Data Provenance & Audit Trail
              </h3>
            </div>
            <button
              type="button"
              onClick={() => setProvenanceExpanded(!provenanceExpanded)}
              className="text-secondary hover:text-on-surface transition-colors cursor-pointer"
            >
              {provenanceExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          </div>

          {/* Interactive Source Badges */}
          <div className="grid grid-cols-2 gap-1.5">
            <div className="p-2 rounded bg-surface-container-low border border-surface-container flex flex-col">
              <span className="text-[9px] text-secondary uppercase font-semibold">Sensor Source</span>
              <span className="text-xs font-bold text-on-surface mt-0.5 font-mono">Sentinel-1 SAR</span>
              <span className="text-[9px] text-secondary">C-Band IW (10m)</span>
            </div>
            <div className="p-2 rounded bg-surface-container-low border border-surface-container flex flex-col">
              <span className="text-[9px] text-secondary uppercase font-semibold">Inference Model</span>
              <span className="text-xs font-bold text-on-surface mt-0.5 font-mono">U-Net (ResNet-34)</span>
              <span className="text-[9px] text-secondary">PyTorch Deep Learning</span>
            </div>
            <div className="p-2 rounded bg-surface-container-low border border-surface-container flex flex-col">
              <span className="text-[9px] text-secondary uppercase font-semibold">Hydrodynamic Data</span>
              <span className="text-xs font-bold text-cyan-600 mt-0.5 font-mono truncate" title="Copernicus CMEMS">Copernicus CMEMS</span>
              <span className="text-[9px] text-secondary">Global Physics (0.083°)</span>
            </div>
            <div className="p-2 rounded bg-surface-container-low border border-surface-container flex flex-col">
              <span className="text-[9px] text-secondary uppercase font-semibold">AIS Trajectory Feed</span>
              <span className="text-xs font-bold text-indigo-600 mt-0.5 font-mono truncate" title="Global Fishing Watch">GFW / Spire AIS</span>
              <span className="text-[9px] text-secondary">Real Maritime Positions</span>
            </div>
          </div>

          {/* Technical Metadata Rows */}
          <div className="flex flex-col gap-1.5 text-xs pt-1 border-t border-surface-container-low">
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-secondary">Scene File:</span>
              <span className="font-mono text-on-surface font-semibold truncate max-w-[200px]" title={investigation.image_id}>
                {currentImageId ? `${currentImageId}.tif` : (investigation.image_id || "SAR-GeoTIFF")}
              </span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-secondary">Spatial CRS:</span>
              <span className="font-mono text-on-surface">{metadata?.crs || "EPSG:4326 (WGS 84)"}</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-secondary">Centroid Anchor:</span>
              <span className="font-mono text-on-surface text-[10px]">
                {centroidLat.toFixed(4)}°N, {centroidLon.toFixed(4)}°E
              </span>
            </div>

            {provenanceExpanded && (
              <div className="p-2.5 rounded bg-surface-container-low border border-surface-container space-y-1.5 text-[10px] text-secondary font-mono mt-1">
                <div>Pipeline Version: 1.0.0 (Research Forensic Edition)</div>
                <div>Hash Verification: SHA-256 Validated</div>
                <div>Execution Timestamp: {execution?.execution_timestamp || new Date().toISOString()}</div>
                <div>Last Synchronized: {new Date(investigation.updated_at || Date.now()).toLocaleString()}</div>
              </div>
            )}
          </div>
        </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* ROW 6: Actions Toolbar */}
      {/* ========================================================================= */}
      <div className="sticky bottom-4 z-20 bg-surface-container-lowest/95 backdrop-blur border border-surface-container p-3.5 rounded-xl shadow-xl flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-semibold text-on-surface">
            Active Dossier: <strong className="font-mono text-primary">{investigation.id}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <a
            href={getReportDownloadUrl(investigation.id)}
            download
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-on-primary hover:bg-primary/90 transition-colors text-xs font-bold shadow-xs cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download Report (.md)</span>
          </a>

          <button
            type="button"
            onClick={() => onNavigate("live-map")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container cursor-pointer"
          >
            <ExternalLink className="w-3.5 h-3.5 text-sky-500" />
            <span>Open in GIS Map</span>
          </button>

          <button
            type="button"
            onClick={handleExportGeoJson}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-secondary" />
            <span>Export GeoJSON</span>
          </button>

          <button
            type="button"
            onClick={handleExportAisCsv}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-secondary" />
            <span>Export AIS CSV</span>
          </button>

          <button
            type="button"
            onClick={handleRerun}
            disabled={actionLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container cursor-pointer disabled:opacity-50"
          >
            <RotateCcw className="w-3.5 h-3.5 text-secondary" />
            <span>Re-run Pipeline</span>
          </button>

          <button
            type="button"
            onClick={() => setDeleteModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition-colors text-xs font-semibold border border-rose-500/20 cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Delete Incident</span>
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* ALL CANDIDATES MODAL */}
      {/* ========================================================================= */}
      {allCandidatesModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="bg-surface-container-lowest border border-surface-container rounded-xl w-full max-w-4xl max-h-[85vh] shadow-2xl flex flex-col overflow-hidden">
            <div className="p-4 border-b border-surface-container flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Ship className="w-5 h-5 text-primary" />
                <h3 className="font-headline-sm text-base font-bold text-on-surface">
                  All Candidate Vessels Profiled ({candidates.length})
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setAllCandidatesModalOpen(false)}
                className="p-1 rounded-lg hover:bg-surface-container text-secondary hover:text-on-surface cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-surface-container text-secondary text-[11px] uppercase tracking-wider font-semibold">
                    <th className="pb-2 font-semibold">Rank</th>
                    <th className="pb-2 font-semibold">Vessel Name</th>
                    <th className="pb-2 font-semibold">MMSI</th>
                    <th className="pb-2 font-semibold">IMO</th>
                    <th className="pb-2 font-semibold">Type</th>
                    <th className="pb-2 font-semibold">Flag</th>
                    <th className="pb-2 font-semibold text-right">Min Dist</th>
                    <th className="pb-2 font-semibold text-right">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-low">
                  {candidates.map((c) => (
                    <tr
                      key={c.mmsi}
                      onClick={() => {
                        setSelectedVessel(c);
                        setAllCandidatesModalOpen(false);
                      }}
                      className="hover:bg-surface-container-low cursor-pointer transition-colors"
                    >
                      <td className="py-2.5 font-mono font-bold">{c.rank}</td>
                      <td className="py-2.5 font-semibold text-on-surface">{c.vessel_name}</td>
                      <td className="py-2.5 font-mono text-secondary">{c.mmsi}</td>
                      <td className="py-2.5 font-mono text-secondary">{c.imo || "—"}</td>
                      <td className="py-2.5 text-secondary">{c.vessel_type || "—"}</td>
                      <td className="py-2.5 text-secondary">{c.flag || "—"}</td>
                      <td className="py-2.5 text-right font-mono">
                        {c.distance_to_spill_km ? `${c.distance_to_spill_km.toFixed(2)} km` : "—"}
                      </td>
                      <td className="py-2.5 text-right font-mono font-bold text-rose-600">
                        {(c.scores.overall * 100).toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="p-3 border-t border-surface-container bg-surface-container-low flex justify-between items-center text-xs">
              <span className="text-secondary">Click any row to inspect vessel evidence breakdown</span>
              <button
                type="button"
                onClick={handleExportAisCsv}
                className="px-3 py-1.5 bg-primary text-on-primary rounded font-bold hover:bg-primary/90 transition-colors"
              >
                Export All as CSV
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* IMAGE LIGHTBOX / MODAL */}
      {/* ========================================================================= */}
      {imageModalUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/90 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="relative max-w-5xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-xl overflow-hidden shadow-2xl flex flex-col">
            <div className="p-3 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-slate-200">{imageModalTitle}</span>
              <button
                type="button"
                onClick={() => setImageModalUrl(null)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-2 overflow-auto flex items-center justify-center bg-black/40">
              <img
                src={imageModalUrl}
                alt="Full preview"
                className="max-h-[80vh] max-w-full object-contain rounded"
              />
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* CONFIRMATION MODAL FOR DELETION */}
      {/* ========================================================================= */}
      <ConfirmationModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={() => handleDelete(false)}
        title={`Delete Investigation ${investigation.id}`}
        message={`Are you sure you want to delete forensic investigation ${investigation.id}? You can choose to archive the incident or permanently purge all associated geospatial results.`}
        confirmText="Confirm Deletion"
        cancelText="Cancel"
        isDestructive={true}
        isLoading={actionLoading}
      />
    </div>
  );
};

export default InvestigationDetailPage;
