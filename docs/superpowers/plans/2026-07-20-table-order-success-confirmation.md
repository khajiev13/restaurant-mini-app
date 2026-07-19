# Table Order Success Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unsupported table-order progress statuses with one localized success confirmation while preserving real payment, submission, synchronization, and cancellation states.

**Architecture:** Keep the existing order-detail API calls and polling unchanged. Derive a table-only successful-placement boolean in `ArtisanOrderStatusPage`, use it for the heading and icon, and render the progress tracker/update message only for delivery orders. Add the copy to the three shipped locales and protect both table and delivery behavior with component tests.

**Tech Stack:** React 19, TypeScript, React Router, react-i18next, Vitest, Testing Library, Vite.

## Global Constraints

- Apply the confirmation behavior only when `order.discriminator === "inplace"`.
- Preserve actionable payment, submission, synchronization, and cancellation states.
- Preserve background polling and all backend/API behavior.
- Preserve delivery-order status tracking.
- Do not modify payment totals, service-fee accounting, table context restoration, or staff workflows.

---

## File Structure

- `frontend/src/pages/artisan/ArtisanOrderStatusPage.tsx`: derive table-order confirmation presentation and restrict the progress UI to delivery orders.
- `frontend/src/pages/artisan/ArtisanOrderStatusPage.test.tsx`: cover successful table states, exceptional table states, and unchanged delivery tracking.
- `frontend/src/i18n/locales/en.json`: English success copy.
- `frontend/src/i18n/locales/uz.json`: Uzbek success copy.
- `frontend/src/i18n/locales/ru.json`: Russian success copy.

### Task 1: Render a truthful table-order confirmation

**Files:**
- Modify: `frontend/src/pages/artisan/ArtisanOrderStatusPage.test.tsx:97-214`
- Modify: `frontend/src/pages/artisan/ArtisanOrderStatusPage.tsx:17-36,247-304,355-375,421-423`
- Modify: `frontend/src/i18n/locales/en.json:104-121`
- Modify: `frontend/src/i18n/locales/uz.json:104-121`
- Modify: `frontend/src/i18n/locales/ru.json:104-121`

**Interfaces:**
- Consumes: existing `Order.status`, `Order.discriminator`, `OrderStatus.status`, and `t(key)` translation access.
- Produces: internal `isSuccessfulTableOrder: boolean` presentation state and translation key `order.placed_successfully`.

- [x] **Step 1: Write failing tests for the table confirmation and delivery boundary**

Replace the first table-mode test with assertions for the success confirmation and absent tracker, add a successful-status matrix, strengthen the failed-payment assertion, and add a delivery regression test:

```tsx
it('shows a successful table-order confirmation without a status tracker', async () => {
  renderPage();

  expect(await screen.findByText(/buyurtma muvaffaqiyatli berildi|order placed successfully|заказ успешно оформлен/i)).toBeVisible();
  expect(screen.getByText('Stol 12')).toBeVisible();
  expect(screen.getByText('Asosiy zal')).toBeVisible();
  expect(screen.getByText(/naqd pul|cash|наличные/i)).toBeVisible();
  expect(screen.queryByText(/tayyorlanmoqda|being prepared|готовится/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/^tayyor$|ready for pickup|^готово$/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/har 15 soniyada|updating every 15 seconds|обновление каждые 15 секунд/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/on the way|yo'lda|в пути/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/ichki buyurtma|internal order|внутренний заказ/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/alipos/i)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /bekor qilish|cancel order|отменить заказ/i })).toBeVisible();
  expect(screen.getByRole('button', { name: /yana buyurtma|order more|заказать ещё/i })).toBeVisible();
  expect(apiMocks.restoreTable).not.toHaveBeenCalled();
});

it.each(['ACCEPTED_BY_RESTAURANT', 'READY'])('keeps table status %s on the success confirmation', async (orderStatus) => {
  const progressed = { ...tableOrder, status: orderStatus };
  apiMocks.getOrder.mockResolvedValue({ data: { data: progressed } });
  apiMocks.getOrderStatus.mockResolvedValue({ data: { data: { ...progressed } } });

  renderPage();

  expect(await screen.findByText(/buyurtma muvaffaqiyatli berildi|order placed successfully|заказ успешно оформлен/i)).toBeVisible();
  expect(screen.queryByText(/tayyorlanmoqda|being prepared|готовится/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/^tayyor$|ready for pickup|^готово$/i)).not.toBeInTheDocument();
});
```

In the existing payment-failure test, add:

```tsx
expect(await screen.findByText(/to'lov amalga oshmadi|payment failed|оплата не прошла/i)).toBeVisible();
expect(screen.queryByText(/buyurtma muvaffaqiyatli berildi|order placed successfully|заказ успешно оформлен/i)).not.toBeInTheDocument();
```

Add a delivery regression test:

```tsx
it('keeps status tracking for delivery orders', async () => {
  const deliveryOrder = {
    ...tableOrder,
    discriminator: 'delivery',
    status: 'ACCEPTED_BY_RESTAURANT',
    table_title: null,
    hall_title: null,
    service_percent: 0,
    delivery_address: 'Test address',
  } satisfies Order;
  apiMocks.getOrder.mockResolvedValue({ data: { data: deliveryOrder } });
  apiMocks.getOrderStatus.mockResolvedValue({ data: { data: { ...deliveryOrder } } });

  renderPage();

  expect(await screen.findByText(/tayyorlanmoqda|being prepared|готовится/i)).toBeVisible();
  expect(screen.getByText(/on the way|yo'lda|в пути/i)).toBeVisible();
  expect(screen.getByText(/har 15 soniyada|updating every 15 seconds|обновление каждые 15 секунд/i)).toBeVisible();
  expect(screen.queryByText(/buyurtma muvaffaqiyatli berildi|order placed successfully|заказ успешно оформлен/i)).not.toBeInTheDocument();
});
```

