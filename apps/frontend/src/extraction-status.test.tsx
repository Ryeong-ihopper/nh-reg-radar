import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExtractionStatusPanel, type ExtractionStatus } from "./components/ExtractionStatusPanel";

describe("file and page extraction observations", () => {
  it("shows coordinate-less uncertainty without a confidence percentage", () => {
    const value: ExtractionStatus = {version:"operational-extraction-status-v1", status:"CHECK_REQUIRED", accuracy_verified:false,
      files:[{asset_id:"A",file_name:"synthetic.png",status:"CHECK_REQUIRED",issues:["PARTIAL_EXTRACTION"],
        pages:[{page_no:3,evidence_page_no:7,status:"CHECK_REQUIRED",issues:["UNCERTAIN_LOCAL_READING","SOURCE_GEOMETRY_MISSING"]}]}]};
    const {container} = render(<ExtractionStatusPanel value={value} />);
    expect(screen.getByText(/synthetic.png/)).toBeVisible();
    expect(screen.getByText(/3페이지/)).toBeVisible();
    expect(screen.getByText(/판독 불확실 · 원본 확인 필요/)).toBeVisible();
    expect(screen.getByText(/전체 판독 미완료/)).toBeVisible();
    expect(container.textContent).not.toMatch(/\d+%|추출 성공|전체 적정/);
  });
  it("does not turn missing historical records into success", () => {
    render(<ExtractionStatusPanel />);
    expect(screen.getByText("추출 상태 기록 없음")).toBeVisible();
  });
  it("keeps successful extraction distinct from verified correctness", () => {
    render(<ExtractionStatusPanel value={{version:"operational-extraction-status-v1",status:"EXTRACTED",accuracy_verified:false,
      files:[{asset_id:"A",file_name:"a.png",status:"EXTRACTED",issues:[],pages:[{page_no:1,evidence_page_no:1,status:"EXTRACTED",issues:[]}]}]}} />);
    expect(screen.getByText(/정확성을 보장하지 않습니다/)).toBeVisible();
    expect(screen.getByText("파일·페이지별 추출 상태").closest("details")).not.toHaveAttribute("open");
  });
});
