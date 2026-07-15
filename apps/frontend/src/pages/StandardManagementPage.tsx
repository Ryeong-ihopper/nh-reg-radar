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
import { Pagination } from "../components/Pagination";
import { ErrorState, LoadingState } from "../components/RequestState";

const EVIDENCE_TYPES: EvidenceType[] = ["LAW", "REGULATION", "INTERNAL_STANDARD", "GUIDELINE", "MANUAL", "REVIEW_CASE", "TEMPLATE", "PRODUCT_STANDARD"];
const RULE_TYPES: RuleType[] = ["REQUIRED", "PROHIBITED", "RECOMMENDED", "REFERENCE"];
const PRODUCT_GROUPS: ProductGroup[] = ["DEPOSIT", "SAVINGS", "DEMAND_DEPOSIT", "EVENT"];
const ADVERTISEMENT_TYPES: AdvertisementType[] = ["BRANCH_FLYER", "NOTICE", "MOBILE_BANNER", "WEB_BANNER", "EVENT_PAGE", "PUSH", "SMS", "ALIMTALK"];

type Panel = "create" | "detail" | "edit" | "deactivate" | "history" | "chunks" | "reindex" | null;

function formatDate(value?: string | null): string {
  return value || "-";
}

function StandardDetailPanel({ detail }: { detail: StandardDetail }) {
  return (
    <div className="detail-grid compact-detail">
      <dl>
        <div><dt>기준자료 ID</dt><dd>{detail.standardId}</dd></div>
        <div><dt>버전 ID</dt><dd>{detail.standardVersionId}</dd></div>
        <div><dt>기준명</dt><dd>{detail.title}</dd></div>
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
      <div className="page-heading">
        <div><p className="eyebrow">S-014</p><h2 id="standards-heading">기준자료 관리</h2></div>
        <button type="button" onClick={() => { setActionError(null); setPanel(panel === "create" ? null : "create"); }}>신규 등록</button>
      </div>

      <form className="filter-grid" onSubmit={submitFilters}>
        <label htmlFor="standard-keyword">기준명</label>
        <input id="standard-keyword" value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} />
        <label htmlFor="standard-evidence-type">기준 유형</label>
        <select id="standard-evidence-type" value={evidenceTypeInput} onChange={(event) => setEvidenceTypeInput(event.target.value as "" | EvidenceType)}>
          <option value="">전체</option>{EVIDENCE_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
        <label htmlFor="standard-product-group">상품군</label>
        <select id="standard-product-group" value={productGroupInput} onChange={(event) => setProductGroupInput(event.target.value as "" | ProductGroup)}><option value="">전체</option>{PRODUCT_GROUPS.map((type) => <option key={type} value={type}>{type}</option>)}</select>
        <label htmlFor="standard-advertisement-type">광고유형</label>
        <select id="standard-advertisement-type" value={advertisementTypeInput} onChange={(event) => setAdvertisementTypeInput(event.target.value as "" | AdvertisementType)}><option value="">전체</option>{ADVERTISEMENT_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}</select>
        <label htmlFor="standard-rule-type">기준 성격</label>
        <select id="standard-rule-type" value={ruleTypeInput} onChange={(event) => setRuleTypeInput(event.target.value as "" | RuleType)}><option value="">전체</option>{RULE_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}</select>
        <div className="form-actions"><button type="submit">조회</button><button type="button" className="button-secondary" onClick={() => { setKeywordInput(""); setEvidenceTypeInput(""); setProductGroupInput(""); setAdvertisementTypeInput(""); setRuleTypeInput(""); setFilters({ activeOnly: true, page: 1, size: 20 }); }}>초기화</button></div>
      </form>

      {standards.isPending ? <LoadingState label="기준자료 목록을 불러오는 중입니다." /> : null}
      {standards.isError ? <ErrorState error={standards.error} onRetry={() => void standards.refetch()} /> : null}
      {standards.data?.contents.length === 0 ? <p className="state-message">등록된 기준자료가 없습니다.</p> : null}
      {standards.data && standards.data.contents.length > 0 ? (
        <div className="table-scroll">
          <table>
            <thead><tr><th>기준자료 ID</th><th>기준명</th><th>기준 유형</th><th>상품군</th><th>광고유형</th><th>성격</th><th>적용일</th><th>버전</th><th>상태</th><th>관리</th></tr></thead>
            <tbody>{standards.data.contents.map((item) => (
              <tr key={item.standardId}>
                <td>{item.standardId}</td><td>{item.title}</td><td>{item.evidenceType}</td><td>{item.productGroup ?? "-"}</td><td>{item.advertisementType ?? "-"}</td><td>{item.ruleType}</td><td>{formatDate(item.effectiveDate)}</td><td>{item.currentVersion}</td><td>{item.isActive ? "활성" : "비활성"}</td>
                <td><div className="table-actions">
                  <button type="button" className="button-secondary" onClick={() => void showDetail(item.standardId)}>상세 보기</button>
                  <button type="button" className="button-secondary" onClick={() => void preparePanel(item.standardId, "edit")}>수정</button>
                  <button type="button" className="button-secondary" onClick={() => void showHistory(item.standardId)}>이력 보기</button>
                  <button type="button" className="button-secondary" onClick={() => void showChunks(item.standardId)}>Chunk 확인</button>
                  <button type="button" className="button-secondary" onClick={() => void preparePanel(item.standardId, "reindex")}>재색인</button>
                  {item.isActive ? <button type="button" className="button-danger" onClick={() => void preparePanel(item.standardId, "deactivate")}>비활성화</button> : null}
                </div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}
      {standards.data ? <Pagination page={standards.data.page} totalPages={standards.data.totalPages} totalElements={standards.data.totalElements} onPageChange={(page) => setFilters((current) => ({ ...current, page }))} /> : null}

      {busy ? <LoadingState label="기준자료 요청을 처리하는 중입니다." /> : null}
      {actionError ? <ErrorState error={actionError} /> : null}

      {panel === "create" ? <div className="management-panel"><h3>기준자료 신규 등록</h3><form className="form-grid" onSubmit={(event) => void createStandard(event)}>
        <label htmlFor="create-title">기준명 *</label><input id="create-title" name="title" required />
        <label htmlFor="create-evidence-type">기준 유형 *</label><select id="create-evidence-type" name="evidenceType" defaultValue="INTERNAL_STANDARD">{EVIDENCE_TYPES.map((type) => <option key={type}>{type}</option>)}</select>
        <label htmlFor="create-product-group">상품군 *</label><select id="create-product-group" name="productGroup" defaultValue="" required><option value="" disabled>선택</option>{PRODUCT_GROUPS.map((type) => <option key={type}>{type}</option>)}</select>
        <label htmlFor="create-ad-type">광고유형</label><select id="create-ad-type" name="advertisementType"><option value="">전체</option>{ADVERTISEMENT_TYPES.map((type) => <option key={type}>{type}</option>)}</select>
        <label htmlFor="create-rule-type">기준 성격 *</label><select id="create-rule-type" name="ruleType" defaultValue="REQUIRED">{RULE_TYPES.map((type) => <option key={type}>{type}</option>)}</select>
        <label htmlFor="create-owning-department">소관 부서 *</label><input id="create-owning-department" name="owningDepartment" required />
        <label htmlFor="create-document-name">문서명 *</label><input id="create-document-name" name="documentName" required />
        <label htmlFor="create-section-path">섹션 경로 *</label><input id="create-section-path" name="sectionPath" required />
        <label htmlFor="create-version">문서 버전 *</label><input id="create-version" name="version" defaultValue="1.0" required />
        <label htmlFor="create-effective-date">적용일 *</label><input id="create-effective-date" name="effectiveDate" type="date" required />
        <label htmlFor="create-content">직접 입력 본문 *</label><textarea id="create-content" name="content" rows={7} required />
        <label htmlFor="create-source-file">보관용 원문</label><input id="create-source-file" name="sourceFile" type="file" />
        <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setPanel(null)}>취소</button><button type="submit" disabled={busy}>등록</button></div>
      </form></div> : null}

      {panel === "detail" && selectedDetail ? <div className="management-panel"><h3>기준자료 상세</h3><StandardDetailPanel detail={selectedDetail} /></div> : null}
      {panel === "edit" && selectedDetail ? <div className="management-panel"><h3>새 불변 버전 등록</h3><form className="form-grid" onSubmit={(event) => void updateStandard(event)}>
        <label htmlFor="edit-title">기준명 *</label><input id="edit-title" name="title" defaultValue={selectedDetail.title} required />
        <label htmlFor="edit-effective-date">적용일</label><input id="edit-effective-date" name="effectiveDate" type="date" defaultValue={selectedDetail.effectiveDate ?? ""} />
        <label htmlFor="edit-content">직접 입력 본문 *</label><textarea id="edit-content" name="content" rows={7} defaultValue={selectedDetail.content} required />
        <label htmlFor="edit-reason">변경 사유 *</label><textarea id="edit-reason" name="changeReason" rows={3} required />
        <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setPanel(null)}>취소</button><button type="submit" disabled={busy}>새 버전 저장</button></div>
      </form></div> : null}
      {panel === "deactivate" && selectedDetail ? <div className="management-panel"><h3>기준자료 비활성화</h3><form className="form-grid" onSubmit={(event) => void deactivateStandard(event)}>
        <p className="form-help">{selectedDetail.title} 및 연결 Chunk를 검색 대상에서 제외합니다.</p>
        <label htmlFor="deactivate-reason">비활성화 사유 *</label><textarea id="deactivate-reason" name="reason" rows={3} required />
        <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setPanel(null)}>취소</button><button type="submit" className="button-danger" disabled={busy}>비활성화 확인</button></div>
      </form></div> : null}
      {panel === "history" && history ? <div className="management-panel"><h3>불변 버전 이력</h3>{history.contents.length === 0 ? <p className="state-message">변경 이력이 없습니다.</p> : <div className="table-scroll"><table><thead><tr><th>버전</th><th>버전 ID</th><th>적용일</th><th>변경 사유</th><th>등록자</th></tr></thead><tbody>{history.contents.map((item) => <tr key={item.standardVersionId}><td>{item.version}</td><td>{item.standardVersionId}</td><td>{formatDate(item.effectiveDate)}</td><td>{item.changeReason ?? "최초 등록"}</td><td>{item.createdBy}</td></tr>)}</tbody></table></div>}</div> : null}
      {panel === "chunks" && chunks ? <div className="management-panel"><h3>관리자 Chunk 확인</h3><p className="panel-note">내부 collection, index, point, document 식별자는 화면에 표시하지 않습니다.</p>{chunks.contents.length === 0 ? <p className="state-message">생성된 Chunk가 없습니다.</p> : <div className="chunk-list">{chunks.contents.map((chunk) => <article key={chunk.evidenceChunkId}><h4>Chunk {chunk.chunkNo} · {chunk.articleNo ?? chunk.sectionPath ?? "구조 정보 없음"}</h4><p>{chunk.chunkText}</p><small>토큰 {chunk.tokenCount ?? "-"} · Qdrant {chunk.qdrantIndexStatus} · OpenSearch {chunk.opensearchIndexStatus}</small></article>)}</div>}</div> : null}
      {panel === "reindex" && selectedDetail ? <div className="management-panel"><h3>기준자료 재색인</h3><form className="form-grid" onSubmit={(event) => void requestReindex(event)}>
        <p className="form-help">{selectedDetail.version} 버전을 Qdrant와 OpenSearch에 동일한 deterministic ID로 재색인합니다.</p>
        <label htmlFor="reindex-reason">재색인 사유 *</label><textarea id="reindex-reason" value={reindexReason} onChange={(event) => setReindexReason(event.target.value)} rows={3} required />
        <div className="form-actions"><button type="submit" disabled={busy || !reindexReason.trim()}>재색인 요청</button></div>
      </form>{reindexJob ? <div className="job-status" aria-live="polite"><strong>{reindexJob.jobStatus}</strong><span>처리 Chunk {reindexJob.indexedChunkCount}/{reindexJob.createdChunkCount}</span><span>Qdrant {reindexJob.qdrantStatus ?? "-"}</span><span>OpenSearch {reindexJob.opensearchStatus ?? "-"}</span><button type="button" className="button-secondary" onClick={() => void runAction(async () => setReindexJob(await api.getStandardReindexJob(token, reindexJob.jobId)))}>상태 새로고침</button></div> : null}</div> : null}

      <div className="management-panel evidence-search-panel"><h3>근거 Hybrid Search 검증</h3><form className="search-bar" onSubmit={(event) => void searchEvidence(event)}><label htmlFor="evidence-keyword">근거 검색어</label><input id="evidence-keyword" value={evidenceKeyword} onChange={(event) => setEvidenceKeyword(event.target.value)} /><button type="submit">근거 검색</button></form>
        {searchError ? <ErrorState error={searchError} /> : null}
        {evidenceResults?.length === 0 ? <p className="state-message">검색된 근거가 없습니다.</p> : null}
        {evidenceResults && evidenceResults.length > 0 ? <ol className="evidence-results">{evidenceResults.map((result) => <li key={result.evidenceChunkId}><strong>{result.title}</strong><span>{result.matchSource} · {result.rankNo}위 · {result.relevanceScore.toFixed(4)}</span><p>{result.contentSummary}</p></li>)}</ol> : null}
      </div>
    </section>
  );
}
