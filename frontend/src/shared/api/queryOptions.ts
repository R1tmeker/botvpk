export const liveQueryOptions = {
  refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 60_000 : false,
  refetchIntervalInBackground: false,
  refetchOnMount: true,
  refetchOnReconnect: true,
  refetchOnWindowFocus: true,
} as const;
