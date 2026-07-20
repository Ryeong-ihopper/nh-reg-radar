BEGIN;

INSERT INTO app.roles (role_id, role_name, role_description, is_active)
VALUES
  ('PRODUCT_DEPARTMENT_USER', '상품부서 담당자', '소속 부서 광고물을 등록하고 조회한다.', true),
  ('COMPLIANCE_REVIEWER', '준법감시 담당자', '검토 대상 광고물을 조회한다.', true),
  ('STANDARD_MANAGER', '기준 관리자', '기준자료를 관리한다.', true),
  ('SYSTEM_ADMIN', '시스템 관리자', '사용자, 권한, 감사 로그를 관리한다.', true)
ON CONFLICT (role_id) DO UPDATE SET
  role_name = EXCLUDED.role_name,
  role_description = EXCLUDED.role_description,
  is_active = EXCLUDED.is_active;

INSERT INTO app.common_codes
  (code_id, code_group, code, code_name, sort_order, is_enabled)
VALUES
  ('00000000-0000-4000-8000-000000000001', 'product-groups', 'DEPOSIT', '예금', 1, true),
  ('00000000-0000-4000-8000-000000000002', 'product-groups', 'SAVINGS', '적금', 2, true),
  ('00000000-0000-4000-8000-000000000003', 'product-groups', 'DEMAND_DEPOSIT', '입출금', 3, true),
  ('00000000-0000-4000-8000-000000000004', 'product-groups', 'EVENT', '이벤트', 4, true),
  ('00000000-0000-4000-8000-000000000005', 'product-groups', 'LOAN', '대출', 5, true),
  ('00000000-0000-4000-8000-000000000101', 'advertisement-types', 'BRANCH_FLYER', '영업점 안내장', 1, true),
  ('00000000-0000-4000-8000-000000000102', 'advertisement-types', 'NOTICE', '고객 안내문', 2, true),
  ('00000000-0000-4000-8000-000000000103', 'advertisement-types', 'MOBILE_BANNER', '모바일 배너', 3, true),
  ('00000000-0000-4000-8000-000000000104', 'advertisement-types', 'WEB_BANNER', '웹 배너', 4, true),
  ('00000000-0000-4000-8000-000000000105', 'advertisement-types', 'EVENT_PAGE', '이벤트 페이지', 5, true),
  ('00000000-0000-4000-8000-000000000106', 'advertisement-types', 'PUSH', '앱 푸시', 6, true),
  ('00000000-0000-4000-8000-000000000107', 'advertisement-types', 'SMS', 'SMS', 7, true),
  ('00000000-0000-4000-8000-000000000108', 'advertisement-types', 'ALIMTALK', '알림톡', 8, true),
  ('00000000-0000-4000-8000-000000000201', 'review-statuses', 'UPLOADED', '등록 완료', 1, true),
  ('00000000-0000-4000-8000-000000000202', 'review-statuses', 'REVISED', '수정본 등록', 2, true)
ON CONFLICT (code_group, code) DO UPDATE SET
  code_name = EXCLUDED.code_name,
  sort_order = EXCLUDED.sort_order,
  is_enabled = EXCLUDED.is_enabled;

COMMIT;
