import { useSyncExternalStore } from 'react';

function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mql = window.matchMedia(query);
      mql.addEventListener('change', cb);
      return () => mql.removeEventListener('change', cb);
    },
    () => window.matchMedia(query).matches,
  );
}

/** Below 820px: drawer sidebar, full-screen source panel. */
export const useIsMobile = () => useMediaQuery('(max-width: 819.98px)');

/** Below 1200px the source panel overlays the chat instead of sitting beside it. */
export const useIsNarrow = () => useMediaQuery('(max-width: 1199.98px)');
