import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { EvidenceItem, Investigation } from "../types";
import {
  getInvestigations,
  getInvestigationEvidence,
  getEvidenceBundleDownloadUrl,
  getArtifactDownloadUrl,
  verifyArtifactIntegrity,
} from "../services/api";
import { useToast } from "../components/ToastNotification";
import {
  FolderArchive,
  FileCode,
  FileSpreadsheet,
  FileText,
  Image,
  Download,
  CheckCircle2,
  XCircle,
  HardDrive,
  RefreshCw,
  Layers,
  ShieldCheck,
  AlertTriangle,
  Copy,
  Check,
  Package,
} from "lucide-react";

interface EvidenceLibraryPageProps {
  onNavigate: (path: NavPath) => void;
  activeInvestigationId?: string | null;
  onSelectInvestigation?: (id: string) => void;
}

export function EvidenceLibraryPage({
  onNavigate,
  activeInvestigationId,
  onSelectInvestigation,
}: EvidenceLibraryPageProps) {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [selectedId, setSelectedId] = useState<string>(activeInvestigationId || "");
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifyingType, setVerifyingType] = useState<string | null>(null);
  const [verifiedMap, setVerifiedMap] = useState<Record<string, { verified: boolean; sha256?: string }>>({});
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const { showToast } = useToast();

  useEffect(() => {
    getInvestigations().then((list) => {
      setInvestigations(list);
      if (!selectedId && list.length > 0) {
        setSelectedId(list[0].id);
      }
    });
  }, []);

  const loadEvidence = (id: string) => {
    if (!id) return;
    setLoading(true);
    getInvestigationEvidence(id)
      .then((items) => setEvidenceList(items))
      .catch((err) => showToast("error", "Failed to load evidence files: " + err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (selectedId) {
      loadEvidence(selectedId);
      setVerifiedMap({});
    }
  }, [selectedId]);

  const handleSelectCase = (id: string) => {
    setSelectedId(id);
    if (onSelectInvestigation) onSelectInvestigation(id);
  };

  const handleVerify = async (item: EvidenceItem) => {
    const artType = item.artifact_type || item.name;
    setVerifyingType(artType);
    try {
      const res = await verifyArtifactIntegrity(selectedId, artType);
      if (res.verified) {
        setVerifiedMap((prev) => ({
          ...prev,
          [artType]: { verified: true, sha256: res.sha256 },
        }));
        showToast("success", `Integrity verified for ${item.name} (${res.byte_size} bytes, SHA-256 match)`);
      } else {
        setVerifiedMap((prev) => ({
          ...prev,
          [artType]: { verified: false },
        }));
        showToast("error", `Integrity check failed: ${res.message || "File mismatch or missing"}`);
      }
    } catch (err: any) {
      showToast("error", `Verification failed: ${err.message}`);
    } finally {
      setVerifyingType(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(text);
    showToast("info", "SHA-256 hash copied to clipboard");
    setTimeout(() => setCopiedHash(null), 2500);
  };

  const formatFileSize = (bytes: number) => {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const getFileIcon = (category: string, previewType: string) => {
    if (previewType === "image" || category === "SATELLITE" || category === "SEGMENTATION") {
      return <Image className="w-5 h-5 text-indigo-500" />;
    }
    if (previewType === "geojson" || previewType === "json" || category === "GIS") {
      return <FileCode className="w-5 h-5 text-emerald-500" />;
    }
    if (previewType === "table" || category === "AIS_ATTRIBUTION") {
      return <FileSpreadsheet className="w-5 h-5 text-amber-500" />;
    }
    if (category === "LEGAL_REPORT" || previewType === "text") {
      return <FileText className="w-5 h-5 text-rose-500" />;
    }
    return <Layers className="w-5 h-5 text-primary" />;
  };

  const totalBytes = evidenceList.reduce((acc, item) => acc + (item.file_size_bytes || 0), 0);
  const availableCount = evidenceList.filter((item) => item.status === "AVAILABLE").length;
  const bundleUrl = selectedId ? getEvidenceBundleDownloadUrl(selectedId) : "#";

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary uppercase tracking-wider">Forensic Custody Chain</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold flex items-center gap-2">
            <FolderArchive className="w-6 h-6 text-primary" />
            Evidence Library &amp; Artifacts
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Verified filesystem records, raw radar GeoTIFFs, vector polygons, Lagrangian particle grids, and prosecution dossiers.
          </p>
        </div>

        {/* Controls: Case Selector & Bundle Download */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-surface-container-lowest p-2 rounded-xl border border-surface-container shadow-xs">
            <span className="text-xs font-semibold text-secondary px-1">Case:</span>
            <select
              value={selectedId}
              onChange={(e) => handleSelectCase(e.target.value)}
              aria-label="Select investigation case"
              className="bg-surface-container text-xs text-on-surface font-mono font-bold px-3 py-1.5 rounded-lg border border-surface-container focus:outline-none"
            >
              {investigations.map((inv) => (
                <option key={inv.id} value={inv.id}>
                  {inv.id} — {inv.title}
                </option>
              ))}
            </select>
          </div>

          {availableCount > 0 ? (
            <a
              href={bundleUrl}
              download={`OILTRACE_${selectedId}_Evidence_Bundle.zip`}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-on-primary hover:bg-primary/90 text-xs font-bold shadow-sm transition-colors"
            >
              <Package className="w-4 h-4" />
              <span>Download Evidence Bundle (.ZIP)</span>
            </a>
          ) : (
            <button
              disabled
              title="No available evidence files to bundle"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-surface-container text-secondary/60 cursor-not-allowed text-xs font-bold border border-surface-container"
            >
              <Package className="w-4 h-4" />
              <span>Bundle Unavailable</span>
            </button>
          )}

          <button
            onClick={() => loadEvidence(selectedId)}
            className="p-2.5 rounded-xl bg-surface-container-lowest border border-surface-container hover:bg-surface-container text-on-surface-variant transition-colors"
            title="Refresh Artifact Status"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-primary" : ""}`} />
          </button>
        </div>
      </div>

      {/* Storage Summary Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-md">
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Total Evidence Artifacts
            </div>
            <div className="text-xl font-bold text-on-surface mt-1 font-mono">
              {evidenceList.length} Files
            </div>
          </div>
          <Layers className="w-8 h-8 text-primary opacity-40" />
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Verified on Disk
            </div>
            <div className="text-xl font-bold text-emerald-600 mt-1 font-mono">
              {availableCount} of {evidenceList.length} Available
            </div>
          </div>
          <CheckCircle2 className="w-8 h-8 text-emerald-500 opacity-40" />
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Cumulative Storage Footprint
            </div>
            <div className="text-xl font-bold text-indigo-600 mt-1 font-mono">
              {formatFileSize(totalBytes)}
            </div>
          </div>
          <HardDrive className="w-8 h-8 text-indigo-500 opacity-40" />
        </div>
      </div>

      {/* Artifacts Table */}
      <div className="bg-surface-container-lowest rounded-xl border border-surface-container shadow-sm overflow-hidden">
        <div className="p-4 border-b border-surface-container flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-bold text-xs text-on-surface uppercase tracking-wider">
              Verified Pipeline Artifacts for
            </span>
            <span className="font-mono text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">
              {selectedId || "N/A"}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-secondary font-mono">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>Cryptographic SHA-256 integrity check enabled for each artifact</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-container-low border-b border-surface-container text-secondary font-mono uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Artifact Details</th>
                <th className="px-4 py-3">Storage Path</th>
                <th className="px-4 py-3">Provenance</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">SHA-256 Digest</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-low">
              {evidenceList.map((item, idx) => {
                const isAvail = item.status === "AVAILABLE";
                const artKey = item.artifact_type || item.name;
                const isVerifying = verifyingType === artKey;
                const verState = verifiedMap[artKey];
                const downloadUrl =
                  item.download_url ||
                  (item.artifact_type ? getArtifactDownloadUrl(selectedId, item.artifact_type) : null);

                return (
                  <tr key={`${item.file_name}-${idx}`} className="hover:bg-surface-container-low/50">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        {getFileIcon(item.category, item.preview_type)}
                        <span className="font-mono font-bold text-[10px] text-secondary uppercase">
                          {item.category}
                        </span>
                      </div>
                    </td>

                    <td className="px-4 py-3 max-w-xs">
                      <span className="font-semibold text-on-surface block">{item.name}</span>
                      <span className="font-mono text-[10px] text-secondary">{item.file_name}</span>
                      {!isAvail && item.unavailable_reason && (
                        <div className="mt-1 flex items-start gap-1 text-[10px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 p-1.5 rounded border border-amber-200 dark:border-amber-800/40">
                          <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                          <span>{item.unavailable_reason}</span>
                        </div>
                      )}
                    </td>

                    <td className="px-4 py-3 font-mono text-[11px] max-w-xs">
                      {item.file_path ? (
                        <span className="text-secondary text-[10px] block truncate font-mono" title={item.file_path}>
                          {item.file_path}
                        </span>
                      ) : (
                        <span className="text-secondary/60 text-[10px] block italic truncate" title={item.expected_storage_path || "Not generated"}>
                          Expected: {item.expected_storage_path || "Dynamic"}
                        </span>
                      )}
                    </td>

                    <td className="px-4 py-3 text-[11px] text-secondary font-mono whitespace-nowrap">
                      {item.provenance_source}
                    </td>

                    <td className="px-4 py-3 font-mono text-on-surface whitespace-nowrap">
                      {formatFileSize(item.file_size_bytes)}
                    </td>

                    <td className="px-4 py-3 font-mono text-[11px] whitespace-nowrap">
                      {item.sha256 ? (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-secondary font-mono bg-surface-container px-1.5 py-0.5 rounded border border-surface-container">
                            {item.sha256.substring(0, 10)}...{item.sha256.substring(item.sha256.length - 6)}
                          </span>
                          <button
                            onClick={() => copyToClipboard(item.sha256!)}
                            className="p-1 hover:bg-surface-container rounded text-secondary hover:text-on-surface"
                            title="Copy full SHA-256"
                          >
                            {copiedHash === item.sha256 ? (
                              <Check className="w-3 h-3 text-emerald-600" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      ) : (
                        <span className="text-secondary/50 text-[10px] italic">No hash</span>
                      )}
                    </td>

                    <td className="px-4 py-3 whitespace-nowrap">
                      {isAvail ? (
                        <div className="flex flex-col gap-1">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1 w-fit">
                            <CheckCircle2 className="w-3 h-3" />
                            AVAILABLE
                          </span>
                          {verState?.verified && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-blue-100 text-blue-800 border border-blue-200 flex items-center gap-0.5 w-fit">
                              <ShieldCheck className="w-2.5 h-2.5" />
                              VERIFIED
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-surface-container text-secondary flex items-center gap-1 w-fit">
                          <XCircle className="w-3 h-3" />
                          UNAVAILABLE
                        </span>
                      )}
                    </td>

                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        {isAvail && (
                          <button
                            onClick={() => handleVerify(item)}
                            disabled={isVerifying}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-surface-container border border-surface-container hover:bg-surface-container-high text-xs font-semibold text-on-surface transition-colors"
                            title="Verify file presence and SHA-256 against disk"
                          >
                            <ShieldCheck className={`w-3 h-3 ${isVerifying ? "animate-spin text-primary" : "text-emerald-600"}`} />
                            <span className="text-[11px]">{isVerifying ? "Verifying..." : "Verify"}</span>
                          </button>
                        )}

                        {downloadUrl && isAvail ? (
                          <a
                            href={downloadUrl}
                            download={item.file_name}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-on-primary hover:bg-primary/90 text-xs font-semibold shadow-xs transition-colors"
                          >
                            <Download className="w-3 h-3" />
                            <span>Download</span>
                          </a>
                        ) : (
                          <span className="text-secondary text-[11px] italic px-2">Unavailable</span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}

              {!loading && evidenceList.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-8 text-center text-secondary">
                    No evidence records discovered for this investigation case.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
