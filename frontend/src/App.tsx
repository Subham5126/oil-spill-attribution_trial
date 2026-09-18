import React, { useState, useEffect } from "react";
import { Sidebar, NavPath } from "./components/Sidebar";
import { Header } from "./components/Header";
import { NotificationsModal } from "./components/NotificationsModal";
import { DossierExportModal } from "./components/DossierExportModal";
import { ToastProvider } from "./components/ToastNotification";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { Investigation, UserProfile } from "./types";
import { getInvestigations, getInvestigation, getUserProfile } from "./services/api";

// Pages
import { DashboardPage } from "./pages/DashboardPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { NewInvestigationPage } from "./pages/NewInvestigationPage";
import { InvestigationHistoryPage } from "./pages/InvestigationHistoryPage";
import { LiveInvestigationsPage } from "./pages/LiveInvestigationsPage";
import { EvidenceLibraryPage } from "./pages/EvidenceLibraryPage";
import { MapExplorerPage } from "./pages/MapExplorerPage";
import { VesselIntelligencePage } from "./pages/VesselIntelligencePage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { SystemStatusPage } from "./pages/SystemStatusPage";
import { AnalysisProcessPage } from "./pages/AnalysisProcessPage";
import { SpillGeometryPage } from "./pages/SpillGeometryPage";
import { DriftAnalysisPage } from "./pages/DriftAnalysisPage";
import { VesselAnalysisPage } from "./pages/VesselAnalysisPage";
import { VesselDetailPage } from "./pages/VesselDetailPage";
import { SatelliteDetailPage } from "./pages/SatelliteDetailPage";
import { LiveGISMapPage } from "./pages/LiveGISMapPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { LoginPage } from "./pages/LoginPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { ProfilePage } from "./pages/ProfilePage";
import { AdminUsersPage } from "./pages/AdminUsersPage";

