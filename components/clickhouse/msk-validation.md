# Validating ClickHouse Connectivity to MSK

This guide walks through a **smoke test** to prove your ClickHouse instance on EC2 can connect to Amazon MSK.

---

## 0. Preconditions

- **Listener type**: MSK must expose a **TLS** or **SASL/SCRAM** listener.  
  > ClickHouse **does not support IAM auth** (`AWS_MSK_IAM`) in the Kafka engine.

- **Networking**:  
  - MSK broker SG allows inbound from your EC2 SG on the chosen listener port (9094 TLS, 9096 SASL).  
  - EC2 SG allows outbound to those broker IPs/ports.  
  - VPC/subnet routing works, no NACL blocks.

- **Broker string**:  
  ```bash
  aws kafka get-bootstrap-brokers --cluster-arn <your-msk-arn>
  ```
  Use `BootstrapBrokerStringTls` (for TLS, 9094) or `BootstrapBrokerStringScram` (for SCRAM, 9096).

---

## 1. Validate with a Kafka Client

### Option A — Install `kcat` (static binary, Amazon Linux 2023)
```bash
cd /tmp
curl -LO https://github.com/edenhill/kcat/releases/download/1.7.1/kcat-1.7.1-x86_64-linux.tar.gz
tar xzf kcat-1.7.1-x86_64-linux.tar.gz
sudo mv kcat-1.7.1-x86_64-linux/kcat /usr/local/bin/kcat
sudo chmod +x /usr/local/bin/kcat

kcat -V   # verify install
```

### Option B — Use Apache Kafka console clients
```bash
cd /opt
curl -LO https://archive.apache.org/dist/kafka/3.6.1/kafka_2.13-3.6.1.tgz
tar xzf kafka_2.13-3.6.1.tgz
cd kafka_2.13-3.6.1
```

Create a client properties file:

- For **TLS**:
  ```bash
  echo "security.protocol=SSL" > ~/tls.properties
  ```

- For **SASL/SCRAM**:
  ```bash
  cat > ~/sasl.properties <<'EOF'
  security.protocol=SASL_SSL
  sasl.mechanism=SCRAM-SHA-512
  sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="<scram-user>" password="<scram-pass>";
  EOF
  ```

---

### Produce & Consume (TLS with kcat)
```bash
BOOTSTRAP="b-1....:9094,b-2....:9094,b-3....:9094"
TOPIC="ch_test"

printf '%s\n' '{"id":1,"msg":"hello"}' '{"id":2,"msg":"world"}' '{"id":3,"msg":"msk"}'  | kcat -b "$BOOTSTRAP" -t "$TOPIC" -P -X security.protocol=SSL

kcat -b "$BOOTSTRAP" -t "$TOPIC" -C -o beginning -e -q -X security.protocol=SSL
```

### Produce & Consume (TLS with Kafka console clients)
```bash
bin/kafka-console-producer.sh --bootstrap-server "$BOOTSTRAP"   --topic "$TOPIC" --producer.config ~/tls.properties <<< '{"id":1,"msg":"hello"}'

bin/kafka-console-consumer.sh --bootstrap-server "$BOOTSTRAP"   --topic "$TOPIC" --from-beginning --consumer.config ~/tls.properties   --timeout-ms 10000
```

### Produce & Consume (SASL/SCRAM)
```bash
BOOTSTRAP="b-1....:9096,b-2....:9096,b-3....:9096"
SASL_USER="<scram-username>"
SASL_PASS="<scram-password>"

# kcat
printf '%s\n' '{"id":1,"msg":"hello"}' '{"id":2,"msg":"world"}'  | kcat -b "$BOOTSTRAP" -t "$TOPIC" -P    -X security.protocol=SASL_SSL -X sasl.mechanisms=SCRAM-SHA-512    -X sasl.username="$SASL_USER" -X sasl.password="$SASL_PASS"

kcat -b "$BOOTSTRAP" -t "$TOPIC" -C -o beginning -e -q    -X security.protocol=SASL_SSL -X sasl.mechanisms=SCRAM-SHA-512    -X sasl.username="$SASL_USER" -X sasl.password="$SASL_PASS"

# or console clients
bin/kafka-console-producer.sh --bootstrap-server "$BOOTSTRAP"   --topic "$TOPIC" --producer.config ~/sasl.properties <<< '{"id":1,"msg":"scram"}'

bin/kafka-console-consumer.sh --bootstrap-server "$BOOTSTRAP"   --topic "$TOPIC" --from-beginning --consumer.config ~/sasl.properties   --timeout-ms 10000
```

If you can produce and consume, networking + authentication are confirmed.

---

## 2. Wire ClickHouse to MSK

### Kafka Table (TLS only)
```sql
CREATE TABLE kafka_src
(
  id  UInt64,
  msg String
)
ENGINE = Kafka
SETTINGS
  kafka_broker_list = 'b-1....:9094,b-2....:9094,b-3....:9094',
  kafka_topic_list  = 'ch_test',
  kafka_group_name  = 'ch_consumer_1',
  kafka_format      = 'JSONEachRow',
  kafka_num_consumers = 1,
  kafka_security_protocol = 'SSL';
```

### Kafka Table (SASL/SCRAM)
```sql
CREATE TABLE kafka_src
(
  id  UInt64,
  msg String
)
ENGINE = Kafka
SETTINGS
  kafka_broker_list = 'b-1....:9096,b-2....:9096,b-3....:9096',
  kafka_topic_list  = 'ch_test',
  kafka_group_name  = 'ch_consumer_1',
  kafka_format      = 'JSONEachRow',
  kafka_num_consumers = 1,
  kafka_security_protocol = 'SASL_SSL',
  kafka_sasl_mechanism = 'SCRAM-SHA-512',
  kafka_sasl_username = '<scram-username>',
  kafka_sasl_password = '<scram-password>';
```

---

## 3. Ingest into MergeTree

```sql
CREATE TABLE events
(
  id  UInt64,
  msg String,
  _ingested_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY id;

CREATE MATERIALIZED VIEW mv_kafka_to_events
TO events
AS
SELECT id, msg
FROM kafka_src;
```

Produce more messages, then query:
```sql
SELECT count() FROM events;
SELECT * FROM events ORDER BY id LIMIT 10;
```

---

## 4. Quick One-Off Validation
```sql
SET stream_like_engine_allow_direct_select = 1;
SELECT * FROM kafka_src LIMIT 5;
```

---

## 5. Common Gotchas

- **IAM auth unsupported** → use TLS or SCRAM listeners.  
- **Topic auto-create disabled** → create topics manually.  
- **Consumer stuck** → try a fresh `kafka_group_name`.  
- **JSON schema mismatch** → enable `input_format_defaults_for_omitted_fields=1` or fix column types.  
- **Cert issues** → set `kafka_ssl_ca_cert` if needed.  
- **DNS issues** → ensure your EC2 can resolve MSK broker hostnames (VPC DNS enabled).  

---

✅ With this, you can confirm **ClickHouse ↔ MSK connectivity works end to end.**
