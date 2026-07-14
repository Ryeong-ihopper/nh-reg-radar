import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import type { AuthSession } from "./auth/context";
import { useAuth } from "./auth/useAuth";
import { AdvertisementCreatePage } from "./pages/AdvertisementCreatePage";
import { AdvertisementDetailPage } from "./pages/AdvertisementDetailPage";
import { AdvertisementListPage } from "./pages/AdvertisementListPage";
import { LoginPage } from "./pages/LoginPage";
import { ReviewProgressPage } from "./pages/ReviewProgressPage";
import { ReviewRequestPage } from "./pages/ReviewRequestPage";
import { StandardManagementPage } from "./pages/StandardManagementPage";

const ADVERTISEMENT_ROLES = new Set(["PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"]);
const CREATE_ROLES = new Set(["PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER"]);
const STANDARD_ROLES = new Set(["STANDARD_MANAGER", "SYSTEM_ADMIN"]);

function homePath(roles: string[]): string {
  return roles.some((role) => STANDARD_ROLES.has(role)) && !roles.some((role) => ADVERTISEMENT_ROLES.has(role))
    ? "/standards"
    : "/advertisements";
}

function ProtectedRoute({ allowedRoles }: { allowedRoles: Set<string> }) {
  const { session } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  if (!session.user.roles.some((role) => allowedRoles.has(role))) {
    return <section><div role="alert" className="state-message state-error"><strong>접근 권한이 없습니다.</strong><p>현재 역할로 사용할 수 없는 기능입니다.</p></div></section>;
  }
  return <Outlet />;
}

function Shell() {
  const { session, logout } = useAuth();
  return (
    <div className="app-shell">
      <header className="app-header">
        <div><span className="brand-mark" aria-hidden="true">NH</span><h1>광고심의 적정성 검토</h1></div>
        <nav aria-label="주 탐색">
          {session ? <Link to="/advertisements">광고물 목록</Link> : <Link to="/login">로그인</Link>}
          {session?.user.roles.some((role) => CREATE_ROLES.has(role)) ? <Link to="/advertisements/new">광고물 등록</Link> : null}
          {session?.user.roles.some((role) => STANDARD_ROLES.has(role)) ? <Link to="/standards">기준자료 관리</Link> : null}
          {session ? <button type="button" className="header-button" onClick={() => void logout()}>로그아웃</button> : null}
        </nav>
      </header>
      <main><Routes>
        <Route path="/login" element={session ? <Navigate to={homePath(session.user.roles)} replace /> : <LoginPage />} />
        <Route element={<ProtectedRoute allowedRoles={ADVERTISEMENT_ROLES} />}>
          <Route path="/advertisements" element={<AdvertisementListPage />} />
          <Route path="/advertisements/:advertisementId" element={<AdvertisementDetailPage />} />
          <Route path="/reviews/:reviewId/status" element={<ReviewProgressPage />} />
        </Route>
        <Route element={<ProtectedRoute allowedRoles={CREATE_ROLES} />}>
          <Route path="/advertisements/new" element={<AdvertisementCreatePage />} />
          <Route path="/advertisements/:advertisementId/reviews/new" element={<ReviewRequestPage />} />
        </Route>
        <Route element={<ProtectedRoute allowedRoles={STANDARD_ROLES} />}><Route path="/standards" element={<StandardManagementPage />} /></Route>
        <Route path="/" element={<Navigate to={session ? homePath(session.user.roles) : "/login"} replace />} />
        <Route path="*" element={<section><h2>페이지를 찾을 수 없습니다.</h2><Link to="/">홈으로 이동</Link></section>} />
      </Routes></main>
    </div>
  );
}

export function App({ initialSession = null }: { initialSession?: AuthSession | null }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return <QueryClientProvider client={queryClient}><AuthProvider initialSession={initialSession}><Shell /></AuthProvider></QueryClientProvider>;
}
