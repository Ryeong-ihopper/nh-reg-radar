import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import type { AuthSession } from "./auth/context";
import { useAuth } from "./auth/useAuth";
import { AdvertisementCreatePage } from "./pages/AdvertisementCreatePage";
import { AdvertisementDetailPage } from "./pages/AdvertisementDetailPage";
import { AdvertisementListPage } from "./pages/AdvertisementListPage";
import { LoginPage } from "./pages/LoginPage";
import { ComparisonPage, M6SupportPage } from "./pages/M6SupportPage";
import { ReviewProgressPage } from "./pages/ReviewProgressPage";
import { ReviewRequestPage } from "./pages/ReviewRequestPage";
import { ReviewAnnotationsPage, ReviewItemsPage, ReviewSummaryPage } from "./pages/ReviewResultsPage";
import { StandardManagementPage } from "./pages/StandardManagementPage";
import { ValidationDatasetsPage, ValidationEvaluationPage } from "./pages/ValidationPage";
import nhBankLogo from "./assets/brand/nh-bank-logo.png";

const ADVERTISEMENT_ROLES = new Set(["PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"]);
const CREATE_ROLES = new Set(["PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER"]);
const STANDARD_ROLES = new Set(["STANDARD_MANAGER", "SYSTEM_ADMIN"]);
const VALIDATION_ROLES = new Set(["COMPLIANCE_REVIEWER", "STANDARD_MANAGER", "SYSTEM_ADMIN"]);

function homePath(roles: string[]): string {
  return roles.some((role) => STANDARD_ROLES.has(role)) && !roles.some((role) => ADVERTISEMENT_ROLES.has(role))
    ? "/standards"
    : "/advertisements";
}

function ProtectedRoute({ allowedRoles }: { allowedRoles: Set<string> }) {
  const { isInitializing, session } = useAuth();
  if (isInitializing) return <div role="status" className="state-message">로그인 상태를 확인하는 중입니다.</div>;
  if (!session) return <Navigate to="/login" replace />;
  if (!session.user.roles.some((role) => allowedRoles.has(role))) {
    return <section><div role="alert" className="state-message state-error access-denied-message"><strong>접근 권한이 없습니다.</strong><p>현재 역할로 사용할 수 없는 기능입니다.</p></div></section>;
  }
  return <Outlet />;
}

function Shell() {
  const { session, logout } = useAuth();
  const canCreate = session?.user.roles.some((role) => CREATE_ROLES.has(role));
  const canManageStandards = session?.user.roles.some((role) => STANDARD_ROLES.has(role));
  const canValidate = session?.user.roles.some((role) => VALIDATION_ROLES.has(role));
  return (
    <div className="app-shell">
      <header className="app-header">
        {session ? <Link className="brand" to={homePath(session.user.roles)}><img className="brand-mark brand-mark--inverse" src={nhBankLogo} alt="NH농협은행" /><span><strong>광고심의 적정성 검토</strong><small>광고 검토 업무 시스템</small></span></Link> : <div className="brand"><span><strong>광고심의 적정성 검토</strong><small>광고 검토 업무 시스템</small></span></div>}
        {session ? <div className="account-context"><span><strong>{session.user.userName}</strong><small>{session.user.departmentName}</small></span><button type="button" className="header-button" onClick={() => void logout()}>로그아웃</button></div> : null}
      </header>
      <div className={session ? "app-workspace" : "app-workspace app-workspace--public"}>
        {session ? <aside className="app-sidebar"><nav aria-label="주 탐색">
          <p className="nav-group-label">광고 심의</p>
          <NavLink to="/advertisements" end aria-label="광고물 목록"><span>광고물 목록</span><small>등록·진행 현황</small></NavLink>
          {canCreate ? <NavLink to="/advertisements/new" aria-label="광고물 등록"><span>광고물 등록</span><small>파일과 기본정보 등록</small></NavLink> : null}
          {canManageStandards || canValidate ? <p className="nav-group-label">운영 도구</p> : null}
          {canManageStandards ? <NavLink to="/standards" aria-label="기준자료 관리"><span>기준자료 관리</span><small>규정·근거 최신화</small></NavLink> : null}
          {canValidate ? <NavLink to="/validation/datasets" aria-label="검토 품질 관리"><span>검토 품질 관리</span><small>검증 데이터·평가</small></NavLink> : null}
        </nav><p className="sidebar-note"><strong>담당자 판단 원칙</strong>AI 결과는 검토를 지원하며 최종 결정을 대신하지 않습니다.</p></aside> : null}
      <main><Routes>
        <Route path="/login" element={session ? <Navigate to={homePath(session.user.roles)} replace /> : <LoginPage />} />
        <Route element={<ProtectedRoute allowedRoles={ADVERTISEMENT_ROLES} />}>
          <Route path="/advertisements" element={<AdvertisementListPage />} />
          <Route path="/advertisements/:advertisementId" element={<AdvertisementDetailPage />} />
          <Route path="/reviews/:reviewId/status" element={<ReviewProgressPage />} />
          <Route path="/reviews/:reviewId/results" element={<ReviewSummaryPage />} />
          <Route path="/reviews/:reviewId/results/items" element={<ReviewItemsPage />} />
          <Route path="/reviews/:reviewId/results/annotations" element={<ReviewAnnotationsPage />} />
          <Route path="/reviews/:reviewId/support" element={<M6SupportPage />} />
          <Route path="/advertisements/:advertisementId/comparisons" element={<ComparisonPage />} />
        </Route>
        <Route element={<ProtectedRoute allowedRoles={CREATE_ROLES} />}>
          <Route path="/advertisements/new" element={<AdvertisementCreatePage />} />
          <Route path="/advertisements/:advertisementId/reviews/new" element={<ReviewRequestPage />} />
        </Route>
        <Route element={<ProtectedRoute allowedRoles={STANDARD_ROLES} />}><Route path="/standards" element={<StandardManagementPage />} /></Route>
        <Route element={<ProtectedRoute allowedRoles={VALIDATION_ROLES} />}><Route path="/validation/datasets" element={<ValidationDatasetsPage />} /><Route path="/validation/evaluations" element={<ValidationEvaluationPage />} /></Route>
        <Route path="/" element={<Navigate to={session ? homePath(session.user.roles) : "/login"} replace />} />
        <Route path="*" element={<section><h2>페이지를 찾을 수 없습니다.</h2><Link to="/">홈으로 이동</Link></section>} />
      </Routes></main></div>
    </div>
  );
}

export function App({ initialSession }: { initialSession?: AuthSession | null }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return <QueryClientProvider client={queryClient}><AuthProvider initialSession={initialSession}><Shell /></AuthProvider></QueryClientProvider>;
}
