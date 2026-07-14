# ADR-0017: S3 호환 Object Storage 기반 파일 저장소

## 상태

Accepted

## 배경

본 프로젝트는 광고 원본, 상품설명서, 약관, 기준자료 원문, OCR/파서 산출물, 리포트 파일을 저장해야 한다. 파일은 PDF, 이미지, HWP/HWPX, JSON, HTML, Markdown, 리포트 문서 등 다양한 형식이 될 수 있으며, PoC 이후 온프렘 환경으로 이전될 가능성이 있다.

초기 PoC의 업로드 허용 확장자와 용량 제한은 [ADR-0037: 파일 업로드 허용 확장자 및 용량 제한](ADR-0037-file-upload-allowlist-and-size-limit.md)을 따른다.

로컬 파일시스템은 초기 구현은 쉽지만 서버가 늘어나거나 온프렘 운영 환경이 바뀔 때 백업, 권한, 경로, 마운트 관리가 애플리케이션에 강하게 묶인다. DB BLOB은 트랜잭션 관리에는 유리하지만 대용량 파일이 늘어날수록 DB 백업과 성능 부담이 커진다.

## 결정

파일 저장소는 S3 호환 Object Storage 인터페이스를 기준으로 설계한다.

개발 및 PoC 환경은 Docker Compose에서 MinIO를 기본 후보로 사용한다. 온프렘 이전 시에는 고객사 환경에 따라 MinIO, 사내 S3 호환 스토리지, 또는 동일 인터페이스를 구현한 NAS Adapter로 교체할 수 있도록 한다.

| 항목 | 결정 |
| --- | --- |
| 기준 인터페이스 | S3 호환 Object Storage |
| 개발/PoC 기본 후보 | MinIO |
| 운영/온프렘 후보 | MinIO, 사내 S3 호환 스토리지, NAS Adapter |
| 애플리케이션 접근 | 내부 `ObjectStorageAdapter`를 통해 접근 |
| DB 저장 방식 | 파일 바이너리가 아니라 객체 메타데이터 저장 |
| 다운로드 방식 | 권한 검증 후 backend proxy 또는 presigned URL |

업무 로직은 특정 저장소 제품을 직접 호출하지 않는다. 파일 업로드, 다운로드, 삭제, 존재 확인, checksum 검증은 내부 Adapter 인터페이스를 통해 수행한다.

```text
upload file
  -> FileService
  -> ObjectStorageAdapter
      -> MinioStorageAdapter
      -> S3StorageAdapter
      -> NasStorageAdapter
  -> file metadata in PostgreSQL
```

## 저장 대상

| 구분 | 저장소 | DB 저장 정보 |
| --- | --- | --- |
| 광고 원본 파일 | Object Storage | 광고 ID, 파일 ID, bucket, object key, checksum, content type, size |
| 상품설명서/약관 | Object Storage | 상품/광고 연결 정보, 버전, object key |
| 기준자료 원문 | Object Storage | 기준자료 ID, 버전, object key, 적용일 |
| OCR/파서 산출물 | Object Storage 또는 DB | 대용량 JSON/HTML/Markdown은 Object Storage, 검색용 메타데이터는 DB |
| 리포트 파일 | Object Storage | 리포트 ID, HWPX/PDF 포맷, object key, 생성 시각 |

DB에는 파일 본문을 저장하지 않고 다음 메타데이터를 저장한다.

| 메타데이터 | 설명 |
| --- | --- |
| `storage_provider` | minio, s3, nas 등 |
| `bucket` | 저장 bucket |
| `object_key` | 객체 경로 |
| `original_file_name` | 원본 파일명 |
| `content_type` | MIME type |
| `file_size` | byte 단위 크기 |
| `checksum_sha256` | 무결성 검증값 |
| `storage_version` | 저장소 버전 또는 객체 version id, 없으면 null |
| `created_by` | 업로드 사용자 |
| `created_at` | 업로드 시각 |

## Bucket 및 Object Key 원칙

Bucket은 데이터 성격별로 분리한다.

| Bucket | 용도 |
| --- | --- |
| `ad-originals` | 광고 원본, 수정본 |
| `reference-documents` | 기준자료, 법령, 내규, 상품자료 원문 |
| `parser-artifacts` | OCR/파서 중간 산출물 |
| `reports` | 생성 리포트 |

