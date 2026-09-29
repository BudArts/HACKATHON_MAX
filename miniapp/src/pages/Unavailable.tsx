import { Button, Card } from '../components/ui';
import { isInsideMax } from '../lib/max';

export function UnavailablePage({ reason, onRetry }: { reason: string | null; onRetry: () => void }): JSX.Element {
  return (
    <div className="app">
      <header className="app__header">
        <div className="app__title">Обращения</div>
      </header>
      <main className="app__content app__content--flush">
        <div className="stack">
          <Card title="Вход не выполнен">
            <div className="stack">
              <p className="muted">
                {reason ?? 'Не удалось подтвердить вход через MAX.'}
              </p>
              {!isInsideMax() && (
                <p className="muted">
                  Личный кабинет открывается только внутри мессенджера MAX: найдите бота школы и нажмите
                  «Личный кабинет».
                </p>
              )}
              <Button block onClick={onRetry}>
                Повторить вход
              </Button>
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
