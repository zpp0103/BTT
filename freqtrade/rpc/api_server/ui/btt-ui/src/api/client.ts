import type { ApiConfig } from "./types";

const SETTINGS_KEY = "btt-api-config";

const defaultConfig: ApiConfig = {
  baseUrl: "",
  accessToken: "",
  refreshToken: "",
};
let refreshInFlight: Promise<string> | null = null;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly endpoint: string,
    message: string,
  ) {
    super(message);
  }
}

export function loadApiConfig(): ApiConfig {
  try {
    const saved = sessionStorage.getItem(SETTINGS_KEY);
    return saved ? { ...defaultConfig, ...JSON.parse(saved) } : { ...defaultConfig };
  } catch {
    return { ...defaultConfig };
  }
}

export function saveApiConfig(config: ApiConfig): void {
  sessionStorage.setItem(SETTINGS_KEY, JSON.stringify(config));
}

export function clearApiConfig(): void {
  sessionStorage.removeItem(SETTINGS_KEY);
}

function apiUrl(path: string, baseUrl = loadApiConfig().baseUrl): string {
  return `${baseUrl.replace(/\/$/, "")}/api/v1${path}`;
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; error?: string };
    return payload.detail ?? payload.error ?? response.statusText;
  } catch {
    return response.statusText || "请求失败";
  }
}

async function refreshAccessToken(config: ApiConfig): Promise<string> {
  if (!config.refreshToken) throw new ApiError(401, "/token/refresh", "登录会话已过期");
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const response = await fetch(apiUrl("/token/refresh", config.baseUrl), {
        method: "POST",
        headers: { Authorization: `Bearer ${config.refreshToken}`, Accept: "application/json" },
      });
      if (!response.ok) {
        clearApiConfig();
        throw new ApiError(response.status, "/token/refresh", await parseError(response));
      }
      const tokens = (await response.json()) as { access_token: string };
      saveApiConfig({ ...config, accessToken: tokens.access_token });
      return tokens.access_token;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const config = loadApiConfig();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (config.accessToken) headers.set("Authorization", `Bearer ${config.accessToken}`);

  let response = await fetch(apiUrl(path, config.baseUrl), { ...init, headers });
  if (response.status === 401 && config.refreshToken) {
    config.accessToken = await refreshAccessToken(config);
    headers.set("Authorization", `Bearer ${config.accessToken}`);
    response = await fetch(apiUrl(path, config.baseUrl), { ...init, headers });
  }
  if (!response.ok) {
    throw new ApiError(response.status, path, await parseError(response));
  }
  return response.json() as Promise<T>;
}

export async function login(baseUrl: string, username: string, password: string): Promise<ApiConfig> {
  const auth = btoa(new TextEncoder().encode(`${username}:${password}`).reduce((s, b) => s + String.fromCharCode(b), ""));
  const response = await fetch(apiUrl("/token/login", baseUrl), {
    method: "POST",
    headers: { Authorization: `Basic ${auth}`, Accept: "application/json" },
  });
  if (!response.ok) throw new ApiError(response.status, "/token/login", await parseError(response));
  const tokens = (await response.json()) as { access_token: string; refresh_token: string };
  const config = { baseUrl, accessToken: tokens.access_token, refreshToken: tokens.refresh_token };
  saveApiConfig(config);
  return config;
}
