BEGIN;

INSERT INTO app.departments
  (department_id, department_name, parent_department_id, is_active)
VALUES
  ('DPT-SYNTH-PRODUCT', 'Synthetic Product Team', NULL, true),
  ('DPT-SYNTH-COMPLIANCE', 'Synthetic Compliance Team', NULL, true)
ON CONFLICT (department_id) DO UPDATE SET
  department_name = EXCLUDED.department_name,
  parent_department_id = EXCLUDED.parent_department_id,
  is_active = EXCLUDED.is_active,
  updated_at = now();

INSERT INTO app.users
  (user_id, auth_provider, user_name, email, password_hash, department_id, user_status,
   auth_token_version, failed_login_count, password_changed_at)
VALUES
  ('USR-SYNTH-PRODUCT', 'LOCAL', 'Synthetic Product User', 'product@example.invalid',
   convert_from(decode(:'dev_password_hash_b64', 'base64'), 'UTF8'),
   'DPT-SYNTH-PRODUCT', 'ACTIVE', 1, 0, now()),
  ('USR-SYNTH-COMPLIANCE', 'LOCAL', 'Synthetic Compliance User', 'compliance@example.invalid',
   convert_from(decode(:'dev_password_hash_b64', 'base64'), 'UTF8'),
   'DPT-SYNTH-COMPLIANCE', 'ACTIVE', 1, 0, now())
ON CONFLICT (user_id) DO UPDATE SET
  user_name = EXCLUDED.user_name,
  email = EXCLUDED.email,
  password_hash = EXCLUDED.password_hash,
  department_id = EXCLUDED.department_id,
  user_status = EXCLUDED.user_status,
  updated_at = now();

INSERT INTO app.user_roles (user_role_id, user_id, role_id)
VALUES
  ('10000000-0000-4000-8000-000000000001', 'USR-SYNTH-PRODUCT', 'PRODUCT_DEPARTMENT_USER'),
  ('10000000-0000-4000-8000-000000000002', 'USR-SYNTH-COMPLIANCE', 'COMPLIANCE_REVIEWER')
ON CONFLICT (user_id, role_id) DO NOTHING;

COMMIT;
