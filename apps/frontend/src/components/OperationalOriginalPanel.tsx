import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { getOperationalHwpHtml, getOperationalParserPreview, operationalRequest, type ParserLayout } from "../api/operational";
import { hwpHtmlPreview } from "./hwpHtmlPreview";
import { missingSourceLabel, resultChunkBoxes, resultEvidenceBoxes, resultHighlightBoxes, type ResultRow } from "./operationalResultModel";
import { ErrorState, LoadingState } from "./RequestState";

export function OperationalOriginalPanel({ reviewId, token, row, locateRequest = 0 }: {reviewId: string; token: string; row?: ResultRow; locateRequest?: number}) {
  const [pageNo, setPageNo] = useState(1);
  const [previewUrl, setPreviewUrl] = useState("");
  const [hwpView, setHwpView] = useState<"HTML" | "IMAGE">("IMAGE");
  const [zoom, setZoom] = useState(0);
  const [naturalWidth, setNaturalWidth] = useState(0);
  const [followEvidence, setFollowEvidence] = useState(true);
  const [showSearchAreas, setShowSearchAreas] = useState(false);
  const [locationNotice, setLocationNotice] = useState("");
  const canvas = useRef<HTMLDivElement>(null);
  const handledLocateRequest = useRef(0);
  const pendingLocateFocus = useRef(false);
  const status = useQuery({queryKey: ["review-progress",reviewId],queryFn:()=>api.getReviewStatus(token,reviewId)});
  const adId=status.data?.advertisementId ?? "";
  const advertisement=useQuery({queryKey:["advertisement",adId],queryFn:()=>api.getAdvertisement(token,adId),enabled:Boolean(adId)});
  const layout=useQuery({queryKey:["operational-parser-layout",reviewId],queryFn:()=>operationalRequest<ParserLayout>(token,`reviews/${reviewId}/parser-layout`),retry:false});
  const originals=advertisement.data?.files.filter(f=>f.fileType==="ADVERTISEMENT") ?? [];
  const layoutPage=layout.data?.pages.find(p=>p.page_no===pageNo);
  const original=originals.find(f=>f.fileId===layoutPage?.asset_id) ?? originals[0];
  const sourcePageNo=layoutPage?.source_page_no ?? pageNo;
  const isHwp=/\.hwpx?$/i.test(original?.fileName ?? "");
  const showHwpHtml=isHwp && hwpView==="HTML";
  const hwpHtml=useQuery({queryKey:["result-hwp-html",reviewId,original?.fileId],queryFn:()=>getOperationalHwpHtml(token,reviewId,original!.fileId),enabled:Boolean(original)&&showHwpHtml,retry:false});
  const preview=useQuery({queryKey:["result-preview",reviewId,original?.fileId,sourcePageNo,layoutPage?.preview_path],queryFn:()=>layoutPage?.preview_path ? getOperationalParserPreview(token,layoutPage.preview_path) : api.getFilePreviewAsset(token,original!.fileId,sourcePageNo),enabled:Boolean(original)&&!layout.isPending&&!showHwpHtml});
  const currentBoxes=useMemo(()=>row ? resultHighlightBoxes(resultEvidenceBoxes(row,layout.data),layout.data):[],[row,layout.data]);
  const currentChunks=useMemo(()=>row ? resultChunkBoxes(row):[],[row]);
  const selectedId=row?.row_id ?? row?.item_id;
  const htmlPreview=useMemo(()=>hwpHtml.data ? hwpHtmlPreview(hwpHtml.data,(row?.evidence ?? "").split(/\r?\n/).map(t=>t.trim()).filter(Boolean),zoom):null,[hwpHtml.data,row,zoom]);
  useEffect(()=>{
    if(!preview.data) return;
    const url=URL.createObjectURL(preview.data.blob);setPreviewUrl(url);
    return ()=>URL.revokeObjectURL(url);
  },[preview.data]);
  useEffect(()=>setLocationNotice(""),[selectedId]);
  useEffect(()=>{
    if(!row || layout.isPending) return;
    const explicit = locateRequest > handledLocateRequest.current;
    if(explicit) handledLocateRequest.current=locateRequest;
    const first=currentBoxes[0];
    if(!first) {
      pendingLocateFocus.current=false;
      if(explicit) setLocationNotice(missingSourceLabel(row).replace(/bbox/g,"위치"));
      return;
    }
    setLocationNotice("");
    if(!followEvidence && !explicit) return;
    if(explicit) pendingLocateFocus.current=true;
    if(showHwpHtml) setHwpView("IMAGE");
    setPageNo(first.pageNo);
  },[selectedId,currentBoxes,followEvidence,locateRequest,layout.isPending,showHwpHtml,row]);
  useEffect(()=>{
    const first=currentBoxes.find(box=>box.pageNo===pageNo);
    const element=canvas.current;
    if(!first||!element||(!followEvidence&&!pendingLocateFocus.current)||showHwpHtml) return;
    const frame=requestAnimationFrame(()=>{
      const image=element.querySelector("img");
      if(image?.clientHeight) {
        if(pendingLocateFocus.current) { element.focus({preventScroll:true}); pendingLocateFocus.current=false; }
        element.scrollTo({top:Math.max(0,image.clientHeight*first.bbox[1]/first.height-element.clientHeight*0.3),left:Math.max(0,image.clientWidth*first.bbox[0]/first.width-element.clientWidth*0.3),behavior:"instant"});
      }
    });
    return ()=>cancelAnimationFrame(frame);
  },[selectedId,pageNo,previewUrl,currentBoxes,followEvidence,locateRequest,zoom,showHwpHtml,naturalWidth]);
  return <aside className="single-advertisement"><div className="single-advertisement-toolbar"><strong title={original?.fileName}>광고 원본{original?.fileName ? ` · ${original.fileName}` : ""}</strong>
        <div className="original-navigation"><button aria-label="이전 원본 페이지" disabled={pageNo <= 1} onClick={() => setPageNo((page) => page - 1)}>이전</button>
          <label>페이지 <select aria-label="원본 페이지" value={pageNo} onChange={event => setPageNo(Number(event.target.value))}>{(layout.data?.pages ?? [{page_no:1}]).map(page => <option key={page.page_no} value={page.page_no}>{page.page_no} / {layout.data?.pages.length ?? 1}</option>)}</select></label>
          <button aria-label="다음 원본 페이지" disabled={pageNo >= (layout.data?.pages.length ?? 1)} onClick={() => setPageNo((page) => page + 1)}>다음</button></div></div>
        <div className="original-view-controls"><label>확대 <select aria-label="원본 확대" value={zoom} onChange={event => setZoom(Number(event.target.value))}><option value={0}>화면 폭 맞춤</option><option value={1}>100% · 원본 크기</option><option value={1.5}>150%</option><option value={2}>200%</option></select></label>
          {isHwp ? <label>표시 <select aria-label="HWP 원문 표시" value={hwpView} onChange={event => setHwpView(event.target.value as 'HTML' | 'IMAGE')}><option value="IMAGE">심의 화면 · 근거 위치</option><option value="HTML">본문 읽기 · HTML</option></select></label> : null}
          {previewUrl && !showHwpHtml ? <a href={previewUrl} target="_blank" rel="noreferrer">원본 새 탭</a> : null}
          <label className="evidence-follow"><input type="checkbox" checked={followEvidence} disabled={showHwpHtml} onChange={event => setFollowEvidence(event.target.checked)} />근거 자동이동{showHwpHtml ? ' · 이미지 보기' : ''}</label></div>
        {showHwpHtml && hwpHtml.isPending ? <LoadingState label="HWP HTML 본문을 준비하는 중입니다." /> : null}
        {showHwpHtml && hwpHtml.isError ? <ErrorState error={hwpHtml.error} onRetry={() => void hwpHtml.refetch()} /> : null}
        {!showHwpHtml && preview.isPending ? <LoadingState label="광고 원본을 준비하는 중입니다." /> : null}
        {!showHwpHtml && preview.isError ? <ErrorState error={preview.error} onRetry={() => void preview.refetch()} /> : null}
        {showHwpHtml ? <p className="panel-note">본문 전체를 읽는 보기입니다. 심의 근거의 페이지와 위치는 ‘심의 화면’에서 확인할 수 있습니다.{htmlPreview?.ambiguous ? ` 반복 문구 ${htmlPreview.ambiguous}개는 위치를 확정하지 않았습니다.` : ''}</p> : null}
        {layout.isError ? <p role="status" className="panel-note">근거 위치를 불러오지 못했습니다. 원본은 확인할 수 있습니다. <button onClick={() => void layout.refetch()}>다시 시도</button></p> : null}
        {locationNotice ? <p role="status" className="panel-note">{locationNotice}</p> : null}
<details className="original-reading-options"><summary>표시 옵션</summary><label className="inline-check"><input type="checkbox" checked={showSearchAreas} onChange={event => setShowSearchAreas(event.target.checked)} />검색에 제공된 영역 함께 표시</label><small>검색 영역은 판정의 직접 인용 위치와 구별됩니다.</small></details>
        <div className="single-advertisement-scroll" ref={canvas} tabIndex={0} aria-label="광고 원문 화면">
          {showHwpHtml && htmlPreview ? <iframe title="HWP HTML 원문" sandbox="" srcDoc={htmlPreview.html} className="hwp-html-preview" /> : null}
          {!showHwpHtml && previewUrl && !preview.isPending ? <div className="single-advertisement-canvas" style={{width:zoom && naturalWidth ? `${naturalWidth * zoom}px` : "100%"}}><img src={previewUrl} alt="심의 광고 원본" onLoad={event => setNaturalWidth(event.currentTarget.naturalWidth)} />
            {showSearchAreas && currentChunks.filter((box) => box.pageNo === pageNo).map((box) => <span data-testid="active-evidence-chunk" key={box.key} className="review-evidence-chunk" title="모델에 제공된 검색 청크 범위" style={{ left: `${box.bbox[0] / box.width * 100}%`, top: `${box.bbox[1] / box.height * 100}%`, width: `${(box.bbox[2] - box.bbox[0]) / box.width * 100}%`, height: `${(box.bbox[3] - box.bbox[1]) / box.height * 100}%` }} />)}
            {currentBoxes.filter((box) => box.pageNo === pageNo).map((box) => <span data-testid="active-evidence-box" data-precision={box.precision} key={box.key} className="review-evidence-highlight" title={box.precision === "REGION" ? "판정 근거가 있는 파서 영역" : "판정 근거 위치"} style={{ left: `${box.bbox[0] / box.width * 100}%`, top: `${box.bbox[1] / box.height * 100}%`, width: `${(box.bbox[2] - box.bbox[0]) / box.width * 100}%`, height: `${(box.bbox[3] - box.bbox[1]) / box.height * 100}%` }} />)}
          </div> : null}
        </div>
      </aside>;
}
