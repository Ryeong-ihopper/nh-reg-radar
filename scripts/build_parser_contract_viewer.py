"""Build a local, self-contained viewer for a pinned upstream parser contract."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path


FIELDS = [
    ('document.doc_id', '문서 식별자', '문자열', '같은 문서의 P1과 P3를 연결합니다.'),
    ('document.source_file', '원본 파일명', '문자열', '출처 확인에 사용하며 파일명으로 심의 의무를 만들지 않습니다.'),
    ('document.file_type', '파일 형식', '문자열', 'PDF·이미지·HWP/HWPX 입력 구분입니다.'),
    ('document.classification', '파서의 상품·광고 분류', '객체', '모델 관찰입니다. 사용자가 확정한 상품·매체를 대체하지 않습니다.'),
    ('document.template', '파서가 선택한 템플릿', '객체', '라벨링 관찰입니다. 실제 적용 범위는 사이트의 확정 입력입니다.'),
    ('review_units[]', '상품별 영역 묶음', '배열', 'product_id·template_id·region_ids·page_common_region_ids를 전달합니다.'),
    ('pages[].page_no', '페이지 번호', '정수', '렌더한 화면의 페이지입니다.'),
    ('pages[].canvas', '화면 크기', '[너비, 높이]', 'bbox와 같은 픽셀 좌표계입니다.'),
    ('pages[].regions[].region_id', '영역 ID', '문자열', 'p1_r001 형식입니다. P1 재조회와 영역 하이라이트에 사용합니다.'),
    ('pages[].regions[].product_id', '영역의 상품 소유권', '문자열 또는 null', '여러 상품이 있는 광고에서 근거가 어느 상품에 속하는지 나타냅니다.'),
    ('pages[].regions[].bbox', '영역 위치', '[x1,y1,x2,y2] 또는 null', '실제 파서 렌더 화면의 픽셀 좌표입니다. 한 문장의 정확한 줄 좌표는 P1에서 따로 확인합니다.'),
    ('pages[].regions[].selected_text', '최종 선택 문구', '문자열', 'OCR·디지털 추출·HWP 구조·VLM 대조 후 선택된 문구입니다. 원문 줄과 다르면 영역 수준 근거로 유지합니다.'),
    ('pages[].regions[].labels', '구분값 라벨', '문자열 배열', '회사명·상품명·가입대상 등 영역의 복수 분류 힌트입니다. 값의 존재나 적정성을 증명하지 않습니다.'),
    ('pages[].regions[].kind', '본문/표 구분', 'text 또는 table', '표의 실제 셀은 P1에 남습니다. P3는 최종 평문을 전달합니다.'),
    ('pages[].regions[].needs_review', '추출 품질 확인 필요', '불리언', '광고 위반 여부가 아닙니다. 자세한 사유는 P1의 review_reasons를 확인합니다.'),
    ('pages[].regions[].text_source', '최종 문구 출처', 'hwp/digital/ocr/vlm', 'VLM이 선택·작성한 문구와 원문 추출을 구분합니다.'),
    ('review_result_contract', '후속 심의 출력 안내', '객체', '위반·판정불가·충족과 region_ids 계약입니다. 파서가 광고를 판정한 결과는 아닙니다.'),
    ('P1 pages[].regions[].lines[]', '원문 줄과 줄 좌표', '배열', 'line_ref·text·bbox·source·confidence·style 등을 보존합니다. 점수는 검증된 정확도 확률이 아닙니다.'),
    ('P1 pages[].regions[].review_reasons', '품질 경고 사유', '배열', '판독·라벨·정렬 등에 관한 구체적인 확인 사유입니다.'),
    ('P1 pages[].regions[].text_candidates', '판독 후보와 원문', '객체, 있는 경우', '최종 선택문과 원래 조립 문장을 비교할 수 있습니다.'),
    ('P1 pages[].regions[].table.cells[]', '확인된 원본/HTML 표 셀', '배열, 있는 경우', '셀의 존재가 문장 간 의미 관계나 계산 가능성을 보장하지 않습니다.'),
    ('P1 pages[].table_checks', '표 검증과 거부 기록', '배열, 있는 경우', '표 후보의 검증·병합·거부를 추적합니다.'),
    ('P1 pages[].unassigned_lines[]', '미배정 원문 줄', '배열', 'P3에 빠져 있어도 삭제하지 않고 어댑터에서 검색 근거로 보존합니다.'),
    ('P1 pages[].recovery_candidates[]', '복구 후보', '배열, 있는 경우', '확정 문구나 bbox로 자동 승격하지 않습니다.'),
    ('P1 pages[].origin', '입력·렌더 출처', '객체', 'HWP 구조와 실제 표시 화면의 관계를 확인하는 감사 정보입니다.'),
]


def build(parser_root: Path, output: Path, *, sample_p1: Path | None = None, sample_p3: Path | None = None):
    revision = subprocess.run(['git', '-c', f'safe.directory={parser_root.resolve().as_posix()}',
        '-C', str(parser_root), 'rev-parse', 'HEAD'], check=True, capture_output=True,
        text=True).stdout.strip()
    module_path = parser_root/'nh_parser_fin/parse/export.py'
    spec = importlib.util.spec_from_file_location('parser_export_for_viewer', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    example = {'doc_id': 'SCHEMA-DEMO', 'source_file': 'schema-example.png', 'file_type': 'png',
        'classification': {}, 'template': {}, 'review_units': [],
        'pages': [{'page_no': 1, 'canvas': [1000, 1400], 'regions': [{
            'region_id': 'p1_r001', 'product_id': 'product_1', 'bbox': [40, 80, 700, 180],
            'text': '회사명: 예시 금융회사\n상품명: 예시 상품',
            'semantic_labels': ['회사명', '상품명'], 'kind': 'text', 'needs_review': False,
            'text_source': 'ocr_lines', 'review_reasons': [],
            'lines': [{'line_ref': 'p1/r001/L001', 'text': '회사명: 예시 금융회사',
                       'bbox': [40, 80, 700, 125], 'source': 'ocr', 'confidence': 0.97},
                      {'line_ref': 'p1/r001/L002', 'text': '상품명: 예시 상품',
                       'bbox': [40, 130, 700, 180], 'source': 'ocr', 'confidence': 0.96}],
        }], 'unassigned_lines': []}]}
    p1 = module.build_p1(example)
    p3 = module.build_p3(p1)
    payload = {'p1_version': module.P1_VERSION, 'p3_version': module.P3_VERSION,
        'commit': revision,
        'export_sha256': hashlib.sha256(module_path.read_bytes()).hexdigest(),
        'fields': FIELDS, 'example_p1': p1, 'example_p3': p3,
        'sample_p1': json.loads(sample_p1.read_text(encoding='utf-8')) if sample_p1 else None,
        'sample_p3': json.loads(sample_p3.read_text(encoding='utf-8')) if sample_p3 else None}
    output.mkdir(parents=True, exist_ok=True)
    (output/'contract-view.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    document = r'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>최신 파서 입력 계약</title>
<style>body{margin:0;background:#f2f6f3;color:#193229;font:16px/1.7 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:28px}h1,h2,a{color:#145a41}.panel{background:white;padding:22px;border:1px solid #cbded3;border-radius:12px;margin:18px 0}.badge{display:inline-block;background:#dceee3;padding:5px 12px;border-radius:7px;margin:3px}input,button,select{font:inherit;padding:9px 12px;border:1px solid #adc8b9;border-radius:7px}button{background:#145a41;color:white;cursor:pointer}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #e0e9e3;padding:12px;vertical-align:top}code,pre{font:14px/1.6 Consolas,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7f5;padding:16px;border-radius:8px}tr.hidden{display:none}.note{background:#edf5ef;padding:14px;border-left:4px solid #237754}summary{cursor:pointer;color:#145a41;font-weight:700}.diagram{display:flex;gap:12px;flex-wrap:wrap}.diagram span{padding:12px;border:1px solid #b5cebe;border-radius:8px}small{color:#516b5d}</style>
<main><h1>우리가 받는 최신 파서 스키마</h1><p id="versions"></p><p><a href="https://github.com/cg-wnsdud/nh-parser-fin/tree/fdfc09f8110107a66af1f5db964b15cc8fe6a559" target="_blank" rel="noreferrer">확인한 최신 저장소 코드</a> · 2026-09-28 기준</p>
<section class="panel"><h2>P1과 P3는 계속 사용합니다</h2><div class="diagram"><span>P1: 원문·후보·좌표·경고 원장</span><span>↔ 같은 region_id</span><span>P3: 최종 문구·라벨·표·좌표</span><span>→ 어댑터 → 검색·Rule/LLM</span></div><p>파서의 최종 외부 계약은 P1 v4 / P3 v9입니다. 우리 검색·판정 내부 계약은 어댑터로 유지합니다. 내부 버전명이 다르다고 옛 파서가 실행되는 것은 아닙니다.</p><p class="note">라벨은 영역 분류 힌트입니다. P3에는 각 값의 검증된 정확도 점수가 없습니다. needs_review는 파싱 품질 경고이며 광고의 적정·부적정 판정이 아닙니다.</p></section>
<section class="panel"><h2>이전 운영본에서 달라진 부분</h2><p>402ab4b → fdfc09f · P1 v3 → v4 · P3 v6 → v9</p><ul><li>P3에 bbox·text_source를 직접 전달하고 영역 ID를 pN_rNNN으로 통일합니다.</li><li>HWP/HWPX 구조 추출·HTML/로컬 PDF 렌더를 run.py 경로에 연결했습니다.</li><li>표는 kind=table과 최종 평문을 P3로, 원본/HTML 셀과 검증 사유를 P1로 나눕니다.</li><li>옛 --with-vlm 인자는 없어졌습니다. VLM을 항상 실행하며 --compact-output으로 최종 산출물을 받습니다.</li><li>새 HWP 하이라이트에는 파서가 실제 사용한 화면을 표시해야 합니다. 한컴 원본 조판과는 다를 수 있습니다.</li></ul></section>
<section class="panel"><h2>필드별 설명</h2><input id="filter" placeholder="회사명, 좌표, confidence, 표 등 검색" aria-label="필드 찾기"><table><thead><tr><th>필드</th><th>뜻·형식</th><th>사용할 때의 기준</th></tr></thead><tbody id="fields"></tbody></table></section>
<section class="panel"><h2>실제 JSON 모양</h2><p>아래 기본 예시는 최신 export.py로 만든 <b>구조 설명용 합성 데이터</b>이며 OCR 정확도 검증이나 실제 광고 결과가 아닙니다. 실제 실행 데이터가 추가되면 선택 목록에서 구분됩니다.</p><select id="which" aria-label="JSON 선택"><option value="example_p3">P3 최종 입력 — 합성 예시</option><option value="example_p1">P1 원문 근거 — 합성 예시</option></select><pre id="json"></pre></section>
<section class="panel"><h2>규칙·구조화에 연결할 값</h2><p>등록한 상품·매체·운용상품으로 필수 검사를 선택합니다. selected_text와 labels로 근거 후보를 찾고, 실제 원문·역할·추출 상태를 확인합니다. 숫자·날짜·단위는 Rule, 문장의 의미는 LLM이 검사하며 필요한 경우 함께 사용합니다. bbox는 표시 위치이고 충족의 증거는 아닙니다.</p><p>한 줄에 여러 유의사항이 있는지, 글자 크기가 적절한지 등의 시각 검사는 문장과 bbox 존재만으로 자동 확정하지 않습니다.</p></section></main>
<script>const data=__DATA__;document.querySelector('#versions').innerHTML=`<span class="badge">${data.p1_version}</span><span class="badge">${data.p3_version}</span><span class="badge">${data.commit.slice(0,7)}</span>`;const body=document.querySelector('#fields');data.fields.forEach(f=>{const row=document.createElement('tr');f.forEach((v,i)=>{});const a=document.createElement('td');const c=document.createElement('code');c.textContent=f[0];a.append(c);const b=document.createElement('td');b.textContent=f[1]+' · '+f[2];const d=document.createElement('td');d.textContent=f[3];row.append(a,b,d);body.append(row)});document.querySelector('#filter').addEventListener('input',e=>{const q=e.target.value.toLowerCase();Array.from(body.children).forEach(r=>r.classList.toggle('hidden',!r.textContent.toLowerCase().includes(q)))});const which=document.querySelector('#which');['sample_p3','sample_p1'].forEach(k=>{if(data[k]){const o=document.createElement('option');o.value=k;o.textContent=(k==='sample_p3'?'P3':'P1')+' — 최신 파서 실제 실행';which.append(o)}});function show(){document.querySelector('#json').textContent=JSON.stringify(data[which.value],null,2)}which.addEventListener('change',show);show();</script></html>'''
    document = document.replace('fdfc09f8110107a66af1f5db964b15cc8fe6a559', revision)
    document = document.replace('402ab4b → fdfc09f', f'402ab4b → {revision[:7]}')
    document = document.replace('아래 기본 예시는 최신 export.py로 만든 <b>구조 설명용 합성 데이터</b>이며 OCR 정확도 검증이나 실제 광고 결과가 아닙니다. 실제 실행 데이터가 추가되면 선택 목록에서 구분됩니다.', '목록에서 <b>실제 실행 P1/P3</b>와 구조 설명용 합성 예시를 구분합니다. 실제 데이터가 있으면 P3부터 표시합니다. 실행 결과는 금융 판정 정확도 평가를 뜻하지 않습니다.')
    document = document.replace("which.addEventListener('change',show);show();", "which.addEventListener('change',show);if(data.sample_p3)which.value='sample_p3';show();")
    encoded = json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')
    (output/'index.html').write_text(document.replace('__DATA__',encoded),encoding='utf-8')
    return {'p1': module.P1_VERSION,'p3':module.P3_VERSION,'fields':len(FIELDS),'output':str(output/'index.html')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parser-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sample-p1',type=Path)
    parser.add_argument('--sample-p3',type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.parser_root,args.output,sample_p1=args.sample_p1,sample_p3=args.sample_p3),ensure_ascii=False))
