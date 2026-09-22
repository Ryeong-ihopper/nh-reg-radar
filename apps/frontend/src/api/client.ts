import type { components, operations } from "./generated/openapi";

export type UserRole = components["schemas"]["Role"];
export type UserContext = components["schemas"]["UserContext"];
export type LoginResponse = components["schemas"]["AuthTokenResponse"];
export type CodeItem = components["schemas"]["CommonCode"];
export type AdvertisementSummary = components["schemas"]["AdvertisementSummary"];
export type AdvertisementListResponse = components["schemas"]["AdvertisementPage"];
export type AdvertisementFile = components["schemas"]["AdvertisementFile"];
export type AdvertisementDetail = components["schemas"]["AdvertisementDetail"];
export type AdvertisementCreateResponse = components["schemas"]["AdvertisementCreated"];
export type AdvertisementRevision = components["schemas"]["AdvertisementRevision"];
export type FilePreview = components["schemas"]["FilePreview"];
export type ProductGroup = components["schemas"]["ProductGroup"];
export type AdvertisementType = components["schemas"]["AdvertisementType"];
export type EvidenceType = components["schemas"]["EvidenceType"];
export type RuleType = components["schemas"]["RuleType"];
export type Importance = components["schemas"]["Importance"];
export type SearchMode = components["schemas"]["SearchMode"];
export type ReindexScope = components["schemas"]["ReindexScope"];
export type StandardSummary = components["schemas"]["StandardSummary"];
export type StandardListResponse = components["schemas"]["StandardPage"];
export type StandardDetail = components["schemas"]["StandardDetail"];
export type StandardHistoryResponse = components["schemas"]["StandardHistoryPage"];
export type StandardCreateResponse = components["schemas"]["StandardCreated"];
export type StandardUpdateInput = components["schemas"]["UpdateStandardRequest"];
export type StandardReindexInput = components["schemas"]["ReindexStandardRequest"];
export type StandardReindexJob = components["schemas"]["StandardReindexJob"];
export type EvidenceSearchResult = components["schemas"]["EvidenceSearchResult"];
export type EvidenceChunkListResponse = components["schemas"]["EvidenceChunkPage"];
export type ReviewType = components["schemas"]["ReviewType"];
export type ReviewRequestInput = components["schemas"]["CreateReviewRequest"];
export type ReviewAccepted = components["schemas"]["ReviewAccepted"];
export type ReviewProgress = components["schemas"]["ReviewProgress"];
export type ReviewHistory = components["schemas"]["ReviewHistory"];
export type RerunReviewInput = components["schemas"]["RerunReviewRequest"];
export type RerunReviewAccepted = components["schemas"]["RerunReviewAccepted"];
export type ReviewSummary = components["schemas"]["ReviewSummary"];
export type ReviewItemSummary = components["schemas"]["ReviewItemSummary"];
export type ReviewItemPage = components["schemas"]["ReviewItemPage"];
export type ReviewItemDetail = components["schemas"]["ReviewItemDetail"];
export type ReviewAnnotation = components["schemas"]["Annotation"];
export type ReviewAnnotationCollection = components["schemas"]["AnnotationCollection"];
export type ReviewItemSearch = NonNullable<operations["listReviewItems"]["parameters"]["query"]>;
export type ReviewAnnotationSearch = NonNullable<operations["listReviewAnnotations"]["parameters"]["query"]>;
export type Suggestion = components["schemas"]["Suggestion"];
export type SuggestionDecision = components["schemas"]["SuggestionDecision"];
export type SuggestionDecisionInput = components["schemas"]["SuggestionDecisionRequest"];
export type QaQuestionInput = components["schemas"]["QaQuestionRequest"];
export type QaAnswer = components["schemas"]["QaAnswer"];
export type OpinionDraft = components["schemas"]["OpinionDraft"];
export type OpinionDraftInput = components["schemas"]["OpinionDraftRequest"];
export type OpinionDraftUpdateInput = components["schemas"]["OpinionDraftUpdateRequest"];
export type Report = components["schemas"]["Report"];
export type ReportInput = components["schemas"]["ReportRequest"];
export type ReportFormat = components["schemas"]["ReportFormat"];
export type Comparison = components["schemas"]["Comparison"];
export type ComparisonInput = components["schemas"]["ComparisonRequest"];
export type ValidationDataset = components["schemas"]["ValidationDataset"];
export type ValidationDatasetPage = components["schemas"]["ValidationDatasetPage"];
export type ValidationJudgmentsInput = components["schemas"]["CreateValidationJudgmentsRequest"];
export type ValidationJudgmentsCreated = components["schemas"]["ValidationJudgmentsCreated"];
export type ValidationEvaluationInput = components["schemas"]["CreateValidationEvaluationRequest"];
export type ValidationEvaluation = components["schemas"]["ValidationEvaluation"];
export type ValidationMetricCode = components["schemas"]["ValidationMetricCode"];
export type ExcludeReasonCode = components["schemas"]["ExcludeReasonCode"];

