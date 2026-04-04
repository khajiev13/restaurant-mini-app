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
}

export interface AddressSuggestion {
  title: string;
  subtitle: string;
  lat: number;
  lng: number;
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
}

export interface OrderStatus {
  status: string;
  order_number: string | null;
  alipos_order_id: string | null;
  payment_status: string | null;
  payment_expires_at: string | null;
  multicard_receipt_url: string | null;
}

export interface CartItem extends MenuItem {
  quantity: number;
}

export interface CreateOrderPayload {
  items: Array<{
    id: string;
    quantity: number;
    price: number;
    modifications: unknown[];
  }>;
  phone_number: string;
  delivery_address: string;
  latitude?: string | null;
  longitude?: string | null;
  address_id?: string;
  comment?: string;
  payment_method: string;
  discriminator: string;
}
