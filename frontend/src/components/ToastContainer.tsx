import React from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';
import { ToastMessage } from '../types';

interface ToastProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md w-full pointer-events-none">
      {toasts.map((toast) => {
        const isError = toast.type === 'error';
        const isSuccess = toast.type === 'success';
        const isWarning = toast.type === 'warning';

        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-3 p-4 rounded-lg border shadow-xl transition-all duration-300 animate-slide-in ${
              isError
                ? 'bg-[#181116] border-terminal-red/40 text-rose-200'
                : isSuccess
                ? 'bg-[#0E1A16] border-terminal-green/40 text-emerald-200'
                : isWarning
                ? 'bg-[#1B1910] border-terminal-amber/40 text-amber-200'
                : 'bg-[#101724] border-terminal-cyan/40 text-cyan-200'
            }`}
          >
            <div className="mt-0.5 shrink-0">
              {isError && <AlertCircle className="w-5 h-5 text-terminal-red" />}
              {isSuccess && <CheckCircle2 className="w-5 h-5 text-terminal-green" />}
              {isWarning && <AlertTriangle className="w-5 h-5 text-terminal-amber" />}
              {!isError && !isSuccess && !isWarning && <Info className="w-5 h-5 text-terminal-cyan" />}
            </div>

            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-white tracking-wide">{toast.title}</h4>
              <p className="text-xs mt-1 text-slate-300 leading-relaxed break-words">{toast.message}</p>
            </div>

            <button
              onClick={() => onDismiss(toast.id)}
              className="text-slate-400 hover:text-white transition-colors p-1 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
