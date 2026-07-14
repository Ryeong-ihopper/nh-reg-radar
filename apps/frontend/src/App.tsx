import { Link, Route, Routes } from "react-router-dom";

function HomePage() {
  return (
    <section aria-labelledby="platform-heading">
      <p className="eyebrow">M1 플랫폼 상태</p>
      <h2 id="platform-heading">광고심의 적정성 검토 플랫폼</h2>
      <p>업무 기능은 각 capability의 계약 게이트를 통과한 뒤 순차적으로 연결됩니다.</p>
    </section>
  );
}

function NotFoundPage() {
  return (
    <section>
      <h2>페이지를 찾을 수 없습니다.</h2>
      <Link to="/">홈으로 이동</Link>
    </section>
  );
}

export function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <span className="brand-mark" aria-hidden="true">
            NH
          </span>
          <h1>광고심의 적정성 검토</h1>
        </div>
        <nav aria-label="주 탐색">
          <Link to="/">홈</Link>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </div>
  );
}
