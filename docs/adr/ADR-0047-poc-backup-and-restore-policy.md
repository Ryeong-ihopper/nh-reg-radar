# ADR-0047: PoC 백업 및 복구 정책

## 상태

Accepted

## 배경

PoC 환경은 개발 속도가 중요하지만, 광고물 원본, 기준자료, 검토 결과, 감사 로그, PoC 평가 데이터가 함께 쌓인다. 또한 ADR-0041은 migration 실패 또는 downgrade가 필요한 경우 백업/restore를 우선한다고 정의했으나, 어떤 데이터를 어떤 주기로 백업하고 어떻게 복구할지는 아직 구체화되어 있지 않았다.

본 프로젝트는 PostgreSQL, S3 호환 Object Storage, Qdrant, OpenSearch를 사용한다. 각 저장소의 성격이 다르므로 모든 구성요소를 같은 수준으로 snapshot하는 것보다 원천 데이터와 재생성 가능한 인덱스를 구분해 백업 정책을 세운다.

## 결정

PoC 백업은 PostgreSQL, Object Storage, Qdrant를 기본 백업 대상으로 삼고, OpenSearch는 원천 데이터 기준 재색인 가능 대상으로 관리한다.

| 구성요소 | 정책 |
| --- | --- |
| PostgreSQL | 매일 1회 dump, migration 전 수동 backup 필수 |
| Object Storage/MinIO | bucket 단위 백업, 광고 원본/기준자료/리포트/파서 산출물 포함 |
| Qdrant | collection snapshot 또는 export 관리 |
| OpenSearch | PoC에서는 snapshot 필수 제외, PostgreSQL/Object Storage 기준 재색인 복구 |
| Redis | queue/cache 성격이므로 백업 대상 제외 |

OpenSearch snapshot은 본사업 전환 또는 검색 인덱스 재생성 비용이 커지는 시점에 재검토한다.

## 백업 대상

| 대상 | 포함 데이터 | 백업 방식 |
| --- | --- | --- |
| PostgreSQL | 사용자, 권한, 광고 메타데이터, 검토 결과, 기준자료 메타데이터, 감사 로그, PoC 평가 데이터 | `pg_dump` 또는 동등한 논리 백업 |
| Object Storage | 광고 원본, 수정본, 상품설명서/약관, 기준자료 원문, OCR/파서 산출물, 리포트 파일 | bucket sync 또는 object storage export |
| Qdrant | 기준자료/심의사례/상품자료 embedding collection | Qdrant snapshot 또는 collection export |
| OpenSearch | 키워드 검색 인덱스 | 원천 데이터 기준 재색인 |

## 백업 시점

| 시점 | 기준 |
| --- | --- |
| 정기 백업 | `prod(main)` 기준 매일 1회 |
| migration 전 | `prod(main)` DB schema 변경 전 PostgreSQL backup 필수 |
| 기준자료 대량 갱신 전 | PostgreSQL, Object Storage, Qdrant backup 권장 |
| PoC 평가 실행 전 | 평가 재현성을 위해 PostgreSQL backup 권장 |
| 결과보고서 작성 전 | 검토 결과와 평가 데이터 backup 권장 |

`dev` 환경은 필수 정기 백업 대상에서 제외할 수 있다. 다만 공유 개발 VM에서 여러 개발자가 함께 쓰는 데이터가 있거나 재현이 필요한 샘플셋이 있는 경우 수동 백업을 허용한다.

## 복구 기준

| 장애 유형 | 복구 방식 |
| --- | --- |
| migration 실패 | PostgreSQL backup restore 우선, 필요 시 Alembic revision 재적용 |
| Object Storage 손실 | bucket backup에서 object 복구, PostgreSQL 파일 메타데이터와 checksum 대조 |
| Qdrant 손실 | snapshot 복구 또는 기준자료 chunk 기준 embedding 재생성 |
| OpenSearch 손실 | PostgreSQL/Object Storage/Qdrant 원천 기준 재색인 |
| Redis 손실 | 진행 중 job은 PostgreSQL job 상태 테이블 기준으로 재시도 또는 실패 처리 |

복구 후에는 최소한 PostgreSQL row count, 주요 bucket object count, Qdrant collection count, OpenSearch index 재색인 완료 여부를 확인한다.

## 보관 기준

