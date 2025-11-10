// seed-sales-data.js
// Populate MongoDB "sales" DB with realistic CDC-friendly data.
// Usage:
//   mongosh "mongodb://127.0.0.1:27017" seed-sales-data.js

(function() {
  const dbName = "sales";
  const appDb = db.getSiblingDB(dbName);

  print("[seed] Using DB: " + dbName);

  // --------------------------------------------------------
  // Helpers
  // --------------------------------------------------------
  function randChoice(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function randInt(min, max) {
    // inclusive [min, max]
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  function addMinutes(date, mins) {
    return new Date(date.getTime() + mins * 60000);
  }

  function formatOrderId(date, seq) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    const s = String(seq).padStart(5, "0");
    return `O${y}${m}${d}-${s}`;
  }

  // --------------------------------------------------------
  // Ensure base collections have enough seed entities
  // --------------------------------------------------------
  function ensureCustomers() {
    const coll = appDb.customers;
    const count = coll.countDocuments();
    if (count >= 5) {
      print(`[seed] Customers already present: ${count}`);
      return;
    }
    print("[seed] Seeding baseline customers...");
    coll.insertMany([
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
      },
      {
        customer_id: "C100003",
        first_name: "Alice",
        last_name: "Nguyen",
        email: "alice.nguyen@example.com",
        phone: "+1-617-555-0102",
        addresses: [
          {
            address_id: "ADDR-3",
            type: "shipping",
            line1: "10 State St",
            city: "Boston",
            state: "MA",
            postal_code: "02109",
            country: "US",
            is_default: true
          }
        ],
        status: "active",
        loyalty_level: "platinum",
        marketing_opt_in: true,
        created_at: new Date(),
        updated_at: new Date()
      },
      {
        customer_id: "C100004",
        first_name: "Michael",
        last_name: "Garcia",
        email: "michael.garcia@example.com",
        phone: "+1-213-555-0190",
        addresses: [
          {
            address_id: "ADDR-4",
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
        marketing_opt_in: false,
        created_at: new Date(),
        updated_at: new Date()
      },
      {
        customer_id: "C100005",
        first_name: "Sara",
        last_name: "Patel",
        email: "sara.patel@example.com",
        phone: "+1-312-555-0180",
        addresses: [
          {
            address_id: "ADDR-5",
            type: "shipping",
            line1: "800 N Michigan",
            city: "Chicago",
            state: "IL",
            postal_code: "60611",
            country: "US",
            is_default: true
          }
        ],
        status: "active",
        loyalty_level: "silver",
        marketing_opt_in: true,
        created_at: new Date(),
        updated_at: new Date()
      }
    ]);
  }

  function ensureVendors() {
    const coll = appDb.vendors;
    const count = coll.countDocuments();
    if (count >= 3) {
      print(`[seed] Vendors already present: ${count}`);
      return;
    }
    print("[seed] Seeding baseline vendors...");
    coll.insertMany([
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
      },
      {
        vendor_id: "V1003",
        name: "Midwest Components LLC",
        contact_name: "Karen Lee",
        contact_email: "karen.lee@midwestcomponents.example",
        contact_phone: "+1-312-555-0222",
        address: {
          line1: "500 W Randolph",
          city: "Chicago",
          state: "IL",
          postal_code: "60661",
          country: "US"
        },
        payment_terms: "NET_15",
        rating: 4.2,
        active: true,
        created_at: new Date(),
        updated_at: new Date()
      }
    ]);
  }

  function ensureProductsAndInventory() {
    const productsColl = appDb.products;
    const inventoryColl = appDb.inventory;

    const productCount = productsColl.countDocuments();
    if (productCount >= 5) {
      print(`[seed] Products already present: ${productCount}`);
    } else {
      print("[seed] Seeding baseline products...");
      productsColl.insertMany([
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
          cost: 15.0,
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
          base_price: 99.0,
          current_price: 89.0,
          cost: 60.0,
          currency: "USD",
          status: "active",
          attributes: { layout: "US", switch: "blue", backlight: "RGB" },
          created_at: new Date(),
          updated_at: new Date()
        },
        {
          product_id: "P1003",
          name: "27\" 4K Monitor",
          description: "Ultra HD monitor with HDMI/DisplayPort",
          category: "Electronics",
          subcategory: "Monitors",
          vendor_id: "V1001",
          base_price: 399.0,
          current_price: 349.0,
          cost: 260.0,
          currency: "USD",
          status: "active",
          attributes: { size_inch: 27, resolution: "3840x2160" },
          created_at: new Date(),
          updated_at: new Date()
        },
        {
          product_id: "P1004",
          name: "USB-C Docking Station",
          description: "Multi-port dock with Ethernet, HDMI, USB",
          category: "Electronics",
          subcategory: "Docking Stations",
          vendor_id: "V1003",
          base_price: 149.0,
          current_price: 129.0,
          cost: 90.0,
          currency: "USD",
          status: "active",
          attributes: { ports: 8, power_delivery_watts: 100 },
          created_at: new Date(),
          updated_at: new Date()
        },
        {
          product_id: "P1005",
          name: "Noise Cancelling Headphones",
          description: "Over-ear wireless ANC headphones",
          category: "Electronics",
          subcategory: "Audio",
          vendor_id: "V1002",
          base_price: 249.0,
          current_price: 219.0,
          cost: 150.0,
          currency: "USD",
          status: "active",
          attributes: { wireless: true, anc: true },
          created_at: new Date(),
          updated_at: new Date()
        }
      ]);
    }

    const allProducts = productsColl.find().toArray();
    const inventoryCount = inventoryColl.countDocuments();
    if (inventoryCount === 0) {
      print("[seed] Seeding inventory for all products at WH-CHI-01...");
      const invDocs = allProducts.map(p => ({
        product_id: p.product_id,
        location_id: "WH-CHI-01",
        location_type: "warehouse",
        on_hand_qty: randInt(80, 200),
        reserved_qty: 0,
        available_qty: 0, // we'll recompute below
        reorder_level: randInt(30, 80),
        safety_stock: randInt(15, 40),
        last_restocked_at: new Date(),
        last_counted_at: new Date(),
        last_restock_source: {
          vendor_id: p.vendor_id,
          purchase_order_id: "PO-" + randInt(90000, 99999)
        },
        created_at: new Date(),
        updated_at: new Date()
      }));
      invDocs.forEach(doc => {
        doc.available_qty = doc.on_hand_qty - doc.reserved_qty;
      });
      inventoryColl.insertMany(invDocs);
    } else {
      print(`[seed] Inventory already present: ${inventoryCount}`);
    }
  }

  ensureCustomers();
  ensureVendors();
  ensureProductsAndInventory();

  const customers = appDb.customers.find().toArray();
  const products = appDb.products.find().toArray();
  const inventoryByProduct = {};
  appDb.inventory.find().forEach(doc => {
    inventoryByProduct[doc.product_id] = doc;
  });

  if (!customers.length || !products.length) {
    print("[seed] ERROR: Need customers and products to generate orders.");
    return;
  }

  // --------------------------------------------------------
  // Generate orders over a rolling time window
  // --------------------------------------------------------
  const ordersColl = appDb.orders;
  print("[seed] Clearing existing orders...");
  ordersColl.deleteMany({});

  const now = new Date();
  const daysBack = 30;           // simulate last 30 days
  const startDate = new Date(now.getTime() - daysBack * 24 * 3600 * 1000);

  let totalOrders = 0;

  for (let d = 0; d < daysBack; d++) {
    const day = new Date(startDate.getTime() + d * 24 * 3600 * 1000);

    // Vary traffic by day of week: more on weekdays, less weekends
    const dayOfWeek = day.getDay(); // 0=Sun
    let baseOrdersPerDay = (dayOfWeek === 0 || dayOfWeek === 6) ? 20 : 40;

    // Add some noise
    baseOrdersPerDay += randInt(-5, 10);
    if (baseOrdersPerDay < 5) baseOrdersPerDay = 5;

    print(`[seed] Generating ~${baseOrdersPerDay} orders for ${day.toISOString().slice(0, 10)}...`);

    // Distribute orders across hours (with peaks in 10:00–14:00)
    const ordersForDay = [];
    let seq = 1;

    for (let i = 0; i < baseOrdersPerDay; i++) {
      const peak = randInt(0, 100) < 60; // 60% of traffic in peak hours
      const hour = peak ? randInt(10, 14) : randInt(7, 21);
      const minute = randInt(0, 59);
      const second = randInt(0, 59);
      const orderTs = new Date(
        day.getFullYear(),
        day.getMonth(),
        day.getDate(),
        hour,
        minute,
        second
      );

      const orderId = formatOrderId(day, seq++);
      const customer = randChoice(customers);

      // 1–3 line items per order
      const numLines = randInt(1, 3);
      const chosenProducts = [];
      for (let j = 0; j < numLines; j++) {
        chosenProducts.push(randChoice(products));
      }

      const lineItems = [];
      let subtotal = 0;
      let discountTotal = 0;
      let taxTotal = 0;

      chosenProducts.forEach((prod, idx) => {
        const quantity = randInt(1, 4);
        // occasional sale discount 0–20%
        const discountPct = randInt(0, 100) < 25 ? randInt(5, 20) : 0;
        const unitPrice = prod.current_price;
        const lineBase = unitPrice * quantity;
        const lineDiscount = (lineBase * discountPct) / 100.0;
        const taxable = lineBase - lineDiscount;
        const tax = taxable * 0.10; // assume flat 10% tax rate

        subtotal += lineBase;
        discountTotal += lineDiscount;
        taxTotal += tax;

        lineItems.push({
          line_no: idx + 1,
          product_id: prod.product_id,
          vendor_id: prod.vendor_id,
          quantity: quantity,
          unit_price: unitPrice,
          discount_amount: lineDiscount,
          tax_amount: tax,
          extended_price: taxable + tax
        });

        // adjust inventory in memory
        const inv = inventoryByProduct[prod.product_id];
        if (inv) {
          inv.on_hand_qty -= quantity;
          if (inv.on_hand_qty < 0) inv.on_hand_qty = 0;
          inv.available_qty = inv.on_hand_qty - inv.reserved_qty;
        }
      });

      const shipping = subtotal > 200 ? 0 : 5.0;
      const grandTotal = subtotal - discountTotal + taxTotal + shipping;

      // Order lifecycle
      const isCanceled = randInt(0, 100) < 10; // ~10% canceled
      let status = "SHIPPED";
      const statusHistory = [];
      const createdAt = orderTs;
      statusHistory.push({ status: "NEW", at: createdAt, reason: "order_created" });

      const paidAt = addMinutes(createdAt, randInt(2, 45));
      statusHistory.push({ status: "PAID", at: paidAt, reason: "payment_captured" });

      if (isCanceled) {
        status = "CANCELED";
        const canceledAt = addMinutes(paidAt, randInt(5, 60));
        statusHistory.push({ status: "CANCELED", at: canceledAt, reason: "customer_request" });
      } else {
        const shippedAt = addMinutes(paidAt, randInt(60, 24 * 60)); // within a day
        statusHistory.push({ status: "SHIPPED", at: shippedAt, reason: "label_printed" });
      }

      const shippingAddress =
        (customer.addresses && customer.addresses.length > 0)
          ? {
              name: customer.first_name + " " + customer.last_name,
              line1: customer.addresses[0].line1,
              city: customer.addresses[0].city,
              state: customer.addresses[0].state,
              postal_code: customer.addresses[0].postal_code,
              country: customer.addresses[0].country
            }
          : {
              name: customer.first_name + " " + customer.last_name,
              line1: "Unknown",
              city: "Unknown",
              state: "NA",
              postal_code: "00000",
              country: "US"
            };

      const orderDoc = {
        order_id: orderId,
        customer_id: customer.customer_id,
        order_date: createdAt,
        status: status,
        status_history: statusHistory,
        line_items: lineItems,
        totals: {
          subtotal: Number(subtotal.toFixed(2)),
          tax: Number(taxTotal.toFixed(2)),
          shipping: Number(shipping.toFixed(2)),
          discount: Number(discountTotal.toFixed(2)),
          grand_total: Number(grandTotal.toFixed(2))
        },
        shipping_address: shippingAddress,
        payment: {
          method: "card",
          provider: randChoice(["VISA", "MASTERCARD", "AMEX"]),
          last4: String(randInt(1000, 9999)),
          transaction_id: "TX-" + randInt(100000000, 999999999),
          paid_at: paidAt
        },
        shipment: isCanceled
          ? null
          : {
              carrier: randChoice(["UPS", "FedEx", "USPS"]),
              service_level: randChoice(["GROUND", "2-DAY", "OVERNIGHT"]),
              tracking_number: "1Z" + randInt(1000000000, 9999999999),
              shipped_at: statusHistory[statusHistory.length - 1].at,
              delivered_at: null
            },
        created_at: createdAt,
        updated_at: statusHistory[statusHistory.length - 1].at
      };

      ordersForDay.push(orderDoc);
    }

    if (ordersForDay.length) {
      ordersColl.insertMany(ordersForDay);
      totalOrders += ordersForDay.length;
    }

    // Occasional price adjustments for some products
    if (randInt(0, 100) < 30) {
      const p = randChoice(products);
      const delta = randInt(-10, 10); // -10% to +10%
      const newPrice = Math.max(5, p.current_price * (1 + delta / 100.0));
      appDb.products.updateOne(
        { product_id: p.product_id },
        {
          $set: {
            current_price: Number(newPrice.toFixed(2)),
            updated_at: new Date()
          }
        }
      );
    }

    // Periodic restock if inventory too low
    Object.keys(inventoryByProduct).forEach(pid => {
      const inv = inventoryByProduct[pid];
      if (!inv) return;
      if (inv.on_hand_qty < inv.reorder_level) {
        const restockQty = randInt(inv.reorder_level, inv.reorder_level * 2);
        inv.on_hand_qty += restockQty;
        inv.available_qty = inv.on_hand_qty - inv.reserved_qty;
        inv.last_restocked_at = new Date();
        inv.updated_at = new Date();

        appDb.inventory.updateOne(
          { product_id: pid, location_id: inv.location_id },
          {
            $set: {
              on_hand_qty: inv.on_hand_qty,
              available_qty: inv.available_qty,
              last_restocked_at: inv.last_restocked_at,
              updated_at: inv.updated_at
            }
          }
        );
      } else {
        // still touch updated_at occasionally to produce CDC noise
        if (randInt(0, 100) < 15) {
          inv.last_counted_at = new Date();
          inv.updated_at = new Date();
          appDb.inventory.updateOne(
            { product_id: pid, location_id: inv.location_id },
            {
              $set: {
                last_counted_at: inv.last_counted_at,
                updated_at: inv.updated_at
              }
            }
          );
        }
      }
    });
  }

  print(`[seed] Inserted total orders: ${totalOrders}`);

  // Basic indexes for orders (in case init script didn't build them)
  ordersColl.createIndex({ order_id: 1 }, { unique: true });
  ordersColl.createIndex({ customer_id: 1, order_date: -1 });
  ordersColl.createIndex({ "line_items.product_id": 1, order_date: -1 });

  print("[seed] Done.");
})();
