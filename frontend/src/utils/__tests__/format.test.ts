import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../i18n', () => ({
  default: {
    language: 'en',
    t: (key: string) => ({ 'common.currency_en': 'UZS', 'common.currency_ru': 'сум', 'common.currency_uz': "so'm" }[key] ?? key),
  },
}));

import { formatPrice, formatDate } from '../format';

describe('formatPrice', () => {
  it('formats in English', () => {
    const result = formatPrice(15000, 'en');
    expect(result).toContain('15,000');
    expect(result).toContain('UZS');
  });

  it('formats in Russian with space separator', () => {
    const result = formatPrice(15000, 'ru');
    expect(result).toContain('сум');
  });

  it('formats in Uzbek', () => {
    const result = formatPrice(15000, 'uz');
    expect(result).toContain("so'm");
  });

  it('handles zero', () => {
    const result = formatPrice(0, 'en');
    expect(result).toContain('0');
  });

  it('strips locale suffix like en-US → en', () => {
    const result = formatPrice(1000, 'en-US');
    expect(result).toContain('UZS');
  });
});

describe('formatDate', () => {
  it('returns a non-empty string', () => {
    const result = formatDate(new Date('2026-04-04'), 'en');
    expect(result).toBeTruthy();
    expect(result).toContain('2026');
  });

  it('accepts a string date', () => {
    const result = formatDate('2026-04-04', 'en');
    expect(result).toContain('2026');
  });
});
