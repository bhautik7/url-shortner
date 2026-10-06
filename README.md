# Production-Grade Scalable URL Shortener

A high-performance, distributed URL Shortener application designed for extreme read-heavy workloads ($\approx 1000:1$ read/write ratio), sub-millisecond redirect latency, and fault-tolerant horizontal scalability.

---

## 📖 System Architecture & Overview

The system decouples read and write concerns into independently scalable microservices, shielded by an Nginx API Gateway, utilizing Redis for both in-memory cache-aside redirection and atomic batch counter leasing, with PostgreSQL as the persistent source of truth.

```
                               ┌───────────────────────────┐
                               │       Client / Browser    │
                               └─────────────┬─────────────┘
                                             │ HTTP
                                             ▼
                               ┌───────────────────────────┐
                               │    Nginx API Gateway      │
                               │        (Port 80)          │
                               └───┬───────────────────┬───┘
               POST /api/v1/urls   │                   │   GET /{short_code}
                                   ▼                   ▼
                     ┌───────────────────┐       ┌───────────────────┐
                     │   Write Service   │       │   Read Service    │
                     │  (Port 8001/80)   │       │  (Port 8002/80)   │
                     └───┬───────────┬───┘       └───┬───────────┬───┘
                         │           │               │           │
           Lease Range   │           │               │ Cache HIT │ Cache MISS
         (INCRBY batch)  │           │               ▼           │
                         │           │       ┌───────────────┐   │
                         │           └──────►│  Redis Cache  │◄──┘ (Populate)
                         │                   └───────────────┘
                         ▼                           │
                 ┌───────────────┐                   │
                 │ Redis Counter │                   │
                 └───────────────┘                   │
                         │                           ▼
                         └──────────────────►┌───────────────┐
                                             │  PostgreSQL   │
                                             │ (Primary DB)  │
                                             └───────────────┘
```

---

## ⚡ Data Flow Pipelines

### 1. Write Flow (URL Creation & Short Code Allocation)

```
Client
  │
  │  POST /api/v1/urls {"long_url": "https://...", "custom_alias": "..."}
  ▼
Nginx Gateway
  │
  ▼
Write Service (FastAPI)
  │
  ├─► [1] Rate Limiter (Redis fixed window per client IP)
  │
  ├─► [2] Custom Alias Check?
  │        ├─► YES: Validate format & check collision in PostgreSQL
  │        └─► NO:  Get next ID from in-memory leased batch
  │                 (If batch exhausted, lease next 1000 IDs via Redis INCRBY)
  │
  ├─► [3] Base62 Encoder (Deterministic integer -> alphanumeric Base62)
  │
  ├─► [4] PostgreSQL INSERT (Enforces UNIQUE constraint & rolls back on conflict)
  │
  ▼
HTTP 201 Created {"short_code": "4C92x", "short_url": "http://localhost/4C92x"}
```

---

### 2. Read Flow (High-Speed Redirect & Cache-Aside)

```
Client
  │
  │  GET /4C92x
  ▼
Nginx Gateway
  │
  ▼
Read Service (FastAPI)
  │
  ▼
Redis Cache (Cache-Aside lookup: key="url:4C92x")
  │
  ├───► [CACHE HIT] ──► Validate expiration ──► Return HTTP 302 Found (Sub-millisecond)
  │
  └───► [CACHE MISS / Redis Unavailable]
           │
           ▼
        PostgreSQL (B-Tree index lookup: WHERE short_code = '4C92x')
           │
           ├───► [NOT FOUND] ───────────────► Return HTTP 404 Not Found
           ├───► [EXPIRED (now >= expires)] ─► Return HTTP 410 Gone
           └───► [ACTIVE URL]
                    │
                    ├─► Compute intelligent TTL (min(remaining_seconds, max_ttl))
                    ├─► Asynchronously populate Redis cache
                    └─► Return HTTP 302 Found
```

---

## 🔬 Core Engineering Decisions Explained

### 1. Why Redis for Caching & Counters?
- **Caching:** Redis stores frequently accessed mappings in RAM, offloading 99.9% of read traffic from disk-backed PostgreSQL and ensuring sub-millisecond response times.
- **Atomic Counter:** Redis single-threaded execution guarantees atomic `INCRBY` operations without distributed database row locks or race conditions.

### 2. Cache-Aside Pattern
- The application code manages the cache directly. On reads, the cache is consulted first; on a miss, the database is queried, and the result is backfilled into Redis with an intelligent TTL.

### 3. Database Indexing
- `short_code` (Unique B-Tree): Enables $O(\log N)$ point lookups on cache misses and prevents race conditions on duplicate custom aliases.
- `expires_at` (B-Tree): Optimizes garbage collection queries (`WHERE expires_at <= NOW()`) for background workers without table scans.

### 4. Base62 Encoding
- Positional numeral system using characters `[0-9a-zA-Z]`.
- Bijective and collision-free: every integer maps to exactly one alphanumeric code.
- 6 characters provide $62^6 \approx 56.8\text{ Billion}$ unique short codes.

### 5. Why HTTP 302 Found instead of 301 Moved Permanently?
- **HTTP 301:** Permanently cached by client browsers. Expired links or updated targets cannot be revoked, and click tracking metrics are bypassed.
- **HTTP 302:** Directs browsers to follow the redirect without storing an immutable local cache, ensuring link expiration enforcement and real-time observability.

