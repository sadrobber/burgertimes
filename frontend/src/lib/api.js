import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

if (!BACKEND_URL) {
  console.warn("REACT_APP_BACKEND_URL is not set");
}

export const API_BASE = `${BACKEND_URL}/api`;

export const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
});

const ADMIN_TOKEN_KEY = "bt_admin_token";

export const getAdminToken = () => localStorage.getItem(ADMIN_TOKEN_KEY);
export const setAdminToken = (t) => {
  if (t) localStorage.setItem(ADMIN_TOKEN_KEY, t);
  else localStorage.removeItem(ADMIN_TOKEN_KEY);
};
export const clearAdminToken = () => localStorage.removeItem(ADMIN_TOKEN_KEY);

export const adminClient = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
});

adminClient.interceptors.request.use((config) => {
  const t = getAdminToken();
  if (t) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${t}`;
  }
  return config;
});

adminClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      clearAdminToken();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/admin/login")) {
        window.location.href = "/admin/login";
      }
    }
    return Promise.reject(err);
  }
);

const KITCHEN_TOKEN_KEY = "bt_kitchen_token";

export const getKitchenToken = () => localStorage.getItem(KITCHEN_TOKEN_KEY);
export const setKitchenToken = (t) => {
  if (t) localStorage.setItem(KITCHEN_TOKEN_KEY, t);
  else localStorage.removeItem(KITCHEN_TOKEN_KEY);
};
export const clearKitchenToken = () => localStorage.removeItem(KITCHEN_TOKEN_KEY);

export const kitchenClient = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
});

kitchenClient.interceptors.request.use((config) => {
  const t = getKitchenToken();
  if (t) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${t}`;
  }
  return config;
});

kitchenClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      clearKitchenToken();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/kitchen/login")) {
        window.location.href = "/kitchen/login";
      }
    }
    return Promise.reject(err);
  }
);

export function menuImageUrl(itemId) {
  return `${API_BASE}/menu/${itemId}/image`;
}

export function builderImageUrl() {
  return `${API_BASE}/builder-image`;
}

export function formatEur(n) {
  const v = Number.isFinite(n) ? n : 0;
  return `${v.toFixed(2)} €`;
}

export function fmtError(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") return detail.message;
    if (typeof detail.msg === "string") return detail.msg;
    return JSON.stringify(detail);
  }
  return err?.message || "Une erreur est survenue";
}
