import { describe, expect, it } from 'vitest';
import { maskPhoneNumber } from '../phone';

describe('maskPhoneNumber', () => {
  it('uses the exact Uzbek display mask', () => {
    expect(maskPhoneNumber('+998901234567')).toBe('+998 90 *** 4567');
  });

  it.each([
    ['+12345678', '+1 *** 5678'],
    ['+12345678901', '+123 **** 8901'],
    ['+123456789012345', '+123 ******** 2345'],
  ])('uses the generic display mask for %s', (phone, masked) => {
    expect(maskPhoneNumber(phone)).toBe(masked);
  });
});
