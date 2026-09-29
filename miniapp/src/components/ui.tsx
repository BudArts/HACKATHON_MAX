import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  block?: boolean;
  small?: boolean;
  loading?: boolean;
}

export function Button({ variant = 'primary', block, small, loading, children, disabled, ...rest }: ButtonProps): JSX.Element {
  const classes = ['button', `button--${variant}`];
  if (block) classes.push('button--block');
  if (small) classes.push('button--sm');
  return (
    <button className={classes.join(' ')} disabled={disabled || loading} {...rest}>
      {loading ? <Spinner /> : children}
    </button>
  );
}

export function Spinner(): JSX.Element {
  return <span className="spinner" role="status" aria-label="Загрузка" />;
}

export function ScreenLoader({ label = 'Загрузка' }: { label?: string | undefined }): JSX.Element {
  return (
    <div className="screen-loader">
      <Spinner />
      <span className="muted">{label}</span>
    </div>
  );
}

export function Card({
  title,
  hint,
  tight,
  children,
  actions,
}: {
  title?: string | undefined;
  hint?: string | undefined;
  tight?: boolean | undefined;
  children: ReactNode;
  actions?: ReactNode | undefined;
}): JSX.Element {
  return (
    <section className={tight ? 'card card--tight' : 'card'}>
      {(title || actions) && (
        <header className="card__header">
          <div>
            {title && <h2 className="card__title">{title}</h2>}
            {hint && <div className="card__hint">{hint}</div>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function SectionTitle({ children }: { children: ReactNode }): JSX.Element {
  return <div className="section-title">{children}</div>;
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string | undefined;
  error?: string | null | undefined;
  children: ReactNode;
}): JSX.Element {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {error ? <span className="field__error">{error}</span> : hint ? <span className="field__hint">{hint}</span> : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>): JSX.Element {
  return <input className="input" {...props} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>): JSX.Element {
  return <textarea className="textarea" {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>): JSX.Element {
  return <select className="select" {...props} />;
}

export type Tone = 'neutral' | 'info' | 'accent' | 'success' | 'warning' | 'danger';

export function Pill({ tone = 'neutral', children }: { tone?: Tone | undefined; children: ReactNode }): JSX.Element {
  const suffix = tone === 'neutral' || tone === 'info' ? '' : ` pill--${tone}`;
  return <span className={`pill${suffix}`}>{children}</span>;
}

export function Alert({ tone = 'info', children }: { tone?: Tone | undefined; children: ReactNode }): JSX.Element {
  const resolved = tone === 'neutral' ? 'info' : tone;
  return <div className={`alert alert--${resolved}`}>{children}</div>;
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string | undefined;
  action?: ReactNode | undefined;
}): JSX.Element {
  return (
    <div className="empty">
      <div className="empty__title">{title}</div>
      {description && <div className="muted">{description}</div>}
      {action}
    </div>
  );
}

export function Stat({ value, label }: { value: ReactNode; label: string }): JSX.Element {
  return (
    <div className="stat">
      <div className="stat__value">{value}</div>
      <div className="stat__label">{label}</div>
    </div>
  );
}
