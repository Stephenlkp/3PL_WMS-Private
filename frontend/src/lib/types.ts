export type Role = "admin" | "warehouse_supervisor" | "picker" | "packer" | "customer";

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  customer_id: string | null;
  customer_name: string | null;
  active: boolean;
};

export type Balance = {
  customer_id: string;
  customer_name: string;
  product_id: string;
  sku: string;
  barcode: string;
  product_name: string;
  location_id: string | null;
  location_code: string | null;
  compact_location: string | null;
  on_hand_qty: number;
  reserved_qty: number;
  available_qty: number;
  location_qty: number | null;
};

export type Product = {
  id: string;
  customer_id: string;
  customer_name: string;
  sku: string;
  barcode: string;
  model: string | null;
  name: string;
  reorder_point: number;
  active: boolean;
};

export type Customer = { id: string; code: string; name: string; email: string | null; active: boolean };
export type Location = {
  id: string;
  location_code: string;
  compact_location: string;
  zone: string;
  rack: string;
  level: string;
  active: boolean;
  photo_file_id: string | null;
};

export type OrderItem = {
  id: string;
  product_id: string;
  sku: string;
  barcode: string;
  product_name: string;
  quantity: number;
  picked_qty: number;
  packed_qty: number;
};

export type Order = {
  id: string;
  customer_id: string;
  customer_name: string;
  order_number: string;
  status: string;
  receiver_name: string;
  receiver_phone: string;
  receiver_address: string;
  courier: string;
  tracking_number: string | null;
  notes: string | null;
  airway_bill_file_id: string | null;
  created_at: string;
  items: OrderItem[];
  picklist_id: string | null;
  shipment_id: string | null;
};

export type PickLine = {
  id: string;
  sku: string;
  barcode: string;
  product_name: string;
  location_code: string;
  compact_location: string;
  quantity: number;
  picked_qty: number;
  sequence: number;
};

export type PickList = {
  id: string;
  pick_number: string;
  order_id: string;
  order_number: string;
  customer_name: string;
  status: string;
  lines: PickLine[];
};

export type Shipment = {
  id: string;
  shipment_number: string;
  order_id: string;
  order_number: string;
  customer_name: string;
  status: string;
  courier: string;
  tracking_number: string | null;
  airway_bill_file_id: string | null;
  receiver_name: string;
  item_count: number;
  shipped_at: string | null;
};

export type Movement = {
  id: string;
  created_at: string;
  customer_name: string;
  sku: string;
  product_name: string;
  location_code: string | null;
  transaction_type: string;
  quantity: number;
  reference_no: string;
  notes: string | null;
  created_by_name: string | null;
};

export type SearchHit = {
  kind: string;
  label: string;
  detail: string;
  sku: string | null;
  location_code: string | null;
  order_number: string | null;
  tracking_number: string | null;
  on_hand_qty: number | null;
  reserved_qty: number | null;
  available_qty: number | null;
  order_id: string | null;
};

export type MapCell = {
  id: string;
  location_code: string;
  compact_location: string;
  zone: string;
  rack: string;
  level: string;
  active: boolean;
  physical_qty: number;
  sku_count: number;
  photo_file_id: string | null;
};

export type RackMap = { zones: { zone: string; racks: { rack: string; cells: MapCell[] }[] }[] };

export type SkuHit = {
  sku: string;
  name: string;
  customer_name: string;
  on_hand_qty: number;
  reserved_qty: number;
  available_qty: number;
  placements: {
    location_id: string;
    location_code: string;
    compact_location: string;
    physical_qty: number;
    photo_file_id: string | null;
  }[];
};
