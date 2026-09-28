/** Small shared UI pieces matching the prototype's styles. Colours only via token classes. */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react';

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ');
}

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        className="flex items-center justify-center bg-accent font-mono font-semibold text-on-accent"
        style={{ width: size, height: size, borderRadius: size * 0.28, fontSize: size * 0.43 }}
      >
        RC
      </div>
      <div className="text-[15px] font-semibold">
        AIwithRC<span className="font-medium text-muted">-RAG</span>
      </div>
    </div>
  );
}

type Tone = 'ok' | 'warn' | 'err' | 'accent' | 'neutral';

const pillTone: Record<Tone, string> = {
  ok: 'bg-ok-soft text-ok-text',
  warn: 'bg-warn-soft text-warn-text',
  err: 'bg-err-soft text-err-text',
  accent: 'bg-accent-soft text-accent-text',
  neutral: 'bg-surface2 text-muted',
};

export function Pill({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-[9px] py-[3px] text-[12px] font-medium',
        pillTone[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link';

const btnVariant: Record<BtnVariant, string> = {
  primary: 'border-none bg-accent font-semibold text-on-accent hover:brightness-[1.08]',
  secondary: 'border border-border bg-surface font-medium text-text hover:bg-surface2',
  ghost: 'border-none bg-transparent text-muted hover:bg-surface2 hover:text-text',
  danger: 'border border-border bg-surface font-medium text-err-text hover:bg-err-soft',
  link: 'border-none bg-transparent p-0 font-medium text-accent-text',
};

export function Button({
  variant = 'secondary',
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  return (
    <button
      type="button"
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-[9px] text-[13px] transition-[filter,background] disabled:opacity-45',
        variant !== 'link' && 'h-9 px-3.5',
        btnVariant[variant],
        className,
      )}
      {...rest}
    />
  );
}

export function TextInput({ className, mono, ...rest }: InputHTMLAttributes<HTMLInputElement> & { mono?: boolean }) {
  return (
    <input
      className={cx(
        'h-10 w-full rounded-[9px] border border-border bg-surface px-3 text-[14px] text-text outline-none focus:border-accent',
        mono && 'font-mono',
        className,
      )}
      {...rest}
    />
  );
}

export function Field({ label, children, className }: { label: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx('flex flex-col gap-1.5 text-[13px] font-medium', className)}>
      {label}
      {children}
    </label>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={cx(
        'flex h-[22px] w-[38px] shrink-0 rounded-full border-none p-[3px] transition-colors',
        on ? 'justify-end bg-accent' : 'justify-start bg-border-strong',
      )}
    >
      <span className="block h-4 w-4 rounded-full bg-on-accent" />
    </button>
  );
}

export function PageHeader({ title, sub, action }: { title: ReactNode; sub?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex max-w-[560px] flex-col gap-1.5">
        <h1 className="m-0 text-[26px] font-semibold tracking-[-0.02em]">{title}</h1>
        {sub && <p className="m-0 text-[14.5px] leading-[1.55] text-muted text-pretty">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function Section({ title, children, action }: { title: ReactNode; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[15px] font-semibold">{title}</div>
        {action}
      </div>
      {children}
    </div>
  );
}

/** Bordered card whose direct <Row> children are separated by lines. */
export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('rounded-xl border border-border bg-surface [&>*+*]:border-t [&>*+*]:border-border', className)}>
      {children}
    </div>
  );
}

export function Row({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3 px-[18px] py-4">
      <div className="min-w-[200px] flex-1">
        <div className="text-[14px] font-medium">{title}</div>
        {sub && <div className="text-[12.5px] text-muted">{sub}</div>}
      </div>
      {children}
    </div>
  );
}

export function Page({ children, width = 820 }: { children: ReactNode; width?: number }) {
  return (
    <div className="flex-1 overflow-auto">
      <div
        className="mx-auto flex flex-col gap-6 px-4 pb-14 pt-8 min-[820px]:px-8"
        style={{ maxWidth: width }}
      >
        {children}
      </div>
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border-strong p-7 text-center text-[13.5px] text-muted">
      {children}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cx('inline-block h-4 w-4 animate-spin rounded-full border-2 border-border border-t-accent', className)}
      role="status"
      aria-label="Loading"
    />
  );
}

export function FullPageSpinner() {
  return (
    <div className="flex h-full items-center justify-center">
      <Spinner />
    </div>
  );
}
