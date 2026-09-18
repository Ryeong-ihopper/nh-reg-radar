import { resolveApiUrl } from "./client";

// Opt-in local bridge only. Production API contracts remain unchanged.
export const operationalMode = import.meta.env.VITE_OPERATIONAL_REVIEW === "true";

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
    canvas_w: number;
    canvas_h: number;
    regions: ParserLayoutRegion[];
  }>;
  counts: { pages: number; regions: number; lines: number };
}

export async function operationalRequest<T>(token: string, path: string, body?: object): Promise<T> {
  const response = await fetch(resolveApiUrl(`/operational/${path}`), {
    method: body ? "PUT" : "GET",
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.message ?? "자동심의 연결 요청 실패");
  return data as T;
}

export async function cancelOperationalReview(token: string, reviewId: string): Promise<void> {
  const response = await fetch(resolveApiUrl(`/operational/reviews/${encodeURIComponent(reviewId)}/cancel`), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { message?: string };
    throw new Error(body.message ?? "검토 중단 요청에 실패했습니다.");
  }
}

export async function deleteLatestOperationalReview(token: string, advertisementId: string): Promise<void> {
  const response = await fetch(resolveApiUrl(`/operational/advertisements/${encodeURIComponent(advertisementId)}/latest-review`), {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { message?: string };
    throw new Error(body.message ?? "심의 결과 삭제에 실패했습니다.");
  }
}
