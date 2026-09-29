import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { endpoints, type ShareInfo } from '../../api/client';
import { Modal } from '../Modal';
import { Button, Spinner, Toggle } from '../ui';

/** Share one answer: creates (or reuses) its public link, toggles source excerpts, can stop sharing. */
export function ShareModal({ messageId, onClose }: { messageId: string | null; onClose: () => void }) {
  const [share, setShare] = useState<ShareInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revoked, setRevoked] = useState(false);

  useEffect(() => {
    setShare(null);
    setError(null);
    setCopied(false);
    setRevoked(false);
    if (!messageId) return;
    endpoints.share(messageId, true).then(setShare, (e: Error) => setError(e.message));
  }, [messageId]);

  const toggle = async (on: boolean) => {
    if (!share) return;
    setBusy(true);
    try {
      setShare(await endpoints.updateShare(share.id, on));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!share) return;
    setBusy(true);
    try {
      await endpoints.revokeShare(share.id);
      setRevoked(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={!!messageId} onClose={onClose} labelledBy="share-title">
      <div className="flex flex-col gap-1.5">
        <div id="share-title" className="text-[17px] font-semibold">
          Share this answer
        </div>
        <div className="text-[13.5px] leading-[1.55] text-muted">
          Anyone with the link can view this answer and its cited passages. Nothing else in the knowledge base is shared.
        </div>
      </div>
      {error && <div className="text-[13px] text-err-text">{error}</div>}
      {!share && !error && <Spinner />}
      {share && !revoked && (
        <>
          <div className="flex gap-2">
            <div className="flex h-10 min-w-0 flex-1 items-center overflow-hidden text-ellipsis whitespace-nowrap rounded-[9px] border border-border bg-surface2 px-3 font-mono text-[12.5px]">
              {share.url}
            </div>
            <Button
              variant="primary"
              className="h-10 shrink-0 text-[13.5px]"
              onClick={() => navigator.clipboard?.writeText(share.url).then(() => setCopied(true))}
            >
              {copied ? 'Copied' : 'Copy link'}
            </Button>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 text-[13.5px]">Include source excerpts</div>
            <Toggle on={share.include_sources} onChange={(v) => !busy && toggle(v)} label="Include source excerpts" />
          </div>
        </>
      )}
      {revoked && <div className="text-[13.5px] text-muted">Sharing stopped. The link no longer works.</div>}
      <div className="flex items-center justify-between gap-2 border-t border-border pt-4">
        <div className="flex items-center gap-4">
          {share && !revoked && (
            <>
              <Link to={`/s/${share.token}`} target="_blank" className="text-[13.5px] font-medium">
                Preview public page
              </Link>
              <button
                type="button"
                onClick={stop}
                disabled={busy}
                className="border-none bg-transparent p-0 text-[13px] font-medium text-err-text disabled:opacity-50"
              >
                Stop sharing
              </button>
            </>
          )}
        </div>
        <Button onClick={onClose}>Done</Button>
      </div>
    </Modal>
  );
}