export interface AdvertisementCreateInput {
  advertisementName: string;
  productGroup: ProductGroup;
  advertisementType: AdvertisementType;
  channelType?: string;
  departmentId: string;
  memo?: string;
  advertisementFile: File;
  advertisementFiles?: File[];
  productDescriptionFile?: File;
  termsFile?: File;
  additionalFiles?: File[];
}

export interface AdvertisementRevisionInput {
  revisionMemo?: string;
  revisedAdvertisementFile: File;
}

export interface StandardCreateInput {
  title: string;
  evidenceType: EvidenceType;
  productGroup?: ProductGroup;
  advertisementType?: AdvertisementType;
  ruleType: RuleType;
  importance?: Importance;
  effectiveDate?: string;
  expiredDate?: string;
  metadata: Record<string, unknown>;
  content: string;
  sourceFile?: File;
}

export interface ValidationDatasetCreateInput {
  datasetName: string;
  productGroup: ProductGroup;
  advertisementType: AdvertisementType;
  advertisementFile: File;
  productConditionFile?: File;
  humanReviewComment?: string;
  labelJson?: string;
  excluded: boolean;
  excludeReasonCode?: ExcludeReasonCode;
  excludeReasonDetail?: string;
}

export type AdvertisementSearch = NonNullable<operations["listAdvertisements"]["parameters"]["query"]>;
export type StandardSearch = NonNullable<operations["listStandards"]["parameters"]["query"]>;
export type EvidenceSearch = operations["searchEvidences"]["parameters"]["query"];

interface ErrorResponse {
  code?: unknown;
  message?: unknown;
  traceId?: unknown;
}

const ERROR_MESSAGES: Record<string, string> = {
  BAD_REQUEST: "요청값을 확인해 주세요.",
  UNAUTHORIZED: "로그인이 필요합니다.",
  FORBIDDEN: "접근 권한이 없습니다.",
  NOT_FOUND: "요청한 대상을 찾을 수 없습니다.",
  CONFLICT: "현재 상태에서는 요청을 처리할 수 없습니다.",
  RATE_LIMITED: "잠시 후 다시 시도해 주세요.",
  FILE_NOT_SUPPORTED: "지원하지 않는 파일 형식입니다.",
  FILE_READ_FAILED: "파일을 읽지 못했습니다. 파일을 다시 확인해 주세요.",
  FILE_SIZE_EXCEEDED: "파일 용량이 50MB를 초과했습니다.",
  INTERNAL_ERROR: "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
  SEARCH_UNAVAILABLE: "검색 인프라를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  RAG_SEARCH_UNAVAILABLE: "검색 인프라를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  RAG_SEARCH_FAILED: "검색 인프라를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  REFERENCE_METADATA_INVALID: "기준 유형에 필요한 메타데이터를 확인해 주세요.",
  REVIEW_ALREADY_RUNNING: "이미 진행 중인 검토가 있습니다.",
  OCR_UNREADABLE: "문구를 판독하기 어려워 담당자 확인이 필요합니다.",
  HWP_PREVIEW_UNAVAILABLE: "한글 문서 미리보기 서비스를 사용할 수 없습니다. 원본 다운로드로 확인해 주세요.",
  HWP_PREVIEW_FAILED: "한글 문서 미리보기를 만들지 못했습니다. 원본 다운로드로 확인해 주세요.",
  PARSER_LAYOUT_PENDING: "파서 좌표가 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요.",
  PARSER_LAYOUT_UNAVAILABLE: "파서 좌표를 표시할 수 없습니다. 원본 문서는 그대로 확인할 수 있습니다.",
};

