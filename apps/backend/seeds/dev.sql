BEGIN;

INSERT INTO app.departments
  (department_id, department_name, parent_department_id, is_active)
VALUES
  ('DPT-SYNTH-PRODUCT', '상품관리부', NULL, true),
  ('DPT-SYNTH-COMPLIANCE', '준법감시부', NULL, true)
ON CONFLICT (department_id) DO UPDATE SET
  department_name = EXCLUDED.department_name,
  parent_department_id = EXCLUDED.parent_department_id,
  is_active = EXCLUDED.is_active,
  updated_at = now();

INSERT INTO app.users
  (user_id, auth_provider, user_name, email, password_hash, department_id, user_status,
   auth_token_version, failed_login_count, password_changed_at)
VALUES
  ('USR-SYNTH-PRODUCT', 'LOCAL', 'PoC 업무·기준자료 담당자', 'test@ihopper.co.kr',
   convert_from(decode(:'dev_password_hash_b64', 'base64'), 'UTF8'),
   'DPT-SYNTH-PRODUCT', 'ACTIVE', 1, 0, now()),
  ('USR-SYNTH-STANDARD', 'LOCAL', 'PoC 시스템 관리자', 'admin@ihopper.co.kr',
   convert_from(decode(:'dev_password_hash_b64', 'base64'), 'UTF8'),
   'DPT-SYNTH-COMPLIANCE', 'ACTIVE', 1, 0, now())
ON CONFLICT (user_id) DO UPDATE SET
  user_name = EXCLUDED.user_name,
  email = EXCLUDED.email,
  password_hash = EXCLUDED.password_hash,
  department_id = EXCLUDED.department_id,
  user_status = EXCLUDED.user_status,
  updated_at = now();

-- PoC 로그인 계정은 test/admin 두 개만 유지한다. 기존 dev seed의 준법감시 계정은
-- 재실행 환경에서도 로그인할 수 없도록 비활성화하고 역할 매핑을 제거한다.
UPDATE app.users
SET user_status = 'INACTIVE', updated_at = now()
WHERE user_id = 'USR-SYNTH-COMPLIANCE';

DELETE FROM app.user_roles
WHERE user_id IN ('USR-SYNTH-PRODUCT', 'USR-SYNTH-STANDARD', 'USR-SYNTH-COMPLIANCE');

INSERT INTO app.user_roles (user_role_id, user_id, role_id)
VALUES
  ('10000000-0000-4000-8000-000000000001', 'USR-SYNTH-PRODUCT', 'PRODUCT_DEPARTMENT_USER'),
  ('10000000-0000-4000-8000-000000000004', 'USR-SYNTH-PRODUCT', 'COMPLIANCE_REVIEWER'),
  ('10000000-0000-4000-8000-000000000005', 'USR-SYNTH-PRODUCT', 'STANDARD_MANAGER'),
  ('10000000-0000-4000-8000-000000000006', 'USR-SYNTH-STANDARD', 'SYSTEM_ADMIN');

COMMIT;
