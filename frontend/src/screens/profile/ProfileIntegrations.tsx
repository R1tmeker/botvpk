import { useEffect, useState } from "react";

import {
  useDeletePassword,
  usePasswordStatus,
  useSetPassword,
  useTwoFactorDisable,
  useTwoFactorEnable,
  useTwoFactorSetup,
  useTwoFactorStatus,
  useVkLinkCode,
  useVkStatus,
  useVkUnlink,
  useWebPushPublicKey,
  useWebPushSubscribe,
  useWebPushUnsubscribe,
} from "../../api/queries";
import { toast } from "../../components/Toast";
import { type AppTheme, saveTheme } from "../../theme";
import styles from "../App.module.scss";

function currentTheme(): AppTheme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function urlBase64ToArrayBuffer(value: string): ArrayBuffer {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const output = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) {
    output[i] = raw.charCodeAt(i);
  }
  return buffer;
}

export function ThemeSection() {
  const [theme, setTheme] = useState<AppTheme>(() => currentTheme());

  const updateTheme = (nextTheme: AppTheme) => {
    setTheme(nextTheme);
    saveTheme(nextTheme);
    toast(nextTheme === "dark" ? "Тёмная тема включена" : "Светлая тема включена", "success");
  };

  return (
    <div className={styles.webAccessCard}>
      <div className={styles.webAccessHeader}>
        <div>
          <strong>Тема</strong>
          <small>{theme === "dark" ? "Тёмная палитра активна" : "Светлая палитра активна"}</small>
        </div>
        <span className={styles.webAccessDot} data-on={theme === "dark"} />
      </div>
      <div className={styles.themeToggle} role="group" aria-label="Переключение темы">
        <button type="button" data-active={theme === "light"} onClick={() => updateTheme("light")}>
          Светлая
        </button>
        <button type="button" data-active={theme === "dark"} onClick={() => updateTheme("dark")}>
          Тёмная
        </button>
      </div>
    </div>
  );
}