export class ApiError extends Error {
  public constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly traceId?: string,
    displayMessage?: string,
  ) {
    // Registration conflicts are actionable (for example, the same source
    // file was already registered).  Keep generic errors generic, but do not
    // hide this safe server explanation behind an unhelpful status message.
    super(code === "CONFLICT" && displayMessage
      ? displayMessage
      : (ERROR_MESSAGES[code] ?? ERROR_MESSAGES.INTERNAL_ERROR));
    this.name = "ApiError";
  }
}

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  return configured ? configured.replace(/\/$/, "") : "/api/v1";
}

export function resolveApiUrl(path: string): string {
  if (path.startsWith("/api/v1/")) {
    return `${apiBaseUrl()}${path.slice("/api/v1".length)}`;
  }
  return `${apiBaseUrl()}${path}`;
}

async function readError(response: Response): Promise<ApiError> {
  let body: ErrorResponse = {};
  try {
    body = (await response.json()) as ErrorResponse;
  } catch {
    // A malformed server error must not be echoed to the user.
  }

  const code = typeof body.code === "string" ? body.code : "INTERNAL_ERROR";
  const traceId = typeof body.traceId === "string" ? body.traceId : undefined;
  const displayMessage = typeof body.message === "string" ? body.message : undefined;
  return new ApiError(response.status, code, traceId, displayMessage);
}

type AuthRefreshHandler = () => Promise<LoginResponse | null>;

let authRefreshHandler: AuthRefreshHandler | null = null;
let refreshInFlight: Promise<LoginResponse | null> | null = null;

export function setAuthRefreshHandler(handler: AuthRefreshHandler | null): void {
  authRefreshHandler = handler;
  if (!handler) refreshInFlight = null;
}

