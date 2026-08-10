# -*- coding: utf-8 -*-
"""원본 자료가 어디 있나 — **경로를 코드에 박지 않는다.**

전에는 `r"C:\\Users\\babie\\Downloads\\…"` 처럼 내 PC 경로가 14곳에 박혀 있었다.
다른 사람이 받으면 그대로 죽고, 폐쇄망에 옮기면 전부 고쳐야 한다.

환경변수로 바꿔 두고, 없으면 이 PC 기준 기본값을 쓴다.

    NH_DOWNLOADS   내려받은 자료 폴더        기본 ~/Downloads
    NH_DATA_DIR    고객사 제공 자료 폴더      기본 ~/OneDrive/Desktop/씨지인사이드
    NH_SAMPLE_DIR  광고 샘플                기본 <NH_DATA_DIR>/샘플데이터

  setx NH_DATA_DIR "D:\\자료\\씨지인사이드"
"""
import os

HOME = os.path.expanduser("~")

DOWNLOADS = os.environ.get("NH_DOWNLOADS", os.path.join(HOME, "Downloads"))
DATA_DIR = os.environ.get(
    "NH_DATA_DIR", os.path.join(HOME, "OneDrive", "Desktop", "씨지인사이드"))
SAMPLE_DIR = os.environ.get("NH_SAMPLE_DIR", os.path.join(DATA_DIR, "샘플데이터"))


def dl(*parts):
    """내려받기 폴더 아래 경로."""
    return os.path.join(DOWNLOADS, *parts)


def data(*parts):
    """고객사 자료 폴더 아래 경로."""
    return os.path.join(DATA_DIR, *parts)


def need(path, what=""):
    """없으면 **무엇을 어디에 두라는 것인지** 말하고 죽는다."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{what or '자료'} 를 못 찾음:\n  {path}\n"
            f"  → 환경변수로 바꿀 수 있다: NH_DATA_DIR · NH_DOWNLOADS · NH_SAMPLE_DIR")
    return path
