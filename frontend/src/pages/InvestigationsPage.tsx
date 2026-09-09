import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { Investigation } from "../types";
import { getInvestigations } from "../services/api";
import { DEMO_INVESTIGATIONS } from "../services/demoDataAdapter";
import {
  Folder,
  Plus,
  Search,
  Filter,
  ArrowRight,
  ShieldAlert,
  Clock,
  MapPin,
} from "lucide-react";

interface InvestigationsPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export function InvestigationsPage({ onNavigate, onOpenDossier }: InvestigationsPageProps) {
  const [investigations, setInvestigations] = useState<Investigation[]>(DEMO_INVESTIGATIONS);
  const [search, setSearch] = useState("");

  useEffect(() => {
    getInvestigations().then(setInvestigations);
  }, []);

  const filtered = investigations.filter(
    (inv) =>
      inv.title.toLowerCase().includes(search.toLowerCase()) ||
      inv.id.toLowerCase().includes(search.toLowerCase()) ||
      inv.region.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary">Operational Registry</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            Maritime Incident Investigations
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Active and archived satellite hydrocarbon detection cases with attributed suspect vessels.
          </p>
        </div>

        {/* Action Button */}
        <button
          type="button"
          onClick={() => onNavigate("new-investigation")}
          className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
        >
          <Plus className="w-4 h-4" />
          <span>New Incident Investigation</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex items-center justify-between gap-space-md bg-surface-container-lowest p-space-sm rounded-xl border border-surface-container shadow-sm">
        <div className="flex items-center gap-2 flex-1 max-w-md bg-surface-container-low px-3 py-1.5 rounded-lg border border-surface-container">
          <Search className="w-4 h-4 text-secondary" />
          <input
            type="text"
            placeholder="Search by incident ID, region, vessel..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent text-xs text-on-surface w-full focus:outline-none font-mono"
          />
        </div>
        <span className="font-data-mono-sm text-xs text-secondary">
          {filtered.length} Incident Cases
        </span>
      </div>

      {/* Investigations List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        {filtered.map((inv) => (
          <div
            key={inv.id}
            onClick={() => onNavigate("dashboard")}
            className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container hover:border-primary transition-all cursor-pointer shadow-sm flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
                <span className="font-data-mono-sm text-xs text-primary font-bold">{inv.id}</span>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    inv.status === "Active"
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                      : "bg-surface-container text-secondary"
                  }`}
                >
                  {inv.status}
                </span>
              </div>
              <h3 className="font-headline-sm text-headline-sm text-on-surface font-bold mt-2">
                {inv.title}
              </h3>
              <p className="text-xs text-secondary mt-1 flex items-center gap-1 font-mono">
                <MapPin className="w-3.5 h-3.5 text-primary" />
                {inv.region}
              </p>

              <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[11px]">
                <div className="bg-surface-container-low p-2 rounded-lg">
                  <span className="text-secondary block text-[10px]">Spill Area:</span>
                  <strong className="text-rose-600">{inv.spill_area_km2} km²</strong>
                </div>
                <div className="bg-surface-container-low p-2 rounded-lg">
                  <span className="text-secondary block text-[10px]">Suspect Vessel:</span>
                  <strong className="text-on-surface truncate block">
                    {inv.suspect_vessel || "Under Analysis"}
                  </strong>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-2 border-t border-surface-container-low flex items-center justify-between text-xs text-primary font-semibold">
              <span>Inspect Case Details</span>
              <ArrowRight className="w-4 h-4" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
