import React, { useState, useMemo, useEffect, useRef } from "react";
import { NavPath } from "./Sidebar";
import {
  Search,
  Bell,
  User,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Clock,
  ExternalLink,
  X,
  Radio,
} from "lucide-react";
import { Investigation, UserProfile, HeaderSearchResult, AppNotification } from "../types";
import {
  searchInvestigations,
  getNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead,
} from "../services/api";

interface HeaderProps {
  currentPath?: NavPath;
  onNavigate: (path: NavPath) => void;
  onSelectInvestigation?: (id: string) => void;
  onOpenNotifications?: () => void;
  activeInvestigation?: Investigation | null;
  userProfile?: UserProfile | null;
  isSidebarCollapsed?: boolean;
}

export function Header({
  currentPath = "dashboard",
  onNavigate,
  onSelectInvestigation,
  activeInvestigation,
  userProfile,
  isSidebarCollapsed = false,
}: HeaderProps) {
  // Search State
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<HeaderSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const [selectedSearchIndex, setSelectedSearchIndex] = useState(-1);

  // Notification State
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotificationsPanel, setShowNotificationsPanel] = useState(false);
  const [isNotificationsLoading, setIsNotificationsLoading] = useState(false);

  // Refs for click outside handling
  const searchContainerRef = useRef<HTMLDivElement>(null);
  const notificationsContainerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Dynamic Route Context Resolution
  const routeContext = useMemo(() => {
    // 1. Clean Global Dashboard (zero residual investigation state)
    if (currentPath === "dashboard") {
      return {
        badge: "OPERATIONAL",
        badgeDot: "bg-emerald-500",
        title: "Global Maritime Monitoring",
        subtitle: null,
      };
    }

    // 2. Specific Investigation Sub-routes
    const isInvestigationRoute = [
      "investigation-detail",
      "spill-analysis",
      "geometry-detail",
      "drift-analysis",
      "vessel-analysis",
      "vessel-detail",
      "analysis-process",
    ].includes(currentPath);

    if (isInvestigationRoute) {
      if (activeInvestigation) {
        return {
          badge: "ACTIVE INCIDENT",
          badgeDot: "bg-primary animate-pulse",
          title: `#${activeInvestigation.id}`,
          subtitle: activeInvestigation.region || "Maritime Surveillance Zone",
        };
      }
      return {
        badge: "INVESTIGATION",
        badgeDot: "bg-emerald-500",
        title: "Incident Investigation",
        subtitle: null,
      };
    }

    // 3. Platform Modules
    switch (currentPath) {
      case "investigations":
      case "incidents":
        return {
          badge: "OPERATIONAL",
          badgeDot: "bg-emerald-500",
          title: "Incident Investigations",
          subtitle: "Case Registry",
        };
      case "new-investigation":
        return {
          badge: "INTAKE",
          badgeDot: "bg-primary",
          title: "New Incident Tasking",
          subtitle: null,
        };
      case "investigation-history":
        return {
          badge: "ARCHIVE",
          badgeDot: "bg-slate-400",
          title: "Investigation History",
          subtitle: "Audit Log",
        };
      case "live-investigations":
        return {
          badge: "LIVE",
          badgeDot: "bg-sky-500 animate-pulse",
          title: "Live Pipelines",
          subtitle: "Active Jobs",
        };
      case "map-explorer":
      case "live-map":
        return {
          badge: "GIS",
          badgeDot: "bg-primary",
          title: "Geospatial Map Explorer",
          subtitle: "Multi-Layer Canvas",
        };
      case "vessel-intelligence":
        return {
          badge: "AIS INTEL",
          badgeDot: "bg-indigo-500",
          title: "Vessel Intelligence",
          subtitle: "Suspect Registry",
        };
      case "evidence-library":
        return {
          badge: "EVIDENCE",
          badgeDot: "bg-slate-500",
          title: "Evidence Library",
          subtitle: null,
        };
      case "reports":
      case "report-detail":
        return {
          badge: "FORENSIC",
          badgeDot: "bg-emerald-500",
          title: activeInvestigation ? `Forensic Report · #${activeInvestigation.id}` : "Forensic Reports",
          subtitle: "MARPOL Dossiers",
        };
      case "datasets":
        return {
          badge: "SENSORS",
          badgeDot: "bg-sky-500",
          title: "Datasets & Provenance",
          subtitle: "Sentinel-1 & CMEMS",
        };
      case "system-status":
        return {
          badge: "TELEMETRY",
          badgeDot: "bg-emerald-500",
          title: "System Status",
          subtitle: "Diagnostics",
        };
      case "settings":
        return {
          badge: "CONFIG",
          badgeDot: "bg-slate-400",
          title: "System Settings",
          subtitle: null,
        };
      case "profile":
        return {
          badge: "AUTHORITY",
          badgeDot: "bg-primary",
          title: "User Profile & Authority",
          subtitle: "Analyst Credentials",
        };
      default:
        return {
          badge: "OPERATIONAL",
          badgeDot: "bg-emerald-500",
          title: "Global Maritime Monitoring",
          subtitle: null,
        };
    }
  }, [currentPath, activeInvestigation]);

  // Load Notifications from Backend
  const fetchNotificationsData = async () => {
    try {
      const res = await getNotifications(20);
      setNotifications(res.items || []);
      setUnreadCount(res.unread_count || 0);
    } catch {
      // Graceful fallback
    }
  };

  useEffect(() => {
    fetchNotificationsData();
    // Lightweight polling every 40 seconds
    const interval = setInterval(fetchNotificationsData, 40000);
    return () => clearInterval(interval);
  }, []);

  // Close open dropdowns when route changes
  useEffect(() => {
    setShowSearchDropdown(false);
    setShowNotificationsPanel(false);
  }, [currentPath]);

  // Click outside listener for search and notifications
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(event.target as Node)
      ) {
        setShowSearchDropdown(false);
      }
      if (
        notificationsContainerRef.current &&
        !notificationsContainerRef.current.contains(event.target as Node)
      ) {
        setShowNotificationsPanel(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Search Debouncing
  useEffect(() => {
    const trimmed = searchTerm.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      setIsSearching(false);
      setSearchError(null);
      setSelectedSearchIndex(-1);
      return;
    }

    setIsSearching(true);
    setSearchError(null);
    setSelectedSearchIndex(-1);

    const timer = setTimeout(() => {
      searchInvestigations(trimmed, 8)
        .then((results) => {
          setSearchResults(results);
          setIsSearching(false);
        })
        .catch(() => {
          setIsSearching(false);
          setSearchError("Search temporarily unavailable");
        });
    }, 250);

    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Keyboard navigation for Search
  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSearchDropdown) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        setShowSearchDropdown(true);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedSearchIndex((prev) =>
        prev < searchResults.length - 1 ? prev + 1 : 0
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedSearchIndex((prev) =>
        prev <= 0 ? searchResults.length - 1 : prev - 1
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target =
        selectedSearchIndex >= 0
          ? searchResults[selectedSearchIndex]
          : searchResults[0];
      if (target) {
        handleSelectSearchResult(target);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setShowSearchDropdown(false);
      searchInputRef.current?.blur();
    }
  };

  const handleSelectSearchResult = (result: HeaderSearchResult) => {
    if (onSelectInvestigation) {
      onSelectInvestigation(result.investigation_id);
    }
    onNavigate("investigation-detail");
    setSearchTerm("");
    setShowSearchDropdown(false);
    setSelectedSearchIndex(-1);
  };

  const handleNotificationClick = async (notif: AppNotification) => {
    if (!notif.is_read) {
      await markNotificationAsRead(notif.id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notif.id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    }

    setShowNotificationsPanel(false);

    if (notif.investigation_id) {
      if (onSelectInvestigation) {
        onSelectInvestigation(notif.investigation_id);
      }
      // If completed, preferably open report view
      if ((notif.status || "").toLowerCase() === "completed" || notif.notification_type === "INVESTIGATION_COMPLETED") {
        onNavigate("reports");
      } else {
        onNavigate("investigation-detail");
      }
    } else {
      onNavigate("dashboard");
    }
  };

  const handleMarkAllRead = async () => {
    await markAllNotificationsAsRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
  };

  const formatRelativeTime = (isoString?: string | null) => {
    if (!isoString) return "just now";
    try {
      const date = new Date(isoString);
      const diffMs = Date.now() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return "just now";
      if (diffMins < 60) return `${diffMins} min ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours} hr ago`;
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays} d ago`;
    } catch {
      return "recently";
    }
  };

  // Avatar Initials Fallback
  const initials = useMemo(() => {
    if (!userProfile?.full_name) return "AN";
    const parts = userProfile.full_name.trim().split(" ");
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
    }
    return userProfile.full_name.slice(0, 2).toUpperCase();
  }, [userProfile?.full_name]);

  return (
    <header
      className={`fixed top-0 ${
        isSidebarCollapsed ? "left-[68px]" : "left-sidebar-width"
      } right-0 h-14 bg-surface-container-lowest shadow-[0_1px_6px_rgba(0,0,0,0.04)] z-40 flex items-center justify-between px-4 sm:px-6 border-b border-surface-container/80 transition-[left] duration-300 ease-in-out`}
    >
      {/* LEFT: Context / Status */}
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-container-low border border-surface-container shrink-0">
          <span className={`w-1.5 h-1.5 rounded-full ${routeContext.badgeDot} shrink-0`} />
          <span className="text-[10px] font-bold font-mono tracking-wider text-secondary uppercase">
            {routeContext.badge}
          </span>
        </div>
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="font-semibold text-xs sm:text-sm text-on-surface tracking-tight truncate">
            {routeContext.title}
          </span>
          {routeContext.subtitle && (
            <>
              <span className="text-outline-variant text-xs hidden md:inline">·</span>
              <span className="text-xs text-secondary truncate hidden md:inline font-normal">
                {routeContext.subtitle}
              </span>
            </>
          )}
        </div>
      </div>

      {/* CENTER & RIGHT: Search, Telemetry, Notifications, Profile */}
      <div className="flex items-center gap-2.5 sm:gap-3 shrink-0">
        {/* Functional Global Search */}
        <div ref={searchContainerRef} className="relative flex items-center">
          <Search className="w-3.5 h-3.5 absolute left-2.5 text-outline pointer-events-none" />
          <input
            ref={searchInputRef}
            className="pl-8 pr-7 py-1 h-8 bg-surface-container-lowest border border-surface-container rounded-lg text-on-surface text-xs placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary w-48 sm:w-56 md:w-64 transition-all"
            placeholder="Search vessels, MMSI, incidents..."
            type="text"
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setShowSearchDropdown(true);
            }}
            onFocus={() => setShowSearchDropdown(true)}
            onKeyDown={handleSearchKeyDown}
            aria-label="Search vessels, MMSI, incidents"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => {
                setSearchTerm("");
                setSearchResults([]);
                setShowSearchDropdown(false);
              }}
              className="absolute right-2 text-outline hover:text-on-surface cursor-pointer"
              title="Clear search"
            >
              <X className="w-3 h-3" />
            </button>
          )}

          {/* Search Results Dropdown */}
          {showSearchDropdown && searchTerm.trim().length >= 2 && (
            <div className="absolute top-9 left-0 right-0 sm:w-80 md:w-96 bg-surface-container-lowest rounded-xl shadow-xl border border-surface-container/90 py-1.5 z-50 flex flex-col text-xs overflow-hidden max-h-[380px]">
              <div className="px-3 py-1.5 text-[10px] font-mono text-outline uppercase tracking-wider border-b border-surface-container/60 flex items-center justify-between">
                <span>Matching Investigations</span>
                {isSearching && (
                  <span className="flex items-center gap-1 text-primary">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Searching...</span>
                  </span>
                )}
              </div>

              <div className="overflow-y-auto">
                {isSearching && searchResults.length === 0 ? (
                  <div className="px-4 py-6 text-center text-secondary flex flex-col items-center gap-2">
                    <Loader2 className="w-5 h-5 animate-spin text-primary" />
                    <span>Searching case records & AIS telemetry...</span>
                  </div>
                ) : searchError ? (
                  <div className="px-4 py-4 text-center text-rose-500">
                    {searchError}
                  </div>
                ) : searchResults.length > 0 ? (
                  searchResults.map((res, i) => {
                    const isSelected = i === selectedSearchIndex;
                    return (
                      <button
                        key={res.investigation_id || i}
                        type="button"
                        className={`w-full px-3 py-2.5 text-left transition-colors flex flex-col cursor-pointer border-b border-surface-container/30 last:border-b-0 ${
                          isSelected
                            ? "bg-primary/10 border-l-2 border-l-primary"
                            : "hover:bg-surface-container-low"
                        }`}
                        onClick={() => handleSelectSearchResult(res)}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-xs text-on-surface truncate">
                            {res.title}
                          </span>
                          <span className="text-[9px] font-mono font-semibold text-primary bg-primary/10 px-1.5 py-0.5 rounded shrink-0 uppercase">
                            {res.match_label || res.match_type}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 mt-1 text-[11px] text-secondary">
                          <span className="font-mono text-primary font-semibold">
                            {res.investigation_id}
                          </span>
                          <span>•</span>
                          <span className="truncate">{res.region}</span>
                          {res.status && (
                            <>
                              <span>•</span>
                              <span
                                className={`text-[10px] font-mono font-bold uppercase ${
                                  res.status.toLowerCase() === "completed"
                                    ? "text-emerald-600"
                                    : res.status.toLowerCase() === "failed"
                                    ? "text-rose-600"
                                    : "text-amber-600"
                                }`}
                              >
                                {res.status}
                              </span>
                            </>
                          )}
                        </div>

                        {res.suspect_vessel && (
                          <div className="text-[10px] text-outline-variant font-mono mt-0.5 truncate">
                            Attributed: {res.suspect_vessel}
                          </div>
                        )}
                      </button>
                    );
                  })
                ) : (
                  <div className="px-4 py-6 text-center text-secondary">
                    <p className="font-semibold text-xs text-on-surface">No matching investigations</p>
                    <p className="text-[11px] text-outline-variant mt-0.5">
                      Try searching by Case ID, Incident title, MMSI, or Vessel name.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Compact Telemetry Indicator */}
        <div
          className="hidden lg:flex items-center gap-2.5 px-2.5 py-1 rounded bg-surface-container-low/60 border border-surface-container/60 text-[10px] font-mono text-secondary"
          title="Real-time Satellite SAR & CMEMS Ocean Current Telemetry"
        >
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="font-semibold text-on-surface-variant uppercase tracking-wider">SAR ONLINE</span>
          </span>
          <span className="text-outline-variant/60">·</span>
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
            <span className="font-semibold text-on-surface-variant uppercase tracking-wider">OCEAN 4h</span>
          </span>
        </div>

        {/* Notifications Bell & Popover Panel */}
        <div ref={notificationsContainerRef} className="relative">
          <button
            aria-label="Incident Notifications"
            type="button"
            onClick={() => setShowNotificationsPanel((prev) => !prev)}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-secondary hover:text-on-surface hover:bg-surface-container-low transition-colors cursor-pointer relative"
            title="Operational Notifications"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-rose-500 text-white font-mono text-[9px] font-bold flex items-center justify-center shadow-xs">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {/* Compact Notification Panel */}
          {showNotificationsPanel && (
            <div className="absolute top-10 right-0 w-80 sm:w-88 bg-surface-container-lowest rounded-xl shadow-2xl border border-surface-container py-2 z-50 flex flex-col text-xs max-h-[420px] animate-fade-in">
              {/* Panel Header */}
              <div className="px-3.5 py-2 border-b border-surface-container/80 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-xs text-on-surface">Notifications</span>
                  {unreadCount > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full bg-primary/10 text-primary font-mono text-[10px] font-bold">
                      {unreadCount} new
                    </span>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    onClick={handleMarkAllRead}
                    className="text-[11px] font-semibold text-primary hover:underline cursor-pointer"
                  >
                    Mark all as read
                  </button>
                )}
              </div>

              {/* Notification List */}
              <div className="overflow-y-auto divide-y divide-surface-container/40">
                {notifications.length > 0 ? (
                  notifications.map((n) => {
                    const isCompleted =
                      (n.status || "").toLowerCase() === "completed" ||
                      n.notification_type === "INVESTIGATION_COMPLETED";
                    const isFailed =
                      (n.status || "").toLowerCase() === "failed" ||
                      n.notification_type === "INVESTIGATION_FAILED";
                    const isBlocked =
                      (n.status || "").toLowerCase() === "blocked" ||
                      n.notification_type === "INVESTIGATION_BLOCKED";

                    return (
                      <button
                        key={n.id}
                        type="button"
                        onClick={() => handleNotificationClick(n)}
                        className={`w-full px-3.5 py-2.5 text-left transition-colors flex items-start gap-2.5 cursor-pointer hover:bg-surface-container-low ${
                          !n.is_read ? "bg-primary/5" : ""
                        }`}
                      >
                        <div className="mt-0.5 shrink-0">
                          {isCompleted ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                          ) : isFailed || isBlocked ? (
                            <AlertTriangle className="w-4 h-4 text-rose-500" />
                          ) : (
                            <Radio className="w-4 h-4 text-primary" />
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <span
                              className={`font-semibold text-xs truncate ${
                                !n.is_read ? "text-on-surface font-bold" : "text-secondary"
                              }`}
                            >
                              {n.title}
                            </span>
                            <span className="text-[10px] text-outline font-mono shrink-0">
                              {formatRelativeTime(n.created_at)}
                            </span>
                          </div>

                          <p className="text-[11px] text-on-surface-variant mt-0.5 line-clamp-2 leading-snug">
                            {n.message}
                          </p>

                          {n.investigation_id && (
                            <div className="flex items-center gap-2 mt-1 font-mono text-[10px] text-primary">
                              <span>{n.investigation_id}</span>
                              {isCompleted && (
                                <span className="text-emerald-600 font-semibold flex items-center gap-0.5">
                                  <FileText className="w-3 h-3" />
                                  <span>Dossier Ready</span>
                                </span>
                              )}
                            </div>
                          )}
                        </div>

                        {!n.is_read && (
                          <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0 mt-1.5" />
                        )}
                      </button>
                    );
                  })
                ) : (
                  <div className="px-4 py-8 text-center text-secondary">
                    <CheckCircle2 className="w-6 h-6 text-emerald-500/60 mx-auto mb-1.5" />
                    <p className="font-semibold text-xs text-on-surface">No new notifications</p>
                    <p className="text-[11px] text-outline-variant mt-0.5">
                      You're all caught up.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* User Profile Avatar Button */}
        <button
          type="button"
          onClick={() => onNavigate("profile")}
          className="w-8 h-8 rounded-full bg-primary flex items-center justify-center hover:opacity-90 transition-opacity cursor-pointer text-on-primary font-bold shadow-xs shrink-0 overflow-hidden border border-surface-container"
          title={`${userProfile?.full_name || 'Analyst'} (Open Profile)`}
          aria-label="Analyst User Profile"
        >
          {userProfile?.avatar_url ? (
            <img
              src={userProfile.avatar_url}
              alt={userProfile.full_name || "Analyst Profile"}
              className="w-full h-full object-cover"
              onError={(e) => {
                // If image fails to load, hide broken img tag so initials show
                (e.target as HTMLElement).style.display = "none";
              }}
            />
          ) : (
            <span className="text-xs font-mono font-bold">{initials}</span>
          )}
        </button>
      </div>
    </header>
  );
}

export default Header;
