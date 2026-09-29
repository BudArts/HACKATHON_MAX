import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { api, ApiError } from '../lib/api';
import type { TokenStorage } from '../lib/api';
import { devLoginEnabled, notifyReady, readInitData } from '../lib/max';
import type { AuthResponse, ConsentPurpose, ConsentState, UserView } from '../types';

const ACCESS_KEY = 'sb.access';
const REFRESH_KEY = 'sb.refresh';

type SessionStatus = 'loading' | 'anonymous' | 'authenticated' | 'unavailable' | 'dev-login';

interface SessionValue {
  status: SessionStatus;
  user: UserView | null;
  consents: ConsentState[];
  onboardingRequired: boolean;
  failure: string | null;
  devLogin: boolean;
  granted: (purpose: ConsentPurpose) => boolean;
  signIn: () => Promise<void>;
  signInWithInitData: (initData: string) => Promise<void>;
  acceptConsent: (purpose: ConsentPurpose) => Promise<void>;
  revokeConsent: (purpose: ConsentPurpose) => Promise<void>;
  reload: () => void;
  setUser: (user: UserView) => void;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

function readToken(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeToken(key: string, value: string | null): void {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    /* хранилище может быть недоступно в веб-версии MAX */
  }
}

export function SessionProvider({ children }: { children: ReactNode }): JSX.Element {
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [user, setUser] = useState<UserView | null>(null);
  const [consents, setConsents] = useState<ConsentState[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const started = useRef(false);

  const storage = useMemo<TokenStorage>(
    () => ({
      getAccessToken: () => readToken(ACCESS_KEY),
      getRefreshToken: () => readToken(REFRESH_KEY),
      setTokens: (accessToken, refreshToken) => {
        writeToken(ACCESS_KEY, accessToken);
        writeToken(REFRESH_KEY, refreshToken);
      },
      onUnauthorized: () => {
        writeToken(ACCESS_KEY, null);
        writeToken(REFRESH_KEY, null);
        setStatus('anonymous');
        setUser(null);
      },
      refreshTokens: async () => {
        const refresh = readToken(REFRESH_KEY);
        if (!refresh) return false;
        try {
          const pair = await api.exchange(refresh);
          writeToken(ACCESS_KEY, pair.access_token);
          writeToken(REFRESH_KEY, pair.refresh_token);
          return true;
        } catch {
          return false;
        }
      },
    }),
    [],
  );

  useEffect(() => {
    api.attach(storage);
  }, [storage]);

  const apply = useCallback((payload: AuthResponse) => {
    if (payload.tokens) {
      writeToken(ACCESS_KEY, payload.tokens.access_token);
      writeToken(REFRESH_KEY, payload.tokens.refresh_token);
    }
    setUser(payload.user);
    setConsents(payload.consents);
    setStatus('authenticated');
  }, []);

  const signIn = useCallback(async () => {
    setStatus('loading');
    setFailure(null);
    const initData = readInitData();
    if (!initData) {
      if (devLoginEnabled()) {
        setStatus('dev-login');
        return;
      }
      setStatus('unavailable');
      setFailure('Приложение открывается только из мессенджера MAX');
      return;
    }
    try {
      apply(await api.login(initData));
    } catch (error) {
      setStatus('anonymous');
      setFailure(error instanceof ApiError ? error.message : 'Не удалось выполнить вход');
    }
  }, [apply]);

  const signInWithInitData = useCallback(
    async (initData: string) => {
      setStatus('loading');
      setFailure(null);
      try {
        apply(await api.login(initData));
      } catch (error) {
        setStatus(devLoginEnabled() ? 'dev-login' : 'anonymous');
        setFailure(error instanceof ApiError ? error.message : 'Не удалось выполнить вход');
      }
    },
    [apply],
  );

  useEffect(() => {
    notifyReady();
    if (started.current) return;
    started.current = true;
    void signIn();
  }, [signIn]);

  const reload = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  useEffect(() => {
    if (reloadToken === 0 || status !== 'authenticated') return;
    void (async () => {
      try {
        const items = await api.get<ConsentState[]>('/consents');
        setConsents(items);
        const profile = await api.get<UserView>('/me');
        setUser(profile);
      } catch {
        /* состояние обновится при следующем открытии */
      }
    })();
  }, [reloadToken, status]);

  const granted = useCallback(
    (purpose: ConsentPurpose) => consents.some((item) => item.purpose === purpose && item.granted),
    [consents],
  );

  const acceptConsent = useCallback(
    async (purpose: ConsentPurpose) => {
      const items = await api.post<ConsentState[]>(`/consents/${purpose}`, { accept: true });
      setConsents(items);
    },
    [],
  );

  const revokeConsent = useCallback(async (purpose: ConsentPurpose) => {
    const items = await api.delete<ConsentState[]>(`/consents/${purpose}`);
    setConsents(items);
  }, []);

  const signOut = useCallback(async () => {
    const refresh = readToken(REFRESH_KEY);
    if (refresh) {
      try {
        await api.post('/auth/logout', { refresh_token: refresh });
      } catch {
        /* сессия уже недействительна */
      }
    }
    storage.setTokens(null, null);
    setUser(null);
    setConsents([]);
    setStatus(devLoginEnabled() ? 'dev-login' : 'anonymous');
  }, [storage]);

  const value = useMemo<SessionValue>(
    () => ({
      status,
      user,
      consents,
      onboardingRequired: status === 'authenticated' && !granted('service'),
      failure,
      devLogin: devLoginEnabled(),
      granted,
      signIn,
      signInWithInitData,
      acceptConsent,
      revokeConsent,
      reload,
      setUser,
      signOut,
    }),
    [
      status,
      user,
      consents,
      failure,
      granted,
      signIn,
      signInWithInitData,
      acceptConsent,
      revokeConsent,
      reload,
      signOut,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error('SessionProvider отсутствует в дереве компонентов');
  return context;
}
