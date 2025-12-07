// ================================================
// MongoDB CDC Demo Schema (Schema Only - No Data)
// ================================================
// Usage:
//   mongosh "mongodb://127.0.0.1:27017" init-sales-db.js
// ================================================

print("\n=== Initializing MongoDB CDC Demo (sales) — SCHEMA ONLY ===\n");

const dbName = "sales";
const salesDb = db.getSiblingDB(dbName);

// Nuke the database to get a clean slate
salesDb.dropDatabase();

// -------------------------------
// Customers collection + validator
// -------------------------------
salesDb.createCollection("customers", {
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

// Other collections (no validators yet, but explicit)
salesDb.createCollection("vendors");
salesDb.createCollection("products");
salesDb.createCollection("inventory");
salesDb.createCollection("orders");

// -------------------------------
// Indexes (no documents yet)
// -------------------------------
salesDb.customers.createIndex({ customer_id: 1 }, { unique: true });
salesDb.customers.createIndex({ email: 1 }, { unique: true });

salesDb.vendors.createIndex({ vendor_id: 1 }, { unique: true });

salesDb.products.createIndex({ product_id: 1 }, { unique: true });

salesDb.inventory.createIndex({ product_id: 1, location_id: 1 }, { unique: true });

salesDb.orders.createIndex({ order_id: 1 }, { unique: true });
salesDb.orders.createIndex({ customer_id: 1, order_date: -1 });
salesDb.orders.createIndex({ "line_items.product_id": 1 });

print("\n✅ MongoDB CDC Demo schema created (no data). Run seed-sales-data.js to populate.\n");
