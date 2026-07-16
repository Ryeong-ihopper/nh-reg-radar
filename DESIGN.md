# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-07-16
- Primary product surfaces: 로그인, 광고물 관리, AI 검토 요청·진행·결과, 기준자료 관리, PoC 검증
- Evidence reviewed: `docs/screen-specification.md`, `docs/screen-api-mapping.md`, `apps/frontend/src/App.tsx`, page components, `apps/frontend/src/styles.css`, existing frontend tests

## Brand
- Personality: 신뢰할 수 있고 차분하며 업무 집중을 돕는 금융 준법 도구
- Trust signals: 명확한 상태·위험도, 일관된 날짜·용어, 과도하지 않은 색, 충분한 여백
- Avoid: 소비자 앱 같은 장식성, 과도한 녹색 면적, 위험 상태를 색만으로 전달하는 UI

## Product goals
- Goals: 검토 흐름의 다음 행동을 명확히 하고, 목록·결과·근거를 빠르게 훑게 하며, 상태와 권한을 안전하게 표현한다.
- Non-goals: 브랜드 마케팅 사이트, 모바일 편집 기능, 새 API/업무 규칙 추가
- Success signals: 주요 화면에서 제목·상태·주요 액션·다음 단계가 한 화면에 보인다.

## Personas and jobs
- Primary personas: 상품부서 담당자, 준법감시 검토자, 기준자료 관리자, PoC 검증 담당자
- User jobs: 광고 등록·요청, 진행 확인, 위험/근거 검토, 기준·검증 데이터 관리
- Key contexts of use: PC/노트북 우선, 장시간 표·문서·근거 검토

## Information architecture
- Primary navigation: 광고물 관리, 기준자료 관리, PoC 검증을 역할 기반 좌측 탐색으로 제공한다.
- Core routes/screens: S-002~S-008, S-014~S-016. 보조 지원 화면은 결과 화면의 행동으로 진입한다.
- Content hierarchy: 페이지 제목/설명 → 상태·주요 CTA → 필터·요약 → 데이터·세부 정보

## Design principles
- 업무 맥락을 먼저 보인다: 제목, 상태, 주요 액션을 고정된 위계로 배치한다.
- 정보 밀도는 유지하되 읽기 부담을 줄인다: 표·패널·상태를 토큰화한다.
- 위험과 진행은 명확하게: 텍스트·색·아이콘 역할을 함께 사용한다.
- Tradeoffs: PC 우선 2열 업무 화면을 유지하고 모바일은 안전한 단일 열 조회로 축소한다.

## Visual language
- Color: 깊은 녹색을 제한된 primary로, 중립 slate와 고대비 status 색을 사용한다.
- Typography: Pretendard/시스템 sans, 14~16px 본문, 명확한 제목 scale.
- Spacing/layout rhythm: 4px 기반, 24px 카드 padding, 넓은 콘텐츠 폭과 좌측 탐색.
- Shape/radius/elevation: 10~16px radius, 얕은 border와 아주 약한 shadow.
- Motion: 160ms 이내의 색·border 전환만 사용하며 reduced motion을 지원한다.
- Imagery/iconography: 외부 아이콘 의존성 없이 텍스트·상태 marker를 사용한다.

## Components
- Existing components to reuse: `RequestState`, `Pagination`, `FileActions`.
- New/changed components: application shell/sidebar, page header, surface/card, status badge, table and form styles.
- Variants and states: primary/secondary/danger buttons, success/warning/error/info panels, selected list rows.
- Token/component ownership: CSS custom properties in `styles.css`.

## Accessibility
- Target standard: WCAG 2.1 AA 수준의 대비·focus visibility.
- Keyboard/focus behavior: 모든 링크/버튼/입력에 3px focus ring 제공.
- Contrast/readability: 본문/경계/상태색은 중립 배경 대비를 유지.
- Screen-reader semantics: 기존 heading, landmark, aria-label을 보존.
- Reduced motion and sensory considerations: motion 감소 환경에서 transition 제거.

## Responsive behavior
- Supported breakpoints/devices: 1024px 이상 업무용 2열, 768px 이하 단일 열.
- Layout adaptations: sidebar는 상단 가로 탐색으로 전환하고 표는 가로 스크롤 유지.
- Touch/hover differences: 버튼 최소 높이 40px, hover 없이도 선택 상태가 보인다.

## Interaction states
- Loading: 상태 패널로 작업 대상과 진행을 설명한다.
- Empty: 다음 행동을 포함한 중립 패널.
- Error: 안전한 일반화 메시지와 재시도.
- Success: 완료/결과 보기 등 다음 행동을 명확히 제공.
- Disabled: 충분한 대비를 유지한 비활성 상태.

## Content voice
- Tone: 간결하고 업무 중심이며 단정하지 않음.
- Terminology: 화면설계서의 화면명과 API 상태 명칭을 유지한다.
- Microcopy rules: 내부 마일스톤·기술 구현명은 사용자 UI에 노출하지 않는다.

## Implementation constraints
- Framework/styling system: React 19, CSS 단일 스타일시트. 로컬 화면 검증은 개발 의존성 Playwright를 사용한다. 한글 webfont는 build-time 개발 의존성으로 번들에 정적 asset만 포함하며, 별도 런타임 패키지 의존성은 두지 않는다.
- Design-token constraints: 기존 클래스 구조를 확장하고 API·route 계약은 변경하지 않는다.
- Performance constraints: 이미지·미리보기 요청 정책을 변경하지 않는다.
- Compatibility constraints: PC/노트북 우선, browser-supported preview 경계 유지.
- Test/screenshot expectations: 기존 접근성 역할 기반 테스트를 유지하고 frontend test/lint/typecheck/build를 통과한다. 인증 정보는 환경변수로만 주입해 `npm run visual:local`로 로그인·업무공간·광고물 등록 화면을 1440px 캡처한다.

## Open questions
- [ ] NH 공식 브랜드 자산·BI 컬러 사용 승인을 받을 경우 brand mark를 교체한다. / owner: 제품 담당 / impact: visual identity
- [ ] 기준 디자인 시안이 제공되면 캡처와의 픽셀 비교 baseline을 추가한다. / owner: 제품·디자인 / impact: visual QA
