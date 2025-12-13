"""
ext-authz + auth/ping 부하 테스트

테스트 대상:
    - Endpoint: GET /api/v1/auth/ping
    - ext-authz (Go): Envoy sidecar에서 JWT 검증 수행
    - auth API (FastAPI): 검증 통과 후 간단한 응답 반환

테스트 목적:
    - ext-authz gRPC 서버의 동시 처리 성능 측정
    - JWT 검증 + Redis 블랙리스트 조회 지연 시간 확인
    - Istio service mesh 환경에서의 인증 오버헤드 측정

Usage:
    # 헤더 방식 (Authorization: Bearer <token>)
    ACCESS_TOKEN="your-token" AUTH_METHOD=header locust -f tests/performance/test_ext_authz.py \
        --host=https://api.dev.growbin.app

    # 쿠키 방식 (Cookie: access_token=<token>)
    ACCESS_TOKEN="your-token" AUTH_METHOD=cookie locust -f tests/performance/test_ext_authz.py \
        --host=https://api.dev.growbin.app

    # Headless 모드
    ACCESS_TOKEN="your-token" AUTH_METHOD=cookie locust -f tests/performance/test_ext_authz.py \
        --host=https://api.dev.growbin.app \
        --headless -u 100 -r 10 -t 60s

Environment:
    ACCESS_TOKEN: JWT access token (required)
    AUTH_METHOD: 'header' or 'cookie' (default: cookie)
"""

import os

from locust import HttpUser, between, task


class ExtAuthzPingUser(HttpUser):
    """
    ext-authz 검증을 거치는 /api/v1/auth/ping 부하 테스트.

    Flow:
        Client → Istio Ingress → EnvoyFilter (cookie→header 변환)
              → ext-authz (JWT verify + Redis blacklist)
              → auth-api /ping → Response
    """

    wait_time = between(1, 3)

    def on_start(self):
        """토큰 및 인증 방식 설정."""
        self.token = os.environ.get("ACCESS_TOKEN", "")
        self.auth_method = os.environ.get("AUTH_METHOD", "cookie").lower()

        if not self.token:
            print("⚠️  ACCESS_TOKEN 미설정. 401 오류 발생 예상.")

        # 인증 방식에 따라 헤더/쿠키 설정
        if self.auth_method == "header":
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            self.cookies = {}
            print(f"🔑 인증 방식: Authorization 헤더")
        else:
            self.headers = {
                "Content-Type": "application/json",
            }
            self.cookies = {"access_token": self.token}
            print(f"🍪 인증 방식: access_token 쿠키")

    @task
    def ping_via_ext_authz(self):
        """
        GET /api/v1/auth/ping

        ext-authz가 검증하는 protected endpoint.
        DB I/O 없이 순수 인증 성능만 측정.
        """
        with self.client.get(
            "/api/v1/auth/ping",
            headers=self.headers,
            cookies=self.cookies,
            name="[ext-authz] /api/v1/auth/ping",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure(f"401 Unauthorized - {resp.text[:100]}")
            elif resp.status_code == 403:
                resp.failure(f"403 Forbidden - {resp.text[:100]}")
            else:
                resp.failure(f"{resp.status_code}: {resp.text[:100]}")


class ExtAuthzCookieUser(HttpUser):
    """
    쿠키 방식 전용 테스트.

    Istio EnvoyFilter가 쿠키 → Authorization 헤더 변환.
    """

    wait_time = between(1, 3)

    def on_start(self):
        self.token = os.environ.get("ACCESS_TOKEN", "")
        self.cookies = {"access_token": self.token}
        print(f"🍪 [CookieUser] access_token 쿠키 사용")

    @task
    def ping_cookie(self):
        """쿠키로 인증."""
        with self.client.get(
            "/api/v1/auth/ping",
            cookies=self.cookies,
            name="[cookie] /api/v1/auth/ping",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"{resp.status_code}: {resp.text[:100]}")


class ExtAuthzHeaderUser(HttpUser):
    """
    헤더 방식 전용 테스트.

    직접 Authorization: Bearer <token> 헤더 전달.
    """

    wait_time = between(1, 3)

    def on_start(self):
        self.token = os.environ.get("ACCESS_TOKEN", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        print(f"🔑 [HeaderUser] Authorization 헤더 사용")

    @task
    def ping_header(self):
        """헤더로 인증."""
        with self.client.get(
            "/api/v1/auth/ping",
            headers=self.headers,
            name="[header] /api/v1/auth/ping",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"{resp.status_code}: {resp.text[:100]}")


class ExtAuthzStressUser(HttpUser):
    """
    ext-authz 스트레스 테스트 (최소 대기).

    극한 부하 상황에서 ext-authz + Redis 성능 측정.
    """

    wait_time = between(0.1, 0.3)

    def on_start(self):
        self.token = os.environ.get("ACCESS_TOKEN", "")
        self.auth_method = os.environ.get("AUTH_METHOD", "cookie").lower()

        if self.auth_method == "header":
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.cookies = {}
        else:
            self.headers = {}
            self.cookies = {"access_token": self.token}

    @task
    def ping_stress(self):
        """최소 대기 연속 요청."""
        self.client.get(
            "/api/v1/auth/ping",
            headers=self.headers,
            cookies=self.cookies,
            name="[stress] /api/v1/auth/ping",
        )
