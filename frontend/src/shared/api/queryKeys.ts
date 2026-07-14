export const queryKeys = {
  identity: {
    session: ["auth", "session"] as const,
    twoFactorStatus: ["auth", "2fa", "status"] as const,
    passwordStatus: ["auth", "password", "status"] as const,
    vkStatus: ["auth", "vk", "status"] as const,
    webPushKey: ["web-push", "public-key"] as const,
  },
  dashboard: {
    root: ["dashboard"] as const,
    actionItems: ["dashboard", "action-items"] as const,
    bootstrap: ["dashboard", "bootstrap"] as const,
  },
  attendance: {
    root: ["attendance"] as const,
    mine: (limit: number, offset: number) => ["attendance", "my", limit, offset] as const,
    myStats: ["attendance", "stats", "my"] as const,
    fullStats: ["attendance", "stats", "full"] as const,
    streak: ["attendance", "streak"] as const,
    event: (eventId: number | null, limit: number, offset: number) => (
      ["attendance", "event", eventId, limit, offset] as const
    ),
  },
  notifications: {
    root: ["notifications"] as const,
    preferences: ["me", "notification-preferences"] as const,
  },
  normatives: { root: ["normatives"] as const },
  appeals: { root: ["appeals"] as const },
  search: (value: string) => ["search", value] as const,
  progress: ["progress", "me"] as const,
  admin: {
    users: ["admin", "users"] as const,
    audit: ["admin", "audit"] as const,
  },
} as const;
