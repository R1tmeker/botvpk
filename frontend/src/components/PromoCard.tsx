import styles from "./PromoCard.module.scss";
import type { PromoBlock } from "../types/api";

type NavigateFn = (section: string) => void;

const STYLE_THEMES: Record<string, { bg: string; border: string; accent: string; btnBg: string; btnText: string }> = {
  DEFAULT:  { bg: "#fff",     border: "#e0e5ef",                accent: "#1a2f5a", btnBg: "#1a2f5a", btnText: "#fff"     },
  INFO:     { bg: "#eaf4fd",  border: "rgba(52,152,219,0.3)",   accent: "#2980b9", btnBg: "#3498db", btnText: "#fff"     },
  SUCCESS:  { bg: "#eafaf1",  border: "rgba(39,174,96,0.3)",    accent: "#27ae60", btnBg: "#27ae60", btnText: "#fff"     },
  WARNING:  { bg: "#fef9e7",  border: "rgba(243,156,18,0.3)",   accent: "#e67e22", btnBg: "#f39c12", btnText: "#fff"     },
  PROMO:    { bg: "linear-gradient(135deg,#1a2f5a,#2c4a8a)", border: "transparent", accent: "#fff", btnBg: "#e74c3c", btnText: "#fff" },
  DANGER:   { bg: "#fdecea",  border: "rgba(231,76,60,0.3)",    accent: "#c0392b", btnBg: "#e74c3c", btnText: "#fff"     },
};

const AUDIENCE_LABELS: Record<string, string> = {
  ALL: "Все", NEW_USER: "Новые", CANDIDATE: "Кандидаты",
  PARTICIPANT: "Участники", COMMANDER: "Командиры", ADMIN: "Администраторы",
};

function openAction(block: PromoBlock, navigate: NavigateFn) {
  if (block.button_url) {
    window.open(block.button_url, "_blank", "noopener");
    return;
  }
  if (block.action_type_code) {
    const sectionMap: Record<string, string> = {
      OPEN_SECTION: "dashboard",
      OPEN_SCHEDULE: "schedule",
      OPEN_NORMATIVE: "normatives",
      OPEN_COURSE: "learning",
      OPEN_FORM: "appeals",
    };
    const section = sectionMap[block.action_type_code];
    if (section) navigate(section);
  }
}

/* ── Public PromoCard (user-facing) ──────────────────── */
export function PromoCard({ block, navigate, compact = false }: { block: PromoBlock; navigate: NavigateFn; compact?: boolean }) {
  const theme = STYLE_THEMES[block.style_code] ?? STYLE_THEMES.DEFAULT;
  const isPromo = block.style_code === "PROMO";
  const hasAction = Boolean(block.button_url || block.action_type_code);

  return (
    <div
      className={`${styles.card} ${compact ? styles.compact : ""}`}
      style={{
        background: theme.bg,
        borderColor: theme.border === "transparent" ? "transparent" : theme.border,
        color: isPromo ? "#fff" : theme.accent,
      }}
    >
      <div className={styles.cardBody}>
        <strong className={styles.cardTitle} style={{ color: isPromo ? "#fff" : theme.accent }}>
          {block.title}
        </strong>
        {block.body && (
          <p className={styles.cardText} style={{ color: isPromo ? "rgba(255,255,255,0.85)" : "#44516b" }}>
            {block.body}
          </p>
        )}
      </div>
      {hasAction && block.button_text && (
        <button
          type="button"
          className={styles.cardBtn}
          style={{ background: theme.btnBg, color: theme.btnText }}
          onClick={() => openAction(block, navigate)}
        >
          {block.button_text}
        </button>
      )}
    </div>
  );
}

/* ── PromoStrip (multiple cards) ─────────────────────── */
export function PromoStrip({ blocks, navigate }: { blocks: PromoBlock[]; navigate: NavigateFn }) {
  if (blocks.length === 0) return null;
  return (
    <div className={styles.strip}>
      {blocks.slice(0, 3).map((block) => (
        <PromoCard key={block.id} block={block} navigate={navigate} />
      ))}
    </div>
  );
}

/* ── AdminPromoCard (editable list item) ─────────────── */
export function AdminPromoCard({
  block,
  onToggle,
  onEdit,
  onDelete,
}: {
  block: PromoBlock;
  onToggle: (id: number, active: boolean) => void;
  onEdit: (block: PromoBlock) => void;
  onDelete: (id: number) => void;
}) {
  const theme = STYLE_THEMES[block.style_code] ?? STYLE_THEMES.DEFAULT;
  return (
    <div className={`${styles.adminCard} ${!block.is_active ? styles.adminCardDimmed : ""}`}
      style={{ borderLeftColor: theme.btnBg }}
    >
      <div className={styles.adminCardHead}>
        <strong>{block.title}</strong>
        <span className={styles.adminBadge} style={{ background: theme.btnBg }}>{block.style_code}</span>
      </div>
      {block.body && <p className={styles.adminCardText}>{block.body.slice(0, 80)}{block.body.length > 80 ? "…" : ""}</p>}
      <div className={styles.adminCardMeta}>
        <span>👥 {AUDIENCE_LABELS[block.audience_code] ?? block.audience_code}</span>
        {block.button_text && <span>🔗 {block.button_text}</span>}
        {block.active_from && <span>📅 с {block.active_from.slice(0, 10)}</span>}
        {block.active_to && <span>до {block.active_to.slice(0, 10)}</span>}
      </div>
      <div className={styles.adminCardActions}>
        <button type="button" onClick={() => onToggle(block.id, !block.is_active)}>
          {block.is_active ? "Скрыть" : "Показать"}
        </button>
        <button type="button" onClick={() => onEdit(block)}>Редактировать</button>
        <button type="button" onClick={() => onDelete(block.id)} className={styles.adminCardDelete}>
          Удалить
        </button>
      </div>
    </div>
  );
}

