import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, type AdvertisementCreateResponse, type AdvertisementType, type ProductGroup, type ReviewType, userMessage } from "../api/client";
import { operationalMode, operationalRequest, type OperationalCapabilities } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import { advertisementTypeLabel, productGroupLabel } from "../components/displayLabels";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/RequestState";
import { WorkflowSteps } from "../components/WorkflowSteps";

const ALLOWED_EXTENSIONS = new Set(["jpg", "jpeg", "png", "pdf", "hwp", "hwpx"]);
const MAX_FILE_SIZE = 50 * 1024 * 1024;
const MAX_OPERATIONAL_ADS = 20;
const MAX_FILES_PER_AD = 20;
const FULL_REVIEW_TYPES: ReviewType[] = ["REQUIRED_PHRASE", "INTEREST_RATE", "MISLEADING_EXPRESSION", "PRODUCT_CONSISTENCY", "VISIBILITY"];
const PRODUCT_GROUPS = new Set<ProductGroup>(["DEPOSIT", "SAVINGS", "DEMAND_DEPOSIT", "EVENT", "LOAN"]);
const ADVERTISEMENT_TYPES = new Set<AdvertisementType>(["BRANCH_FLYER", "NOTICE", "MOBILE_BANNER", "WEB_BANNER", "WEB_PRODUCT_PAGE", "EVENT_PAGE", "SOCIAL_MEDIA", "VIDEO", "EMAIL", "OUTDOOR", "PRINT_AD", "PUSH", "SMS", "ALIMTALK", "OTHER"]);

type OperationalAdvertisementDraft = {
  key: string;
  advertisementName: string;
  productGroup: ProductGroup | "";
  advertisementType: AdvertisementType | "";
  productClassificationCode: string;
  files: File[];
  created?: AdvertisementCreateResponse;
};

let draftSequence = 0;
function createOperationalDraft(): OperationalAdvertisementDraft {
  draftSequence += 1;
  return { key: `advertisement-draft-${draftSequence}`, advertisementName: "", productGroup: "", advertisementType: "", productClassificationCode: "", files: [] };
}

function fileErrors(files: Array<{ label: string; file: File }>): string[] {
  const errors: string[] = [];
  for (const { label, file } of files) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ALLOWED_EXTENSIONS.has(extension)) errors.push(`${label}: 지원하지 않는 파일 형식입니다. JPG, PNG, PDF, HWP, HWPX 파일을 선택해 주세요.`);
    if (file.size === 0) errors.push(`${label}: 비어 있는 파일은 등록할 수 없습니다.`);
    if (file.size > MAX_FILE_SIZE) errors.push(`${label}: 파일 용량이 50MB를 초과했습니다.`);
  }
  return errors;
}

