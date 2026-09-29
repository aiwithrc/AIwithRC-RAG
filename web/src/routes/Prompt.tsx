import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { endpoints, type WorkspaceSettings } from '../api/client';
import { Topbar } from '../components/AppShell';
import { Button, Page, PageHeader, Spinner, cx } from '../components/ui';

const settingsKey = ['settings'] as const;

const EXAMPLES = [
  'Answer as a short numbered list when the question asks for steps or several items.',
  'Always mention dates, amounts and names exactly as written in the documents.',
  'Write for a non-expert: plain words, no jargon.',
  'When documents disagree, say so and cite both.',
  'Give detailed, thorough answers: explain the context and include every relevant detail from the documents.',
  'Keep answers to 3 sentences or fewer unless I ask for detail.',
  'End every answer with a one-line "Bottom line:" summary.',
];

export default function PromptPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: settingsKey, queryFn: endpoints.settings });
  const [text, setText] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) setText(data.custom_instructions);
  }, [data]);

  const save = useMutation({
    mutationFn: () => endpoints.patchSettings({ custom_instructions: text }),
    onSuccess: (s) => {
      qc.setQueryData<WorkspaceSettings>(settingsKey, s);
      setText(s.custom_instructions);
      setSaved(true);
    },
  });

  const max = data?.max_instructions ?? 4000;
  const dirty = !!data && text.trim() !== data.custom_instructions;
  const canEdit = data?.can_edit ?? false;
  const over = text.length > max;

  const addExample = (ex: string) => {
    setText((t) => (t.trim() ? `${t.trimEnd()}\n${ex}` : ex));
    setSaved(false);
  };

  return (
    <>
      <Topbar title="Prompt" />
      <Page>
        <PageHeader
          title="Prompt"
          sub="Instructions for every answer in this workspace: length, tone, format, what to focus on. They override the default answer style. Changes apply to the next question, no restart needed."
        />
        {isLoading && <Spinner />}
        {error && <div className="text-[13px] text-err-text">{error.message}</div>}
        {data && (
          <>
            <div className="flex flex-col gap-3 rounded-[14px] border border-border bg-surface p-5">
              <label htmlFor="instructions" className="text-[15px] font-semibold">
                Your instructions
              </label>
              <textarea
                id="instructions"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  setSaved(false);
                  if (save.error) save.reset();
                }}
                readOnly={!canEdit}
                placeholder={'e.g. "Answer as a recruiter would: include job titles, companies and dates. Keep answers under 5 bullet points."'}
                rows={14}
                className="min-h-[280px] w-full resize-y rounded-[10px] border border-border bg-surface p-3.5 text-[14px] leading-[1.6] text-text outline-none focus:border-accent read-only:bg-surface2"
              />
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="primary"
                  className="h-10 px-5 text-[14px]"
                  disabled={!canEdit || !dirty || over || save.isPending}
                  onClick={() => save.mutate()}
                >
                  {save.isPending ? 'Saving…' : 'Save'}
                </Button>
                {saved && !dirty && <span className="text-[13px] text-ok-text">Saved. Used from the next question.</span>}
                {save.error && <span className="text-[13px] text-err-text">{save.error.message}</span>}
                {!canEdit && <span className="text-[13px] text-muted">Only the workspace owner can change the prompt.</span>}
                <span className={cx('ml-auto font-mono text-[12px]', over ? 'text-err-text' : 'text-muted')}>
                  {text.length.toLocaleString()} / {max.toLocaleString()}
                </span>
              </div>
              {canEdit && (
                <div className="flex flex-col gap-2 border-t border-border pt-3">
                  <div className="text-[12.5px] font-medium text-muted">Add an example</div>
                  <div className="flex flex-wrap gap-2">
                    {EXAMPLES.map((ex) => (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => addExample(ex)}
                        className="rounded-full border border-border bg-surface px-3 py-1.5 text-left text-[12.5px] text-text hover:border-accent hover:text-accent-text"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <details className="rounded-[14px] border border-border bg-surface p-5 [&_summary]:cursor-pointer">
              <summary className="text-[15px] font-semibold">
                Built-in prompt <span className="font-normal text-muted">(grounding rules and default answer style)</span>
              </summary>
              <p className="mb-3 mt-2 text-[13px] leading-[1.55] text-muted">
                The grounding rules keep answers to what your documents say and make the numbered citations and source
                panel work; they always apply. The answer style is only a default: your instructions above override it.
              </p>
              <pre className="m-0 whitespace-pre-wrap rounded-[10px] bg-surface2 p-3.5 font-mono text-[12.5px] leading-[1.6] text-text">
                {data.built_in_prompt}
              </pre>
            </details>
          </>
        )}
      </Page>
    </>
  );
}
