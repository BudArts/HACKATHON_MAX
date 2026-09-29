import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from './components/AppShell';
import { Alert, ScreenLoader } from './components/ui';
import { ConsentPage } from './pages/Consent';
import { DevLoginPage } from './pages/DevLogin';
import { HomePage } from './pages/Home';
import { LegalDocumentPage, LegalListPage } from './pages/Legal';
import { ParentLinkPage, ParentChildrenPage, ChildDigestPage } from './pages/Parent';
import { PersonalDataPage } from './pages/PersonalData';
import { SettingsPage } from './pages/Settings';
import { TeacherRiskPage } from './pages/Teacher';
import { TaskDetailPage } from './pages/TaskDetail';
import { TasksPage } from './pages/Tasks';
import { UnavailablePage } from './pages/Unavailable';
import { SessionProvider, useSession } from './state/session';
import type { Role } from './types';

function RoleGate({ allow, children }: { allow: Role[]; children: JSX.Element }): JSX.Element {
  const { user } = useSession();
  if (!user || !allow.includes(user.role)) {
    return <Alert tone="warning">Раздел недоступен для вашей роли.</Alert>;
  }
  return children;
}

function Cabinet(): JSX.Element {
  const { status, failure, signIn, onboardingRequired } = useSession();

  if (status === 'loading') {
    return (
      <div className="app">
        <main className="app__content app__content--flush">
          <ScreenLoader label="Проверяем вход через MAX" />
        </main>
      </div>
    );
  }

  if (status === 'dev-login') return <DevLoginPage />;

  if (status === 'unavailable' || status === 'anonymous') {
    return <UnavailablePage reason={failure} onRetry={() => void signIn()} />;
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/consent" element={<ConsentPage />} />
        <Route path="/legal" element={<LegalListPage />} />
        <Route path="/legal/:code" element={<LegalDocumentPage />} />
        {onboardingRequired ? (
          <Route path="*" element={<Navigate to="/consent" replace />} />
        ) : (
          <>
            <Route path="/" element={<HomePage />} />
            <Route
              path="/tasks"
              element={
                <RoleGate allow={['student']}>
                  <TasksPage />
                </RoleGate>
              }
            />
            <Route
              path="/tasks/:taskId"
              element={
                <RoleGate allow={['student']}>
                  <TaskDetailPage />
                </RoleGate>
              }
            />
            <Route
              path="/parent"
              element={
                <RoleGate allow={['parent', 'guest']}>
                  <ParentChildrenPage />
                </RoleGate>
              }
            />
            <Route
              path="/parent/link"
              element={
                <RoleGate allow={['parent', 'guest']}>
                  <ParentLinkPage />
                </RoleGate>
              }
            />
            <Route
              path="/parent/child/:childId"
              element={
                <RoleGate allow={['parent', 'guest']}>
                  <ChildDigestPage />
                </RoleGate>
              }
            />
            <Route
              path="/teacher/risk"
              element={
                <RoleGate allow={['teacher', 'administrator']}>
                  <TeacherRiskPage />
                </RoleGate>
              }
            />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/data" element={<PersonalDataPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        )}
      </Route>
    </Routes>
  );
}

export function App(): JSX.Element {
  return (
    <BrowserRouter>
      <SessionProvider>
        <Cabinet />
      </SessionProvider>
    </BrowserRouter>
  );
}