export function WebPushSection() {
  const supported =
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window;
  const key = useWebPushPublicKey(supported);
  const subscribe = useWebPushSubscribe();
  const unsubscribe = useWebPushUnsubscribe();
  const [permission, setPermission] = useState<NotificationPermission>(
    supported ? Notification.permission : "denied",
  );
  const [browserSubscription, setBrowserSubscription] = useState<PushSubscription | null>(null);

  useEffect(() => {
    if (!supported) {
      return;
    }
    let alive = true;
    navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => {
        if (alive) {
          setBrowserSubscription(subscription);
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [supported]);

  const enabled = permission === "granted" && browserSubscription !== null;
  const available = supported && (key.data?.available ?? false) && Boolean(key.data?.public_key);

  const enablePush = async () => {
    if (!available || !key.data?.public_key) {
      toast("Push-уведомления пока не настроены на сервере", "error");
      return;
    }
    const result = await Notification.requestPermission();
    setPermission(result);
    if (result !== "granted") {
      toast("Разрешение на уведомления не выдано", "error");
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription =
      (await registration.pushManager.getSubscription()) ??
      (await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToArrayBuffer(key.data.public_key),
      }));
    subscribe.mutate(subscription.toJSON(), {
      onSuccess: () => {
        setBrowserSubscription(subscription);
        toast("Push-уведомления включены", "success");
      },
      onError: () => toast("Не удалось включить push", "error"),
    });
  };

  const disablePush = async () => {
    if (!browserSubscription) {
      return;
    }
    const endpoint = browserSubscription.endpoint;
    await browserSubscription.unsubscribe().catch(() => false);
    unsubscribe.mutate(endpoint, {
      onSuccess: () => {
        setBrowserSubscription(null);
        toast("Push-уведомления отключены", "success");
      },
      onError: () => toast("Подписка отключена в браузере, но сервер не ответил", "warning"),
    });
  };

  if (!supported) {
    return null;
  }

  return (
    <div className={styles.webAccessCard}>
      <div className={styles.webAccessHeader}>
        <div>
          <strong>Push в браузере</strong>
          <small>
            {available
              ? "Важные уведомления могут приходить в установленное приложение"
              : "Серверные ключи Web Push ещё не настроены"}
          </small>
        </div>
        <span className={styles.webAccessDot} data-on={enabled} />
      </div>
      <div className={styles.webAccessActions}>
        <button type="button" onClick={enablePush} disabled={!available || subscribe.isPending}>
          {subscribe.isPending ? "Включаем..." : enabled ? "Обновить подписку" : "Включить push"}
        </button>
        {enabled && (
          <button
            type="button"
            className={styles.webAccessGhost}
            onClick={disablePush}
            disabled={unsubscribe.isPending}
          >
            Отключить
          </button>
        )}
      </div>
    </div>
  );
}

export function TwoFactorSection() {
  const status = useTwoFactorStatus(true);
  const setup = useTwoFactorSetup();
  const enable = useTwoFactorEnable();
  const disable = useTwoFactorDisable();
  const [code, setCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const enabled = status.data?.enabled ?? false;
  const setupData = setup.data;

  const startSetup = () => {
    setup.mutate(undefined, {
      onError: () => toast("Не удалось начать настройку 2FA", "error"),
    });
  };

  const confirmSetup = () => {
    enable.mutate(code, {
      onSuccess: () => {
        setCode("");
        setup.reset();
        toast("2FA включена", "success");
      },
      onError: () => toast("Код 2FA не подошёл", "error"),
    });
  };

  const turnOff = () => {
    disable.mutate(disableCode, {
      onSuccess: () => {
        setDisableCode("");
        toast("2FA отключена", "success");
      },
      onError: () => toast("Не удалось отключить 2FA", "error"),
    });
  };

  return (
    <div className={styles.webAccessCard}>
      <div className={styles.webAccessHeader}>
        <div>
          <strong>Двухфакторная защита</strong>
          <small>{enabled ? "При входе на сайт требуется код authenticator app" : "Рекомендуется для командиров и админов"}</small>
        </div>
        <span className={styles.webAccessDot} data-on={enabled} />
      </div>
      {enabled ? (
        <div className={styles.webAccessForm}>
          <input
            inputMode="numeric"
            placeholder="Код 2FA для отключения"
            value={disableCode}
            onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <div className={styles.webAccessActions}>
            <button
              type="button"
              className={styles.webAccessDanger}
              onClick={turnOff}
              disabled={disableCode.length < 6 || disable.isPending}
            >
              Отключить 2FA
            </button>
          </div>
        </div>
      ) : setupData ? (
        <div className={styles.webAccessForm}>
          <div className={styles.vkCodeBox}>
            <span className={styles.vkCodeValue}>{setupData.secret}</span>
            <small>Добавьте секрет в приложение-аутентификатор или откройте URI:</small>
            <a className={styles.vkBotLink} href={setupData.provisioning_uri}>
              Открыть authenticator URI
            </a>
          </div>
          <input
            inputMode="numeric"
            placeholder="Код из приложения"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <div className={styles.webAccessActions}>
            <button type="button" onClick={confirmSetup} disabled={code.length < 6 || enable.isPending}>
              Подтвердить и включить
            </button>
          </div>
        </div>
      ) : (
        <div className={styles.webAccessActions}>
          <button type="button" onClick={startSetup} disabled={setup.isPending}>
            {setup.isPending ? "Готовим..." : "Настроить 2FA"}
          </button>
        </div>
      )}
    </div>
  );
}

export function WebAccessSection() {
  const status = usePasswordStatus(true);
  const setPassword = useSetPassword();
  const deletePassword = useDeletePassword();
  const [open, setOpen] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const hasPassword = status.data?.has_password ?? false;

  const submit = () => {
    if (newPassword.length < 8) {
      toast("Пароль должен быть не короче 8 символов", "error");
      return;
    }
    setPassword.mutate(
      { new_password: newPassword, current_password: hasPassword ? currentPassword : undefined },
      {
        onSuccess: () => {
          toast(hasPassword ? "Пароль изменён" : "Пароль установлен", "success");
          setOpen(false);
          setNewPassword("");
          setCurrentPassword("");
        },
        onError: () => toast("Не удалось сохранить пароль", "error"),
      },
    );
  };

  return (
    <div className={styles.webAccessCard}>
      <div className={styles.webAccessHeader}>
        <div>
          <strong>Вход на сайте</strong>
          <small>{hasPassword ? "Пароль установлен — можно входить на сайте по Telegram ID" : "Задайте пароль, чтобы входить на сайте без Telegram"}</small>
        </div>
        <span className={styles.webAccessDot} data-on={hasPassword} />
      </div>
      {!open ? (
        <div className={styles.webAccessActions}>
          <button type="button" onClick={() => setOpen(true)}>
            {hasPassword ? "Сменить пароль" : "Задать пароль"}
          </button>
          {hasPassword && (
            <button
              type="button"
              className={styles.webAccessDanger}
              onClick={() =>
                deletePassword.mutate(undefined, {
                  onSuccess: () => toast("Вход по паролю отключён", "success"),
                  onError: () => toast("Не удалось отключить", "error"),
                })
              }
            >
              Отключить
            </button>
          )}
        </div>
      ) : (
        <div className={styles.webAccessForm}>
          {hasPassword && (
            <input
              type="password"
              placeholder="Текущий пароль"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          )}
          <input
            type="password"
            placeholder="Новый пароль (минимум 8 символов)"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <div className={styles.webAccessActions}>
            <button type="button" onClick={submit} disabled={setPassword.isPending}>
              {setPassword.isPending ? "Сохраняем..." : "Сохранить"}
            </button>
            <button type="button" className={styles.webAccessGhost} onClick={() => setOpen(false)}>
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function VkLinkSection() {
  const status = useVkStatus(true);
  const linkCode = useVkLinkCode();
  const unlink = useVkUnlink();
  const [code, setCode] = useState<string | null>(null);
  const linked = status.data?.linked ?? false;
  const botUrl = status.data?.bot_url ?? null;

  const requestCode = () => {
    linkCode.mutate(undefined, {
      onSuccess: (data) => setCode(data.code),
      onError: () => toast("Не удалось получить код", "error"),
    });
  };

  return (
    <div className={styles.webAccessCard}>
      <div className={styles.webAccessHeader}>
        <div>
          <strong>ВКонтакте</strong>
          <small>
            {linked
              ? "Аккаунт привязан — уведомления приходят и в ВК"
              : "Привяжите ВК, чтобы пользоваться ботом и получать уведомления там"}
          </small>
        </div>
        <span className={styles.webAccessDot} data-on={linked} />
      </div>
      {linked ? (
        <div className={styles.webAccessActions}>
          <button
            type="button"
            className={styles.webAccessDanger}
            onClick={() =>
              unlink.mutate(undefined, {
                onSuccess: () => toast("ВК отвязан", "success"),
                onError: () => toast("Не удалось отвязать", "error"),
              })
            }
          >
            Отвязать ВК
          </button>
        </div>
      ) : code ? (
        <div className={styles.vkCodeBox}>
          <span className={styles.vkCodeValue}>{code}</span>
          <small>
            Отправьте этот код боту ВКонтакте в течение 10 минут.
            {botUrl ? "" : " Найдите сообщество ВПК в ВК и напишите ему."}
          </small>
          {botUrl && (
            <a className={styles.vkBotLink} href={botUrl} target="_blank" rel="noopener noreferrer">
              Открыть бота ВК
            </a>
          )}
        </div>
      ) : (
        <div className={styles.webAccessActions}>
          <button type="button" onClick={requestCode} disabled={linkCode.isPending}>
            {linkCode.isPending ? "Готовим код..." : "Привязать ВК"}
          </button>
        </div>
      )}
    </div>
  );
}
