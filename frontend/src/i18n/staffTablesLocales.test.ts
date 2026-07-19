import { createInstance } from 'i18next';
import { describe, expect, it } from 'vitest';
import en from './locales/en.json';
import ru from './locales/ru.json';
import uz from './locales/uz.json';

const required = [
  'nav_admin', 'nav_tables', 'nav_delivery', 'title', 'workspace', 'tables', 'menu',
  'browse_only', 'all', 'with_orders', 'attention', 'filters', 'updated', 'refresh', 'retry',
  'directory_stale', 'status_stale', 'last_confirmed', 'refresh_failed', 'freshness_restored',
  'unavailable', 'empty_directory', 'no_filter_results', 'no_orders', 'mini_app_orders',
  'mini_app_orders_one', 'mini_app_orders_other', 'processing_count', 'attention_count',
  'unlisted', 'unlisted_explanation', 'service_charge', 'more_items', 'view_details',
  'unknown_table', 'unknown_hall', 'unknown_item', 'back_to_tables',
  'combined_summary', 'combined_items', 'original_orders', 'synchronized_orders',
  'processing_orders', 'attention_orders', 'items_cost', 'service_amount',
  'total_amount', 'synchronized', 'processing', 'verify_pos', 'not_synchronized',
  'active', 'not_found', 'order', 'modifiers', 'payment_cash', 'payment_online',
  'payment_paid', 'payment_refund_pending', 'payment_refund_verification_required',
  'payment_refund_failed', 'payment_unknown',
] as const;

describe.each([['en', en], ['ru', ru], ['uz', uz]] as const)(
  '%s staff table copy',
  (_name, locale) => {
    it('defines every required non-empty string', () => {
      for (const key of required) {
        expect(locale.staff_tables[key], key).toEqual(expect.any(String));
        expect(locale.staff_tables[key].trim(), key).not.toBe('');
      }
    });
  },
);

describe('staff table order pluralization', () => {
  it.each([
    ['en', 1, '1 mini-app order'],
    ['en', 2, '2 mini-app orders'],
    ['ru', 1, '1 заказ из мини-приложения'],
    ['ru', 2, '2 заказа из мини-приложения'],
    ['ru', 5, '5 заказов из мини-приложения'],
    ['uz', 1, '1 ta mini-ilova buyurtmasi'],
    ['uz', 2, '2 ta mini-ilova buyurtmasi'],
  ])('selects the runtime %s plural for count %i', async (language, count, expected) => {
    const instance = createInstance();
    await instance.init({
      lng: language,
      fallbackLng: 'en',
      resources: { en: { translation: en }, ru: { translation: ru }, uz: { translation: uz } },
      interpolation: { escapeValue: false },
    });

    expect(instance.t('staff_tables.mini_app_orders', { count })).toBe(expected);
  });
});
