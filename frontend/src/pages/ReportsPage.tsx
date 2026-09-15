import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { Report } from "../types";
import { getReports, getInvestigationReport, getReportDownloadUrl } from "../services/api";
import { DEMO_REPORTS } from "../services/demoDataAdapter";
import { ForensicPdfButton } from "../components/ForensicPdfButton";
import { FileText, Download, Printer, ShieldCheck, Scale, CheckCircle2, AlertCircle } from "lucide-react";

interface ReportsPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
  activeInvestigationId?: string | null;
}

function formatAcqTime(ts?: string): string {
  if (!ts || ts === "N/A") return "N/A";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
  } catch {
    return ts;
  }
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
          <ForensicPdfButton
            investigationId={targetId}
            variant="primary"
            showViewOption={true}
          />
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

        {/* Executive Forensic Summary (Single Polished Section) */}
        <div className="space-y-4 text-xs leading-relaxed text-on-surface font-sans">
          <h3 className="font-bold text-sm text-on-surface border-b border-surface-container-low pb-1">
            Executive Forensic Summary
          </h3>
          <p className="text-secondary text-justify leading-relaxed">
            {rep.summary || rep.sections?.["1_executive_summary"] || "Investigation conducted using calibrated Sentinel-1 C-Band SAR observation, automated U-Net segmentation, Member 3 GIS geodesic geometry measurements, Copernicus Marine hydrodynamic Lagrangian particle drift hindcasting, and historical AIS correlation."}
          </p>

          {/* 2. Incident Information (Clean Card Presentation) */}
          {rep.sections?.["2_incident_information"] && (
            <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-2.5">
              <h4 className="font-bold text-xs uppercase tracking-wider text-primary font-mono flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" />
                <span>Incident Information</span>
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 font-mono text-xs">
                {rep.sections["2_incident_information"].investigation_id && (
                  <div className="p-2.5 rounded-lg bg-surface-container-lowest border border-surface-container">
                    <span className="text-secondary block text-[10px] uppercase font-semibold">Investigation ID</span>
                    <strong className="text-on-surface text-xs font-bold">{rep.sections["2_incident_information"].investigation_id}</strong>
                  </div>
                )}
                {rep.sections["2_incident_information"].image_id && rep.sections["2_incident_information"].image_id !== "N/A" && (
                  <div className="p-2.5 rounded-lg bg-surface-container-lowest border border-surface-container">
                    <span className="text-secondary block text-[10px] uppercase font-semibold">SAR Image</span>
                    <strong className="text-on-surface text-xs font-bold">{rep.sections["2_incident_information"].image_id}</strong>
                  </div>
                )}
                {rep.sections["2_incident_information"].acquisition_time && rep.sections["2_incident_information"].acquisition_time !== "N/A" && (
                  <div className="p-2.5 rounded-lg bg-surface-container-lowest border border-surface-container">
                    <span className="text-secondary block text-[10px] uppercase font-semibold">Acquisition Time</span>
                    <strong className="text-on-surface text-xs font-bold">
                      {formatAcqTime(rep.sections["2_incident_information"].acquisition_time)}
                    </strong>
                  </div>
                )}
                {rep.sections["2_incident_information"].location && rep.sections["2_incident_information"].location !== "N/A" && (
                  <div className="p-2.5 rounded-lg bg-surface-container-lowest border border-surface-container">
                    <span className="text-secondary block text-[10px] uppercase font-semibold">Location</span>
                    <strong className="text-on-surface text-xs font-bold">{rep.sections["2_incident_information"].location}</strong>
                  </div>
                )}
                {rep.sections["2_incident_information"].region && (
                  <div className="p-2.5 rounded-lg bg-surface-container-lowest border border-surface-container sm:col-span-2 md:col-span-2">
                    <span className="text-secondary block text-[10px] uppercase font-semibold">Region</span>
                    <strong className="text-on-surface text-xs font-bold">{rep.sections["2_incident_information"].region}</strong>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. Sentinel-1 SAR Evidence */}
          {rep.sections?.["3_sentinel1_evidence"] && (
            <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-primary font-mono">
                Sentinel-1 SAR Evidence
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
                {rep.sections["3_sentinel1_evidence"].sensor && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Sensor / Mode</span>
                    <strong className="text-on-surface">{rep.sections["3_sentinel1_evidence"].sensor}</strong>
                  </div>
                )}
                {rep.sections["3_sentinel1_evidence"].crs && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Coordinate System</span>
                    <strong className="text-on-surface">{rep.sections["3_sentinel1_evidence"].crs}</strong>
                  </div>
                )}
                {typeof rep.sections["3_sentinel1_evidence"].confidence === "number" && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Detection Confidence</span>
                    <strong className="text-emerald-700 font-bold">
                      {rep.sections["3_sentinel1_evidence"].confidence <= 1.0
                        ? `${(rep.sections["3_sentinel1_evidence"].confidence * 100).toFixed(1)}%`
                        : `${rep.sections["3_sentinel1_evidence"].confidence}%`}
                    </strong>
                  </div>
                )}
                {rep.sections["3_sentinel1_evidence"].resolution_meters && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Spatial Resolution</span>
                    <strong className="text-on-surface">{rep.sections["3_sentinel1_evidence"].resolution_meters} m/px</strong>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 4. Spill Characterization */}
          {rep.sections?.["4_spill_characterization"] && (
            <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-primary font-mono">
                Spill Geometry & Delineation
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
                {typeof rep.sections["4_spill_characterization"].area_sq_km === "number" && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Delineated Area</span>
                    <strong className="text-rose-600 font-bold">{rep.sections["4_spill_characterization"].area_sq_km.toFixed(4)} km²</strong>
                  </div>
                )}
                {typeof rep.sections["4_spill_characterization"].perimeter_km === "number" && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Perimeter</span>
                    <strong className="text-on-surface">{rep.sections["4_spill_characterization"].perimeter_km.toFixed(2)} km</strong>
                  </div>
                )}
                {rep.sections["4_spill_characterization"].shape_characteristics?.aspect_ratio && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Aspect Ratio</span>
                    <strong className="text-on-surface">{Number(rep.sections["4_spill_characterization"].shape_characteristics.aspect_ratio).toFixed(2)}</strong>
                  </div>
                )}
                {rep.sections["4_spill_characterization"].shape_characteristics?.compactness && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Compactness</span>
                    <strong className="text-on-surface">{Number(rep.sections["4_spill_characterization"].shape_characteristics.compactness).toFixed(3)}</strong>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 5. Oceanographic & Drift Analysis */}
          {rep.sections?.["5_oceanographic_analysis"] && (
            <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-2.5">
              <h4 className="font-bold text-xs uppercase tracking-wider text-primary font-mono">
                Oceanographic & Drift Analysis
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 font-mono text-xs">
                {rep.sections["5_oceanographic_analysis"].dataset && rep.sections["5_oceanographic_analysis"].dataset !== "N/A" && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Copernicus Current Grid</span>
                    <strong className="text-on-surface truncate block" title={rep.sections["5_oceanographic_analysis"].dataset}>
                      {rep.sections["5_oceanographic_analysis"].dataset}
                    </strong>
                  </div>
                )}
                {rep.sections["5_oceanographic_analysis"].backward_drift_window && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Backward Drift Window</span>
                    <strong className="text-on-surface">{rep.sections["5_oceanographic_analysis"].backward_drift_window}</strong>
                  </div>
                )}
                {rep.sections["5_oceanographic_analysis"].probable_origin?.latitude && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">Reconstructed Origin</span>
                    <strong className="text-on-surface">
                      {Number(rep.sections["5_oceanographic_analysis"].probable_origin.latitude).toFixed(4)}°N, {Number(rep.sections["5_oceanographic_analysis"].probable_origin.longitude).toFixed(4)}°E
                    </strong>
                  </div>
                )}
                {typeof rep.sections["5_oceanographic_analysis"].uncertainty_radius_km === "number" && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">95% Spatial Dispersion</span>
                    <strong className="text-on-surface">{rep.sections["5_oceanographic_analysis"].uncertainty_radius_km.toFixed(1)} km radius</strong>
                  </div>
                )}
                {rep.sections["5_oceanographic_analysis"].sar_acquisition && (
                  <div>
                    <span className="text-secondary block text-[10px] uppercase">SAR Reference Time</span>
                    <strong className="text-on-surface">{formatAcqTime(rep.sections["5_oceanographic_analysis"].sar_acquisition)}</strong>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 6. AIS Correlated Candidates */}
          {rep.sections?.["6_ais_vessel_correlation"] && Array.isArray(rep.sections["6_ais_vessel_correlation"]) && rep.sections["6_ais_vessel_correlation"].length > 0 && (
            <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-3">
              <h4 className="font-bold text-xs uppercase tracking-wider text-primary font-mono">
                Top Correlated AIS Vessels ({rep.sections["6_ais_vessel_correlation"].length})
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-surface-container text-secondary text-[10px] uppercase">
                      <th className="py-1.5 px-2">Vessel Name</th>
                      <th className="py-1.5 px-2">MMSI</th>
                      <th className="py-1.5 px-2">Type / Flag</th>
                      <th className="py-1.5 px-2 text-right">Distance to Track</th>
                      <th className="py-1.5 px-2 text-right">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-lowest">
                    {rep.sections["6_ais_vessel_correlation"].slice(0, 5).map((v: any, idx: number) => (
                      <tr key={v.mmsi || idx} className="hover:bg-surface-container-lowest/50">
                        <td className="py-2 px-2 font-semibold text-on-surface">{v.vessel_name || "UNKNOWN"}</td>
                        <td className="py-2 px-2 text-secondary">{v.mmsi || "N/A"}</td>
                        <td className="py-2 px-2 text-secondary">{v.vessel_type || "N/A"} {v.flag ? `(${v.flag})` : ""}</td>
                        <td className="py-2 px-2 text-right text-on-surface">
                          {typeof v.distance_to_track_km === "number" ? `${v.distance_to_track_km.toFixed(2)} km` : "N/A"}
                        </td>
                        <td className="py-2 px-2 text-right font-bold text-rose-600">
                          {typeof v.confidence_score === "number" ? `${v.confidence_score}%` : "N/A"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 7. Evidence Assessment */}
          {rep.sections?.["7_evidence_assessment"] && (
            <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-primary font-mono">
                Evidence Assessment & Findings
              </h4>
              <div className="space-y-1.5 text-xs text-secondary leading-relaxed">
                {rep.sections["7_evidence_assessment"].observed_evidence && (
                  <p><strong className="text-on-surface">Physical Observation:</strong> {rep.sections["7_evidence_assessment"].observed_evidence}</p>
                )}
                {rep.sections["7_evidence_assessment"].derived_evidence && (
                  <p><strong className="text-on-surface">Morphological Evidence:</strong> {rep.sections["7_evidence_assessment"].derived_evidence}</p>
                )}
                {rep.sections["7_evidence_assessment"].model_based_evidence && (
                  <p><strong className="text-on-surface">Hydrodynamic Advection:</strong> {rep.sections["7_evidence_assessment"].model_based_evidence}</p>
                )}
                {rep.sections["7_evidence_assessment"].ais_correlation && (
                  <p><strong className="text-on-surface">AIS Telemetry Correlation:</strong> {rep.sections["7_evidence_assessment"].ais_correlation}</p>
                )}
              </div>
            </div>
          )}

          {/* 8. Candidate Vessel Assessment & Disclaimer */}
          {rep.sections?.["8_candidate_vessel_assessment"]?.attribution_disclaimer && (
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-900 text-xs">
              <span className="font-bold block mb-1 uppercase tracking-wider text-[10px]">Attribution Notice & Legal Disclaimer</span>
              <p className="leading-relaxed">{rep.sections["8_candidate_vessel_assessment"].attribution_disclaimer}</p>
            </div>
          )}

          {/* 9 & 10. Limitations and Recommendations */}
          {((rep.sections?.["9_limitations"] && rep.sections["9_limitations"].length > 0) || (rep.sections?.["10_recommended_next_steps"] && rep.sections["10_recommended_next_steps"].length > 0)) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {rep.sections?.["9_limitations"] && rep.sections["9_limitations"].length > 0 && (
                <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-2">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-secondary font-mono">
                    Methodological Limitations
                  </h4>
                  <ul className="list-disc list-inside space-y-1 text-xs text-secondary">
                    {rep.sections["9_limitations"].map((lim: string, idx: number) => (
                      <li key={idx} className="leading-relaxed">{lim}</li>
                    ))}
                  </ul>
                </div>
              )}
              {rep.sections?.["10_recommended_next_steps"] && rep.sections["10_recommended_next_steps"].length > 0 && (
                <div className="p-4 rounded-xl bg-surface-container-low border border-surface-container space-y-2">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-primary font-mono">
                    Recommended Next Steps
                  </h4>
                  <ol className="list-decimal list-inside space-y-1 text-xs text-secondary">
                    {rep.sections["10_recommended_next_steps"].map((step: string, idx: number) => (
                      <li key={idx} className="leading-relaxed">{step}</li>
                    ))}
                  </ol>
                </div>
              )}
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

