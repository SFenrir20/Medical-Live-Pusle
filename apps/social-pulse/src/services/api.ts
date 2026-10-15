import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";

// `/api` is part of the base URL, so calls are written as "/auth/me", "/marketing/tiktok/...".
const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

type TokenProvider = () => Promise<string | null>;
let tokenProvider: TokenProvider = async () => null;

/** AuthContext registers Clerk's getToken here. Tokens are short-lived and never stored by us. */
export function setTokenProvider(provider: TokenProvider) {
  tokenProvider = provider;
}

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await tokenProvider();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error),
);

export default apiClient;
