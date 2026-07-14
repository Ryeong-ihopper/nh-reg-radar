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
export type FilePreview = components["schemas"]["FilePreview"];
export type ProductGroup = components["schemas"]["ProductGroup"];
export type AdvertisementType = components["schemas"]["AdvertisementType"];

export interface AdvertisementCreateInput {
  advertisementName: string;
  productGroup: ProductGroup;
  advertisementType: AdvertisementType;
  channelType?: string;
  departmentId: string;
  memo?: string;
  advertisementFile: File;
  productDescriptionFile?: File;
  termsFile?: File;
  additionalFiles?: File[];
}

export type AdvertisementSearch = NonNullable<operations["listAdvertisements"]["parameters"]["query"]>;

interface ErrorResponse {
  code?: unknown;
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
};

export class ApiError extends Error {
  public constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly traceId?: string,
  ) {
    super(ERROR_MESSAGES[code] ?? ERROR_MESSAGES.INTERNAL_ERROR);
    this.name = "ApiError";
  }
}

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  return configured ? configured.replace(/\/$/, "") : "/api/v1";
}

function resolveApiUrl(path: string): string {
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
  return new ApiError(response.status, code, traceId);
}

async function request<T>(path: string, accessToken?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(resolveApiUrl(path), {
    ...init,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    throw await readError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function requestBlob(path: string, accessToken: string): Promise<Blob> {
  const response = await fetch(resolveApiUrl(path), {
    headers: { Authorization: `Bearer ${accessToken}` },
    credentials: "include",
  });
  if (!response.ok) throw await readError(response);
  return response.blob();
}

export const api = {
  login(email: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>("/auth/login", undefined, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  logout(): Promise<void> {
    return request<void>("/auth/logout", undefined, { method: "POST" });
  },

  listAdvertisements(accessToken: string, search: AdvertisementSearch = {}): Promise<AdvertisementListResponse> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(search)) {
      if (value !== undefined && value !== "") {
        params.set(key, String(value));
      }
    }
    const query = params.size > 0 ? `?${params.toString()}` : "";
    return request<AdvertisementListResponse>(`/advertisements${query}`, accessToken);
  },

  getAdvertisement(accessToken: string, advertisementId: string): Promise<AdvertisementDetail> {
    return request<AdvertisementDetail>(`/advertisements/${encodeURIComponent(advertisementId)}`, accessToken);
  },

  getFilePreview(accessToken: string, fileId: string, pageNo = 1): Promise<FilePreview> {
    return request<FilePreview>(`/files/${encodeURIComponent(fileId)}/preview?pageNo=${pageNo}`, accessToken);
  },

  async getFilePreviewContent(accessToken: string, fileId: string, pageNo = 1): Promise<Blob> {
    const descriptor = await request<FilePreview>(`/files/${encodeURIComponent(fileId)}/preview?pageNo=${pageNo}`, accessToken);
    const expectedPath = `/api/v1/files/${encodeURIComponent(fileId)}/preview/content`;
    if (descriptor.previewPath !== expectedPath) {
      throw new ApiError(500, "INTERNAL_ERROR");
    }
    return requestBlob(`${descriptor.previewPath}?pageNo=${pageNo}`, accessToken);
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
    body.set("advertisementFile", input.advertisementFile);
    if (input.channelType) body.set("channelType", input.channelType);
    if (input.memo) body.set("memo", input.memo);
    if (input.productDescriptionFile) body.set("productDescriptionFile", input.productDescriptionFile);
    if (input.termsFile) body.set("termsFile", input.termsFile);
    for (const additionalFile of input.additionalFiles ?? []) body.append("additionalFiles", additionalFile);

    return request<AdvertisementCreateResponse>("/advertisements", accessToken, { method: "POST", body });
  },
};

export function userMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : ERROR_MESSAGES.INTERNAL_ERROR;
}
