import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import type { AuthSession } from "./auth/context";
import { useAuth } from "./auth/useAuth";
import { ReviewScopedBoundary } from "./components/ReviewScopedBoundary";
import { AdvertisementCreatePage } from "./pages/AdvertisementCreatePage";
import { AdvertisementDetailPage } from "./pages/AdvertisementDetailPage";
import { AdvertisementListPage } from "./pages/AdvertisementListPage";
import { LoginPage } from "./pages/LoginPage";
import { ComparisonPage, M6SupportPage } from "./pages/M6SupportPage";
import { ComplianceQaPage } from "./pages/ComplianceQaPage";
import { ReviewProgressPage } from "./pages/ReviewProgressPage";
import { ReviewCriteriaPage } from "./pages/ReviewCriteriaPage";
import { LegalReferencePage } from "./pages/LegalReferencePage";
import { OperationalReviewHubPage } from "./pages/OperationalReviewHubPage";
import { OperationalSuggestionsPage } from "./pages/OperationalSuggestionsPage";
import { ReviewRequestPage } from "./pages/ReviewRequestPage";
import { ReviewAnnotationsPage, ReviewItemsPage, ReviewSummaryPage } from "./pages/ReviewResultsPage";
import { StandardManagementPage } from "./pages/StandardManagementPage";
import { ValidationDatasetsPage, ValidationEvaluationPage } from "./pages/ValidationPage";
import nhBankLogo from "./assets/brand/nh-bank-logo.png";
import cgInsideLogo from "./assets/brand/cg-inside-logo.png";
import { localAuthBypass, operationalMode } from "./api/operational";

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

type NavigationIconKind = "list" | "create" | "standards" | "quality" | "suggestions" | "law";

function NavigationIcon({ kind }: { kind: NavigationIconKind }) {
  const paths = {
    list: <><path d="M5 6h14M5 12h14M5 18h14" /><path d="M3 6h.01M3 12h.01M3 18h.01" /></>,
    create: <><path d="M12 5v14M5 12h14" /><rect x="3" y="3" width="18" height="18" rx="3" /></>,
    standards: <><path d="M6 4h12v16H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></>,
    quality: <><path d="M4 5h16v14H4z" /><path d="m8 12 2.5 2.5L16 9" /></>,
    suggestions: <><path d="m16 3 5 5-12 12-6 1 1-6zM13 6l5 5" /></>,
    law: <><path d="M12 3v18M6 21h12M4 7h16M6 7l-4 8h8zM18 7l-4 8h8z" /></>,
  } satisfies Record<NavigationIconKind, ReactNode>;

  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[kind]}</svg>;
}

