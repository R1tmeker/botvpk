import { useEffect, useState } from "react";
import { Bell } from "lucide-react";

import { useReadAllNotifications, useReadNotification } from "../../api/queries";
import { toast } from "../../components/Toast";
import { formatDate, formatUnreadCount } from "../../utils/format";
import styles from "../../screens/App.module.scss";
import { useNotificationInbox, useNotificationSummary } from "./api";
import { notificationCategories, notificationDestination } from "./model";

export function NotificationInbox({ onOpen }: { onOpen: (path: string) => void }) {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [category, setCategory] = useState("");
  const [value, setValue] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(value.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [value]);
  const inbox = useNotificationInbox(unreadOnly, category, query);
  const summary = useNotificationSummary();
  const read = useReadNotification();
  const readAll = useReadAllNotifications();
  const items = [...new Map(inbox.data?.pages.flatMap((page) => page.items).map((item) => [item.id, item]) ?? []).values()];
  const markRead = (id: number) => read.mutate(id, { onError: () => toast("Не удалось отметить прочтение. Повторите попытку.", "error") });

  return (
    <section className={styles.panel} aria-label="Уведомления">
      <div className={styles.panelHeader}>
        <h2>Уведомления</h2>
        <span>{summary.data ? formatUnreadCount(summary.data.unread) : summary.isError ? "Счётчик недоступен" : "Загрузка счётчика…"}</span>
      </div>
      <div className={styles.filterChips}>
        <button type="button" className={styles.chip} data-active={!unreadOnly} aria-pressed={!unreadOnly} onClick={() => setUnreadOnly(false)}>Все</button>
        <button type="button" className={styles.chip} data-active={unreadOnly} aria-pressed={unreadOnly} onClick={() => setUnreadOnly(true)}>Непрочитанные</button>
        {(summary.data?.unread ?? 0) > 0 && <button type="button" className={styles.chip} disabled={readAll.isPending} onClick={() => readAll.mutate(undefined, {
          onSuccess: () => toast("Уведомления отмечены прочитанными", "success"),
          onError: () => toast("Не удалось отметить уведомления. Повторите попытку.", "error"),
        })}>{readAll.isPending ? "Сохраняем…" : "Прочитать все"}</button>}
      </div>
      <div className={styles.formBlock}>
        <input type="search" aria-label="Поиск по уведомлениям" placeholder="Найти в заголовке или тексте" maxLength={100} value={value} onChange={(event) => setValue(event.target.value)} />
        <select aria-label="Категория уведомлений" value={category} onChange={(event) => setCategory(event.target.value)}>
          {notificationCategories.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
        </select>
      </div>
      <div aria-live="polite">
        {inbox.isPending && <p role="status">Загружаем уведомления…</p>}
        {inbox.isError && <div className={styles.commandStrip}><span>Не удалось загрузить уведомления.</span><button type="button" onClick={() => void inbox.refetch()}>Повторить</button></div>}
        {!inbox.isPending && !inbox.isError && items.length === 0 && <p>{query ? "По этому запросу ничего не найдено." : unreadOnly ? "Непрочитанных уведомлений нет." : "В этой категории уведомлений пока нет."}</p>}
      </div>
      <div className={styles.list}>
        {items.map((item) => {
          const destination = notificationDestination(item);
          return <article className={styles.row} key={item.id} data-muted={item.is_read}>
            <Bell className={styles.appIcon} aria-hidden="true" />
            <div>
              <strong>{item.is_pinned ? "📌 " : ""}{item.title}</strong>
              <span>{formatDate(item.created_at)}{!item.is_read ? " · новое" : ""}</span>
              {item.body && <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{item.body}</p>}
            </div>
            <div className={styles.filePreviewActions}>
              {destination && <button type="button" onClick={() => { if (!item.is_read) markRead(item.id); onOpen(destination); }}>Открыть</button>}
              {!item.is_read && <button type="button" disabled={read.isPending || readAll.isPending} onClick={() => markRead(item.id)}>Прочитано</button>}
            </div>
          </article>;
        })}
      </div>
      {inbox.hasNextPage && <div className={styles.commandStrip}><button type="button" disabled={inbox.isFetchingNextPage} onClick={() => void inbox.fetchNextPage()}>{inbox.isFetchingNextPage ? "Загружаем…" : "Загрузить ещё"}</button></div>}
    </section>
  );
}
