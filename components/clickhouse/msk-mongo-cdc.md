# MongoDB CDC to MSK with Kafka Connect (TLS, Self-Hosted, ClickHouse Ingest)

This guide sets up a pipeline: **MongoDB change streams → Kafka Connect (self-hosted) → MSK (TLS) → ClickHouse ingestion**.

---

## 1. Prerequisites

- MSK cluster with a **TLS listener** (port 9094).  
- MongoDB replica set (Atlas or self-hosted). Change streams require replica set or sharded cluster.  
- EC2 instance with access to MSK brokers and MongoDB.  

---

## 2. Install Kafka + Connect + MongoDB Kafka Connector

```bash
# Java runtime
sudo apt-get update && sudo apt-get -y install default-jre jq

# Kafka (Apache binary)
curl -LO https://archive.apache.org/dist/kafka/3.6.1/kafka_2.13-3.6.1.tgz
tar xzf kafka_2.13-3.6.1.tgz
mv kafka_2.13-3.6.1 /opt/kafka

# MongoDB Kafka Connector (plugin)
mkdir -p /opt/kafka/plugins/mongodb
curl -L -o /tmp/mongo-kafka.zip https://repo1.maven.org/maven2/org/mongodb/kafka/mongo-kafka-connect/1.12.0/mongo-kafka-connect-1.12.0.zip
unzip -o /tmp/mongo-kafka.zip -d /opt/kafka/plugins/mongodb
```

---

## 3. Configure Kafka Connect Worker (TLS)

Create `/opt/kafka/config/connect-distributed-msk.properties`:

```properties
bootstrap.servers=b-1....:9094,b-2....:9094,b-3....:9094
security.protocol=SSL

group.id=connect-mongo

offset.storage.topic=connect-offsets
config.storage.topic=connect-configs
status.storage.topic=connect-status

key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=false
value.converter.schemas.enable=false

plugin.path=/opt/kafka/plugins
rest.port=8083
```

Create the three Kafka topics if auto-create is disabled:

```bash
kafka-topics.sh --bootstrap-server b-1....:9094   --create --topic connect-offsets --partitions 25 --replication-factor 3
kafka-topics.sh --bootstrap-server b-1....:9094   --create --topic connect-configs --partitions 1 --replication-factor 3
kafka-topics.sh --bootstrap-server b-1....:9094   --create --topic connect-status --partitions 5 --replication-factor 3
```

---

## 4. Start Kafka Connect

```bash
/opt/kafka/bin/connect-distributed.sh /opt/kafka/config/connect-distributed-msk.properties > /var/log/connect.log 2>&1 &
```

---

## 5. Create MongoDB CDC Connector

Create a JSON config (`mongo-cdc-src.json`):

```json
{
  "name": "mongo-cdc-src",
  "config": {
    "connector.class": "com.mongodb.kafka.connect.MongoSourceConnector",
    "tasks.max": "2",

    "connection.uri": "mongodb://USER:PASSWORD@host1:27017,host2:27017/?replicaSet=rs0&authSource=admin",
    "database": "appdb",
    "collection": "orders",

    "topic.prefix": "mongo.cdc.",

    "publish.full.document.only": "true",
    "full.document": "updateLookup",

    "copy.existing": "true",
    "copy.existing.namespace.regex": "appdb\.orders",

    "output.format.value": "json",
    "output.format.key": "json",
    "errors.tolerance": "all",
    "errors.log.enable": "true",
    "errors.deadletterqueue.topic.name": "dlq.mongo.cdc",
    "errors.deadletterqueue.context.headers.enable": "true"
  }
}
```

Post it to the worker:

```bash
curl -s -X POST -H 'Content-Type: application/json'      localhost:8083/connectors -d @mongo-cdc-src.json | jq
```

---

## 6. Validate with `kcat`

Insert/update a doc in MongoDB, then consume from the topic:

```bash
kcat -b b-1....:9094,b-2....:9094,b-3....:9094 -t mongo.cdc.appdb.orders      -C -o beginning -e -q -X security.protocol=SSL
```

You should see JSON payloads.

---

## 7. Ingest into ClickHouse

### Kafka Table

```sql
CREATE TABLE kafka_mdb_orders
(
  _raw String
)
ENGINE = Kafka
SETTINGS
  kafka_broker_list = 'b-1....:9094,b-2....:9094,b-3....:9094',
  kafka_topic_list = 'mongo.cdc.appdb.orders',
  kafka_group_name = 'ch_mongo_orders',
  kafka_format = 'JSONEachRow',
  kafka_num_consumers = 1,
  kafka_security_protocol = 'SSL';
```

### Target Table

```sql
CREATE TABLE mdb_orders_raw
(
  _id String,
  sku String,
  qty Int32,
  price Float64,
  ts DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY _id;
```

### Materialized View

```sql
CREATE MATERIALIZED VIEW mv_mdb_orders
TO mdb_orders_raw
AS
SELECT
  JSON_VALUE(_raw, '$._id') AS _id,
  JSON_VALUE(_raw, '$.sku') AS sku,
  toInt32OrNull(JSON_VALUE(_raw, '$.qty')) AS qty,
  toFloat64OrNull(JSON_VALUE(_raw, '$.price')) AS price
FROM kafka_mdb_orders;
```

### Verify

```sql
SELECT count() FROM mdb_orders_raw;
SELECT * FROM mdb_orders_raw ORDER BY ts DESC LIMIT 10;
```

---

## 8. Notes & Gotchas

- **IAM auth unsupported** → must use TLS (9094) or SASL/SCRAM listeners.  
- **MongoDB must be replica set** → CDC won’t work on standalone.  
- **Schema handling** → JSON converter avoids Schema Registry, simpler for ClickHouse.  
- **Throughput** → scale `tasks.max`, topic partitions, and connector batch settings.  
- **Idempotency** → consider `ReplacingMergeTree` with a version column if you want current-state tables.  

---

✅ With this pipeline, you can replicate **MongoDB → MSK → ClickHouse** end-to-end using TLS and a self-hosted Kafka Connect worker.
