# System Design Interview Guide: Scalable URL Shortener

This guide provides a structured, interview-ready walkthrough for designing a URL Shortener (like Bitly / TinyURL) from fundamental requirements to massive global scale.

---

## 1. Functional Requirements

1. **Shorten URL:** Users provide a long URL (e.g. `https://example.com/very/long/path`) and receive a compact short URL (e.g. `http://short.ly/4C92x`).
2. **Redirection:** Visiting `GET /{short_code}` redirects the user with HTTP 302 to the original destination.
3. **Custom Aliases:** Users can optionally specify a custom alias (e.g. `http://short.ly/my-sale`).
4. **Link Expiration:** Users can optionally specify an expiration timestamp. Expired links return HTTP 410 Gone.

---

## 2. Non-Functional Requirements & Capacity Estimation

- **Read-Heavy Skew:** $\approx 1000:1$ read-to-write ratio.
- **Traffic Estimations:**
  - New URLs created: $100\text{M URLs/month} \approx 40\text{ writes/sec}$ (peak $200\text{ writes/sec}$).
  - URL Redirects: $100\text{B redirects/month} \approx 40,000\text{ reads/sec}$ (peak $100,000\text{ reads/sec}$).
- **Storage Calculations (5 years):**
  - $100\text{M} \times 12 \times 5 = 6\text{ Billion records}$.
  - Avg URL size: $500\text{ bytes} \implies 6\text{B} \times 500\text{B} \approx 3\text{ TB}$ total database storage.
- **Cache Memory (80/20 Rule):**
  - Top 20% of hot URLs generate 80% of read traffic.
  - Daily active URLs: $40\text{K reads/sec} \times 86,400\text{s} \times 0.2 \approx 700\text{M reads/day}$.
  - Unique hot URLs to cache: $\approx 20\text{M URLs} \times 500\text{B} \approx 10\text{ GB RAM}$ (very manageable in Redis).
- **Latency SLAs:** Redirection latency $< 10\text{ms}$ (p99 $< 20\text{ms}$), creation latency $< 50\text{ms}$.
- **Availability:** 99.99% uptime.

---

## 3. API Design

### `POST /api/v1/urls` (Write Service)
```json
// Request
{
  "long_url": "https://example.com/products/deals",
  "custom_alias": "spring-deal", // Optional
  "expiration_date": "2026-12-31T23:59:59Z" // Optional
}

// Response (HTTP 201 Created)
{
  "short_code": "spring-deal",
  "short_url": "http://localhost/spring-deal",
  "long_url": "https://example.com/products/deals",
  "expiration_date": "2026-12-31T23:59:59Z"
}
```

### `GET /{short_code}` (Read Service)
- **Response:** HTTP 302 Found (`Location: https://example.com/...`)
- **Expired:** HTTP 410 Gone
- **Not Found:** HTTP 404 Not Found

---

## 4. Data Model

### Relational Table: `urls`
```sql
CREATE TABLE urls (
    id            BIGSERIAL PRIMARY KEY,
    short_code    VARCHAR(30) NOT NULL,
    long_url      TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ,
    custom_alias  VARCHAR(30),
    created_by    VARCHAR(255)
);

CREATE UNIQUE INDEX ix_urls_short_code ON urls (short_code);
CREATE INDEX ix_urls_expires_at ON urls (expires_at);
```

---

## 5. High-Level Architecture

```
                      ┌───────────────┐
                      │    Client     │
                      └───────┬───────┘
                              │
                              ▼
                      ┌───────────────┐
                      │ Nginx Gateway │
                      └───┬───────┬───┘
          POST /urls      │       │      GET /{short_code}
      ┌───────────────────┘       └──────────────────┐
      ▼                                              ▼
┌───────────────┐                             ┌───────────────┐
│ Write Service │                             │ Read Service  │
└───┬───────┬───┘                             └───┬───────┬───┘
    │       │                                     │       │
    │   Lease ID Range                            │       │
    │       │                               Cache HIT     │
    │       ▼                                     │       ▼
    │   ┌───────┐                                 │   ┌───────┐
    │   │ Redis │◄────────────────────────────────┴───┤ Redis │
    │   │Counter│         Cache MISS & Populate       │ Cache │
    │   └───────┘                                     └───────┘
    │                                                     │
    └─────────────────────┬───────────────────────────────┘
                          ▼
                 ┌─────────────────┐
                 │ PostgreSQL (DB) │
                 └─────────────────┘
```

