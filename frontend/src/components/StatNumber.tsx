import { useCountUp } from "./chartUtils";
import styles from "./Charts.module.scss";

export function StatNumber({
  value,
  label,
  color = "var(--text)",
  suffix = "",
}: {
  value: number;
  label: string;
  color?: string;
  suffix?: string;
}) {
  const anim = useCountUp(value, 900);
  return (
    <div className={styles.statNumber}>
      <strong style={{ color }}>
        {anim}
        {suffix}
      </strong>
      <span>{label}</span>
    </div>
  );
}
