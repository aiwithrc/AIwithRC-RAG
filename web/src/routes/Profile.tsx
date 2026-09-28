import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { endpoints, type Me } from '../api/client';
import { Topbar, initials } from '../components/AppShell';
import { IconChevronDown, IconMonitor } from '../components/icons';
import { ConfirmDialog } from '../components/Modal';
import { Button, Field, Page, Pill, Section, Spinner, TextInput, cx } from '../components/ui';
import { useKbs } from '../hooks/useKbs';
import { meKey, useMe } from '../hooks/useMe';
import { useTheme } from '../hooks/useTheme';
import { relativeTime } from '../lib/time';

function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('flex flex-col gap-4 rounded-[14px] border border-border bg-surface p-[18px]', className)}>
      {children}
    </div>
  );
}

function PersonalInfo({ me }: { me: Me }) {
  const qc = useQueryClient();
  const [name, setName] = useState(me.name);
  const [email, setEmail] = useState(me.email);
  const [saved, setSaved] = useState(false);
  const dirty = name.trim() !== me.name || email.trim().toLowerCase() !== me.email;

  const save = useMutation({
    mutationFn: () => endpoints.patchMe({ name: name.trim(), email: email.trim() }),
    onSuccess: (user) => {
      qc.setQueryData(meKey, user);
      setSaved(true);
    },
  });

  return (
    <Section title="Personal information">
      <Panel>
        <div className="flex flex-wrap gap-3.5">
          <Field label="Full name" className="min-w-[220px] flex-1">
            <TextInput value={name} autoComplete="name" onChange={(e) => (setName(e.target.value), setSaved(false))} />
          </Field>
          <Field label="Email" className="min-w-[220px] flex-1">
            <TextInput
              type="email"
              value={email}
              autoComplete="email"
              onChange={(e) => (setEmail(e.target.value), setSaved(false))}
            />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            className="h-[38px] px-4 text-[13.5px]"
            disabled={!dirty || !name.trim() || save.isPending}
            onClick={() => save.mutate()}
          >
            Save changes
          </Button>
          {saved && !dirty && <span className="text-[13px] text-ok-text">Saved</span>}
          {save.error && <span className="text-[13px] text-err-text">{save.error.message}</span>}
        </div>
      </Panel>
    </Section>
  );
}

function Password() {
  const [cur, setCur] = useState('');
  const [nw, setNw] = useState('');
  const [cf, setCf] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const save = useMutation({
    mutationFn: () => endpoints.changePassword({ current: cur, new: nw }),
    onSuccess: () => {
      setCur('');
      setNw('');
      setCf('');
      setMsg({ ok: true, text: 'Password updated' });
    },
    onError: (e) => setMsg({ ok: false, text: e.message }),
  });

  const submit = () => {
    const err = !cur
      ? 'Enter your current password.'
      : nw.length < 10
        ? 'New password needs at least 10 characters.'
        : nw !== cf
          ? "Passwords don't match."
          : '';
    if (err) return setMsg({ ok: false, text: err });
    save.mutate();
  };
  const edit = (set: (v: string) => void) => (e: { target: { value: string } }) => {
    set(e.target.value);
    setMsg(null);
  };

  return (
    <Section title="Password">
      <Panel>
        <Field label="Current password" className="max-w-[360px]">
          <TextInput type="password" autoComplete="current-password" placeholder="••••••••" value={cur} onChange={edit(setCur)} />
        </Field>
        <div className="flex flex-wrap gap-3.5">
          <Field label="New password" className="min-w-[220px] flex-1">
            <TextInput type="password" autoComplete="new-password" placeholder="At least 10 characters" value={nw} onChange={edit(setNw)} />
          </Field>
          <Field label="Confirm new password" className="min-w-[220px] flex-1">
            <TextInput type="password" autoComplete="new-password" placeholder="Repeat new password" value={cf} onChange={edit(setCf)} />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button className="h-[38px]" onClick={submit} disabled={save.isPending}>
            Update password
          </Button>
          {msg && <span className={cx('text-[13px]', msg.ok ? 'text-ok-text' : 'text-err-text')}>{msg.text}</span>}
        </div>
      </Panel>
    </Section>
  );
}

