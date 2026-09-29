export type ExtractionStatus = {
  version: "operational-extraction-status-v1";
  status: string;
  accuracy_verified: false;
  files: Array<{asset_id: string | null; file_name: string | null; status: string; issues: string[];
    pages: Array<{page_no: number; evidence_page_no: number; status: string; issues: string[]}>}>;
};

const STATES: Record<string, string> = {FAILED: "추출 실패", CHECK_REQUIRED: "추출 확인필요", EXTRACTED: "텍스트 추출됨", UNRECORDED: "추출 상태 기록 없음"};
const ISSUES: Record<string, string> = {
  FILE_EXTRACTION_FAILED: "파일 추출 실패 · 성공 파일은 보존됨",
  PAGE_EXTRACTION_FAILED: "페이지 추출 실패",
  PAGE_STATUS_REVIEW: "파서 처리 상태 확인 필요",
  UNREAD_REGIONS: "미판독 영역 있음",
  EMPTY_PAGE: "추출된 텍스트 없음 · 빈 페이지인지 원본 확인 필요",
  EMPTY_LOCAL_REGION: "빈 추출 영역 있음 · 원본 대조 필요",
  UNCERTAIN_LOCAL_READING: "판독 불확실 · 원본 확인 필요",
  SOURCE_GEOMETRY_MISSING: "원문 좌표 없음 · 텍스트와 위치 확인을 구분",
  UNVERIFIED_RECOVERY_CANDIDATE: "복구 후보 미검증 · 판정 근거로 채택되지 않음",
  PARTIAL_EXTRACTION: "전체 판독 미완료 기록 있음",
};

export function ExtractionStatusPanel({value}: {value?: ExtractionStatus}) {
  const requiresReview = value?.status !== "EXTRACTED";
  return <aside aria-label="파일·페이지별 추출 상태" className={`state-message extraction-status ${requiresReview ? "state-warning" : ""}`}>
    <strong>{STATES[value?.status ?? "UNRECORDED"] ?? "추출 상태 확인 필요"}</strong>
    <p>처리 완료는 추출 내용의 정확성을 보장하지 않습니다. 판독 불확실·부분 누락은 원본과 대조해 주세요.</p>
    {value?.files.length ? <details open={requiresReview}><summary>파일·페이지별 추출 상태</summary><ul>{value.files.map((file, index) => <li key={file.asset_id ?? index}>
      <strong>{file.file_name ?? "광고 파일"} · {STATES[file.status] ?? "상태 확인 필요"}</strong>
      {file.issues.map(code => <p key={code}>{ISSUES[code] ?? "추출 경고 확인 필요"}</p>)}
      {!file.pages.length ? <p>페이지별 기록 없음 · 성공으로 판단하지 않습니다.</p> : <ul>{file.pages.map(page => <li key={page.evidence_page_no}>
        {page.page_no}페이지 · {STATES[page.status] ?? "상태 확인 필요"}
        {page.issues.length ? <span> — {page.issues.map(code => ISSUES[code] ?? "추출 경고 확인 필요").join(" / ")}</span> : null}
      </li>)}</ul>}
    </li>)}</ul></details> : <p>이 회차에는 확인 가능한 파일·페이지별 추출 기록이 없습니다.</p>}
  </aside>;
}
