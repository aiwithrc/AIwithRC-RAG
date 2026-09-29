import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { endpoints } from '../api/client';
import { AnswerText } from '../components/chat/Answer';
import { Logo, Pill, Spinner } from '../components/ui';
import { useMe } from '../hooks/useMe';

/** Public shared answer (/s/:token). No sign-in needed; shows only the frozen snapshot. */
export default function SharePublic() {
  const { token } = useParams();
  const { data: me } = useMe();
  const { data, isLoading, error } = useQuery({
    queryKey: ['public-share', token],
    queryFn: () => endpoints.publicShare(token!),
    enabled: !!token,
    retry: false,
  });
  const answered = data?.answered_at
    ? new Date(data.answered_at.endsWith('Z') ? data.answered_at : `${data.answered_at}Z`).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : '';

  return (
    <div className="h-full overflow-auto bg-bg">
      <header className="sticky top-0 z-[5] flex items-center gap-2.5 border-b border-border bg-surface px-4 py-3.5 min-[820px]:px-8">
        <div className="flex-1">
          <Logo size={26} />
        </div>
        <Link
          to={me ? '/' : '/login'}
          className="flex h-[34px] items-center rounded-[9px] border border-border bg-surface px-3 text-[13px] font-medium text-text hover:no-underline"
        >
          {me ? 'Back to app' : 'Sign in'}
        </Link>
      </header>
      <main className="mx-auto flex max-w-[720px] flex-col gap-7 px-4 pb-16 pt-11 min-[820px]:px-8">
        {isLoading && <Spinner />}
        {error && (
          <div className="flex flex-col gap-3">
            <h1 className="m-0 text-[26px] font-semibold tracking-[-0.02em]">This shared answer isn't available</h1>
            <p className="m-0 text-[15px] text-muted">The link may be wrong, or the owner stopped sharing it.</p>
          </div>
        )}
        {data && (
          <>
            <div className="flex flex-col gap-3">
              <div className="text-[12.5px] font-medium text-muted">Shared answer{data.kb_name ? ` · ${data.kb_name}` : ''}</div>
              <h1 className="m-0 text-[30px] font-semibold leading-[1.2] tracking-[-0.02em] text-balance">{data.question}</h1>
              <div className="flex flex-wrap items-center gap-2.5 text-[12.5px] text-muted">
                {data.confidence === 'high' && (
                  <Pill tone="ok">
                    High confidence · {data.citations.length || 'cited'} source{data.citations.length === 1 ? '' : 's'}
                  </Pill>
                )}
                {data.confidence === 'low' && <Pill tone="warn">Low confidence · partial match</Pill>}
                {data.model && <>Answered by {data.model.split('/').pop()}</>}
                {answered && <> · {answered}</>}
              </div>
            </div>
            <AnswerText text={data.answer} className="text-[17px] leading-[1.75]" />
            {data.citations.length > 0 && (
              <div className="flex flex-col gap-3">
                <div className="text-[13px] font-semibold">Sources</div>
                {data.citations.map((c) => (
                  <div key={c.n} className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-4">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] bg-accent-soft font-mono text-[11px] font-semibold text-accent-text">
                        {c.n}
                      </span>
                      <span className="font-mono text-[12.5px]">{c.filename}</span>
                      {c.location && <span className="text-[12.5px] text-muted">{c.location}</span>}
                      <span className="ml-auto font-mono text-[12px] text-muted">{c.score.toFixed(2)}</span>
                    </div>
                    <div className="whitespace-pre-line text-[14px] leading-[1.7] text-muted">
                      {c.before}
                      <mark className="rounded-[3px] bg-hl px-0.5 py-px text-text">{c.hit}</mark>
                      {c.after}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-col gap-4 rounded-2xl bg-accent-soft p-7">
              <div className="flex flex-col gap-1.5">
                <div className="text-[20px] font-semibold tracking-[-0.01em]">Get answers like this from your own documents</div>
                <div className="text-[14.5px] leading-[1.6] text-muted text-pretty">
                  AIwithRC-RAG indexes your PDFs, Word files and spreadsheets, then answers with citations to the exact
                  passage. Self-host it free on your own server.
                </div>
              </div>
              <div className="flex flex-wrap gap-2.5">
                <Link
                  to={me ? '/' : '/login'}
                  className="flex h-[42px] items-center rounded-[10px] bg-accent px-[18px] text-[14px] font-semibold text-on-accent hover:no-underline hover:brightness-[1.08]"
                >
                  Try it with your docs
                </Link>
                <a
                  href={data.project_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex h-[42px] items-center rounded-[10px] border border-border-strong bg-surface px-[18px] text-[14px] font-medium text-text hover:no-underline"
                >
                  Self-host on your server
                </a>
              </div>
            </div>
            <div className="text-center text-[12.5px] text-muted">
              Only this answer and its cited passages are shared. The rest of the knowledge base stays private.
            </div>
          </>
        )}
      </main>
    </div>
  );
}