function Sessions() {
  const qc = useQueryClient();
  const { data: sessions, isLoading } = useQuery({ queryKey: ['sessions'], queryFn: endpoints.sessions });
  const refresh = () => qc.invalidateQueries({ queryKey: ['sessions'] });
  const revoke = useMutation({ mutationFn: endpoints.revokeSession, onSuccess: refresh });
  const revokeOthers = useMutation({ mutationFn: endpoints.revokeOtherSessions, onSuccess: refresh });
  const hasOthers = sessions?.some((s) => !s.current);

  return (
    <Section
      title="Active sessions"
      action={
        hasOthers && (
          <button
            type="button"
            onClick={() => revokeOthers.mutate()}
            className="border-none bg-transparent p-0 text-[13px] font-medium text-err-text"
          >
            Sign out all other sessions
          </button>
        )
      }
    >
      <div className="rounded-[14px] border border-border bg-surface [&>*+*]:border-t [&>*+*]:border-border">
        {isLoading && (
          <div className="p-4">
            <Spinner />
          </div>
        )}
        {sessions?.map((s) => (
          <div key={s.id} className="flex flex-wrap items-center gap-3.5 px-[18px] py-3.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface2 text-muted">
              <IconMonitor />
            </span>
            <div className="flex min-w-[180px] flex-1 flex-col gap-[3px]">
              <span className="text-[14px] font-medium">{s.device}</span>
              <span className="text-[12.5px] text-muted">
                {s.ip || 'unknown IP'} · {s.current ? 'Active now' : `Last active ${relativeTime(s.last_seen_at)}`}
              </span>
            </div>
            {s.current ? (
              <Pill tone="ok" className="px-2 py-0.5 text-[11.5px]">
                This device
              </Pill>
            ) : (
              <Button className="h-8" onClick={() => revoke.mutate(s.id)} disabled={revoke.isPending}>
                Sign out
              </Button>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

function Preferences({ me }: { me: Me }) {
  const { theme, setTheme } = useTheme();
  const { data: kbs } = useKbs();
  const qc = useQueryClient();
  const setDefaultKb = useMutation({
    mutationFn: (id: string) => endpoints.patchMe({ default_kb_id: id }),
    onSuccess: (user) => qc.setQueryData(meKey, user),
  });
  const seg = (t: 'light' | 'dark') =>
    cx(
      'h-[30px] rounded-[7px] border-none px-3.5 text-[13px] font-medium',
      theme === t ? 'bg-surface text-text' : 'bg-transparent text-muted',
    );

  return (
    <Section title="Preferences">
      <div className="rounded-[14px] border border-border bg-surface [&>*+*]:border-t [&>*+*]:border-border">
        <div className="flex flex-wrap items-center gap-3 px-[18px] py-4">
          <div className="min-w-[180px] flex-1">
            <div className="text-[14px] font-medium">Theme</div>
            <div className="text-[12.5px] text-muted">Only affects your account.</div>
          </div>
          <div className="flex gap-0.5 rounded-[9px] bg-surface2 p-[3px]" role="radiogroup" aria-label="Theme">
            <button type="button" role="radio" aria-checked={theme === 'light'} className={seg('light')} onClick={() => setTheme('light')}>
              Light
            </button>
            <button type="button" role="radio" aria-checked={theme === 'dark'} className={seg('dark')} onClick={() => setTheme('dark')}>
              Dark
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 px-[18px] py-4">
          <div className="min-w-[180px] flex-1">
            <div className="text-[14px] font-medium">Default knowledge base</div>
            <div className="text-[12.5px] text-muted">Selected when you start a new chat.</div>
          </div>
          <div className="relative min-w-[220px]">
            <select
              value={me.default_kb_id ?? ''}
              onChange={(e) => setDefaultKb.mutate(e.target.value)}
              aria-label="Default knowledge base"
              className="h-[38px] w-full appearance-none rounded-[9px] border border-border bg-surface pl-3 pr-[34px] text-[13.5px] text-text outline-none"
            >
              {!me.default_kb_id && <option value="">Choose…</option>}
              {kbs?.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
            <IconChevronDown className="pointer-events-none absolute right-3 top-3 text-muted" />
          </div>
        </div>
      </div>
    </Section>
  );
}

function DangerZone() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const del = useMutation({
    mutationFn: endpoints.deleteMe,
    onSuccess: () => {
      qc.clear();
      qc.setQueryData(meKey, null);
      navigate('/login');
    },
  });

  return (
    <Section title={<span className="text-err-text">Danger zone</span>}>
      <div className="flex flex-wrap items-center gap-3 rounded-[14px] border border-err-soft bg-surface px-[18px] py-4">
        <div className="min-w-[200px] flex-1">
          <div className="text-[14px] font-medium">Delete account</div>
          <div className="text-[12.5px] text-muted">
            Removes your account, chats and sessions. Knowledge bases stay with the workspace.
          </div>
        </div>
        <Button variant="danger" onClick={() => (del.reset(), setOpen(true))}>
          Delete account
        </Button>
      </div>
      <ConfirmDialog
        open={open}
        title="Delete your account?"
        body="This signs you out everywhere and permanently removes your account and chats. It can't be undone."
        confirmLabel="Delete account"
        danger
        busy={del.isPending}
        error={del.error?.message}
        onConfirm={() => del.mutate()}
        onClose={() => setOpen(false)}
      />
    </Section>
  );
}

export default function Profile() {
  const { data: me } = useMe();
  useEffect(() => window.scrollTo(0, 0), []);
  if (!me) return null;

  return (
    <>
      <Topbar title="My profile" />
      <Page>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[22px] font-semibold text-accent-text">
            {initials(me.name)}
          </div>
          <div className="flex min-w-[180px] flex-1 flex-col gap-1">
            <h1 className="m-0 text-[24px] font-semibold tracking-[-0.02em]">{me.name}</h1>
            <div className="text-[14px] text-muted">
              {me.email} · {me.role === 'owner' ? 'Owner' : 'Member'}
            </div>
          </div>
        </div>
        <PersonalInfo me={me} />
        <Password />
        <Sessions />
        <Preferences me={me} />
        <DangerZone />
      </Page>
    </>
  );
}
