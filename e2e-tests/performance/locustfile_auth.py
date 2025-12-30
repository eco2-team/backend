"""
ext-authz Performance Test with Locust

Usage:
  locust -f locustfile_auth.py --headless \
    -u 2500 -r 250 -t 60s \
    --host https://api.dev.growbin.app \
    --csv results

Environment:
  TOKEN: JWT access token
"""
import os
from locust import HttpUser, task, between

TOKEN = os.getenv("TOKEN", "")

class AuthUser(HttpUser):
    # 매우 공격적인 부하 (딜레이 거의 없음)
    wait_time = between(0.01, 0.05)

    @task
    def ping(self):
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        }

        with self.client.get("/api/v1/user/ping", headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 403:
                response.failure("403 Forbidden (ext-authz timeout)")
            elif response.status_code == 401:
                response.failure("401 Unauthorized")
            elif response.status_code >= 500:
                response.failure(f"Server Error ({response.status_code})")
            else:
                response.failure(f"Unexpected ({response.status_code})")
