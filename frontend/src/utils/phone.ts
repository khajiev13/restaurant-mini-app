const CANONICAL_PHONE_PATTERN = /^\+\d{8,15}$/;

export function maskPhoneNumber(canonicalPhone: string): string {
  if (!CANONICAL_PHONE_PATTERN.test(canonicalPhone)) {
    throw new Error('Phone number must be canonical');
  }

  const digits = canonicalPhone.slice(1);
  if (digits.length === 12 && digits.startsWith('998')) {
    return `+998 ${digits.slice(3, 5)} *** ${digits.slice(-4)}`;
  }

  const prefixLength = Math.min(3, digits.length - 7);
  const hiddenDigits = digits.length - prefixLength - 4;
  return `+${digits.slice(0, prefixLength)} ${'*'.repeat(hiddenDigits)} ${digits.slice(-4)}`;
}
