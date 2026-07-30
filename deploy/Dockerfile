# 규정 수집·변경감지 파이프라인
# 배치(CronJob)와 API(Deployment)가 같은 이미지를 쓰고 command 로만 갈린다.
#
#   배치: python src/check_updates.py --cron
#   API : uvicorn api:app --host 0.0.0.0 --port 8000
#
# 빌드는 **저장소 루트**에서 실행한다.
#   docker build -f deploy/Dockerfile -t regulation-pipeline .
FROM python:3.12-slim

# document-processor 는 JVM 기반(jpype)이라 JRE 가 필수다.
# HWP/PDF 표 구조를 보존하는 유일한 경로이므로 빼면 파싱 품질이 떨어진다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jre-headless \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Seoul \
    PYTHONPATH=/app/src \
    REGULATION_DB=/data/regulations.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY targets.json ./
COPY deploy/sql/ ./sql/

# 수집 산출물(JSON/TXT/원본파일)과 DB 는 볼륨에 둔다
RUN mkdir -p /data /app/output
VOLUME ["/data", "/app/output"]

EXPOSE 8000

# 기본은 API 서버. 배치는 K8s CronJob 에서 command 를 덮어쓴다.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
