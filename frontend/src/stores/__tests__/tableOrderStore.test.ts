import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  resolveTable: vi.fn(),
  restoreTable: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

async function loadStore() {
  vi.resetModules();
  const mod = await import('../tableOrderStore');
  return mod.useTableOrderStore;
}

describe('tableOrderStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('normalizes a manual code and stores only the safe resolved context', async () => {
    apiMocks.resolveTable.mockResolvedValue({
      data: {
        data: {
          table_title: 'Stol 12',
          hall_title: 'Asosiy zal',
          service_percent: 10,
          manual_code: 'A7K2P9',
          access_token: 'signed-access-token',
        },
      },
    });
    const useTableOrderStore = await loadStore();

    await useTableOrderStore.getState().resolveCode('a7-k2 p9');

    expect(apiMocks.resolveTable).toHaveBeenCalledWith({ code: 'A7K2P9' });
    expect(useTableOrderStore.getState().context).toEqual({
      tableTitle: 'Stol 12',
      hallTitle: 'Asosiy zal',
      servicePercent: 10,
      accessToken: 'signed-access-token',
    });
    const stored = sessionStorage.getItem('table-order:v1');
    expect(stored).toContain('Stol 12');
    expect(stored).not.toContain('tableId');
    expect(stored).not.toContain('A7K2P9');
  });

  it('hydrates a valid context from sessionStorage', async () => {
    sessionStorage.setItem('table-order:v1', JSON.stringify({
      tableTitle: 'Stol 7',
      hallTitle: 'Terrace',
      servicePercent: 15,
      accessToken: 'session-token',
    }));

    const useTableOrderStore = await loadStore();

    expect(useTableOrderStore.getState().context?.tableTitle).toBe('Stol 7');
  });

  it('restores table context from an owned order after a fresh WebView', async () => {
    apiMocks.restoreTable.mockResolvedValue({
      data: {
        data: {
          table_title: 'Stol 12',
          hall_title: 'Asosiy zal',
          service_percent: 10,
          manual_code: 'A7K2P9',
          access_token: 'fresh-access-token',
        },
      },
    });
    const useTableOrderStore = await loadStore();

    await useTableOrderStore.getState().restoreOrder('order-123');

    expect(apiMocks.restoreTable).toHaveBeenCalledWith('order-123');
    expect(useTableOrderStore.getState().context?.accessToken).toBe('fresh-access-token');
  });

  it('clears malformed session data instead of throwing', async () => {
    sessionStorage.setItem('table-order:v1', '{broken-json');

    const useTableOrderStore = await loadStore();

    expect(useTableOrderStore.getState().context).toBeNull();
    expect(sessionStorage.getItem('table-order:v1')).toBeNull();
  });
});
