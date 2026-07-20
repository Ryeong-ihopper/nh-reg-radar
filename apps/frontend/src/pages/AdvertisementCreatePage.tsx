import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, type AdvertisementType, type ProductGroup, userMessage } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/RequestState";
import { WorkflowSteps } from "../components/WorkflowSteps";

const ALLOWED_EXTENSIONS = new Set(["jpg", "jpeg", "png", "pdf", "hwp", "hwpx"]);
const MAX_FILE_SIZE = 50 * 1024 * 1024;
const PRODUCT_GROUPS = new Set<ProductGroup>(["DEPOSIT", "SAVINGS", "DEMAND_DEPOSIT", "EVENT", "LOAN"]);
const ADVERTISEMENT_TYPES = new Set<AdvertisementType>(["BRANCH_FLYER", "NOTICE", "MOBILE_BANNER", "WEB_BANNER", "EVENT_PAGE", "PUSH", "SMS", "ALIMTALK"]);

export function AdvertisementCreatePage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const token = session?.accessToken ?? "";
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);
  const [advertisementFile, setAdvertisementFile] = useState<File | null>(null);
  const [productDescriptionFile, setProductDescriptionFile] = useState<File | null>(null);
  const [termsFile, setTermsFile] = useState<File | null>(null);
  const [additionalFiles, setAdditionalFiles] = useState<File[]>([]);
  const productGroups = useQuery({ queryKey: ["codes", "product-groups"], queryFn: () => api.getCodes(token, "product-groups") });
  const advertisementTypes = useQuery({ queryKey: ["codes", "advertisement-types"], queryFn: () => api.getCodes(token, "advertisement-types") });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const productGroup = String(form.get("productGroup") ?? "") as ProductGroup;
    const advertisementType = String(form.get("advertisementType") ?? "") as AdvertisementType;
    const missing: string[] = [];
    if (!String(form.get("advertisementName") ?? "").trim()) missing.push("광고명을 입력해 주세요.");
    if (!PRODUCT_GROUPS.has(productGroup)) missing.push("상품군을 선택해 주세요.");
    if (!ADVERTISEMENT_TYPES.has(advertisementType)) missing.push("광고유형을 선택해 주세요.");
    if (!advertisementFile || advertisementFile.size === 0) missing.push("광고 파일을 선택해 주세요.");
    const selectedFiles = [
      ...(advertisementFile ? [{ label: "광고 파일", file: advertisementFile }] : []),
      ...(productDescriptionFile ? [{ label: "상품설명서", file: productDescriptionFile }] : []),
      ...(termsFile ? [{ label: "약관", file: termsFile }] : []),
      ...additionalFiles.map((file, index) => ({ label: `추가 첨부 ${index + 1}`, file })),
    ];
    if (additionalFiles.length > 10) missing.push("추가 첨부파일은 최대 10개까지 선택할 수 있습니다.");
    for (const { label, file } of selectedFiles) {
      const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
      if (!ALLOWED_EXTENSIONS.has(extension)) missing.push(`${label}: 지원하지 않는 파일 형식입니다. jpg, jpeg, png, pdf, hwp, hwpx 파일을 선택해 주세요.`);
      if (file.size > MAX_FILE_SIZE) missing.push(`${label}: 파일 용량이 50MB를 초과했습니다.`);
    }
    setFieldErrors(missing);
    if (missing.length > 0 || !advertisementFile) return;

    setSubmitting(true);
    setFormError(null);
    try {
      const created = await api.createAdvertisement(token, {
        advertisementName: String(form.get("advertisementName")).trim(),
        productGroup,
        advertisementType,
        channelType: String(form.get("channelType") ?? ""),
        departmentId: session?.user.departmentId ?? "",
        memo: String(form.get("memo") ?? ""),
        advertisementFile,
        productDescriptionFile: productDescriptionFile && productDescriptionFile.size > 0 ? productDescriptionFile : undefined,
        termsFile: termsFile && termsFile.size > 0 ? termsFile : undefined,
        additionalFiles,
      });
      navigate(`/advertisements/${encodeURIComponent(created.advertisementId)}`, { replace: true });
    } catch (cause) {
      setFormError(userMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  const codesPending = productGroups.isPending || advertisementTypes.isPending;
  const codesError = productGroups.error ?? advertisementTypes.error;
  return (
    <section aria-labelledby="advertisement-create-heading">
      <WorkflowSteps current={1} />
      <PageHeader
        headingId="advertisement-create-heading"
        eyebrow="1단계 · 광고 등록"
        title="광고물 등록"
        description="검토할 광고 원본을 필수로 등록하고, 상품설명서·약관을 함께 첨부하면 정합성 검토 정확도를 높일 수 있습니다."
      />
      {codesPending ? <LoadingState label="등록 선택값을 불러오는 중입니다." /> : null}
      {codesError ? <ErrorState error={codesError} /> : null}
      {!codesPending && !codesError ? (
        <form className="form-layout" onSubmit={submit} noValidate>
          <section className="form-section" aria-labelledby="advertisement-basic-heading"><div className="form-section-heading"><span>01</span><div><h3 id="advertisement-basic-heading">기본 정보</h3><p>광고를 구분하고 적용 범위를 확인하는 정보입니다.</p></div></div><div className="form-field-grid">
            <label htmlFor="advertisementName"><span>광고명 *</span><input id="advertisementName" name="advertisementName" /></label>
            <label htmlFor="productGroup"><span>상품군 *</span><select id="productGroup" name="productGroup" defaultValue=""><option value="" disabled>선택</option>{productGroups.data?.filter((item) => item.enabled).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
            <label htmlFor="advertisementType"><span>광고유형 *</span><select id="advertisementType" name="advertisementType" defaultValue=""><option value="" disabled>선택</option>{advertisementTypes.data?.filter((item) => item.enabled).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
            <label htmlFor="channelType"><span>광고채널</span><select id="channelType" name="channelType" defaultValue=""><option value="">선택 안 함</option><option value="MOBILE_APP">모바일 앱</option><option value="INTERNET_BANKING">인터넷뱅킹</option><option value="BRANCH">영업점</option></select></label>
            <label><span>담당부서</span><output>{session?.user.departmentName}</output></label>
          </div></section>
          <section className="form-section" aria-labelledby="advertisement-files-heading"><div className="form-section-heading"><span>02</span><div><h3 id="advertisement-files-heading">검토 자료</h3><p>광고 원본은 필수이며 관련 문서를 함께 등록하면 정합성 검토에 활용됩니다.</p></div></div><div className="form-file-grid">
            <label htmlFor="advertisementFile" className="file-input-card" data-required="true"><span>광고 원본 *</span><small>JPG, PNG, PDF, HWP, HWPX · 최대 50MB</small><input id="advertisementFile" name="advertisementFile" type="file" aria-label="광고 원본 *" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setAdvertisementFile(event.target.files?.[0] ?? null)} /></label>
            <label htmlFor="productDescriptionFile" className="file-input-card"><span>상품설명서</span><small>상품 조건 정합성 검토에 활용</small><input id="productDescriptionFile" name="productDescriptionFile" type="file" aria-label="상품설명서" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setProductDescriptionFile(event.target.files?.[0] ?? null)} /></label>
            <label htmlFor="termsFile" className="file-input-card"><span>약관</span><small>상품 조건·필수 안내 비교에 활용</small><input id="termsFile" name="termsFile" type="file" aria-label="약관" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setTermsFile(event.target.files?.[0] ?? null)} /></label>
            <label htmlFor="additionalFiles" className="file-input-card"><span>추가 첨부파일</span><small>최대 10개</small><input id="additionalFiles" name="additionalFiles" type="file" aria-label="추가 첨부파일" multiple accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setAdditionalFiles(Array.from(event.target.files ?? []))} /></label>
          </div></section>
          <section className="form-section" aria-labelledby="advertisement-note-heading"><div className="form-section-heading"><span>03</span><div><h3 id="advertisement-note-heading">검토 메모</h3><p>담당자가 참고해야 할 조건이나 확인 사항을 남깁니다.</p></div></div><label htmlFor="memo"><span>비고</span><textarea id="memo" name="memo" rows={4} placeholder="예: 우대금리 조건과 이벤트 기간을 중점적으로 확인해 주세요." /></label></section>
          {fieldErrors.length > 0 ? <div role="alert" className="field-error"><strong>필수 입력 항목을 확인해 주세요.</strong><ul>{fieldErrors.map((error) => <li key={error}>{error}</li>)}</ul></div> : null}
          {formError ? <p role="alert" className="field-error">{formError}</p> : null}
          <div className="form-actions"><Link className="button-link button-secondary" to="/advertisements">취소</Link><button type="submit" disabled={submitting}>{submitting ? "등록 중..." : "광고물 등록"}</button></div>
        </form>
      ) : null}
    </section>
  );
}
