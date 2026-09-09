import React, { useState } from "react";
import { Sidebar, NavPath } from "./components/Sidebar";
import { Header } from "./components/Header";
import { NotificationsModal } from "./components/NotificationsModal";
import { DossierExportModal } from "./components/DossierExportModal";

// Pages
import { DashboardPage } from "./pages/DashboardPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { NewInvestigationPage } from "./pages/NewInvestigationPage";
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

export function App() {
  const [currentPath, setCurrentPath] = useState<NavPath>("dashboard");
  const [showNotifications, setShowNotifications] = useState(false);
  const [showDossierExport, setShowDossierExport] = useState(false);

  const handleNavigate = (path: NavPath) => {
    setCurrentPath(path);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Login view
  if (currentPath === "login") {
    return <LoginPage onLoginSuccess={() => setCurrentPath("dashboard")} />;
  }

  return (
    <div className="min-h-screen bg-surface text-on-surface font-sans flex">
      {/* Fixed Navigation Sidebar */}
      <Sidebar currentPath={currentPath} onNavigate={handleNavigate} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col pl-sidebar-width min-w-0">
        {/* Fixed Command Header with Prominent Data Mode Badge */}
        <Header
          onNavigate={handleNavigate}
          onOpenNotifications={() => setShowNotifications(true)}
          dataMode="DEMO / SYNTHETIC AIS"
        />

        {/* Dynamic Route Container */}
        <main className="mt-16 p-space-lg flex-1 flex flex-col min-w-0">
          {currentPath === "dashboard" && (
            <DashboardPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
            />
          )}

          {(currentPath === "investigations" || currentPath === "incidents") && (
            <InvestigationsPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
            />
          )}

          {currentPath === "new-investigation" && (
            <NewInvestigationPage onNavigate={handleNavigate} />
          )}

          {currentPath === "analysis-process" && (
            <AnalysisProcessPage onNavigate={handleNavigate} />
          )}

          {(currentPath === "spill-analysis" || currentPath === "geometry-detail") && (
            <SpillGeometryPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
            />
          )}

          {currentPath === "drift-analysis" && (
            <DriftAnalysisPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
            />
          )}

          {currentPath === "vessel-analysis" && (
            <VesselAnalysisPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
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
            />
          )}

          {(currentPath === "reports" || currentPath === "report-detail") && (
            <ReportsPage
              onNavigate={handleNavigate}
              onOpenDossier={() => setShowDossierExport(true)}
            />
          )}

          {currentPath === "settings" && (
            <SettingsPage onNavigate={handleNavigate} />
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

export default App;
