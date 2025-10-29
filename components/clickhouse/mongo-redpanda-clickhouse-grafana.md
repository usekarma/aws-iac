# PoC with Redpanda, MongoDB, ClickHouse, Grafana

This guide sets up a PoC with **Kafka Connect** (MongoDB CDC), **Kafka Streams** (normalization), and **ClickHouse** (ingestion + Grafana dashboards).

---

## 1) Minimal multi-EC2 layout (PoC)

- **Redpanda (Kafka API)** — 1 node now (upgrade to 3 later)  
  `c6i.large`, gp3 200–300 GB, open **9092** (PLAINTEXT, VPC only) + **9644**
- **MongoDB (single RS)** — `r6i.large`, gp3 200–300 GB, port **27017**
- **ClickHouse + Grafana** — `r6i.xlarge`, gp3 500 GB+, **8123/9000**, Grafana **3000**
- **Kafka Connect + Streams** — `t3.large` (4 vCPU better), no public ports; egress to Redpanda & Mongo

---

## 2) Topic plan

```text
mongo.cdc.appdb.orders     # raw CDC from Mongo Source Connector (JSON)
mongo.cdc.appdb.customers  # (optional) another CDC stream
ch_ingest_normalized       # Kafka Streams output (unified schema, JSON)
connect-configs / offsets / status  # internal Connect topics
dlq.mongo.cdc              # dead-letter for CDC errors
```

---

## 3) Kafka Connect (distributed worker)

### 3.1 Worker properties (`/opt/connect/connect-distributed.properties`)
```properties
bootstrap.servers=<rp-ip>:9092
group.id=connect-cluster
config.storage.topic=connect-configs
offset.storage.topic=connect-offsets
status.storage.topic=connect-status
config.storage.replication.factor=1
offset.storage.replication.factor=1
status.storage.replication.factor=1
key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=false
value.converter.schemas.enable=false
rest.port=8083
plugin.path=/opt/connect/plugins
```

### 3.2 MongoDB Source Connector (`mongo-cdc.json`)
```json
{
  "name": "mongo-cdc-orders",
  "config": {
    "connector.class": "com.mongodb.kafka.connect.MongoSourceConnector",
    "tasks.max": "2",
    "connection.uri": "mongodb://<user>:<pass>@<mongo-ip>:27017/?replicaSet=rs0&authSource=admin",
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

Deploy:
```bash
curl -s -X POST http://localhost:8083/connectors \
  -H 'Content-Type: application/json' -d @mongo-cdc.json | jq
```

---

## 4) Kafka Streams app (normalization to a single topic)

### 4.1 Unified schema
```json
{
  "event_time": "2025-01-01T00:00:00Z",
  "source": "mongo.orders",
  "entity_id": "5f...id...",
  "op": "c|u|d",
  "payload": {
    "sku": "ABC123",
    "qty": 2,
    "price": 9.99
  }
}
```

### 4.2 Minimal Java app

**`build.gradle`**
```groovy
plugins { id 'java' }
repositories { mavenCentral() }
dependencies {
  implementation 'org.apache.kafka:kafka-streams:3.6.1'
  implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.1'
  implementation 'com.fasterxml.jackson.core:jackson-core:2.17.1'
  implementation 'com.fasterxml.jackson.core:jackson-annotations:2.17.1'
}
tasks.withType(JavaCompile) { options.release = 17 }
```

**`src/main/java/poc/NormalizeApp.java`**
```java
package poc;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.*;
import org.apache.kafka.streams.kstream.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;

public class NormalizeApp {
  static final ObjectMapper M = new ObjectMapper();

  public static void main(String[] args) {
    var props = new java.util.Properties();
    props.put(StreamsConfig.APPLICATION_ID_CONFIG, "kstreams-normalizer-01");
    props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, System.getenv().getOrDefault("BOOTSTRAP", "<rp-ip>:9092"));
    props.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, StreamsConfig.EXACTLY_ONCE_V2);
    props.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, "2");

    var builder = new StreamsBuilder();

    var orders = builder.stream("mongo.cdc.appdb.orders",
        Consumed.with(Serdes.String(), Serdes.String()));

    KStream<String,String> normalized = orders.mapValues(v -> {
      try {
        var src = (ObjectNode) M.readTree(v);
        var env = M.createObjectNode();
        env.put("event_time", Instant.now().toString());
        env.put("source", "mongo.orders");
        var full = src.has("fullDocument") ? src.get("fullDocument") : src;
        env.put("entity_id", full.has("_id") ? full.get("_id").asText() : "");
        env.put("op", src.has("operationType") ? src.get("operationType").asText().substring(0,1) : "u");

        var payload = M.createObjectNode();
        payload.put("sku", full.has("sku") ? full.get("sku").asText() : null);
        payload.put("qty", full.has("qty") ? full.get("qty").asInt() : 0);
        payload.put("price", full.has("price") ? full.get("price").asDouble() : 0.0);
        env.set("payload", payload);
        return M.writeValueAsString(env);
      } catch (Exception e) {
        return "{\"op\":\"e\"}";
      }
    });

    normalized.to("ch_ingest_normalized", Produced.with(Serdes.String(), Serdes.String()));
    var topology = builder.build();
    KafkaStreams app = new KafkaStreams(topology, props);
    app.start();
    Runtime.getRuntime().addShutdownHook(new Thread(app::close));
  }
}
```

---

## 5) ClickHouse DDL (reads the unified topic)

```sql
CREATE TABLE kafka_src_norm
(
  line String
)
ENGINE = Kafka
SETTINGS
  kafka_broker_list = '<rp-ip>:9092',
  kafka_topic_list  = 'ch_ingest_normalized',
  kafka_group_name  = 'ch_norm_consumer_1',
  kafka_format      = 'JSONEachRow',
  kafka_num_consumers = 1;

CREATE TABLE events
(
  event_time    DateTime,
  source        String,
  entity_id     String,
  op            LowCardinality(String),
  sku           LowCardinality(String),
  qty           Int32,
  price         Float64,
  _ingested_at  DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (event_time, entity_id);

CREATE MATERIALIZED VIEW mv_norm_to_events
TO events AS
SELECT
  parseDateTimeBestEffortOrNull(JSON_VALUE(line, '$.event_time')) AS event_time,
  JSON_VALUE(line, '$.source') AS source,
  JSON_VALUE(line, '$.entity_id') AS entity_id,
  JSON_VALUE(line, '$.op') AS op,
  JSON_VALUE(line, '$.payload.sku') AS sku,
  toInt32OrNull(JSON_VALUE(line, '$.payload.qty')) AS qty,
  toFloat64OrNull(JSON_VALUE(line, '$.payload.price')) AS price
FROM kafka_src_norm;
```

---

## 6) Validation flow

1. Insert/update a doc in MongoDB → appears on `mongo.cdc.appdb.orders`
2. Streams app picks it up → writes to `ch_ingest_normalized`
3. ClickHouse MV → ingests into `events`
4. Grafana → queries ClickHouse (`SELECT count() FROM events`)

---

## 7) Gotchas

- Keep topics RF=1 for single-node Redpanda
- Schema changes: ClickHouse can default nulls, or adjust MV logic
- PLAINTEXT is fine for VPC-only PoC; switch to TLS/SASL for real environments

---
