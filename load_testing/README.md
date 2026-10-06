# Load Testing Guide

This directory contains load testing scripts using [Locust](https://locust.io/) to evaluate performance under high-concurrency read-heavy traffic.

## Architecture Tested

```
Client / Locust
      │
      ▼
Nginx (Port 80)
      │
  ┌───┴────────────────────────┐
  │ 99.9% Traffic              │ 0.1% Traffic
  ▼                            ▼
Read Service (FastAPI)    Write Service (FastAPI)
  │                            │
  ▼                            ▼
Redis Cache ◄──────────────► PostgreSQL
```

## Running Load Tests

### 1. Ensure Services are Running & Seeded

```bash
# Start Docker stack
make up

# Run DB migrations
make migrate

# Seed sample short URLs
make seed
```

### 2. Run Locust via CLI (Headless)

Run a 1-minute benchmark with 50 concurrent users spawning at 10 users/second:

```bash
locust -f load_testing/locustfile.py --headless -u 50 -r 10 --run-time 1m --host http://localhost
```

### 3. Run Locust with Interactive Web UI

```bash
locust -f load_testing/locustfile.py --host http://localhost
```

Open your browser at `http://localhost:8089` and configure:
- **Number of users**: 100 - 500
- **Ramp-up rate**: 20 users/sec
- **Host**: `http://localhost`

### Expected Benchmarks

- **Read Endpoint (`GET /{short_code}`)**:
  - Redis Cache Hit Latency: `< 2ms` (sub-millisecond at application layer)
  - Throughput: `2,000+ req/sec` per container instance
- **Write Endpoint (`POST /api/v1/urls`)**:
  - Latency: `5-15ms`
  - In-memory batch counter eliminates Redis round-trips for 99.9% of write calls
