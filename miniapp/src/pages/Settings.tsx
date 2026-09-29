import { Link } from 'react-router-dom';

import { Alert, Button, Card, Pill } from '../components/ui';
import { roleLabel } from '../components/AppShell';
import { api } from '../lib/api';
import { webApp } from '../lib/max';
import { closeApp, openExternal } from '../lib/max';
import { formatDate, formatInitials } from '../lib/format';
import { useAction } from '../lib/useQuery';
import { useSession } from '../state/session';

export function SettingsPage(): JSX.Element {
  const { user, consents, granted, acceptConsent, revokeConsent, signOut } = useSession();
  const action = useAction();

  const service = consents.find((item) => item.purpose === 'service');

  async function toggleAi(): Promise<void> {
    await action.run(async () => {
      if (granted('ai_processing')) await revokeConsent('ai_processing');
      else await acceptConsent('ai_processing');
    });
  }

  async function shareContact(): Promise<void> {
    await action.run(async () => {
      const app = webApp();
      if (!app?.requestContact) {
        throw new Error('Передача контакта недоступна в этой версии MAX');
      }
      const contact = await app.requestContact();
      await api.patch('/me/phone', {
        phone: contact.phone,
        auth_date: contact.authDate,
        hash: contact.hash,
      });
    }, 'Номер телефона сохранён');
  }

  async function leave(): Promise<void> {
    await signOut();
    closeApp();
  }

  return (
    <div className="stack">
      <Card title="Профиль" tight>
        <div className="stack">
          <div className="row row--between">
            <div>
              <div className="card__title">{user ? formatInitials(user.first_name, user.last_name) : 'Гость'}</div>
              <div className="card__hint">{user ? roleLabel(user.role) : 'Войдите через MAX'}</div>
            </div>
            <Pill tone={user?.is_active ? 'success' : 'danger'}>{user?.is_active ? 'Активен' : 'Заблокирован'}</Pill>
          </div>
          <div className="divider" />
          <div className="row row--between">
            <span className="muted small">Телефон</span>
            <span className="small">{user?.has_phone ? 'сохранён' : 'не указан'}</span>
          </div>
          {!user?.has_phone && (
            <Button variant="secondary" small onClick={() => void shareContact()} loading={action.busy}>
              Передать номер из MAX
            </Button>
          )}
          <div className="row row--between">
            <span className="muted small">В сервисе с</span>
            <span className="small">{formatDate(user?.created_at)}</span>
          </div>
        </div>
      </Card>

      {action.error && <Alert tone="danger">{action.error}</Alert>}
      {action.notice && <Alert tone="success">{action.notice}</Alert>}

      <Card title="Согласия" hint="Управляются в любой момент" tight>
        <div className="stack">
          <div className="row row--between">
            <div>
              <div className="card__title">Обработка персональных данных</div>
              <div className="card__hint">
                {service?.granted ? `предоставлено ${formatDate(service.granted_at)}` : 'не предоставлено'}
                {service?.policy_version ? `, редакция ${service.policy_version}` : ''}
              </div>
            </div>
            <Pill tone={service?.granted ? 'success' : 'danger'}>{service?.granted ? 'Да' : 'Нет'}</Pill>
          </div>
          <div className="divider" />
          <div className="row row--between">
            <div>
              <div className="card__title">ИИ-наставник</div>
              <div className="card__hint">Обработка задач и диалогов с наставником. Без неё бот не отвечает</div>
            </div>
            <Button variant="secondary" small loading={action.busy} onClick={() => void toggleAi()}>
              {granted('ai_processing') ? 'Отключить' : 'Разрешить'}
            </Button>
          </div>
          <div className="divider" />
          <div className="row row--wrap">
            <Link to="/legal">
              <Button variant="ghost" small>
                Документы сервиса
              </Button>
            </Link>
            <Link to="/settings/data">
              <Button variant="ghost" small>
                Персональные данные
              </Button>
            </Link>
          </div>
        </div>
      </Card>

      <Card title="Поддержка" tight>
        <div className="stack">
          <p className="muted small">
            Вопросы по работе сервиса направляйте классному руководителю или оператору школы.
            Контакты указаны в документах сервиса. Сервис соответствует 152-ФЗ; данные детей
            обрабатываются с согласия родителей.
          </p>
          <Button variant="secondary" small onClick={() => openExternal('https://max.ru/')}>
            Открыть MAX
          </Button>
        </div>
      </Card>

      <Button variant="danger" block onClick={() => void leave()}>
        Выйти из кабинета
      </Button>
    </div>
  );
}