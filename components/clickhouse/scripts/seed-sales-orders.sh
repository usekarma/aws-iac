#!/usr/bin/env bash
set -euo pipefail

# Simple Mongo traffic generator for CDC testing.
# Inserts and updates documents in sales.orders.

MONGO_HOST="${MONGO_HOST:-127.0.0.1}"
MONGO_PORT="${MONGO_PORT:-27017}"
DB_NAME="${DB_NAME:-sales}"
COLL_NAME="${COLL_NAME:-orders}"

# How many records to insert
COUNT="${1:-10}"
# Delay between operations in seconds
SLEEP_SEC="${SLEEP_SEC:-1}"

echo "[seed] Target Mongo: mongodb://${MONGO_HOST}:${MONGO_PORT}/${DB_NAME}"
echo "[seed] Collection: ${DB_NAME}.${COLL_NAME}"
echo "[seed] Count: ${COUNT}, Sleep: ${SLEEP_SEC}s"
echo

for ((i=1; i<=COUNT; i++)); do
  CUSTOMER_ID="C$(printf '%04d' "$i")"
  PRODUCT_ID="P$(( (RANDOM % 10) + 1 ))"
  QTY=$(( (RANDOM % 5) + 1 ))
  PRICE_CENTS=$(( (RANDOM % 5000) + 500 )) # between 5.00 and 55.00
  PRICE="$(printf '%.2f' "$(echo "$PRICE_CENTS / 100" | bc -l)")"

  echo "[seed] Inserting order ${i} (customer=${CUSTOMER_ID}, product=${PRODUCT_ID}, qty=${QTY}, price=${PRICE})"

  mongosh --quiet "mongodb://${MONGO_HOST}:${MONGO_PORT}" <<EOF
const dbName = "${DB_NAME}";
const collName = "${COLL_NAME}";
const db = db.getSiblingDB(dbName);

const doc = {
  customer_id: "${CUSTOMER_ID}",
  product_id: "${PRODUCT_ID}",
  quantity: ${QTY},
  price: ${PRICE},
  status: "NEW",
  created_at: new Date()
};

db[collName].insertOne(doc);

// Randomly update some docs to generate 'u' CDC events
if (Math.random() < 0.4) {
  db[collName].updateOne(
    { customer_id: "${CUSTOMER_ID}" },
    { \$set: { status: "SHIPPED", shipped_at: new Date() } }
  );
}
EOF

  sleep "${SLEEP_SEC}"
done

echo "[seed] Done."
