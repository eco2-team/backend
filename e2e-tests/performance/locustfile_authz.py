"""Locust load test for pure ext-authz performance testing.

This script tests /api/v1/authz/ping which uses Istio directResponse,
measuring only ext-authz + Istio overhead without any backend calls.

Usage:
    # Headless mode
    TOKEN="<jwt>" locust -f locustfile_authz.py --headless -u 2500 -r 250 -t 60s \
        --host https://api.dev.growbin.app

    # Web UI mode
    TOKEN="<jwt>" locust -f locustfile_authz.py --host https://api.dev.growbin.app
    # Then open http://localhost:8089
"""

import os
import urllib3

from locust import HttpUser, task, between

# 연결 경고 무시
urllib3.disable_warnings()


class AuthzPingUser(HttpUser):
    """User that only calls authz/ping endpoint."""

    wait_time = between(0.1, 0.3)  # 100-300ms between requests (reduced aggression)

    # 연결 타임아웃 설정 (DC 방지)
    connection_timeout = 10.0  # 연결 타임아웃 10초
    network_timeout = 30.0     # 응답 타임아웃 30초

    def on_start(self):
        """Set up authentication header."""
        self.token = os.getenv("TOKEN")
        if not self.token:
            raise ValueError("TOKEN environment variable is required")

        self.headers = {
            "Authorization": f"Bearer {self.token}",
        }

    @task
    def authz_ping(self):
        """Call authz/ping - ext-authz + Istio directResponse only."""
        with self.client.get(
            "/api/v1/authz/ping",
            headers=self.headers,
            catch_response=True,
            timeout=(self.connection_timeout, self.network_timeout),  # (connect, read) timeout
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure("Unauthorized (401) - Token expired?")
            elif response.status_code == 403:
                response.failure("Forbidden (403) - ext-authz denied")
            else:
                response.failure(f"Unexpected status: {response.status_code}")
