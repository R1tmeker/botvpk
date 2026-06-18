import { useState } from "react";
import { LogIn, LockKeyhole } from "lucide-react";

import { usePasswordLogin } from "../api/queries";
import type { AuthResponse } from "../types/api";
import { toast } from "../components/Toast";

type ApiError = { response?: { data?: { detail?: string } } };

function errorDetail(err: unknown): string | null {
  const detail = (err as ApiError)?.response?.data?.detail;
  return typeof detail === "string" ? detail : null;
}

export function LoginScreen({ onSuccess }: { onSuccess: (data: AuthResponse) => void }) {
  const [telegramId, setTelegramId] = useState("");
  const [password, setPassword] = useState("");
  const login = usePasswordLogin();
  const canSubmit = telegramId.trim().length > 0 && password.length > 0 && !login.isPending;

  const submit = () => {
    const id = Number(telegramId.trim());
    if (!Number.isInteger(id) || id <= 0) {
      toast("Введите корректный Telegram ID (только цифры)", "error");
      return;
    }
    login.mutate(
      { telegram_id: id, password },
      {
        onSuccess: (data) => onSuccess(data),
        onError: (err) => {
          const detail = errorDetail(err);
          toast(detail ?? "Не удалось войти. Проверьте ID и пароль.", "error");
        },
      },
    );
  };

  return (
    <div style={styles.shell}>
      <section style={styles.card}>
        <div style={styles.iconWrap}>
          <LockKeyhole size={28} strokeWidth={2.2} color="#fff" />
        </div>
        <h1 style={styles.title}>ВПК «Звезда»</h1>
        <p style={styles.subtitle}>Вход на сайт по паролю</p>

        <label style={styles.label}>
          <span style={styles.labelText}>Telegram ID</span>
          <input
            style={styles.input}
            inputMode="numeric"
            autoComplete="username"
            placeholder="например, 123456789"
            value={telegramId}
            onChange={(e) => setTelegramId(e.target.value.replace(/\D/g, ""))}
          />
        </label>

        <label style={styles.label}>
          <span style={styles.labelText}>Пароль</span>
          <input
            style={styles.input}
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) submit();
            }}
          />
        </label>

        <button type="button" style={{ ...styles.button, opacity: canSubmit ? 1 : 0.6 }} disabled={!canSubmit} onClick={submit}>
          <LogIn size={18} strokeWidth={2.4} />
          {login.isPending ? "Входим…" : "Войти"}
        </button>

        <p style={styles.hint}>
          Пароль задаётся в приложении ВПК внутри Telegram: Профиль → «Вход на сайте».
          Доступ только для подтверждённых участников состава.
        </p>
      </section>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  shell: {
    minHeight: "100vh",
    display: "grid",
    placeItems: "center",
    padding: 20,
    background: "linear-gradient(160deg, #1a2f5a 0%, #2c4a8a 100%)",
  },
  card: {
    width: "100%",
    maxWidth: 360,
    background: "#fff",
    borderRadius: 18,
    padding: "28px 22px",
    boxShadow: "0 20px 50px rgba(10,22,50,0.35)",
    display: "grid",
    gap: 14,
  },
  iconWrap: {
    width: 56,
    height: 56,
    borderRadius: 16,
    background: "linear-gradient(135deg, #1a2f5a, #2c4a8a)",
    display: "grid",
    placeItems: "center",
    justifySelf: "center",
  },
  title: { margin: 0, textAlign: "center", fontSize: 20, fontWeight: 900, color: "#1a2f5a" },
  subtitle: { margin: 0, textAlign: "center", fontSize: 13, color: "#65708a", marginTop: -8 },
  label: { display: "grid", gap: 6 },
  labelText: { fontSize: 11, fontWeight: 800, color: "#65708a", textTransform: "uppercase", letterSpacing: 0.4 },
  input: {
    border: "1px solid #d9deea",
    borderRadius: 10,
    padding: "11px 13px",
    fontSize: 16,
    fontFamily: "inherit",
    color: "#1a2f5a",
    outline: "none",
  },
  button: {
    marginTop: 4,
    border: "none",
    borderRadius: 10,
    padding: "12px 16px",
    fontSize: 15,
    fontWeight: 800,
    color: "#fff",
    background: "linear-gradient(135deg, #1a2f5a, #2c4a8a)",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  hint: { margin: 0, fontSize: 11.5, lineHeight: 1.5, color: "#8a96b0", textAlign: "center" },
};
