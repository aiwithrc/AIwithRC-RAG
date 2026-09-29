import { useInfiniteQuery } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { endpoints, type ActivityEvent, type EventCategory } from '../api/client';
import { Topbar } from '../components/AppShell';
import { IconChat, IconDownload, IconKey, IconSearch, IconSliders } from '../components/icons';
import { Button, Page, PageHeader, Pill, Spinner, cx } from '../components/ui';
import { parseUtc } from '../lib/time';

const TABS: [('all' | EventCategory), string][] = [
  ['all', 'All activity'],
  ['chat', 'Chats'],
  ['doc', 'Documents'],
  ['login', 'Sign-ins'],
  ['key', 'API keys'],
  ['settings', 'Settings'],
];

function DocIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function LoginIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
      <polyline points="10 17 15 12 10 7" />
      <line x1="15" y1="12" x2="3" y2="12" />
    </svg>
  );
}

const ICON: Record<EventCategory, { el: ReactNode; cls: string }> = {
  chat: { el: <IconChat size={15} />, cls: 'bg-accent-soft text-accent-text' },
  doc: { el: <DocIcon />, cls: 'bg-surface2 text-text' },
  login: { el: <LoginIcon />, cls: 'bg-ok-soft text-ok-text' },
  key: { el: <IconKey size={15} />, cls: 'bg-warn-soft text-warn-text' },
  settings: { el: <IconSliders size={15} />, cls: 'bg-surface2 text-muted' },
};

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function groupOf(d: Date, now: Date): string {
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return 'Previous 7 days';
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

function timeOf(d: Date, group: string): string {
  if (group === 'Today' || group === 'Yesterday') return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (group === 'Previous 7 days') return d.toLocaleDateString(undefined, { weekday: 'short' });
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function History() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<'all' | EventCategory>('all');
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const events = useInfiniteQuery({
    queryKey: ['events', tab, debounced],
    queryFn: ({ pageParam }) =>
      endpoints.events({ category: tab === 'all' ? undefined : tab, q: debounced || undefined, cursor: pageParam || undefined }),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items: ActivityEvent[] = events.data?.pages.flatMap((p) => p.items) ?? [];
  const counts = events.data?.pages[0]?.counts;

  const now = new Date();
  const groups: { label: string; items: (ActivityEvent & { at: Date })[] }[] = [];
  for (const e of items) {
    const at = parseUtc(e.created_at);
    const label = groupOf(at, now);
    let g = groups.find((x) => x.label === label);
    if (!g) groups.push((g = { label, items: [] }));
    g.items.push({ ...e, at });
  }
  const label = TABS.find((t) => t[0] === tab)![1];
  const csv = `/api/events.csv?${new URLSearchParams({ ...(tab !== 'all' ? { category: tab } : {}), ...(debounced ? { q: debounced } : {}) })}`;

  return (
    <>
      <Topbar title="History" />
      <Page>
        <PageHeader
          title="History"
          sub="Conversations and every change made in this workspace."
          action={
            <a href={csv} download className="hover:no-underline">
              <Button>
                <IconDownload size={15} />
                Export CSV
              </Button>
            </a>
          }
        />
        <div className="-mb-2 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-border [scrollbar-width:none]">
          {TABS.map(([id, text]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={cx(
                'flex h-10 items-center gap-[7px] whitespace-nowrap border-x-0 border-b-2 border-t-0 bg-transparent px-3 text-[13.5px] font-medium hover:text-text',
                tab === id ? 'border-accent text-text' : 'border-transparent text-muted',
              )}
            >
              {text}
              <span className="rounded-full bg-surface2 px-[7px] py-px font-mono text-[11.5px] text-muted">{counts?.[id] ?? '·'}</span>
            </button>
          ))}
        </div>
        <div className="flex h-[42px] items-center gap-2.5 rounded-[10px] border border-border bg-surface px-3.5">
          <IconSearch className="text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={tab === 'all' ? 'Search all activity' : `Search ${label.toLowerCase()}`}
            aria-label="Search history"
            className="flex-1 border-none bg-transparent text-[14.5px] text-text outline-none"
          />
        </div>
        {events.isLoading && <Spinner />}
        {events.error && <div className="text-[13px] text-err-text">{events.error.message}</div>}
        {groups.map((g) => (
          <div key={g.label} className="flex flex-col gap-1.5">
            <div className="px-1 text-[12.5px] font-medium text-muted">{g.label}</div>
            <div className="overflow-hidden rounded-xl border border-border bg-surface">
              {g.items.map((h) => (
                <button
                  key={h.id}
                  type="button"
                  onClick={() => h.link && navigate(h.link)}
                  className={cx(
                    'flex w-full items-center gap-3.5 border-x-0 border-b border-t-0 border-border bg-transparent px-4 py-[13px] text-left text-text last:border-b-0 hover:bg-surface2',
                    h.link ? 'cursor-pointer' : 'cursor-default',
                  )}
                >
                  <span className={cx('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', ICON[h.category].cls)}>
                    {ICON[h.category].el}
                  </span>
                  <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
                    <span className="truncate text-[14px] font-medium">{h.title}</span>
                    <span className="truncate text-[12.5px] text-muted">{h.detail}</span>
                  </div>
                  {h.tag && (
                    <Pill tone={h.tone === 'ok' ? 'ok' : h.tone === 'err' ? 'err' : h.tone === 'accent' ? 'accent' : 'neutral'} className="px-2 py-0.5 text-[11.5px]">
                      {h.tag}
                    </Pill>
                  )}
                  <span className="min-w-[52px] whitespace-nowrap text-right text-[12.5px] text-muted">{timeOf(h.at, g.label)}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
        {events.data && items.length === 0 && (
          <div className="p-8 text-center text-muted">{debounced ? `Nothing matches "${debounced}".` : 'No activity yet.'}</div>
        )}
        {events.hasNextPage && (
          <Button className="self-center" onClick={() => events.fetchNextPage()} disabled={events.isFetchingNextPage}>
            {events.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </Button>
        )}
      </Page>
    </>
  );
}
