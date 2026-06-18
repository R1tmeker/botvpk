import axios from "axios";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";

export const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 15000,
});

// Token persists in localStorage so website (password) sessions survive reloads.
// In the Telegram Mini App the token is refreshed from initData on every launch,
// so persistence there is harmless.
const TOKEN_KEY = "vpk_access_token";

let accessToken: string | null = null;
try {
  accessToken = localStorage.getItem(TOKEN_KEY);
} catch {
  accessToken = null;
}
if (accessToken) {
  api.defaults.headers.common.Authorization = `Bearer ${accessToken}`;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable — keep in-memory only */
    }
  } else {
    delete api.defaults.headers.common.Authorization;
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  }
}

export function getStoredToken(): string | null {
  return accessToken;
}

export function clearAccessToken() {
  setAccessToken(null);
}
