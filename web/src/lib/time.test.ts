import { describe, expect, it } from 'vitest';

import { parseUtc, relativeTime } from './time';

describe('time', () => {
  const now = new Date('2026-09-28T12:00:00Z');

  it('parses naive API timestamps as UTC', () => {
    expect(parseUtc('2026-09-28T10:00:00').toISOString()).toBe('2026-09-28T10:00:00.000Z');
    expect(parseUtc('2026-09-28T10:00:00Z').toISOString()).toBe('2026-09-28T10:00:00.000Z');
  });

  it('formats relative times', () => {
    expect(relativeTime('2026-09-28T11:59:30', now)).toBe('just now');
    expect(relativeTime('2026-09-28T11:55:00', now)).toBe('5 min ago');
    expect(relativeTime('2026-09-28T10:00:00', now)).toBe('2h ago');
    expect(relativeTime('2026-09-27T09:00:00', now)).toBe('yesterday');
    expect(relativeTime('2026-09-25T12:00:00', now)).toBe('3d ago');
  });
});
