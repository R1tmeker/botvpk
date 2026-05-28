import { useEffect, useRef, useState } from "react";
import styles from "./Charts.module.scss";

/* ─────────────── useCountUp ─────────────────── */
export function useCountUp(target: number, duration = 900, enabled = true): number {
  const [value, setValue] = useState(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!enabled) return;
    const start = performance.now();
    const animate = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(eased * target));
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration, enabled]);

  return value;
}

/* ─────────────── DonutChart ─────────────────── */
type DonutSegment = { value: number; color: string; label?: string };

export function DonutChart({
  segments,
  size = 120,
  strokeWidth = 14,
  label,
  sublabel,
}: {
  segments: DonutSegment[];
  size?: number;
  strokeWidth?: number;
  label?: string | number;
  sublabel?: string;
}) {
  const [animated, setAnimated] = useState(false);
  useEffect(() => { const t = setTimeout(() => setAnimated(true), 50); return () => clearTimeout(t); }, []);

  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const cx = size / 2;
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;

  let offset = 0;
  const arcs = segments.map((seg) => {
    const fraction = seg.value / total;
    const dash = fraction * circumference;
    const gap = circumference - dash;
    const startOffset = circumference - offset * circumference / total;
    offset += seg.value;
    return { ...seg, dash, gap, startOffset };
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={styles.donut}>
      {/* background track */}
      <circle cx={cx} cy={cx} r={r} fill="none" stroke="#e8ecf0" strokeWidth={strokeWidth} />
      {arcs.map((arc, i) => (
        <circle
          key={i}
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke={arc.color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${animated ? arc.dash : 0} ${circumference}`}
          strokeDashoffset={arc.startOffset}
          strokeLinecap="round"
          className={styles.donutArc}
          style={{ transition: `stroke-dasharray 0.9s cubic-bezier(0.4,0,0.2,1) ${i * 0.1}s` }}
        />
      ))}
      {label !== undefined && (
        <text x={cx} y={cx - (sublabel ? 8 : 0)} textAnchor="middle" dominantBaseline="middle" className={styles.donutLabel}>
          {label}
        </text>
      )}
      {sublabel && (
        <text x={cx} y={cx + 14} textAnchor="middle" dominantBaseline="middle" className={styles.donutSublabel}>
          {sublabel}
        </text>
      )}
    </svg>
  );
}

/* ─────────────── DonutWithStats ─────────────── */
export function AttendanceDonut({ present, absent, late, total }: { present: number; absent: number; late: number; total: number }) {
  const pct = total ? Math.round((present / total) * 100) : 0;
  const animPct = useCountUp(pct, 1000);
  return (
    <div className={styles.donutRow}>
      <DonutChart
        size={110}
        strokeWidth={12}
        segments={[
          { value: present, color: "#27ae60", label: "Присутствовал" },
          { value: late, color: "#f39c12", label: "Опоздал" },
          { value: absent, color: "#e74c3c", label: "Отсутствовал" },
          { value: Math.max(0, total - present - late - absent), color: "#e8ecf0", label: "Не отмечен" },
        ]}
        label={`${animPct}%`}
        sublabel="явка"
      />
      <div className={styles.donutLegend}>
        <LegendItem color="#27ae60" label="Присутствовал" value={present} />
        <LegendItem color="#f39c12" label="Опоздал" value={late} />
        <LegendItem color="#e74c3c" label="Отсутствовал" value={absent} />
      </div>
    </div>
  );
}

function LegendItem({ color, label, value }: { color: string; label: string; value: number }) {
  const v = useCountUp(value, 800);
  return (
    <div className={styles.legendItem}>
      <span className={styles.legendDot} style={{ background: color }} />
      <span>{label}</span>
      <strong>{v}</strong>
    </div>
  );
}

/* ─────────────── BarChart ───────────────────── */
export type BarDatum = { label: string; value: number; color?: string };

export function BarChart({
  data,
  height = 120,
  barColor = "#1a2f5a",
  showValues = true,
}: {
  data: BarDatum[];
  height?: number;
  barColor?: string;
  showValues?: boolean;
}) {
  const [animated, setAnimated] = useState(false);
  useEffect(() => { const t = setTimeout(() => setAnimated(true), 80); return () => clearTimeout(t); }, []);

  const max = Math.max(...data.map((d) => d.value), 1);
  const barW = 28;
  const gap = 10;
  const chartH = height - 32;
  const width = data.length * (barW + gap) - gap + 20;

  return (
    <div className={styles.barWrap}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {data.map((d, i) => {
          const barH = animated ? Math.max(4, (d.value / max) * chartH) : 4;
          const x = i * (barW + gap) + 10;
          const y = chartH - barH;
          const color = d.color ?? barColor;
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={barH}
                rx={5}
                fill={color}
                className={styles.bar}
                style={{ transition: `y 0.7s cubic-bezier(0.4,0,0.2,1) ${i * 0.06}s, height 0.7s cubic-bezier(0.4,0,0.2,1) ${i * 0.06}s` }}
              />
              {showValues && d.value > 0 && (
                <text x={x + barW / 2} y={y - 4} textAnchor="middle" className={styles.barValue}>
                  {d.value}
                </text>
              )}
              <text x={x + barW / 2} y={height - 4} textAnchor="middle" className={styles.barLabel}>
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ─────────────── CalendarHeatmap ────────────── */
export function CalendarHeatmap({ records }: { records: Array<{ date: string; status: string }> }) {
  const today = new Date();
  const weeks = 13; // ~3 months

  // Build date map
  const byDate = new Map<string, string>();
  for (const r of records) {
    const d = r.date.slice(0, 10);
    byDate.set(d, r.status);
  }

  const statusColor = (s: string | undefined) => {
    if (!s) return "#e8ecf0";
    if (s === "PRESENT") return "#27ae60";
    if (s === "LATE") return "#f39c12";
    if (s === "ABSENT") return "#e74c3c";
    if (s === "EXCUSED" || s === "SICK") return "#3498db";
    return "#e8ecf0";
  };

  // Build grid: columns = weeks, rows = weekdays Mon–Sun
  const cells: Array<{ date: Date; dateStr: string }[]> = [];
  const start = new Date(today);
  start.setDate(today.getDate() - (weeks * 7 - 1));
  // align to Monday
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));

  for (let w = 0; w < weeks; w++) {
    const col: Array<{ date: Date; dateStr: string }> = [];
    for (let d = 0; d < 7; d++) {
      const dt = new Date(start);
      dt.setDate(start.getDate() + w * 7 + d);
      col.push({ date: dt, dateStr: dt.toISOString().slice(0, 10) });
    }
    cells.push(col);
  }

  const DAY_SIZE = 14;
  const GAP = 3;
  const step = DAY_SIZE + GAP;

  return (
    <div className={styles.heatmapWrap}>
      <div className={styles.heatmapTitle}>Посещаемость за 3 месяца</div>
      <svg
        width={weeks * step}
        height={7 * step}
        viewBox={`0 0 ${weeks * step} ${7 * step}`}
      >
        {cells.map((col, wi) =>
          col.map((cell, di) => {
            const isFuture = cell.date > today;
            const color = isFuture ? "transparent" : statusColor(byDate.get(cell.dateStr));
            return (
              <rect
                key={`${wi}-${di}`}
                x={wi * step}
                y={di * step}
                width={DAY_SIZE}
                height={DAY_SIZE}
                rx={3}
                fill={color}
                className={isFuture ? "" : styles.heatCell}
              >
                <title>{cell.dateStr}: {byDate.get(cell.dateStr) ?? "нет данных"}</title>
              </rect>
            );
          })
        )}
      </svg>
      <div className={styles.heatmapLegend}>
        <span><span className={styles.legendDot} style={{ background: "#27ae60" }} /> Присутствовал</span>
        <span><span className={styles.legendDot} style={{ background: "#f39c12" }} /> Опоздал</span>
        <span><span className={styles.legendDot} style={{ background: "#e74c3c" }} /> Отсутствовал</span>
        <span><span className={styles.legendDot} style={{ background: "#3498db" }} /> Уважит.</span>
      </div>
    </div>
  );
}

/* ─────────────── AnimatedProgress ──────────── */
export function AnimatedProgress({
  value,
  max = 100,
  color = "#27ae60",
  label,
  showPercent = true,
  height = 8,
}: {
  value: number;
  max?: number;
  color?: string;
  label?: string;
  showPercent?: boolean;
  height?: number;
}) {
  const [width, setWidth] = useState(0);
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const animPct = useCountUp(Math.round(pct), 900);

  useEffect(() => {
    const t = setTimeout(() => setWidth(pct), 80);
    return () => clearTimeout(t);
  }, [pct]);

  return (
    <div className={styles.progress}>
      {label && (
        <div className={styles.progressHeader}>
          <span>{label}</span>
          {showPercent && <strong style={{ color }}>{animPct}%</strong>}
        </div>
      )}
      <div className={styles.progressTrack} style={{ height }}>
        <div
          className={styles.progressFill}
          style={{
            width: `${width}%`,
            background: color,
            height,
            transition: "width 0.9s cubic-bezier(0.4,0,0.2,1)",
          }}
        />
      </div>
    </div>
  );
}

/* ─────────────── GradeDonut ─────────────────── */
export function GradeDistribution({ grades }: { grades: Record<string, number> }) {
  const colorMap: Record<string, string> = {
    "5": "#27ae60",
    "4": "#2ecc71",
    "3": "#f39c12",
    "2": "#e74c3c",
    "1": "#c0392b",
    PASS: "#3498db",
    FAIL: "#e74c3c",
  };
  const total = Object.values(grades).reduce((s, v) => s + v, 0) || 1;
  const avg = Object.entries(grades)
    .filter(([k]) => ["1","2","3","4","5"].includes(k))
    .reduce((s, [k, v]) => s + parseInt(k) * v, 0) /
    (Object.entries(grades).filter(([k]) => ["1","2","3","4","5"].includes(k)).reduce((s, [, v]) => s + v, 0) || 1);
  const animAvg = useCountUp(Math.round(avg * 10), 900);

  return (
    <div className={styles.donutRow}>
      <DonutChart
        size={110}
        strokeWidth={12}
        segments={Object.entries(grades).map(([k, v]) => ({ value: v, color: colorMap[k] ?? "#95a5a6" }))}
        label={isNaN(avg) || avg === 0 ? "—" : (animAvg / 10).toFixed(1)}
        sublabel="средний балл"
      />
      <div className={styles.donutLegend}>
        {Object.entries(grades).map(([k, v]) => (
          <LegendItem key={k} color={colorMap[k] ?? "#95a5a6"} label={k === "PASS" ? "Зачёт" : k === "FAIL" ? "Незачёт" : `Оценка ${k}`} value={v} />
        ))}
      </div>
    </div>
  );
}

/* ─────────────── StatNumber ─────────────────── */
export function StatNumber({ value, label, color = "#1a2f5a", suffix = "" }: { value: number; label: string; color?: string; suffix?: string }) {
  const anim = useCountUp(value, 900);
  return (
    <div className={styles.statNumber}>
      <strong style={{ color }}>{anim}{suffix}</strong>
      <span>{label}</span>
    </div>
  );
}
