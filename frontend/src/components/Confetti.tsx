import { useEffect, useRef } from "react";
import { Flame, Gem, Medal, PartyPopper, Star, Trophy, type LucideIcon } from "lucide-react";
import styles from "./Confetti.module.scss";

type Particle = {
  x: number; y: number;
  vx: number; vy: number;
  color: string;
  size: number;
  rotation: number;
  rotationSpeed: number;
  opacity: number;
  shape: "rect" | "circle";
};

const COLORS = ["#e74c3c", "#27ae60", "#3498db", "#f39c12", "#9b59b6", "#1abc9c", "#e74c3c", "#1a2f5a"];

function mkParticle(w: number): Particle {
  return {
    x: Math.random() * w,
    y: -10,
    vx: (Math.random() - 0.5) * 4,
    vy: Math.random() * 3 + 2,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    size: Math.random() * 8 + 4,
    rotation: Math.random() * 360,
    rotationSpeed: (Math.random() - 0.5) * 8,
    opacity: 1,
    shape: Math.random() > 0.5 ? "rect" : "circle",
  };
}

export function ConfettiCanvas({ duration = 3000 }: { duration?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const particles: Particle[] = Array.from({ length: 120 }, () => mkParticle(canvas.width));
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed = now - startTime;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.06; // gravity
        p.rotation += p.rotationSpeed;
        p.opacity = Math.max(0, 1 - elapsed / duration);

        ctx.save();
        ctx.globalAlpha = p.opacity;
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.fillStyle = p.color;
        if (p.shape === "rect") {
          ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
        } else {
          ctx.beginPath();
          ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }

      if (elapsed < duration) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [duration]);

  return <canvas ref={canvasRef} className={styles.canvas} />;
}

/* ── MilestoneToast — pop-up for streak milestones ── */
export function MilestoneToast({ streak, onDismiss }: { streak: number; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  const messages: Record<number, { Icon: LucideIcon; text: string }> = {
    5:  { Icon: Flame, text: "5 занятий подряд! Так держать!" },
    10: { Icon: Star, text: "10 занятий — ты молодец!" },
    15: { Icon: Trophy, text: "15 занятий без пропуска! Рекорд!" },
    20: { Icon: Medal, text: "20 подряд — легенда отделения!" },
    30: { Icon: Gem, text: "30 занятий подряд! Невероятно!" },
  };

  const msg = messages[streak] ?? { Icon: PartyPopper, text: `${streak} занятий подряд — новый рекорд!` };
  const Icon = msg.Icon;

  return (
    <button
      type="button"
      className={styles.milestone}
      onClick={onDismiss}
      aria-label={`Закрыть достижение: ${msg.text}`}
    >
      <ConfettiCanvas duration={3500} />
      <div className={styles.milestoneCard}>
        <span className={styles.milestoneIcon} aria-hidden="true">
          <Icon />
        </span>
        <strong>{msg.text}</strong>
        <span>Серия: {streak} занятий</span>
      </div>
    </button>
  );
}
