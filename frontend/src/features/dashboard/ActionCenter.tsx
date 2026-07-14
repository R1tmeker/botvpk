import type { ActionItem } from "../../types/api";
import styles from "../../screens/App.module.scss";

export function actionItemLabel(actionCode: string): string {
  return {
    send_reminder: "Напомнить всем",
    assign_reviewer: "Взять в работу",
    assign: "Назначить на себя",
    mark_all_present: "Все присутствовали",
    retry_delivery: "Повторить доставку",
  }[actionCode] ?? actionCode;
}

export function ActionCenter({
  items,
  isPending,
  onOpen,
  onAction,
}: {
  items: ActionItem[];
  isPending: boolean;
  onOpen: (deepLink: string) => void;
  onAction: (itemCode: string, actionCode: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section className={styles.actionCenter} aria-labelledby="action-center-title">
      <div className={styles.actionCenterHeader}>
        <h3 id="action-center-title">Требует действия</h3>
        <span>{items.reduce((sum, item) => sum + item.count, 0)}</span>
      </div>
      <div className={styles.actionCenterList}>
        {items.map((item) => (
          <article key={item.code} className={styles.actionCenterItem} data-severity={item.severity}>
            <button type="button" className={styles.actionCenterLink} onClick={() => onOpen(item.deep_link)}>
              <span className={styles.actionCenterCount}>{item.count}</span>
              <span>
                <strong>{item.title}</strong>
                <small>{item.description}</small>
              </span>
            </button>
            {item.bulk_actions.length > 0 && (
              <div className={styles.actionCenterActions}>
                {item.bulk_actions.map((actionCode) => (
                  <button
                    key={actionCode}
                    type="button"
                    disabled={isPending}
                    onClick={() => onAction(item.code, actionCode)}
                  >
                    {actionItemLabel(actionCode)}
                  </button>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
