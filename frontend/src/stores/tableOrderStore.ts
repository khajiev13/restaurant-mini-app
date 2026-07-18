import { create } from 'zustand';
import { resolveTable, restoreTable } from '../services/api';

const STORAGE_KEY = 'table-order:v1';

export interface TableContext {
  tableTitle: string;
  hallTitle: string;
  servicePercent: number;
  accessToken: string;
}

interface TableOrderState {
  context: TableContext | null;
  isResolving: boolean;
  error: string | null;
  resolveEntry: (entry: string) => Promise<void>;
  resolveCode: (code: string) => Promise<void>;
  restoreOrder: (orderId: string) => Promise<void>;
  clearContext: () => void;
  clearError: () => void;
}

function isTableContext(value: unknown): value is TableContext {
  if (!value || typeof value !== 'object') return false;
  const context = value as Record<string, unknown>;
  return typeof context.tableTitle === 'string'
    && typeof context.hallTitle === 'string'
    && typeof context.servicePercent === 'number'
    && Number.isFinite(context.servicePercent)
    && typeof context.accessToken === 'string'
    && context.accessToken.length > 0;
}

function readStoredContext(): TableContext | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isTableContext(parsed)) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return {
      tableTitle: parsed.tableTitle,
      hallTitle: parsed.hallTitle,
      servicePercent: parsed.servicePercent,
      accessToken: parsed.accessToken,
    };
  } catch {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // Storage can be unavailable in hardened webviews.
    }
    return null;
  }
}

function persistContext(context: TableContext | null): void {
  try {
    if (context) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(context));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Keep the in-memory session usable when storage is unavailable.
  }
}

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    .response?.data?.detail;
  return typeof detail === 'string' ? detail : 'Table could not be found. Please try again.';
}

async function resolveAndStore(
  request: ReturnType<typeof resolveTable>,
  set: (partial: Partial<TableOrderState>) => void,
): Promise<void> {
  set({ isResolving: true, error: null });
  try {
    const response = await request;
    const data = response.data.data;
    const context: TableContext = {
      tableTitle: data.table_title,
      hallTitle: data.hall_title,
      servicePercent: data.service_percent,
      accessToken: data.access_token,
    };
    persistContext(context);
    set({ context });
  } catch (error) {
    set({ error: errorMessage(error) });
    throw error;
  } finally {
    set({ isResolving: false });
  }
}

export const useTableOrderStore = create<TableOrderState>((set) => ({
  context: readStoredContext(),
  isResolving: false,
  error: null,

  resolveEntry: async (entry) => {
    await resolveAndStore(resolveTable({ entry }), set);
  },

  resolveCode: async (code) => {
    const digits = code.replace(/\D/g, '').slice(0, 6);
    const normalized = digits.replace(/^0+(?=\d)/, '');
    await resolveAndStore(resolveTable({ code: normalized }), set);
  },

  restoreOrder: async (orderId) => {
    await resolveAndStore(restoreTable(orderId), set);
  },

  clearContext: () => {
    persistContext(null);
    set({ context: null, error: null });
  },

  clearError: () => set({ error: null }),
}));
