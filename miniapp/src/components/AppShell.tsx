import { useEffect } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { bindBackButton, releaseBackButton } from '../lib/max';
import { formatInitials } from '../lib/format';
import { useSession } from '../state/session';
import type { Role } from '../types';

interface Tab {
  to: string;
  label: string;
  icon: string;
  roles: Role[];
}

const TABS: Tab[] = [
  { to: '/', label: 'Главная', icon: '⌂', roles: ['student', 'parent', 'teacher', 'administrator', 'guest'] },
  { to: '/tasks', label: 'Задачи', icon: '∑', roles: ['student'] },
  { to: '/parent', label: 'Дети', icon: '⚑', roles: ['parent', 'guest'] },
  { to: '/teacher/risk', label: 'Риск', icon: '⚑', roles: ['teacher', 'administrator'] },
  { to: '/settings', label: 'Кабинет', icon: '⚙', roles: ['student', 'parent', 'teacher', 'administrator', 'guest'] },
];

const TITLES: Record<string, { title: string; subtitle?: string }> = {
  '/': { title: 'УчусьИИ' },
  '/tasks': { title: 'Мои задачи' },
  '/parent': { title: 'Мои дети' },
  '/parent/link': { title: 'Привязка ребёнка' },
  '/parent/child': { title: 'Недельный дайджест' },
  '/teacher/risk': { title: 'Группа риска' },
  '/settings': { title: 'Личный кабинет' },
  '/settings/data': { title: 'Персональные данные' },
  '/legal': { title: 'Документы' },
};

export function AppShell(): JSX.Element {
  const { user, onboardingRequired } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const role: Role = user?.role ?? 'guest';

  const matched = Object.keys(TITLES)
    .filter((path) => location.pathname === path || (path !== '/' && location.pathname.startsWith(path)))
    .sort((a, b) => b.length - a.length)[0];
  const heading = (matched ? TITLES[matched] : undefined) ?? { title: 'УчусьИИ' };
  const detail =
    location.pathname.startsWith('/tasks/') || location.pathname.startsWith('/parent/child/');

  const tabs = TABS.filter((tab) => tab.roles.includes(role));
  const isTabRoute = TABS.some((tab) => tab.to === location.pathname);
  const showTabs = !onboardingRequired && isTabRoute && tabs.length > 1;

  useEffect(() => {
    if (isTabRoute) {
      releaseBackButton();
      return undefined;
    }
    return bindBackButton(() => navigate(-1));
  }, [isTabRoute, navigate]);

  return (
    <div className="app">
      <header className="app__header">
        {detail && (
          <button className="icon-button" type="button" aria-label="Назад" onClick={() => navigate(-1)}>
            ‹
          </button>
        )}
        <div className="grow">
          <div className="app__title">{detail ? 'Обращение' : heading.title}</div>
          {user && (
            <div className="app__subtitle">
              {formatInitials(user.first_name, user.last_name)} · {roleLabel(role)}
            </div>
          )}
        </div>
      </header>

      <main className={showTabs ? 'app__content' : 'app__content app__content--flush'}>
        <Outlet />
      </main>

      {showTabs && (
        <nav className="tabbar">
          {tabs.map((tab) => (
            <NavLink key={tab.to} to={tab.to} end={tab.to === '/'} className="tabbar__item">
              <span className="tabbar__icon" aria-hidden>
                {tab.icon}
              </span>
              <span>{tab.label}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}

export function roleLabel(role: Role): string {
  switch (role) {
    case 'student':
      return 'ученик';
    case 'parent':
      return 'родитель';
    case 'teacher':
      return 'педагог';
    case 'administrator':
      return 'администратор';
    default:
      return 'роль не подтверждена';
  }
}
