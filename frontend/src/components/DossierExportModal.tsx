import React, { useState } from "react";
import { X, Download, FileText, CheckCircle2, ShieldCheck, Database } from "lucide-react";

interface DossierExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DossierExportModal: React.FC<DossierExportModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [exporting, setExporting] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  if (!isOpen) return null;

  const handleExport = () => {
    setExporting(true);
    setTimeout(() => {
      setExporting(false);
      setDownloaded(true);
      // Trigger download of GeoJSON layers
      window.open("/data/end_to_end_layers.geojson", "_blank");
    }, 1000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-sky-400" />
            <h3 className="font-bold text-white text-base">Export Forensic Dossier Package</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs font-sans text-slate-300">
          <p>
            Generate a tamper-evident prosecution package including calibrated SAR polygons,
            backward Lagrangian drift hindcast steps, correlated AIS trajectories, and multi-criteria attribution scores.
          </p>

          <div className="space-y-2 font-mono text-[11px]">
            <label className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
              <input type="checkbox" defaultChecked className="accent-primary" />
              <span>Full Investigation Forensic Report (PDF)</span>
            </label>
            <label className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
              <input type="checkbox" defaultChecked className="accent-primary" />
              <span>Multi-Layer GIS FeatureCollection (GeoJSON)</span>
            </label>
            <label className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
              <input type="checkbox" defaultChecked className="accent-primary" />
              <span>Attribution Evidence Matrix (JSON)</span>
            </label>
          </div>

          <div className="p-3 rounded-lg bg-sky-950/40 border border-sky-800 text-sky-200 flex items-center gap-2 font-mono text-[11px]">
            <ShieldCheck className="w-4 h-4 text-sky-400 shrink-0" />
            <span>Digital SHA-256 seal will be appended to exported bundle.</span>
          </div>

          <div className="pt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleExport}
              disabled={exporting}
              className="px-4 py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors flex items-center gap-1.5 font-semibold cursor-pointer shadow-md"
            >
              {exporting ? (
                <span>Assembling Package...</span>
              ) : downloaded ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-300" />
                  <span>Package Downloaded</span>
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  <span>Download Dossier</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
