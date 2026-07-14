import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, type AdvertisementType, type ProductGroup, userMessage } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";

const ALLOWED_EXTENSIONS = new Set(["jpg", "jpeg", "png", "pdf", "hwp", "hwpx"]);
const MAX_FILE_SIZE = 50 * 1024 * 1024;
const PRODUCT_GROUPS = new Set<ProductGroup>(["DEPOSIT", "SAVINGS", "DEMAND_DEPOSIT", "EVENT"]);
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
      <p className="eyebrow">S-003</p><h2 id="advertisement-create-heading">광고물 등록</h2>
      {codesPending ? <LoadingState label="등록 선택값을 불러오는 중입니다." /> : null}
      {codesError ? <ErrorState error={codesError} /> : null}
      {!codesPending && !codesError ? (
        <form className="form-grid" onSubmit={submit} noValidate>
          <label htmlFor="advertisementName">광고명 *</label><input id="advertisementName" name="advertisementName" />
          <label htmlFor="productGroup">상품군 *</label><select id="productGroup" name="productGroup" defaultValue=""><option value="" disabled>선택</option>{productGroups.data?.filter((item) => item.enabled).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select>
          <label htmlFor="advertisementType">광고유형 *</label><select id="advertisementType" name="advertisementType" defaultValue=""><option value="" disabled>선택</option>{advertisementTypes.data?.filter((item) => item.enabled).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select>
          <label htmlFor="channelType">광고채널</label><select id="channelType" name="channelType" defaultValue=""><option value="">선택 안 함</option><option value="MOBILE_APP">모바일 앱</option><option value="INTERNET_BANKING">인터넷뱅킹</option><option value="BRANCH">영업점</option></select>
          <label>담당부서</label><output>{session?.user.departmentName} ({session?.user.departmentId})</output>
          <label htmlFor="advertisementFile">광고 파일 *</label><input id="advertisementFile" name="advertisementFile" type="file" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setAdvertisementFile(event.target.files?.[0] ?? null)} />
          <label htmlFor="productDescriptionFile">상품설명서</label><input id="productDescriptionFile" name="productDescriptionFile" type="file" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setProductDescriptionFile(event.target.files?.[0] ?? null)} />
          <label htmlFor="termsFile">약관</label><input id="termsFile" name="termsFile" type="file" accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setTermsFile(event.target.files?.[0] ?? null)} />
          <label htmlFor="additionalFiles">추가 첨부파일</label><input id="additionalFiles" name="additionalFiles" type="file" multiple accept=".jpg,.jpeg,.png,.pdf,.hwp,.hwpx" onChange={(event) => setAdditionalFiles(Array.from(event.target.files ?? []))} />
          <label htmlFor="memo">비고</label><textarea id="memo" name="memo" rows={4} />
          {fieldErrors.length > 0 ? <div role="alert" className="field-error"><strong>필수 입력 항목을 확인해 주세요.</strong><ul>{fieldErrors.map((error) => <li key={error}>{error}</li>)}</ul></div> : null}
          {formError ? <p role="alert" className="field-error">{formError}</p> : null}
          <div className="form-actions"><Link to="/advertisements">취소</Link><button type="submit" disabled={submitting}>{submitting ? "등록 중..." : "저장"}</button></div>
        </form>
      ) : null}
    </section>
  );
}
