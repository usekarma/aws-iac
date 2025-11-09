#!/usr/bin/env bash
set -euo pipefail

# Simple Mongo traffic generator for CDC testing.
# Inserts, updates, and deletes documents in sales.orders.

MONGO_HOST="${MONGO_HOST:-127.0.0.1}"
MONGO_PORT="${MONGO_PORT:-27017}"
DB_NAME="${DB_NAME:-sales}"
COLL_NAME="${COLL_NAME:-orders}"

# How many records to insert (default 10)
COUNT="${1:-10}"
# Delay between operations in seconds
SLEEP_SEC="${SLEEP_SEC:-1}"

echo "[seed] Target Mongo: mongodb://${MONGO_HOST}:${MONGO_PORT}/${DB_NAME}"
echo "[seed] Collection: ${DB_NAME}.${COLL_NAME}"
echo "[seed] Count: ${COUNT}, Sleep: ${SLEEP_SEC}s"
echo

# Currencies to pick from
CURRENCIES=(USD EUR GBP JPY CAD AUD)

# Frequent / "loyal" customers that should repeat often
FREQ_CUSTOMERS=(C1001 C1002 C1003 C2001 C2002 C3001 C4001 C5001)

for ((i=1; i<=COUNT; i++)); do
  # Order id is unique, sequential
  ORDER_ID="O$(printf '%06d' "$i")"

  # Choose customer:
  # ~65% of orders go to the frequent customers,
  # ~35% go to a random ad-hoc customer.
  if (( RANDOM % 100 < 65 )); then
    CUSTOMER_ID="${FREQ_CUSTOMERS[$((RANDOM % ${#FREQ_CUSTOMERS[@]}))]}"
  else
    CUSTOMER_ID="C$(printf '%04d' "$((RANDOM % 5000))")"
  fi

  # Random amount between 5.00 and 500.00
  AMOUNT_CENTS=$(( (RANDOM % 49500) + 500 ))    # 500..49999
  AMOUNT_DOLLARS=$(( AMOUNT_CENTS / 100 ))
  AMOUNT_REMAINDER=$(( AMOUNT_CENTS % 100 ))
  AMOUNT="$(printf '%d.%02d' "$AMOUNT_DOLLARS" "$AMOUNT_REMAINDER")"

  # Random currency
  CURRENCY="${CURRENCIES[$((RANDOM % ${#CURRENCIES[@]}))]}"

  echo "[seed] Inserting order ${i} (order_id=${ORDER_ID}, customer=${CUSTOMER_ID}, amount=${AMOUNT} ${CURRENCY})"

  mongosh --quiet "mongodb://${MONGO_HOST}:${MONGO_PORT}" <<EOF
const dbName = "${DB_NAME}";
const collName = "${COLL_NAME}";
const db = db.getSiblingDB(dbName);
const coll = db[collName];

// Spread created_at randomly over the last 7 days
const now = new Date();
const maxMinutes = 7 * 24 * 60; // 7 days in minutes
const minutesAgo = Math.floor(Math.random() * maxMinutes);
const createdAt = new Date(now.getTime() - minutesAgo * 60000);

const doc = {
  order_id: "${ORDER_ID}",
  customer_id: "${CUSTOMER_ID}",
  amount: ${AMOUNT},
  currency: "${CURRENCY}",
  status: "NEW",
  created_at: createdAt,
  updated_at: createdAt
};

coll.insertOne(doc);

// ~40% chance to update this order (new status + slightly tweaked amount)
if (Math.random() < 0.4) {
  const statuses = ["PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED"];
  const randomStatus = statuses[Math.floor(Math.random() * statuses.length)];

  // Adjust amount by -20% .. +20%, keep 2 decimals
  const baseAmount = ${AMOUNT};
  const factor = 0.8 + Math.random() * 0.4; // 0.8..1.2
  const newAmount = +(baseAmount * factor).toFixed(2);

  coll.updateOne(
    { order_id: "${ORDER_ID}" },
    { \$set: { status: randomStatus, amount: newAmount, updated_at: new Date() } }
  );
}

// ~10% chance to delete this order
if (Math.random() < 0.1) {
  coll.deleteOne({ order_id: "${ORDER_ID}" });
}
EOF

  sleep "${SLEEP_SEC}"
done

echo "[seed] Done."
