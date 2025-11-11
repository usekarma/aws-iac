// seed-sales-data.js
// Populate MongoDB "sales" DB with realistic CDC-friendly data.
// Usage:
//   mongosh "mongodb://127.0.0.1:27017" /usr/local/bin/seed-sales-data.js

(function () {
  const dbName = "sales";
  const appDb = db.getSiblingDB(dbName);

  print("[seed] Using DB: " + dbName);

  // ================================
  // Tunable knobs
  // ================================
  const DAYS_BACK = 180;              // how many days of history
  const WEEKDAY_BASE_ORDERS = 80;     // baseline weekday volume
  const WEEKEND_BASE_ORDERS = 40;     // baseline weekend volume
  const EXTRA_SYNTHETIC_CUSTOMERS = 200; // on top of the baseline "named" customers

  // --------------------------------------------------------
  // Helpers
  // --------------------------------------------------------
  function randChoice(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  function randFloat(min, max, decimals) {
    const v = Math.random() * (max - min) + min;
    const factor = Math.pow(10, decimals || 2);
    return Math.round(v * factor) / factor;
  }

  function makeDateInDay(day) {
    // day is a Date at midnight; add random hour/min/sec
    const d = new Date(day.getTime());
    d.setHours(randInt(0, 23), randInt(0, 59), randInt(0, 59), 0);
    return d;
  }

  // --------------------------------------------------------
  // Baseline Customers (idempotent upserts)
  // --------------------------------------------------------
  function ensureBaseCustomers() {
    const coll = appDb.customers;

    const baseCustomers = [
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
        marketing_opt_in: true
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
        marketing_opt_in: false
      },
      {
        customer_id: "C100003",
        first_name: "Alice",
        last_name: "Nguyen",
        email: "alice.nguyen@example.com",
        phone: "+1-617-555-0123",
        addresses: [
          {
            address_id: "ADDR-3",
            type: "shipping",
            line1: "1 Market St",
            city: "San Francisco",
            state: "CA",
            postal_code: "94105",
            country: "US",
            is_default: true
          }
        ],
        status: "active",
        loyalty_level: "platinum",
        marketing_opt_in: true
      },
      {
        customer_id: "C100004",
        first_name: "Robert",
        last_name: "Garcia",
        email: "robert.garcia@example.com",
        phone: "+1-773-555-0456",
        addresses: [
          {
            address_id: "ADDR-4",
            type: "shipping",
            line1: "750 N Rush St",
            city: "Chicago",
            state: "IL",
            postal_code: "60611",
            country: "US",
            is_default: true
          }
        ],
        status: "active",
        loyalty_level: "bronze",
        marketing_opt_in: true
      },
      {
        customer_id: "C100005",
        first_name: "Emily",
        last_name: "Chen",
        email: "emily.chen@example.com",
        phone: "+1-213-555-0789",
        addresses: [
          {
            address_id: "ADDR-5",
            type: "shipping",
            line1: "200 Spring St",
            city: "Los Angeles",
            state: "CA",
            postal_code: "90013",
            country: "US",
            is_default: true
          }
        ],
        status: "active",
        loyalty_level: "bronze",
        marketing_opt_in: false
      }
    ];

    print("[seed] Ensuring baseline customers...");
    baseCustomers.forEach((c) => {
      const now = new Date();
      c.created_at = c.created_at || now;
      c.updated_at = now;
      coll.updateOne(
        { customer_id: c.customer_id },
        { $set: c },
        { upsert: true }
      );
    });
    print("[seed] Baseline customers upserted.");
  }

  // Extra synthetic customers for volume
  function addSyntheticCustomers(extraCount) {
    const coll = appDb.customers;
    const baseCount = coll.countDocuments();
    print(
      `[seed] Adding ~${extraCount} synthetic customers (current count: ${baseCount})...`
    );

    const bulk = [];
    for (let i = 0; i < extraCount; i++) {
      const n = baseCount + i + 1;
      bulk.push({
        customer_id: `C${100000 + n}`,
        first_name: `Cust${n}`,
        last_name: "Demo",
        email: `customer${n}@example.com`,
        phone: `+1-555-000-${String(n).padStart(4, "0")}`,
        addresses: [
          {
            address_id: `ADDR-${n}`,
            type: "shipping",
            line1: `${100 + (n % 900)} Demo St`,
            city: randChoice(["Chicago", "New York", "Los Angeles", "Dallas"]),
            state: randChoice(["IL", "NY", "CA", "TX"]),
            postal_code: "60601",
            country: "US",
            is_default: true
          }
        ],
        status: "active",
        loyalty_level: randChoice(["bronze", "silver", "gold", "platinum"]),
        marketing_opt_in: randInt(0, 100) < 60,
        created_at: new Date(),
        updated_at: new Date()
      });
    }

    if (bulk.length) {
      coll.insertMany(bulk);
      print(`[seed] Inserted ${bulk.length} synthetic customers.`);
    }
  }

  // --------------------------------------------------------
  // Vendors (idempotent upserts)
  // --------------------------------------------------------
  function ensureVendors() {
    const coll = appDb.vendors;

    const vendors = [
      {
        vendor_id: "V1001",
        name: "Acme Supplies",
        contact_email: "sales@acmesupplies.com",
        status: "active",
        terms: "NET_30"
      },
      {
        vendor_id: "V1002",
        name: "Global Tech Distributors",
        contact_email: "accounts@globaltech.example",
        status: "active",
        terms: "NET_45"
      },
      {
        vendor_id: "V1003",
        name: "Midwest Retail Partners",
        contact_email: "info@midwestretail.example",
        status: "active",
        terms: "NET_30"
      }
    ];

    print("[seed] Ensuring baseline vendors...");
    vendors.forEach((v) => {
      const now = new Date();
      v.created_at = v.created_at || now;
      v.updated_at = now;
      coll.updateOne(
        { vendor_id: v.vendor_id },
        { $set: v },
        { upsert: true }
      );
    });
    print("[seed] Baseline vendors upserted.");
  }

  // --------------------------------------------------------
  // Products & Inventory (idempotent upserts)
  // --------------------------------------------------------
  function ensureProductsAndInventory() {
    const productsColl = appDb.products;
    const inventoryColl = appDb.inventory;

    const products = [
      {
        product_id: "P1001",
        name: "Wireless Mouse",
        category: "Electronics",
        unit_price: 24.99,
        vendor_id: "V1001"
      },
      {
        product_id: "P1002",
        name: "Mechanical Keyboard",
        category: "Electronics",
        unit_price: 89.99,
        vendor_id: "V1001"
      },
      {
        product_id: "P1003",
        name: "USB-C Docking Station",
        category: "Accessories",
        unit_price: 149.99,
        vendor_id: "V1002"
      },
      {
        product_id: "P1004",
        name: "27\" 4K Monitor",
        category: "Displays",
        unit_price: 329.99,
        vendor_id: "V1002"
      },
      {
        product_id: "P1005",
        name: "Noise-Cancelling Headphones",
        category: "Audio",
        unit_price: 199.99,
        vendor_id: "V1003"
      }
    ];

    print("[seed] Ensuring baseline products...");
    products.forEach((p) => {
      const now = new Date();
      p.created_at = p.created_at || now;
      p.updated_at = now;
      productsColl.updateOne(
        { product_id: p.product_id },
        { $set: p },
        { upsert: true }
      );

      // Inventory: one primary Chicago warehouse row per product
      const invKey = { product_id: p.product_id, location_id: "WH-CHI-01" };
      const invDoc = {
        product_id: p.product_id,
        location_id: "WH-CHI-01",
        on_hand: randInt(100, 500),
        on_order: randInt(0, 100),
        safety_stock: 50,
        updated_at: now
      };

      inventoryColl.updateOne(invKey, { $set: invDoc }, { upsert: true });
    });
    print("[seed] Baseline products + inventory upserted.");
  }

  // --------------------------------------------------------
  // Orders (large volume, orders only are wiped)
  // --------------------------------------------------------
  function generateOrders() {
    const ordersColl = appDb.orders;
    const customers = appDb.customers.find({ status: "active" }).toArray();
    const vendors = appDb.vendors.find({ status: "active" }).toArray();
    const products = appDb.products.find({}).toArray();

    if (!customers.length || !vendors.length || !products.length) {
      throw new Error(
        "Need customers, vendors, and products before generating orders."
      );
    }

    print("[seed] Clearing existing orders...");
    ordersColl.deleteMany({});

    const now = new Date();
    const daysBack = DAYS_BACK;
    const startDate = new Date(
      now.getTime() - daysBack * 24 * 3600 * 1000
    );

    let totalOrders = 0;
    let globalOrderSeq = 1;

    for (let d = 0; d < daysBack; d++) {
      const day = new Date(startDate.getTime() + d * 24 * 3600 * 1000);
      const dayStr = day.toISOString().slice(0, 10);
      const dayOfWeek = day.getDay(); // 0=Sun

      let baseOrdersPerDay =
        dayOfWeek === 0 || dayOfWeek === 6
          ? WEEKEND_BASE_ORDERS
          : WEEKDAY_BASE_ORDERS;

      baseOrdersPerDay += randInt(-10, 25);
      if (baseOrdersPerDay < 20) baseOrdersPerDay = 20;

      print(
        `[seed] Generating ~${baseOrdersPerDay} orders for ${dayStr}...`
      );

      const dayOrders = [];
      for (let i = 0; i < baseOrdersPerDay; i++) {
        const customer = randChoice(customers);
        const vendor = randChoice(vendors);
        const orderDate = makeDateInDay(day);

        const numItems = randInt(1, 5);
        const usedProductIds = new Set();
        const lineItems = [];
        let orderTotal = 0;

        for (let j = 0; j < numItems; j++) {
          let product;
          // try to avoid duplicate products in same order
          for (let attempts = 0; attempts < 5; attempts++) {
            product = randChoice(products);
            if (!usedProductIds.has(product.product_id)) break;
          }
          usedProductIds.add(product.product_id);

          const qty = randInt(1, 5);
          const unitPrice =
            product.unit_price *
            (1 + randFloat(-0.05, 0.05, 4)); // small price drift
          const extended = unitPrice * qty;

          orderTotal += extended;

          lineItems.push({
            product_id: product.product_id,
            quantity: qty,
            unit_price: Math.round(unitPrice * 100) / 100,
            extended_price: Math.round(extended * 100) / 100
          });
        }

        orderTotal = Math.round(orderTotal * 100) / 100;

        const orderId = `SO-${String(globalOrderSeq).padStart(8, "0")}`;
        globalOrderSeq++;

        const addr =
          (customer.addresses && customer.addresses[0]) || {
            address_id: "ADDR-DEFAULT",
            type: "shipping",
            line1: "Unknown",
            city: "Unknown",
            state: "NA",
            postal_code: "00000",
            country: "US",
            is_default: true
          };

        const paymentMethod = randChoice([
          "visa",
          "mastercard",
          "amex",
          "paypal"
        ]);
        const channel = randChoice(["web", "mobile", "phone", "store"]);

        const statusRoll = randInt(1, 100);
        let status = "NEW";
        if (statusRoll > 90) status = "CANCELLED";
        else if (statusRoll > 70) status = "SHIPPED";
        else if (statusRoll > 40) status = "PAID";

        const doc = {
          order_id: orderId,
          customer_id: customer.customer_id,
          vendor_id: vendor.vendor_id,
          order_date: orderDate,
          status: status,
          line_items: lineItems,
          order_total: orderTotal,
          currency: "USD",
          payment_method: paymentMethod,
          sales_channel: channel,
          shipping_address: addr,
          billing_address: addr,
          created_at: orderDate,
          updated_at: orderDate
        };

        dayOrders.push(doc);
      }

      if (dayOrders.length) {
        ordersColl.insertMany(dayOrders);
        totalOrders += dayOrders.length;
      }
    }

    print(`[seed] Inserted total orders: ${totalOrders}`);

    // Basic indexes for orders (in case init script didn't build them)
    ordersColl.createIndex({ order_id: 1 }, { unique: true });
    ordersColl.createIndex({ customer_id: 1, order_date: -1 });
    ordersColl.createIndex({ "line_items.product_id": 1, order_date: -1 });

    print("[seed] Orders generation complete.");
  }

  // --------------------------------------------------------
  // Main
  // --------------------------------------------------------
  print("[seed] Starting seeding process...");

  ensureBaseCustomers();
  ensureVendors();
  ensureProductsAndInventory();

  if (EXTRA_SYNTHETIC_CUSTOMERS > 0) {
    addSyntheticCustomers(EXTRA_SYNTHETIC_CUSTOMERS);
  }

  generateOrders();

  print("[seed] Done.");
})();
