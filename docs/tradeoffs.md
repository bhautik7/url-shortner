# System Design Trade-Off Analysis

This document explores the architectural decisions, trade-offs, and design rationales made in this production-grade URL Shortener.

---

## 1. Short-Code Generation: Hash vs. Atomic Counter

### Option A: Cryptographic / Non-Cryptographic Hashing (MD5, SHA-256, Murmur3)

**Mechanism:** Compute `hash(long_url)` and take the first 6–7 characters encoded in Base62.

- **Advantages:**
  - **Decentralized:** Any stateless worker can compute the hash locally without coordinating with a central counter or database.
  - **Natural Deduplication:** The same `long_url` hashed by different workers produces the identical hash.
- **Disadvantages:**
  - **Hash Collisions:** 7 Base62 characters offer $62^7 \approx 3.52 \times 10^{12}$ combinations. By the Birthday Paradox, collisions begin occurring after $\sqrt{3.52 \times 10^{12}} \approx 1.87 \times 10^6$ items (around 2 million URLs).
  - **Collision Resolution Overhead:** When a collision occurs in the DB, the service must append a salt/counter and re-hash (e.g., `hash(long_url + salt)`), necessitating repetitive DB read-before-write queries and degrading write throughput.
  - **Non-compact Codes:** To avoid collisions, hash lengths must be artificially increased to 8–10+ characters.

---

### Option B: Atomic Monotonic Counter + Base62 (Chosen Strategy)

**Mechanism:** Lease integer IDs from a centralized atomic counter (Redis `INCRBY`) and bijectively convert the integer to Base62.

- **Advantages:**
  - **Zero Collisions:** Integers are strictly unique. Base62 conversion is a bijective (one-to-one) mapping, mathematically guaranteeing zero collisions.
  - **Optimal Code Compactness:** Codes start as short as possible and grow monotonically:
    - Base62 4-char: $62^4 = 14,776,336$ IDs.
    - Base62 6-char: $62^6 = 56,800,235,584$ (56.8 Billion) IDs.
    - Base62 7-char: $62^7 = 3.52$ Trillion IDs.
  - **High Performance via Batching:** Instances lease batches of 1,000+ IDs in a single Redis `INCRBY` call and allocate them from local memory in $O(1)$ time with sub-microsecond latency.
- **Disadvantages:**
  - **Centralized Dependency:** Requires a high-availability counter store (Redis / Database sequence / ZooKeeper / Snowflake).
  - **Predictability / Scraping:** Sequential Base62 codes can be sequentially crawled if no obfuscation (e.g., Feistel cipher or bit-reversal) is applied.
  - **Gaps on Instance Crash:** If a service instance restarts with unallocated IDs in its leased batch, those integers are skipped. (This is completely benign given the $56.8\text{B}+$ capacity).

---

## 2. Redis Caching & Cache-Aside Pattern

### Advantages:
1. **Sub-Millisecond Redirect Latency:** Redis in-memory lookups take $< 1\text{ms}$, compared to $5\text{–}15\text{ms}$ for disk-backed database queries.
2. **Massive Database Offloading:** In a 1000:1 read-to-write ratio, Redis absorbs over 99.9% of all incoming read traffic, protecting PostgreSQL from connection exhaustion and disk I/O bottlenecks.
3. **Intelligent Expiration Alignment:** Cache TTL is computed dynamically: if a URL expires in 15 minutes, its Redis TTL is capped at 15 minutes, preventing stale redirects.

### Disadvantages:
1. **Memory Cost:** Storing billions of keys in RAM is significantly more expensive than SSD storage. (Mitigated by setting a 24-hour default TTL and LRU eviction policy).
2. **Cache Invalidation Complexity:** When a URL expires or is modified, cache entries must be evicted or updated consistently.
3. **Infrastructure Overhead:** Requires managing Redis replication, clustering, and persistence (AOF/RDB).

---

## 3. Read / Write Service Separation

### Why Separate?
URL shorteners exhibit extreme read-heavy skew ($\approx 1000:1$ reads to writes).

```
         Read Service (99.9% Traffic)              Write Service (0.1% Traffic)
         ─────────────────────────────              ────────────────────────────
Workload: High-concurrency I/O, Cache lookups       Atomic ID leasing, DB transactions
Scaling:  Horizontal auto-scaling (e.g. 50 pods)    Modest scale (e.g. 2–4 pods)
Resource: Optimized for low latency & memory        Optimized for transactional consistency
```

### Key Benefits:
- **Independent Auto-scaling:** The Read Service can scale up rapidly during traffic spikes without provisioning unnecessary Write Service instances.
- **Fault Isolation:** A massive influx of URL creation requests or a slow database write pool will never block or starve the redirect event loops.
- **Tailored Resilience:** The Read Service gracefully falls back to PostgreSQL when Redis is degraded, whereas the Write Service enforces strict dependency checks for counter integrity.

---

## 4. PostgreSQL vs. NoSQL

### Why PostgreSQL is Ideal for this Architecture:
1. **Access Pattern Simplicity:** The query pattern is almost exclusively point lookups:
   `SELECT long_url, expires_at FROM urls WHERE short_code = :code;`
   A B-Tree unique index on `short_code` resolves this in $O(\log N)$ disk seek time.
2. **ACID Uniqueness Protection:** Relational unique constraints on `short_code` and `custom_alias` provide an ironclad guarantee against duplicate collisions under concurrent writes.
3. **Redis Absorbs Read Pressure:** Because Redis serves $>99.9\%$ of redirects, PostgreSQL handles only a fraction of reads (cache misses) plus write traffic.

### When to Transition to NoSQL (e.g., Cassandra, ScyllaDB, DynamoDB):
- **Scale:** When dataset exceeds $10\text{–}50\text{TB}$ ($100\text{B}+$ records) and exceeds single-node SSD capacity.
- **Multi-Region Active-Active Writes:** When writes must be accepted across global data centers with low latency and eventual consistency.
