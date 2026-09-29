import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Card, EmptyState, Pill } from '../components/ui';
import { api } from '../lib/api';
import { STATUS_LABELS, STATUS_TONES, SUBJECT_LABELS } from '../constants';
import type { TaskDetail as TaskDetailData } from '../types';

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function TaskDetailPage(): JSX.Element {
  const { taskId } = useParams();
  const [task, setTask] = useState<TaskDetailData | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setTask(await api.get<TaskDetailData>(`/tasks/${taskId}`));
      } catch {
        setTask(null);
      }
    })();
  }, [taskId]);

  if (task === null) {
    return (
      <Card title="Задача">
        <EmptyState title="Задача не найдена" description="Возможно, она удалена или недоступна." />
      </Card>
    );
  }

  return (
    <div className="stack">
      <Card
        title={task.topic ?? 'Тема уточняется'}
        hint={`${SUBJECT_LABELS[task.subject]} · ${task.grade} класс`}
      >
        <div className="stack">
          <div className="row row--between">
            <span className="muted">Начата {formatDateTime(task.started_at)}</span>
            <Pill tone={STATUS_TONES[task.status]}>{STATUS_LABELS[task.status]}</Pill>
          </div>
          <p className="muted">Шагов диалога: {task.steps}</p>
          {task.summary && (
            <p>
              <strong>Итог наставника:</strong> {task.summary}
            </p>
          )}
        </div>
      </Card>

      <Card title="Ход работы">
        <div className="thread">
          {task.thread.map((message, index) => (
            <div
              key={index}
              className={`bubble ${message.author === 'student' ? 'bubble--mine' : 'bubble--internal'}`}
            >
              <div className="bubble__meta">
                <span>{message.author === 'student' ? 'Ученик' : 'Наставник'}</span>
                <span>{formatDateTime(message.created_at)}</span>
              </div>
              <div>{message.content}</div>
            </div>
          ))}
        </div>
      </Card>

      <Link className="list-item" to="/tasks">
        Ко всем задачам
      </Link>
    </div>
  );
}
