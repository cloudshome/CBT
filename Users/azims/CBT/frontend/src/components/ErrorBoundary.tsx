import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary caught error]:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#05070c] text-slate-100 flex items-center justify-center p-6 font-mono">
          <div className="max-w-2xl w-full bg-[#0d121d] border border-red-500/40 rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-red-400">
              <AlertTriangle className="w-8 h-8 text-red-500 shrink-0" />
              <div>
                <h1 className="text-lg font-bold text-slate-100">Application Error Encountered</h1>
                <p className="text-xs text-slate-400">A runtime exception prevented CTB from rendering.</p>
              </div>
            </div>

            <div className="bg-[#05070c] border border-red-950 rounded-lg p-4 text-xs overflow-auto max-h-60 text-red-300">
              <p className="font-semibold text-red-400 mb-1">
                {this.state.error?.name}: {this.state.error?.message}
              </p>
              {this.state.error?.stack && (
                <pre className="text-[11px] text-slate-400 whitespace-pre-wrap leading-relaxed">
                  {this.state.error.stack}
                </pre>
              )}
            </div>

            {this.state.errorInfo?.componentStack && (
              <details className="text-xs text-slate-400">
                <summary className="cursor-pointer hover:text-slate-200">Component Hierarchy Stack</summary>
                <pre className="mt-2 p-2 bg-[#05070c] rounded text-[10px] text-slate-500 overflow-auto max-h-40 whitespace-pre-wrap">
                  {this.state.errorInfo.componentStack}
                </pre>
              </details>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={this.handleReset}
                className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold transition-all shadow"
              >
                <RefreshCw className="w-4 h-4" />
                <span>Reload Terminal</span>
              </button>
              <button
                onClick={() => {
                  localStorage.clear();
                  window.location.reload();
                }}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs transition-all"
              >
                Clear Local Storage & Reload
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
