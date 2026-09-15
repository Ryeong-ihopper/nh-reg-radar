import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import {
  api,
  type AdvertisementType,
  type EvidenceChunkListResponse,
  type EvidenceSearchResult,
  type EvidenceType,
  type ProductGroup,
  type RuleType,
  type StandardDetail,
  type StandardHistoryResponse,
  type StandardReindexJob,
  type StandardSearch,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { ErrorState, LoadingState } from "../components/RequestState";
import { advertisementTypeLabel, evidenceTypeLabel, productGroupLabel, ruleTypeLabel } from "../components/displayLabels";

const EVIDENCE_TYPES: EvidenceType[] = ["LAW", "REGULATION", "INTERNAL_STANDARD", "GUIDELINE", "MANUAL", "REVIEW_CASE", "TEMPLATE", "PRODUCT_STANDARD"];
const RULE_TYPES: RuleType[] = ["REQUIRED", "PROHIBITED", "RECOMMENDED", "REFERENCE"];
const PRODUCT_GROUPS: ProductGroup[] = ["DEPOSIT", "SAVINGS", "DEMAND_DEPOSIT", "EVENT", "LOAN"];
const ADVERTISEMENT_TYPES: AdvertisementType[] = ["BRANCH_FLYER", "NOTICE", "MOBILE_BANNER", "WEB_BANNER", "WEB_PRODUCT_PAGE", "EVENT_PAGE", "SOCIAL_MEDIA", "VIDEO", "EMAIL", "OUTDOOR", "PRINT_AD", "PUSH", "SMS", "ALIMTALK", "OTHER"];

type Panel = "create" | "detail" | "edit" | "deactivate" | "history" | "chunks" | "reindex" | null;

function formatDate(value?: string | null): string {
  return value || "-";
}

function localToday(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function indexStatusLabel(value?: string | null): string {
  if (value === "INDEXED" || value === "COMPLETED") return "반영됨";
  if (value === "EXCLUDED") return "제외됨";
  if (value === "FAILED") return "반영 실패";
  return "반영 대기";
}

function StandardDetailPanel({ detail }: { detail: StandardDetail }) {
  return (
    <div className="detail-grid compact-detail">
      <dl>
        <div><dt>기준명</dt><dd>{detail.title}</dd></div>
        <div><dt>기준 유형</dt><dd>{evidenceTypeLabel(detail.evidenceType)}</dd></div>
        <div><dt>기준 성격</dt><dd>{ruleTypeLabel(detail.ruleType)}</dd></div>
        <div><dt>적용 상품군</dt><dd>{detail.productGroup ? productGroupLabel(detail.productGroup) : "전체"}</dd></div>
        <div><dt>적용 광고유형</dt><dd>{detail.advertisementType ? advertisementTypeLabel(detail.advertisementType) : "전체"}</dd></div>
        <div><dt>버전</dt><dd>{detail.version}</dd></div>
        <div><dt>적용일</dt><dd>{formatDate(detail.effectiveDate)}</dd></div>
        <div><dt>상태</dt><dd>{detail.isActive ? "활성" : "비활성"}</dd></div>
      </dl>
      <div><h4>직접 입력 본문</h4><p className="content-preview">{detail.content}</p></div>
    </div>
  );
}

export function StandardManagementPage() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const token = session?.accessToken ?? "";
  const [keywordInput, setKeywordInput] = useState("");
  const [evidenceTypeInput, setEvidenceTypeInput] = useState<"" | EvidenceType>("");
  const [productGroupInput, setProductGroupInput] = useState<"" | ProductGroup>("");
  const [advertisementTypeInput, setAdvertisementTypeInput] = useState<"" | AdvertisementType>("");
  const [ruleTypeInput, setRuleTypeInput] = useState<"" | RuleType>("");
  const [filters, setFilters] = useState<StandardSearch>({ activeOnly: true, page: 1, size: 20 });
  const [panel, setPanel] = useState<Panel>(null);
  const [selectedDetail, setSelectedDetail] = useState<StandardDetail | null>(null);
  const [history, setHistory] = useState<StandardHistoryResponse | null>(null);
  const [chunks, setChunks] = useState<EvidenceChunkListResponse | null>(null);
  const [evidenceKeyword, setEvidenceKeyword] = useState("");
  const [evidenceResults, setEvidenceResults] = useState<EvidenceSearchResult[] | null>(null);
  const [searchError, setSearchError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [reindexReason, setReindexReason] = useState("");
  const [reindexJob, setReindexJob] = useState<StandardReindexJob | null>(null);

  const standards = useQuery({
    queryKey: ["standards", filters],
    queryFn: () => api.listStandards(token, filters),
  });

  async function loadDetail(standardId: string): Promise<StandardDetail> {
    if (selectedDetail?.standardId === standardId) return selectedDetail;
    const detail = await api.getStandard(token, standardId);
    setSelectedDetail(detail);
    return detail;
  }

  async function runAction(action: () => Promise<void>): Promise<void> {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(error);
    } finally {
      setBusy(false);
    }
  }

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({
      keyword: keywordInput.trim() || undefined,
      evidenceType: evidenceTypeInput || undefined,
      productGroup: productGroupInput || undefined,
      advertisementType: advertisementTypeInput || undefined,
      ruleType: ruleTypeInput || undefined,
      activeOnly: true,
      page: 1,
      size: 20,
    });
  }

  async function showDetail(standardId: string) {
    await runAction(async () => {
      await loadDetail(standardId);
      setPanel("detail");
    });
  }

  async function showHistory(standardId: string) {
    await runAction(async () => {
      setHistory(await api.listStandardHistories(token, standardId));
      setPanel("history");
    });
  }

  async function showChunks(standardId: string) {
    await runAction(async () => {
      const detail = await loadDetail(standardId);
      setChunks(await api.listEvidenceChunks(token, detail.evidenceId));
      setPanel("chunks");
    });
  }

  async function preparePanel(standardId: string, nextPanel: "edit" | "deactivate" | "reindex") {
    await runAction(async () => {
      await loadDetail(standardId);
      if (nextPanel === "reindex") {
        setReindexReason("");
        setReindexJob(null);
      }
      setPanel(nextPanel);
    });
  }

  async function searchEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const keyword = evidenceKeyword.trim();
    if (!keyword) return;
    setSearchError(null);
    setEvidenceResults(null);
    try {
      setEvidenceResults(await api.searchEvidences(token, { keyword, searchMode: "HYBRID", limit: 20 }));
    } catch (error) {
      setSearchError(error);
    }
  }

  async function createStandard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const sourceFile = form.get("sourceFile");
    const productGroup = String(form.get("productGroup") ?? "") as ProductGroup;
    const effectiveDate = String(form.get("effectiveDate") ?? "");
    await runAction(async () => {
      await api.createStandard(token, {
        title: String(form.get("title") ?? "").trim(),
        evidenceType: String(form.get("evidenceType")) as EvidenceType,
        productGroup,
        advertisementType: (String(form.get("advertisementType") ?? "") || undefined) as AdvertisementType | undefined,
        ruleType: String(form.get("ruleType")) as RuleType,
        importance: "HIGH",
        effectiveDate,
        metadata: {
          inputBoundary: "DIRECT_TEXT_ONLY",
          owningDepartment: String(form.get("owningDepartment") ?? "").trim(),
          documentName: String(form.get("documentName") ?? "").trim(),
          sectionPath: String(form.get("sectionPath") ?? "").trim(),
          effectiveDate,
          version: String(form.get("version") ?? "").trim(),
          productGroup,
        },
        content: String(form.get("content") ?? "").trim(),
        sourceFile: sourceFile instanceof File && sourceFile.size > 0 ? sourceFile : undefined,
      });
      setPanel(null);
      await queryClient.invalidateQueries({ queryKey: ["standards"] });
    });
  }

  async function updateStandard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDetail) return;
    const form = new FormData(event.currentTarget);
    await runAction(async () => {
      const updated = await api.updateStandard(token, selectedDetail.standardId, {
        title: String(form.get("title") ?? "").trim(),
        content: String(form.get("content") ?? "").trim(),
        effectiveDate: String(form.get("effectiveDate") ?? "") || null,
        expiredDate: null,
        metadata: selectedDetail.metadata,
        changeReason: String(form.get("changeReason") ?? "").trim(),
      });
      setSelectedDetail(updated);
      setPanel("detail");
      await queryClient.invalidateQueries({ queryKey: ["standards"] });
    });
  }

  async function deactivateStandard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDetail) return;
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    await runAction(async () => {
      const updated = await api.deactivateStandard(token, selectedDetail.standardId, reason);
      setSelectedDetail(updated);
      setPanel("detail");
      await queryClient.invalidateQueries({ queryKey: ["standards"] });
    });
  }

  function toggleCreatePanel() {
    if (panel === "create") {
      setPanel(null);
      return;
    }
    setActionError(null);
    setPanel("create");
    window.setTimeout(() => {
      const heading = document.getElementById("standard-registration-heading");
      if (heading && typeof heading.scrollIntoView === "function") heading.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }

  async function requestReindex(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDetail) return;
    await runAction(async () => {
      const accepted = await api.requestStandardReindex(token, selectedDetail.standardId, selectedDetail.standardVersionId, {
        reindexScope: "INDEX_ONLY",
        reason: reindexReason.trim(),
        parserRuleVersion: null,
        chunkingPolicyVersion: "direct-text-v1",
        embeddingModel: null,
        searchSchemaVersion: "m3-v1",
        opensearchAnalyzerVersion: "m3-v1",
        synonymVersion: null,
        targetIndexes: ["QDRANT", "OPENSEARCH"],
      });
      setReindexJob(await api.getStandardReindexJob(token, accepted.jobId));
    });
  }

  return (
    <section aria-labelledby="standards-heading">
      <PageHeader
        headingId="standards-heading"
        eyebrow="검토 기준 운영"
        title="검토 기준자료 관리"
        description="규정·가이드라인·내부 기준을 등록하고, 광고 검토 적용 여부와 검색 데이터를 관리합니다."
        actions={<button type="button" onClick={toggleCreatePanel}>{panel === "create" ? "등록 닫기" : "기준자료 등록"}</button>}
      />

      <section className="standards-lifecycle" aria-label="기준자료 등록 및 검토 적용 흐름">
        <ol>
          <li><strong>1. 기준 등록</strong><span>규정 또는 가이드라인의 적용 범위를 입력합니다.</span></li>
          <li><strong>2. 내용 확인</strong><span>검토에 쓸 문구와 원문 보관 파일을 확인합니다.</span></li>
          <li><strong>3. 검색 데이터 갱신</strong><span>필요한 경우 벡터·문서 검색 데이터를 다시 만듭니다.</span></li>
          <li><strong>4. 광고 검토 적용</strong><span>활성 기준이 AI 검토의 근거로 사용됩니다.</span></li>
        </ol>
      </section>

      <form className="filter-grid" onSubmit={submitFilters}>
        <label htmlFor="standard-keyword">기준명</label>
        <input id="standard-keyword" value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} />
        <label htmlFor="standard-evidence-type">기준 유형</label>
        <select id="standard-evidence-type" value={evidenceTypeInput} onChange={(event) => setEvidenceTypeInput(event.target.value as "" | EvidenceType)}>
          <option value="">전체</option>{EVIDENCE_TYPES.map((type) => <option key={type} value={type}>{evidenceTypeLabel(type)}</option>)}
        </select>
        <label htmlFor="standard-product-group">상품군</label>
        <select id="standard-product-group" value={productGroupInput} onChange={(event) => setProductGroupInput(event.target.value as "" | ProductGroup)}><option value="">전체</option>{PRODUCT_GROUPS.map((type) => <option key={type} value={type}>{productGroupLabel(type)}</option>)}</select>
        <label htmlFor="standard-advertisement-type">광고유형</label>
        <select id="standard-advertisement-type" value={advertisementTypeInput} onChange={(event) => setAdvertisementTypeInput(event.target.value as "" | AdvertisementType)}><option value="">전체</option>{ADVERTISEMENT_TYPES.map((type) => <option key={type} value={type}>{advertisementTypeLabel(type)}</option>)}</select>
        <label htmlFor="standard-rule-type">기준 성격</label>
        <select id="standard-rule-type" value={ruleTypeInput} onChange={(event) => setRuleTypeInput(event.target.value as "" | RuleType)}><option value="">전체</option>{RULE_TYPES.map((type) => <option key={type} value={type}>{ruleTypeLabel(type)}</option>)}</select>
        <div className="form-actions"><button type="submit">조회</button><button type="button" className="button-secondary" onClick={() => { setKeywordInput(""); setEvidenceTypeInput(""); setProductGroupInput(""); setAdvertisementTypeInput(""); setRuleTypeInput(""); setFilters({ activeOnly: true, page: 1, size: 20 }); }}>초기화</button></div>
      </form>

      {standards.isPending ? <LoadingState label="기준자료 목록을 불러오는 중입니다." /> : null}
      {standards.isError ? <ErrorState error={standards.error} onRetry={() => void standards.refetch()} /> : null}
      {standards.data?.contents.length === 0 ? <p className="state-message">등록된 기준자료가 없습니다.</p> : null}
      {standards.data && standards.data.contents.length > 0 ? (
        <div className="table-scroll">
          <table className="standards-table">
            <colgroup><col className="standards-table__title" /><col /><col /><col /><col /><col /><col /><col /><col className="standards-table__actions" /></colgroup>
            <thead><tr><th>기준명</th><th>기준 유형</th><th>상품군</th><th>광고유형</th><th>성격</th><th>적용일</th><th>버전</th><th>검토 적용</th><th>관리</th></tr></thead>
            <tbody>{standards.data.contents.map((item) => (
              <tr key={item.standardId}>
                <td className="standard-title" title={item.title}><span>{item.title}</span></td><td>{evidenceTypeLabel(item.evidenceType)}</td><td>{item.productGroup ? productGroupLabel(item.productGroup) : "전체"}</td><td>{item.advertisementType ? advertisementTypeLabel(item.advertisementType) : "전체"}</td><td>{ruleTypeLabel(item.ruleType)}</td><td>{formatDate(item.effectiveDate)}</td><td>{item.currentVersion}</td><td><span className="standard-status" data-active={item.isActive}>{item.isActive ? "적용 중" : "미적용"}</span></td>
                <td><div className="table-actions">
                  <button type="button" className="button-secondary" onClick={() => void showDetail(item.standardId)}>내용 확인</button>
                  <button type="button" className="button-secondary" onClick={() => void preparePanel(item.standardId, "edit")}>개정</button>
                  <button type="button" className="button-secondary" onClick={() => void showHistory(item.standardId)}>버전 이력</button>
                  <button type="button" className="button-secondary" onClick={() => void showChunks(item.standardId)}>청크 확인</button>
                  <div className="standard-operation-actions" aria-label="운영 상태 관리">
                    <span>운영 상태</span>
                    <button type="button" className="button-secondary" onClick={() => void preparePanel(item.standardId, "reindex")}>검색 데이터 갱신</button>
                    {item.isActive ? <button type="button" className="button-danger" onClick={() => void preparePanel(item.standardId, "deactivate")}>검토 적용 중지</button> : null}
                  </div>
                </div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}
      {standards.data ? <Pagination page={standards.data.page} totalPages={standards.data.totalPages} totalElements={standards.data.totalElements} onPageChange={(page) => setFilters((current) => ({ ...current, page }))} /> : null}

      {busy ? <LoadingState label="기준자료 요청을 처리하는 중입니다." /> : null}
      {actionError ? <ErrorState error={actionError} /> : null}

      {panel === "create" ? <section className="management-panel standard-registration-panel" aria-labelledby="standard-registration-heading">
        <div className="panel-heading"><div><p className="eyebrow">새 검토 기준</p><h3 id="standard-registration-heading">규정·가이드라인 등록</h3></div><p>등록 후 활성 기준은 광고 검토의 근거로 활용됩니다. 변경할 때는 개정으로 새 버전을 만드세요.</p></div>
        <form className="form-grid" onSubmit={(event) => void createStandard(event)}>
          <fieldset className="standard-form-section"><legend>1. 적용 범위</legend>
            <label htmlFor="create-title">기준명 *</label><input id="create-title" name="title" placeholder="예: 예금상품 금리 표시 기준" required />
            <label htmlFor="create-evidence-type">기준 유형 *</label><select id="create-evidence-type" name="evidenceType" defaultValue="INTERNAL_STANDARD">{EVIDENCE_TYPES.map((type) => <option key={type} value={type}>{evidenceTypeLabel(type)}</option>)}</select>
            <label htmlFor="create-product-group">상품군 *</label><select id="create-product-group" name="productGroup" defaultValue="" required><option value="" disabled>선택하세요</option>{PRODUCT_GROUPS.map((type) => <option key={type} value={type}>{productGroupLabel(type)}</option>)}</select>
            <label htmlFor="create-ad-type">적용 광고유형</label><select id="create-ad-type" name="advertisementType"><option value="">모든 광고유형</option>{ADVERTISEMENT_TYPES.map((type) => <option key={type} value={type}>{advertisementTypeLabel(type)}</option>)}</select>
            <label htmlFor="create-rule-type">기준 성격 *</label><select id="create-rule-type" name="ruleType" defaultValue="REQUIRED">{RULE_TYPES.map((type) => <option key={type} value={type}>{ruleTypeLabel(type)}</option>)}</select>
          </fieldset>
          <fieldset className="standard-form-section"><legend>2. 문서 정보</legend>
            <label htmlFor="create-owning-department">소관 부서 *</label><input id="create-owning-department" name="owningDepartment" placeholder="예: 상품심의부" required />
            <label htmlFor="create-document-name">문서명 *</label><input id="create-document-name" name="documentName" placeholder="원문 문서의 제목" required />
            <label htmlFor="create-section-path">조항·섹션 위치 *</label><input id="create-section-path" name="sectionPath" placeholder="예: 제3장 제2절" required />
            <label htmlFor="create-version">문서 버전 *</label><input id="create-version" name="version" defaultValue="1.0" required />
            <label htmlFor="create-effective-date">적용 시작일 *</label><input id="create-effective-date" name="effectiveDate" type="date" defaultValue={localToday()} required />
          </fieldset>
          <fieldset className="standard-form-section standard-form-content"><legend>3. 검토 기준 내용</legend>
            <label htmlFor="create-content">검토에 사용할 본문 *</label><textarea id="create-content" name="content" rows={8} placeholder="광고 검토에서 확인할 기준 문구를 그대로 입력하세요." required />
            <p className="form-help">본문은 검색·AI 검토의 근거로 사용됩니다. 원문 파일은 보관과 추적을 위해 함께 등록할 수 있습니다.</p>
            <label htmlFor="create-source-file">원문 파일 (선택)</label><input id="create-source-file" name="sourceFile" type="file" />
          </fieldset>
          <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setPanel(null)}>취소</button><button type="submit" disabled={busy}>기준자료 등록</button></div>
        </form>
      </section> : null}

      {panel === "detail" && selectedDetail ? <div className="management-panel"><h3>등록 기준자료 확인</h3><StandardDetailPanel detail={selectedDetail} /></div> : null}
      {panel === "edit" && selectedDetail ? <div className="management-panel"><h3>새 불변 버전 등록</h3><form className="form-grid" onSubmit={(event) => void updateStandard(event)}>
        <label htmlFor="edit-title">기준명 *</label><input id="edit-title" name="title" defaultValue={selectedDetail.title} required />
        <label htmlFor="edit-effective-date">적용일</label><input id="edit-effective-date" name="effectiveDate" type="date" defaultValue={selectedDetail.effectiveDate ?? ""} />
        <label htmlFor="edit-content">직접 입력 본문 *</label><textarea id="edit-content" name="content" rows={7} defaultValue={selectedDetail.content} required />
        <label htmlFor="edit-reason">변경 사유 *</label><textarea id="edit-reason" name="changeReason" rows={3} required />
        <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setPanel(null)}>취소</button><button type="submit" disabled={busy}>새 버전 저장</button></div>
      </form></div> : null}
      {panel === "deactivate" && selectedDetail ? <div className="management-panel"><h3>검토 적용 중지</h3><form className="form-grid" onSubmit={(event) => void deactivateStandard(event)}>
        <p className="form-help">{selectedDetail.title}는 이후 광고 검토와 근거 검색에 사용되지 않습니다. 기준자료와 이력은 삭제되지 않습니다.</p>
        <label htmlFor="deactivate-reason">적용 중지 사유 *</label><textarea id="deactivate-reason" name="reason" rows={3} required />
        <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setPanel(null)}>취소</button><button type="submit" className="button-danger" disabled={busy}>적용 중지 확인</button></div>
      </form></div> : null}
      {panel === "history" && history ? <div className="management-panel"><h3>불변 버전 이력</h3>{history.contents.length === 0 ? <p className="state-message">변경 이력이 없습니다.</p> : <div className="table-scroll"><table><thead><tr><th>버전</th><th>적용일</th><th>변경 사유</th><th>등록자</th></tr></thead><tbody>{history.contents.map((item) => <tr key={item.standardVersionId}><td>{item.version}</td><td>{formatDate(item.effectiveDate)}</td><td>{item.changeReason ?? "최초 등록"}</td><td>{item.createdBy}</td></tr>)}</tbody></table></div>}</div> : null}
      {panel === "chunks" && chunks ? <div className="management-panel"><h3>청크 확인</h3><p className="panel-note">내부 collection, index, point, document 식별자는 화면에 표시하지 않습니다.</p>{chunks.contents.length === 0 ? <p className="state-message">생성된 청크가 없습니다.</p> : <div className="chunk-list">{chunks.contents.map((chunk) => <article key={chunk.evidenceChunkId}><h4>청크 {chunk.chunkNo} · {chunk.articleNo ?? chunk.sectionPath ?? "구조 정보 없음"}</h4><p>{chunk.chunkText}</p><small>토큰 {chunk.tokenCount ?? "-"} · 벡터 검색 {indexStatusLabel(chunk.qdrantIndexStatus)} · 문서 검색 {indexStatusLabel(chunk.opensearchIndexStatus)}</small></article>)}</div>}</div> : null}
      {panel === "reindex" && selectedDetail ? <div className="management-panel"><h3>검색 데이터 갱신</h3><form className="form-grid" onSubmit={(event) => void requestReindex(event)}>
        <div className="form-help"><p>{selectedDetail.version} 버전의 벡터·문서 검색 데이터를 다시 만듭니다. 검토 적용 여부와 기준 내용은 바뀌지 않습니다.</p><p><strong>언제 사용하나요?</strong> 새 버전을 등록한 뒤 검색 결과를 확인해야 할 때, 이 기준자료만 검색되지 않거나 색인 처리에 실패했을 때 사용합니다.</p><p>임베딩 모델·검색 스키마 같은 <strong>공통 검색 설정</strong>을 바꾼 경우에는 전체 기준자료를 대상으로 한 일괄 갱신이 필요합니다. 이 화면은 현재 선택한 기준자료 버전만 갱신합니다.</p></div>
        <label htmlFor="reindex-reason">검색 데이터 갱신 사유 *</label><textarea id="reindex-reason" value={reindexReason} onChange={(event) => setReindexReason(event.target.value)} rows={3} required />
        <div className="form-actions"><button type="submit" disabled={busy || !reindexReason.trim()}>검색 데이터 갱신 요청</button></div>
      </form>{reindexJob ? <div className="job-status" aria-live="polite"><strong>{reindexJob.jobStatus}</strong><span>처리 청크 {reindexJob.indexedChunkCount}/{reindexJob.createdChunkCount}</span><span>Qdrant {reindexJob.qdrantStatus ?? "-"}</span><span>OpenSearch {reindexJob.opensearchStatus ?? "-"}</span><button type="button" className="button-secondary" onClick={() => void runAction(async () => setReindexJob(await api.getStandardReindexJob(token, reindexJob.jobId)))}>상태 새로고침</button></div> : null}</div> : null}

      <div className="management-panel evidence-search-panel"><h3>검토 근거 검색 확인</h3><form className="search-bar" onSubmit={(event) => void searchEvidence(event)}><label htmlFor="evidence-keyword">검색어</label><input id="evidence-keyword" value={evidenceKeyword} onChange={(event) => setEvidenceKeyword(event.target.value)} /><button type="submit">근거 검색</button></form>
        {searchError ? <ErrorState error={searchError} /> : null}
        {evidenceResults?.length === 0 ? <p className="state-message">검색된 근거가 없습니다.</p> : null}
        {evidenceResults && evidenceResults.length > 0 ? <ol className="evidence-results">{evidenceResults.map((result) => <li key={result.evidenceChunkId}><strong>{result.title}</strong><span>검색 결과 {result.rankNo}위 · 관련도 {result.relevanceScore.toFixed(4)}</span><p>{result.contentSummary}</p></li>)}</ol> : null}
      </div>
    </section>
  );
}
