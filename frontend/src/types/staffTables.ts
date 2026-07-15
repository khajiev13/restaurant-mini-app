export type StaffTableSyncState = 'synchronized' | 'processing' | 'attention';
export type StaffTableSyncLabel =
  | 'synchronized'
  | 'processing'
  | 'not_synchronized'
  | 'verify_in_pos';

export interface StaffTableModifier {
  id: string;
  name: string | null;
  quantity: number;
  price: number;
}

export interface StaffTableOrderItem {
  id: string;
  name: string | null;
  quantity: number;
  price: number;
  modifications: StaffTableModifier[];
}

export interface StaffTableItem extends StaffTableOrderItem {
  line_total: number;
}

export interface StaffTableOrder {
  id: string;
  order_number: string | null;
  created_at: string;
  status: string;
  sync_state: StaffTableSyncState;
  sync_label: StaffTableSyncLabel;
  payment_method: 'cash' | 'online';
  payment_status: 'paid' | null;
  items: StaffTableOrderItem[];
  items_cost: number;
  service_amount: number;
  total_amount: number;
}

export interface StaffTableSummary {
  table_id: string;
  table_title: string;
  hall_id: string | null;
  hall_title: string | null;
  service_percent: number;
  is_listed: boolean;
  synchronized_order_count: number;
  processing_order_count: number;
  attention_order_count: number;
  combined_item_count: number;
  combined_line_count: number;
  combined_items: StaffTableItem[];
  items_cost: number;
  service_amount: number;
  total_amount: number;
}

export interface StaffHall {
  hall_id: string | null;
  hall_title: string | null;
  service_percent: number | null;
  is_listed: boolean;
  tables: StaffTableSummary[];
}

export interface StaffTablesFreshness {
  generated_at: string;
  directory_stale: boolean;
  directory_last_success_at: string;
  order_status_stale: boolean;
  order_status_oldest_success_at: string | null;
}

export interface StaffTablesOverview {
  freshness: StaffTablesFreshness;
  halls: StaffHall[];
}

export interface StaffTableDetail {
  freshness: StaffTablesFreshness;
  table: StaffTableSummary;
  orders: StaffTableOrder[];
}
