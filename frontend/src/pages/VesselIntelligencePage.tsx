import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { VesselIntelligenceItem, VesselIncidentAppearance } from "../types";
import { getVesselIntelligence } from "../services/api";
import {
  Ship,
  Search,
  AlertCircle,
  ShieldAlert,
  ArrowRight,
  Filter,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  MapPin,
  Calendar,
} from "lucide-react";

interface VesselIntelligencePageProps {
  onNavigate: (path: NavPath) => void;
  onSelectInvestigation?: (id: string) => void;
}

export function VesselIntelligencePage({ onNavigate, onSelectInvestigation }: VesselIntelligencePageProps) {
  const [vessels, setVessels] = useState<VesselIntelligenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [expandedMmsi, setExpandedMmsi] = useState<string | number | null>(null);

  useEffect(() => {
    getVesselIntelligence()
      .then((data) => setVessels(data))
      .catch((err) => console.error("Failed to load vessel intelligence:", err))
      .finally(() => setLoading(false));
  }, []);

  const filtered = vessels.filter((v) => {
    const q = search.toLowerCase();
    const match =
      v.vessel_name.toLowerCase().includes(q) ||
      String(v.mmsi).includes(q) ||
      (v.imo && v.imo.toLowerCase().includes(q)) ||
      (v.flag && v.flag.toLowerCase().includes(q));
    if (!match) return false;

    if (typeFilter !== "ALL") {
      if (typeFilter === "MULTI" && v.appearances_count < 2) return false;
      if (typeFilter === "HIGH_SCORE" && v.highest_score < 0.6) return false;
    }

    return true;
  });

  const totalVessels = vessels.length;
  const multiIncidentCount = vessels.filter((v) => v.appearances_count > 1).length;
  const highScoreCount = vessels.filter((v) => v.highest_score >= 0.7).length;

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary uppercase tracking-wider">AIS Correlation Registry</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold flex items-center gap-2">
            <Ship className="w-6 h-6 text-primary" />
            Vessel Intelligence &amp; Suspect Registry
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Cross-incident tracking of AIS candidate vessels detected in drift-dispersion search corridors.
          </p>
        </div>
      </div>

      {/* Mandatory Legal & Scientific Disclaimer Banner */}
      <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-900 flex items-start gap-3 shadow-xs">
        <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="flex flex-col gap-1">
          <span className="font-bold text-amber-800 uppercase tracking-wider text-[11px]">
            Statutory Evidentiary Disclaimer
          </span>
          <p className="leading-relaxed text-secondary text-xs">
            Appearance in this intelligence registry indicates that an AIS transponder signal was recorded within
            the spatiotemporal backward-trajectory corridor of an oil slick during the estimated release window.
            Candidate ranking reflects mathematical proximity and drift alignment; it does <strong>NOT</strong> constitute
            an accusation of culpability without corroborating physical sampling and boarding inspection.
          </p>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-md">
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Profiled Vessels
            </div>
            <div className="text-2xl font-bold text-on-surface mt-1 font-mono">
              {totalVessels.toLocaleString()}
            </div>
          </div>
          <Ship className="w-8 h-8 text-primary opacity-40" />
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Multi-Incident Candidates
            </div>
            <div className="text-2xl font-bold text-indigo-600 mt-1 font-mono">
              {multiIncidentCount}
            </div>
          </div>
          <AlertCircle className="w-8 h-8 text-indigo-500 opacity-40" />
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              High Attribution Score (≥70%)
            </div>
            <div className="text-2xl font-bold text-rose-600 mt-1 font-mono">
              {highScoreCount}
            </div>
          </div>
          <ShieldAlert className="w-8 h-8 text-rose-500 opacity-40" />
        </div>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-surface-container-lowest p-space-md rounded-xl border border-surface-container shadow-sm">
        <div className="flex items-center gap-2 flex-1 max-w-md bg-surface-container-low px-3 py-2 rounded-lg border border-surface-container">
          <Search className="w-4 h-4 text-secondary" />
          <input
            type="text"
            placeholder="Filter by vessel name, MMSI, IMO, or flag..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent text-xs text-on-surface w-full focus:outline-none font-mono"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-secondary" />
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label="Filter vessel intelligence"
            className="bg-surface-container-low text-xs text-on-surface px-2.5 py-1.5 rounded-lg border border-surface-container focus:outline-none font-mono"
          >
            <option value="ALL">All Profiled Vessels</option>
            <option value="MULTI">Multi-Incident Only</option>
            <option value="HIGH_SCORE">Score ≥ 60%</option>
          </select>
        </div>
      </div>

      {/* Intelligence Table */}
      <div className="bg-surface-container-lowest rounded-xl border border-surface-container shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-container-low border-b border-surface-container text-secondary font-mono uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3">Vessel Identity</th>
                <th className="px-4 py-3">Type &amp; Flag</th>
                <th className="px-4 py-3">Incident Count</th>
                <th className="px-4 py-3">Min Distance</th>
                <th className="px-4 py-3">Attribution Confidence</th>
                <th className="px-4 py-3">Last Correlated</th>
                <th className="px-4 py-3 text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-low">
              {filtered.map((vessel) => {
                const isExpanded = expandedMmsi === vessel.mmsi;
                const confScore = Math.round((vessel.highest_score || 0) * 100);
                const confLevel =
                  confScore >= 90
                    ? "VERY HIGH"
                    : confScore >= 75
                    ? "HIGH"
                    : confScore >= 50
                    ? "MODERATE"
                    : confScore >= 25
                    ? "LOW"
                    : "VERY LOW";

                const levelColors: Record<string, string> = {
                  "VERY HIGH": "bg-emerald-500/15 text-emerald-700 border-emerald-500/30",
                  "HIGH": "bg-sky-500/15 text-sky-700 border-sky-500/30",
                  "MODERATE": "bg-amber-500/15 text-amber-700 border-amber-500/30",
                  "LOW": "bg-orange-500/15 text-orange-700 border-orange-500/30",
                  "VERY LOW": "bg-slate-500/15 text-slate-700 border-slate-500/30",
                };

                return (
                  <React.Fragment key={vessel.mmsi}>
                    <tr
                      className="hover:bg-surface-container-low/50 transition-colors cursor-pointer"
                      onClick={() => setExpandedMmsi(isExpanded ? null : vessel.mmsi)}
                    >
                      <td className="px-4 py-3.5">
                        <div className="font-bold text-on-surface text-xs">{vessel.vessel_name}</div>
                        <div className="font-mono text-[10px] text-secondary flex items-center gap-2 mt-0.5">
                          <span>MMSI: {vessel.mmsi}</span>
                          {vessel.imo && <span>• IMO: {vessel.imo}</span>}
                        </div>
                      </td>

                      <td className="px-4 py-3.5 text-secondary font-mono text-[11px]">
                        <div>{vessel.vessel_type || "Cargo/Tanker"}</div>
                        <div className="text-[10px] text-outline-variant">{vessel.flag || "Unknown Flag"}</div>
                      </td>

                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold ${
                            vessel.appearances_count > 1
                              ? "bg-indigo-100 text-indigo-800 border border-indigo-200"
                              : "bg-surface-container text-secondary"
                          }`}
                        >
                          {vessel.appearances_count} {vessel.appearances_count === 1 ? "Incident" : "Incidents"}
                        </span>
                      </td>

                      <td className="px-4 py-3.5 font-mono text-on-surface">
                        {vessel.min_distance_km ? `${vessel.min_distance_km.toFixed(2)} km` : "—"}
                      </td>

                      <td className="px-4 py-3.5 font-mono">
                        <div className="inline-flex items-center gap-1.5">
                          <span className="font-bold text-xs">{confScore} / 100</span>
                          <span
                            className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase border ${
                              levelColors[confLevel] || levelColors["MODERATE"]
                            }`}
                          >
                            {confLevel}
                          </span>
                        </div>
                      </td>

                      <td className="px-4 py-3.5 text-secondary font-mono text-[11px]">
                        {vessel.last_observed ? new Date(vessel.last_observed).toLocaleDateString() : "Historical"}
                      </td>

                      <td className="px-4 py-3.5 text-right">
                        <button
                          type="button"
                          className="p-1 rounded text-secondary hover:text-primary transition-colors"
                        >
                          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                      </td>
                    </tr>

                    {/* Expandable row showing all incident appearances */}
                    {isExpanded && vessel.incidents && vessel.incidents.length > 0 && (
                      <tr className="bg-surface-container-low/30">
                        <td colSpan={7} className="px-6 py-3">
                          <div className="flex flex-col gap-2">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-secondary">
                              Correlated Incidents ({vessel.incidents.length})
                            </span>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {vessel.incidents.map((inc: VesselIncidentAppearance) => (
                                <div
                                  key={inc.investigation_id}
                                  onClick={() => {
                                    if (onSelectInvestigation) onSelectInvestigation(inc.investigation_id);
                                    onNavigate("dashboard");
                                  }}
                                  className="p-2.5 rounded-lg bg-surface-container-lowest border border-surface-container hover:border-primary cursor-pointer flex items-center justify-between text-xs"
                                >
                                  <div>
                                    <div className="font-mono font-bold text-primary text-[11px]">
                                      {inc.investigation_id}
                                    </div>
                                    <div className="font-semibold text-on-surface truncate mt-0.5">
                                      {inc.title}
                                    </div>
                                    <div className="text-[10px] text-secondary font-mono mt-0.5">
                                      Region: {inc.region} • Rank: #{inc.rank}
                                    </div>
                                  </div>
                                  <div className="text-right">
                                    <span className="font-mono font-bold text-rose-600 block text-xs">
                                      {(inc.score * 100).toFixed(1)}%
                                    </span>
                                    <span className="text-[10px] text-secondary font-mono">
                                      {inc.min_distance_km.toFixed(1)} km
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}

              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-secondary">
                    No vessel records match the current search filters.
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
