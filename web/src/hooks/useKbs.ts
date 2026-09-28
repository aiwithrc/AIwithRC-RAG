import { useQuery } from '@tanstack/react-query';

import { endpoints } from '../api/client';

export const kbsKey = ['kbs'] as const;

export function useKbs() {
  return useQuery({ queryKey: kbsKey, queryFn: endpoints.kbs });
}
