import React from "react";

export type NavPath =
  | "dashboard"
  | "investigations"
  | "spill-analysis"
  | "vessel-analysis"
  | "drift-analysis"
  | "live-map"
  | "incidents"
  | "reports"
  | "settings"
  | "new-investigation"
  | "analysis-process"
  | "satellite-detail"
  | "geometry-detail"
  | "vessel-detail"
  | "report-detail"
  | "login";

interface SidebarProps {
  currentPath: NavPath;
  onNavigate: (path: NavPath) => void;
}

export function Sidebar({ currentPath, onNavigate }: SidebarProps) {
  const navItems: { path: NavPath; label: string; icon: string }[] = [
    { path: "dashboard", label: "Dashboard", icon: "dashboard" },
    { path: "investigations", label: "Investigations", icon: "manage_search" },
    { path: "spill-analysis", label: "Spill Geometry", icon: "opacity" },
    { path: "drift-analysis", label: "Drift Analysis", icon: "airwave" },
    { path: "vessel-analysis", label: "Vessel Attribution", icon: "directions_boat" },
    { path: "live-map", label: "Live GIS Map", icon: "public" },
    { path: "analysis-process", label: "Pipeline Stream", icon: "polyline" },
    { path: "reports", label: "Forensic Reports", icon: "description" },
    { path: "settings", label: "System Config", icon: "settings" },
  ];

  return (
    <aside className="fixed left-0 top-0 h-full w-sidebar-width bg-inverse-surface text-inverse-on-surface z-50 flex flex-col justify-between shadow-[0_1px_8px_rgba(0,0,0,0.08)]">
      <div className="flex flex-col">
        {/* Brand Header */}
        <div className="p-space-lg flex flex-col gap-space-xs border-b border-surface-container-high/10">
          <div
            className="flex items-center gap-space-sm cursor-pointer"
            onClick={() => onNavigate("dashboard")}
          >
            <div className="w-9 h-9 rounded-xl bg-primary-container flex items-center justify-center text-on-primary shadow-md">
              <span className="material-symbols-outlined text-[22px]">radar</span>
            </div>
            <div className="flex flex-col">
              <span className="font-headline-sm text-headline-sm tracking-tight text-surface-container-lowest font-bold">
                OILTRACE
              </span>
              <span className="font-data-mono-sm text-[11px] text-tertiary-fixed-dim uppercase tracking-wider font-semibold">
                Operational GIS
              </span>
            </div>
          </div>
          <p className="font-label-sm text-label-sm text-outline-variant mt-space-2xs">
            Satellite Detection &amp; Vessel Attribution
          </p>
        </div>

        {/* Navigation List */}
        <nav className="flex flex-col px-space-sm py-space-md gap-space-2xs">
          {navItems.map((item) => {
            const isActive =
              currentPath === item.path ||
              (item.path === "investigations" &&
                ["investigations", "new-investigation"].includes(currentPath)) ||
              (item.path === "spill-analysis" &&
                ["spill-analysis", "satellite-detail", "geometry-detail"].includes(currentPath)) ||
              (item.path === "vessel-analysis" &&
                ["vessel-analysis", "vessel-detail"].includes(currentPath)) ||
              (item.path === "reports" && ["reports", "report-detail"].includes(currentPath));

            return (
              <button
                key={item.path}
                type="button"
                onClick={() => onNavigate(item.path)}
                className={`flex items-center gap-space-sm px-space-md py-space-sm rounded-lg transition-all font-label-md text-label-md text-left w-full cursor-pointer ${
                  isActive
                    ? "bg-primary-container text-on-primary font-semibold shadow-sm"
                    : "text-outline-variant hover:bg-surface-container-high/15 hover:text-surface-container-lowest"
                }`}
              >
                <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Analyst Credentials Footer Badge */}
      <div className="p-space-md m-space-sm rounded-xl bg-surface-container-high/10 border border-surface-container-high/15 flex flex-col gap-space-sm">
        <div className="flex items-center gap-space-sm">
          <div className="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary font-bold shadow-sm">
            <span className="material-symbols-outlined text-[18px]">person</span>
          </div>
          <div className="flex flex-col overflow-hidden">
            <span className="font-label-md text-label-md text-surface-container-lowest font-semibold truncate">
              Senior Forensic Analyst
            </span>
            <span className="font-label-sm text-label-sm text-outline-variant truncate">
              DG Shipping / Coast Guard
            </span>
          </div>
        </div>
        <div className="flex items-center justify-between pt-space-xs border-t border-surface-container-high/20">
          <span className="font-data-mono-sm text-data-mono-sm text-tertiary-fixed-dim">
            Node #IND-WEST-01
          </span>
          <button
            type="button"
            onClick={() => onNavigate("login")}
            className="flex items-center gap-space-2xs text-outline-variant hover:text-surface-container-lowest font-label-sm text-label-sm transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">logout</span>
            <span>Sign out</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
