import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { EvidenceItem, Investigation } from "../types";
import { getInvestigations, getInvestigationEvidence } from "../services/api";
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
  ExternalLink,
  Layers,
  MapPin,
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

  const { showToast } = useToast();

  useEffect(() => {
    getInvestigations().then((list) => {
      setInvestigations(list);
      if (!selectedId && list.length > 0) {
        setSelectedId(list[0].id);
      }
    });
  }, []);

  useEffect(() => {
    if (selectedId) {
      setLoading(true);
      getInvestigationEvidence(selectedId)
        .then((items) => setEvidenceList(items))
        .catch((err) => showToast("error", "Failed to load evidence files: " + err.message))
        .finally(() => setLoading(false));
    }
  }, [selectedId, showToast]);

  const handleSelectCase = (id: string) => {
    setSelectedId(id);
    if (onSelectInvestigation) onSelectInvestigation(id);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
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

        {/* Case Selector Dropdown */}
        <div className="flex items-center gap-2 bg-surface-container-lowest p-2 rounded-xl border border-surface-container shadow-xs">
          <span className="text-xs font-semibold text-secondary px-2">Case:</span>
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
        <div className="p-4 border-b border-surface-container flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-bold text-xs text-on-surface uppercase tracking-wider">
              Verified Pipeline Artifacts for
            </span>
            <span className="font-mono text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">
              {selectedId || "N/A"}
            </span>
          </div>
          <span className="text-[11px] text-secondary font-mono">
            Cryptographic SHA-256 integrity checks enabled
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-container-low border-b border-surface-container text-secondary font-mono uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Artifact Title</th>
                <th className="px-4 py-3">File Name &amp; Storage Path</th>
                <th className="px-4 py-3">Data Provenance</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-low">
              {evidenceList.map((item, idx) => {
                const isAvail = item.status === "AVAILABLE";
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

                    <td className="px-4 py-3 font-semibold text-on-surface">
                      {item.name}
                    </td>

                    <td className="px-4 py-3 font-mono text-[11px] max-w-xs truncate">
                      <span className="text-primary font-semibold block truncate">{item.file_name}</span>
                      <span className="text-secondary text-[10px] truncate block opacity-75">{item.file_path || "data/"}</span>
                    </td>

                    <td className="px-4 py-3 text-[11px] text-secondary font-mono">
                      {item.provenance_source}
                    </td>

                    <td className="px-4 py-3 font-mono text-on-surface whitespace-nowrap">
                      {formatFileSize(item.file_size_bytes)}
                    </td>

                    <td className="px-4 py-3 whitespace-nowrap">
                      {isAvail ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1 w-fit">
                          <CheckCircle2 className="w-3 h-3" />
                          AVAILABLE
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-surface-container text-secondary flex items-center gap-1 w-fit">
                          <XCircle className="w-3 h-3" />
                          UNAVAILABLE
                        </span>
                      )}
                    </td>

                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {item.download_url && isAvail ? (
                        <a
                          href={item.download_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-on-primary hover:bg-primary/90 text-xs font-semibold shadow-xs"
                        >
                          <Download className="w-3 h-3" />
                          <span>Download</span>
                        </a>
                      ) : (
                        <span className="text-secondary text-[11px] italic">Not on disk</span>
                      )}
                    </td>
                  </tr>
                );
              })}

              {!loading && evidenceList.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-secondary">
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