export function AppContent() {
  const { isAuthenticated, isLoading: isAuthLoading, user: authUser, logout } = useAuth();
  const [currentPath, setCurrentPath] = useState<NavPath>("dashboard");
  const [showNotifications, setShowNotifications] = useState(false);
  const [showDossierExport, setShowDossierExport] = useState(false);
  const [activeInvestigationId, setActiveInvestigationId] = useState<string | null>(null);
  const [activeInvestigation, setActiveInvestigation] = useState<Investigation | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("oiltrace_sidebar_collapsed") === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    getUserProfile().then((p) => setUserProfile(p)).catch(() => {});
  }, []);

  // ── Auth guard ─────────────────────────────────────────────────────────────
  // While the initial /api/auth/me call is in flight, show a neutral loading screen.
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-[#070f1a] flex items-center justify-center">
        <div className="text-slate-500 font-mono text-sm animate-pulse">Verifying session…</div>
      </div>
    );
  }

  // Unauthenticated — always show login regardless of currentPath
  if (!isAuthenticated) {
    return (
      <LoginPage
        onLoginSuccess={() => {
          // Force re-render by resetting to dashboard after successful login
          setCurrentPath("dashboard");
        }}
      />
    );
  }
  // ──────────────────────────────────────────────────────────────────────────

  const handleToggleSidebar = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("oiltrace_sidebar_collapsed", String(next));
      } catch {}
      return next;
    });
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        handleToggleSidebar();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Do NOT auto-select an active investigation on application launch.
  // The user remains on the clean global Dashboard until an investigation is explicitly selected.
  useEffect(() => {
    // Initial warmup / cache load without forcing active selection
    getInvestigations().catch(() => {});
  }, []);

  useEffect(() => {
    if (activeInvestigationId) {
      getInvestigation(activeInvestigationId).then((inv) => {
        if (inv) setActiveInvestigation(inv);
      });
    }
  }, [activeInvestigationId]);

  // Parse URL on mount and handle browser history
  useEffect(() => {
    const parseUrl = () => {
      const rawPath = window.location.pathname;
      const path = decodeURIComponent(rawPath).toLowerCase();
      if (
        path === "/new-incident" ||
        path === "/new-investigation" ||
        path === "/investigations/new" ||
        path === "/investigations/new-incident" ||
        path === "/investigations/new-investigation" ||
        path === "/investigations/<new-investigation>" ||
        path.startsWith("/investigations/new") ||
        path.includes("<new")
      ) {
        setCurrentPath("new-investigation");
        return;
      }
      const invMatch = rawPath.match(/\/investigations\/([^\/]+)/);
      if (invMatch && invMatch[1]) {
        setActiveInvestigationId(invMatch[1]);
        setCurrentPath("investigation-detail");
      } else if (rawPath === "/investigations" || rawPath === "/incidents") {
        setCurrentPath("investigations");
      }
    };
    parseUrl();

    const handlePopState = () => parseUrl();
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const handleNavigate = (path: NavPath) => {
    if (path === "dashboard") {
      setActiveInvestigationId(null);
      setActiveInvestigation(null);
      try {
        window.history.pushState(null, "", "/");
      } catch {}
    }
    setCurrentPath(path);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSelectInvestigation = (id: string) => {
    setActiveInvestigationId(id);
    setCurrentPath("investigation-detail");
    try {
      window.history.pushState(null, "", `/investigations/${id}`);
    } catch {}
  };

  return (
    <div className="min-h-screen bg-surface text-on-surface font-sans flex overflow-x-hidden">
      {/* Fixed Navigation Sidebar */}
      <Sidebar
        currentPath={currentPath}
        onNavigate={handleNavigate}
        userProfile={userProfile}
        userRole={authUser?.role ?? null}
        onLogout={logout}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={handleToggleSidebar}
      />

      {/* Main Content Area */}
      <div
        className={`flex-1 flex flex-col ${
          isSidebarCollapsed ? "pl-[68px]" : "pl-sidebar-width"
        } min-w-0 transition-[padding] duration-300 ease-in-out`}
      >
        {/* Fixed Route-Aware Command Header */}
        <Header
          currentPath={currentPath}
          onNavigate={handleNavigate}
          onSelectInvestigation={handleSelectInvestigation}
          onOpenNotifications={() => setShowNotifications(true)}
          activeInvestigation={activeInvestigation}
          userProfile={userProfile}
          isSidebarCollapsed={isSidebarCollapsed}
        />

        {/* Dynamic Route Container */}
        <main className="mt-16 p-space-lg flex-1 flex flex-col min-w-0">
          {currentPath === "dashboard" && (
            <DashboardPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
              activeInvestigationId={activeInvestigationId}
              onSelectInvestigation={handleSelectInvestigation}
            />
          )}

          {(currentPath === "investigations" || currentPath === "incidents") && (
            <InvestigationsPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
              onSelectInvestigation={handleSelectInvestigation}
            />
          )}

          {currentPath === "investigation-detail" && (
            activeInvestigationId ? (
              <InvestigationDetailPage
                investigationId={activeInvestigationId}
                onNavigate={handleNavigate}
                onOpenDossier={() => setShowDossierExport(true)}
              />
            ) : (
              <InvestigationsPage
                onNavigate={handleNavigate}
                onOpenDossier={() => setShowDossierExport(true)}
                onSelectInvestigation={handleSelectInvestigation}
              />
            )
          )}

          {currentPath === "new-investigation" && (
            <NewInvestigationPage
              onNavigate={handleNavigate}
              onSelectInvestigation={handleSelectInvestigation}
            />
          )}

          {currentPath === "investigation-history" && (
            <InvestigationHistoryPage
              onNavigate={handleNavigate}
              onSelectInvestigation={handleSelectInvestigation}
            />
          )}

          {currentPath === "live-investigations" && (
            <LiveInvestigationsPage
              onNavigate={handleNavigate}
              onSelectInvestigation={handleSelectInvestigation}
            />
          )}

          {currentPath === "evidence-library" && (
            <EvidenceLibraryPage
              onNavigate={handleNavigate}
              activeInvestigationId={activeInvestigationId}
              onSelectInvestigation={handleSelectInvestigation}
            />
          )}

          {currentPath === "map-explorer" && (
            <MapExplorerPage
              onNavigate={handleNavigate}
              activeInvestigationId={activeInvestigationId}
              onSelectInvestigation={handleSelectInvestigation}
              onOpenDossier={() => setShowDossierExport(true)}
            />
          )}

          {currentPath === "vessel-intelligence" && (
            <VesselIntelligencePage
              onNavigate={handleNavigate}
              onSelectInvestigation={handleSelectInvestigation}
            />
          )}

          {currentPath === "datasets" && (
            <DatasetsPage onNavigate={handleNavigate} />
          )}

          {currentPath === "system-status" && (
            <SystemStatusPage onNavigate={handleNavigate} />
          )}

          {currentPath === "analysis-process" && (
            <AnalysisProcessPage
              onNavigate={handleNavigate}
              activeInvestigationId={activeInvestigationId}
            />
          )}

          {(currentPath === "spill-analysis" || currentPath === "geometry-detail") && (
            <SpillGeometryPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
              activeInvestigationId={activeInvestigationId}
            />
          )}

          {currentPath === "drift-analysis" && (
            <DriftAnalysisPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
              activeInvestigationId={activeInvestigationId}
            />
          )}

          {currentPath === "vessel-analysis" && (
            <VesselAnalysisPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
              activeInvestigationId={activeInvestigationId}
            />
          )}

          {currentPath === "vessel-detail" && (
            <VesselDetailPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
            />
          )}

          {currentPath === "satellite-detail" && (
            <SatelliteDetailPage onNavigate={handleNavigate} />
          )}

          {currentPath === "live-map" && (
            <LiveGISMapPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
              activeInvestigationId={activeInvestigationId}
            />
          )}

          {(currentPath === "reports" || currentPath === "report-detail") && (
            <ReportsPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
              activeInvestigationId={activeInvestigationId}
            />
          )}

          {currentPath === "settings" && (
            <SettingsPage onNavigate={handleNavigate} />
          )}

          {currentPath === "profile" && (
            <ProfilePage
              onNavigate={handleNavigate}
              onProfileUpdated={(updated) => setUserProfile(updated)}
            />
          )}

          {currentPath === "admin-users" && (
            <AdminUsersPage onNavigate={handleNavigate} />
          )}
        </main>
      </div>

      {/* Global Notifications Modal */}
      <NotificationsModal
        isOpen={showNotifications}
        onClose={() => setShowNotifications(false)}
        onNavigate={handleNavigate}
      />

      {/* Global Legal Dossier Export Modal */}
      <DossierExportModal
        isOpen={showDossierExport}
        onClose={() => setShowDossierExport(false)}
      />
    </div>
  );
}

export function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ToastProvider>
  );
}

export default App;


