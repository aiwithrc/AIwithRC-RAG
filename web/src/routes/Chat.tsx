import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import type { Kb } from '../api/client';
import { Topbar } from '../components/AppShell';
import { Dropdown, DropdownItem } from '../components/Dropdown';
import { IconArrowUp, IconBook, IconLock, IconUpload } from '../components/icons';
import { Pill, cx } from '../components/ui';
import { DropZone } from '../components/DropZone';
import { useConnections } from '../hooks/useConnections';
import { ACCEPT, stageLabel, useDocuments, useUpload } from '../hooks/useDocuments';
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
  const { data: conns } = useConnections();
  const [kbId, setKbId] = useState<string | null>(null);
  const [pick, setPick] = useState<{ conn: string; model: string } | null>(null);
  const [draft, setDraft] = useState('');

  const [quickId, setQuickId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // "New chat" resets to the user's default KB, or to the KB we were sent here with.
  const navState = location.state as { fresh?: number; kbId?: string } | null;
  const fresh = navState?.fresh;
  useEffect(() => {
    setKbId(navState?.kbId ?? null);
    setDraft('');
    setQuickId(null);
  }, [fresh]);

  const kb = kbs?.find((k) => k.id === kbId) ?? kbs?.find((k) => k.id === me?.default_kb_id) ?? kbs?.[0];
  const kbName = kb?.name ?? 'your documents';

  // Drop-to-index: upload into the selected KB and follow the first file's progress.
  const upload = useUpload(kb?.id);
  const { data: kbDocs } = useDocuments(quickId ? kb?.id : undefined);
  const quick = quickId ? kbDocs?.find((d) => d.id === quickId) : undefined;
  const startUpload = (files: File[]) =>
    upload.mutate(files, { onSuccess: (res) => setQuickId(res.documents[0]?.id ?? null) });
  const rejected = upload.data?.rejected ?? [];

  // Every chat model from every connection; default = first connection's current pick (Auto or fixed).
  const options = (conns ?? []).flatMap((c) =>
    c.chat_models.map((m) => ({ conn: c, model: m, via: `${c.name} · ${c.runtime === 'local' ? 'local' : 'cloud'}` })),
  );
  const firstConn = conns?.find((c) => c.resolved_model);
  const current =
    options.find((o) => pick && o.conn.id === pick.conn && o.model === pick.model) ??
    (firstConn ? options.find((o) => o.conn.id === firstConn.id && o.model === firstConn.resolved_model) : undefined) ??
    options[0];
  const cloudModel = current?.conn.runtime === 'cloud';

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
          width={300}
          leading={
            <span
              className={cx(
                'h-[7px] w-[7px] shrink-0 rounded-full',
                !current ? 'bg-border-strong' : cloudModel ? 'bg-accent' : 'bg-ok',
              )}
            />
          }
          label={current ? current.model.split('/').pop() : 'No model'}
          footer={(close) => (
            <Link
              to="/keys"
              onClick={close}
              className="block rounded-lg px-2.5 py-2 text-[13px] font-medium hover:bg-surface2 hover:no-underline"
            >
              Manage model providers
            </Link>
          )}
        >
          {(close) =>
            options.length === 0 ? (
              <div className="px-2.5 pb-2.5 pt-1 text-[13px] leading-[1.5] text-muted">No model provider connected yet.</div>
            ) : (
              <div className="max-h-[320px] overflow-auto">
                {options.map((o) => (
                  <DropdownItem
                    key={o.conn.id + o.model}
                    selected={current === o}
                    onSelect={() => {
                      setPick({ conn: o.conn.id, model: o.model });
                      close();
                    }}
                  >
                    <div className="flex items-center gap-2.5">
                      <span
                        className={cx(
                          'h-[7px] w-[7px] shrink-0 rounded-full',
                          o.conn.runtime === 'local' ? 'bg-ok' : 'bg-accent',
                        )}
                      />
                      <div className="min-w-0">
                        <div className="truncate text-[13.5px] font-medium">{o.model}</div>
                        <div className="text-[12px] text-muted">{o.via}</div>
                      </div>
                    </div>
                  </DropdownItem>
                ))}
              </div>
            )
          }
        </Dropdown>
      </Topbar>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div
          className="mx-auto flex max-w-[680px] flex-col gap-[22px] px-4 pb-10 min-[820px]:px-8"
          style={{ paddingTop: mobile ? 40 : '11vh' }}
        >
          <div className="flex flex-col items-center gap-3 text-center">
            {(current ? cloudModel : kb?.runtime === 'cloud') ? (
              <Pill tone="warn" className="px-[11px] py-[5px] text-[12.5px]">
                <IconLock />
                {current ? `Uses ${current.conn.name} · passages sent via API` : 'Cloud knowledge base · passages sent via API'}
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
                onClick={() => fileInput.current?.click()}
                disabled={!kb || upload.isPending}
                className="flex h-[30px] items-center gap-1.5 rounded-lg border border-border bg-transparent pl-2 pr-2.5 text-[12.5px] text-muted hover:bg-surface2 hover:text-text"
              >
                <IconUpload size={14} />
                Add file
              </button>
              <input
                ref={fileInput}
                type="file"
                accept={ACCEPT}
                hidden
                onChange={(e) => {
                  const f = Array.from(e.target.files ?? []);
                  if (f.length) startUpload(f.slice(0, 1));
                  e.target.value = '';
                }}
              />
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

          {quick ? (
            <div className="flex items-center gap-3.5 rounded-[14px] border border-border bg-surface px-4 py-3.5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-surface2 font-mono text-[10.5px] font-semibold text-muted">
                {quick.type}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-[7px]">
                <div className="flex justify-between gap-2.5">
                  <span className="truncate font-mono text-[13.5px] font-medium">{quick.filename}</span>
                  <span
                    className={cx(
                      'whitespace-nowrap text-[12.5px]',
                      quick.status === 'indexed' ? 'text-ok-text' : quick.status === 'failed' ? 'text-err-text' : 'text-muted',
                    )}
                  >
                    {quick.status === 'indexed' ? 'Ready' : quick.status === 'failed' ? 'Failed' : `${quick.progress}%`}
                  </span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-surface2">
                  <div
                    className={cx(
                      'h-full rounded-full transition-[width] duration-300',
                      quick.status === 'indexed' ? 'bg-ok' : quick.status === 'failed' ? 'bg-err-text' : 'bg-accent',
                    )}
                    style={{ width: `${quick.status === 'failed' ? 100 : quick.progress}%` }}
                  />
                </div>
                <div
                  className={cx(
                    'flex flex-wrap gap-x-2 text-[12.5px]',
                    quick.status === 'failed' ? 'text-err-text' : 'text-muted',
                  )}
                >
                  <span>{stageLabel(quick, kb?.runtime !== 'cloud')}</span>
                  {(quick.status === 'indexed' || quick.status === 'failed') && (
                    <button
                      type="button"
                      onClick={() => setQuickId(null)}
                      className="border-none bg-transparent p-0 text-[12.5px] font-medium text-accent-text"
                    >
                      Add another
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <DropZone
              onFiles={(files) => startUpload(files.slice(0, 1))}
              multiple={false}
              disabled={!kb || upload.isPending}
              className="flex items-center gap-3.5 rounded-[14px] bg-transparent p-[18px] text-left"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-accent-soft text-accent-text">
                <IconUpload size={18} />
              </div>
              <div className="flex min-w-0 flex-col gap-[3px]">
                <div className="text-[14px] font-semibold">{upload.isPending ? 'Uploading…' : 'Drop a document to start'}</div>
                <div className="text-[13px] text-muted">
                  PDF, DOCX, MD, TXT, CSV or XLSX. Indexed into {kbName} in seconds.
                </div>
              </div>
            </DropZone>
          )}
          {(upload.error || rejected.length > 0) && (
            <div className="rounded-xl bg-err-soft px-4 py-3 text-[13px] text-err-text" role="alert">
              {upload.error?.message ?? rejected.map((r) => `${r.filename}: ${r.reason}`).join(' ')}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
