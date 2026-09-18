const PRODUCT_GROUP_LABELS: Record<string, string> = {
  DEPOSIT: "예금",
  SAVINGS: "적금",
  DEMAND_DEPOSIT: "입출금",
  EVENT: "이벤트",
  LOAN: "대출",
  INVESTMENT: "투자",
};

const ADVERTISEMENT_TYPE_LABELS: Record<string, string> = {
  BRANCH_FLYER: "영업점 전단",
  NOTICE: "안내문",
  MOBILE_BANNER: "모바일 배너",
  WEB_BANNER: "웹 배너",
  WEB_PRODUCT_PAGE: "웹 상품상세 페이지",
  EVENT_PAGE: "이벤트 페이지",
  SOCIAL_MEDIA: "SNS 게시물",
  VIDEO: "영상 광고",
  EMAIL: "이메일",
  OUTDOOR: "옥외 광고",
  PRINT_AD: "인쇄 광고",
  PUSH: "앱 푸시",
  SMS: "문자 메시지",
  ALIMTALK: "알림톡",
  OTHER: "기타",
};

const CHANNEL_LABELS: Record<string, string> = {
  MOBILE_APP: "모바일 앱",
  INTERNET_BANKING: "인터넷뱅킹",
  BRANCH: "영업점",
};

const FILE_TYPE_LABELS: Record<string, string> = {
  ADVERTISEMENT: "광고 원본",
  PRODUCT_DESCRIPTION: "상품설명서",
  TERMS: "약관",
  ADDITIONAL: "추가 첨부",
};

const RISK_LABELS: Record<string, string> = {
  HIGH: "높음",
  MEDIUM: "중간",
  LOW: "낮음",
};

const REVIEW_TYPE_LABELS: Record<string, string> = {
  REQUIRED_PHRASE: "필수 문구",
  INTEREST_RATE: "금리·조건",
  MISLEADING_EXPRESSION: "과장·오인 표현",
  PRODUCT_CONSISTENCY: "상품 정합성",
  VISIBILITY: "시인성",
  OCR_QUALITY: "문구 판독 품질",
};

const ANNOTATION_STATUS_LABELS: Record<string, string> = {
  LOCATED: "위치 확인됨",
  PARTIALLY_LOCATED: "일부 위치 확인",
  LOW_CONFIDENCE: "위치 확인 필요",
  UNAVAILABLE: "위치 정보 없음",
};

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  LAW: "법령",
  REGULATION: "감독 규정",
  INTERNAL_STANDARD: "내부 기준",
  GUIDELINE: "가이드라인",
  MANUAL: "업무 매뉴얼",
  REVIEW_CASE: "심의 사례",
  TEMPLATE: "문구 템플릿",
  PRODUCT_STANDARD: "상품 기준",
};

const RULE_TYPE_LABELS: Record<string, string> = {
  REQUIRED: "필수",
  PROHIBITED: "금지",
  RECOMMENDED: "권고",
  REFERENCE: "참고",
};

export function productGroupLabel(value: string): string {
  return PRODUCT_GROUP_LABELS[value] ?? "기타 상품";
}

export function advertisementTypeLabel(value: string): string {
  return ADVERTISEMENT_TYPE_LABELS[value] ?? "기타 광고";
}

export function channelLabel(value: string): string {
  return CHANNEL_LABELS[value] ?? "기타 채널";
}

export function fileTypeLabel(value: string): string {
  return FILE_TYPE_LABELS[value] ?? "첨부파일";
}

export function riskLevelLabel(value: string): string {
  return RISK_LABELS[value] ?? "확인 필요";
}

export function reviewTypeLabel(value: string): string {
  return REVIEW_TYPE_LABELS[value] ?? "기타 검토";
}

export function annotationStatusLabel(value: string): string {
  return ANNOTATION_STATUS_LABELS[value] ?? "위치 확인 필요";
}

export function evidenceTypeLabel(value: string): string {
  return EVIDENCE_TYPE_LABELS[value] ?? "기타 기준";
}

export function ruleTypeLabel(value: string): string {
  return RULE_TYPE_LABELS[value] ?? "기준 확인 필요";
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes.toLocaleString("ko-KR")}바이트`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}
