import React from "react";
import { AlertTriangle, Trash2, X } from "lucide-react";

interface ConfirmationModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  confirmLabel?: string;
  cancelText?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
  onConfirm: () => void;
  onClose?: () => void;
  onCancel?: () => void;
  isLoading?: boolean;
  loading?: boolean;
  details?: string;
  children?: React.ReactNode;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  title,
  message,
  confirmText,
  confirmLabel,
  cancelText,
  cancelLabel,
  isDestructive = true,
  onConfirm,
  onClose,
  onCancel,
  isLoading,
  loading,
  details,
  children,
}) => {
  if (!isOpen) return null;

  const actualConfirmText = confirmLabel || confirmText || "Confirm";
  const actualCancelText = cancelLabel || cancelText || "Cancel";
  const handleClose = onCancel || onClose || (() => {});
  const isActionLoading = loading ?? isLoading ?? false;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl flex flex-col gap-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                isDestructive
                  ? "bg-rose-950/70 border border-rose-800/80 text-rose-400"
                  : "bg-amber-950/70 border border-amber-800/80 text-amber-400"
              }`}
            >
              {isDestructive ? <Trash2 className="w-5 h-5" /> : <AlertTriangle className="w-5 h-5" />}
            </div>
            <h3 className="font-bold text-slate-100 text-lg">{title}</h3>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="text-slate-400 hover:text-slate-200 p-1 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-slate-300 leading-relaxed">{message}</p>

        {details && (
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-400 font-mono">
            {details}
          </div>
        )}

        {children}

        <div className="flex items-center justify-end gap-3 mt-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={isActionLoading}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-300 hover:bg-slate-800 transition-colors cursor-pointer disabled:opacity-50"
          >
            {actualCancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isActionLoading}
            className={`px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors cursor-pointer shadow-md disabled:opacity-50 flex items-center gap-2 ${
              isDestructive
                ? "bg-rose-600 hover:bg-rose-700"
                : "bg-primary-container hover:bg-primary text-on-primary"
            }`}
          >
            {isActionLoading ? (
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
            ) : null}
            <span>{actualConfirmText}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
