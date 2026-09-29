import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { endpoints, isProcessing, uploadFiles, type Doc } from '../api/client';
import { kbsKey } from './useKbs';

export const docsKey = (kbId: string) => ['documents', kbId] as const;

/** Documents in a KB. Polls every second while anything is queued or indexing. */
export function useDocuments(kbId: string | undefined) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: docsKey(kbId ?? ''),
    queryFn: () => endpoints.documents(kbId!),
    enabled: !!kbId,
    refetchInterval: (query) => ((query.state.data ?? []).some(isProcessing) ? 1000 : false),
  });

  // When processing finishes, refresh KB counts (docs/chunks/indexed) too.
  const busy = (q.data ?? []).some(isProcessing);
  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy) qc.invalidateQueries({ queryKey: kbsKey });
    wasBusy.current = busy;
  }, [busy, qc]);

  return q;
}

export function useUpload(kbId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => uploadFiles(kbId!, files),
    onSuccess: (res) => {
      if (!kbId) return;
      qc.setQueryData<Doc[]>(docsKey(kbId), (old) => [...res.documents, ...(old ?? [])]);
      qc.invalidateQueries({ queryKey: docsKey(kbId) });
      qc.invalidateQueries({ queryKey: kbsKey });
    },
  });
}

export const ACCEPT = '.pdf,.docx,.md,.markdown,.txt,.csv,.xlsx';

/** Stage label shown under a progress bar, mirroring the prototype's copy. */
export function stageLabel(d: Doc, local: boolean): string {
  switch (d.status) {
    case 'queued':
      return 'Waiting to start…';
    case 'parsing':
      return 'Reading the file…';
    case 'chunking':
      return 'Splitting into passages…';
    case 'embedding':
      return local ? 'Embedding on your server…' : 'Creating embeddings…';
    case 'indexed':
      return `Indexed ${d.chunk_count} passage${d.chunk_count === 1 ? '' : 's'}. Ask it anything.`;
    case 'failed':
      return d.error ?? 'Indexing failed.';
  }
}
