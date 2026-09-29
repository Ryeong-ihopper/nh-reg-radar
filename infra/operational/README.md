# 브라우저 접속용 운영 검토 서버

현재 운영 검토 실행기를 서버에서 실행하는 중간 배포 구성이다. 웹/API, 작업 실행,
애플리케이션 Python 3.11, 파서 전용 Python 3.13, nh-parser-fin, Java 25,
LibreOffice와 H2Orestart, 상태·파일 저장소를
서버에 둔다. 사용자는 접속 가능한 HTTPS 주소와 브라우저만 사용한다.
Spark arm64와 H200 amd64에 같은 Dockerfile/Compose를 사용하며 모델·OCR·ES 주소만
실행 설정으로 바꾼다. H200에서의 실기 검증은 별도 수행해야 한다.

2026-09-22 현행 배포는 spark-1118의 `https://172.23.80.104:5180`이다. 운영 컨테이너는
`nh-operational-1118-web-1`이며 ES9201/BGE8103/Gemma8102/PaddleX8081을 같은 서버에서
직접 사용한다. 로컬 PC나 구 서버 터널 없이 동작한다. 상태 사본 해시와 새 등록부터 bbox
표시까지의 실기 결과는 `docs/handoff-current.md` 최상단을 따른다.

## 패키징과 설치

애플리케이션 파일 포함 범위는 `runtime-files.json`의 명시 목록을 정본으로 사용한다.
`scripts/operational_runtime.py`가 파일 존재·경로·심볼릭 링크·저장소 import 및
문자열로 지정된 subprocess/해시 파일 의존성을 검사하고 파일별 SHA를 남긴다.
Docker의 `application-source` 단계에서 선별하며 최종 이미지의 `/app`에는 이 산출물과
프런트엔드 `dist`만 복사한다. 프런트엔드 빌드 입력과 private 파서/처리기 소스는
기존 경계를 유지한다. 실행 목록은 Python106·config/schema19의125파일이다.
requirements 두 파일은 의존성 설치용 빌드 입력으로만 사용하고 최종 이미지에서 제거한다.
서버별 예시 설정·제안 schema는 저장소에 보존하되 실행 목록에 포함하지 않는다.

생성·평가·테스트·DB 마이그레이션·CI 도구는 저장소에 보존하고 독립 작업에서 사용한다.
공유 요청 생성에 쓰이는 `build_silver_requests.py`와 운영 복구 도구는 이미지에 남긴다.
정적 목록 검사는 동적 경로 실행이나 파싱 정확도를 보장하지 않는다. 목록 변경 시
`tests/test_operational_runtime.py`의 격리 import/CLI 검사와 포장 SHA 검사도 실행한다.
새 후보의 실제 이미지 검증과 운영 교체는 구분하며 마지막 적용 상태는 인수인계 상단을 따른다.
화면 배포에서는 현재 HTML·JS·CSS가 참조하는 파일만 남긴다. 과거 해시 이름의 화면
파일이나 대체된 설계 코드를 새 이미지에 누적 복사하지 않는다. 상태·동결 결과·
원문·Accepted ADR·이행에 필요한 호환 코드는 별도 보존한다.

1. `scripts/package_operational_server.py --parser-root ... --document-processor-root ... --output ...`
   로 private 의존성을 포함한 소스 묶음을 생성한다. Git/환경파일/실행물은 제외하고
   파일별 SHA를 포함한다. 묶음은 고객 원문과 분리해 비공개로 전달한다.
2. 서버의 새 디렉터리에 풀고 manifest 해시를 검증한다.
   `docker build -f infra/operational/Dockerfile -t <불변-태그> .`로 이미지를 만든다.
   nh-parser-fin은 전용 Python 3.13(`/opt/python313`)에서 실행하고 웹/RAG는 Python 3.11을
   유지한다. HWP 읽기는 private Java 변환기, 미리보기는 LibreOffice/H2Orestart가 담당한다.
   private document-processor의 상위 Python 버전 선언을 수정하지 않는다.
   document-processor는 파서 실행 시 `PYTHONPATH`로만 제공하며 PDF·이미지 경로와 분리한다.
   정본 계획·migration·disposition을 포함한 `rag-pipeline/config`도 반드시 번들/이미지에 넣는다.
   현재 파서의 HWP 경로는 내장 이미지를 사용하므로 이미지 없는 HWP는 심의 입력 생성에
   실패할 수 있다. LibreOffice 원본 미리보기 지원과 파서의 입력 지원은 별도로 검증한다.
