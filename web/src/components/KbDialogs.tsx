import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { endpoints, type Kb } from '../api/client';
import { kbsKey } from '../hooks/useKbs';
import { ConfirmDialog, Modal } from './Modal';
import { Button, Field, TextInput, cx } from './ui';

type Runtime = 'local' | 'cloud';

function RuntimeChoice({ value, onChange }: { value: Runtime; onChange: (r: Runtime) => void }) {
  const card = (r: Runtime) =>
    cx(
      'flex flex-col gap-1 rounded-xl border-[1.5px] p-3.5 text-left text-text',
      value === r ? 'border-accent bg-accent-soft' : 'border-border bg-surface',
    );
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[13px] font-medium">Where should answers be generated?</div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-2.5" role="radiogroup">
        <button type="button" role="radio" aria-checked={value === 'local'} className={card('local')} onClick={() => onChange('local')}>
          <span className="text-[14px] font-semibold">Local</span>
          <span className="text-[12.5px] leading-[1.45] text-muted">A model on this server or your network. Documents never leave it.</span>
        </button>
        <button type="button" role="radio" aria-checked={value === 'cloud'} className={card('cloud')} onClick={() => onChange('cloud')}>
          <span className="text-[14px] font-semibold">Cloud</span>
          <span className="text-[12.5px] leading-[1.45] text-muted">Anthropic or OpenAI. Stronger answers, passages sent via API.</span>
        </button>
      </div>
    </div>
  );
}

export function NewKbDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [runtime, setRuntime] = useState<Runtime>('local');
  const create = useMutation({
    mutationFn: () => endpoints.createKb({ name: name.trim() || 'Untitled knowledge base', runtime }),
    onSuccess: (kb) => {
      qc.invalidateQueries({ queryKey: kbsKey });
      onClose();
      navigate(`/kbs/${kb.id}`);
    },
  });

  useEffect(() => {
    if (open) {
      setName('');
      setRuntime('local');
      create.reset();
    }
  }, [open]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <Modal open={open} onClose={onClose} width={480} labelledBy="new-kb-title">
      <form onSubmit={submit} className="flex flex-col gap-[18px]">
        <div id="new-kb-title" className="text-[17px] font-semibold">
          New knowledge base
        </div>
        <Field label="Name">
          <TextInput autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. HR policies" maxLength={200} />
        </Field>
        <RuntimeChoice value={runtime} onChange={setRuntime} />
        {create.error && <div className="text-[13px] text-err-text">{create.error.message}</div>}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} className="h-[38px] text-[13.5px]">
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={create.isPending} className="h-[38px] px-4 text-[13.5px]">
            Create and add files
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function EditKbDialog({ kb, open, onClose }: { kb: Kb; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState(kb.name);
  const [description, setDescription] = useState(kb.description);
  const [runtime, setRuntime] = useState<Runtime>(kb.runtime);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (open) {
      setName(kb.name);
      setDescription(kb.description);
      setRuntime(kb.runtime);
    }
  }, [open, kb]);

  const save = useMutation({
    mutationFn: () => endpoints.patchKb(kb.id, { name: name.trim(), description: description.trim(), runtime }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: kbsKey });
      onClose();
    },
  });
  const del = useMutation({
    mutationFn: () => endpoints.deleteKb(kb.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: kbsKey });
      navigate('/kbs');
    },
  });

  return (
    <>
      <Modal open={open && !confirmDelete} onClose={onClose} width={480} labelledBy="edit-kb-title">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
          className="flex flex-col gap-[18px]"
        >
          <div id="edit-kb-title" className="text-[17px] font-semibold">
            Edit knowledge base
          </div>
          <Field label="Name">
            <TextInput value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          </Field>
          <Field label="Description">
            <TextInput value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What's in here?" maxLength={2000} />
          </Field>
          <RuntimeChoice value={runtime} onChange={setRuntime} />
          {save.error && <div className="text-[13px] text-err-text">{save.error.message}</div>}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button variant="danger" onClick={() => (del.reset(), setConfirmDelete(true))} className="h-[38px] text-[13.5px]">
              Delete knowledge base
            </Button>
            <div className="flex gap-2">
              <Button onClick={onClose} className="h-[38px] text-[13.5px]">
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={!name.trim() || save.isPending} className="h-[38px] px-4 text-[13.5px]">
                Save
              </Button>
            </div>
          </div>
        </form>
      </Modal>
      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${kb.name}?`}
        body={`This permanently deletes the knowledge base, its ${kb.doc_count} document${kb.doc_count === 1 ? '' : 's'} and their index. Chats that used it stay in History.`}
        confirmLabel="Delete knowledge base"
        danger
        busy={del.isPending}
        error={del.error?.message}
        onConfirm={() => del.mutate()}
        onClose={() => setConfirmDelete(false)}
      />
    </>
  );
}
