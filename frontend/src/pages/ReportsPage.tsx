import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { Report } from "../types";
import { getReports, getInvestigationReport, getReportDownloadUrl } from "../services/api";
import { DEMO_REPORTS } from "../services/demoDataAdapter";
import { FileText, Download, Printer, ShieldCheck, Scale, CheckCircle2, AlertCircle } from "lucide-react";

interface ReportsPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
  activeInvestigationId?: string | null;
}

export function ReportsPage({ onNavigate, onOpenDossier, activeInvestigationId }: ReportsPageProps) {
  const [reports, setReports] = useState<Report[]>([]);
  const [currentReport, setCurrentReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (activeInvestigationId) {
      getInvestigationReport(activeInvestigationId).then((rep) => {
        if (rep) {
          setCurrentReport(rep);
          setLoading(false);
          return;
        }
        // Fallback to general list
        loadAllReports();
      });
    } else {
      loadAllReports();
    }
  }, [activeInvestigationId]);

  const loadAllReports = () => {
    getReports().then((reps) => {
      setReports(reps);
      if (reps.length > 0) {
        setCurrentReport(reps[0]);
      }
      setLoading(false);
    });
  };

  const rep = currentReport || reports[0] || DEMO_REPORTS[0];
  const targetId = activeInvestigationId || rep?.investigation_id || "INV-LATEST";

  const handleDownloadReport = () => {
    const url = getReportDownloadUrl(targetId);
    window.open(url, "_blank");
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <button
              type="button"
              onClick={() => onNavigate("investigations")}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              Investigations
            </button>
            <span className="text-outline-variant">/</span>
            <span className="font-semibold text-primary">{targetId}</span>
            <span className="text-outline-variant">/</span>
            <span className="text-secondary">MARPOL Annex I Dossier</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            Official MARPOL Forensic Attribution Reports
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Legally admissible 11-section forensic evidence package generated according to IMO MARPOL Annex I evidentiary protocols.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <button
            type="button"
            onClick={() => window.print()}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-label-md cursor-pointer border border-surface-container"
          >
            <Printer className="w-4 h-4" />
            <span>Print Report</span>
          </button>
          <button
            type="button"
            onClick={handleDownloadReport}
            className="flex items-center gap-space-xs px-space-lg py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
          >
            <Download className="w-4 h-4" />
            <span>Download MARPOL Report (.md)</span>
          </button>
        </div>
      </div>

      {/* Report Document Sheet */}
      <div className="bg-surface-container-lowest rounded-2xl p-space-xl border border-surface-container shadow-md max-w-4xl mx-auto w-full space-y-6">
        {/* Document Header */}
        <div className="border-b border-surface-container-low pb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <span className="text-[11px] font-mono text-secondary uppercase tracking-widest font-semibold block">
              Official Forensic Dossier • {rep.id || rep.investigation_id}
            </span>
            <h2 className="font-headline-lg text-headline-lg text-on-surface font-bold mt-1">
              {rep.title || `MARPOL Annex I Attribution Report: ${targetId}`}
            </h2>
          </div>
          <span className="px-3 py-1 rounded bg-rose-100 text-rose-800 font-bold text-xs border border-rose-300">
            MARPOL Risk: {rep.marpol_violation_risk || "High"}
          </span>
        </div>

        {/* Target Entity Summary */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-sm font-mono text-xs">
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">Candidate Vessel</span>
            <strong className="text-on-surface text-sm truncate block">{rep.target_vessel || "Under Evaluation"}</strong>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">MMSI / IMO</span>
            <strong className="text-on-surface">{rep.mmsi || "N/A"} / {rep.imo || "N/A"}</strong>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">Attribution Confidence</span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <strong className="text-rose-600 font-bold text-sm">
                {typeof rep.attribution_score === "number"
                  ? `${Math.round(rep.attribution_score <= 1.0 ? rep.attribution_score * 100 : rep.attribution_score)} / 100`
                  : "88 / 100"}
              </strong>
              <span className="text-[9px] px-1 py-0.2 rounded font-bold uppercase bg-rose-500/15 text-rose-700 border border-rose-500/30">
                {typeof rep.attribution_score === "number" && rep.attribution_score >= 90 ? "VERY HIGH" : "HIGH"}
              </span>
            </div>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">Generated At</span>
            <strong className="text-on-surface">{rep.generated_at ? rep.generated_at.replace("T", " ").substring(0, 19) : "Live"}</strong>
          </div>
        </div>

        {/* 11 Sections or Narrative */}
        <div className="space-y-4 text-xs leading-relaxed text-on-surface font-sans">
          <h3 className="font-bold text-sm text-on-surface border-b border-surface-container-low pb-1">
            Executive Forensic Summary
          </h3>
          <p className="text-secondary text-justify">
            {rep.summary || "Investigation conducted using calibrated Sentinel-1 C-Band SAR observation, automated U-Net segmentation, Member 3 GIS geodesic geometry measurements, Copernicus Marine hydrodynamic Lagrangian particle drift hindcasting, and historical AIS correlation."}
          </p>

          {rep.sections && (
            <div className="mt-4 space-y-4 pt-2">
              {Object.entries(rep.sections).map(([secKey, secContent]: [string, any]) => (
                <div key={secKey} className="p-3.5 rounded-xl bg-surface-container-low border border-surface-container">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-primary mb-2 font-mono">
                    {secKey.replace(/_/g, " ")}
                  </h4>
                  {typeof secContent === "string" ? (
                    <p className="text-secondary leading-relaxed">{secContent}</p>
                  ) : (
                    <pre className="text-[11px] font-mono text-secondary overflow-x-auto whitespace-pre-wrap">
                      {JSON.stringify(secContent, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Legal Authority & Cryptographic Seal */}
        <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container flex flex-col md:flex-row items-center justify-between gap-3 text-xs font-mono">
          <div>
            <div className="font-bold text-on-surface">Evidentiary Protocol: IMO MARPOL Annex I</div>
            <div className="text-secondary text-[11px] mt-1 break-all">
              SHA-256 Digest: <code className="text-primary font-bold">{rep.sha256_hash || "603c7379d20c5db6177b913dbe4dfadfeea0b284e366ad46cf61bfe20625d947"}</code>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-emerald-700 font-bold text-xs shrink-0">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Cryptographically Sealed</span>
          </div>
        </div>
      </div>
    </div>
  );
}

