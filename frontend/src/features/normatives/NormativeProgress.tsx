import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { normativeStatusLabels, type NormativeMemberProgress } from "./model";
import styles from "./NormativeProgress.module.scss";

export function NormativeProgress({ canReview }: { canReview: boolean }) {
  const [view, setView] = useState<"mine" | "roster">("mine");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const mine = useQuery({ queryKey: ["normatives", "progress", "my"], queryFn: async () => (await api.get<NormativeMemberProgress>("/normatives/progress/my")).data, refetchInterval: 15_000, refetchIntervalInBackground: false });
  const roster = useQuery({ queryKey: ["normatives", "progress", "roster"], queryFn: async () => (await api.get<NormativeMemberProgress[]>("/normatives/progress/roster")).data, enabled: canReview && view === "roster", refetchInterval: 15_000, refetchIntervalInBackground: false });
  const own = mine.data?.user_id ? mine.data : null;
  const members = (Array.isArray(roster.data) ? roster.data : []).filter((member) => member.full_name.toLocaleLowerCase().includes(search.toLocaleLowerCase())
    && (filter === "all" || filter === "missing" && member.missing + member.redo > 0 || filter === "done" && member.total > 0 && member.accepted === member.total || filter === "pending" && member.pending > 0));
  const counters = (member: NormativeMemberProgress) => <div className={styles.counts}>
    <span><b>{member.accepted}</b> принято</span><span><b>{member.pending}</b> на проверке</span>
    <span><b>{member.redo}</b> пересдать</span><span><b>{member.missing}</b> не сдавал</span>
  </div>;
  return <section className={styles.panel} aria-label="Выполнение нормативов">
    <div className={styles.heading}><h3>Выполнение нормативов</h3><span>Текущие задания</span></div>
    {canReview && <div className={styles.tabs}><button type="button" aria-pressed={view === "mine"} onClick={() => setView("mine")}>Мой прогресс</button><button type="button" aria-pressed={view === "roster"} onClick={() => setView("roster")}>Состав</button></div>}
    {view === "mine" && (own ? <>
      <div className={styles.total}><strong>{own.accepted}<small> / {own.total}</small></strong><span>нормативов принято</span></div>
      <progress aria-label="Принятые нормативы" value={own.accepted} max={Math.max(1, own.total)} />
      {counters(own)}<p>За всё время принято сдач: {own.accepted_all_time}. Еженедельные задания обновляются в понедельник в 00:00 по Барнаулу.</p>
      <details className={styles.member}><summary><strong>Мои задания и результаты</strong></summary><ul className={styles.tasks}>{own.items.map((item) => <li key={item.normative_id}><Link to={`/normatives?id=${item.normative_id}`}>{item.title}</Link><b data-status={item.status}>{normativeStatusLabels[item.status] ?? item.status}</b></li>)}</ul></details>
    </> : <p>{mine.isPending ? "Загружаем прогресс…" : "Не удалось загрузить прогресс."} {!mine.isPending && <button type="button" onClick={() => void mine.refetch()}>Повторить</button>}</p>)}
    {view === "roster" && <>
      <div className={styles.filters}><input aria-label="Найти участника в прогрессе нормативов" placeholder="Найти по ФИО" value={search} onChange={(event) => setSearch(event.target.value)} /><select aria-label="Фильтр выполнения нормативов" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">Все участники</option><option value="missing">Есть несданные</option><option value="pending">На проверке</option><option value="done">Всё принято</option></select></div>
      {roster.isError && <p>Сводка недоступна. <button type="button" onClick={() => void roster.refetch()}>Повторить</button></p>}
      {roster.isPending && <p>Загружаем состав…</p>}
      {members.map((member) => <details className={styles.member} key={member.user_id}>
        <summary><strong>{member.full_name}</strong><span>{member.accepted} / {member.total} принято</span></summary>
        {counters(member)}<ul>{member.items.map((item) => <li key={item.normative_id}><span>{item.title}</span><b data-status={item.status}>{normativeStatusLabels[item.status] ?? item.status}</b></li>)}</ul>
        <p>За всё время принято сдач: {member.accepted_all_time}</p>
      </details>)}
      {!roster.isPending && !roster.isError && members.length === 0 && <p>По выбранному фильтру участников нет.</p>}
    </>}
  </section>;
}