- [x] **Step 2: Run the focused tests and verify the new behavior fails**

Run:

```bash
cd frontend
npm test -- src/pages/artisan/ArtisanOrderStatusPage.test.tsx
```

Expected: FAIL because `order.placed_successfully` is absent and the current table tracker still renders preparation/ready labels and the polling message.

- [x] **Step 3: Add the localized success copy**

Add the key inside each locale's `order` object:

```json
// en.json
"placed_successfully": "Order placed successfully",

// uz.json
"placed_successfully": "Buyurtma muvaffaqiyatli berildi",

// ru.json
"placed_successfully": "Заказ успешно оформлен",
```

- [x] **Step 4: Implement the minimal table-only presentation**

Replace `TABLE_STEPS` with the successful table-state set:

```tsx
const TABLE_SUCCESS_STATUSES = new Set([
  'NEW',
  'PAID_AWAITING_RESTAURANT',
  'ACCEPTED_BY_RESTAURANT',
  'READY',
]);
```

After deriving `currentStatus`, derive the presentation boolean and keep delivery progress based on `DELIVERY_STEPS`:

```tsx
const isSuccessfulTableOrder = isTableOrder && TABLE_SUCCESS_STATUSES.has(currentStatus);
const currentStep = STATUS_STEP[currentStatus] || 1;
```

Use the success icon and heading only for the successful table states:

```tsx
<Icon
  name={isCancelled ? 'cancel' : isSuccessfulTableOrder ? 'check_circle' : isTableOrder ? 'table_restaurant' : 'receipt_long'}
  fill
  size={38}
  style={{ color: isCancelled ? COLORS.error : COLORS.primary }}
/>
```

```tsx
{isSuccessfulTableOrder ? t('order.placed_successfully') : statusLabels[currentStatus] || currentStatus}
```

Restrict the existing tracker and polling message to delivery orders:

```tsx
{!isTableOrder && !isCancelled && !isPendingPayment && (
  <section style={{ backgroundColor: COLORS.surfaceContainerLow, borderRadius: 14, padding: 20 }}>
    <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between' }}>
      <div style={{ position: 'absolute', top: 16, left: 0, width: '100%', height: 4, backgroundColor: COLORS.surfaceContainerHighest, borderRadius: 99 }} />
      <div style={{ position: 'absolute', top: 16, left: 0, width: `${((currentStep - 1) / (DELIVERY_STEPS.length - 1)) * 100}%`, height: 4, backgroundColor: COLORS.primary, borderRadius: 99 }} />
      {DELIVERY_STEPS.map((step, index) => {
        const reached = currentStep >= index + 1;
        return (
          <div key={step.key} style={{ zIndex: 1, width: `${100 / DELIVERY_STEPS.length}%`, textAlign: 'center' }}>
            <div style={{ margin: '0 auto 10px', width: 32, height: 32, borderRadius: '50%', display: 'grid', placeItems: 'center', backgroundColor: reached ? COLORS.primary : COLORS.surfaceContainerHighest, color: reached ? '#fff' : COLORS.outline, boxShadow: `0 0 0 4px ${COLORS.surfaceContainerLow}` }}>
              <Icon name={reached && index < currentStep - 1 ? 'check' : step.icon} size={16} fill={reached} />
            </div>
            <span style={{ fontSize: 10, fontWeight: 800, color: reached ? COLORS.primary : COLORS.outline }}>
              {t(step.labelKey)}
            </span>
          </div>
        );
      })}
    </div>
  </section>
)}
```

```tsx
{!isTableOrder && !isCancelled && !isPendingPayment && (
  <div style={{ textAlign: 'center', color: COLORS.outline, fontSize: 12 }}>{t('order.updating')}</div>
)}
```

Do not change polling, status labels, payment actions, cancellation, totals, order items, table restoration, or delivery behavior.

- [x] **Step 5: Run the focused tests and verify they pass**

Run:

```bash
cd frontend
npm test -- src/pages/artisan/ArtisanOrderStatusPage.test.tsx
```

Expected: all tests in `ArtisanOrderStatusPage.test.tsx` PASS with no unhandled errors.

- [x] **Step 6: Run frontend verification**

Run:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
npm test
```

Expected: TypeScript, ESLint, Vite build, and the full Vitest suite exit successfully. If the full Vitest run times out under constrained resources, rerun it serially with `npm test -- --maxWorkers=1` and report both results.

- [x] **Step 7: Inspect and commit only the scoped implementation**

Run:

```bash
git diff --check
git diff -- frontend/src/pages/artisan/ArtisanOrderStatusPage.tsx frontend/src/pages/artisan/ArtisanOrderStatusPage.test.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json
git add frontend/src/pages/artisan/ArtisanOrderStatusPage.tsx frontend/src/pages/artisan/ArtisanOrderStatusPage.test.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json docs/superpowers/plans/2026-07-20-table-order-success-confirmation.md
git commit -m "fix: simplify table order confirmation"
```

Expected: the diff contains only the table-order presentation, tests, three translations, and this plan; unrelated untracked files remain untouched.
