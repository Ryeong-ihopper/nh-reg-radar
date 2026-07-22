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
          <div className="fatal-error-content">
            <h1>화면을 불러오지 못했습니다.</h1>
            <p>세션 또는 화면 버전이 만료되었을 수 있습니다. 로그인 화면을 다시 열어 주세요.</p>
            <button
              type="button"
              className="button-secondary"
              onClick={() => window.location.replace(`/login?recovery=${Date.now()}`)}
            >
              로그인 화면으로 다시 열기
            </button>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}
