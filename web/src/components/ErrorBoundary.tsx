import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  fallback: (error: Error) => ReactNode;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Keeps one failing part (for example a map in a browser without WebGL) from
// blanking the whole page.
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("Sikka view error", error.message, info.componentStack?.length ?? 0);
  }

  override render(): ReactNode {
    return this.state.error ? this.props.fallback(this.state.error) : this.props.children;
  }
}