Object key는 예측 가능한 업무 ID를 포함하되, 원본 파일명만으로 구성하지 않는다.

```text
advertisements/{advertisement_id}/revisions/{revision_no}/{file_id}/{safe_file_name}
standards/{standard_id}/versions/{version}/{file_id}/{safe_file_name}
reports/{review_id}/{report_id}/{format}/{file_name}
```

원본 파일명은 표시용 메타데이터로 보관하고, 저장 경로에는 파일 ID나 revision 정보를 포함해 충돌을 방지한다.

## 접근 및 보안 원칙

| 항목 | 원칙 |
| --- | --- |
| 직접 공개 | Object Storage bucket은 기본 비공개 |
| 다운로드 | backend 권한 검증 후 proxy 또는 짧은 만료시간의 presigned URL 발급 |
| 업로드 | backend가 검증 후 저장하거나 제한된 presigned upload 사용 |
| 비밀값 | access key, secret key는 `.env` 커밋 금지, 서버 secret으로 주입 |
| 무결성 | 업로드 후 checksum 저장 및 필요 시 다운로드 검증 |
| 삭제 | 업무상 삭제보다 비활성화/보존 정책 우선 |

고객사 자료와 광고 원본은 외부 공개 URL로 장기 노출하지 않는다. presigned URL을 사용하는 경우 만료 시간을 짧게 두고, 발급 이력은 감사 로그 대상에 포함한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 로컬 파일시스템 | 가장 단순하지만 서버 확장, 백업, 권한, 온프렘 이전 시 경로 의존성이 커진다. |
| NAS/NFS/SMB | 온프렘 인프라와 맞을 수 있으나 마운트 장애, 권한, 잠금, 경로 의존성 처리가 필요하다. |
| DB BLOB | 트랜잭션 단일화는 가능하지만 대용량 파일 증가 시 DB 백업, 복구, 성능 부담이 크다. |
| S3 호환 Object Storage | 초기 설정은 필요하지만 MinIO, 사내 S3, AWS S3 등으로 교체 가능해 PoC와 온프렘 이전에 적합하다. |

## 결정 근거

- Docker Compose 기반 PoC와 온프렘 이전 가능성을 동시에 만족한다.
- MinIO를 사용하면 로컬/개발 VM에서 S3 API를 재현할 수 있다.
- 파일 바이너리를 DB에서 분리해 PostgreSQL의 백업/복구 부담을 줄일 수 있다.
- Object key와 checksum을 DB에 저장하면 감사 추적과 무결성 검증이 가능하다.
- 저장소 제품을 Adapter 뒤에 숨기면 NAS나 고객사 스토리지로 교체할 때 업무 로직 변경을 줄일 수 있다.

## 영향

- Docker Compose 구성에 MinIO 서비스를 추가해야 한다.
- DB 명세의 파일 테이블은 `file_path` 중심에서 `storage_provider`, `bucket`, `object_key`, `checksum_sha256` 중심으로 정리해야 한다.
- API 명세의 파일 미리보기/다운로드는 권한 검증과 presigned URL 또는 backend proxy 방식을 반영해야 한다.
- 테스트는 Object Storage mock 또는 MinIO 컨테이너 기반 통합 테스트를 포함해야 한다.
- 운영 환경에서는 bucket 정책, 백업, 보존 기간, 접근 로그 정책을 별도로 정의해야 한다.

## 후속 조치

- `compose.yml` 또는 개발 Compose 설계에 MinIO 서비스를 추가한다.
- `ObjectStorageAdapter` 인터페이스와 MinIO 구현체를 만든다.
- DB 명세의 `advertisement_files`, 기준자료 원문, 리포트 파일 저장 필드를 본 ADR 기준으로 갱신한다.
- API 명세의 파일 다운로드/미리보기 응답에 presigned URL 또는 proxy 다운로드 정책을 반영한다.
- 파일 접근 권한 및 다운로드 정책은 별도 ADR에서 확정한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
- `docs/adr/ADR-0002-customer-sample-data-ai-input-policy.md`
- `docs/adr/ADR-0037-file-upload-allowlist-and-size-limit.md`
