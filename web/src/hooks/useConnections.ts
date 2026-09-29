import { useQuery } from '@tanstack/react-query';

import { endpoints } from '../api/client';

export const connectionsKey = ['connections'] as const;

export function useConnections() {
  return useQuery({ queryKey: connectionsKey, queryFn: endpoints.connections });
}
