import { useEffect, useState } from 'react';

import { Card, EmptyState, ScreenLoader, Stat } from '../components/ui';
import { api } from '../lib/api';
import type { RiskStudent } from '../types';

export function TeacherRiskPage(): JSX.Element {
  const [students, setStudents] = useState<RiskStudent[] | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.get<{ students: RiskStudent[] }>('/tutor/risk');
        setStudents(data.students);
      } catch {
        setStudents([]);
      }
    })();
  }, []);

  if (students === null) return <ScreenLoader label="Загрузка группы риска" />;

  if (students.length === 0) {
    return (
      <Card title="Группа риска">
        <EmptyState
          title="Кто систематически застревает — не найден"
          description="В список попадают ученики с тремя и более нерешёнными задачами за последние 7 дней."
        />
      </Card>
    );
  }

  return (
    <div className="stack">
      <p className="muted">
        Ученики с тремя и более нерешёнными задачами за последние 7 дней. Стоит обсудить темы на
        уроке и поддержать учеников.
      </p>
      {students.map((student) => (
        <Card key={student.user_id} title={student.name} hint={`${student.grade} класс`}>
          <div className="stack">
            <Stat value={student.unsolved} label="Нерешённых задач за неделю" />
            {student.stuck_topics.length > 0 && (
              <p className="muted">Темы: {student.stuck_topics.join(', ')}</p>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
