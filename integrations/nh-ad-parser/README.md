# 파서 사용자 선택 템플릿 호환 패치

연구원은 파서 담당자의 push를 기다리지 않고 이 저장소의 패치를 로컬 파서에 적용할 수 있다. 심의 앱 설정의 `parser_root`가 가리키는 실제 파서 체크아웃을 지정한다.

```powershell
python scripts/apply_parser_template_support.py --parser-root "C:\path\to\nh-ad-parser"
```

적용 후 심의 앱을 다시 실행한다. `--check`를 추가하면 파일 변경 없이 적용 가능 여부만 확인한다. 충돌 시 파일을 수정하지 않고 중단하며, 이미 같은 패치가 적용됐으면 변경하지 않는다. 기존 작업을 reset하거나 덮어쓰지 않는다.

원본 기준은 `cg-wnsdud/nh-ad-parser`의 main 커밋 `f27b2638135b6337cac6297c2e0cd8e0c44b2e8b`다. 패치는 `--template-id` 수용, 카탈로그 유효성 검사, 사용자 선택 템플릿의 P1/P3 유지, 문서 자동 분류 생략과 오프라인 테스트만 포함한다. 일반 P1/P3 실행에는 템플릿 인자가 필수이며 `--parse-only`는 예외다. 로컬 의존성 변경·라벨/줄 매핑의 별도 수정은 포함하지 않는다.

파서 담당자에게 같은 패치를 원본 저장소 반영용으로 전달할 수도 있다. 원본에 지원이 반영되면 이 호환 패치와의 충돌 여부를 확인한 후 전환한다. `Already up to date`만으로 이 패치 적용 여부가 확인되지는 않는다.

파서 환경의 오프라인 검증:

```powershell
python -m pytest -s -q tests/test_cli_template_selection.py
```
