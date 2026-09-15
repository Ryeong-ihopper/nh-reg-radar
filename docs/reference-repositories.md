# 참조 레포지토리

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.3 |
| 기준일 | 2026-09-10 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.3 | 2026-09-10 | ADR-0084의 Python 3.11 기준과 document-processor 내부 source 제공 필요 상태 반영 |
| v1.2 | 2026-07-20 | document-processor commit `07c6790`을 Python 3.13/OpenJDK 25 private structure service 이미지의 재현 가능한 기준으로 고정 |
| v1.1 | 2026-07-20 | ADR-0079에 따라 rhwp는 HWP/HWPX 기준 텍스트, document-processor는 구조 원천으로 함께 사용하는 역할을 명시 |
| v1.0 | 2026-07-13 | ADR-0072 기준 Parser/OCR 후보 참조 저장소 목록 정리 |

- HWP/HWPX 기준 텍스트·미리보기 엔진(rust)

    [https://github.com/edwardkim/rhwp](https://github.com/edwardkim/rhwp)

- pdf 파서

    [https://github.com/opendataloader-project/opendataloader-pdf](https://github.com/opendataloader-project/opendataloader-pdf)

- HWP/HWPX 문단·표·스타일 구조 원천인 사내 document parser

    [https://github.com/CGINSIDE-ROOKIES/document-processor](https://github.com/CGINSIDE-ROOKIES/document-processor)

    현행 고정 commit archive는 현재 외부 경로에서 404이므로 Python 3.11 이미지 검증에는
    접근 가능한 사내 mirror 또는 승인된 패키지 artifact 제공이 필요하다.

- ocr 후보군

    [https://huggingface.co/baidu/Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR)

    [https://github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU)

    [https://github.com/PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
