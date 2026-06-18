import { useState } from "react";
import { Eye, EyeOff, IdCard, LockKeyhole, LogIn, CalendarCheck, Bell, ShieldCheck } from "lucide-react";

import { usePasswordLogin } from "../api/queries";
import type { AuthResponse } from "../types/api";
import { toast } from "../components/Toast";
import styles from "./LoginScreen.module.scss";

type ApiError = { response?: { data?: { detail?: string } } };

function errorDetail(err: unknown): string | null {
  const detail = (err as ApiError)?.response?.data?.detail;
  return typeof detail === "string" ? detail : null;
}

export function LoginScreen({ onSuccess }: { onSuccess: (data: AuthResponse) => void }) {
  const [telegramId, setTelegramId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div className={styles.shell}>
      <section className={styles.card}>
        <aside className={styles.brand}>
          <svg className={styles.brandStars} viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <g fill="#ffffff">
              <path d="M60 50l4 12 12 4-12 4-4 12-4-12-12-4 12-4z" opacity="0.5" />
              <path d="M330 90l5 15 15 5-15 5-5 15-5-15-15-5 15-5z" opacity="0.35" />
              <path d="M300 320l3 9 9 3-9 3-3 9-3-9-9-3 9-3z" opacity="0.4" />
              <path d="M90 300l3 9 9 3-9 3-3 9-3-9-9-3 9-3z" opacity="0.25" />
            </g>
          </svg>
          <img className={styles.emblem} src="/assets/zvezda-emblem.jpg" alt="Эмблема ВПК Звезда" />
          <h1 className={styles.brandTitle}>ВПК «Звезда»</h1>
          <p className={styles.brandSlogan}>
            Личный кабинет участника. Расписание, посещаемость, нормативы и уведомления — в одном месте.
          </p>
          <ul className={styles.brandPoints}>
            <li><CalendarCheck size={18} strokeWidth={2.4} /> Расписание и ответы на занятия</li>
            <li><Bell size={18} strokeWidth={2.4} /> Уведомления командиров</li>
            <li><ShieldCheck size={18} strokeWidth={2.4} /> Доступ только для состава</li>
          </ul>
        </aside>

        <div className={styles.form}>
          <div className={styles.formHeader}>
            <h2>Вход на сайт</h2>
            <p>По Telegram ID и паролю</p>
          </div>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>Telegram ID</span>
            <div className={styles.inputWrap}>
              <IdCard className={styles.inputIcon} size={18} strokeWidth={2.2} />
              <input
                className={styles.input}
                inputMode="numeric"
                autoComplete="username"
                placeholder="например, 123456789"
                value={telegramId}
                onChange={(e) => setTelegramId(e.target.value.replace(/\D/g, ""))}
              />
            </div>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>Пароль</span>
            <div className={styles.inputWrap}>
              <LockKeyhole className={styles.inputIcon} size={18} strokeWidth={2.2} />
              <input
                className={`${styles.input} ${styles.hasToggle}`}
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canSubmit) submit();
                }}
              />
              <button
                type="button"
                className={styles.toggle}
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>

          <button type="button" className={styles.submit} disabled={!canSubmit} onClick={submit}>
            <LogIn size={18} strokeWidth={2.4} />
            {login.isPending ? "Входим…" : "Войти"}
          </button>

          <p className={styles.hint}>
            Пароль задаётся в приложении ВПК внутри Telegram: Профиль → «Вход на сайте».
            Доступ только для подтверждённых участников состава.
          </p>
        </div>
      </section>
    </div>
  );
}
