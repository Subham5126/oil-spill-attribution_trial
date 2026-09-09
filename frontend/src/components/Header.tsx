import React, { useState } from "react";
import { NavPath } from "./Sidebar";
import { Info, AlertTriangle, ShieldCheck } from "lucide-react";

interface HeaderProps {
  onNavigate: (path: NavPath) => void;
  onOpenNotifications?: () => void;
  dataMode?: string;
}

export function Header({
  onNavigate,
  onOpenNotifications,
  dataMode = "DEMO / SYNTHETIC AIS",
}: HeaderProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const [showDataModeInfo, setShowDataModeInfo] = useState(false);

  const searchResults = [
    {
      type: "Primary Suspect",
      title: "PACIFIC VOYAGER",
      subtitle: "MMSI 413999001 (95.4% Attribution Match)",
      path: "vessel-analysis" as NavPath,
    },
    {
      type: "Candidate Vessel",
      title: "NORDIC TRADER",
      subtitle: "MMSI 211888002 (88.5% Secondary Match)",
      path: "vessel-analysis" as NavPath,
    },
    {
      type: "SAR Spill Slick",
      title: "SAR-20250101-IND-0042",
      subtitle: "Arabian Sea (3.9275 km²) EPSG:4326",
      path: "spill-analysis" as NavPath,
    },
    {
      type: "Drift Hindcast",
      title: "Probable Origin @ 18.5253°N, 72.5032°E",
      subtitle: "Lagrangian -4h Hindcast (95% Disp. 1.885 km)",
      path: "drift-analysis" as NavPath,
    },
    {
      type: "Incident Report",
      title: "REP-2025-0042 MARPOL Annex I Dossier",
      subtitle: "Official Forensic Evidence Package",
      path: "reports" as NavPath,
    },
  ].filter((item) =>
    searchTerm.trim()
      ? item.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.subtitle.toLowerCase().includes(searchTerm.toLowerCase())
      : true
  );

  return (
    <header className="fixed top-0 left-sidebar-width right-0 h-16 bg-surface-container-lowest shadow-[0_1px_8px_rgba(0,0,0,0.06)] z-40 flex items-center justify-between px-space-xl border-b border-surface-container">
      {/* Left Active Investigation Context */}
      <div className="flex items-center gap-space-md">
        <button
          type="button"
          onClick={() => onNavigate("investigations")}
          className="flex items-center gap-space-xs px-space-sm py-space-2xs rounded bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer"
        >
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
          <span className="font-label-sm text-label-sm text-primary font-semibold tracking-wide uppercase">
            Active Incident
          </span>
        </button>
        <span
          className="font-data-mono-md text-data-mono-md text-on-surface font-semibold cursor-pointer hover:text-primary transition-colors"
          onClick={() => onNavigate("investigations")}
        >
          #SAR-20250101-IND-0042
        </span>
        <span className="text-outline-variant font-label-md text-label-md">•</span>
        <span className="font-body-sm text-body-sm text-on-surface-variant">
          Arabian Sea (Offshore Mumbai Corridor)
        </span>
      </div>

      {/* Right Controls: Search, DATA MODE BADGE, Live Status, Notifications, Profile */}
      <div className="flex items-center gap-space-md">
        {/* PROMINENT DATA MODE BADGE (PHASE 13) */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowDataModeInfo(!showDataModeInfo)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-700 hover:bg-amber-500/20 transition-colors font-data-mono-sm text-[11px] font-bold"
            title="Data Integrity Mode"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            <span>{dataMode}</span>
            <Info className="w-3 h-3 text-amber-500 opacity-80" />
          </button>

          {showDataModeInfo && (
            <div className="absolute right-0 top-10 w-80 bg-slate-900 border border-slate-700 text-slate-100 rounded-xl p-3.5 shadow-2xl z-50 text-xs font-sans">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <span className="font-bold text-amber-400 flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  Data Pipeline Provenance
                </span>
                <button
                  type="button"
                  onClick={() => setShowDataModeInfo(false)}
                  className="text-slate-400 hover:text-white"
                >
                  ✕
                </button>
              </div>
              <div className="mt-2.5 space-y-2 text-slate-300 font-sans">
                <p>
                  <strong className="text-white">Satellite SAR & GIS:</strong> Real calibrated Sentinel-1 C-Band SAR detection (3.9275 km², 10m resolution).
                </p>
                <p>
                  <strong className="text-white">Ocean Drift:</strong> Physical Lagrangian hindcasting powered by Copernicus marine surface currents and ERA5 wind dynamics.
                </p>
                <p>
                  <strong className="text-amber-300">AIS Trajectories:</strong> Synthetic scenario vessel trajectories generated to simulate realistic Class-A vessel movements for end-to-end attribution validation.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Global Search with Autocomplete */}
        <div className="relative flex items-center">
          <span className="material-symbols-outlined absolute left-space-sm text-outline text-[18px]">
            search
          </span>
          <input
            className="pl-9 pr-space-md py-1.5 h-9 bg-surface-container-lowest border border-surface-container rounded-lg text-on-surface font-body-sm text-body-sm placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary w-56 md:w-72"
            placeholder="Search MMSI, vessel, spill ID..."
            type="text"
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setShowSearchDropdown(true);
            }}
            onFocus={() => setShowSearchDropdown(true)}
            onBlur={() => setTimeout(() => setShowSearchDropdown(false), 200)}
          />

          {showSearchDropdown && searchTerm.trim() && (
            <div className="absolute top-10 left-0 right-0 bg-surface-container-lowest rounded-xl shadow-xl border border-surface-container py-1 z-50 flex flex-col">
              <div className="px-3 py-1 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                Matching Entities
              </div>
              {searchResults.length > 0 ? (
                searchResults.map((res, i) => (
                  <button
                    key={i}
                    type="button"
                    className="px-3 py-2 text-left hover:bg-surface-container-low transition-colors flex flex-col cursor-pointer"
                    onMouseDown={() => {
                      onNavigate(res.path);
                      setSearchTerm("");
                      setShowSearchDropdown(false);
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-label-md text-label-md text-on-surface font-semibold">
                        {res.title}
                      </span>
                      <span className="font-data-mono-sm text-[10px] text-primary bg-primary-fixed px-1.5 py-0.5 rounded">
                        {res.type}
                      </span>
                    </div>
                    <span className="font-body-sm text-body-sm text-secondary">
                      {res.subtitle}
                    </span>
                  </button>
                ))
              ) : (
                <div className="px-3 py-2 text-body-sm text-secondary">No matching entities found</div>
              )}
            </div>
          )}
        </div>

        {/* Live Feeds Status */}
        <div className="hidden xl:flex items-center gap-space-xs px-space-sm py-1 rounded-lg bg-surface-container-low border border-surface-container">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span className="font-data-mono-sm text-data-mono-sm text-on-surface-variant">
            SAR: Sentinel-1 IW
          </span>
          <span className="text-outline-variant">|</span>
          <span className="font-data-mono-sm text-data-mono-sm text-on-surface-variant">
            Lagrangian Hindcast: 4h
          </span>
        </div>

        {/* Notifications Trigger */}
        <button
          aria-label="Notifications"
          type="button"
          onClick={onOpenNotifications}
          className="relative p-1.5 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors cursor-pointer"
          title="Incident Alerts"
        >
          <span className="material-symbols-outlined text-[22px]">notifications</span>
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-error"></span>
        </button>

        {/* User Profile Avatar */}
        <button
          type="button"
          onClick={() => onNavigate("settings")}
          className="w-8 h-8 rounded-full bg-primary flex items-center justify-center hover:opacity-90 transition-opacity cursor-pointer text-on-primary font-bold shadow-sm"
          title="Operational Profile"
        >
          <span className="material-symbols-outlined text-[18px]">person</span>
        </button>
      </div>
    </header>
  );
}
