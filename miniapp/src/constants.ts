import type { Tone } from './components/ui';
import type { TaskStatus, TaskSubject } from './types';

export const STATUS_LABELS: Record<TaskStatus, string> = {
  active: 'В работе',
  solved: 'Решено',
  abandoned: 'Заброшено',
};

export const STATUS_TONES: Record<TaskStatus, Tone> = {
  active: 'warning',
  solved: 'success',
  abandoned: 'neutral',
};

export const SUBJECT_LABELS: Record<TaskSubject, string> = {
  math: 'Математика',
  physics: 'Физика',
};

export const MAX_GRADE = 11;
export const MIN_GRADE = 5;
