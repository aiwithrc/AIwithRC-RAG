import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError, endpoints, type Me } from '../api/client';

export const meKey = ['me'] as const;

/** Current user, or `null` when signed out. */
export function useMe() {
  return useQuery<Me | null>({
    queryKey: meKey,
    queryFn: async () => {
      try {
        return await endpoints.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

export function useSignOut() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: endpoints.logout,
    onSettled: () => {
      qc.clear();
      qc.setQueryData(meKey, null);
    },
  });
}
