import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Alert, Card, EmptyState, ScreenLoader, Stat } from '../components/ui';
import { api, ApiError } from '../lib/api';
import type { ChildView, DigestView } from '../types';

export function ParentLinkPage(): JSX.Element {
  const navigate = useNavigate();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.post('/parent/link', { code: code.trim() });
      navigate('/parent', { replace: true });
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Не удалось привязать ребёнка');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Привязка ребёнка" hint="Код выдаёт ученик в боте командой /code">
      <form className="stack" onSubmit={(event) => void submit(event)}>
        <label className="field">
          <span>Код из шести цифр</span>
          <input
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
            placeholder="123456"
            required
          />
        </label>
        {error && <Alert tone="danger">{error}</Alert>}
        <button className="btn" type="submit" disabled={busy || code.length !== 6}>
          {busy ? 'Проверяем…' : 'Привязать'}
        </button>
        <p className="muted">Код действует 30 минут и рассчитан на 5 попыток ввода.</p>
      </form>
    </Card>
  );
}

export function ParentChildrenPage(): JSX.Element {
  const [children, setChildren] = useState<ChildView[] | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setChildren(await api.get<ChildView[]>('/parent/children'));
      } catch {
        setChildren([]);
      }
    })();
  }, []);

  if (children === null) return <ScreenLoader label="Загрузка" />;

  return (
    <div className="stack">
      {children.length === 0 ? (
        <Card title="Дети">
          <EmptyState
            title="Пока никто не привязан"
            description="Ученик получает код командой /code в боте и сообщает его вам."
          />
        </Card>
      ) : (
        children.map((child) => (
          <Link key={child.user_id} className="list-item" to={`/parent/child/${child.user_id}`}>
            <div className="row row--between">
              <div className="list-item__title">{child.name}</div>
              <span className="muted">Дайджест →</span>
            </div>
            <div className="list-item__meta">
              <span>Класс {child.grade ?? '—'}</span>
            </div>
          </Link>
        ))
      )}
      <Card title="Привязать ребёнка">
        <Link className="list-item" to="/parent/link">
          Ввести код
        </Link>
      </Card>
    </div>
  );
}

export function ChildDigestPage(): JSX.Element {
  const { childId } = useParams();
  const [digest, setDigest] = useState<DigestView | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setDigest(await api.get<DigestView>(`/parent/children/${childId}/digest`));
      } catch {
        setDigest(null);
      }
    })();
  }, [childId]);

  if (digest === null) {
    return (
      <Card title="Дайджест">
        <EmptyState title="Нет данных" description="Дайджест появится после первой недели занятий." />
      </Card>
    );
  }

  return (
    <div className="stack">
      <Card title={digest.student.name} hint={`Класс ${digest.student.grade ?? '—'} · неделя`}>
        <div className="stack">
          <div className="stat-grid">
            <Stat value={digest.started} label="Задач начато" />
            <Stat value={digest.solved} label="Решено" />
          </div>
          {digest.topics.length > 0 && <p className="muted">Темы недели: {digest.topics.join(', ')}</p>}
          {digest.last_activity_at && (
            <p className="muted">
              Последняя активность:{' '}
              {new Date(digest.last_activity_at).toLocaleString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </p>
          )}
        </div>
      </Card>

      <Card title="По дням">
        <div className="stack">
          {digest.daily.map((day) => (
            <div key={day.day} className="row row--between">
              <span>{day.day}</span>
              <span className="muted">
                начато {day.started} · решено {day.solved}
              </span>
            </div>
          ))}
        </div>
      </Card>

      <Link className="list-item" to="/parent">
        Ко всем детям
      </Link>
    </div>
  );
}
