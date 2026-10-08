export function canUseOfflineCache(error: unknown): boolean {
  const value = error as { code?: string; name?: string; response?: { status?: number } } | null;
  if (value?.code === "ERR_CANCELED" || value?.name === "AbortError" || value?.name === "CanceledError") return false;
  const status = value?.response?.status;
  return status === undefined || status >= 500;
}
