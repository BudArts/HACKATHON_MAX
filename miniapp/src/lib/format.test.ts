import { describe, expect, it } from 'vitest';

import { appealsWord, formatDate, formatDateTime, formatInitials, plural, truncate } from './format';

describe('plural', () => {
  it('выбирает форму по правилам русского языка', () => {
    expect(plural(1, 'обращение', 'обращения', 'обращений')).toBe('обращение');
    expect(plural(2, 'обращение', 'обращения', 'обращений')).toBe('обращения');
    expect(plural(5, 'обращение', 'обращения', 'обращений')).toBe('обращений');
    expect(plural(11, 'обращение', 'обращения', 'обращений')).toBe('обращений');
    expect(plural(21, 'обращение', 'обращения', 'обращений')).toBe('обращение');
    expect(plural(104, 'обращение', 'обращения', 'обращений')).toBe('обращения');
  });

  it('формирует счётчик обращений', () => {
    expect(appealsWord(0)).toBe('0 обращений');
    expect(appealsWord(3)).toBe('3 обращения');
  });
});

describe('formatInitials', () => {
  it('показывает фамилию с инициалом имени', () => {
    expect(formatInitials('Мария', 'Ковалёва')).toBe('Ковалёва М.');
  });

  it('обрабатывает неполные данные', () => {
    expect(formatInitials(null, 'Ковалёва')).toBe('Ковалёва');
    expect(formatInitials('Мария', null)).toBe('Мария');
    expect(formatInitials(null, null)).toBe('Пользователь');
  });
});

describe('formatDate', () => {
  it('возвращает дату в русском формате', () => {
    expect(formatDate('2026-09-29T10:00:00Z')).toMatch(/^\d{1,2} [а-яё]+ \d{4}$/);
  });

  it('не падает на пустых и некорректных значениях', () => {
    expect(formatDate(null)).toBe('');
    expect(formatDate(undefined)).toBe('');
    expect(formatDate('не дата')).toBe('');
    expect(formatDateTime(null)).toBe('');
    expect(formatDateTime('не дата')).toBe('');
  });
});

describe('truncate', () => {
  it('сохраняет короткий текст без изменений', () => {
    expect(truncate('Короткий текст', 140)).toBe('Короткий текст');
  });

  it('обрезает длинный текст и ставит многоточие', () => {
    const result = truncate('а'.repeat(50), 20);
    expect(result).toHaveLength(20);
    expect(result.endsWith('…')).toBe(true);
  });
});
