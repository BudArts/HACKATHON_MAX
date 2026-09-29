export interface MaxUserProfile {
  id: number;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  language_code: string | null;
  photo_url: string | null;
}

export interface MaxChatInfo {
  id: number;
  type: 'DIALOG' | 'CHAT' | 'CHANNEL';
}

export interface MaxInitDataUnsafe {
  query_id?: string;
  auth_date?: number;
  user?: MaxUserProfile;
  chat?: MaxChatInfo;
  start_param?: string;
}

export interface MaxBackButton {
  show: () => void;
  hide: () => void;
  isVisible?: boolean;
  onClick: (callback: () => void) => void;
  offClick: (callback: () => void) => void;
}

export interface MaxWebApp {
  initData: string;
  initDataUnsafe?: MaxInitDataUnsafe;
  platform?: string;
  version?: string;
  deviceName?: string;
  ready?: () => void;
  expand?: () => void;
  close?: () => void;
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void;
  requestContact?: () => Promise<{ phone: string; authDate: string; hash: string }>;
  getViewportSize?: () => Promise<{ height: string; width: string }>;
  BackButton?: MaxBackButton;
  enableClosingConfirmation?: () => void;
  disableClosingConfirmation?: () => void;
}

declare global {
  interface Window {
    WebApp?: MaxWebApp;
  }
}

export function webApp(): MaxWebApp | null {
  if (typeof window === 'undefined') return null;
  return window.WebApp ?? null;
}

export function isInsideMax(): boolean {
  return webApp() !== null;
}

function fromLocationHash(): string {
  if (typeof window === 'undefined') return '';
  const fragment = window.location.hash.replace(/^#/, '');
  if (!fragment) return '';
  const params = new URLSearchParams(fragment);
  return params.get('WebAppData') ?? '';
}

export function readInitData(): string {
  const app = webApp();
  if (app?.initData) return app.initData;
  const fromHash = fromLocationHash();
  if (fromHash) return fromHash;
  if (!import.meta.env.DEV) return '';
  return import.meta.env.VITE_DEV_INIT_DATA ?? '';
}

export function devLoginEnabled(): boolean {
  return import.meta.env.DEV || import.meta.env.VITE_DEV_LOGIN === 'true';
}

export function readStartParam(): string {
  const app = webApp();
  return app?.initDataUnsafe?.start_param ?? '';
}

export function openExternal(url: string): void {
  const app = webApp();
  if (app?.openLink) {
    app.openLink(url);
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function closeApp(): void {
  webApp()?.close?.();
}

export function bindBackButton(handler: () => void): () => void {
  const button = webApp()?.BackButton;
  if (!button) return () => undefined;
  button.show();
  button.onClick(handler);
  return () => {
    button.offClick(handler);
    button.hide();
  };
}

export function releaseBackButton(): void {
  webApp()?.BackButton?.hide();
}

export function notifyReady(): void {
  const app = webApp();
  app?.ready?.();
  app?.expand?.();
}
