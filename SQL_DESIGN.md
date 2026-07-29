# 규정 데이터 SQL 적재 설계 초안

## 목적

파싱된 법령·협회 규정을 최신본만 덮어쓰지 않고 버전별로 보관하고, 변경 조문과 수집 오류를 조회할 수 있도록 한다. RAG 도입 여부와 무관하게 Rule-first 및 감사 이력의 기준 데이터로 사용한다.

## 핵심 원칙

- `regulations`는 규정의 고정 식별정보를 저장한다.
- `regulation_versions`는 공식 버전키와 본문 해시별 전체 스냅샷을 저장한다.
- `regulation_sections`는 조·항·호·부칙·별표·표를 조회 가능한 단위로 저장한다.
- `collection_runs`는 동일·신규·변경·오류를 포함한 실행 이력을 저장한다.
- `regulation_changes`와 `regulation_section_changes`는 버전 간 변경 내용만 저장한다.
- HWP/PDF/XLSX는 `regulation_artifacts`에서 원본 위치와 파일 해시를 관리한다.
- 현재본도 과거 버전을 삭제하지 않고 `is_current`만 전환한다.

## 공통 메타데이터

| 필드 | 의미 |
|---|---|
| `source_code` | lawgo, kofia, crefia, kfb 등 출처 코드 |
| `external_id` | 법령 ID, seq, 게시물 idx 등 출처 식별자 |
| `official_version_key` | MST·공포번호, historySeq 등 공식 버전 |
| `content_hash` | 본문 구조 또는 원본 파일 SHA-256 |
| `promulgated_at` | 공포·발령일 |
| `effective_at` | 시행일 |
| `collected_at` | 실제 수집 시각 |
| `parsed_content` | 조문·부칙·별표·표를 포함한 JSON |
| `plain_text` | 검색·비교용 전체 텍스트 |
| `validation_status` | pending, valid, warning, invalid |
| `is_current` | 현재 사용해야 하는 버전 여부 |

## 변경 적재 순서

1. 수집 실행을 `collection_runs`에 생성한다.
2. 공식 버전키와 필요 시 본문/파일 해시를 비교한다.
3. 동일하면 실행 결과만 기록하고 종료한다.
4. 신규·변경이면 새 `regulation_versions`와 `regulation_sections`를 삽입한다.
5. 기존 버전의 `is_current`를 false, 신규 버전을 true로 변경한다.
6. 조문 diff를 `regulation_section_changes`에 저장한다.
7. 원본 첨부파일 정보를 `regulation_artifacts`에 저장한다.
8. 원문 대조 검증 후 `validation_status`를 valid 또는 warning으로 갱신한다.

실제 DDL은 [sql/regulation_schema.sql](sql/regulation_schema.sql)에 작성했다.
