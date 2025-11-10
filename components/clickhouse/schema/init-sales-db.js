// ================================================
// MongoDB CDC Demo Schema & Sample Data
// ================================================
// Usage:
//   mongosh "mongodb://127.0.0.1:27017" init-sales-db.js
// ================================================

print("\n=== Initializing MongoDB CDC Demo (sales) ===\n");

use("sales");

db.customers.drop();
db.vendors.drop();
db.products.drop();
db.inventory.drop();
db.orders.drop();

db.createCollection("customers", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["customer_id", "first_name", "last_name", "email", "created_at"],
      properties: {
        customer_id: { bsonType: "string" },
        email: { bsonType: "string" },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" }
      }
    }
  }
});

db.customers.insertMany([
  {
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
    created_at: new Date(),
    updated_at: new Date()
  },
  {
    customer_id: "C100002",
    first_name: "John",
    last_name: "Smith",
    email: "john.smith@example.com",
    phone: "+1-415-555-0199",
    addresses: [
      {
        address_id: "ADDR-2",
        type: "shipping",
        line1: "500 W Madison",
        city: "Chicago",
        state: "IL",
        postal_code: "60661",
        country: "US",
        is_default: true
      }
    ],
    status: "active",
    loyalty_level: "silver",
    marketing_opt_in: false,
    created_at: new Date(),
    updated_at: new Date()
  }
]);

db.customers.createIndex({ customer_id: 1 }, { unique: true });
db.customers.createIndex({ email: 1 }, { unique: true });

db.vendors.insertMany([
  {
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
    created_at: new Date(),
    updated_at: new Date()
  },
  {
    vendor_id: "V1002",
    name: "Global Tech Distributors",
    contact_name: "Bob Johnson",
    contact_email: "bob.johnson@globaltech.example",
    contact_phone: "+1-646-555-0177",
    address: {
      line1: "200 Park Ave",
      city: "New York",
      state: "NY",
      postal_code: "10017",
      country: "US"
    },
    payment_terms: "NET_45",
    rating: 4.7,
    active: true,
    created_at: new Date(),
    updated_at: new Date()
  }
]);

db.vendors.createIndex({ vendor_id: 1 }, { unique: true });

db.products.insertMany([
  {
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
    created_at: new Date(),
    updated_at: new Date()
  },
  {
    product_id: "P1002",
    name: "Mechanical Keyboard",
    description: "RGB mechanical keyboard with blue switches",
    category: "Electronics",
    subcategory: "Accessories",
    vendor_id: "V1002",
    base_price: 99.00,
    current_price: 89.00,
    cost: 60.00,
    currency: "USD",
    status: "active",
    attributes: { layout: "US", switch: "blue", backlight: "RGB" },
    created_at: new Date(),
    updated_at: new Date()
  }
]);

db.products.createIndex({ product_id: 1 }, { unique: true });

db.inventory.insertMany([
  {
    product_id: "P1001",
    location_id: "WH-CHI-01",
    location_type: "warehouse",
    on_hand_qty: 120,
    reserved_qty: 15,
    available_qty: 105,
    reorder_level: 50,
    safety_stock: 25,
    last_restocked_at: new Date(),
    last_counted_at: new Date(),
    last_restock_source: { vendor_id: "V1001", purchase_order_id: "PO-90001" },
    created_at: new Date(),
    updated_at: new Date()
  },
  {
    product_id: "P1002",
    location_id: "WH-CHI-01",
    location_type: "warehouse",
    on_hand_qty: 50,
    reserved_qty: 5,
    available_qty: 45,
    reorder_level: 20,
    safety_stock: 10,
    last_restocked_at: new Date(),
    last_counted_at: new Date(),
    last_restock_source: { vendor_id: "V1002", purchase_order_id: "PO-90002" },
    created_at: new Date(),
    updated_at: new Date()
  }
]);

db.inventory.createIndex({ product_id: 1, location_id: 1 }, { unique: true });

db.orders.insertMany([
  {
    order_id: "O200001",
    customer_id: "C100001",
    order_date: new Date(),
    status: "SHIPPED",
    status_history: [
      { status: "NEW", at: new Date(Date.now() - 3600 * 1000 * 24) },
      { status: "PAID", at: new Date(Date.now() - 3600 * 1000 * 23) },
      { status: "SHIPPED", at: new Date() }
    ],
    line_items: [
      {
        line_no: 1,
        product_id: "P1001",
        vendor_id: "V1001",
        quantity: 2,
        unit_price: 24.99,
        discount_amount: 5.0,
        tax_amount: 3.5,
        extended_price: 48.98
      },
      {
        line_no: 2,
        product_id: "P1002",
        vendor_id: "V1002",
        quantity: 1,
        unit_price: 89.0,
        discount_amount: 0.0,
        tax_amount: 9.41,
        extended_price: 98.41
      }
    ],
    totals: {
      subtotal: 148.97,
      tax: 12.91,
      shipping: 5.00,
      discount: 5.00,
      grand_total: 161.88
    },
    shipping_address: {
      name: "Jane Doe",
      line1: "123 Main St",
      city: "Chicago",
      state: "IL",
      postal_code: "60601",
      country: "US"
    },
    payment: {
      method: "card",
      provider: "VISA",
      last4: "4242",
      transaction_id: "TX-987654321",
      paid_at: new Date()
    },
    shipment: {
      carrier: "UPS",
      service_level: "GROUND",
      tracking_number: "1Z9999W99999999999",
      shipped_at: new Date()
    },
    created_at: new Date(),
    updated_at: new Date()
  }
]);

db.orders.createIndex({ order_id: 1 }, { unique: true });
db.orders.createIndex({ customer_id: 1, order_date: -1 });
db.orders.createIndex({ "line_items.product_id": 1 });

print("\n✅ MongoDB CDC Demo schema and sample data created successfully!\n");
