import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Alert, Button, Card, Pill } from '../components/ui';
import { useSession } from '../state/session';
import { formatDate } from '../lib/format';

export function ConsentPage(): JSX.Element {
  const { consents, acceptConsent, revokeConsent, granted } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiAccepted, setAiAccepted] = useState(granted('ai_processing'));

  const service = consents.find((item) => item.purpose === 'service');

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await acceptConsent('service');
      if (aiAccepted) await acceptConsent('ai_processing');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Не удалось сохранить согласие');
    } finally {
      setBusy(false);
    }
  }

  async function withdrawAi(): Promise<void> {
    setBusy(true);
    try {
      await revokeConsent('ai_processing');
      setAiAccepted(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <Card title="Согласие на обработку персональных данных">
        <div className="stack">
          <p className="muted">
            Сервис принимает обращения родителей к педагогическим работникам и хранит историю переписки.
            Без согласия обработка персональных данных невозможна.
          </p>
          <div className="divider" />
          <dl className="stack">
            <div>
              <dt className="field__label">Какие данные обрабатываются</dt>
              <dd className="muted">
                Идентификатор профиля MAX, имя и фамилия из профиля, номер телефона при его передаче,
                содержание ваших обращений, служебные отметки о действиях.
              </dd>
            </div>
            <div>
              <dt className="field__label">Цель обработки</dt>
              <dd className="muted">
                Приём и обработка обращений, направление ответов и уведомлений, подтверждение полномочий
                родителя или педагогического работника.
              </dd>
            </div>
            <div>
              <dt className="field__label">Где хранятся данные</dt>
              <dd className="muted">
                На территории Российской Федерации. Телефон и электронная почта — в зашифрованном виде.
              </dd>
            </div>
            <div>
              <dt className="field__label">Срок действия</dt>
              <dd className="muted">
                До достижения цели обработки или до отзыва. Отозвать согласие можно в разделе
                «Персональные данные».
              </dd>
            </div>
          </dl>
          {service && service.granted && (
            <Pill tone="success">Согласие предоставлено {formatDate(service.granted_at)}</Pill>
          )}
        </div>
      </Card>

      <Card title="Черновики ответов" hint="Необязательно">
        <div className="stack">
          <p className="muted">
            Программа поможет педагогу подготовить черновик ответа. Перед передачей текста из обращения
            автоматически удаляются фамилии, имена, отчества, телефоны, адреса почты и реквизиты документов.
            Решение всегда принимает педагог.
          </p>
          {granted('ai_processing') ? (
            <div className="row">
              <Pill tone="success">Разрешено</Pill>
              <Button variant="ghost" small onClick={() => void withdrawAi()} disabled={busy}>
                Отключить
              </Button>
            </div>
          ) : (
            <label className="checklist">
              <input
                type="checkbox"
                checked={aiAccepted}
                onChange={(event) => setAiAccepted(event.target.checked)}
              />
              <span className="muted">Разрешить автоматическую подготовку черновиков ответов</span>
            </label>
          )}
        </div>
      </Card>

      {error && <Alert tone="danger">{error}</Alert>}

      <Button block loading={busy} onClick={() => void submit()} disabled={granted('service')}>
        {granted('service') ? 'Согласие уже предоставлено' : 'Согласиться и продолжить'}
      </Button>

      <p className="muted small">
        Продолжая, вы подтверждаете, что ознакомились с документами: <Link to="/legal/consent_processing">Согласие на обработку</Link>,{' '}
        <Link to="/legal/privacy_policy">Политика обработки персональных данных</Link>,{' '}
        <Link to="/legal/terms">Правила использования сервиса</Link>.
      </p>
    </div>
  );
}
