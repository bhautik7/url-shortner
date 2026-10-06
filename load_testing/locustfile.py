"""
Locust Load Testing Suite for URL Shortener.

Focuses heavily on the read path (GET /{short_code}) to simulate
realistic production traffic ratios (99.9% reads, 0.1% writes).
"""

import random
from locust import HttpUser, between, task

# Sample short codes pre-seeded or expected to exist
SAMPLE_SHORT_CODES = [
    "docs",
    "github",
    "google",
    "promo2026",
    "4C92x",
    "4C92y",
    "4C92z",
]


class UrlShortenerUser(HttpUser):
    """
    Simulates user traffic hitting the API Gateway (Nginx).
    """

    # Wait 10ms - 50ms between requests to generate high load
    wait_time = between(0.01, 0.05)

    @task(999)
    def test_redirect_read_heavy(self) -> None:
        """
        Simulates high-throughput GET /{short_code} redirects (Cache HIT & MISS).
        Follow_redirects is disabled to accurately benchmark redirect response time.
        """
        short_code = random.choice(SAMPLE_SHORT_CODES)
        with self.client.get(
            f"/{short_code}",
            allow_redirects=False,
            name="GET /{short_code} (Redirect)",
            catch_response=True,
        ) as response:
            if response.status_code in (302, 404, 410):
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code}")

    @task(1)
    def test_create_short_url_write(self) -> None:
        """
        Simulates occasional write traffic creating short URLs.
        """
        random_suffix = random.randint(100000, 99999999)
        payload = {
            "long_url": f"https://example.com/target-page/{random_suffix}",
            "custom_alias": None,
            "expiration_date": None,
        }
        with self.client.post(
            "/api/v1/urls",
            json=payload,
            name="POST /api/v1/urls (Create)",
            catch_response=True,
        ) as response:
            if response.status_code in (201, 429):
                response.success()
            else:
                response.failure(f"Write failed with status {response.status_code}: {response.text}")
