export function DraftStatus({ ready, saving, restored, saved, mode }: {
  ready: boolean; saving: boolean; restored: boolean; saved: boolean; mode: "persistent" | "memory";
}) {
  const text = !ready ? "Восстанавливаем черновик…" : mode === "memory"
    ? "Черновик хранится только до закрытия вкладки: постоянное хранилище недоступно."
    : saving ? "Сохраняем черновик…" : saved ? "Черновик сохранён на этом устройстве"
    : restored ? "Черновик восстановлен" : "Введённые данные сохраняются на этом устройстве";
  return <p role="status" aria-live="polite" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{text}</p>;
}
