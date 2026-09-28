import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import type { Kb } from '../api/client';
import { Topbar } from '../components/AppShell';
import { Dropdown, DropdownItem } from '../components/Dropdown';
import { IconArrowUp, IconBook, IconLock, IconUpload } from '../components/icons';
import { Pill, cx } from '../components/ui';
import { useKbs } from '../hooks/useKbs';
import { useIsMobile } from '../hooks/useMediaQuery';
import { useMe } from '../hooks/useMe';

function runtimePill(kb: Kb) {
  return kb.runtime === 'local' ? (
    <Pill tone="ok" className="px-[7px] py-0.5 text-[11px]">
      Local
    </Pill>
  ) : (
    <Pill tone="accent" className="px-[7px] py-0.5 text-[11px]">
      Cloud
    </Pill>
  );
}

export default function Chat() {
  const { data: me } = useMe();
  const { data: kbs } = useKbs();
  const mobile = useIsMobile();
  const navigate = useNavigate();
  const location = useLocation();
  const [kbId, setKbId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  // "New chat" resets to the user's default knowledge base.
  const fresh = (location.state as { fresh?: number } | null)?.fresh;
  useEffect(() => {
    setKbId(null);
    setDraft('');
  }, [fresh]);

  const kb = kbs?.find((k) => k.id === kbId) ?? kbs?.find((k) => k.id === me?.default_kb_id) ?? kbs?.[0];
  const kbName = kb?.name ?? 'your documents';

  return (
    <>
      <Topbar title="New chat">
        <Dropdown
          heading="Search in"
          leading={<IconBook size={15} className="shrink-0" />}
          label={kb?.name ?? 'No knowledge base'}
          footer={(close) => (
            <button
              type="button"
              onClick={() => {
                close();
                navigate('/kbs');
              }}
              className="w-full rounded-lg border-none bg-transparent px-2.5 py-2 text-left text-[13px] font-medium text-accent-text hover:bg-surface2"
            >
              Manage knowledge bases
            </button>
          )}
        >
          {(close) =>
            (kbs ?? []).map((k) => (
              <DropdownItem
                key={k.id}
                selected={k.id === kb?.id}
                onSelect={() => {
                  setKbId(k.id);
                  close();
                }}
                trailing={runtimePill(k)}
              >
                <div className="text-[13.5px] font-medium">{k.name}</div>
                <div className="text-[12px] text-muted">{k.doc_count} docs</div>
              </DropdownItem>
            ))
          }
        </Dropdown>
        <Dropdown
          heading="Answer with"
          width={280}
          leading={<span className="h-[7px] w-[7px] shrink-0 rounded-full bg-border-strong" />}
          label="No model"
        >
          {(close) => (
            <div className="flex flex-col gap-2 px-2.5 pb-2.5 pt-1 text-[13px] leading-[1.5] text-muted">
              No model provider connected yet.
              <Link to="/keys" onClick={close} className="font-medium">
                Connect one on the API keys screen
              </Link>
            </div>
          )}
        </Dropdown>
      </Topbar>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div
          className="mx-auto flex max-w-[680px] flex-col gap-[22px] px-4 pb-10 min-[820px]:px-8"
          style={{ paddingTop: mobile ? 40 : '11vh' }}
        >
          <div className="flex flex-col items-center gap-3 text-center">
            {kb?.runtime === 'cloud' ? (
              <Pill tone="warn" className="px-[11px] py-[5px] text-[12.5px]">
                <IconLock />
                Cloud knowledge base · passages sent via API
              </Pill>
            ) : (
              <Pill tone="ok" className="px-[11px] py-[5px] text-[12.5px]">
                <IconLock />
                Private · runs on your server
              </Pill>
            )}
            <h1
              className="m-0 font-semibold leading-[1.1] tracking-[-0.025em] text-balance"
              style={{ fontSize: mobile ? 28 : 38 }}
            >
              Ask your documents anything
            </h1>
            <p className="m-0 max-w-[460px] text-[15.5px] leading-[1.55] text-muted text-pretty">
              Answers cite the exact passage they came from, so you can check every claim.
            </p>
          </div>

          <form
            onSubmit={(e) => e.preventDefault()}
            className="flex flex-col gap-1.5 rounded-2xl border border-border bg-surface py-2.5 pl-4 pr-2.5 shadow-card"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={`Ask anything about ${kbName}…`}
              aria-label="Question"
              className="w-full border-none bg-transparent py-2 text-[15.5px] text-text outline-none"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => kb && navigate(`/kbs/${kb.id}`)}
                className="flex h-[30px] items-center gap-1.5 rounded-lg border border-border bg-transparent pl-2 pr-2.5 text-[12.5px] text-muted hover:bg-surface2 hover:text-text"
              >
                <IconUpload size={14} />
                Add file
              </button>
              <div className="flex-1" />
              <button
                type="submit"
                disabled
                title="Answering is not available yet"
                aria-label="Send"
                className={cx(
                  'flex h-[34px] w-[34px] items-center justify-center rounded-[10px] border-none bg-accent text-on-accent',
                  draft.trim() ? 'opacity-100' : 'opacity-45',
                )}
              >
                <IconArrowUp />
              </button>
            </div>
          </form>

          <button
            type="button"
            onClick={() => kb && navigate(`/kbs/${kb.id}`)}
            className="flex w-full items-center gap-3.5 rounded-[14px] border-[1.5px] border-dashed border-border-strong bg-transparent p-[18px] text-left text-text hover:border-accent hover:bg-accent-soft"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-accent-soft text-accent-text">
              <IconUpload size={18} />
            </div>
            <div className="flex min-w-0 flex-col gap-[3px]">
              <div className="text-[14px] font-semibold">Drop a document to start</div>
              <div className="text-[13px] text-muted">
                PDF, DOCX, MD, TXT, CSV or XLSX. Indexed into {kbName} in seconds.
              </div>
            </div>
          </button>
        </div>
      </div>
    </>
  );
}
