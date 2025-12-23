import React from "react";

interface ErrorBoundaryState {
  hasError: boolean;
  message?: string;
}

export class ErrorBoundary extends React.Component<React.PropsWithChildren<{}>, ErrorBoundaryState> {
  constructor(props: React.PropsWithChildren<{}>) {
    super(props);
    this.state = { hasError: false, message: undefined };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error?.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("UI ErrorBoundary caught", error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, message: undefined });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-[#f5f7fb] px-6">
          <div className="max-w-md w-full text-center bg-white/80 backdrop-blur-xl p-8 rounded-2xl shadow-lg">
            <h1 className="text-2xl font-semibold mb-2">Something went wrong</h1>
            <p className="text-sm text-[#475569] mb-4">
              {this.state.message || "The page encountered an error. Please reload and try again."}
            </p>
            <button
              onClick={this.handleRetry}
              className="px-4 py-2 rounded-lg bg-[#4169E1] text-white shadow hover:bg-[#3355c0] transition"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