### 6. Counter Batching
- Each Write Service instance leases a block of 1,000 IDs at a time via `INCRBY`.
- Dispenses numbers locally under an async lock in $O(1)$ time, eliminating 99.9% of Redis round-trips during writes.

### 7. Read / Write Separation
- Extreme traffic skew ($\approx 1000:1$) allows the Read Service to scale horizontally to 50+ pods, while the Write Service remains lean at 2–3 pods. Failure in write paths does not impact redirection uptime.

---

## 🚀 Quick Start (Docker Compose)

The entire system runs out-of-the-box with Docker and Docker Compose.

```bash
# 1. Clone repository and start Docker Compose
git clone <repo-url>
cd quick-babbage

# 2. Build and start all services in background
make up

# 3. View logs across all services
make logs
```

Verify services are healthy:
```bash
curl -i http://localhost/health
curl -i http://localhost/ready
```

---

## 🛠️ API Usage Examples

### 1. Create Short URL (Auto-Generated Base62)
```bash
curl -X POST http://localhost/api/v1/urls \
  -H "Content-Type: application/json" \
  -d '{
    "long_url": "https://fastapi.tiangolo.com/tutorial/"
  }'
```
**Response (HTTP 201 Created):**
```json
{
  "short_code": "4C92x",
  "short_url": "http://localhost/4C92x",
  "long_url": "https://fastapi.tiangolo.com/tutorial/",
  "expiration_date": null
}
```

### 2. Create Short URL with Custom Alias & Expiration
```bash
curl -X POST http://localhost/api/v1/urls \
  -H "Content-Type: application/json" \
  -d '{
    "long_url": "https://github.com/fastapi/fastapi",
    "custom_alias": "fastapi-docs",
    "expiration_date": "2026-12-31T23:59:59Z"
  }'
```

### 3. Test Redirection (HTTP 302)
```bash
curl -i http://localhost/4C92x
```
**Response Header:**
```http
HTTP/1.1 302 Found
Location: https://fastapi.tiangolo.com/tutorial/
X-Request-ID: c5a9a832-6a68-450f-a39c-36ecfb6a86fe
```

### 4. Duplicate Custom Alias Error (HTTP 409)
```bash
curl -X POST http://localhost/api/v1/urls \
  -H "Content-Type: application/json" \
  -d '{
    "long_url": "https://example.com/another",
    "custom_alias": "fastapi-docs"
  }'
```
**Response (HTTP 409 Conflict):**
```json
{
  "error": {
    "code": "ALIAS_ALREADY_EXISTS",
    "message": "The requested alias is already in use."
  }
}
```

---

## 🧪 Testing

```bash
# Run all unit and integration tests
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration
```

---

## 📊 Load Testing

Run Locust headless benchmark:
```bash
make load-test
```
Or launch Locust web dashboard at `http://localhost:8089`:
```bash
locust -f load_testing/locustfile.py --host http://localhost
```

---

## 📂 Project Structure

```
.
├── services/
│   ├── write_service/
│   │   ├── app/
│   │   │   ├── api/          # Route handlers (POST /api/v1/urls, /health, /ready)
│   │   │   ├── core/         # Config, rate limiter, middleware
│   │   │   ├── db/           # Async DB session lifecycle
│   │   │   ├── models/       # Models
│   │   │   ├── repositories/ # SQL data access & transaction management
│   │   │   ├── schemas/      # Pydantic request/response schemas
│   │   │   ├── services/     # Counter leasing & URL creation logic
│   │   │   └── main.py       # FastAPI application entrypoint
│   │   ├── tests/            # Write service unit tests
│   │   └── Dockerfile
│   │
│   └── read_service/
│       ├── app/
│       │   ├── api/          # Route handlers (GET /{short_code}, /health, /ready)
│       │   ├── core/         # Config, middleware
│       │   ├── db/           # Async DB session lifecycle
│       │   ├── repositories/ # Read repository
│       │   ├── services/     # Cache-aside & redirect orchestration
│       │   └── main.py       # FastAPI application entrypoint
│       ├── tests/            # Read service unit tests
│       └── Dockerfile
│
├── shared/                   # Shared libraries across services
│   ├── config/               # Pydantic base settings
│   ├── database/             # Declarative base & async engine
│   ├── models/               # SQLAlchemy URL model & indexes
│   └── utilities/            # Base62, structured logging, errors, validation
│
├── migrations/               # Alembic database migrations
├── nginx/                    # Nginx API Gateway configuration
├── scripts/                  # Seed script & background cleanup worker
├── tests/                    # End-to-end and resilience integration tests
├── load_testing/             # Locust load test scenarios
├── docs/                     # System design trade-offs, failures, and interview notes
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

---

## 📚 In-Depth Documentation

- [System Design Trade-Offs](docs/tradeoffs.md): Deep-dive into Hash vs. Counter, Redis caching, Read/Write separation, and PostgreSQL vs NoSQL.
- [Failure Scenarios & Resilience](docs/failure-scenarios.md): Comprehensive breakdown of 10 failure modes and production recovery strategies.
- [System Design Interview Walkthrough](docs/interview-notes.md): Structured interview preparation notes with 10x and 100x scaling roadmaps.
