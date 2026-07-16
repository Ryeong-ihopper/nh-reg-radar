import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ApiError, userMessage } from "../api/client";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError("이메일과 비밀번호를 입력해 주세요.");
      return;
    }
    if (password.length < 10) {
      setError("비밀번호는 10자 이상 입력해 주세요.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 401
        ? "이메일 또는 비밀번호가 올바르지 않거나 로그인이 제한되었습니다."
        : userMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="login-card" aria-labelledby="login-heading">
      <h2 id="login-heading">로그인</h2>
      <form onSubmit={submit} noValidate>
        <label htmlFor="email">이메일</label>
        <input id="email" name="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} />
        <label htmlFor="password">비밀번호</label>
        <input id="password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
        {error ? <p role="alert" className="field-error">{error}</p> : null}
        <button type="submit" disabled={submitting}>{submitting ? "로그인 중..." : "로그인"}</button>
      </form>
    </section>
  );
}
