import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import type { Me } from '../api/client';
import { useIsMobile } from '../hooks/useMediaQuery';
import { useMe, useSignOut } from '../hooks/useMe';
import { useTheme } from '../hooks/useTheme';
import { IconBook, IconChat, IconClock, IconKey, IconMenu, IconMoon, IconPlus, IconSliders, IconSun } from './icons';
import { Logo, cx } from './ui';

const ShellCtx = createContext<{ openDrawer: () => void }>({ openDrawer: () => {} });

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

const NAV = [
  { to: '/', label: 'Chat', icon: IconChat, end: true },
  { to: '/kbs', label: 'Knowledge bases', icon: IconBook, end: false },
  { to: '/history', label: 'History', icon: IconClock, end: false },
  { to: '/keys', label: 'API keys', icon: IconKey, end: false },
  { to: '/settings', label: 'Settings', icon: IconSliders, end: false },
];

function Sidebar({ me, onNavigate }: { me: Me; onNavigate: () => void }) {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const signOut = useSignOut();

  const itemClass = ({ isActive }: { isActive: boolean }) =>
    cx(
      'flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-[14px] font-medium no-underline hover:bg-surface2 hover:no-underline',
      isActive ? 'bg-surface2 text-text' : 'text-muted',
    );

  return (
    <>
      <div className="px-4 pb-3.5 pt-4">
        <Logo />
      </div>
      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={() => {
            navigate('/', { state: { fresh: Date.now() } });
            onNavigate();
          }}
          className="flex h-[38px] w-full items-center justify-center gap-2 rounded-[10px] border-none bg-accent text-[14px] font-semibold text-on-accent hover:brightness-[1.08]"
        >
          <IconPlus />
          New chat
        </button>
      </div>
      <nav className="flex flex-col gap-0.5 px-3">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={itemClass} onClick={onNavigate}>
            <Icon size={17} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-[22px] pb-1.5 pt-5 text-[12px] font-medium text-muted">Recent</div>
      <div className="flex min-h-0 flex-1 flex-col gap-px overflow-auto px-3">
        <div className="px-2.5 py-[7px] text-[13px] text-muted">No chats yet</div>
      </div>
      <div className="flex flex-col gap-1 border-t border-border p-3">
        <button
          type="button"
          onClick={toggle}
          className="flex h-[34px] w-full items-center gap-2.5 rounded-lg border-none bg-transparent px-2.5 text-left text-[13.5px] text-muted hover:bg-surface2"
        >
          {theme === 'dark' ? <IconSun /> : <IconMoon />}
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
        <div className="flex items-center gap-2.5 px-2.5 py-1.5">
          <NavLink
            to="/profile"
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(
                '-mx-1.5 -my-1 flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-1.5 py-1 text-text no-underline hover:bg-surface2 hover:no-underline',
                isActive && 'bg-surface2',
              )
            }
          >
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-text">
              {initials(me.name)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium">{me.name}</div>
              <div className="text-[12px] text-muted">My profile</div>
            </div>
          </NavLink>
          <button
            type="button"
            onClick={() => signOut.mutate(undefined, { onSettled: () => navigate('/login') })}
            className="border-none bg-transparent p-1 text-[12.5px] text-muted hover:text-err-text"
          >
            Sign out
          </button>
        </div>
      </div>
    </>
  );
}

export function AppShell() {
  const { data: me } = useMe();
  const mobile = useIsMobile();
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();

  useEffect(() => setDrawer(false), [location.pathname, mobile]);

  if (!me) return null;

  return (
    <ShellCtx.Provider value={{ openDrawer: () => setDrawer(true) }}>
      <div className="relative flex h-full overflow-hidden">
        {mobile && drawer && (
          <div className="absolute inset-0 z-[39] bg-overlay" onClick={() => setDrawer(false)} aria-hidden="true" />
        )}
        <aside
          className={cx(
            'z-40 flex h-full w-64 shrink-0 flex-col border-r border-border bg-surface transition-transform duration-200',
            mobile ? 'absolute inset-y-0 left-0' : 'relative',
            mobile && !drawer && '-translate-x-[105%]',
          )}
          aria-hidden={mobile && !drawer ? true : undefined}
        >
          <Sidebar me={me} onNavigate={() => setDrawer(false)} />
        </aside>
        <div className="relative flex h-full min-w-0 flex-1 flex-col">
          <Outlet />
        </div>
      </div>
    </ShellCtx.Provider>
  );
}

/** The 56px bar at the top of every in-app screen. */
export function Topbar({ title, children }: { title: ReactNode; children?: ReactNode }) {
  const mobile = useIsMobile();
  const { openDrawer } = useContext(ShellCtx);
  return (
    <header className="relative z-[22] flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface px-4 min-[820px]:px-8">
      {mobile && (
        <button
          type="button"
          onClick={openDrawer}
          aria-label="Open menu"
          className="-ml-2 flex h-9 w-9 items-center justify-center border-none bg-transparent text-text"
        >
          <IconMenu />
        </button>
      )}
      <div className="min-w-0 flex-1 truncate text-[15px] font-semibold">{title}</div>
      {children && <div className="flex shrink-0 items-center gap-1.5">{children}</div>}
    </header>
  );
}
