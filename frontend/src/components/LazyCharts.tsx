import { lazy, Suspense } from "react";
import type { BarDatum } from "./Charts";

type AttendanceDonutProps = { present: number; absent: number; late: number; total: number };
type BarChartProps = { data: BarDatum[]; height?: number; barColor?: string; showValues?: boolean };
type CalendarHeatmapProps = { records: Array<{ date: string; status: string }> };
type AnimatedProgressProps = {
  value: number;
  max?: number;
  color?: string;
  label?: string;
  showPercent?: boolean;
  height?: number;
};
type GradeDistributionProps = { grades: Record<string, number> };

const LazyAttendanceDonut = lazy(async () => ({ default: (await import("./Charts")).AttendanceDonut }));
const LazyBarChart = lazy(async () => ({ default: (await import("./Charts")).BarChart }));
const LazyCalendarHeatmap = lazy(async () => ({ default: (await import("./Charts")).CalendarHeatmap }));
const LazyAnimatedProgress = lazy(async () => ({ default: (await import("./Charts")).AnimatedProgress }));
const LazyGradeDistribution = lazy(async () => ({ default: (await import("./Charts")).GradeDistribution }));

export function AttendanceDonut(props: AttendanceDonutProps) {
  return (
    <Suspense fallback={null}>
      <LazyAttendanceDonut {...props} />
    </Suspense>
  );
}

export function BarChart(props: BarChartProps) {
  return (
    <Suspense fallback={null}>
      <LazyBarChart {...props} />
    </Suspense>
  );
}

export function CalendarHeatmap(props: CalendarHeatmapProps) {
  return (
    <Suspense fallback={null}>
      <LazyCalendarHeatmap {...props} />
    </Suspense>
  );
}

export function AnimatedProgress(props: AnimatedProgressProps) {
  return (
    <Suspense fallback={null}>
      <LazyAnimatedProgress {...props} />
    </Suspense>
  );
}

export function GradeDistribution(props: GradeDistributionProps) {
  return (
    <Suspense fallback={null}>
      <LazyGradeDistribution {...props} />
    </Suspense>
  );
}
