import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

export class AppErrorBoundary extends Component<Props, State> {
  public state: State = { failed: false };

  public static getDerivedStateFromError(): State {
    return { failed: true };
  }

  public componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Application render failed", { name: error.name, componentStack: info.componentStack });
  }

  public render(): ReactNode {
    if (this.state.failed) {
      return (
        <main role="alert" className="fatal-error">
          <h1>화면을 불러오지 못했습니다.</h1>
          <p>잠시 후 다시 시도해 주세요.</p>
        </main>
      );
    }

    return this.props.children;
  }
}
