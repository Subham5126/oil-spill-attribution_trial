import React from "react";
import { CheckCircle2, Circle, ArrowRight } from "lucide-react";

interface PipelineStepsProps {
  currentStep?: number;
}

export const PipelineSteps: React.FC<PipelineStepsProps> = ({ currentStep = 8 }) => {
  const steps = [
    { num: 1, label: "SAR Detect", desc: "Sentinel-1 IW C-Band" },
    { num: 2, label: "AI Segment", desc: "Dark Slick Mask" },
    { num: 3, label: "GIS Measure", desc: "3.927 km² Area" },
    { num: 4, label: "MetOcean", desc: "Copernicus & ERA5" },
    { num: 5, label: "Drift Hindcast", desc: "40 Particles (4h)" },
    { num: 6, label: "Origin Region", desc: "95% Dispersion" },
    { num: 7, label: "AIS Correlate", desc: "Spatial/Temporal Filter" },
    { num: 8, label: "Rank & Dossier", desc: "4-Tier Attribution" },
  ];

  return (
    <div className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md overflow-x-auto">
      <div className="flex items-center justify-between min-w-[760px] gap-2">
        {steps.map((s, idx) => {
          const isDone = s.num <= currentStep;
          const isCurrent = s.num === currentStep;

          return (
            <React.Fragment key={s.num}>
              <div className="flex items-center gap-2">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs shrink-0 transition-colors ${
                    isDone
                      ? "bg-primary text-white shadow-sm"
                      : "bg-slate-800 text-slate-400 border border-slate-700"
                  }`}
                >
                  {isDone ? <CheckCircle2 className="w-4 h-4" /> : s.num}
                </div>
                <div className="flex flex-col">
                  <span
                    className={`font-semibold text-xs leading-tight ${
                      isCurrent
                        ? "text-primary font-bold"
                        : isDone
                        ? "text-slate-200"
                        : "text-slate-500"
                    }`}
                  >
                    {s.label}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono leading-tight">
                    {s.desc}
                  </span>
                </div>
              </div>
              {idx < steps.length - 1 && (
                <ArrowRight className="w-3.5 h-3.5 text-slate-700 shrink-0" />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
