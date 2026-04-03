import '@testing-library/jest-dom/vitest';
import { beforeAll, beforeEach, afterEach, afterAll } from 'vitest';
import { setupServer } from 'msw/node';
import { handlers } from './src/mocks/handlers';

// Vitest 4.x regression: localStorage.clear may be missing in jsdom workers
if (typeof window !== 'undefined' && typeof window.localStorage?.clear !== 'function') {
  const store: Record<string, string> = {};
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = String(v); },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { Object.keys(store).forEach(k => delete store[k]); },
      get length() { return Object.keys(store).length; },
      key: (i: number) => Object.keys(store)[i] ?? null,
    },
    writable: true,
  });
}

export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
beforeEach(() => { window.localStorage.clear(); });
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
