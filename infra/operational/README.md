# 브라우저 접속용 운영 검토 서버

현재 운영 검토 실행기를 서버에서 실행하는 중간 배포 구성이다. 웹/API, 작업 실행,
애플리케이션 Python 3.11, 파서 전용 Python 3.13, nh-parser-fin, Java 25,
LibreOffice와 H2Orestart, 상태·파일 저장소를
서버에 둔다. 사용자는 접속 가능한 HTTPS 주소와 브라우저만 사용한다.
Spark arm64와 H200 amd64에 같은 Dockerfile/Compose를 사용하며 모델·OCR·ES 주소만
실행 설정으로 바꾼다. H200에서의 실기 검증은 별도 수행해야 한다.

## 패키징과 설치

1. `scripts/package_operational_server.py --parser-root ... --document-processor-root ... --output ...`
   로 private 의존성을 포함한 소스 묶음을 생성한다. Git/환경파일/실행물은 제외하고
   파일별 SHA를 포함한다. 묶음은 고객 원문과 분리해 비공개로 전달한다.
2. 서버의 새 디렉터리에 풀고 manifest 해시를 검증한다.
   `docker build -f infra/operational/Dockerfile -t <불변-태그> .`로 이미지를 만든다.
   nh-parser-fin은 전용 Python 3.13(`/opt/python313`)에서 실행하고 웹/RAG는 Python 3.11을
   유지한다. HWP 읽기는 private Java 변환기, 미리보기는 LibreOffice/H2Orestart가 담당한다.
   private document-processor의 상위 Python 버전 선언을 수정하지 않는다.
   document-processor는 파서 실행 시 `PYTHONPATH`로만 제공하며 PDF·이미지 경로와 분리한다.
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
