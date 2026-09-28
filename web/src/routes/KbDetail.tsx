import { Link, useNavigate, useParams } from 'react-router-dom';

import { Topbar } from '../components/AppShell';
import { IconChat, IconUpload } from '../components/icons';
import { Button, Page, Pill, Spinner } from '../components/ui';
import { useKbs } from '../hooks/useKbs';
import { useIsMobile } from '../hooks/useMediaQuery';

export default function KbDetail() {
  const { id } = useParams();
  const { data: kbs, isLoading } = useKbs();
  const mobile = useIsMobile();
  const navigate = useNavigate();
  const kb = kbs?.find((k) => k.id === id);
  const cols = mobile ? 'minmax(0,1fr) auto' : 'minmax(0,1fr) 90px 70px 150px';

  return (
    <>
      <Topbar title={kb?.name ?? 'Knowledge base'} />
      <Page width={1080}>
        <Link to="/kbs" className="-mb-2 self-start text-[13px] text-muted hover:text-text hover:no-underline">
          ← Knowledge bases
        </Link>
        {isLoading && <Spinner />}
        {!isLoading && !kb && <div className="text-muted">This knowledge base doesn't exist or was deleted.</div>}
        {kb && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h1 className="m-0 text-[26px] font-semibold tracking-[-0.02em]">{kb.name}</h1>
                  <Pill tone={kb.runtime === 'local' ? 'ok' : 'accent'}>{kb.runtime === 'local' ? 'Local' : 'Cloud'}</Pill>
                </div>
                {kb.description && <div className="text-[14px] text-muted">{kb.description}</div>}
                <div className="text-[13px] text-muted">0 of {kb.doc_count} documents indexed</div>
              </div>
              <Button variant="primary" className="h-[38px] text-[14px]" onClick={() => navigate('/')}>
                <IconChat />
                Chat with this knowledge base
              </Button>
            </div>
            <button
              type="button"
              disabled
              title="Upload arrives with the ingest pipeline"
              className="flex w-full flex-col items-center gap-2.5 rounded-[14px] border-[1.5px] border-dashed border-border-strong bg-surface px-5 py-[30px] text-text"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-[11px] bg-accent-soft text-accent-text">
                <IconUpload size={20} />
              </div>
              <div className="text-[14.5px] font-semibold">Drop files here or click to upload</div>
              <div className="text-[13px] text-muted">PDF, DOCX, MD, TXT, CSV, XLSX · up to 50 MB each</div>
            </button>
            <div className="overflow-hidden rounded-[14px] border border-border bg-surface">
              <div
                className="grid gap-4 border-b border-border px-[18px] py-[11px] text-[12px] font-medium text-muted"
                style={{ gridTemplateColumns: cols }}
              >
                <span>Document</span>
                {!mobile && <span>Size</span>}
                {!mobile && <span>Chunks</span>}
                <span>Status</span>
              </div>
              <div className="px-[18px] py-8 text-center text-[13.5px] text-muted">
                No documents yet. Upload a file to start indexing.
              </div>
            </div>
          </>
        )}
      </Page>
    </>
  );
}
