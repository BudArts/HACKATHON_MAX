import { useEffect, useState } from 'react';

import { roleLabel } from '../components/AppShell';
import { Alert, Button, Card, Field, Input, Spinner } from '../components/ui';
import { api, ApiError } from '../lib/api';
import { useSession } from '../state/session';
import type { DevUser } from '../types';

function displayName(user: DevUser): string {
  const name = [user.last_name, user.first_name].filter(Boolean).join(' ');
  return name || `Пользователь ${user.max_user_id}`;
}

export function DevLoginPage(): JSX.Element {
  const { signInWithInitData, failure } = useSession();
  const [users, setUsers] = useState<DevUser[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pending, setPending] = useState<number | null>(null);
  const [manualId, setManualId] = useState('');

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const items = await api.devUsers();
        if (!cancelled) setUsers(items);
      } catch (error) {
        if (cancelled) return;
        setUsers([]);
        setLoadError(
          error instanceof ApiError
            ? `${error.message}. Демо-вход включается переменной DEV_LOGIN_ENABLED и недоступен в production.`
            : 'Список пользователей недоступен',
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function enter(maxUserId: number): Promise<void> {
    setPending(maxUserId);
    setLoadError(null);
    try {
      const signed = await api.devInitData(maxUserId);
      await signInWithInitData(signed.init_data);
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : 'Не удалось выполнить вход');
    } finally {
      setPending(null);
    }
  }

  const manual = Number.parseInt(manualId, 10);
  const manualReady = Number.isInteger(manual) && manual > 0;

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__title">Обращения</div>
      </header>
      <main className="app__content app__content--flush">
        <div className="stack">
          <Card title="Выбор кабинета" hint="Запуск вне мессенджера MAX">
            <div className="stack">
              <p className="muted">
                Сервис открыт в браузере, поэтому стартовые данные MAX подписывает сервер. Выберите
                кабинет для проверки: ученик, родитель или педагог.
              </p>

              {loadError && <Alert tone="danger">{loadError}</Alert>}
              {failure && <Alert tone="warning">{failure}</Alert>}

              {users === null && <Spinner />}

              {users?.map((user) => (
                <Button
                  key={user.max_user_id}
                  block
                  variant={user.role === 'student' ? 'primary' : 'secondary'}
                  loading={pending === user.max_user_id}
                  disabled={pending !== null}
                  onClick={() => void enter(user.max_user_id)}
                >
                  {displayName(user)} · {roleLabel(user.role)}
                </Button>
              ))}

              {users !== null && users.length === 0 && !loadError && (
                <Alert tone="info">
                  Пользователей нет. Заполните демо-данные командой seed и обновите страницу.
                </Alert>
              )}

              <Field label="Другой идентификатор MAX" hint="Вход от имени пользователя, которого нет в списке">
                <div className="row">
                  <Input
                    value={manualId}
                    inputMode="numeric"
                    placeholder="9100101"
                    onChange={(event) => setManualId(event.target.value.replace(/\D/g, ''))}
                  />
                  <Button
                    variant="secondary"
                    disabled={!manualReady || pending !== null}
                    loading={pending !== null && pending === manual}
                    onClick={() => void enter(manual)}
                  >
                    Войти
                  </Button>
                </div>
              </Field>
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
