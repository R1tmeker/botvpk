import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../shared/api/queryKeys";
import type { AuthResponse } from "../../types/api";

type TwoFactorStatus = { available: boolean; enabled: boolean };
type VkStatus = { linked: boolean; vk_id: number | null; bot_url: string | null };
type WebPushKeyResponse = { available: boolean; public_key: string | null };
type PasswordStatus = { has_password: boolean; password_set_at: string | null };

export function useTelegramAuth() {
  return useMutation({
    mutationFn: async (initData: string) => (await api.post<AuthResponse>("/auth/telegram", { init_data: initData })).data,
  });
}

export function usePasswordLogin() {
  return useMutation({
    mutationFn: async (payload: { telegram_id: number; password: string; totp_code?: string }) => (
      await api.post<AuthResponse>("/auth/password/login", payload)
    ).data,
  });
}

export function useSession() {
  return useQuery({
    queryKey: queryKeys.identity.session,
    queryFn: async () => (await api.get<AuthResponse>("/auth/session")).data,
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogout() {
  return useMutation({ mutationFn: async () => { await api.post("/auth/logout"); } });
}

export function useStepUp() {
  return useMutation({
    mutationFn: async (payload: { password?: string; totp_code?: string; init_data?: string }) => (
      await api.post<{ step_up: boolean }>("/auth/step-up", payload)
    ).data,
  });
}

export function useTwoFactorStatus(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.identity.twoFactorStatus,
    queryFn: async () => (await api.get<TwoFactorStatus>("/auth/2fa/status")).data,
    enabled,
  });
}

export function useTwoFactorSetup() {
  return useMutation({
    mutationFn: async () => (
      await api.post<{ secret: string; provisioning_uri: string }>("/auth/2fa/setup")
    ).data,
  });
}

export function useTwoFactorEnable() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => (await api.post<TwoFactorStatus>("/auth/2fa/enable", { code })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.identity.twoFactorStatus }),
  });
}

export function useTwoFactorDisable() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => (await api.post<TwoFactorStatus>("/auth/2fa/disable", { code })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.identity.twoFactorStatus }),
  });
}

export function usePasswordReset() {
  return useMutation({
    mutationFn: async (payload: { telegram_id: number; code: string; new_password: string }) => (
      await api.post<PasswordStatus>("/auth/password/reset", payload)
    ).data,
  });
}

export function usePasswordStatus(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.identity.passwordStatus,
    queryFn: async () => (await api.get<PasswordStatus>("/auth/password/status")).data,
    enabled,
  });
}

export function useSetPassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { new_password: string; current_password?: string }) => (
      await api.post<PasswordStatus>("/auth/password/set", payload)
    ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.identity.passwordStatus }),
  });
}

export function useDeletePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.delete<PasswordStatus>("/auth/password")).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.identity.passwordStatus }),
  });
}

export function useVkStatus(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.identity.vkStatus,
    queryFn: async () => (await api.get<VkStatus>("/auth/vk/status")).data,
    enabled,
  });
}

export function useVkLinkCode() {
  return useMutation({
    mutationFn: async () => (await api.post<{ code: string; expires_at: string }>("/auth/vk/link-code")).data,
  });
}

export function useVkUnlink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.delete<VkStatus>("/auth/vk/")).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.identity.vkStatus }),
  });
}

export function useWebPushPublicKey(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.identity.webPushKey,
    queryFn: async () => (await api.get<WebPushKeyResponse>("/web-push/public-key")).data,
    enabled,
  });
}

export function useWebPushSubscribe() {
  return useMutation({
    mutationFn: async (subscription: PushSubscriptionJSON) => (
      await api.post<{ subscribed: boolean }>("/web-push/subscriptions", subscription)
    ).data,
  });
}

export function useWebPushUnsubscribe() {
  return useMutation({
    mutationFn: async (endpoint: string) => (
      await api.delete<{ unsubscribed: boolean }>("/web-push/subscriptions", { data: { endpoint } })
    ).data,
  });
}
