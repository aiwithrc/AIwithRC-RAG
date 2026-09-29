import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import type { Connection, Kb } from '../../api/client';
import { useConnections } from '../../hooks/useConnections';
import type { ModelChoice } from '../../hooks/useChat';
import { Dropdown, DropdownItem } from '../Dropdown';
import { IconBook } from '../icons';
import { Pill, cx } from '../ui';

export interface ModelOption {
  conn: Connection;
  model: string;
  via: string;
}

const STORE = 'chat-model';

function readChoice(): ModelChoice | null {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) ?? 'null');
    return v && typeof v.connection_id === 'string' && typeof v.model === 'string' ? v : null;
  } catch {
    return null;
  }
}

/** All chat models across connections, and the one to answer with (remembered on this device). */
export function useModelChoice() {
  const { data: conns } = useConnections();
  const [pick, setPickState] = useState<ModelChoice | null>(readChoice);
  const options: ModelOption[] = (conns ?? []).flatMap((c) =>
    c.chat_models.map((m) => ({ conn: c, model: m, via: `${c.name} · ${c.runtime === 'local' ? 'local' : 'cloud'}` })),
  );
  const firstConn = conns?.find((c) => c.resolved_model);
  const current =
    options.find((o) => pick && o.conn.id === pick.connection_id && o.model === pick.model) ??
    (firstConn ? options.find((o) => o.conn.id === firstConn.id && o.model === firstConn.resolved_model) : undefined) ??
    options[0];
  const setPick = (o: ModelOption) => {
    const v = { connection_id: o.conn.id, model: o.model };
    setPickState(v);
    try {
      localStorage.setItem(STORE, JSON.stringify(v));
    } catch {
      /* storage unavailable */
    }
  };
  const choice: ModelChoice | undefined = current ? { connection_id: current.conn.id, model: current.model } : undefined;
  return { options, current, setPick, choice, loaded: conns !== undefined };
}

export function RuntimePill({ runtime }: { runtime: 'local' | 'cloud' }) {
  return (
    <Pill tone={runtime === 'local' ? 'ok' : 'accent'} className="px-[7px] py-0.5 text-[11px]">
      {runtime === 'local' ? 'Local' : 'Cloud'}
    </Pill>
  );
}

export function KbPicker({ kbs, kb, onSelect, disabled }: { kbs: Kb[]; kb?: Kb; onSelect: (id: string) => void; disabled?: boolean }) {
  const navigate = useNavigate();
  return (
    <Dropdown
      heading={disabled ? 'This chat searches' : 'Search in'}
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
        disabled ? (
          <div className="px-2.5 pb-2.5 pt-1 text-[13px] leading-[1.5] text-muted">
            {kb?.name}. Start a new chat to search a different knowledge base.
          </div>
        ) : (
          kbs.map((k) => (
            <DropdownItem
              key={k.id}
              selected={k.id === kb?.id}
              onSelect={() => {
                onSelect(k.id);
                close();
              }}
              trailing={<RuntimePill runtime={k.runtime} />}
            >
              <div className="text-[13.5px] font-medium">{k.name}</div>
              <div className="text-[12px] text-muted">
                {k.indexed_count} of {k.doc_count} docs indexed
              </div>
            </DropdownItem>
          ))
        )
      }
    </Dropdown>
  );
}

export function ModelPicker({ m }: { m: ReturnType<typeof useModelChoice> }) {
  const { options, current, setPick } = m;
  const cloud = current?.conn.runtime === 'cloud';
  return (
    <Dropdown
      heading="Answer with"
      width={300}
      leading={
        <span className={cx('h-[7px] w-[7px] shrink-0 rounded-full', !current ? 'bg-border-strong' : cloud ? 'bg-accent' : 'bg-ok')} />
      }
      label={current ? current.model.split('/').pop() : 'No model'}
      footer={(close) => (
        <Link to="/keys" onClick={close} className="block rounded-lg px-2.5 py-2 text-[13px] font-medium hover:bg-surface2 hover:no-underline">
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
                  setPick(o);
                  close();
                }}
              >
                <div className="flex items-center gap-2.5">
                  <span className={cx('h-[7px] w-[7px] shrink-0 rounded-full', o.conn.runtime === 'local' ? 'bg-ok' : 'bg-accent')} />
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
  );
}
