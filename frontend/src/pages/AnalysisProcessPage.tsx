import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { PipelineSteps } from "../components/PipelineSteps";
import { EndToEndResult } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  CheckCircle2,
  Terminal,
  Activity,
  ArrowRight,
  ShieldCheck,
  FileText,
  Clock,
  Database,
} from "lucide-react";

interface AnalysisProcessPageProps {
  onNavigate: (path: NavPath) => void;
}

export function AnalysisProcessPage({ onNavigate }: AnalysisProcessPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    getActivePipelineResult().then(setPipelineData);
  }, []);

  const execution = pipelineData.pipeline_execution;

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <button
              type="button"
              onClick={() => onNavigate("investigations")}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              Investigations
            </button>
            <span className="text-outline-variant">/</span>
            <span className="text-on-surface font-semibold">{pipelineData.spill_metadata.spill_id}</span>
            <span className="text-outline-variant">/</span>
            <span className="text-primary font-bold">Pipeline Stream</span>
          </div>
          <div className="flex items-center gap-3">
            <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
              Integrated Pipeline Execution
            </h1>
            <span className="px-2.5 py-1 rounded bg-emerald-600 text-white font-bold text-xs shadow-sm">
              Status: {execution.status}
            </span>
          </div>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Full end-to-end execution of Member 3 GIS, Member 4 Ocean/Drift, and Member 5 AIS/Attribution.
          </p>
        </div>

        {/* Action Button */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <button
            type="button"
            onClick={() => onNavigate("vessel-analysis")}
            className="flex items-center gap-space-xs px-space-lg py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
          >
            <span>Inspect Suspect Ranking</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 8-Stage Pipeline Graphic */}
      <PipelineSteps currentStep={8} />

      {/* Pipeline Stages Execution Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        {/* Stage Statuses */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-3">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            Workflow Stage Statuses
          </h3>
          <div className="space-y-2.5 font-mono text-xs">
            {Object.entries(execution.stage_statuses).map(([stage, status]) => (
              <div
                key={stage}
                className="flex items-center justify-between p-2.5 rounded-lg bg-surface-container-low"
              >
                <span className="font-semibold text-on-surface">{stage}</span>
                <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold border border-emerald-300 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Execution Notes */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-3">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
            <Terminal className="w-4 h-4 text-sky-500" />
            Execution Trace &amp; Audit Logs
          </h3>
          <div className="space-y-2 font-mono text-xs">
            {execution.notes.map((note, idx) => (
              <div
                key={idx}
                className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-secondary flex items-start gap-2"
              >
                <span className="text-primary font-bold">[{idx + 1}]</span>
                <span>{note}</span>
              </div>
            ))}
          </div>
          <div className="pt-2 text-[11px] text-secondary font-mono flex items-center justify-between">
            <span>Execution Timestamp:</span>
            <span className="text-on-surface font-bold">
              {execution.execution_timestamp}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
