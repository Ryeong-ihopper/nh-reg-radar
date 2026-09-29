import { refreshAuthentication, resolveApiUrl } from "./client";

// Opt-in local bridge only. Production API contracts remain unchanged.
export const operationalMode = import.meta.env.VITE_OPERATIONAL_REVIEW === "true";
export const localAuthBypass = operationalMode
  && typeof window !== "undefined"
  && ["localhost", "127.0.0.1"].includes(window.location.hostname);

export interface ProductClassificationOption {
  code: string;
  label: string;
  productGroup: "DEPOSIT" | "LOAN" | "INVESTMENT";
}

export interface OperationalCapabilities {
  enabled: boolean;
  productClassifications: ProductClassificationOption[];
  regulation: string;
  sourcePolicy: "template-only" | "template-plus-v2";
  progressMeaning: string;
  productContexts?: Array<{
    code: string;
    label: string;
    base_template: string;
    components: Array<{ code: string; label: string; template: string }>;
    restricted_standalone_templates: string[];
  }>;
  templatePlanCounts?: Record<string, number>;
  evidencePolicy?: string;
}

export interface ParserLayoutLine {
  line_ref: string | null;
  text: string;
  bbox: [number, number, number, number];
  text_source: string | null;
  confidence: number | null;
}

export interface ParserLayoutRegion {
  region_id: string | null;
  bbox: [number, number, number, number];
  layout_label: string | null;
  text: string;
  lines: ParserLayoutLine[];
}

export interface ParserLayout {
  schema_version: "operational-parser-layout-v1";
  source: string;
  coordinate_basis: string;
  pages: Array<{
    page_no: number;
    asset_id?: string | null;
    source_page_no?: number;
    preview_path?: string;
    canvas_w: number;
    canvas_h: number;
    regions: ParserLayoutRegion[];
  }>;
  counts: { pages: number; regions: number; lines: number };
}

async function fetchOperational(token: string, path: string, init: RequestInit): Promise<Response> {
  const request = (accessToken: string) => fetch(resolveApiUrl(path), {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${accessToken}` },
  });
  let response = await request(token);
  if (response.status === 401 && localAuthBypass) {
    const refreshed = await refreshAuthentication();
    if (refreshed) response = await request(refreshed.accessToken);
  }
  return response;
}

export async function operationalRequest<T>(token: string, path: string, body?: object): Promise<T> {
  const response = await fetchOperational(token, `/operational/${path}`, {
    method: body ? "PUT" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.message ?? "자동심의 연결 요청 실패");
  return data as T;
}

export async function cancelOperationalReview(token: string, reviewId: string): Promise<void> {
  const response = await fetchOperational(token, `/operational/reviews/${encodeURIComponent(reviewId)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { message?: string };
    throw new Error(body.message ?? "검토 중단 요청에 실패했습니다.");
  }
}

export async function deleteOperationalAdvertisement(token: string, advertisementId: string): Promise<void> {
  const response = await fetchOperational(token, `/operational/advertisements/${encodeURIComponent(advertisementId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { message?: string };
    throw new Error(body.message ?? "광고와 심의 결과 삭제에 실패했습니다.");
  }
}

export async function downloadOperationalResult(token: string, reviewId: string): Promise<Blob> {
  const response = await fetchOperational(token, `/operational/reviews/${encodeURIComponent(reviewId)}/export.json`, {});
  if (!response.ok) throw new Error("결과 JSON을 만들지 못했습니다.");
  return response.blob();
}

export async function getOperationalParserPreview(token: string, path: string): Promise<{ blob: Blob }> {
  const response = await fetchOperational(token, path, {});
  if (!response.ok) throw new Error("파서가 사용한 원문 화면을 불러올 수 없습니다.");
  return { blob: await response.blob() };
}

export async function getOperationalHwpHtml(token: string, reviewId: string, assetId: string): Promise<string> {
  const response = await fetchOperational(token,
    `/operational/reviews/${encodeURIComponent(reviewId)}/hwp-html/${encodeURIComponent(assetId)}`, {});
  if (!response.ok) throw new Error('HWP HTML 본문을 불러올 수 없습니다.');
  return response.text();
}
