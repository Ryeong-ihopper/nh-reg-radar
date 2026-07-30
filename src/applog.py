# -*- coding: utf-8 -*-
"""
공통 로깅 설정.

print 대신 파이썬 표준 `logging` 을 쓴다. print 는
  · 언제 찍혔는지 모르고 (배치가 한 달에 한 번 도는데 시각이 없으면 추적 불가)
  · 심각도 구분이 없어 cron.log 에서 오류만 골라볼 수 없고
  · 파일이 무한정 커진다
는 문제가 있다.

사용:
    from applog import get_logger
    log = get_logger(__name__)
    log.info("...")   log.warning("...")   log.error("...", exc_info=True)

환경변수
    LOG_LEVEL   기본 INFO (DEBUG/INFO/WARNING/ERROR)
    LOG_FILE    기본 output/_reports/app.log
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "output", "_reports")
LOG_FILE = os.environ.get("LOG_FILE", os.path.join(LOG_DIR, "app.log"))

_configured = False


def setup(level=None, to_file=True):
    """루트 로거를 한 번만 구성한다."""
    global _configured
    if _configured:
        return logging.getLogger()

    lv = getattr(logging, (level or os.environ.get("LOG_LEVEL", "INFO")).upper(),
                 logging.INFO)
    root = logging.getLogger()
    root.setLevel(lv)

    # 화면: 사람이 읽는 용도라 시각은 짧게
    con = logging.StreamHandler(sys.stdout)
    con.setLevel(lv)
    con.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(con)

    if to_file:
        os.makedirs(LOG_DIR, exist_ok=True)
        # 5MB × 5개까지만 보관 — 배치 로그가 무한정 커지지 않게
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024,
                                 backupCount=5, encoding="utf-8")
        fh.setLevel(lv)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(fh)

    _configured = True
    return root


def get_logger(name=None):
    setup()
    return logging.getLogger(name or "app")
