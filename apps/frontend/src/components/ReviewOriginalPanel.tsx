import type { AdvertisementDetail } from "../api/client";
import { FileActions, type PreviewFocus } from "./FileActions";

export function ReviewOriginalPanel({
  accessToken,
  advertisement,
  focusTarget,
}: {
  accessToken: string;
  advertisement: AdvertisementDetail;
  focusTarget?: PreviewFocus;
}) {
  const allFiles = advertisement.files ?? [];
  const originals = allFiles.filter((file) => file.fileType === "ADVERTISEMENT");
  const files = originals.length > 0 ? originals : allFiles;

  return (
    <aside className="review-original-panel" aria-label="광고 원본 병행 검토">
      <header><h3>광고 원본</h3></header>
      {files.length === 0 ? <p className="state-message">표시할 광고 원본이 없습니다.</p> : files.map((file, index) => (
        <FileActions key={file.fileId} accessToken={accessToken} file={file} autoPreview focusTarget={index === 0 ? focusTarget : undefined} />
      ))}
    </aside>
  );
}
