import React from "react";
import { NavPath } from "./Sidebar";
import { X, Bell, AlertTriangle, CheckCircle2, Satellite, Ship } from "lucide-react";

interface NotificationsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (path: NavPath) => void;
}

export const NotificationsModal: React.FC<NotificationsModalProps> = ({
  isOpen,
  onClose,
  onNavigate,
}) => {
  if (!isOpen) return null;

  const notifications = [
    {
      id: "n1",
      title: "New Hydrocarbon Anomaly Detected",
      time: "10 mins ago",
      desc: "Sentinel-1 SAR C-Band confirmed dark slick #SAR-20250101-IND-0042 in Arabian Sea.",
      icon: Satellite,
      type: "alert",
      path: "spill-analysis" as NavPath,
    },
    {
      id: "n2",
      title: "Drift Hindcasting Completed",
      time: "6 mins ago",
      desc: "Probable origin localized at 18.5253°N, 72.5032°E with 95% empirical dispersion radius of 1.885 km.",
      icon: CheckCircle2,
      type: "success",
      path: "drift-analysis" as NavPath,
    },
    {
      id: "n3",
      title: "High Suspect Attribution Correlated",
      time: "2 mins ago",
      desc: "PACIFIC VOYAGER (MMSI 413999001) matched with 95.4% multi-criteria confidence score.",
      icon: Ship,
      type: "priority",
      path: "vessel-analysis" as NavPath,
    },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden">
        <div className="p-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-sky-400" />
            <h3 className="font-bold text-white text-sm">System &amp; Attribution Alerts</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 divide-y divide-slate-800 space-y-3 text-xs">
          {notifications.map((n) => {
            const Icon = n.icon;
            return (
              <div
                key={n.id}
                onClick={() => {
                  onNavigate(n.path);
                  onClose();
                }}
                className="pt-2.5 first:pt-0 flex items-start gap-3 cursor-pointer hover:bg-slate-800/40 p-2 rounded-lg transition-colors"
              >
                <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 text-sky-400">
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-200">{n.title}</span>
                    <span className="text-[10px] text-slate-500 font-mono">{n.time}</span>
                  </div>
                  <p className="text-slate-400 mt-0.5 leading-relaxed">{n.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
