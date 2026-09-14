import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from "lucide-react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  durationMs?: number;
}

interface ToastContextType {
  showToast: (toastOrType: Omit<Toast, "id"> | ToastType, titleOrMessage?: string, message?: string) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const ToastProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (toastOrType: Omit<Toast, "id"> | ToastType, titleOrMessage?: string, message?: string) => {
      let toastObj: Omit<Toast, "id">;
      if (typeof toastOrType === "string") {
        toastObj = {
          type: toastOrType,
          title: titleOrMessage || "",
          message: message,
        };
      } else {
        toastObj = toastOrType;
      }

      const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const newToast: Toast = { ...toastObj, id };
      setToasts((prev) => [...prev, newToast]);

      const timer = setTimeout(() => {
        removeToast(id);
      }, toastObj.durationMs || 4500);

      return () => clearTimeout(timer);
    },
    [removeToast]
  );

  return (
    <ToastContext.Provider value={{ showToast, removeToast }}>
      {children}
      {/* Toast Overlay Container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none max-w-sm w-full">
        {toasts.map((toast) => {
          const icon =
            toast.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            ) : toast.type === "error" ? (
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
            ) : toast.type === "warning" ? (
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            ) : (
              <Info className="w-5 h-5 text-sky-400 shrink-0" />
            );

          const borderBg =
            toast.type === "success"
              ? "bg-slate-900 border-emerald-900/80 text-emerald-300"
              : toast.type === "error"
              ? "bg-slate-900 border-rose-900/80 text-rose-300"
              : toast.type === "warning"
              ? "bg-slate-900 border-amber-900/80 text-amber-300"
              : "bg-slate-900 border-sky-900/80 text-sky-300";

          return (
            <div
              key={toast.id}
              className={`pointer-events-auto p-4 rounded-xl border shadow-xl flex items-start gap-3 transition-all animate-in slide-in-from-bottom-3 duration-200 ${borderBg}`}
            >
              {icon}
              <div className="flex-1 flex flex-col min-w-0">
                <span className="font-semibold text-sm text-slate-100">{toast.title}</span>
                {toast.message && (
                  <span className="text-xs text-slate-400 mt-0.5 leading-relaxed">{toast.message}</span>
                )}
              </div>
              <button
                type="button"
                onClick={() => removeToast(toast.id)}
                className="text-slate-400 hover:text-slate-200 p-0.5 rounded cursor-pointer transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return {
      showToast: () => {},
      removeToast: () => {},
    };
  }
  return context;
}