function Shell() {
  const { session, logout } = useAuth();
  const { pathname } = useLocation();
  const inReview = pathname.startsWith("/reviews/");
  const inSuggestions = inReview && pathname.endsWith("/suggestions");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const canCreate = session?.user.roles.some((role) => CREATE_ROLES.has(role));
  const canManageStandards = session?.user.roles.some((role) => STANDARD_ROLES.has(role));
  const canValidate = session?.user.roles.some((role) => VALIDATION_ROLES.has(role));
  return (
    <div className="app-shell">
      <header className="app-header">
        {session ? <Link className="brand" to={homePath(session.user.roles)}><img className="brand-mark brand-mark--inverse" src={nhBankLogo} alt="NH농협은행" /><span><strong>광고심의 적정성 검토</strong><small>광고 검토 업무 시스템</small></span></Link> : <div className="brand"><img className="brand-mark brand-mark--inverse" src={nhBankLogo} alt="NH농협은행" /><span><strong>광고심의 적정성 검토</strong><small>광고 검토 업무 시스템</small></span></div>}
        <div className="header-partners">{session ? <div className="account-context"><span><strong>{session.user.userName}</strong><small>{session.user.departmentName}</small></span>{!localAuthBypass ? <button type="button" className="header-button" onClick={() => void logout()}>로그아웃</button> : null}</div> : null}<img className="partner-mark" src={cgInsideLogo} alt="씨지인사이드" /></div>
      </header>
      <div className={session ? "app-workspace" : "app-workspace app-workspace--public"} data-sidebar-collapsed={session ? sidebarCollapsed : undefined} data-operational={session && operationalMode ? "true" : undefined}>
        {session ? <aside className="app-sidebar">
          <button
            type="button"
            className="sidebar-toggle"
            aria-label={sidebarCollapsed ? "사이드바 펼치기" : "사이드바 접기"}
            aria-expanded={!sidebarCollapsed}
            onClick={() => setSidebarCollapsed((current) => !current)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={sidebarCollapsed ? "m9 18 6-6-6-6" : "m15 18-6-6 6-6"} /></svg>
          </button>
          <nav aria-label="주 탐색">
          <p className="nav-group-label">광고 심의</p>
          <NavLink to="/advertisements" end aria-label="광고물 목록" title="광고물 목록"><NavigationIcon kind="list" /><span className="nav-copy"><span>광고물 목록</span><small>등록·진행 현황</small></span></NavLink>
          {canCreate ? <NavLink to="/advertisements/new" aria-label="광고물 등록" title="광고물 등록"><NavigationIcon kind="create" /><span className="nav-copy"><span>광고물 등록</span><small>파일과 기본정보 등록</small></span></NavLink> : null}
          {operationalMode ? <><NavLink to="/review-results" className={({isActive}) => isActive || (inReview && !inSuggestions) ? "active" : undefined} aria-label="심의 결과" title="심의 결과"><NavigationIcon kind="quality" /><span className="nav-copy"><span>심의 결과</span><small>항목별 판정·원문 확인</small></span></NavLink><NavLink to="/recommendations" className={({isActive}) => isActive || inSuggestions ? "active" : undefined} aria-label="추천 문구" title="추천 문구"><NavigationIcon kind="suggestions" /><span className="nav-copy"><span>추천 문구</span><small>확인·수정 초안</small></span></NavLink><p className="nav-group-label">심의 기준·참고자료</p><NavLink to="/review-criteria" aria-label="심의 기준표" title="심의 기준표"><NavigationIcon kind="standards" /><span className="nav-copy"><span>심의 기준표</span><small>템플릿 원문·검사 기준</small></span></NavLink><NavLink to="/legal-references" aria-label="법령·규정 검색" title="법령·규정 검색"><NavigationIcon kind="law" /><span className="nav-copy"><span>법령·규정 검색</span><small>템플릿에 연결된 근거</small></span></NavLink></> : <>
          {canManageStandards || canValidate ? <p className="nav-group-label">운영 도구</p> : null}
          {canManageStandards ? <NavLink to="/standards" aria-label="기준자료 관리" title="기준자료 관리"><NavigationIcon kind="standards" /><span className="nav-copy"><span>기준자료 관리</span><small>규정·근거 최신화</small></span></NavLink> : null}
          {canValidate ? <NavLink to="/validation/datasets" aria-label="검토 품질 관리" title="검토 품질 관리"><NavigationIcon kind="quality" /><span className="nav-copy"><span>검토 품질 관리</span><small>검증 데이터·평가</small></span></NavLink> : null}</>}
        </nav><p className="sidebar-note"><strong>담당자 판단 원칙</strong>AI 결과는 검토를 지원하며 최종 결정을 대신하지 않습니다.</p></aside> : null}
      <main><Routes>
        <Route path="/login" element={session ? <Navigate to={homePath(session.user.roles)} replace /> : <LoginPage />} />
        <Route element={<ProtectedRoute allowedRoles={ADVERTISEMENT_ROLES} />}>
          <Route path="/advertisements" element={<AdvertisementListPage />} />
          <Route path="/review-criteria" element={operationalMode ? <ReviewCriteriaPage /> : <Navigate to="/advertisements" replace />} />
          <Route path="/review-results" element={operationalMode ? <OperationalReviewHubPage /> : <Navigate to="/advertisements" replace />} />
          <Route path="/recommendations" element={operationalMode ? <OperationalReviewHubPage key="suggestions" suggestions /> : <Navigate to="/advertisements" replace />} />
          <Route path="/legal-references" element={operationalMode ? <LegalReferencePage /> : <Navigate to="/advertisements" replace />} />
          <Route path="/advertisements/:advertisementId" element={<AdvertisementDetailPage />} />
          {/* 검토 화면은 모두 이 경계 아래에 둔다. 경계 밖에 두면 검토 전환 시 이전 검토의
              화면 상태가 남는다. */}
          <Route path="/reviews/:reviewId" element={<ReviewScopedBoundary />}>
            <Route path="status" element={<ReviewProgressPage />} />
            <Route path="results" element={<ReviewSummaryPage />} />
            <Route path="results/items" element={operationalMode ? <Navigate to="../results" replace /> : <ReviewItemsPage />} />
            <Route path="results/annotations" element={operationalMode ? <Navigate to="../results" replace /> : <ReviewAnnotationsPage />} />
            <Route path="results/qa" element={<ComplianceQaPage />} />
            <Route path="support" element={<M6SupportPage />} />
            <Route path="suggestions" element={operationalMode ? <OperationalSuggestionsPage /> : <M6SupportPage />} />
          </Route>
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
