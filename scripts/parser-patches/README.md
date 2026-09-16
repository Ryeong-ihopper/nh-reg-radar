# 사용자 선택 템플릿을 받는 파서 전달본

이 폴더의 `user-template-labeling.patch`는 별도 `nh-ad-parser` 저장소에 적용한다.
심의 앱 변경만 받아서는 파서의 새 CLI 인자가 생기지 않는다. 패치는 코드와 합성
검사만 포함하며, 고객 원문·모델 응답·개인키·접속 설정은 포함하지 않는다.

## 적용

심의 앱 저장소 루트에서 PowerShell로 실행한다. 파서 폴더는 실제 경로로 바꾼다.

```powershell
$parserRoot = 'C:/work/nh-ad-parser'
$patchPath = (Resolve-Path 'scripts/parser-patches/user-template-labeling.patch').Path
git -C $parserRoot status --short
git -C $parserRoot apply --reverse --check $patchPath 2>$null
if ($LASTEXITCODE -eq 0) {
  Write-Host '이미 적용된 전달본입니다.'
} else {
  git -C $parserRoot apply --check $patchPath
  if ($LASTEXITCODE -ne 0) { throw '파서 버전 또는 로컬 변경이 다릅니다. 변경을 지우지 말고 담당자에게 병합을 요청하세요.' }
  git -C $parserRoot apply $patchPath
  if ($LASTEXITCODE -ne 0) { throw '패치 적용 실패' }
}
```

파서 가상환경을 활성화한 뒤 `python tools/parse.py --help`에서 `--template-id`를
확인한다. 개발 환경에 pytest가 있으면 `python -m pytest tests/test_user_template.py`
로 사용자 입력과 하위 라벨 줄 대응을 검증한다.

앱에서 선택한 상세 상품군은 연결부가 자동으로 전달한다. 수동 파싱 예시는 다음과 같다.

```powershell
python tools/parse.py --input input/ad.png --out output --template-id '대출성상품-상품명 노출'
```

## 적용 내용과 한계

- 운영 P1/P3 생성은 사용자 템플릿을 필수로 받고, 문서/템플릿 자동 분류를 생략한다.
- OCR·보조 판독·좌표 수집은 유지하고, 선택 템플릿의 하위 항목을 P1 줄에 라벨링한다.
- 모델에 줄별 좌표를 전달하며 `line_ids`로 해당 줄만 선택한다. 떨어진 두 줄 사이의 다른 항목을 포함하지 않는다. 공개 P1/P3의 연속 span 형식은 유지한다.
- P1 내보내기에서도 잘못된 범위·참조를 임의 보정하지 않고 원문/유효 라벨을 보존하며 사람 확인 표시를 남긴다.
- 줄별 OCR 신뢰도와 전체 템플릿 기재요령을 전달하고, 저신뢰/디코딩 손상 줄의 라벨을 제외한다. 실제 선택된 P3 판독은 원문을 바꾸지 않는 문맥 보조로만 사용한다.
- 한 줄에 세로줄/세미콜론으로 구분된 복수 명시 표제가 있으면 해당 라벨을 모두 보존한다. 모델이 찾은 두 번째 필드의 라벨을 첫 표제 때문에 삭제하지 않는다.
- 항목명으로 시작하는 일반 문장·메뉴를 명시 표제로 확정하지 않는다. 정상 표제·단위·값 구분과 식별 숫자가 이어지는 심의필 형식은 보존한다.
- 기존 독립 `resolve_template` API는 과거 진단/다른 소비자를 위해 남아 있지만 운영 CLI는 호출하지 않는다.
- 이 변경으로 라벨의 의미 정확도가 보장되지는 않는다. 읽기/라벨 불확실성과 시인성은 사람 검토로 남긴다.
- 패치 기준 커밋과 SHA-256은 `manifest.json`에서 확인한다. 기존 `pyproject.toml`/잠금파일 변경은 포함하지 않는다.
