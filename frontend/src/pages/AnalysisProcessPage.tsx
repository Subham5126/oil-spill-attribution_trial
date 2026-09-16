import React, { useState, useEffect, useRef } from "react";
import { NavPath } from "../components/Sidebar";
import { PipelineSteps } from "../components/PipelineSteps";
import { ForensicPdfButton } from "../components/ForensicPdfButton";
import { EndToEndResult } from "../types";
import {
  getActivePipelineResult,
  getInvestigationStatus,
  getReportDownloadUrl,
  runInvestigationPipeline,
} from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  CheckCircle2,
  Terminal,
  Activity,
  ArrowRight,
  ShieldCheck,
  FileText,
  Clock,
  Loader2,
  AlertTriangle,
  Download,
  Maximize2,
  Ship,
  RotateCcw,
} from "lucide-react";

interface AnalysisProcessPageProps {
  onNavigate: (path: NavPath) => void;
  activeInvestigationId?: string | null;
}

export function AnalysisProcessPage({ onNavigate, activeInvestigationId }: AnalysisProcessPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [liveStatus, setLiveStatus] = useState<string>("RUNNING");
  const [stageStatuses, setStageStatuses] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<string[]>([]);
  const [progress, setProgress] = useState<number>(0);
  const [isDone, setIsDone] = useState<boolean>(false);
  const [isRedirecting, setIsRedirecting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const hasRedirectedRef = useRef(false);
  const isInitialMount = useRef(true);

  useEffect(() => {
    let interval: any = null;
    let redirectTimer: any = null;

    const poll = async () => {
      try {
        if (activeInvestigationId) {
          const st = await getInvestigationStatus(activeInvestigationId);
          const currentStatus = st.status || "RUNNING";
          setLiveStatus(currentStatus);
          setStageStatuses(st.stage_statuses || {});
          setNotes(st.notes || []);
          setProgress(st.progress_percentage || 0);

          if (currentStatus === "COMPLETED" || currentStatus === "PASS") {
            setIsDone(true);
            clearInterval(interval);
            const res = await getActivePipelineResult(activeInvestigationId);
            setPipelineData(res);

            // AUTO-REDIRECT GUARD:
            // Only trigger automatic redirection when transitioning to completed during active monitoring.
            // Avoid looping if the user manually navigates back.
            if (!hasRedirectedRef.current && !isInitialMount.current) {
              hasRedirectedRef.current = true;
              setIsRedirecting(true);
              redirectTimer = setTimeout(() => {
                onNavigate("reports");
              }, 1200);
            }
          } else if (
            currentStatus === "FAILED" ||
            currentStatus.startsWith("BLOCKED") ||
            st.error
          ) {
            setIsDone(true);
            clearInterval(interval);
            setErrorMessage(st.error || `Pipeline halted: ${currentStatus}`);
          }
        } else {
          const res = await getActivePipelineResult();
          setPipelineData(res);
          setLiveStatus(res.pipeline_execution.status);
          setStageStatuses(res.pipeline_execution.stage_statuses);
          setNotes(res.pipeline_execution.notes);
          setProgress(100);
          setIsDone(true);
        }
      } catch (e: any) {
        console.warn("Polling error:", e);
      } finally {
        isInitialMount.current = false;
      }
    };

    poll();
    interval = setInterval(poll, 1500);

    return () => {
      clearInterval(interval);
      if (redirectTimer) clearTimeout(redirectTimer);
    };
  }, [activeInvestigationId, onNavigate]);

  const handleRetry = async () => {
    if (!activeInvestigationId) return;
    setErrorMessage(null);
    setIsDone(false);
    setProgress(5);
    setLiveStatus("RUNNING");
    try {
      await runInvestigationPipeline(activeInvestigationId, { sync: false });
    } catch (err: any) {
      setErrorMessage(err.message || "Retry failed");
    }
  };

  const currentStep = progress >= 100 ? 8 : Math.max(1, Math.floor((progress / 100) * 8));

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Auto-Redirect Toast Notification */}
      {isRedirecting && (
        <div className="p-4 rounded-xl bg-emerald-600 text-white shadow-lg flex items-center justify-between gap-3 animate-pulse">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-200 shrink-0" />
            <div>
              <span className="font-bold text-sm">Pipeline Execution Completed Successfully!</span>
              <p className="text-xs text-emerald-100 mt-0.5">
                Automatically redirecting to official MARPOL Forensic Report...
              </p>
            </div>
          </div>
          <Loader2 className="w-5 h-5 animate-spin text-white" />
        </div>
      )}

      {/* Failure / Blocked Alert Card */}
      {errorMessage && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-sm text-rose-800">Pipeline Execution Blocked / Failed</span>
              <p className="text-xs text-rose-700 mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => onNavigate("investigations")}
              className="px-3 py-1.5 rounded-lg bg-surface-container-lowest border border-rose-300 hover:bg-rose-100 transition-colors text-xs font-semibold cursor-pointer"
            >
              Back to Cases
            </button>
            <button
              type="button"
              onClick={handleRetry}
              className="px-3 py-1.5 rounded-lg bg-rose-600 text-white hover:bg-rose-700 transition-colors text-xs font-bold shadow-xs cursor-pointer flex items-center gap-1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Retry Pipeline</span>
            </button>
          </div>
        </div>
      )}

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
            <span className="text-on-surface font-semibold">
              {activeInvestigationId || pipelineData.spill_metadata.spill_id}
            </span>
            <span className="text-outline-variant">/</span>
            <span className="text-primary font-bold">Execution Stream</span>
          </div>
          <div className="flex items-center gap-3">
            <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
              Integrated Pipeline Execution
            </h1>
            <span
              className={`px-2.5 py-1 rounded font-bold text-xs shadow-sm flex items-center gap-1.5 ${
                liveStatus === "COMPLETED" || liveStatus === "PASS"
                  ? "bg-emerald-600 text-white"
                  : liveStatus === "FAILED" || liveStatus.startsWith("BLOCKED")
                  ? "bg-rose-600 text-white"
                  : "bg-amber-500 text-white animate-pulse"
              }`}
            >
              {!isDone && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>Status: {liveStatus}</span>
            </span>
          </div>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Full end-to-end execution of SAR Ingestion, AI Segmentation, GIS Geometry, Copernicus Hydrodynamic Drift, and AIS Vessel Attribution.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-space-sm flex-wrap">
          {isDone && (liveStatus === "COMPLETED" || liveStatus === "PASS") && (
            <button
              type="button"
              onClick={() => onNavigate("reports")}
              className="flex items-center gap-space-xs px-space-lg py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition-colors font-label-md text-label-md font-bold cursor-pointer shadow-sm"
            >
              <FileText className="w-4 h-4" />
              <span>View Forensic Report</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          )}

          <button
            type="button"
            onClick={() => onNavigate("dashboard")}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-label-md cursor-pointer border border-surface-container"
          >
            <Maximize2 className="w-4 h-4 text-primary" />
            <span>Command Overview</span>
          </button>
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

      {/* Progress Bar */}
      <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm space-y-2">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="font-bold text-on-surface flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            Execution Lifecycle Progress: {progress}%
          </span>
          <span className="text-secondary">{isDone ? "Execution Finished" : "Processing Stage..."}</span>
        </div>
        <div className="w-full bg-surface-container-high rounded-full h-2.5 overflow-hidden">
          <div
            className="bg-primary h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          ></div>
        </div>
      </div>

      {/* 8-Stage Pipeline Graphic */}
      <PipelineSteps currentStep={currentStep} />

      {/* Pipeline Stages Execution Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        {/* Stage Statuses */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-3">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            Scientific Workflow Stages
          </h3>
          <div className="space-y-2.5 font-mono text-xs">
            {Object.entries(stageStatuses).map(([stage, status]) => {
              const isPass = status === "COMPLETED" || status === "PASS";
              const isFail = status.startsWith("FAILED");
              const isRunning = status === "RUNNING";

              return (
                <div
                  key={stage}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-surface-container-low"
                >
                  <span className="font-semibold text-on-surface">{stage}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold border flex items-center gap-1 ${
                      isPass
                        ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                        : isFail
                        ? "bg-rose-100 text-rose-800 border-rose-300"
                        : isRunning
                        ? "bg-sky-100 text-sky-800 border-sky-300 animate-pulse"
                        : "bg-surface-container text-secondary border-surface-container-high"
                    }`}
                  >
                    {isPass && <CheckCircle2 className="w-3.5 h-3.5" />}
                    {isRunning && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    {isFail && <AlertTriangle className="w-3.5 h-3.5" />}
                    {status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Execution Notes */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-3">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
            <Terminal className="w-4 h-4 text-sky-500" />
            Execution Trace &amp; Audit Logs
          </h3>
          <div className="space-y-2 font-mono text-xs max-h-96 overflow-y-auto pr-1">
            {notes.map((note, idx) => (
              <div
                key={idx}
                className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-secondary flex items-start gap-2"
              >
                <span className="text-primary font-bold">[{idx + 1}]</span>
                <span className="break-all">{note}</span>
              </div>
            ))}
          </div>
          {activeInvestigationId && isDone && (
            <div className="pt-2 border-t border-surface-container-low flex items-center justify-between">
              <span className="text-xs text-secondary font-mono">11-Section Evidence Dossier:</span>
              <ForensicPdfButton
                investigationId={activeInvestigationId}
                variant="primary"
                showViewOption={true}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

