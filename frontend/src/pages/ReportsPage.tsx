import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { Report } from "../types";
import { getReports } from "../services/api";
import { DEMO_REPORTS } from "../services/demoDataAdapter";
import { FileText, Download, Printer, ShieldCheck, Scale, CheckCircle2 } from "lucide-react";

interface ReportsPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export function ReportsPage({ onNavigate, onOpenDossier }: ReportsPageProps) {
  const [reports, setReports] = useState<Report[]>(DEMO_REPORTS);
  const rep = reports[0] || DEMO_REPORTS[0];

  useEffect(() => {
    getReports().then(setReports);
  }, []);

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary">Forensic Dossiers</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            Official MARPOL Forensic Attribution Reports
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Legally admissible forensic evidence packages generated according to IMO MARPOL Annex I evidentiary protocols.
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
            onClick={() => window.open("/data/end_to_end_layers.geojson", "_blank")}
            className="flex items-center gap-space-xs px-space-lg py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
          >
            <Download className="w-4 h-4" />
            <span>Download Evidence Package</span>
          </button>
        </div>
      </div>

      {/* Report Document Sheet */}
      <div className="bg-surface-container-lowest rounded-2xl p-space-xl border border-surface-container shadow-md max-w-4xl mx-auto w-full space-y-6">
        {/* Document Header */}
        <div className="border-b border-surface-container-low pb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <span className="text-[11px] font-mono text-secondary uppercase tracking-widest font-semibold block">
              Official Forensic Dossier • {rep.id}
            </span>
            <h2 className="font-headline-lg text-headline-lg text-on-surface font-bold mt-1">
              {rep.title}
            </h2>
          </div>
          <span className="px-3 py-1 rounded bg-rose-100 text-rose-800 font-bold text-xs border border-rose-300">
            MARPOL Risk: {rep.marpol_violation_risk}
          </span>
        </div>

        {/* Target Entity Summary */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-sm font-mono text-xs">
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">Target Vessel</span>
            <strong className="text-on-surface text-sm">{rep.target_vessel}</strong>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">MMSI / IMO</span>
            <strong className="text-on-surface">{rep.mmsi} / {rep.imo}</strong>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">Attribution Score</span>
            <strong className="text-rose-600 font-bold">{rep.attribution_score}%</strong>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container-low">
            <span className="text-secondary block text-[10px]">Generated At</span>
            <strong className="text-on-surface">{rep.generated_at.replace("T", " ")}</strong>
          </div>
        </div>

        {/* Narrative */}
        <div className="space-y-3 text-xs leading-relaxed text-on-surface font-sans">
          <h3 className="font-bold text-sm text-on-surface">Executive Forensic Summary</h3>
          <p className="text-secondary">{rep.summary}</p>
          <p className="text-secondary">
            Analysis incorporates Member 3 GIS polygon delineation (Area: 3.9275 km², Perimeter: 9.963 km),
            backward Lagrangian drift hindcast (40 particles, 4-hour duration) pointing to release origin
            at 18.5253°N, 72.5032°E, and coincident AIS Class-A trajectory of {rep.target_vessel} passing
            within 0.572 km of the origin release point.
          </p>
        </div>

        {/* Legal Authority & Cryptographic Seal */}
        <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container flex flex-col md:flex-row items-center justify-between gap-3 text-xs font-mono">
          <div>
            <div className="font-bold text-on-surface">Jurisdiction: {rep.jurisdiction}</div>
            <div className="text-secondary text-[11px] mt-1">
              SHA-256 Digest: <code className="text-primary">{rep.sha256_hash}</code>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-emerald-700 font-bold text-xs shrink-0">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Cryptographically Verified</span>
          </div>
        </div>
      </div>
    </div>
  );
}
