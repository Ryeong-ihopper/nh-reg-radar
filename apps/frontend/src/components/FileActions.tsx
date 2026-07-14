import { useEffect, useRef, useState } from "react";

import { api, ApiError, type AdvertisementFile, userMessage } from "../api/client";

export function FileActions({ accessToken, file }: { accessToken: string; file: AdvertisementFile }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [pending, setPending] = useState<"preview" | "download" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  async function preview() {
    setPending("preview");
    setError(null);
    try {
      const blob = await api.getFilePreviewContent(accessToken, file.fileId);
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
      const objectUrl = URL.createObjectURL(blob);
      previewUrlRef.current = objectUrl;
      setPreviewUrl(objectUrl);
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 403 ? "파일 미리보기 권한이 없습니다." : userMessage(cause));
    } finally {
      setPending(null);
    }
  }

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
    <div className="file-actions">
      <span>{file.fileName} ({file.fileType}, {file.fileSize.toLocaleString("ko-KR")} bytes)</span>
      <button type="button" className="button-secondary" disabled={pending !== null} onClick={() => void preview()}>{pending === "preview" ? "미리보기 중..." : "미리보기"}</button>
      <button type="button" className="button-secondary" disabled={pending !== null} onClick={() => void download()}>{pending === "download" ? "다운로드 중..." : "다운로드"}</button>
      {error ? <p role="alert" className="field-error">{error}</p> : null}
      {previewUrl ? <img className="file-preview" src={previewUrl} alt={`${file.fileName} 미리보기`} /> : null}
    </div>
  );
}