export function AdvertisementCreatePage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const token = session?.accessToken ?? "";
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);
  const [operationalDrafts, setOperationalDrafts] = useState<OperationalAdvertisementDraft[]>([createOperationalDraft()]);
  const [advertisementFiles, setAdvertisementFiles] = useState<File[]>([]);
  const [productDescriptionFile, setProductDescriptionFile] = useState<File | null>(null);
  const [termsFile, setTermsFile] = useState<File | null>(null);
  const [additionalFiles, setAdditionalFiles] = useState<File[]>([]);
  const productGroups = useQuery({ queryKey: ["codes", "product-groups"], queryFn: () => api.getCodes(token, "product-groups") });
  const advertisementTypes = useQuery({ queryKey: ["codes", "advertisement-types"], queryFn: () => api.getCodes(token, "advertisement-types") });
  const capabilities = useQuery({ queryKey: ["operational-capabilities"], queryFn: () => operationalRequest<OperationalCapabilities>(token, "capabilities"), enabled: operationalMode, retry: false });

  function updateDraft<K extends keyof OperationalAdvertisementDraft>(key: string, field: K, value: OperationalAdvertisementDraft[K]) {
    setOperationalDrafts((current) => current.map((draft) => draft.key === key ? { ...draft, [field]: value } : draft));
  }

  async function registerOperationalAdvertisement(draft: OperationalAdvertisementDraft): Promise<string> {
    const productGroup = draft.productGroup as ProductGroup;
    const advertisementType = draft.advertisementType as AdvertisementType;
    const created = draft.created ?? await api.createAdvertisement(token, {
        advertisementName: draft.advertisementName.trim(), productGroup, advertisementType, channelType: "",
        departmentId: session?.user.departmentId ?? "", memo: "", advertisementFile: draft.files[0],
        advertisementFiles: draft.files, additionalFiles: [],
      });
    if (!draft.created) updateDraft(draft.key, "created", created);
    await operationalRequest(token, `advertisements/${created.advertisementId}/routing`, { product_classification_code: draft.productClassificationCode });
    const normalizedProductGroup = productGroup === "LOAN" ? "대출성" : "예금성";
    const advertisementAssets = created.files.filter((file) => file.fileType === "ADVERTISEMENT");
    await operationalRequest(token, `advertisements/${created.advertisementId}/intake`, {
      schema_version: "operational-ad-intake-v1", advertisement_name: created.advertisementName,
      media_codes: [advertisementType],
      assets: advertisementAssets.map((file) => ({ asset_id: file.fileId, file_name: file.fileName })),
      products: [{ product_id: "P-1", product_name: draft.advertisementName.trim(),
        product_group: draft.productClassificationCode.startsWith("대출성") ? "대출성" : normalizedProductGroup,
        product_classification_code: draft.productClassificationCode,
        asset_scopes: advertisementAssets.map((file) => ({ asset_id: file.fileId, page_ranges: null })) }],
      shared_asset_scopes: [], follow_up: null,
    });
    await api.requestAdvertisementReview(token, created.advertisementId, {
      standardEffectiveDate: new Date().toISOString().slice(0, 10), reviewTypes: FULL_REVIEW_TYPES,
      includeSuggestion: false, includeOpinionDraft: false, requestMemo: null,
    });
    return created.advertisementId;
  }

  async function submitOperational() {
    const errors: string[] = [];
    if (operationalDrafts.length > MAX_OPERATIONAL_ADS) errors.push(`광고는 한 번에 최대 ${MAX_OPERATIONAL_ADS}건까지 등록할 수 있습니다.`);
    operationalDrafts.forEach((draft, index) => {
      const prefix = `광고 ${index + 1}`;
      if (!draft.advertisementName.trim()) errors.push(`${prefix}: 광고명을 입력해 주세요.`);
      if (!PRODUCT_GROUPS.has(draft.productGroup as ProductGroup)) errors.push(`${prefix}: 상품군을 선택해 주세요.`);
      if (!draft.productClassificationCode) errors.push(`${prefix}: 상세 상품군을 선택해 주세요.`);
      if (!ADVERTISEMENT_TYPES.has(draft.advertisementType as AdvertisementType)) errors.push(`${prefix}: 광고유형을 선택해 주세요.`);
      if (draft.files.length === 0) errors.push(`${prefix}: 광고 원본을 선택해 주세요.`);
      if (draft.files.length > MAX_FILES_PER_AD) errors.push(`${prefix}: 동일 광고 파일은 최대 ${MAX_FILES_PER_AD}개까지 첨부할 수 있습니다.`);
      errors.push(...fileErrors(draft.files.map((file, fileIndex) => ({ label: `${prefix} 파일 ${fileIndex + 1}`, file }))));
    });
    setFieldErrors(errors);
    if (errors.length > 0) return;
    setSubmitting(true);
    setFormError(null);
    const results = await Promise.allSettled(operationalDrafts.map(registerOperationalAdvertisement));
    const failedIndexes = results.flatMap((result, index) => result.status === "rejected" ? [index] : []);
    if (failedIndexes.length === 0) {
      navigate("/advertisements", { replace: true });
    } else {
      const failed = new Set(failedIndexes);
      setOperationalDrafts((current) => current.filter((_, index) => failed.has(index)));
      setFormError(`${results.length - failedIndexes.length}건은 등록·검토 요청됐고 ${failedIndexes.length}건은 실패했습니다. 화면에 남은 광고만 확인한 뒤 다시 요청해 주세요.`);
      setFieldErrors(failedIndexes.map((index) => `광고 ${index + 1}: ${userMessage((results[index] as PromiseRejectedResult).reason)}`));
    }
    setSubmitting(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (operationalMode) { await submitOperational(); return; }
    const form = new FormData(event.currentTarget);
    const productGroup = String(form.get("productGroup") ?? "") as ProductGroup;
    const advertisementType = String(form.get("advertisementType") ?? "") as AdvertisementType;
    const missing: string[] = [];
    if (!String(form.get("advertisementName") ?? "").trim()) missing.push("광고명을 입력해 주세요.");
    if (!PRODUCT_GROUPS.has(productGroup)) missing.push("상품군을 선택해 주세요.");
    if (!ADVERTISEMENT_TYPES.has(advertisementType)) missing.push("광고유형을 선택해 주세요.");
    if (advertisementFiles.length === 0) missing.push("광고 파일을 선택해 주세요.");
    const selectedFiles = [...advertisementFiles.map((file, index) => ({ label: `광고 파일 ${index + 1}`, file })),
      ...(productDescriptionFile ? [{ label: "상품설명서", file: productDescriptionFile }] : []),
      ...(termsFile ? [{ label: "약관", file: termsFile }] : []),
      ...additionalFiles.map((file, index) => ({ label: `추가 첨부 ${index + 1}`, file }))];
    if (additionalFiles.length > 10) missing.push("추가 첨부파일은 최대 10개까지 선택할 수 있습니다.");
    missing.push(...fileErrors(selectedFiles));
    setFieldErrors(missing);
    if (missing.length > 0) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await api.createAdvertisement(token, {
        advertisementName: String(form.get("advertisementName") ?? "").trim(), productGroup, advertisementType,
        channelType: String(form.get("channelType") ?? ""), departmentId: session?.user.departmentId ?? "",
        memo: String(form.get("memo") ?? ""), advertisementFile: advertisementFiles[0], advertisementFiles,
        productDescriptionFile: productDescriptionFile ?? undefined, termsFile: termsFile ?? undefined, additionalFiles,
      });
      navigate(`/advertisements/${encodeURIComponent(created.advertisementId)}`);
    } catch (cause) { setFormError(userMessage(cause)); } finally { setSubmitting(false); }
  }

  const codesPending = productGroups.isPending || advertisementTypes.isPending;
  const codesError = productGroups.error ?? advertisementTypes.error;
  return <section aria-labelledby="advertisement-create-heading">
    <WorkflowSteps current={1} />
    <PageHeader headingId="advertisement-create-heading" eyebrow="1단계 · 광고 등록" title="광고물 등록"
      description={operationalMode ? "광고별로 기본정보와 원본 파일을 묶어 한 번에 등록하고 독립적으로 자동심의를 시작합니다." : "검토할 광고 원본을 필수로 등록하고, 상품설명서·약관을 함께 첨부하면 정합성 검토 정확도를 높일 수 있습니다."} />
    {codesPending ? <LoadingState label="등록 선택값을 불러오는 중입니다." /> : null}
    {codesError ? <ErrorState error={codesError} /> : null}
    {!codesPending && !codesError ? <form className="form-layout" onSubmit={submit} noValidate>
      {operationalMode ? <section className="form-section" aria-labelledby="advertisement-batch-heading">
        <div className="form-section-heading"><span>01</span><div><h3 id="advertisement-batch-heading">등록할 광고</h3><p>광고 하나당 카드 하나를 사용합니다. 한 카드에 첨부한 여러 파일은 모두 동일 광고로 묶입니다.</p></div></div>
        <div className="operational-ad-list">{operationalDrafts.map((draft, index) => <article className="operational-ad-card" key={draft.key}>
          <header><div><strong>광고 {index + 1}</strong><small>{draft.created ? "광고 등록 완료 · 후속 단계만 재요청" : "독립 파싱·검색·판정 작업"}</small></div>{operationalDrafts.length > 1 ? <button type="button" className="button-secondary compact-button" disabled={submitting} onClick={() => setOperationalDrafts((current) => current.filter((item) => item.key !== draft.key))}>삭제</button> : null}</header>
          <div className="form-field-grid">
            <label htmlFor={`${draft.key}-name`}><span>광고명 *</span><input id={`${draft.key}-name`} disabled={Boolean(draft.created)} value={draft.advertisementName} onChange={(event) => updateDraft(draft.key, "advertisementName", event.target.value)} /></label>
            <label htmlFor={`${draft.key}-type`}><span>광고유형 *</span><select id={`${draft.key}-type`} disabled={Boolean(draft.created)} value={draft.advertisementType} onChange={(event) => updateDraft(draft.key, "advertisementType", event.target.value as AdvertisementType)}><option value="" disabled>선택</option>{advertisementTypes.data?.filter((item) => item.enabled).map((item) => <option key={item.code} value={item.code}>{advertisementTypeLabel(item.code)}</option>)}</select></label>
            <label htmlFor={`${draft.key}-group`}><span>상품군 *</span><select id={`${draft.key}-group`} disabled={Boolean(draft.created)} value={draft.productGroup} onChange={(event) => { updateDraft(draft.key, "productGroup", event.target.value as ProductGroup); updateDraft(draft.key, "productClassificationCode", ""); }}><option value="" disabled>선택</option>{productGroups.data?.filter((item) => item.enabled && ["DEPOSIT", "LOAN"].includes(item.code)).map((item) => <option key={item.code} value={item.code}>{item.code === "DEPOSIT" ? "예금성상품" : "대출성상품"}</option>)}</select><small>예금·적금·입출금 구분은 아래 상세 상품군에서 선택합니다.</small></label>
            <label htmlFor={`${draft.key}-classification`}><span>상세 상품군 *</span><select id={`${draft.key}-classification`} disabled={Boolean(draft.created)} value={draft.productClassificationCode} onChange={(event) => updateDraft(draft.key, "productClassificationCode", event.target.value)}><option value="" disabled>선택</option>{capabilities.data?.productClassifications.filter((item) => draft.productGroup && item.productGroup === (draft.productGroup === "LOAN" ? "LOAN" : "DEPOSIT")).map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}</select><small>선택값은 이 카드에 첨부한 모든 파일에 공통 적용됩니다.</small></label>
          </div>
          <label className="file-input-card" data-required="true" htmlFor={`${draft.key}-files`}><span>동일 광고 원본 *</span><small>한 광고를 구성하는 파일을 함께 선택 · 파일당 50MB</small><input id={`${draft.key}-files`} type="file" multiple disabled={Boolean(draft.created)} aria-label={`광고 ${index + 1} 원본 파일`} accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => updateDraft(draft.key, "files", Array.from(event.target.files ?? []))} /></label>
          {draft.files.length > 0 ? <p className="operational-file-summary">{draft.files.length}개 파일을 하나의 광고로 처리: {draft.files.map((file) => file.name).join(" · ")}</p> : null}
        </article>)}</div>
        <button type="button" className="button-secondary add-advertisement-button" disabled={submitting || operationalDrafts.length >= MAX_OPERATIONAL_ADS} onClick={() => setOperationalDrafts((current) => [...current, createOperationalDraft()])}>+ 다른 광고 추가</button>
        <p className="panel-note">광고들은 서로 내용을 섞지 않고 독립 판정하며, 등록·검토 요청은 병렬로 시작합니다. 최대 {MAX_OPERATIONAL_ADS}개 광고를 한 번에 등록할 수 있습니다.</p>
      </section> : <>
        <section className="form-section" aria-labelledby="advertisement-basic-heading"><div className="form-section-heading"><span>01</span><div><h3 id="advertisement-basic-heading">기본 정보</h3><p>광고를 구분하고 적용 범위를 확인하는 정보입니다.</p></div></div><div className="form-field-grid">
          <label htmlFor="advertisementName"><span>광고명 *</span><input id="advertisementName" name="advertisementName" /></label>
          <label htmlFor="productGroup"><span>상품군 *</span><select id="productGroup" name="productGroup" defaultValue=""><option value="" disabled>선택</option>{productGroups.data?.filter((item) => item.enabled).map((item) => <option key={item.code} value={item.code}>{productGroupLabel(item.code)}</option>)}</select></label>
          <label htmlFor="advertisementType"><span>광고유형 *</span><select id="advertisementType" name="advertisementType" defaultValue=""><option value="" disabled>선택</option>{advertisementTypes.data?.filter((item) => item.enabled).map((item) => <option key={item.code} value={item.code}>{advertisementTypeLabel(item.code)}</option>)}</select></label>
          <label htmlFor="channelType"><span>광고채널</span><select id="channelType" name="channelType" defaultValue=""><option value="">선택 안 함</option><option value="MOBILE_APP">모바일 앱</option><option value="INTERNET_BANKING">인터넷뱅킹</option><option value="BRANCH">영업점</option></select></label>
          <label><span>담당부서</span><output>{session?.user.departmentName}</output></label>
        </div></section>
        <section className="form-section" aria-labelledby="advertisement-files-heading"><div className="form-section-heading"><span>02</span><div><h3 id="advertisement-files-heading">검토 자료</h3><p>광고 원본은 필수이며 관련 문서를 함께 등록하면 정합성 검토에 활용됩니다.</p></div></div><div className="form-file-grid">
          <label htmlFor="advertisementFile" className="file-input-card" data-required="true"><span>광고 원본 *</span><small>JPG, PNG, PDF, HWP, HWPX · 최대 50MB</small><input id="advertisementFile" name="advertisementFile" type="file" aria-label="광고 원본 *" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setAdvertisementFiles(Array.from(event.target.files ?? []).slice(0, 1))} /></label>
          <label htmlFor="productDescriptionFile" className="file-input-card"><span>상품설명서</span><small>상품 조건 정합성 검토에 활용</small><input id="productDescriptionFile" name="productDescriptionFile" type="file" aria-label="상품설명서" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setProductDescriptionFile(event.target.files?.[0] ?? null)} /></label>
          <label htmlFor="termsFile" className="file-input-card"><span>약관</span><small>상품 조건·필수 안내 비교에 활용</small><input id="termsFile" name="termsFile" type="file" aria-label="약관" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setTermsFile(event.target.files?.[0] ?? null)} /></label>
          <label htmlFor="additionalFiles" className="file-input-card"><span>추가 첨부파일</span><small>최대 10개</small><input id="additionalFiles" name="additionalFiles" type="file" aria-label="추가 첨부파일" multiple accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setAdditionalFiles(Array.from(event.target.files ?? []))} /></label>
        </div></section>
        <section className="form-section" aria-labelledby="advertisement-note-heading"><div className="form-section-heading"><span>03</span><div><h3 id="advertisement-note-heading">검토 메모</h3><p>담당자가 참고해야 할 조건이나 확인 사항을 남깁니다.</p></div></div><label htmlFor="memo"><span>비고</span><textarea id="memo" name="memo" rows={4} placeholder="예: 우대금리 조건과 이벤트 기간을 중점적으로 확인해 주세요." /></label></section>
      </>}
      {fieldErrors.length > 0 ? <div role="alert" className="field-error"><strong>입력 또는 처리 결과를 확인해 주세요.</strong><ul>{fieldErrors.map((error) => <li key={error}>{error}</li>)}</ul></div> : null}
      {formError ? <p role="alert" className="field-error">{formError}</p> : null}
      <div className="form-actions"><Link className="button-link button-secondary" to="/advertisements">취소</Link><button type="submit" disabled={submitting}>{submitting ? "등록·검토 요청 중..." : operationalMode ? `광고 ${operationalDrafts.length}개 등록 후 자동심의` : "광고물 등록"}</button></div>
    </form> : null}
  </section>;
}
