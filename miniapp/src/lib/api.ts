import type { AuthResponse, DevInitData, DevUser, TokenPair } from '../types';

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export interface TokenStorage {
  getAccessToken(): string | null;
  getRefreshToken(): string | null;
  setTokens(accessToken: string | null, refreshToken: string | null): void;
  onUnauthorized(): void;
  refreshTokens(): Promise<boolean>;
}

const API_PREFIX = '/api/v1';

export class ApiClient {
  private storage: TokenStorage | null = null;
  private refreshInFlight: Promise<boolean> | null = null;

  attach(storage: TokenStorage): void {
    this.storage = storage;
  }

  private async send<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const token = this.storage?.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const init: RequestInit = { method, headers, credentials: 'omit' };
    if (body !== undefined) init.body = JSON.stringify(body);
    const response = await fetch(`${API_PREFIX}${path}`, init);

    if (response.status === 401 && retry && this.storage?.getRefreshToken()) {
      const refreshed = await this.refresh();
      if (refreshed) return this.send<T>(method, path, body, false);
      this.storage.onUnauthorized();
    }

    if (response.status === 204) return undefined as T;

    const text = await response.text();
    const payload = text ? (JSON.parse(text) as unknown) : null;

    if (!response.ok) {
      const error = payload as ApiErrorBody | null;
      throw new ApiError(
        response.status,
        error?.error?.code ?? `http_${response.status}`,
        error?.error?.message ?? 'Запрос не выполнен',
        error?.error?.detail,
      );
    }
    return payload as T;
  }

  private async refresh(): Promise<boolean> {
    if (!this.storage) return false;
    this.refreshInFlight ??= this.storage
      .refreshTokens()
      .finally(() => {
        this.refreshInFlight = null;
      });
    return this.refreshInFlight;
  }

  get<T>(path: string): Promise<T> {
    return this.send<T>('GET', path);
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.send<T>('POST', path, body);
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.send<T>('PATCH', path, body);
  }

  delete<T>(path: string, body?: unknown): Promise<T> {
    return this.send<T>('DELETE', path, body);
  }

  login(initData: string): Promise<AuthResponse> {
    return this.send<AuthResponse>('POST', '/auth/max', { init_data: initData }, false);
  }

  exchange(refreshToken: string): Promise<TokenPair> {
    return this.send<TokenPair>('POST', '/auth/refresh', { refresh_token: refreshToken }, false);
  }

  devUsers(): Promise<DevUser[]> {
    return this.send<DevUser[]>('GET', '/dev/users', undefined, false);
  }

  devInitData(maxUserId: number): Promise<DevInitData> {
    return this.send<DevInitData>('GET', `/dev/init-data?max_user_id=${maxUserId}`, undefined, false);
  }
}

export const api = new ApiClient();
