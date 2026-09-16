import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertOctagon, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error caught by ErrorBoundary:", error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.href = "/";
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
          <div className="max-w-xl w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl flex flex-col items-center text-center">
            <div className="w-14 h-14 rounded-full bg-rose-950/60 border border-rose-800/80 flex items-center justify-center mb-4 text-rose-500">
              <AlertOctagon className="w-8 h-8" />
            </div>
            <h1 className="text-xl font-bold text-slate-100 mb-2">
              System Interface Error
            </h1>
            <p className="text-sm text-slate-400 mb-6">
              A UI rendering error occurred while loading maritime attribution telemetry.
            </p>
            <div className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-left font-mono text-xs text-rose-400 overflow-x-auto mb-6 max-h-40">
              {this.state.error?.message || "Unknown rendering exception"}
            </div>
            <button
              type="button"
              onClick={this.handleReset}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold text-sm transition-colors cursor-pointer shadow-lg shadow-sky-600/20"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Reload Command Hub</span>
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
