import { useCallback, useEffect, useRef, useState } from "react";
import notoSansKoreanUrl from "@fontsource/noto-sans-kr/files/noto-sans-kr-korean-400-normal.woff2?url";

import { api, ApiError, type AdvertisementFile, userMessage } from "../api/client";
import { fileTypeLabel, formatFileSize } from "./displayLabels";

type PreviewAsset = { url: string; pageNo: number; totalPages: number };

export type PreviewFocus = { normalizedY: number };

function supportsPreview(file: AdvertisementFile): boolean {
  return ["image/png", "image/jpeg", "application/pdf", "application/x-hwp", "application/haansofthwp", "application/vnd.hancom.hwpx"].includes(file.mimeType)
    || /\.(hwp|hwpx)$/i.test(file.fileName);
}

let embeddedKoreanFont: Promise<string> | null = null;

function koreanFontDataUri(): Promise<string> {
  if (!embeddedKoreanFont) {
    embeddedKoreanFont = fetch(notoSansKoreanUrl)
      .then(async (response) => {
        if (!response.ok) throw new Error("Korean preview font could not be loaded");
        const bytes = new Uint8Array(await response.arrayBuffer());
        let binary = "";
        for (let start = 0; start < bytes.length; start += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
        }
        return `data:font/woff2;base64,${btoa(binary)}`;
      })
      .catch((error: unknown) => {
        embeddedKoreanFont = null;
        throw error;
      });
  }
  return embeddedKoreanFont;
}

async function withHwpPreviewFont(svg: string): Promise<string> {
  const root = svg.match(/<(?<prefix>[\w-]+:)?svg\b[^>]*>/i);
  if (!root?.groups) return svg;
  const prefix = root.groups.prefix ?? "";
  const fontDataUri = await koreanFontDataUri();
  const style = `<${prefix}style>
    @font-face { font-family: "NH Preview Noto"; src: url("${fontDataUri}") format("woff2"); }
    svg text, svg tspan { font-family: "NH Preview Noto", sans-serif !important; }
  </${prefix}style>`;
  return svg.replace(root[0], `${root[0]}${style}`);
}

export function FileActions({ accessToken, file, autoPreview = false, focusTarget }: { accessToken: string; file: AdvertisementFile; autoPreview?: boolean; focusTarget?: PreviewFocus }) {
  const [preview, setPreview] = useState<PreviewAsset | null>(null);
  const [pending, setPending] = useState<"preview" | "download" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const previewViewportRef = useRef<HTMLDivElement>(null);
  const previewSupported = supportsPreview(file);
  const isPdf = file.fileName.toLowerCase().endsWith(".pdf");
  const isHwp = /\.(hwp|hwpx)$/i.test(file.fileName);

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  const loadPreview = useCallback(async (pageNo = 1) => {
    setPending("preview");
    setError(null);
    try {
      const asset = await api.getFilePreviewAsset(accessToken, file.fileId, pageNo);
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
      const isHwpSvg = isHwp && asset.blob.type === "image/svg+xml";
      const previewBlob = isHwpSvg
        ? new Blob([await withHwpPreviewFont(await asset.blob.text())], { type: "image/svg+xml" })
        : asset.blob;
      const objectUrl = URL.createObjectURL(previewBlob);
      previewUrlRef.current = objectUrl;
      setPreview({ url: objectUrl, pageNo: asset.descriptor.pageNo, totalPages: asset.descriptor.totalPages });
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 403 ? "파일 미리보기 권한이 없습니다." : userMessage(cause));
    } finally {
      setPending(null);
    }
  }, [accessToken, file, isHwp]);

  useEffect(() => {
    if (autoPreview && previewSupported && preview === null && pending === null && error === null) {
      void loadPreview();
    }
  }, [autoPreview, error, loadPreview, pending, preview, previewSupported]);

  const focusPreview = useCallback(() => {
    if (!focusTarget || !previewViewportRef.current) return;
    const viewport = previewViewportRef.current;
    const image = viewport.querySelector("img");
    if (!image) return;
    viewport.scrollTo({ top: Math.max(0, image.scrollHeight * focusTarget.normalizedY - viewport.clientHeight * 0.35), behavior: "smooth" });
    viewport.focus({ preventScroll: true });
  }, [focusTarget]);

  useEffect(() => {
    if (!preview || !focusTarget) return;
    const frame = requestAnimationFrame(focusPreview);
    return () => cancelAnimationFrame(frame);
  }, [focusPreview, focusTarget, preview]);

  async function download() {
    setPending("download");
    setError(null);
    try {
      const blob = await api.downloadFile(accessToken, file.fileId);
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = file.fileName;
      link.click();
      URL.revokeObjectURL(objectUrl);
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 403 ? "파일 다운로드 권한이 없습니다." : userMessage(cause));
    } finally {
      setPending(null);
    }
  }

  return (
    <article className="file-actions">
      <header className="file-actions-header"><div><strong>{file.fileName}</strong><span>{fileTypeLabel(file.fileType)} · {formatFileSize(file.fileSize)}</span></div><div className="file-actions-controls">
        <button type="button" className="button-secondary" disabled={pending !== null || !previewSupported} onClick={() => void loadPreview()}>{pending === "preview" ? "미리보기를 준비하는 중..." : "미리보기"}</button>
        <button type="button" className="button-secondary" disabled={pending !== null} onClick={() => void download()}>{pending === "download" ? "다운로드 중..." : "다운로드"}</button>
      </div></header>
      {error ? <p role="alert" className="field-error">{error}</p> : null}
      {!previewSupported ? <p className="state-message">이 파일 형식은 브라우저 미리보기를 지원하지 않습니다. 원본을 다운로드해 확인해 주세요.</p> : null}
      {preview ? <div className="file-preview-panel">
        <div className="file-preview-toolbar"><span>{isHwp ? "한글 문서 변환 미리보기" : "원본 미리보기"}</span>{preview.totalPages > 1 ? <div className="preview-pagination"><button type="button" className="button-secondary" disabled={pending !== null || preview.pageNo <= 1} onClick={() => void loadPreview(preview.pageNo - 1)}>이전 페이지</button><strong>{preview.pageNo} / {preview.totalPages}</strong><button type="button" className="button-secondary" disabled={pending !== null || preview.pageNo >= preview.totalPages} onClick={() => void loadPreview(preview.pageNo + 1)}>다음 페이지</button></div> : null}</div>
        <div ref={previewViewportRef} className="file-preview-viewport" tabIndex={-1} aria-label="원본 미리보기 영역">
          {isPdf ? <object className="file-preview" data={preview.url} type="application/pdf" aria-label={`${file.fileName} 미리보기`} /> : <img className="file-preview" src={preview.url} alt={`${file.fileName} 미리보기`} onLoad={focusPreview} />}
        </div>
      </div> : null}
    </article>
  );
}
