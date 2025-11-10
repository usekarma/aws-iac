
# MongoDB CDC Demo Schema

## Collections

### 1. customers

```js
{
  _id: ObjectId(),
  customer_id: "C100001",
  first_name: "Jane",
  last_name: "Doe",
  email: "jane.doe@example.com",
  phone: "+1-312-555-0101",
  addresses: [
    {
      address_id: "ADDR-1",
      type: "shipping",
      line1: "123 Main St",
      city: "Chicago",
      state: "IL",
      postal_code: "60601",
      country: "US",
      is_default: true
    }
  ],
  status: "active",
  loyalty_level: "gold",
  marketing_opt_in: true,
  created_at: ISODate("2025-11-09T13:00:00Z"),
  updated_at: ISODate("2025-11-09T13:00:00Z")
}
```

Indexes:
```js
db.customers.createIndex({ customer_id: 1 }, { unique: true });
db.customers.createIndex({ email: 1 }, { unique: true });
```

---

### 2. vendors

```js
{
  _id: ObjectId(),
  vendor_id: "V1001",
  name: "Acme Supplies Inc.",
  contact_name: "Alice Smith",
  contact_email: "alice.smith@acme.example",
  contact_phone: "+1-415-555-0123",
  address: {
    line1: "1 Market St",
    city: "San Francisco",
    state: "CA",
    postal_code: "94105",
    country: "US"
  },
  payment_terms: "NET_30",
  rating: 4.5,
  active: true,
  created_at: ISODate("2025-11-09T13:00:00Z"),
  updated_at: ISODate("2025-11-09T13:00:00Z")
}
```

---

### 3. products

```js
{
  _id: ObjectId(),
  product_id: "P1001",
  name: "Wireless Mouse",
  description: "Ergonomic wireless mouse with 2.4GHz receiver",
  category: "Electronics",
  subcategory: "Accessories",
  vendor_id: "V1001",
  secondary_vendor_ids: ["V1002"],
  base_price: 29.99,
  current_price: 24.99,
  cost: 15.00,
  currency: "USD",
  status: "active",
  attributes: { color: "black", connectivity: "wireless", dpi: 1600 },
  created_at: ISODate("2025-11-09T13:00:00Z"),
  updated_at: ISODate("2025-11-09T13:00:00Z")
}
```

---

### 4. inventory

```js
{
  _id: ObjectId(),
  product_id: "P1001",
  location_id: "WH-CHI-01",
  location_type: "warehouse",
  on_hand_qty: 120,
  reserved_qty: 15,
  available_qty: 105,
  reorder_level: 50,
  safety_stock: 25,
  last_restocked_at: ISODate("2025-11-08T15:30:00Z"),
  last_counted_at: ISODate("2025-11-08T16:00:00Z"),
  last_restock_source: { vendor_id: "V1001", purchase_order_id: "PO-90001" },
  created_at: ISODate("2025-11-01T10:00:00Z"),
  updated_at: ISODate("2025-11-09T13:00:00Z")
}
```

---

### 5. orders

```js
{
  _id: ObjectId(),
  order_id: "O200001",
  customer_id: "C100001",
  order_date: ISODate("2025-11-09T13:15:00Z"),
  status: "SHIPPED",
  status_history: [
    { status: "NEW", at: ISODate("2025-11-09T13:15:00Z") },
    { status: "PAID", at: ISODate("2025-11-09T13:16:30Z") },
    { status: "SHIPPED", at: ISODate("2025-11-10T09:02:00Z") }
  ],
  line_items: [
    {
      line_no: 1,
      product_id: "P1001",
      vendor_id: "V1001",
      quantity: 2,
      unit_price: 24.99,
      discount_amount: 5.00,
      tax_amount: 3.50,
      extended_price: 48.98
    }
  ],
  totals: { subtotal: 148.97, tax: 12.91, shipping: 5.00, discount: 5.00, grand_total: 161.88 },
  shipping_address: { name: "Jane Doe", line1: "123 Main St", city: "Chicago", state: "IL" },
  payment: { method: "card", provider: "VISA", last4: "4242", transaction_id: "TX-987654321" },
  shipment: { carrier: "UPS", tracking_number: "1Z9999W99999999999" },
  created_at: ISODate("2025-11-09T13:15:00Z"),
  updated_at: ISODate("2025-11-10T09:02:00Z")
}
```

---

## Usage Notes

- All collections have `created_at` and `updated_at` for CDC analysis.
- IDs (`customer_id`, `product_id`, `vendor_id`, `order_id`) can be used for joins in ClickHouse.
- Works great for Debezium Mongo CDC → Kafka → ClickHouse → Grafana.
