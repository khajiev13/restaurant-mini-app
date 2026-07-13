export interface ApiResponse<T> {
  success: boolean;
  data: T;
}

export interface AuthResponse {
  access_token: string;
}

export interface User {
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  username: string | null;
  photo_url?: string | null;
  phone_number: string | null;
  language: string;
  role: 'customer' | 'staff' | 'admin';
}

export interface Address {
  id: string;
  label: string;
  full_address: string;
  latitude: string | null;
  longitude: string | null;
  entrance: string | null;
  apartment: string | null;
  floor: string | null;
  door_code: string | null;
  courier_instructions: string | null;
  is_default: boolean;
}

export interface AddressCreate {
  label?: string;
  full_address: string;
  latitude?: string | null;
  longitude?: string | null;
  entrance?: string | null;
  apartment?: string | null;
  floor?: string | null;
  door_code?: string | null;
  courier_instructions?: string | null;
  is_default?: boolean;
}

export interface ReverseGeocodeResult {
  address: string;
  name: string;
  description: string;
  nearby?: AddressSuggestion[];
}

export interface AddressSuggestion {
  title: string;
  subtitle: string;
  lat: number;
  lng: number;
  address?: string;
}

export interface MenuImage {
  url: string;
}

export interface MenuItem {
  id: string;
  name: string;
  description: string | null;
  price: number;
  categoryId: string;
  sortOrder: number;
  available: boolean;
  availableCount: number | null;
  images?: MenuImage[];
}

export interface MenuCategory {
  id: string;
  name: string;
  sortOrder: number;
}

export interface MenuData {
  categories: MenuCategory[];
  items: MenuItem[];
}

export interface TableContextResponse {
  table_title: string;
  hall_title: string;
  service_percent: number;
  manual_code: string;
  access_token: string;
}

export interface OrderItem {
  id: string;
  name?: string;
  quantity: number;
  price: number;
  modifications: unknown[];
}

export interface Order {
  id: string;
  status: string;
  discriminator: 'delivery' | 'inplace';
  items_cost: number;
  total_amount: number;
  created_at: string;
  order_number: string | null;
  items: OrderItem[];
  comment: string | null;
  delivery_address?: string | null;
  payment_method: string;
  payment_provider: string | null;
  payment_status: string | null;
  payment_expires_at: string | null;
  multicard_checkout_url: string | null;
  multicard_receipt_url: string | null;
  alipos_order_id: string | null;
  alipos_sync_status: string | null;
  table_title: string | null;
  hall_title: string | null;
  service_percent: number;
}

export interface OrderStatus {
  status: string;
  order_number: string | null;
  alipos_order_id: string | null;
  payment_status: string | null;
  payment_expires_at: string | null;
  multicard_receipt_url: string | null;
  table_title: string | null;
  hall_title: string | null;
  service_percent: number;
  alipos_sync_status: string | null;
}

export interface CartItem extends MenuItem {
  quantity: number;
}

export interface CreateOrderPayload {
  items: Array<{
    id: string;
    name?: string;
    quantity: number;
    price: number;
    modifications: unknown[];
  }>;
  phone_number: string;
  delivery_address?: string;
  latitude?: string | null;
  longitude?: string | null;
  address_id?: string;
  comment?: string;
  payment_method: string;
  discriminator: string;
  table_access_token?: string;
}
