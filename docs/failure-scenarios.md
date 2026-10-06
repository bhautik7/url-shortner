# Failure Scenarios and Fault Tolerance Analysis

This document details 10 critical failure modes in the URL Shortener architecture, documenting the problem, impact, current system behavior, and enterprise production improvements.

---

## 1. Redis Cache Goes Down

- **Problem:** Redis master/replica becomes unresponsive or crashes due to network partition or OOM.
- **Impact:** Read operations experience a cache miss for all requests. Write operations cannot access the global counter or rate limiter.
- **Current Behavior:**
  - **Read Path:** `CacheService` catches `RedisError` / timeouts gracefully, logs a warning, and falls back directly to PostgreSQL without failing client redirects. Redirects succeed with slightly higher latency ($5\text{–}15\text{ms}$ vs $<1\text{ms}$).
  - **Write Path:** Fails with `503 Service Unavailable` (`DEPENDENCY_UNAVAILABLE`), preventing uncoordinated ID generation. Rate limiter fails open to preserve write flow if DB is still reachable.
- **Production Improvement:**
  - Deploy Redis Sentinel or Redis Cluster with Multi-AZ replication and automated failover.
  - Implement circuit breakers (e.g. pybreaker) to stop hammering Redis during sustained outages.

---

## 2. PostgreSQL Goes Down

- **Problem:** Primary database crashes or exhausts its connection pool.
- **Impact:** All write operations fail. Read operations for cached short codes continue working; cache misses fail.
- **Current Behavior:**
  - **Read Path (Cache Hit):** Client redirect succeeds with 302 Found directly from Redis without touching PostgreSQL.
  - **Read Path (Cache Miss):** Returns `500 Internal Server Error` with standardized JSON error payload.
  - **Write Path:** Returns `500 Internal Server Error` or `503 Service Unavailable` after transaction rollback.
- **Production Improvement:**
  - Deploy PostgreSQL Multi-AZ High Availability with automated failover (e.g. AWS Aurora PostgreSQL or Patroni).
  - Use read replicas for cache-miss read queries with PgBouncer connection pooling.

---

## 3. Write Service Goes Down

- **Problem:** All Write Service containers crash or are killed by OOM.
- **Impact:** New short URLs and custom aliases cannot be created (`POST /api/v1/urls`).
- **Current Behavior:**
  - Nginx returns `502 Bad Gateway` for `POST /api/v1/urls`.
  - Read Service and redirects continue operating at 100% availability because the services are strictly decoupled.
- **Production Improvement:**
  - Kubernetes Horizontal Pod Autoscaler (HPA) with multi-replica deployments spread across availability zones.
  - Graceful rolling updates and health probe restarts.

---

## 4. Read Service Goes Down

- **Problem:** Read Service instances crash or encounter memory exhaustion.
- **Impact:** Redirection requests (`GET /{short_code}`) fail.
- **Current Behavior:**
  - Nginx returns `502 Bad Gateway` for redirect requests.
  - Write Service remains fully operational.
- **Production Improvement:**
  - Run high-density Read Service replicas (e.g. 10–50 pods).
  - Edge redirection using Cloudflare Workers or AWS CloudFront Lambda@Edge with KV cache.

---

## 5. Nginx (API Gateway) Goes Down

- **Problem:** Nginx reverse proxy crashes or server host loses network connectivity.
- **Impact:** Entire system is unreachable from external clients.
- **Current Behavior:**
  - Client receives connection refused or timeout.
- **Production Improvement:**
  - Cloud Load Balancers (AWS ALB, GCP Cloud Load Balancing) with multi-region DNS routing (AWS Route 53 latency-based routing).
  - High-availability redundant gateway clusters with Keepalived / VRRP.

---

## 6. Redis Counter Goes Down

- **Problem:** Redis node hosting the global atomic counter crashes or experiences high network latency.
- **Impact:** Write Service instances cannot lease new ID batches.
- **Current Behavior:**
  - As long as a Write Service instance has remaining IDs in its local in-memory batch, it continues generating short codes with zero disruption.
  - Once the local batch runs out and Redis is still unreachable, the service raises `DependencyUnavailableError` and returns `503 Service Unavailable`.
- **Production Improvement:**
  - Dedicated Redis cluster exclusively for counter leasing, separated from volatile caching.
  - Fallback to Snowflake-style 64-bit ID generation (Timestamp + Worker ID + Sequence) or PostgreSQL sequences if Redis is offline.

---

## 7. Duplicate Short Code Somehow Occurs

- **Problem:** A custom alias matches an existing short code, or counter state was manually tampered with.
- **Impact:** Potential URL collision and data corruption if not handled.
- **Current Behavior:**
  - PostgreSQL enforces a hard `UNIQUE(short_code)` constraint at the database storage engine level.
  - The repository catches SQLAlchemy `IntegrityError`, immediately calls `session.rollback()`, and returns `409 Conflict` (`ALIAS_ALREADY_EXISTS`) to the client.
- **Production Improvement:**
  - Idempotency keys on URL creation requests (`X-Idempotency-Key`) to prevent duplicate writes on client retries.

---

## 8. Request Times Out After URL Creation

- **Problem:** URL is successfully written to PostgreSQL and committed, but network drops before HTTP 201 response reaches the client.
- **Impact:** Client thinks the creation failed and retries.
- **Current Behavior:**
  - If a custom alias was specified, the retry receives `409 Conflict` because the alias is now in DB.
  - If auto-generated, retry generates a new short code for the same URL.
- **Production Improvement:**
  - Support client-provided idempotency keys cached in Redis for 24 hours.
  - If identical idempotency key is received, return the previously created short URL.

---

## 9. URL Expires While Cached

- **Problem:** A URL with a 1-hour expiration is cached in Redis.
- **Impact:** Risk of serving redirects to expired destinations.
- **Current Behavior:**
  - **Intelligent TTL Alignment:** `CacheService.compute_ttl()` computes remaining seconds until expiration and sets the Redis key TTL $\le \text{remaining\_time}$. Redis automatically purges the key at expiration.
  - **Defense-in-Depth Validation:** The cached payload contains `"expires_at"`. On cache hit, `RedirectService` double-checks the timestamp against current UTC time. If expired, it raises `410 Gone` and does not redirect.
- **Production Improvement:**
  - Background cleanup cron job (`cleanup_expired_urls.py`) sweeps PostgreSQL and invalidates Redis keys to maintain storage hygiene.

---

## 10. Multiple Write Service Instances Request IDs Simultaneously

- **Problem:** 20 Write Service instances exhaust their local batches simultaneously and request new batches from Redis.
- **Impact:** Potential race conditions or duplicate ID ranges.
- **Current Behavior:**
  - Redis executes commands on a single-threaded event loop. `INCRBY` is strictly atomic:
    - Instance 1 receives `[1001, 2000]`
    - Instance 2 receives `[2001, 3000]`
    - Instance 3 receives `[3001, 4000]`
  - Each instance uses an internal `asyncio.Lock()` to synchronize ID dispensing across concurrent async coroutines within its process.
  - Zero duplicate IDs and zero race conditions.
- **Production Improvement:**
  - Dynamic batch sizing based on current write throughput (e.g. larger batches during flash sales).
