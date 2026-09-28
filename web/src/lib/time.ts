/** API timestamps are naive UTC ("2026-09-28T10:42:00"); parse them as UTC. */
export function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

/** "just now", "5 min ago", "2h ago", "yesterday", "3d ago", "Sep 20". */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const d = parseUtc(iso);
  const s = Math.max(0, (now.getTime() - d.getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 2 * 86400) return 'yesterday';
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
