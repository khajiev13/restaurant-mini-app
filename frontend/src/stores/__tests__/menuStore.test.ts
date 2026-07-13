import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  getMenu: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

async function loadStore() {
  vi.resetModules();
  const mod = await import('../menuStore');
  return mod.useMenuStore;
}

describe('menuStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('refreshMenu replaces stale availability from the previous response', async () => {
    apiMocks.getMenu
      .mockResolvedValueOnce({
        data: {
          data: {
            categories: [{ id: 'c1', name: 'Somsa', sortOrder: 0 }],
            items: [{
              id: 'i1',
              categoryId: 'c1',
              name: 'Classic Somsa',
              description: null,
              price: 18000,
              sortOrder: 0,
              available: true,
              availableCount: null,
            }],
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          data: {
            categories: [{ id: 'c1', name: 'Somsa', sortOrder: 0 }],
            items: [{
              id: 'i1',
              categoryId: 'c1',
              name: 'Classic Somsa',
              description: null,
              price: 18000,
              sortOrder: 0,
              available: false,
              availableCount: 0,
            }],
          },
        },
      });

    const useMenuStore = await loadStore();
    await useMenuStore.getState().fetchMenu();
    await useMenuStore.getState().refreshMenu();

    expect(apiMocks.getMenu).toHaveBeenCalledTimes(2);
    expect(useMenuStore.getState().menu?.items[0]).toMatchObject({
      available: false,
      availableCount: 0,
    });
  });
});
