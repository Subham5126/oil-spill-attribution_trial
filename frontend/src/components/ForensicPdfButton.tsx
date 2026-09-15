import React, { useState, useEffect } from "react";
import { Download, ExternalLink, FileText, Loader2, CheckCircle, AlertTriangle } from "lucide-react";
import { getReportDownloadUrl, getReportViewUrl } from "../services/api";

interface ForensicPdfButtonProps {
  investigationId: string;
  variant?: "primary" | "secondary" | "header" | "compact";
  showViewOption?: boolean;
  className?: string;
}

const GENERATION_STEPS = [
  "Preparing forensic report...",
  "Collecting evidence...",
  "Building maps...",
  "Embedding SAR evidence...",
  "Building attribution analysis...",
  "Finalizing PDF...",
];

export const ForensicPdfButton: React.FC<ForensicPdfButtonProps> = ({
  investigationId,
  variant = "primary",
  showViewOption = true,
  className = "",
}) => {
  const [status, setStatus] = useState<"idle" | "generating" | "ready" | "error">("idle");
  const [stepIndex, setStepIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let timer: any;
    if (status === "generating") {
      timer = setInterval(() => {
        setStepIndex((prev) => (prev < GENERATION_STEPS.length - 1 ? prev + 1 : prev));
      }, 700);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [status]);

  const handleGenerateAndDownload = async () => {
    if (status === "generating") return;

    // If already generated and ready, trigger download directly
    if (status === "ready" && pdfBlobUrl) {
      triggerDownload(pdfBlobUrl);
      return;
    }

    setStatus("generating");
    setStepIndex(0);
    setErrorMessage(null);

    try {
      const url = getReportDownloadUrl(investigationId);
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error("Unable to generate forensic PDF.");
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      setPdfBlobUrl(blobUrl);
      setStatus("ready");

      // Auto trigger initial download
      triggerDownload(blobUrl);
    } catch (err: any) {
      console.error("[PDF_DOWNLOAD_ERROR]", err);
      setStatus("error");
      setErrorMessage(err.message || "Unable to generate forensic PDF.");
    }
  };

  const triggerDownload = (url: string) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = `OILTRACE_${investigationId}_Forensic_Report.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleView = () => {
    const viewUrl = getReportViewUrl(investigationId);
    window.open(viewUrl, "_blank", "noopener,noreferrer");
  };

  if (status === "generating") {
    return (
      <div className={`flex items-center gap-2 px-3.5 py-2 rounded-lg bg-sky-950/40 border border-sky-500/30 text-sky-400 text-xs font-semibold ${className}`}>
        <Loader2 className="w-4 h-4 animate-spin text-sky-400" />
        <span className="font-mono">{GENERATION_STEPS[stepIndex]}</span>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleGenerateAndDownload}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-950/40 border border-rose-500/40 text-rose-400 hover:bg-rose-900/50 text-xs font-semibold transition-colors cursor-pointer ${className}`}
          title={errorMessage || "Click to retry"}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>Retry PDF Generation</span>
        </button>
      </div>
    );
  }

  if (status === "ready") {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={handleGenerateAndDownload}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-md transition-all cursor-pointer"
        >
          <CheckCircle className="w-3.5 h-3.5" />
          <span>Download PDF</span>
        </button>

        {showViewOption && (
          <button
            type="button"
            onClick={handleView}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface border border-surface-container text-xs font-semibold transition-colors cursor-pointer"
            title="Open forensic report in new tab"
          >
            <ExternalLink className="w-3.5 h-3.5 text-sky-400" />
            <span>View PDF</span>
          </button>
        )}
      </div>
    );
  }

  // Idle state styles
  const baseClasses =
    variant === "primary"
      ? "bg-primary text-on-primary hover:bg-primary/90 font-bold shadow-xs"
      : variant === "header"
      ? "bg-surface-container text-on-surface hover:bg-surface-container-high border border-surface-container shadow-xs font-semibold"
      : "bg-surface-container text-on-surface hover:bg-surface-container-high border border-surface-container font-semibold";

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        type="button"
        onClick={handleGenerateAndDownload}
        className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg transition-colors text-xs cursor-pointer ${baseClasses} ${className}`}
      >
        <FileText className="w-3.5 h-3.5 text-sky-400" />
        <span>Download Forensic PDF</span>
      </button>

      {showViewOption && (
        <button
          type="button"
          onClick={handleView}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold border border-surface-container cursor-pointer"
          title="Open forensic report in new tab"
        >
          <ExternalLink className="w-3.5 h-3.5 text-secondary" />
          <span>View PDF</span>
        </button>
      )}
    </div>
  );
};
export default ForensicPdfButton;
