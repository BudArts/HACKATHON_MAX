import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { Card, EmptyState, Pill, ScreenLoader } from '../components/ui';
import { api } from '../lib/api';
import { STATUS_LABELS, STATUS_TONES, SUBJECT_LABELS } from '../constants';
import type { TaskView } from '../types';

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function TasksPage(): JSX.Element {
  const [tasks, setTasks] = useState<TaskView[] | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setTasks(await api.get<TaskView[]>('/tasks'));
      } catch {
        setTasks([]);
      }
    })();
  }, []);

  if (tasks === null) return <ScreenLoader label="Загрузка задач" />;

  if (tasks.length === 0) {
    return (
      <Card title="Задачи">
        <EmptyState
          title="Пока пусто"
          description="Пришлите боту текст или фото задачи — она появится здесь вместе с ходом решения."
        />
      </Card>
    );
  }

  return (
    <div className="stack">
      {tasks.map((task) => (
        <Link key={task.id} className="list-item" to={`/tasks/${task.id}`}>
          <div className="row row--between">
            <div className="list-item__title">
              {task.topic ?? 'Тема уточняется'} · {SUBJECT_LABELS[task.subject]}
            </div>
            <Pill tone={STATUS_TONES[task.status]}>{STATUS_LABELS[task.status]}</Pill>
          </div>
          <div className="list-item__meta">
            <span>{formatDateTime(task.started_at)}</span>
            <span>шагов: {task.steps}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