---

## 6. Short-Code Generation & Counter Batching

1. **Centralized Redis Counter:** Redis `INCRBY url_shortener:global_counter 1000` atomically leases a contiguous integer block `[start, end]`.
2. **In-Memory Dispensing:** The Write Service dispenses IDs locally without network roundtrips.
3. **Base62 Encoding:** Converts monotonic integers to alphanumeric strings using alphabet `0-9a-zA-Z`.
   - $1,000,001 \implies \text{"4C92x"}$
   - $56.8\text{ Billion}$ combinations with just 6 characters ($62^6$).

---

## 7. Database Indexing Strategy

- **B-Tree on `short_code` (Unique):** Guarantees $O(\log N)$ point lookups on cache misses and prevents race conditions on custom alias collisions.
- **Index on `expires_at`:** Accelerates background garbage collection queries (`WHERE expires_at <= NOW()`) without full table scans.

---

## 8. Redis Caching & Intelligent TTL

- **Cache-Aside Pattern:**
  1. Check Redis for `url:{short_code}`.
  2. If Hit: Validate expiration; return 302 redirect.
  3. If Miss: Query PostgreSQL; populate Redis with dynamic TTL; return 302 redirect.
- **Intelligent TTL Formula:**
  $$\text{TTL} = \min(\text{Remaining Lifetime}, \text{DEFAULT\_TTL})$$
  Ensures Redis keys expire concurrently with or before the URL's true expiration.

---

## 9. Horizontal Scaling & Microservice Separation

- **Decoupled Read & Write Services:** Allows Read Service to scale horizontally to 50+ pods while Write Service remains lean at 2–3 pods.
- **Stateless Application Tier:** All state is held in Redis or PostgreSQL, allowing seamless rolling deployments and load balancing across instances.

---

## 10. Failure Handling & Resilience

- **Redis Cache Outage:** Read Service seamlessly falls back to PostgreSQL queries, preserving 100% redirect availability.
- **Database Unique Constraint Enforcement:** PostgreSQL acts as the definitive source of truth, guaranteeing uniqueness even if concurrent services allocate conflicting custom aliases.

---

## 11. Scaling Roadmap

### What would I improve at 10x Traffic (~10,000 writes/sec, ~1M reads/sec)?

1. **Redis Cluster with Read Replicas:** Deploy Redis Cluster with multi-replica read distribution across availability zones.
2. **Database Read Replicas & PgBouncer:** Implement PostgreSQL primary-replica topology with PgBouncer connection pooling for cache-miss read offloading.
3. **Local In-Memory L1 Cache (e.g., Cachetools / Ristretto):** Add a 5-second in-memory LRU cache in each Read Service pod for ultra-hot viral links, preventing Redis hotkey saturation.
4. **Bloom Filters:** Place a Redis Bloom Filter in front of the database to immediately reject non-existent short codes without hitting PostgreSQL on cache misses.

---

### What would I improve at 100x Traffic (~100,000 writes/sec, ~10M reads/sec)?

1. **Edge Redirection via Global CDN / Anycast:** Move redirect logic to Cloudflare Workers or AWS CloudFront Lambda@Edge with edge KV storage (e.g. Cloudflare KV or DynamoDB Global Tables). 99.9% of redirects never touch the origin data center.
2. **Distributed ID Generator (Snowflake / Epoch Sequences):** Replace Redis atomic counter with a decentralized 64-bit Snowflake ID generation algorithm across nodes to eliminate centralized counter lock contention.
3. **NoSQL Distributed Storage (ScyllaDB / Cassandra / DynamoDB):** Partition URLs by `short_code` hash across a multi-region distributed wide-column database for linear write scaling and petabyte storage capacity.
4. **Asynchronous Kafka Event Pipeline:** Decouple click analytics and access logging into Kafka/ClickHouse for real-time analytics aggregation without impacting redirect latency.
