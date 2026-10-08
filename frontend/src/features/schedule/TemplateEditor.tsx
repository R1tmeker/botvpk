import { useRef, useState } from "react";
import {
  useCreateScheduleTemplate, useDeleteScheduleTemplate, useGenerateScheduleTemplate,
  usePreviewScheduleTemplate, useScheduleTemplates, useUpdateScheduleTemplate,
  type ScheduleTemplatePayload,
} from "../../api/queries";
import { toast } from "../../components/Toast";
import type { ScheduleTemplate, Squad } from "../../types/api";
import { getAppTimezone } from "../../utils/format";
import styles from "../../screens/App.module.scss";

const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const fullDays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
const emptyForm = () => ({ title: "", description: "", days: [] as number[], week_parity: "", start_time: "16:00", end_time: "", place: "", squad_id: "", valid_from: "", valid_to: "", requires_response: true, deadline: "" });

function errorText(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "Не удалось сохранить расписание. Проверьте поля и повторите.";
}

function readableDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", weekday: "short", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`));
}

export function TemplateEditor({ squads }: { squads: Squad[] }) {
  const templates = useScheduleTemplates(true);
  const create = useCreateScheduleTemplate();
  const update = useUpdateScheduleTemplate();
  const remove = useDeleteScheduleTemplate();
  const generate = useGenerateScheduleTemplate();
  const preview = usePreviewScheduleTemplate();
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState<ScheduleTemplate | null>(null);
  const [horizon, setHorizon] = useState(60);
  const [applyFuture, setApplyFuture] = useState(true);
  const [dates, setDates] = useState<string[] | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const editor = useRef<HTMLDivElement>(null);
  const titleInput = useRef<HTMLInputElement>(null);
  const patch = (values: Partial<typeof form>) => { setForm((previous) => ({ ...previous, ...values })); setDates(null); setNotice(""); };
  const payload: ScheduleTemplatePayload = {
    title: form.title.trim(), description: form.description.trim() || null,
    week_days: [...form.days].sort((a, b) => a - b).join(","),
    week_parity: form.week_parity ? form.week_parity as "A" | "B" : null,
    start_time: form.start_time, end_time: form.end_time || null, place: form.place.trim() || null,
    squad_id: form.squad_id ? Number(form.squad_id) : null,
    valid_from: form.valid_from || null, valid_to: form.valid_to || null,
    requires_response: form.requires_response,
    response_deadline_minutes: form.requires_response && form.deadline !== "" ? Number(form.deadline) : null,
  };
  const valid = !!payload.title && form.days.length > 0 && !!form.start_time
    && (!form.end_time || form.end_time > form.start_time)
    && (!form.valid_from || !form.valid_to || form.valid_to >= form.valid_from)
    && (form.deadline === "" || (Number.isInteger(Number(form.deadline)) && Number(form.deadline) >= 0 && Number(form.deadline) <= 43200));
  const reset = () => { setForm(emptyForm()); setEditing(null); setDates(null); setApplyFuture(true); };

  const save = async () => {
    if (lock.current || !valid) return;
    lock.current = true; setBusy(true); setNotice("");
    try {
      const result = editing
        ? await update.mutateAsync({ ...payload, id: editing.id, days: horizon, apply_to_future: applyFuture })
        : await create.mutateAsync({ ...payload, generate_days: horizon });
      const summary = result.sync_summary;
      const message = summary
        ? `Сохранено. Занятий создано: ${summary.created}, обновлено: ${summary.updated}, отменено: ${summary.cancelled}.${summary.preserved ? ` Сохранено без изменений: ${summary.preserved} — проверьте их отдельно.` : ""}`
        : "Шаблон сохранён. Уже созданные занятия не изменены.";
      reset(); setNotice(message); toast(message, summary?.preserved ? "warning" : "success");
    } catch (error) { setNotice(errorText(error)); toast(errorText(error), "error"); }
    finally { lock.current = false; setBusy(false); }
  };

  const edit = (template: ScheduleTemplate) => {
    setEditing(template); setDates(null); setNotice(""); setApplyFuture(true);
    setForm({ title: template.title, description: template.description ?? "", days: template.week_days.split(",").map(Number),
      week_parity: template.week_parity ?? "", start_time: template.start_time.slice(0, 5), end_time: template.end_time?.slice(0, 5) ?? "",
      place: template.place ?? "", squad_id: template.squad_id?.toString() ?? "", valid_from: template.valid_from ?? "", valid_to: template.valid_to ?? "",
      requires_response: template.requires_response, deadline: template.response_deadline_minutes?.toString() ?? "" });
    editor.current?.scrollIntoView({ behavior: "smooth", block: "start" }); titleInput.current?.focus({ preventScroll: true });
  };

  return <>
    <div className={styles.formBlock} ref={editor}>
      <strong className={styles.formTitle}>{editing ? `Редактирование: ${editing.title}` : "Регулярные занятия"}</strong>
      <p className={styles.templateHint}>Выберите дни и время, проверьте даты и создайте занятия. Время клуба: {getAppTimezone()}.</p>
      <fieldset className={styles.templateFields} disabled={busy || preview.isPending}>
        <label className={styles.fieldLabel}><span>Название шаблона *</span><input ref={titleInput} maxLength={255} placeholder="Например, строевая подготовка" value={form.title} onChange={(e) => patch({ title: e.target.value })} /></label>
        <fieldset className={styles.templateDays}><legend>Дни занятий *</legend>
          <div className={styles.weekdayGrid}>{weekdays.map((day, index) => <button type="button" key={day} aria-label={fullDays[index]} aria-pressed={form.days.includes(index + 1)} onClick={() => patch({ days: form.days.includes(index + 1) ? form.days.filter((value) => value !== index + 1) : [...form.days, index + 1] })}>{day}</button>)}</div>
        </fieldset>
        {!form.days.length && <p className={styles.templateHint}>Нажмите на дни, в которые проходят занятия. Можно выбрать несколько.</p>}
        <div className={styles.twoCol}>
          <label className={styles.fieldLabel}><span>Начало занятия *</span><input type="time" value={form.start_time} onChange={(e) => patch({ start_time: e.target.value })} /></label>
          <label className={styles.fieldLabel}><span>Конец занятия</span><input type="time" value={form.end_time} onChange={(e) => patch({ end_time: e.target.value })} /></label>
        </div>
        {form.end_time && form.end_time <= form.start_time && <p role="alert">Конец занятия должен быть позже начала.</p>}
        <label className={styles.fieldLabel}><span>Повторять</span><select value={form.week_parity} onChange={(e) => patch({ week_parity: e.target.value })}><option value="">Каждую неделю</option><option value="A">Через неделю · неделя 1</option><option value="B">Через неделю · неделя 2</option></select></label>
        {form.week_parity && <p className={styles.templateHint}>Чередование считается от даты начала недели 1 в настройках клуба.</p>}
        <label className={styles.fieldLabel}><span>Место занятия</span><input maxLength={255} value={form.place} onChange={(e) => patch({ place: e.target.value })} /></label>
        <label className={styles.fieldLabel}><span>Участники</span><select value={form.squad_id} onChange={(e) => patch({ squad_id: e.target.value })}><option value="">Все отделения</option>{squads.map((squad) => <option key={squad.id} value={squad.id}>{squad.name}</option>)}</select></label>
        <div className={styles.twoCol}>
          <label className={styles.fieldLabel}><span>Действует с</span><input type="date" value={form.valid_from} onChange={(e) => patch({ valid_from: e.target.value })} /></label>
          <label className={styles.fieldLabel}><span>Действует до</span><input type="date" min={form.valid_from || undefined} value={form.valid_to} onChange={(e) => patch({ valid_to: e.target.value })} /></label>
        </div>
        <label className={styles.fieldLabel}><span>Создать занятия на ближайшие</span><select value={horizon} onChange={(e) => { setHorizon(Number(e.target.value)); setDates(null); }}>
          {[30, 60, 90, 180, 365].map((days) => <option value={days} key={days}>{days} дней</option>)}
        </select></label>
        <p className={styles.templateHint}>Если даты периода не указаны, начинаем с сегодня. Прошедшие занятия и дубли не создаются.</p>
        <details><summary>Описание и ответы участников</summary>
          <label className={styles.fieldLabel}><span>Описание занятия</span><textarea rows={3} value={form.description} onChange={(e) => patch({ description: e.target.value })} /></label>
          <label className={styles.checkboxLine}><input type="checkbox" checked={form.requires_response} onChange={(e) => patch({ requires_response: e.target.checked })} /><span>Участники отвечают «Иду / Не иду»</span></label>
          {form.requires_response && <label className={styles.fieldLabel}><span>Закрыть ответы за минут до начала</span><input type="number" min={0} max={43200} step={1} placeholder="До начала занятия" value={form.deadline} onChange={(e) => patch({ deadline: e.target.value })} /></label>}
        </details>
        {editing && <><label className={styles.checkboxLine}><input type="checkbox" checked={applyFuture} onChange={(e) => setApplyFuture(e.target.checked)} /><span>Применить к занятиям на ближайшие {horizon} дней</span></label><p className={styles.templateHint}>Занятия с ответами, явкой или ручными правками сохранятся. Остальные обновятся, лишние даты отменятся.</p></>}
        <button type="button" className={styles.secondaryButton} disabled={!valid} onClick={async () => {
          setNotice(""); setDates(null);
          try { const result = await preview.mutateAsync({ ...payload, days: horizon }); setDates(result.dates); }
          catch (error) { setNotice(errorText(error)); }
        }}>{preview.isPending ? "Проверяем даты…" : "Показать даты занятий"}</button>
        {dates !== null && <div className={styles.templatePreview} aria-live="polite">
          <strong>По шаблону: {dates.length} занятий</strong>
          {dates.length ? <><ul>{dates.slice(0, 8).map((day) => <li key={day}>{readableDate(day)} · {form.start_time}{form.end_time ? `–${form.end_time}` : ""}</li>)}</ul>{dates.length > 8 && <span>И ещё {dates.length - 8} по выбранным дням.</span>}</> : <p>Нет подходящих дат в ближайшие {horizon} дней. Проверьте период и дни недели.</p>}
        </div>}
        <button type="button" className={styles.primaryButton} disabled={!valid || ((!editing || applyFuture) && !dates?.length)} onClick={save}>{busy ? "Сохраняем…" : editing ? "Сохранить изменения" : "Создать шаблон и занятия"}</button>
        {editing && <button type="button" className={styles.secondaryButton} onClick={() => { reset(); setNotice(""); }}>Отменить редактирование</button>}
      </fieldset>
      {notice && <p role="status">{notice}</p>}
    </div>
    <div className={styles.list} aria-label="Шаблоны расписания">
      {templates.isPending && <p>Загружаем шаблоны…</p>}
      {templates.isError && <button type="button" onClick={() => templates.refetch()}>Не удалось загрузить. Повторить</button>}
      {templates.data?.length === 0 && <p>Шаблонов пока нет.</p>}
      {templates.data?.map((template) => <article className={styles.templateCard} key={template.id}>
        <strong>{template.title}</strong>
        <span>{template.week_days.split(",").map((day) => weekdays[Number(day) - 1]).join(", ")} · {template.start_time.slice(0, 5)}{template.end_time ? `–${template.end_time.slice(0, 5)}` : ""}</span>
        <span>{template.week_parity === "A" ? "Неделя 1" : template.week_parity === "B" ? "Неделя 2" : "Каждую неделю"}{template.place ? ` · ${template.place}` : ""}</span>
        <div className={styles.commandStrip}>
          <button type="button" disabled={busy || preview.isPending} onClick={() => edit(template)}>Редактировать шаблон</button>
          <button type="button" className={styles.secondaryButton} disabled={busy || generate.isPending} onClick={() => generate.mutate({ id: template.id, days: horizon }, {
            onSuccess: (created) => toast(created.length ? `Добавлено занятий: ${created.length}` : "Все подходящие занятия уже созданы.", created.length ? "success" : "info"),
            onError: (error) => toast(errorText(error), "error"),
          })}>Добавить занятия на {horizon} дней</button>
          <button type="button" className={styles.btnNotComing} disabled={busy || remove.isPending} onClick={() => {
            if (!window.confirm(`Архивировать шаблон «${template.title}»? Все будущие занятия по нему будут отменены. История и ответы сохранятся.`)) return;
            remove.mutate(template.id, { onSuccess: () => { if (editing?.id === template.id) reset(); toast("Шаблон в архиве, будущие занятия отменены", "warning"); }, onError: (error) => toast(errorText(error), "error") });
          }}>В архив</button>
        </div>
      </article>)}
    </div>
  </>;
}
