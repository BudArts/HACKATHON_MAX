import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Alert, Button, Card, Pill, ScreenLoader } from '../components/ui';
import { api } from '../lib/api';
import { formatDate, formatDateTime, formatInitials } from '../lib/format';
import { useAction, useQuery } from '../lib/useQuery';
import { useSession } from '../state/session';
import type { PersonalDataReport } from '../types';

const ACTION_LABELS: Record<string, string> = {
  'consent.granted': 'Предоставлено согласие',
  'consent.revoked': 'Отозвано согласие',
  'appeal.created': 'Создано обращение',
  'appeal.message_added': 'Добавлено сообщение',
  'appeal.status_changed': 'Изменён статус обращения',
  'appeal.rated': 'Поставлена оценка',
  'auth.miniapp': 'Вход в кабинет',
  'auth.logout': 'Выход из кабинета',
  'user.phone_updated': 'Сохранён номер телефона',
  'guardian.link_requested': 'Заявка на привязку ребёнка',
  'guardian.link_verified': 'Связь с ребёнком подтверждена',
  'personal_data.erasure_requested': 'Заявление о прекращении обработки',
};

export function PersonalDataPage(): JSX.Element {
  const query = useQuery<PersonalDataReport>(() => api.get<PersonalDataReport>('/me/personal-data'), 'report');
  const { revokeConsent, signOut } = useSession();
  const action = useAction();
  const [confirming, setConfirming] = useState(false);

  async function erase(): Promise<void> {
    const ok = await action.run(async () => {
      await api.delete('/me');
      await signOut();
    });
    if (ok) setConfirming(false);
  }

  if (query.loading) return <ScreenLoader />;
  if (query.error) return <Alert tone="danger">{query.error}</Alert>;
  const report = query.data;
  if (!report) return <Alert tone="danger">Выписка недоступна</Alert>;

  return (
    <div className="stack">
      <Alert tone="info">
        Это выписка о персональных данных, которые обрабатываются в сервисе. Она формируется по статье 14
        Федерального закона № 152-ФЗ.
      </Alert>

      {action.error && <Alert tone="danger">{action.error}</Alert>}

      <Card title="Сведения о субъекте" tight>
        <div className="stack">
          <Row label="Имя в сервисе" value={formatInitials(report.profile.first_name, report.profile.last_name)} />
          <Row label="Роль" value={report.profile.role} />
          <Row label="Номер телефона" value={report.profile.has_phone ? 'хранится в зашифрованном виде' : 'не указан'} />
          <Row label="Электронная почта" value={report.profile.has_email ? 'хранится в зашифрованном виде' : 'не указана'} />
          <Row label="Учебных задач" value={String(report.tasks_total)} />
          <Row label="Уведомлений" value={String(report.notifications_total)} />
        </div>
      </Card>

      <Card title="Согласия" tight>
        <div className="stack">
          {report.consents.map((consent) => (
            <div className="row row--between" key={consent.purpose}>
              <div>
                <div className="card__title">{purposeLabel(consent.purpose)}</div>
                <div className="card__hint">
                  редакция {consent.policy_version || '—'}
                  {consent.granted_at ? ` · предоставлено ${formatDate(consent.granted_at)}` : ''}
                  {consent.revoked_at ? ` · отозвано ${formatDate(consent.revoked_at)}` : ''}
                </div>
              </div>
              {consent.granted ? (
                <Button variant="ghost" small loading={action.busy} onClick={() => void revokeConsent(consent.purpose)}>
                  Отозвать
                </Button>
              ) : (
                <Pill tone="danger">Не предоставлено</Pill>
              )}
            </div>
          ))}
          <Link to="/legal">
            <Button variant="secondary" small block>
              Документы сервиса
            </Button>
          </Link>
        </div>
      </Card>

      <Card title="Журнал действий" hint={`${report.audit_entries.length} последних записей`} tight>
        <div className="stack">
          {report.audit_entries.slice(0, 25).map((entry, index) => (
            <div className="row row--between" key={`${String(entry.created_at)}-${index}`}>
              <span className="small">
                {ACTION_LABELS[String(entry.action)] ?? String(entry.action)}
              </span>
              <span className="small muted nowrap">{formatDateTime(String(entry.created_at))}</span>
            </div>
          ))}
          {report.audit_entries.length === 0 && <p className="muted small">Действий пока не зафиксировано.</p>}
        </div>
      </Card>

      <Card title="Прекращение обработки" tight>
        <div className="stack">
          <p className="muted small">
            Обработка прекращается, персональные данные обезличиваются, доступ к кабинету закрывается.
            Журнал действий сохраняется три года в силу требований законодательства.
          </p>
          {confirming ? (
            <>
              <Alert tone="warning">Действие необратимо. Продолжить?</Alert>
              <div className="row row--wrap">
                <Button variant="danger" small loading={action.busy} onClick={() => void erase()}>
                  Да, прекратить обработку
                </Button>
                <Button variant="ghost" small onClick={() => setConfirming(false)}>
                  Отмена
                </Button>
              </div>
            </>
          ) : (
            <Button variant="danger" small onClick={() => setConfirming(true)}>
              Прекратить обработку и удалить данные
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="row row--between">
      <span className="muted small">{label}</span>
      <span className="small">{value}</span>
    </div>
  );
}

function purposeLabel(purpose: string): string {
  switch (purpose) {
    case 'service':
      return 'Обработка персональных данных';
    case 'notifications':
      return 'Уведомления';
    case 'ai_processing':
      return 'Черновики ответов';
    default:
      return purpose;
  }
}
