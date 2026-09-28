import { useState } from 'react';

import { Topbar } from '../components/AppShell';
import { IconDownload, IconSearch } from '../components/icons';
import { Button, Page, PageHeader, cx } from '../components/ui';

const TABS = [
  ['all', 'All activity'],
  ['chat', 'Chats'],
  ['doc', 'Documents'],
  ['login', 'Sign-ins'],
  ['key', 'API keys'],
  ['settings', 'Settings'],
] as const;

export default function History() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('all');
  const [q, setQ] = useState('');
  const label = TABS.find((t) => t[0] === tab)![1];

  return (
    <>
      <Topbar title="History" />
      <Page>
        <PageHeader
          title="History"
          sub="Conversations and every change made in this workspace."
          action={
            <Button disabled title="Available once the activity log is wired up">
              <IconDownload size={15} />
              Export CSV
            </Button>
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
              <span className="rounded-full bg-surface2 px-[7px] py-px font-mono text-[11.5px] text-muted">0</span>
            </button>
          ))}
        </div>
        <div className="flex h-[42px] items-center gap-2.5 rounded-[10px] border border-border bg-surface px-3.5">
          <IconSearch className="text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={tab === 'all' ? 'Search all activity' : `Search ${label.toLowerCase()}`}
            className="flex-1 border-none bg-transparent text-[14.5px] text-text outline-none"
          />
        </div>
        <div className="p-8 text-center text-muted">No activity to show yet.</div>
      </Page>
    </>
  );
}
