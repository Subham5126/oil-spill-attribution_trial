import React from "react";
import { UserProfile } from "../types";

export type NavPath =
  | "dashboard"
  | "investigations"
  | "new-investigation"
  | "investigation-history"
  | "live-investigations"
  | "reports"
  | "evidence-library"
  | "map-explorer"
  | "vessel-intelligence"
  | "datasets"
  | "system-status"
  | "settings"
  | "spill-analysis"
  | "vessel-analysis"
  | "drift-analysis"
  | "live-map"
  | "incidents"
  | "analysis-process"
  | "satellite-detail"
  | "geometry-detail"
  | "vessel-detail"
  | "report-detail"
  | "investigation-detail"
  | "profile"
  | "admin-users"
  | "employee-management"
  | "login";

interface SidebarProps {
  currentPath: NavPath;
  onNavigate: (path: NavPath) => void;
  userProfile?: UserProfile | null;
  userRole?: string | null;
  onLogout?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function Sidebar({
  currentPath,
  onNavigate,
  userProfile,
  userRole,
  onLogout,
  isCollapsed = false,
  onToggleCollapse,
}: SidebarProps) {
  const navSections: {
    heading: string;
    items: { path: NavPath; label: string; icon: string }[];
  }[] = [
    {
      heading: "OPERATIONAL",
      items: [
        { path: "dashboard", label: "Dashboard", icon: "dashboard" },
        { path: "investigations", label: "Investigations", icon: "manage_search" },
        { path: "new-investigation", label: "New Incident", icon: "add_circle" },
        { path: "investigation-history", label: "History Log", icon: "history" },
        { path: "live-investigations", label: "Live Pipeline", icon: "sensors" },
      ],
    },
    {
      heading: "ANALYSIS & EVIDENCE",
      items: [
        { path: "map-explorer", label: "Map Explorer", icon: "public" },
        { path: "vessel-intelligence", label: "Vessel Intelligence", icon: "directions_boat" },
        { path: "evidence-library", label: "Evidence Library", icon: "folder_zip" },
        { path: "reports", label: "Forensic Reports", icon: "description" },
      ],
    },
    {
      heading: "PLATFORM & DATA",
      items: [
        { path: "datasets", label: "Datasets", icon: "dataset" },
        { path: "system-status", label: "System Status", icon: "health_and_safety" },
        { path: "settings", label: "Settings", icon: "settings" },
        ...(userRole === "ADMIN"
          ? [{ path: "admin-users" as NavPath, label: "User Management", icon: "admin_panel_settings" }]
          : []),
      ],
    },
    ...(userRole === "TECH_ADMIN"
      ? [
          {
            heading: "TECH ADMIN",
            items: [
              {
                path: "employee-management" as NavPath,
                label: "Employee Management",
                icon: "badge",
              },
            ],
          },
        ]
      : []),
  ];

  return (
    <aside
      data-testid="main-sidebar"
      aria-expanded={!isCollapsed}
      className={`fixed left-0 top-0 h-full ${
        isCollapsed ? "w-[68px]" : "w-sidebar-width"
      } bg-inverse-surface text-inverse-on-surface z-50 flex flex-col justify-between shadow-[0_1px_8px_rgba(0,0,0,0.08)] overflow-y-auto overflow-x-hidden transition-all duration-300 ease-in-out`}
    >
      <div className="flex flex-col">
        {/* Brand Header */}
        <div
          className={`${
            isCollapsed ? "p-2.5 items-center" : "p-space-md"
          } flex flex-col gap-space-2xs border-b border-surface-container-high/10 transition-all`}
        >
          <div className="flex items-center justify-between w-full">
            <div
              className={`flex items-center ${
                isCollapsed ? "justify-center w-full" : "gap-space-sm"
              } cursor-pointer`}
              onClick={() => onNavigate("dashboard")}
              title="OILTRACE Operational GIS"
            >
              <div className="w-9 h-9 rounded-xl bg-primary-container flex items-center justify-center text-on-primary shadow-md shrink-0">
                <span className="material-symbols-outlined text-[22px]">radar</span>
              </div>
              {!isCollapsed && (
                <div className="flex flex-col overflow-hidden">
                  <span className="font-headline-sm text-headline-sm tracking-tight text-surface-container-lowest font-bold truncate">
                    OILTRACE
                  </span>
                  <span className="font-data-mono-sm text-[10px] text-tertiary-fixed-dim uppercase tracking-wider font-semibold truncate">
                    Operational GIS
                  </span>
                </div>
              )}
            </div>

            {/* Collapse/Expand Toggle Button (Desktop & Tablet) */}
            {onToggleCollapse && (
              <button
                data-testid="sidebar-collapse-toggle"
                type="button"
                onClick={onToggleCollapse}
                className={`${
                  isCollapsed ? "mt-2 self-center" : ""
                } w-7 h-7 rounded-lg flex items-center justify-center text-outline-variant hover:text-surface-container-lowest hover:bg-surface-container-high/20 transition-all cursor-pointer shrink-0`}
                title={isCollapsed ? "Expand Sidebar (Ctrl+B)" : "Collapse Sidebar (Ctrl+B)"}
                aria-label={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
              >
                <span className="material-symbols-outlined text-[18px]">
                  {isCollapsed ? "chevron_right" : "chevron_left"}
                </span>
              </button>
            )}
          </div>

          {!isCollapsed && (
            <p className="font-label-sm text-[11px] text-outline-variant mt-1 leading-snug">
              Satellite Hydrocarbon Attribution System
            </p>
          )}
        </div>

        {/* Navigation Sections */}
        <nav className={`flex flex-col ${isCollapsed ? "px-1.5 py-3" : "px-space-sm py-space-sm"} gap-2`}>
          {navSections.map((section, sIdx) => (
            <div key={section.heading} className="flex flex-col gap-1">
              {!isCollapsed ? (
                <span className="px-space-sm text-[10px] font-bold tracking-wider text-outline-variant/70 uppercase">
                  {section.heading}
                </span>
              ) : sIdx > 0 ? (
                <div className="my-1 border-t border-surface-container-high/15 mx-1" />
              ) : null}

              {section.items.map((item) => {
                const isActive =
                  currentPath === item.path ||
                  (item.path === "investigations" &&
                    ["investigations", "incidents"].includes(currentPath)) ||
                  (item.path === "map-explorer" && currentPath === "live-map") ||
                  (item.path === "reports" && currentPath === "report-detail") ||
                  (item.path === "vessel-intelligence" && currentPath === "vessel-analysis");

                return (
                  <button
                    key={item.path}
                    data-testid={`sidebar-nav-${item.path}`}
                    type="button"
                    onClick={() => onNavigate(item.path)}
                    title={item.label}
                    aria-label={item.label}
                    className={`flex items-center ${
                      isCollapsed ? "justify-center py-2 px-0" : "gap-space-sm px-space-sm py-1.5 text-left"
                    } rounded-lg transition-all font-label-sm text-xs w-full cursor-pointer overflow-hidden group ${
                      isActive
                        ? "bg-primary-container text-on-primary font-semibold shadow-sm"
                        : "text-outline-variant hover:bg-surface-container-high/15 hover:text-surface-container-lowest"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[18px] shrink-0 w-6 h-6 flex items-center justify-center overflow-hidden">
                      {item.icon}
                    </span>
                    {!isCollapsed && <span className="truncate">{item.label}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </div>

      {/* Analyst Credentials Footer Badge */}
      <div
        className={`${
          isCollapsed ? "p-2 m-1 items-center" : "p-space-md m-space-sm"
        } rounded-xl bg-surface-container-high/10 border flex flex-col gap-space-sm transition-all ${
          currentPath === "profile"
            ? "border-primary-container shadow-sm bg-surface-container-high/20"
            : "border-surface-container-high/15"
        }`}
      >
        <div
          data-testid="sidebar-analyst-badge"
          className={`flex items-center ${isCollapsed ? "justify-center" : "gap-space-sm"} cursor-pointer group`}
          onClick={() => onNavigate("profile")}
          title={`${userProfile?.full_name || 'Senior Forensic Analyst'} (Open Profile)`}
          aria-label="User Profile"
        >
          <div className="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary font-bold shadow-sm group-hover:ring-2 group-hover:ring-primary-container transition-all shrink-0 overflow-hidden border border-surface-container-high/30">
            {userProfile?.avatar_url ? (
              <img
                src={userProfile.avatar_url}
                alt={userProfile.full_name || "Analyst"}
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = "none";
                }}
              />
            ) : (
              <span className="font-mono text-xs font-bold">
                {userProfile?.full_name
                  ? userProfile.full_name
                      .trim()
                      .split(" ")
                      .map((w) => w[0])
                      .slice(0, 2)
                      .join("")
                      .toUpperCase()
                  : "AV"}
              </span>
            )}
          </div>
          {!isCollapsed && (
            <div className="flex flex-col overflow-hidden">
              <span className="font-label-md text-label-md text-surface-container-lowest font-semibold truncate group-hover:text-primary-container transition-colors">
                {userProfile?.title || "Senior Forensic Analyst"}
              </span>
              <span className="font-label-sm text-label-sm text-outline-variant truncate">
                {userProfile?.organization || "DG Shipping / Coast Guard"}
              </span>
            </div>
          )}
        </div>

        {!isCollapsed ? (
          <div className="flex items-center justify-between pt-space-xs border-t border-surface-container-high/20">
            <button
              data-testid="sidebar-node-btn"
              type="button"
              onClick={() => onNavigate("profile")}
              className="font-data-mono-sm text-data-mono-sm text-tertiary-fixed-dim hover:underline cursor-pointer truncate max-w-[120px]"
              title="Edit Profile"
            >
              {userProfile?.node_id || "Node #IND-WEST-01"}
            </button>
            <button
              type="button"
              onClick={() => onLogout?.()}
              className="flex items-center gap-space-2xs text-outline-variant hover:text-surface-container-lowest font-label-sm text-label-sm transition-colors cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px] w-4 h-4 flex items-center justify-center overflow-hidden">logout</span>
              <span>Sign out</span>
            </button>
          </div>
        ) : (
          <div className="pt-1 border-t border-surface-container-high/20 flex justify-center w-full">
            <button
              type="button"
              onClick={() => onLogout?.()}
              title="Sign Out"
              aria-label="Sign Out"
              className="text-outline-variant hover:text-surface-container-lowest p-1 rounded transition-colors cursor-pointer overflow-hidden"
            >
              <span className="material-symbols-outlined text-[16px] w-4 h-4 flex items-center justify-center overflow-hidden">logout</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