| 백업 | PoC 기준 보관 |
| --- | --- |
| PostgreSQL 정기 백업 | 최근 7일 보관 |
| migration 전 백업 | 해당 migration 안정화 확인 후 삭제 가능 |
| Object Storage 백업 | PoC 종료 후 산출물 정리 시점까지 보관 |
| Qdrant snapshot | 기준자료 버전 또는 대량 재색인 단위로 보관 |
| OpenSearch snapshot | PoC 필수 보관 대상 아님 |

본사업 전환 시에는 고객사 보안 정책, 저장 용량, 복구 목표 시간, 복구 목표 시점에 따라 보관 기간을 다시 산정한다.

## 복구 검증

PoC에서는 정기 DR 훈련까지는 요구하지 않지만, 최소 1회 restore runbook 검증을 수행한다.

| 검증 항목 | 기준 |
| --- | --- |
| PostgreSQL restore | dump 파일로 빈 DB에 복구 가능해야 함 |
| Object Storage restore | 대표 bucket의 sample object를 복구하고 checksum을 확인해야 함 |
| Qdrant restore | snapshot 또는 export로 collection을 복구하거나 embedding 재생성 절차가 확인되어야 함 |
| OpenSearch 재색인 | 원천 데이터 기준 재색인 절차가 문서화되어야 함 |

## 대안

| 대안 | 판단 |
| --- | --- |
| 백업 정책 없음 | 구현은 빠르지만 migration 실패, 데이터 유실, PoC 결과 재현 실패 위험이 크다. |
| PostgreSQL만 정기 백업 | 핵심 메타데이터는 보호되지만 원본 파일과 vector collection 복구가 불완전하다. |
| PostgreSQL, Object Storage, Qdrant 백업 + OpenSearch 재색인 | 원천 데이터 보호와 PoC 운영 부담의 균형이 좋다. |
| 모든 저장소 정기 snapshot | 안전하지만 PoC 단계에서는 운영 부담과 저장소 사용량이 커진다. |
| 본사업 전환 시 결정 | 초기에는 편하지만 온프렘 이전 및 고객 검수 시 복구 절차 공백이 생긴다. |

## 결정 근거

- PostgreSQL은 업무 메타데이터와 감사 로그의 원천이므로 정기 백업과 migration 전 백업이 필요하다.
- Object Storage는 광고 원본과 기준자료 원문을 보관하므로 DB만으로는 복구할 수 없다.
- Qdrant는 embedding 재생성 비용이 있으므로 snapshot 또는 export를 관리하는 것이 PoC 재현성에 유리하다.
- OpenSearch는 키워드 색인이며 원천 데이터에서 재생성 가능하므로 PoC에서는 필수 snapshot 대상에서 제외할 수 있다.
- Redis는 job queue/cache 성격이므로 PostgreSQL job 상태 테이블을 복구 기준으로 삼는다.

## 영향

- Docker Compose 또는 운영 스크립트에 PostgreSQL dump, MinIO bucket sync, Qdrant snapshot 명령을 추가해야 한다.
- Migration 실행 절차에는 `prod(main)` 반영 전 PostgreSQL backup 단계를 포함해야 한다.
- Object Storage 파일 메타데이터의 checksum은 복구 검증에 사용된다.
- OpenSearch index 생성/재색인 절차는 스크립트 또는 runbook으로 남겨야 한다.
- PoC 결과보고서 작성 전에는 평가 데이터와 검토 결과가 백업되어 있어야 한다.

## 후속 조치

- `scripts/backup-postgres.sh`, `scripts/backup-object-storage.sh`, `scripts/backup-qdrant.sh` 후보를 구현 단계에서 작성한다.
- Restore runbook을 `docs` 또는 운영 문서에 추가한다.
- DB 명세서의 백업 정책 후속 상세화 항목을 본 ADR 기준으로 갱신한다.
- 본사업 전환 시 RTO/RPO, 장기 보관 기간, 암호화 백업, 오프사이트 백업 여부를 별도 ADR 또는 운영 정책으로 확정한다.

## 관련 문서

- `docs/database-specification.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0029-postgresql-schema-separation.md`
- `docs/adr/ADR-0041-alembic-migration-and-seed-policy.md`
- `docs/adr/ADR-0035-redis-queue-postgresql-job-state.md`
