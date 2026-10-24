import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type Me } from "../api";
import { useAuth } from "../auth";
import { AuthFrame } from "../components/AuthFrame";

type Preview = {
  team_name: string;
  role: string;
  email: string | null;
  valid: boolean;
};

export function JoinPage() {
  const { token = "" } = useParams();
  const { user, ready, setUser } = useAuth();
  const navigate = useNavigate();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Preview>(`/api/v1/join/${token}`)
      .then(setPreview)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Приглашение не найдено"));
  }, [token]);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>(`/api/v1/join/${token}`, { method: "POST" });
      setUser(me);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
    } finally {
      setBusy(false);
    }
  }

  const role = preview?.role === "admin" ? "админом" : "участником";

  return (
    <AuthFrame
      kicker="Приглашение"
      title={preview ? `«${preview.team_name}»` : "Ссылка"}
      text="Одноразовая ссылка из письма живёт 7 дней. Общая ссылка команды пускает участником, пока её не сменят."
    >
      <section className="panel login-form">
        <h2>{preview?.valid ? `Войти ${role}` : "Ссылка не действует"}</h2>
        {preview?.email && <p className="caption">Письмо адресовано {preview.email}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {!ready && <p className="muted">Загрузка…</p>}
        {ready && preview?.valid && user && (
          <button type="button" className="primary" disabled={busy} onClick={() => void accept()}>
            {busy ? "Вступаю…" : "Вступить"}
          </button>
        )}
        {ready && preview?.valid && !user && (
          <>
            <Link className="primary" to={`/register?invite=${encodeURIComponent(token)}`}>Зарегистрироваться</Link>
            <Link className="ghost" to={`/login?next=/join/${encodeURIComponent(token)}`}>У меня уже есть аккаунт</Link>
          </>
        )}
      </section>
    </AuthFrame>
  );
}
