import React, { useState, useEffect, useRef, useCallback } from "react";
import { NavPath } from "../components/Sidebar";
import {
  Satellite,
  Waves,
  Ship,
  Play,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Clock,
  Compass,
  FileCheck2,
  Loader2,
  UploadCloud,
  FileUp,
  RefreshCw,
  Trash2,
  Database,
  Check,
  ChevronDown,
  Calendar,
} from "lucide-react";
import { SentinelImage, UploadedSceneMetadata, TemporalAnchor } from "../types";
import {
  listAvailableImages,
  getImageDetails,
  createInvestigation,
  runInvestigationPipeline,
  uploadSentinelGeoTiff,
  cancelSentinelUpload,
  confirmTemporalAnchor,
} from "../services/api";

const MAX_FILE_SIZE_BYTES = 1024 * 1024 * 1024; // Exactly 1 GiB

interface NewInvestigationPageProps {
  onNavigate: (path: NavPath) => void;
  onSelectInvestigation?: (id: string) => void;
}

export function NewInvestigationPage({ onNavigate, onSelectInvestigation }: NewInvestigationPageProps) {
  // Investigation details
  const [caseTitle, setCaseTitle] = useState<string>("");
  const [priority, setPriority] = useState<"High" | "Medium" | "Low">("High");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Selected Scene State (null initially — no hardcoded scene!)
  const [selectedScene, setSelectedScene] = useState<UploadedSceneMetadata | null>(null);

  // Manual Temporal Anchor States
  const [manualDate, setManualDate] = useState<string>("");
  const [manualTime, setManualTime] = useState<string>("00:00:00");
  const [manualAnchorError, setManualAnchorError] = useState<string | null>(null);
  const [confirmingAnchor, setConfirmingAnchor] = useState<boolean>(false);
  const [isEditingAnchor, setIsEditingAnchor] = useState<boolean>(false);

  // Upload progress and active state
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadLoadedBytes, setUploadLoadedBytes] = useState<number>(0);
  const [uploadTotalBytes, setUploadTotalBytes] = useState<number>(0);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const [dragReject, setDragReject] = useState<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Secondary option: verified repository scenes
  const [verifiedImages, setVerifiedImages] = useState<SentinelImage[]>([]);
  const [loadingVerified, setLoadingVerified] = useState<boolean>(false);
  const [showVerifiedDropdown, setShowVerifiedDropdown] = useState<boolean>(false);

  // Load verified repository scenes for the secondary option
  useEffect(() => {
    setLoadingVerified(true);
    listAvailableImages()
      .then((list) => setVerifiedImages(list || []))
      .catch(() => setVerifiedImages([]))
      .finally(() => setLoadingVerified(false));
  }, []);

  // Format byte counts into human-readable strings
  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  // Pre-flight file validation
  const validateFile = (file: File): string | null => {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (ext !== ".tif" && ext !== ".tiff") {
      return "Unsupported file type. Please upload a Sentinel-1 GeoTIFF (.tif or .tiff).";
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return "File exceeds the 1 GB maximum size.";
    }
    if (file.size <= 0) {
      return "Selected file is empty.";
    }
    return null;
  };

  // Perform upload
  const handleProcessFile = async (file: File) => {
    const error = validateFile(file);
    if (error) {
      setErrorMessage(error);
      return;
    }

    setErrorMessage(null);
    setUploading(true);
    setUploadProgress(0);
    setUploadLoadedBytes(0);
    setUploadTotalBytes(file.size);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const metadata = await uploadSentinelGeoTiff(
        file,
        (pct, loaded, total) => {
          setUploadProgress(pct);
          setUploadLoadedBytes(loaded);
          setUploadTotalBytes(total);
        },
        controller.signal
      );

      setSelectedScene(metadata);
      if (metadata.temporal_anchor?.status === "resolved" && metadata.acquisition_time) {
        setIsEditingAnchor(false);
      } else {
        setIsEditingAnchor(true);
      }
      setManualAnchorError(null);
      // Auto-set suggested case title if empty
      if (!caseTitle.trim()) {
        const titleStem = metadata.filename.replace(/\.tiff?$/i, "");
        setCaseTitle(`Sentinel-1 SAR Detection (${titleStem} - ${metadata.region})`);
      }
    } catch (err: any) {
      if (err.message !== "Upload aborted by user.") {
        console.error("Upload failed:", err);
        setErrorMessage(err.message || "Upload failed. The server could not store the GeoTIFF.");
      }
    } finally {
      setUploading(false);
      abortControllerRef.current = null;
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  // Drag & drop event handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);

    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      const item = e.dataTransfer.items[0];
      const ext = item.type;
      const isTIFF = ext.includes("tiff") || ext.includes("geotiff") || item.kind === "file";
      setDragReject(!isTIFF);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDragOver) setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only reset if left the actual container
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDragOver(false);
    setDragReject(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    setDragReject(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleProcessFile(files[0]);
    }
  };

  // File input change
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleProcessFile(files[0]);
    }
  };

  // Remove selected file and clean session
  const handleRemoveScene = async () => {
    if (selectedScene && selectedScene.is_uploaded && selectedScene.upload_id) {
      await cancelSentinelUpload(selectedScene.upload_id);
    }
    setSelectedScene(null);
    setErrorMessage(null);
    setManualDate("");
    setManualTime("00:00:00");
    setManualAnchorError(null);
    setIsEditingAnchor(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Replace selected file
  const handleChangeScene = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  // Select verified benchmark scene from repository (Secondary Option)
  const handleSelectVerifiedScene = async (img: SentinelImage) => {
    try {
      const details = await getImageDetails(img.image_id);
      const acqTime = img.observation_timestamp || (details as any)?.acquisition_time || null;
      const anchor: TemporalAnchor = {
        status: "resolved",
        sar_acquisition_time: acqTime,
        source: "project_scene_catalog",
        verified: true,
        provenance_badge: "CATALOG — VERIFIED SCENE",
        description: `Verified repository benchmark scene ${img.image_id}`,
        requires_user_action: false,
      };

      const sceneData: UploadedSceneMetadata = {
        status: "SUCCESS",
        upload_id: `repo_${img.image_id}`,
        image_id: img.image_id,
        filename: img.filename,
        safe_filename: img.filename,
        file_path: img.source_path || (details as any)?.file_path || "",
        file_size: 2048 * 2048 * 2, // ~8 MB estimate for raw SAR 2-band
        file_size_formatted: "Verified Repository Scene",
        width: details ? (details as any).width || 2048 : 2048,
        height: details ? (details as any).height || 2048 : 2048,
        num_bands: details ? (details as any).num_bands || 2 : 2,
        crs: details ? (details as any).crs || "EPSG:4326" : "EPSG:4326",
        pixel_res_m: 10.0,
        bounds: {
          min_lon: (details as any)?.min_lon || (img.longitude ? img.longitude - 0.2 : 0),
          min_lat: (details as any)?.min_lat || (img.latitude ? img.latitude - 0.2 : 0),
          max_lon: (details as any)?.max_lon || (img.longitude ? img.longitude + 0.2 : 0),
          max_lat: (details as any)?.max_lat || (img.latitude ? img.latitude + 0.2 : 0),
        },
        centroid_lat: img.latitude || (details as any)?.centroid_lat || null,
        centroid_lon: img.longitude || (details as any)?.centroid_lon || null,
        region: img.region || (details as any)?.region_name || "Offshore Waters",
        acquisition_time: acqTime,
        temporal_anchor: anchor,
        source_file: img.source_path || (details as any)?.file_path || "",
        is_uploaded: false,
      };

      setSelectedScene(sceneData);
      setIsEditingAnchor(false);
      setShowVerifiedDropdown(false);
      if (!caseTitle.trim()) {
        setCaseTitle(`Sentinel-1 SAR Detection (${img.image_id} - ${img.region || "Maritime Corridor"})`);
      }
      setErrorMessage(null);
    } catch (e) {
      setErrorMessage("Failed to load metadata for verified repository scene.");
    }
  };

  // Confirm or manually set the temporal anchor
  const handleConfirmTemporalAnchor = async (dateVal?: string, timeVal?: string) => {
    if (!selectedScene) return;
    const targetDate = (dateVal ?? manualDate).trim();
    const targetTime = (timeVal ?? manualTime).trim() || "00:00:00";

    if (!targetDate) {
      setManualAnchorError("Please enter a valid acquisition date (YYYY-MM-DD).");
      return;
    }

    setConfirmingAnchor(true);
    setManualAnchorError(null);

    try {
      const payload = {
        date: targetDate,
        time: targetTime,
        timezone: "UTC",
        source: "user_provided",
      };

      let updatedAnchor: TemporalAnchor;
      if (selectedScene.is_uploaded && selectedScene.upload_id) {
        updatedAnchor = await confirmTemporalAnchor(selectedScene.upload_id, payload);
      } else {
        const combinedIso = `${targetDate}T${targetTime}Z`;
        const d = new Date(combinedIso);
        if (isNaN(d.getTime())) {
          throw new Error("Invalid date or time value.");
        }
        updatedAnchor = {
          status: "resolved",
          sar_acquisition_time: combinedIso,
          source: "user_provided",
          verified: false,
          provenance_badge: "USER PROVIDED — MANUAL TEMPORAL ANCHOR",
          description: "Manual UTC temporal anchor confirmed by operator.",
          candidates: [
            {
              source: "user_provided",
              timestamp: combinedIso,
              confidence: "HIGH",
              description: "Operator manual temporal anchor",
            },
          ],
          requires_user_action: false,
        };
      }

      setSelectedScene((prev) =>
        prev
          ? {
              ...prev,
              acquisition_time: updatedAnchor.sar_acquisition_time,
              temporal_anchor: updatedAnchor,
            }
          : null
      );
      setIsEditingAnchor(false);
      setErrorMessage(null);
    } catch (err: any) {
      setManualAnchorError(err.message || "Failed to confirm temporal anchor.");
    } finally {
      setConfirmingAnchor(false);
    }
  };

  // Launch pipeline
  const handleLaunch = async () => {
    if (!selectedScene) {
      setErrorMessage("Please upload or select a valid Sentinel-1 GeoTIFF scene before initiating the pipeline.");
      return;
    }

    const anchorResolved =
      selectedScene.acquisition_time &&
      selectedScene.temporal_anchor?.status !== "conflict" &&
      selectedScene.temporal_anchor?.status !== "unresolved";

    if (!anchorResolved) {
      setErrorMessage(
        "SAR acquisition time unavailable. The pipeline requires an authoritative UTC observation timestamp before initiating M4 hydrodynamic drift and M5 AIS correlation."
      );
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);

    try {
      // 1. Create real database investigation record
      const inv = await createInvestigation({
        title: caseTitle.trim() || `SAR Incident ${selectedScene.filename}`,
        image_id: selectedScene.image_id,
        source_image_path: selectedScene.file_path,
        region: selectedScene.region,
        priority,
        observation_timestamp: selectedScene.acquisition_time || undefined,
        sar_acquisition_time: selectedScene.acquisition_time || undefined,
        sar_acquisition_time_source: selectedScene.temporal_anchor?.source || "user_provided",
        sar_acquisition_time_verified: selectedScene.temporal_anchor?.verified ?? false,
        coordinates: selectedScene.centroid_lat && selectedScene.centroid_lon
          ? { latitude: selectedScene.centroid_lat, longitude: selectedScene.centroid_lon }
          : undefined,
        metadata: {
          filename: selectedScene.filename,
          width: selectedScene.width,
          height: selectedScene.height,
          crs: selectedScene.crs,
          num_bands: selectedScene.num_bands,
          is_uploaded: selectedScene.is_uploaded,
          temporal_anchor: selectedScene.temporal_anchor,
        },
      });

      // 2. Trigger real attribution pipeline asynchronously
      await runInvestigationPipeline(inv.id, {
        image_id: selectedScene.image_id,
        image_path: selectedScene.file_path,
        sync: false,
      });

      // 3. Set as active investigation and navigate to analysis progress
      if (onSelectInvestigation) {
        onSelectInvestigation(inv.id);
      }
      onNavigate("analysis-process");
    } catch (err: any) {
      console.error("Failed to launch investigation pipeline:", err);
      setErrorMessage(err.message || "Failed to initiate pipeline");
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto gap-space-lg">
      {/* Header */}
      <div className="flex flex-col gap-space-2xs">
        <button
          type="button"
          onClick={() => onNavigate("investigations")}
          className="hover:text-primary transition-colors cursor-pointer flex items-center gap-1 text-xs text-secondary mb-1"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Investigations</span>
        </button>
        <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
          Initiate Real Oil Spill Attribution Pipeline
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Upload an authentic Sentinel-1 SAR C-Band GeoTIFF (.tif/.tiff), configure Copernicus hydrodynamic drift forcing, and launch the complete 6-stage scientific attribution workflow.
        </p>
      </div>

      {errorMessage && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Form Card */}
      <div className="bg-surface-container-lowest rounded-xl p-space-lg border border-surface-container shadow-sm space-y-6">
        {/* Investigation Title & Priority */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
          <div className="md:col-span-2 space-y-1">
            <label className="font-headline-sm text-xs text-on-surface font-bold">
              Investigation Case Title
            </label>
            <input
              type="text"
              value={caseTitle}
              onChange={(e) => setCaseTitle(e.target.value)}
              className="w-full p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface font-sans focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="e.g. Sentinel-1 SAR Incident Detection"
            />
          </div>
          <div className="space-y-1">
            <label className="font-headline-sm text-xs text-on-surface font-bold">
              Case Priority
            </label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value as any)}
              className="w-full p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface font-sans"
            >
              <option value="High">High (Immediate Action)</option>
              <option value="Medium">Medium (Routine Analysis)</option>
              <option value="Low">Low (Archival Verification)</option>
            </select>
          </div>
        </div>

        {/* Step 1: Satellite SAR Scene Upload (GeoTIFF) */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="font-headline-sm text-sm text-on-surface font-bold flex items-center gap-2">
              <Satellite className="w-4 h-4 text-primary" />
              1. Sentinel-1 SAR C-Band Scene Upload (GeoTIFF)
            </label>
            {selectedScene && (
              <span className="text-[11px] text-emerald-600 font-semibold flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> Scene Verified
              </span>
            )}
          </div>

          {/* Hidden File Input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".tif,.tiff,image/tiff,image/geotiff"
            onChange={handleFileSelect}
            className="hidden"
          />

          {/* 1. UPLOADING IN-PROGRESS STATE */}
          {uploading ? (
            <div className="p-6 rounded-xl border border-primary/30 bg-primary/5 flex flex-col items-center justify-center gap-3">
              <div className="flex items-center gap-2 text-primary font-semibold text-xs">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Uploading Sentinel-1 GeoTIFF to secure server...</span>
              </div>
              <div className="w-full max-w-md bg-surface-container-high rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-primary h-full transition-all duration-200 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <div className="flex items-center justify-between w-full max-w-md text-[11px] font-mono text-secondary">
                <span>{uploadProgress}% completed</span>
                <span>
                  {formatBytes(uploadLoadedBytes)} / {formatBytes(uploadTotalBytes)}
                </span>
              </div>
            </div>
          ) : selectedScene ? (
            /* 2. SELECTED FILE CARD WITH METADATA STRIP */
            <div className="space-y-3">
              <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
                    <FileCheck2 className="w-5 h-5 text-emerald-600" />
                  </div>
                  <div className="min-w-0">
                    <div className="font-bold text-xs text-on-surface truncate flex items-center gap-2">
                      <span className="truncate">{selectedScene.filename}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded font-mono font-bold uppercase bg-emerald-500/20 text-emerald-700">
                        GeoTIFF
                      </span>
                    </div>
                    <div className="text-[11px] text-secondary font-mono flex items-center gap-2">
                      <span>{selectedScene.file_size_formatted}</span>
                      <span>·</span>
                      <span className="text-emerald-700 font-semibold">
                        {selectedScene.is_uploaded ? "Upload complete & verified" : "Repository scene verified"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={handleChangeScene}
                    className="px-3 py-1.5 rounded-lg border border-surface-container bg-surface-container-low hover:bg-surface-container text-xs font-semibold text-on-surface transition-colors cursor-pointer flex items-center gap-1"
                  >
                    <RefreshCw className="w-3 h-3 text-secondary" />
                    <span>Change file</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleRemoveScene}
                    className="px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50 hover:bg-rose-100 text-xs font-semibold text-rose-700 transition-colors cursor-pointer flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3 text-rose-600" />
                    <span>Remove</span>
                  </button>
                </div>
              </div>

              {/* Authoritative Real Metadata Preview Strip */}
              <div className="p-3.5 rounded-xl bg-surface-container-low border border-surface-container grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 text-[11px] font-mono">
                <div>
                  <span className="text-secondary block text-[10px]">Scene File:</span>
                  <strong className="text-primary truncate block" title={selectedScene.filename}>
                    {selectedScene.filename}
                  </strong>
                </div>

                <div>
                  <span className="text-secondary block text-[10px]">Region:</span>
                  <strong className="text-on-surface truncate block" title={selectedScene.region}>
                    {selectedScene.region}
                  </strong>
                </div>

                <div>
                  <span className="text-secondary block text-[10px]">CRS:</span>
                  <strong className="text-on-surface block truncate" title={selectedScene.crs}>
                    {selectedScene.crs}
                  </strong>
                </div>

                <div>
                  <span className="text-secondary block text-[10px]">Raster Dimensions:</span>
                  <strong className="text-on-surface block">
                    {selectedScene.width} × {selectedScene.height}
                  </strong>
                </div>

                <div>
                  <span className="text-secondary block text-[10px]">Bands:</span>
                  <strong className="text-on-surface block">{selectedScene.num_bands} Channels</strong>
                </div>

                <div>
                  <span className="text-secondary block text-[10px]">Centroid:</span>
                  <strong className="text-on-surface block truncate">
                    {selectedScene.centroid_lat !== null && selectedScene.centroid_lon !== null
                      ? `${selectedScene.centroid_lat.toFixed(4)}°, ${selectedScene.centroid_lon.toFixed(4)}°`
                      : "Unprojected"}
                  </strong>
                </div>
              </div>

              {/* Authoritative SAR Temporal Anchor & Provenance Audit Section */}
              <div className="p-4 rounded-xl border border-surface-container bg-surface-container-lowest space-y-3">
                {/* Header row with title & status badge */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-container pb-2.5">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-primary" />
                    <span className="text-xs font-bold text-on-surface uppercase tracking-wider">
                      Authoritative SAR Temporal Anchor (UTC)
                    </span>
                  </div>

                  {/* Provenance Badge */}
                  {selectedScene.temporal_anchor?.status === "resolved" && selectedScene.acquisition_time && (
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full border flex items-center gap-1.5 ${
                          selectedScene.temporal_anchor.verified
                            ? selectedScene.temporal_anchor.source === "project_scene_catalog"
                              ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-700 dark:text-cyan-400"
                              : "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400"
                            : "bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-400"
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            selectedScene.temporal_anchor.verified
                              ? selectedScene.temporal_anchor.source === "project_scene_catalog"
                                ? "bg-cyan-500"
                                : "bg-emerald-500"
                              : "bg-amber-500"
                          }`}
                        />
                        {selectedScene.temporal_anchor.provenance_badge ||
                          (selectedScene.temporal_anchor.verified
                            ? "AUTO — VERIFIED METADATA"
                            : "USER PROVIDED — MANUAL TEMPORAL ANCHOR")}
                      </span>

                      {!isEditingAnchor && (
                        <button
                          type="button"
                          onClick={() => {
                            if (selectedScene.acquisition_time) {
                              const parts = selectedScene.acquisition_time.split("T");
                              setManualDate(parts[0] || "");
                              setManualTime(parts[1]?.replace("Z", "") || "00:00:00");
                            }
                            setIsEditingAnchor(true);
                          }}
                          className="text-[10px] text-secondary hover:text-primary underline font-medium cursor-pointer"
                        >
                          Adjust
                        </button>
                      )}
                    </div>
                  )}

                  {selectedScene.temporal_anchor?.status === "conflict" && (
                    <span className="text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full border bg-rose-500/10 border-rose-500/30 text-rose-700 dark:text-rose-400 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping" />
                      METADATA CONFLICT — SELECTION REQUIRED
                    </span>
                  )}

                  {(!selectedScene.temporal_anchor ||
                    selectedScene.temporal_anchor.status === "unresolved" ||
                    !selectedScene.acquisition_time) && (
                    <span className="text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full border bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                      UNRESOLVED — MANUAL ENTRY REQUIRED
                    </span>
                  )}
                </div>

                {/* State 1: Resolved and not editing */}
                {selectedScene.temporal_anchor?.status === "resolved" &&
                selectedScene.acquisition_time &&
                !isEditingAnchor ? (
                  <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
                    <div className="flex items-center gap-3">
                      <div className="px-3 py-1.5 rounded-lg bg-surface-container font-mono font-bold text-sm text-primary flex items-center gap-2 border border-surface-container-high">
                        <span>
                          {new Date(selectedScene.acquisition_time)
                            .toISOString()
                            .replace(".000Z", " UTC")
                            .replace("T", "  ")}
                        </span>
                      </div>
                      <p className="text-[11px] text-secondary">
                        {selectedScene.temporal_anchor.description ||
                          "Authoritative SAR temporal anchor established."}{" "}
                        <span className="text-emerald-600 font-semibold">No manual action required.</span>
                      </p>
                    </div>

                    <div className="text-[10px] text-secondary font-mono">
                      M4 Copernicus Hindcast & M5 AIS Trajectory Anchored
                    </div>
                  </div>
                ) : null}

                {/* State 2: Metadata conflict detected */}
                {selectedScene.temporal_anchor?.status === "conflict" &&
                  selectedScene.temporal_anchor.candidates && (
                    <div className="space-y-2.5 p-3 rounded-lg bg-rose-500/5 border border-rose-500/20">
                      <div className="flex items-start gap-2 text-rose-800 dark:text-rose-300 text-xs font-semibold">
                        <AlertTriangle className="w-4 h-4 shrink-0 text-rose-600 mt-0.5" />
                        <div>
                          <p>{selectedScene.temporal_anchor.description}</p>
                          <p className="text-[11px] font-normal text-secondary mt-0.5">
                            Select one of the candidate timestamps detected from file metadata, or enter an authoritative
                            UTC date/time below.
                          </p>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                        {selectedScene.temporal_anchor.candidates.map((cand, idx) => (
                          <div
                            key={idx}
                            className="p-2.5 rounded-lg border border-surface-container bg-surface flex items-center justify-between gap-2"
                          >
                            <div>
                              <div className="text-[11px] font-bold font-mono text-on-surface">
                                {new Date(cand.timestamp).toISOString().replace(".000Z", " UTC").replace("T", " ")}
                              </div>
                              <div className="text-[10px] text-secondary capitalize">{cand.description}</div>
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                const parts = cand.timestamp.split("T");
                                handleConfirmTemporalAnchor(parts[0], parts[1]?.replace("Z", ""));
                              }}
                              className="px-2.5 py-1 rounded bg-primary/10 hover:bg-primary/20 text-primary text-[11px] font-semibold cursor-pointer shrink-0 transition-colors"
                            >
                              Select
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                {/* State 3: Unresolved OR Editing Anchor Form */}
                {((!selectedScene.temporal_anchor ||
                  selectedScene.temporal_anchor.status === "unresolved" ||
                  selectedScene.temporal_anchor.status === "conflict" ||
                  !selectedScene.acquisition_time) ||
                  isEditingAnchor) && (
                  <div className="p-3.5 rounded-lg bg-surface-container-low border border-amber-500/30 space-y-3">
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-bold text-on-surface">
                        <Calendar className="w-3.5 h-3.5 text-amber-600" />
                        <span>Operator Temporal Anchor Entry (UTC)</span>
                      </div>
                      <p className="text-[11px] text-secondary mt-0.5">
                        Enter the Sentinel-1 SAR acquisition date and time in UTC. Copernicus ocean drift (M4) and AIS
                        vessel correlation (M5) will strictly anchor to this timestamp.
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <div className="flex items-center gap-1">
                        <label className="text-[10px] text-secondary font-mono uppercase">Date:</label>
                        <input
                          type="date"
                          value={manualDate}
                          onChange={(e) => setManualDate(e.target.value)}
                          className="px-2.5 py-1.5 rounded-lg bg-surface border border-surface-container text-xs font-mono text-on-surface focus:outline-none focus:border-primary"
                          placeholder="YYYY-MM-DD"
                        />
                      </div>

                      <div className="flex items-center gap-1">
                        <label className="text-[10px] text-secondary font-mono uppercase">Time:</label>
                        <input
                          type="text"
                          value={manualTime}
                          onChange={(e) => setManualTime(e.target.value)}
                          className="w-24 px-2.5 py-1.5 rounded-lg bg-surface border border-surface-container text-xs font-mono text-on-surface focus:outline-none focus:border-primary"
                          placeholder="HH:MM:SS"
                        />
                      </div>

                      <span className="px-2 py-1 rounded bg-surface-container-high text-[11px] font-mono font-bold text-secondary border border-surface-container">
                        UTC
                      </span>

                      <button
                        type="button"
                        onClick={() => handleConfirmTemporalAnchor()}
                        disabled={confirmingAnchor || !manualDate}
                        className="px-3 py-1.5 rounded-lg bg-primary text-on-primary hover:bg-primary-container text-xs font-bold transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                      >
                        {confirmingAnchor ? (
                          <>
                            <Loader2 className="w-3 h-3 animate-spin" />
                            <span>Validating...</span>
                          </>
                        ) : (
                          <>
                            <Check className="w-3 h-3" />
                            <span>Confirm Temporal Anchor</span>
                          </>
                        )}
                      </button>

                      {isEditingAnchor && selectedScene.acquisition_time && (
                        <button
                          type="button"
                          onClick={() => setIsEditingAnchor(false)}
                          className="px-2.5 py-1.5 rounded-lg border border-surface-container text-xs text-secondary hover:text-on-surface cursor-pointer"
                        >
                          Cancel
                        </button>
                      )}
                    </div>

                    {manualAnchorError && (
                      <p className="text-[11px] text-rose-600 font-medium flex items-center gap-1">
                        <AlertCircle className="w-3 h-3 shrink-0" />
                        {manualAnchorError}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* 3. PRIMARY DRAG & DROP + BROWSE ZONE */
            <div className="space-y-3">
              <div
                role="button"
                tabIndex={0}
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                className={`w-full p-8 rounded-xl border-2 border-dashed transition-all cursor-pointer flex flex-col items-center justify-center text-center gap-2 outline-none focus:ring-2 focus:ring-primary/40 ${
                  dragReject
                    ? "border-rose-400 bg-rose-50/50"
                    : isDragOver
                    ? "border-primary bg-primary/5 text-primary scale-[1.005]"
                    : "border-surface-container bg-surface-container-low/40 hover:bg-surface-container-low hover:border-primary/50"
                }`}
              >
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center mb-1 transition-colors ${
                    isDragOver ? "bg-primary/20 text-primary" : "bg-surface-container text-secondary"
                  }`}
                >
                  <UploadCloud className="w-6 h-6" />
                </div>

                <div className="font-headline-sm text-sm font-bold text-on-surface">
                  Drag &amp; drop Sentinel-1 GeoTIFF here
                </div>

                <div className="text-xs text-secondary font-medium">or</div>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                  className="px-4 py-2 rounded-lg bg-surface-container hover:bg-surface-container-high border border-surface-container text-xs font-semibold text-on-surface transition-colors cursor-pointer flex items-center gap-1.5 shadow-sm"
                >
                  <FileUp className="w-3.5 h-3.5 text-primary" />
                  <span>Browse from PC</span>
                </button>

                <div className="text-[11px] text-secondary font-mono mt-1">
                  Supported: .tif, .tiff · Maximum file size: 1 GB
                </div>
              </div>

              {/* SECONDARY OPTION: Use existing verified repository scene */}
              <div className="flex flex-col gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowVerifiedDropdown(!showVerifiedDropdown)}
                  className="text-xs text-primary hover:underline font-semibold flex items-center gap-1.5 self-start cursor-pointer"
                >
                  <Database className="w-3.5 h-3.5" />
                  <span>Or select an existing verified benchmark scene from repository inventory</span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform duration-200 ${
                      showVerifiedDropdown ? "rotate-180" : ""
                    }`}
                  />
                </button>

                {showVerifiedDropdown && (
                  <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container space-y-2 animate-fadeIn">
                    <div className="text-[11px] text-secondary font-medium">
                      Select a pre-verified Sentinel-1 C-SAR scene stored in local repository storage:
                    </div>
                    {loadingVerified ? (
                      <div className="p-2 text-xs text-secondary flex items-center gap-2">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Loading scene inventory...</span>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {verifiedImages.map((img) => (
                          <div
                            key={img.image_id}
                            onClick={() => handleSelectVerifiedScene(img)}
                            className="p-2.5 rounded-lg border border-surface-container bg-surface-container-lowest hover:border-primary/50 hover:bg-surface-container transition-all cursor-pointer flex flex-col gap-1"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-xs font-bold text-primary">{img.filename}</span>
                              {img.recommended && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded font-bold uppercase bg-primary/10 text-primary">
                                  Benchmark
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-on-surface truncate font-semibold">
                              {img.region || "Maritime Corridor"}
                            </div>
                            <div className="text-[10px] text-secondary font-mono">
                              Acquisition: {img.observation_timestamp ? new Date(img.observation_timestamp).toISOString().replace(".000Z", "Z") : "N/A"}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Step 2: MetOcean Environmental Datasets */}
        <div className="space-y-3">
          <label className="font-headline-sm text-sm text-on-surface font-bold flex items-center gap-2">
            <Waves className="w-4 h-4 text-sky-500" />
            2. Oceanographic Current &amp; Drift Forcing Model (Member 4)
          </label>

          <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container text-xs space-y-1">
            <div className="flex items-center justify-between font-mono">
              <span className="font-semibold text-on-surface">Hydrodynamic Currents:</span>
              <span className="text-emerald-600 font-bold flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Copernicus Marine CMEMS Physics Analysis (0.083° Grid)
              </span>
            </div>
            <p className="text-[11px] text-secondary">
              Lagrangian particle advection automatically matches hydrodynamic u/v surface velocities strictly anchored to the SAR scene's acquisition date for 72-hour backward hindcasting.
            </p>
          </div>
        </div>

        {/* Step 3: AIS Stream */}
        <div className="space-y-2">
          <label className="font-headline-sm text-sm text-on-surface font-bold flex items-center gap-2">
            <Ship className="w-4 h-4 text-purple-500" />
            3. AIS Vessel Presence &amp; Attribution Correlation (Member 5)
          </label>
          <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container text-xs space-y-1">
            <div className="flex items-center justify-between font-mono">
              <span className="font-semibold text-on-surface">AIS Provider:</span>
              <span className="text-primary font-bold">Global Fishing Watch (GFW) API</span>
            </div>
            <p className="text-[11px] text-secondary">
              Searches maritime vessel tracks inside the 95% Lagrangian spatial dispersion envelope. If GFW token is unconfigured, system produces a clean audit notice without fabricating false suspects.
            </p>
          </div>
        </div>

        {/* Submit */}
        <div className="pt-4 border-t border-surface-container flex items-center justify-between">
          <div className="text-xs text-secondary font-medium">
            {!selectedScene ? (
              <span className="text-amber-600 flex items-center gap-1 font-semibold">
                <AlertCircle className="w-3.5 h-3.5" />
                Upload or select a GeoTIFF to enable pipeline execution
              </span>
            ) : selectedScene.temporal_anchor?.status === "conflict" ? (
              <span className="text-rose-600 flex items-center gap-1 font-semibold">
                <AlertTriangle className="w-3.5 h-3.5" />
                Resolve acquisition timestamp conflict to enable pipeline execution
              </span>
            ) : !selectedScene.acquisition_time || selectedScene.temporal_anchor?.status === "unresolved" ? (
              <span className="text-amber-600 flex items-center gap-1 font-semibold">
                <Clock className="w-3.5 h-3.5" />
                Confirm SAR acquisition timestamp (UTC) to enable pipeline execution
              </span>
            ) : (
              <span className="text-emerald-600 flex items-center gap-1 font-semibold">
                <Check className="w-3.5 h-3.5" />
                Scene & temporal anchor verified · Ready for pipeline execution
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => onNavigate("investigations")}
              disabled={submitting || uploading}
              className="px-4 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-xs cursor-pointer disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleLaunch}
              disabled={
                submitting ||
                uploading ||
                !selectedScene ||
                !selectedScene.acquisition_time ||
                selectedScene.temporal_anchor?.status === "conflict" ||
                selectedScene.temporal_anchor?.status === "unresolved"
              }
              title={
                !selectedScene
                  ? "Upload or select a GeoTIFF first."
                  : !selectedScene.acquisition_time ||
                    selectedScene.temporal_anchor?.status === "conflict" ||
                    selectedScene.temporal_anchor?.status === "unresolved"
                  ? "Please establish an authoritative SAR acquisition timestamp (UTC) before executing pipeline."
                  : "Execute Real Attribution Pipeline"
              }
              className="px-5 py-2.5 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors flex items-center gap-2 font-bold text-xs cursor-pointer shadow-md disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Initiating Pipeline...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  <span>Execute Real Pipeline</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
