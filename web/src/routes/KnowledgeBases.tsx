import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Topbar } from '../components/AppShell';
import { IconPlus } from '../components/icons';
import { NewKbDialog } from '../components/KbDialogs';
import { Button, Page, PageHeader, Pill, Spinner } from '../components/ui';
import { useKbs } from '../hooks/useKbs';
import { relativeTime } from '../lib/time';

export default function KnowledgeBases() {
  const { data: kbs, isLoading, error } = useKbs();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);

  return (
    <>
      <Topbar title="Knowledge bases" />
      <Page width={1080}>
        <PageHeader
          title="Knowledge bases"
          sub="Each knowledge base has its own documents and model. Local ones are never sent off this server."
          action={
            <Button variant="primary" className="h-[38px] text-[14px]" onClick={() => setCreating(true)}>
              <IconPlus />
              New knowledge base
            </Button>
          }
        />
        {isLoading && <Spinner />}
        {error && <div className="text-[13px] text-err-text">{error.message}</div>}
        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3.5">
          {kbs?.map((k) => (
            <button
              key={k.id}
              type="button"
              onClick={() => navigate(`/kbs/${k.id}`)}
              className="flex min-h-[170px] flex-col gap-3.5 rounded-[14px] border border-border bg-surface p-[18px] text-left text-text hover:border-border-strong hover:shadow-card"
            >
              <div className="flex w-full items-center justify-between gap-2.5">
                <span className="text-[15.5px] font-semibold">{k.name}</span>
                <Pill tone={k.runtime === 'local' ? 'ok' : 'accent'} className="px-2 text-[11.5px]">
                  {k.runtime === 'local' ? 'Local' : 'Cloud'}
                </Pill>
              </div>
              <div className="flex-1 text-[13.5px] leading-[1.5] text-muted">{k.description || 'No description yet'}</div>
              <div className="flex w-full justify-between gap-2.5 border-t border-border pt-3 text-[12.5px] text-muted">
                <span>
                  {k.doc_count} doc{k.doc_count === 1 ? '' : 's'} · {k.chunk_count.toLocaleString()} chunk{k.chunk_count === 1 ? '' : 's'}
                </span>
                <span>Updated {relativeTime(k.updated_at)}</span>
              </div>
            </button>
          ))}
        </div>
        <NewKbDialog open={creating} onClose={() => setCreating(false)} />
      </Page>
    </>
  );
}
