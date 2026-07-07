export interface StaffCustomer {
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  phone_number: string | null;
}

export interface StaffAddress {
  full_address: string;
  latitude: string | null;
  longitude: string | null;
  entrance: string | null;
  apartment: string | null;
  floor: string | null;
  courier_instructions: string | null;
}

export interface StaffSummary {
  telegram_id: number;
  first_name: string;
  last_name: string | null;
}

export interface StaffOrderItem {
  id?: string;
  name?: string;
  quantity: number;
  price?: number;
  modifications?: unknown[];
}

export interface StaffOrder {
  id: string;
  order_number: string | null;
  status: string;
  created_at: string;
  status_updated_at: string | null;
  assigned_at: string | null;
  delivered_at: string | null;
  customer: StaffCustomer;
  address: StaffAddress;
  items: StaffOrderItem[];
  total_amount: number;
  delivery_fee: number;
  payment_method: string;
  payment_status: string | null;
  assigned_staff: StaffSummary | null;
}