3. `server.example.json`, `execution.example.json`을 비공개 서버 설정으로 복사한다.
   별도 난수 비밀번호/JWT 키 파일, 해당 서비스 주소용 TLS 인증서와 키를 준비한다.
   설정과 원본은 Git/공개 이미지에 넣지 않는다. 실제 서비스에는 신뢰할 수 있는
   조직 인증서를 사용한다. 임시 자체 서명 인증서는 시험 접속 시 신뢰 확인이 필요하다.
4. `NH_OPERATIONAL_IMAGE`, `NH_SERVER_STATE`, `NH_SERVER_WORK`, `NH_SERVER_CONFIG`,
   `NH_SERVER_RULES`를 서버 절대 경로로 지정한다. 볼륨은 컨테이너 UID/GID 10001이
   접근하도록 준비하고 비밀 파일은 제한된 권한을 유지한다. Windows 개인 경로와
   SSH 터널을 실행 설정에 넣지 않는다.
5. `docker compose --env-file <비공개-env> -f infra/operational/compose.yml up -d --no-build web`
   으로 이 프로젝트의 웹 서비스만 기동한다. 기존 GPU/OCR/ES 컨테이너는 관리하지 않는다.
   Linux host 네트워크를 사용해 기존 loopback 모델 서비스에 접속한다.

## 상태 이전과 검증

### 선택적 로컬 접속

`scripts/serve_loopback_proxy.py --upstream <HTTPS-origin> --ca-file <공개인증서-경로> --port 5182`
로 같은 서버를 로컬에서 열 수 있다. 수신은127.0.0.1로 고정하고 upstream 인증서를 검증한다.
개인키나 OS 신뢰 저장소 변경은 필요하지 않다. 원격 서버의 계정으로 최초 로그인하며 로컬
세션 요청은 인증된 refresh 쿠키 갱신으로 전달한다. 데이터나 심의 실행기를 로컬로 복제하지 않는다.
서버와의 TLS 연결을 유지하고 loopback 구간에서만 HTTP 쿠키를 사용한다.

### 보존 절차

웹/RAG 진행 작업이 0일 때 상태 디렉터리를 사본으로 동결한다. 기존 결과·원본·감사
파일의 바이트를 보존하고 새 사본의 결과 파일 연결 경로만 `/state/execution`으로
변환한다. 원래 상태 파일도 별도 보존한다. 복사 후 모든 파일 해시, 광고/검토 수,
인증되지 않은 접근 차단, Secure 쿠키, 브라우저 결과·원본·JSON 내보내기를 대조한다.
새 컨테이너에서 실제 HWP 원문 읽기와 미리보기를 각각 검증한다.

서버 모드의 `/open/{token}` 자동 로그인은 비활성이다. 서버의 viewer-session 파일은
접속 주소만 기록하고 비밀번호를 기록하지 않는다. 단일 운영 실행기의 파일 기반
상태와 작업 큐를 보존하는 구성으로, 다중 웹 replica용 공유 DB/큐 전환 완료를 뜻하지 않는다.
영속 볼륨은 별도 백업하며 `down -v`를 사용하지 않는다. 되돌릴 때는 진행 작업이 0인지
확인하고 이 Compose의 웹 이미지만 이전 태그로 변경한다. 원래 로컬 상태와 기존
Spark 서비스는 삭제하거나 재시작하지 않는다.

### 로그인 입력 없는 로컬 시연

사용자가 자동 접속을 선택한 경우 위 명령에 `--login-file <비공개-계정-JSON>`을 추가한다.
JSON의 email/password를 사용하며 파일은 Git에 추가하지 않는다. 세션이 없을 때만 서버에
로그인하고 이미 있는 쿠키는 갱신한다. 새 브라우저에서도 바로 광고 목록을 연다.
localhost 밖에서 수신하도록 옵션을 추가하지 않는다.