async function refreshSession(): Promise<LoginResponse | null> {
  if (!authRefreshHandler) return null;
  refreshInFlight ??= authRefreshHandler().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

export function refreshAuthentication(): Promise<LoginResponse | null> {
  return refreshSession();
}

async function fetchWithToken(path: string, accessToken: string | undefined, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(resolveApiUrl(path), {
    ...init,
    headers,
    credentials: "include",
  });
}

async function request<T>(path: string, accessToken?: string, init: RequestInit = {}, allowRefresh = true): Promise<T> {
  let response = await fetchWithToken(path, accessToken, init);
  if (response.status === 401 && accessToken && allowRefresh) {
    const refreshed = await refreshSession();
    if (refreshed) response = await fetchWithToken(path, refreshed.accessToken, init);
  }

  if (!response.ok) {
    throw await readError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function requestBlob(path: string, accessToken: string): Promise<Blob> {
  let response = await fetchWithToken(path, accessToken, {});
  if (response.status === 401) {
    const refreshed = await refreshSession();
    if (refreshed) response = await fetchWithToken(path, refreshed.accessToken, {});
  }
  if (!response.ok) throw await readError(response);
  return response.blob();
}

function queryString(values: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return params.size > 0 ? `?${params.toString()}` : "";
}

export const api = {
  login(email: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>("/auth/login", undefined, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  refresh(): Promise<LoginResponse> {
    return request<LoginResponse>("/auth/refresh", undefined, { method: "POST" }, false);
  },

  localSession(): Promise<LoginResponse> {
    return request<LoginResponse>("/auth/local-session", undefined, {}, false);
  },

  logout(): Promise<void> {
    return request<void>("/auth/logout", undefined, { method: "POST" });
  },

  listAdvertisements(accessToken: string, search: AdvertisementSearch = {}): Promise<AdvertisementListResponse> {
    return request<AdvertisementListResponse>(`/advertisements${queryString(search)}`, accessToken);
  },

  getAdvertisement(accessToken: string, advertisementId: string): Promise<AdvertisementDetail> {
    return request<AdvertisementDetail>(`/advertisements/${encodeURIComponent(advertisementId)}`, accessToken);
  },

  deleteAdvertisement(accessToken: string, advertisementId: string): Promise<void> {
    return request<void>(`/advertisements/${encodeURIComponent(advertisementId)}`, accessToken, { method: "DELETE" });
  },

  getFilePreview(accessToken: string, fileId: string, pageNo = 1): Promise<FilePreview> {
    return request<FilePreview>(`/files/${encodeURIComponent(fileId)}/preview?pageNo=${pageNo}`, accessToken);
  },

  async getFilePreviewAsset(accessToken: string, fileId: string, pageNo = 1): Promise<{ descriptor: FilePreview; blob: Blob }> {
    const descriptor = await request<FilePreview>(`/files/${encodeURIComponent(fileId)}/preview?pageNo=${pageNo}`, accessToken);
    const expectedPath = `/api/v1/files/${encodeURIComponent(fileId)}/preview/content`;
    if (descriptor.previewPath !== expectedPath) {
      throw new ApiError(500, "INTERNAL_ERROR");
    }
    return { descriptor, blob: await requestBlob(`${descriptor.previewPath}?pageNo=${pageNo}`, accessToken) };
  },

  async getFilePreviewContent(accessToken: string, fileId: string, pageNo = 1): Promise<Blob> {
    return requestBlob(
      `/files/${encodeURIComponent(fileId)}/preview/content?pageNo=${pageNo}`,
      accessToken,
    );
  },

  downloadFile(accessToken: string, fileId: string): Promise<Blob> {
    return requestBlob(`/files/${encodeURIComponent(fileId)}/download`, accessToken);
  },

  getCodes(accessToken: string, group: "product-groups" | "advertisement-types"): Promise<CodeItem[]> {
    return request<CodeItem[]>(`/codes/${group}`, accessToken);
  },

  createAdvertisement(accessToken: string, input: AdvertisementCreateInput): Promise<AdvertisementCreateResponse> {
    const body = new FormData();
    body.set("advertisementName", input.advertisementName);
    body.set("productGroup", input.productGroup);
    body.set("advertisementType", input.advertisementType);
    body.set("departmentId", input.departmentId);
    for (const advertisementFile of input.advertisementFiles ?? [input.advertisementFile]) body.append("advertisementFile", advertisementFile);
    if (input.channelType) body.set("channelType", input.channelType);
    if (input.memo) body.set("memo", input.memo);
    if (input.productDescriptionFile) body.set("productDescriptionFile", input.productDescriptionFile);
    if (input.termsFile) body.set("termsFile", input.termsFile);
    for (const additionalFile of input.additionalFiles ?? []) body.append("additionalFiles", additionalFile);

    return request<AdvertisementCreateResponse>("/advertisements", accessToken, { method: "POST", body });
  },

  createAdvertisementRevision(
    accessToken: string,
    advertisementId: string,
    input: AdvertisementRevisionInput,
  ): Promise<AdvertisementRevision> {
    const body = new FormData();
    body.set("revisedAdvertisementFile", input.revisedAdvertisementFile);
    if (input.revisionMemo) body.set("revisionMemo", input.revisionMemo);
    return request<AdvertisementRevision>(
      `/advertisements/${encodeURIComponent(advertisementId)}/revisions`,
      accessToken,
      { method: "POST", body },
    );
  },

  listStandards(accessToken: string, search: StandardSearch = {}): Promise<StandardListResponse> {
    return request<StandardListResponse>(`/standards${queryString(search)}`, accessToken);
  },

  getStandard(accessToken: string, standardId: string): Promise<StandardDetail> {
    return request<StandardDetail>(`/standards/${encodeURIComponent(standardId)}`, accessToken);
  },

  createStandard(accessToken: string, input: StandardCreateInput): Promise<StandardCreateResponse> {
    const body = new FormData();
    body.set("title", input.title);
    body.set("evidenceType", input.evidenceType);
    body.set("ruleType", input.ruleType);
    body.set("metadata", JSON.stringify(input.metadata));
    body.set("content", input.content);
    if (input.productGroup) body.set("productGroup", input.productGroup);
    if (input.advertisementType) body.set("advertisementType", input.advertisementType);
    if (input.importance) body.set("importance", input.importance);
    if (input.effectiveDate) body.set("effectiveDate", input.effectiveDate);
    if (input.expiredDate) body.set("expiredDate", input.expiredDate);
    if (input.sourceFile) body.set("sourceFile", input.sourceFile);
    return request<StandardCreateResponse>("/standards", accessToken, { method: "POST", body });
  },

  updateStandard(accessToken: string, standardId: string, input: StandardUpdateInput): Promise<StandardDetail> {
    return request<StandardDetail>(`/standards/${encodeURIComponent(standardId)}`, accessToken, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  deactivateStandard(accessToken: string, standardId: string, reason: string): Promise<StandardDetail> {
    return request<StandardDetail>(`/standards/${encodeURIComponent(standardId)}/deactivate`, accessToken, {
      method: "PATCH",
      body: JSON.stringify({ reason }),
    });
  },

  listStandardHistories(accessToken: string, standardId: string): Promise<StandardHistoryResponse> {
    return request<StandardHistoryResponse>(`/standards/${encodeURIComponent(standardId)}/histories?page=1&size=20`, accessToken);
  },

  searchEvidences(accessToken: string, search: EvidenceSearch): Promise<EvidenceSearchResult[]> {
    return request<EvidenceSearchResult[]>(`/evidences/search${queryString(search)}`, accessToken);
  },

  listEvidenceChunks(accessToken: string, evidenceId: string): Promise<EvidenceChunkListResponse> {
    return request<EvidenceChunkListResponse>(`/evidences/${encodeURIComponent(evidenceId)}/chunks?page=1&size=20`, accessToken);
  },

  requestStandardReindex(
    accessToken: string,
    standardId: string,
    standardVersionId: string,
    input: StandardReindexInput,
  ): Promise<StandardReindexJob> {
    return request<StandardReindexJob>(
      `/standards/${encodeURIComponent(standardId)}/versions/${encodeURIComponent(standardVersionId)}/reindex`,
      accessToken,
      { method: "POST", body: JSON.stringify(input) },
    );
  },

  getStandardReindexJob(accessToken: string, jobId: string): Promise<StandardReindexJob> {
    return request<StandardReindexJob>(`/standard-reindex-jobs/${encodeURIComponent(jobId)}`, accessToken);
  },

  listAdvertisementReviews(accessToken: string, advertisementId: string): Promise<ReviewHistory[]> {
    return request<ReviewHistory[]>(`/advertisements/${encodeURIComponent(advertisementId)}/reviews`, accessToken);
  },

  requestAdvertisementReview(
    accessToken: string,
    advertisementId: string,
    input: ReviewRequestInput,
  ): Promise<ReviewAccepted> {
    return request<ReviewAccepted>(`/advertisements/${encodeURIComponent(advertisementId)}/reviews`, accessToken, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  getReviewStatus(accessToken: string, reviewId: string): Promise<ReviewProgress> {
    return request<ReviewProgress>(`/reviews/${encodeURIComponent(reviewId)}/status`, accessToken);
  },

  getReviewSummary(accessToken: string, reviewId: string): Promise<ReviewSummary> {
    return request<ReviewSummary>(`/reviews/${encodeURIComponent(reviewId)}/summary`, accessToken);
  },

  listReviewItems(
    accessToken: string,
    reviewId: string,
    search: ReviewItemSearch = {},
  ): Promise<ReviewItemPage> {
    return request<ReviewItemPage>(`/reviews/${encodeURIComponent(reviewId)}/items${queryString(search)}`, accessToken);
  },

  getReviewItem(accessToken: string, reviewId: string, reviewItemId: string): Promise<ReviewItemDetail> {
    return request<ReviewItemDetail>(
      `/reviews/${encodeURIComponent(reviewId)}/items/${encodeURIComponent(reviewItemId)}`,
      accessToken,
    );
  },

  listReviewAnnotations(
    accessToken: string,
    reviewId: string,
    search: ReviewAnnotationSearch = {},
  ): Promise<ReviewAnnotationCollection> {
    return request<ReviewAnnotationCollection>(
      `/reviews/${encodeURIComponent(reviewId)}/annotations${queryString(search)}`,
      accessToken,
    );
  },

  rerunReview(accessToken: string, reviewId: string, input: RerunReviewInput): Promise<RerunReviewAccepted> {
    return request<RerunReviewAccepted>(`/reviews/${encodeURIComponent(reviewId)}/rerun`, accessToken, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  listReviewSuggestions(accessToken: string, reviewId: string): Promise<Suggestion[]> {
    return request<Suggestion[]>(`/reviews/${encodeURIComponent(reviewId)}/suggestions`, accessToken);
  },

  recordSuggestionDecision(accessToken: string, suggestionId: string, input: SuggestionDecisionInput): Promise<SuggestionDecision> {
    return request<SuggestionDecision>(`/suggestions/${encodeURIComponent(suggestionId)}/decision`, accessToken, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  askComplianceQuestion(accessToken: string, input: QaQuestionInput): Promise<QaAnswer> {
    return request<QaAnswer>("/qa/questions", accessToken, { method: "POST", body: JSON.stringify(input) });
  },

  listComplianceQuestions(accessToken: string, reviewId: string): Promise<QaAnswer[]> {
    return request<QaAnswer[]>(`/qa/questions${queryString({ reviewId })}`, accessToken);
  },

  listOpinionDrafts(accessToken: string, reviewId: string): Promise<OpinionDraft[]> {
    return request<OpinionDraft[]>(`/reviews/${encodeURIComponent(reviewId)}/opinion-drafts`, accessToken);
  },

  createOpinionDraft(accessToken: string, reviewId: string, input: OpinionDraftInput = {}): Promise<OpinionDraft> {
    return request<OpinionDraft>(`/reviews/${encodeURIComponent(reviewId)}/opinion-drafts`, accessToken, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  updateOpinionDraft(accessToken: string, draftId: string, input: OpinionDraftUpdateInput): Promise<OpinionDraft> {
    return request<OpinionDraft>(`/opinion-drafts/${encodeURIComponent(draftId)}`, accessToken, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  createReviewReport(accessToken: string, reviewId: string, input: ReportInput): Promise<Report> {
    return request<Report>(`/reviews/${encodeURIComponent(reviewId)}/reports`, accessToken, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  getReviewReport(accessToken: string, reportId: string): Promise<Report> {
    return request<Report>(`/reports/${encodeURIComponent(reportId)}`, accessToken);
  },

  downloadReviewReport(accessToken: string, reportId: string): Promise<Blob> {
    return requestBlob(`/reports/${encodeURIComponent(reportId)}/download`, accessToken);
  },

  createAdvertisementComparison(accessToken: string, advertisementId: string, input: ComparisonInput): Promise<Comparison> {
    return request<Comparison>(`/advertisements/${encodeURIComponent(advertisementId)}/comparisons`, accessToken, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  getAdvertisementComparison(accessToken: string, comparisonId: string): Promise<Comparison> {
    return request<Comparison>(`/comparisons/${encodeURIComponent(comparisonId)}`, accessToken);
  },

  listValidationDatasets(accessToken: string, page = 1, size = 20): Promise<ValidationDatasetPage> {
    return request<ValidationDatasetPage>(`/validation/datasets${queryString({ page, size })}`, accessToken);
  },

  createValidationDataset(accessToken: string, input: ValidationDatasetCreateInput): Promise<ValidationDataset> {
    const body = new FormData();
    body.set("datasetName", input.datasetName);
    body.set("productGroup", input.productGroup);
    body.set("advertisementType", input.advertisementType);
    body.set("advertisementFile", input.advertisementFile);
    body.set("excluded", String(input.excluded));
    if (input.productConditionFile) body.set("productConditionFile", input.productConditionFile);
    if (input.humanReviewComment) body.set("humanReviewComment", input.humanReviewComment);
    if (input.labelJson) body.set("labelJson", input.labelJson);
    if (input.excludeReasonCode) body.set("excludeReasonCode", input.excludeReasonCode);
    if (input.excludeReasonDetail) body.set("excludeReasonDetail", input.excludeReasonDetail);
    return request<ValidationDataset>("/validation/datasets", accessToken, { method: "POST", body });
  },

  createValidationJudgments(accessToken: string, datasetId: string, input: ValidationJudgmentsInput): Promise<ValidationJudgmentsCreated> {
    return request<ValidationJudgmentsCreated>(`/validation/datasets/${encodeURIComponent(datasetId)}/judgments`, accessToken, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  createValidationEvaluation(accessToken: string, input: ValidationEvaluationInput): Promise<ValidationEvaluation> {
    return request<ValidationEvaluation>("/validation/evaluations", accessToken, { method: "POST", body: JSON.stringify(input) });
  },

  getValidationEvaluation(accessToken: string, evaluationId: string): Promise<ValidationEvaluation> {
    return request<ValidationEvaluation>(`/validation/evaluations/${encodeURIComponent(evaluationId)}`, accessToken);
  },
};

export function userMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : ERROR_MESSAGES.INTERNAL_ERROR;
}