/* ── PromoEditForm ────────────────────────────────────── */
type PromoFormData = {
  title: string;
  body: string;
  button_text: string;
  button_url: string;
  action_type_code: string;
  audience_code: string;
  style_code: string;
  sort_order: number;
  is_active: boolean;
  active_from: string;
  active_to: string;
};

const EMPTY_FORM: PromoFormData = {
  title: "", body: "", button_text: "", button_url: "",
  action_type_code: "", audience_code: "ALL", style_code: "DEFAULT",
  sort_order: 0, is_active: true, active_from: "", active_to: "",
};

export function PromoEditForm({
  initial,
  onSave,
  onCancel,
  isSaving,
}: {
  initial?: PromoBlock | null;
  onSave: (data: PromoFormData) => void;
  onCancel: () => void;
  isSaving: boolean;
}) {
  const [form, setForm] = React.useState<PromoFormData>(() =>
    initial ? {
      title: initial.title,
      body: initial.body ?? "",
      button_text: initial.button_text ?? "",
      button_url: initial.button_url ?? "",
      action_type_code: initial.action_type_code ?? "",
      audience_code: initial.audience_code,
      style_code: initial.style_code,
      sort_order: initial.sort_order,
      is_active: initial.is_active,
      active_from: initial.active_from?.slice(0, 10) ?? "",
      active_to: initial.active_to?.slice(0, 10) ?? "",
    } : EMPTY_FORM
  );
  const set = (key: keyof PromoFormData, value: string | number | boolean) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const theme = STYLE_THEMES[form.style_code] ?? STYLE_THEMES.DEFAULT;

  return (
    <div className={styles.editForm}>
      <div className={styles.editPreview}>
        <div className={styles.card}
          style={{ background: theme.bg, borderColor: theme.border, color: theme.accent }}
        >
          <strong className={styles.cardTitle} style={{ color: theme.accent }}>
            {form.title || "Заголовок блока"}
          </strong>
          {form.body && <p className={styles.cardText} style={{ color: form.style_code === "PROMO" ? "rgba(255,255,255,0.85)" : "#44516b" }}>{form.body}</p>}
          {form.button_text && (
            <button type="button" className={styles.cardBtn}
              style={{ background: theme.btnBg, color: theme.btnText }}
            >
              {form.button_text}
            </button>
          )}
        </div>
        <small className={styles.previewHint}>Предпросмотр</small>
      </div>

      <div className={styles.editFields}>
        <label>Заголовок *
          <input value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="Заголовок блока" />
        </label>
        <label>Текст
          <textarea rows={3} value={form.body} onChange={(e) => set("body", e.target.value)} placeholder="Описание или анонс" />
        </label>
        <label>Текст кнопки
          <input value={form.button_text} onChange={(e) => set("button_text", e.target.value)} placeholder="Например: Подробнее" />
        </label>
        <label>Ссылка кнопки
          <input type="url" value={form.button_url} onChange={(e) => set("button_url", e.target.value)} placeholder="https://..." />
        </label>
        <div className={styles.editRow}>
          <label>Стиль
            <select value={form.style_code} onChange={(e) => set("style_code", e.target.value)}>
              <option value="DEFAULT">Обычный</option>
              <option value="INFO">Информация</option>
              <option value="SUCCESS">Успех</option>
              <option value="WARNING">Предупреждение</option>
              <option value="PROMO">Промо (тёмный)</option>
              <option value="DANGER">Важно</option>
            </select>
          </label>
          <label>Аудитория
            <select value={form.audience_code} onChange={(e) => set("audience_code", e.target.value)}>
              <option value="ALL">Все</option>
              <option value="NEW_USER">Новые пользователи</option>
              <option value="CANDIDATE">Кандидаты</option>
              <option value="PARTICIPANT">Участники</option>
              <option value="COMMANDER">Командиры</option>
              <option value="ADMIN">Администраторы</option>
            </select>
          </label>
        </div>
        <div className={styles.editRow}>
          <label>Действие кнопки
            <select value={form.action_type_code} onChange={(e) => set("action_type_code", e.target.value)}>
              <option value="">Только ссылка (URL)</option>
              <option value="OPEN_SCHEDULE">Открыть расписание</option>
              <option value="OPEN_NORMATIVE">Открыть нормативы</option>
              <option value="OPEN_COURSE">Открыть материалы</option>
              <option value="OPEN_FORM">Открыть обращения</option>
              <option value="SEND_BOT_MESSAGE">Написать боту</option>
            </select>
          </label>
          <label>Порядок
            <input type="number" min={0} value={form.sort_order}
              onChange={(e) => set("sort_order", parseInt(e.target.value) || 0)} />
          </label>
        </div>
        <div className={styles.editRow}>
          <label>Активен с
            <input type="date" value={form.active_from} onChange={(e) => set("active_from", e.target.value)} />
          </label>
          <label>Активен до
            <input type="date" value={form.active_to} onChange={(e) => set("active_to", e.target.value)} />
          </label>
        </div>
        <label className={styles.checkboxField}>
          <input type="checkbox" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />
          Показывать блок прямо сейчас
        </label>
        <div className={styles.editButtons}>
          <button type="button" disabled={!form.title.trim() || isSaving} onClick={() => onSave(form)} className={styles.editSaveBtn}>
            {isSaving ? "Сохраняем..." : initial ? "Сохранить изменения" : "Создать блок"}
          </button>
          <button type="button" onClick={onCancel} className={styles.editCancelBtn}>Отмена</button>
        </div>
      </div>
    </div>
  );
}

// Need React import for useState in PromoEditForm
import React from "react";
