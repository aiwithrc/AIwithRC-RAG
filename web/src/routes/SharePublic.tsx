import { Link } from 'react-router-dom';

import { Logo } from '../components/ui';

/** Public shared-answer page (/s/:token). Filled in once sharing lands. */
export default function SharePublic() {
  return (
    <div className="h-full overflow-auto bg-bg">
      <header className="sticky top-0 z-[5] flex items-center gap-2.5 border-b border-border bg-surface px-4 py-3.5 min-[820px]:px-8">
        <div className="flex-1">
          <Logo size={26} />
        </div>
        <Link
          to="/"
          className="flex h-[34px] items-center rounded-[9px] border border-border bg-surface px-3 text-[13px] font-medium text-text hover:no-underline"
        >
          Back to app
        </Link>
      </header>
      <main className="mx-auto flex max-w-[720px] flex-col gap-3 px-4 pb-16 pt-11 min-[820px]:px-8">
        <h1 className="m-0 text-[26px] font-semibold tracking-[-0.02em]">This shared answer isn't available</h1>
        <p className="m-0 text-[15px] text-muted">The link may be wrong, or the owner stopped sharing it.</p>
      </main>
    </div>
  );
}
