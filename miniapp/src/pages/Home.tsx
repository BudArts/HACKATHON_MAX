import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { Alert, Card, EmptyState, ScreenLoader, Stat } from '../components/ui';
import { api } from '../lib/api';
import { useSession } from '../state/session';
import type { ChildView, DigestView, GradeOverview, TaskStatistics } from '../types';

function StudentHome(): JSX.Element {
  const { user } = useSession();
  const [stats, setStats] = useState<TaskStatistics | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setStats(await api.get<TaskStatistics>('/tasks/statistics'));
      } catch {
        setStats({ total: 0, solved: 0, active: 0, recent_topics: [] });
      }
    })();
  }, []);

  return (
    <div className="stack">
      <Card title={`Привет, ${user?.first_name ?? 'ученик'}!`} hint="ИИ-наставник по математике и физике">
        <div className="stack">
          <p className="muted">
            Пришли боту фото задачи или её текст — наставник задаст наводящие вопросы и доведёт до
            решения. Готовые ответы не выдаются.
          </p>
          <Alert tone="info">
            Задачи решаются в чате с ботом. Здесь видно прогресс: сколько задач решено и какие темы.
          </Alert>
        </div>
      </Card>

      {stats === null ? (
        <ScreenLoader />
      ) : (
        <Card title="Мой прогресс">
          <div className="stat-grid">
            <Stat value={stats.total} label="Всего задач" />
            <Stat value={stats.solved} label="Решено" />
            <Stat value={stats.active} label="В работе" />
          </div>
          {stats.recent_topics.length > 0 && (
            <p className="muted">Недавние темы: {stats.recent_topics.join(', ')}</p>
          )}
        </Card>
      )}

      <Card title="История задач">
        <Link className="list-item" to="/tasks">
          Открыть список задач
        </Link>
      </Card>
    </div>
  );
}

function ParentHome(): JSX.Element {
  const [children, setChildren] = useState<ChildView[] | null>(null);
  const [digests, setDigests] = useState<Record<string, DigestView>>({});

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.get<ChildView[]>('/parent/children');
        setChildren(list);
        const loaded: Record<string, DigestView> = {};
        await Promise.all(
          list.map(async (child) => {
            try {
              loaded[child.user_id] = await api.get<DigestView>(
                `/parent/children/${child.user_id}/digest`,
              );
            } catch {
              loaded[child.user_id] = {
                student: child,
                started: 0,
                solved: 0,
                topics: [],
                daily: [],
                last_activity_at: null,
              };
            }
          }),
        );
        setDigests(loaded);
      } catch {
        setChildren([]);
      }
    })();
  }, []);

  if (children === null) return <ScreenLoader />;

  if (children.length === 0) {
    return (
      <Card title="Дети не привязаны">
        <div className="stack">
          <EmptyState
            title="Привяжите ребёнка"
            description="Ученик получает код командой /code в боте и сообщает его вам. Введите код, чтобы видеть прогресс."
          />
          <Link className="list-item" to="/parent/link">
            Ввести код
          </Link>
        </div>
      </Card>
    );
  }

  return (
    <div className="stack">
      {children.map((child) => {
        const digest = digests[child.user_id];
        return (
          <Card key={child.user_id} title={child.name} hint={`Класс ${child.grade ?? '—'}`}>
            <div className="stack">
              {digest ? (
                <>
                  <div className="stat-grid">
                    <Stat value={digest.started} label="Задач за неделю" />
                    <Stat value={digest.solved} label="Решено" />
                  </div>
                  {digest.topics.length > 0 && <p className="muted">Темы: {digest.topics.join(', ')}</p>}
                </>
              ) : (
                <p className="muted">Данных пока нет</p>
              )}
              <Link className="list-item" to={`/parent/child/${child.user_id}`}>
                Недельный дайджест
              </Link>
            </div>
          </Card>
        );
      })}
      <Card title="Привязать ещё ребёнка">
        <Link className="list-item" to="/parent/link">
          Ввести код
        </Link>
      </Card>
    </div>
  );
}

function TeacherHome(): JSX.Element {
  const [overview, setOverview] = useState<GradeOverview[] | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.get<{ grades: GradeOverview[] }>('/tutor/overview');
        setOverview(data.grades);
      } catch {
        setOverview([]);
      }
    })();
  }, []);

  if (overview === null) return <ScreenLoader />;

  if (overview.length === 0) {
    return (
      <Card title="Аналитика">
        <EmptyState title="Данных нет" description="Задачи появятся, когда ученики начнут работать с наставником." />
      </Card>
    );
  }

  return (
    <div className="stack">
      {overview.map((item) => {
        const share = item.tasks_total > 0 ? Math.round((item.tasks_solved / item.tasks_total) * 100) : 0;
        return (
          <Card key={item.grade} title={`${item.grade} класс`} hint={`Учеников: ${item.students}`}>
            <div className="stack">
              <div className="stat-grid">
                <Stat value={item.tasks_total} label="Задач" />
                <Stat value={item.tasks_solved} label="Решено" />
                <Stat value={`${share}%`} label="Доля решённых" />
              </div>
              {item.topics.length > 0 && (
                <div className="stack">
                  <p className="muted">Темы класса:</p>
                  {item.topics.map((topic) => (
                    <div key={topic.topic} className="row row--between">
                      <span>{topic.topic}</span>
                      <span className="muted">
                        решено {topic.solved} из {topic.total}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        );
      })}
      <Card title="Группа риска">
        <p className="muted">
          Ученики с тремя и более нерешёнными задачами за неделю попадают в группу риска на странице
          «Ученики».
        </p>
        <Link className="list-item" to="/teacher/risk">
          Открыть группу риска
        </Link>
      </Card>
    </div>
  );
}

export function HomePage(): JSX.Element {
  const { user, status } = useSession();

  if (status !== 'authenticated' || !user) return <ScreenLoader label="Загрузка кабинета" />;

  if (user.role === 'student') return <StudentHome />;
  if (user.role === 'parent') return <ParentHome />;
  return <TeacherHome />;
}
