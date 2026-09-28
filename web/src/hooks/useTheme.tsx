import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { endpoints, type Me, type Theme } from '../api/client';
import { meKey, useMe } from './useMe';

function readStored(): Theme {
  try {
    const t = localStorage.getItem('theme');
    if (t === 'dark' || t === 'light') return t;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function apply(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try {
    localStorage.setItem('theme', theme);
  } catch {
    /* storage unavailable */
  }
}

interface ThemeCtx {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

/** Theme follows the signed-in user's saved preference; before sign-in, the last value used on this device. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [local, setLocal] = useState<Theme>(readStored);
  const theme: Theme = me?.theme ?? local;

  useEffect(() => apply(theme), [theme]);

  const setTheme = useCallback(
    (next: Theme) => {
      setLocal(next);
      if (me) {
        const updated: Me = { ...me, theme: next };
        qc.setQueryData(meKey, updated);
        endpoints.patchMe({ theme: next }).catch(() => qc.invalidateQueries({ queryKey: meKey }));
      }
    },
    [me, qc],
  );

  const value = useMemo(
    () => ({ theme, setTheme, toggle: () => setTheme(theme === 'dark' ? 'light' : 'dark') }),
    [theme, setTheme],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useTheme must be used inside ThemeProvider');
  return v;
}
