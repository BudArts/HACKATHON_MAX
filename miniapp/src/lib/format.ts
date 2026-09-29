const MONTHS = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
];

export function formatDate(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const time = date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return time;
  const yesterday = new Date(today.getTime() - 86_400_000);
  if (date.toDateString() === yesterday.toDateString()) return `вчера, ${time}`;
  return `${date.getDate()} ${MONTHS[date.getMonth()]}, ${time}`;
}

export function formatInitials(firstName: string | null, lastName: string | null): string {
  const parts = [lastName, firstName].filter(Boolean) as string[];
  if (parts.length === 0) return 'Пользователь';
  if (parts.length === 1) return parts[0] as string;
  const [first, second] = parts as [string, string];
  return `${first} ${second.charAt(0)}.`;
}

export function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export function appealsWord(count: number): string {
  return `${count} ${plural(count, 'обращение', 'обращения', 'обращений')}`;
}

export function truncate(value: string, limit = 140): string {
  return value.length > limit ? `${value.slice(0, limit - 1).trimEnd()}…` : value;
}
