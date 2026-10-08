import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight, Pause, Play, Sparkles } from "lucide-react";
import type { PromoBlock } from "../types/api";
import { openPromoAction } from "./PromoCard";
import styles from "./PromoCarousel.module.scss";

export function PromoCarousel({ blocks, navigate }: { blocks: PromoBlock[]; navigate: (section: string) => void }) {
  const slides = useMemo(() => blocks.filter((block) => block.is_active).sort((a, b) => a.sort_order - b.sort_order), [blocks]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [touching, setTouching] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const suppressClick = useRef(false);
  const index = Math.max(0, slides.findIndex((slide) => slide.id === selectedId));
  const current = slides[index];
  const multiple = slides.length > 1;
  const stopped = paused || hovered || focused || touching || reducedMotion;
  const goTo = (next: number) => setSelectedId(slides[(next + slides.length) % slides.length].id);
  const select = (next: number) => { setPaused(true); goTo(next); };

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReducedMotion(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);

  useEffect(() => {
    if (!multiple || stopped) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setSelectedId(slides[(index + 1) % slides.length].id);
    }, 6500);
    return () => window.clearInterval(timer);
  }, [index, slides, multiple, stopped]);

  if (!current) return null;

  return (
    <section
      className={styles.carousel}
      aria-label="Промо клуба"
      aria-roledescription={multiple ? "карусель" : undefined}
      data-style={current.style_code}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false); }}
      onTouchStart={(event) => {
        const touch = event.touches[0];
        touchStart.current = { x: touch.clientX, y: touch.clientY };
        suppressClick.current = false;
        setTouching(true);
      }}
      onTouchCancel={() => { touchStart.current = null; setTouching(false); }}
      onTouchEnd={(event) => {
        const start = touchStart.current;
        touchStart.current = null;
        setTouching(false);
        if (!start || !multiple) return;
        const touch = event.changedTouches[0];
        const dx = start.x - touch.clientX, dy = start.y - touch.clientY;
        if (Math.abs(dx) > 42 && Math.abs(dx) > Math.abs(dy)) {
          suppressClick.current = true;
          window.setTimeout(() => { suppressClick.current = false; }, 450);
          select(index + (dx > 0 ? 1 : -1));
        }
      }}
      onClickCapture={(event) => {
        if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; }
      }}
    >
      <div className={styles.eyebrow}><Sparkles aria-hidden="true" /> Промо клуба</div>
      <div aria-live={stopped ? "polite" : "off"} aria-atomic="true">
        <article key={current.id} className={styles.slide} aria-roledescription={multiple ? "слайд" : undefined} aria-label={multiple ? `${index + 1} из ${slides.length}` : undefined}>
          <h2>{current.title}</h2>
          {current.body && <p>{current.body}</p>}
          {(current.button_url || current.action_type_code) && (
            <button className={styles.action} type="button" onClick={() => openPromoAction(current, navigate)}>
              {current.button_text || "Подробнее"}<ArrowUpRight aria-hidden="true" />
            </button>
          )}
        </article>
      </div>
      {multiple && (
        <div className={styles.controls}>
          <div className={styles.pages} aria-label="Выбор промо">
            {slides.length <= 3 ? slides.map((slide, i) => (
              <button key={slide.id} type="button" className={styles.dot} aria-label={`Промо ${i + 1}`} aria-current={i === index ? "true" : undefined} onClick={() => select(i)} />
            )) : <span className={styles.counter}>{index + 1} / {slides.length}</span>}
          </div>
          <div className={styles.arrows}>
            {!reducedMotion && <button type="button" aria-label={paused ? "Включить автопереключение промо" : "Приостановить промо"} onClick={() => setPaused((value) => !value)}>{paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}</button>}
            <button type="button" aria-label="Предыдущее промо" onClick={() => select(index - 1)}><ChevronLeft aria-hidden="true" /></button>
            <button type="button" aria-label="Следующее промо" onClick={() => select(index + 1)}><ChevronRight aria-hidden="true" /></button>
          </div>
        </div>
      )}
    </section>
  );
}
