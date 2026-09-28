import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { endpoints } from '../api/client';
import { IconServer } from '../components/icons';
import { FullPageSpinner, Logo } from '../components/ui';
import { useIsMobile } from '../hooks/useMediaQuery';
import { meKey, useMe } from '../hooks/useMe';

const inputClass =
  'h-[42px] rounded-[10px] border border-border bg-surface px-3 text-[14.5px] font-normal text-text outline-none focus:border-accent';

export default function Login() {
  const { data: me, isLoading } = useMe();
  const cfg = useQuery({ queryKey: ['auth-config'], queryFn: endpoints.authConfig });
  const mobile = useIsMobile();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const [mode, setMode] = useState<'in' | 'up'>('in');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showForgot, setShowForgot] = useState(false);

  // A fresh install has no users yet: go straight to "Create your workspace".
  useEffect(() => {
    if (cfg.data && !cfg.data.has_users) setMode('up');
  }, [cfg.data]);

  const submit = useMutation({
    mutationFn: () =>
      mode === 'up' ? endpoints.signup({ name, email, password }) : endpoints.login({ email, password }),
    onSuccess: (user) => {
      qc.setQueryData(meKey, user);
      qc.invalidateQueries({ queryKey: ['auth-config'] });
      navigate(from, { replace: true });
    },
  });

  if (isLoading) return <FullPageSpinner />;
  if (me) return <Navigate to={from} replace />;

  const signUp = mode === 'up';
  const canSignUp = cfg.data?.signup_open ?? false;
  const firstUser = cfg.data ? !cfg.data.has_users : false;
  const copy = signUp
    ? {
        title: firstUser ? 'Create your workspace' : 'Create an account',
        sub: firstUser ? 'Set up the admin account for this server.' : 'Join this knowledge workspace.',
        cta: 'Create account',
        switchText: 'Already have an account?',
        switchCta: 'Sign in',
      }
    : {
        title: 'Sign in',
        sub: 'Welcome back to your knowledge workspace.',
        cta: 'Sign in',
        switchText: 'New here?',
        switchCta: 'Create an account',
      };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit.mutate();
  };

  return (
    <div className="flex h-full overflow-auto">
      <div className="flex min-w-0 flex-1 flex-col p-7">
        <Logo />
        <div className="flex flex-1 items-center justify-center py-8">
          <form onSubmit={onSubmit} className="flex w-full max-w-[360px] flex-col gap-[18px]" noValidate>
            <div className="flex flex-col gap-1.5">
              <h1 className="m-0 text-[26px] font-semibold tracking-[-0.02em]">{copy.title}</h1>
              <p className="m-0 text-[14.5px] text-muted">{copy.sub}</p>
            </div>
            {signUp && (
              <label className="flex flex-col gap-1.5 text-[13px] font-medium">
                Name
                <input
                  className={inputClass}
                  placeholder="Your name"
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </label>
            )}
            <label className="flex flex-col gap-1.5 text-[13px] font-medium">
              Email
              <input
                className={inputClass}
                type="email"
                placeholder="you@company.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1.5 text-[13px] font-medium">
              <span className="flex justify-between">
                Password
                {!signUp && (
                  <button
                    type="button"
                    onClick={() => setShowForgot((v) => !v)}
                    className="border-none bg-transparent p-0 text-[13px] font-medium text-accent-text"
                  >
                    Forgot password?
                  </button>
                )}
              </span>
              <input
                className={inputClass}
                type="password"
                placeholder={signUp ? 'At least 10 characters' : '••••••••'}
                autoComplete={signUp ? 'new-password' : 'current-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            {showForgot && !signUp && (
              <div className="rounded-[10px] bg-surface2 px-3.5 py-3 text-[13px] leading-[1.6] text-muted">
                Ask the server owner to reset it. On the server, run:
                <code className="mt-1.5 block break-all font-mono text-[12px] text-text">
                  docker compose exec app python -m app.cli reset-password --email you@company.com
                </code>
              </div>
            )}
            {submit.error && (
              <div className="text-[13px] text-err-text" role="alert">
                {submit.error.message}
              </div>
            )}
            <button
              type="submit"
              disabled={submit.isPending}
              className="h-11 rounded-[10px] border-none bg-accent text-[14.5px] font-semibold text-on-accent hover:brightness-[1.08] disabled:opacity-60"
            >
              {submit.isPending ? 'One moment…' : copy.cta}
            </button>
            {(canSignUp || signUp) && !firstUser && (
              <div className="flex justify-center gap-1.5 text-[13.5px] text-muted">
                {copy.switchText}
                <button
                  type="button"
                  onClick={() => {
                    setMode(signUp ? 'in' : 'up');
                    submit.reset();
                  }}
                  className="border-none bg-transparent p-0 text-[13.5px] font-medium text-accent-text"
                >
                  {copy.switchCta}
                </button>
              </div>
            )}
          </form>
        </div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted">
          <IconServer />
          Self-hosted workspace · {cfg.data?.public_host ?? window.location.host}
        </div>
      </div>
      {!mobile && (
        <div className="flex min-w-0 flex-1 items-center justify-center bg-accent-soft p-12">
          <div className="flex max-w-[460px] flex-col gap-7">
            <div className="flex flex-col gap-2.5">
              <h2 className="m-0 text-[34px] font-semibold leading-[1.1] tracking-[-0.025em] text-balance">
                Answers you can check.
              </h2>
              <p className="m-0 text-[16px] leading-[1.55] text-muted text-pretty">
                Every response links to the exact passage it came from. Your documents stay on your own server.
              </p>
            </div>
            <div className="flex flex-col gap-3.5 rounded-2xl border border-border bg-surface p-5 shadow-card">
              <div className="text-[13px] text-muted">What's the termination notice period?</div>
              <div className="text-[15px] leading-[1.65]">
                Either party can terminate with <strong className="font-semibold">60 days' written notice</strong>{' '}
                <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[5px] bg-accent align-[2px] font-mono text-[11px] font-semibold text-on-accent">
                  1
                </span>
              </div>
              <div className="rounded-[10px] bg-surface2 px-3.5 py-3 text-[13px] leading-[1.6] text-muted">
                <div className="mb-1.5 font-mono text-[11.5px]">Acme_MSA_2024.pdf · p. 14</div>
                11.2 Termination for Convenience.{' '}
                <mark className="rounded-[3px] bg-hl px-0.5 py-px text-text">
                  Either party may terminate this Agreement for any reason upon sixty (60) days' prior written notice.
                </mark>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
