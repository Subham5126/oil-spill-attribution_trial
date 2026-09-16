import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { DatasetItem } from "../types";
import { getDatasetsStatus } from "../services/api";
import {
  Database,
  CheckCircle2,
  AlertTriangle,
  HardDrive,
  RefreshCw,
  Folder,
  Layers,
  Satellite,
  Waves,
  Ship,
  FileCode,
} from "lucide-react";

interface DatasetsPageProps {
  onNavigate: (path: NavPath) => void;
}

export function DatasetsPage({ onNavigate }: DatasetsPageProps) {
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchDatasets = () => {
    setLoading(true);
    getDatasetsStatus()
      .then((data) => setDatasets(data.datasets || []))
      .catch((err) => console.error("Failed to fetch datasets:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDatasets();
  }, []);

  const getProviderIcon = (provider: string) => {
    if (provider.includes("Copernicus") || provider.includes("Sentinel")) {
      return <Satellite className="w-5 h-5 text-sky-500" />;
    }
    if (provider.includes("CMEMS") || provider.includes("Ocean")) {
      return <Waves className="w-5 h-5 text-emerald-500" />;
    }
    if (provider.includes("GFW") || provider.includes("AIS")) {
      return <Ship className="w-5 h-5 text-indigo-500" />;
    }
    return <Database className="w-5 h-5 text-primary" />;
  };

  const verifiedCount = datasets.filter((d) => d.verified).length;

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary uppercase tracking-wider">Repository Management</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold flex items-center gap-2">
            <Database className="w-6 h-6 text-primary" />
            Operational Datasets Registry
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Status of Sentinel-1 radar scenes, U-Net model checkpoints, Copernicus hydrodynamic grids, and AIS logs.
          </p>
        </div>

        <button
          type="button"
          onClick={fetchDatasets}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Verify Filesystem</span>
        </button>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-md">
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Monitored Datasets
            </div>
            <div className="text-2xl font-bold text-on-surface mt-1 font-mono">
              {datasets.length} Subsystems
            </div>
          </div>
          <Layers className="w-8 h-8 text-primary opacity-40" />
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Verified Operational
            </div>
            <div className="text-2xl font-bold text-emerald-600 mt-1 font-mono">
              {verifiedCount} of {datasets.length} Ready
            </div>
          </div>
          <CheckCircle2 className="w-8 h-8 text-emerald-500 opacity-40" />
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Data Integrity Mode
            </div>
            <div className="text-lg font-bold text-sky-600 mt-1 font-mono">
              Strict (No Mocking)
            </div>
          </div>
          <HardDrive className="w-8 h-8 text-sky-500 opacity-40" />
        </div>
      </div>

      {/* Datasets Table */}
      <div className="bg-surface-container-lowest rounded-xl border border-surface-container shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-container-low border-b border-surface-container text-secondary font-mono uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3">Dataset</th>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Format</th>
                <th className="px-4 py-3">Coverage / Description</th>
                <th className="px-4 py-3">Records / Items</th>
                <th className="px-4 py-3">Local Storage Path</th>
                <th className="px-4 py-3 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-low">
              {datasets.map((dataset) => (
                <tr key={dataset.id} className="hover:bg-surface-container-low/50 transition-colors">
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-2">
                      {getProviderIcon(dataset.provider)}
                      <div>
                        <div className="font-bold text-on-surface text-xs">{dataset.name}</div>
                        <div className="font-mono text-[10px] text-secondary">{dataset.id}</div>
                      </div>
                    </div>
                  </td>

                  <td className="px-4 py-3.5 font-mono text-secondary text-[11px]">
                    {dataset.provider}
                  </td>

                  <td className="px-4 py-3.5 font-mono text-[11px] font-semibold text-on-surface">
                    {dataset.format}
                  </td>

                  <td className="px-4 py-3.5 text-secondary text-[11px] max-w-xs truncate">
                    {dataset.coverage}
                  </td>

                  <td className="px-4 py-3.5 font-mono font-bold text-on-surface">
                    {dataset.records_count}
                  </td>

                  <td className="px-4 py-3.5 font-mono text-[11px] text-secondary max-w-xs truncate">
                    <span className="bg-surface-container px-2 py-0.5 rounded block truncate">
                      {dataset.local_path}
                    </span>
                  </td>

                  <td className="px-4 py-3.5 text-right whitespace-nowrap">
                    {dataset.verified ? (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 inline-flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        VERIFIED
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200 inline-flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" />
                        CHECK REQUIRED
                      </span>
                    )}
                  </td>
                </tr>
              ))}

              {!loading && datasets.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-secondary">
                    No datasets discovered in local repository.
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
