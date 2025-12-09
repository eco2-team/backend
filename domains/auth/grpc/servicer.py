import logging
from typing import Optional

# 실제 환경에서는 grpcio-tools로 컴파일된 모듈을 임포트해야 합니다.
# 개발 편의를 위해 Mock 처리하거나 실제 경로를 맞춰주세요.
try:
    from envoy.service.auth.v3 import external_auth_pb2
    from envoy.service.auth.v3 import external_auth_pb2_grpc
    from google.rpc import status_pb2
    from google.rpc import code_pb2
except ImportError:

    class Mock:
        pass

    external_auth_pb2 = Mock()
    external_auth_pb2_grpc = Mock()
    external_auth_pb2_grpc.AuthorizationServicer = object
    external_auth_pb2.CheckResponse = lambda **kwargs: kwargs
    external_auth_pb2.OkHttpResponse = lambda **kwargs: kwargs
    external_auth_pb2.DeniedHttpResponse = lambda **kwargs: kwargs
    external_auth_pb2.HttpStatus = lambda **kwargs: kwargs
    external_auth_pb2.HttpStatusCode = Mock()
    external_auth_pb2.HttpStatusCode.Forbidden = 403
    status_pb2 = Mock()
    status_pb2.Status = lambda **kwargs: kwargs
    code_pb2 = Mock()
    code_pb2.OK = 0
    code_pb2.PERMISSION_DENIED = 7

from domains.auth.services.token_blacklist import TokenBlacklist


class AuthorizationServicer(external_auth_pb2_grpc.AuthorizationServicer):
    """
    gRPC Interface Layer
    - REST API의 Router 역할과 동일합니다.
    - 요청을 파싱하고 Service Layer(TokenBlacklist)를 호출하여 결과를 반환합니다.
    """

    def __init__(self):
        self.blacklist_service = TokenBlacklist()

    async def Check(self, request, context):
        """
        Envoy External Authorization Check implementation
        """
        # 1. Request Parsing
        try:
            # Envoy가 전달하는 속성에서 헤더 추출
            headers = request.attributes.request.http.headers
            auth_header = headers.get("authorization", "")
        except Exception:
            auth_header = ""

        token = self._extract_token(auth_header)

        # 2. Call Service Layer
        if token:
            try:
                is_blacklisted = await self.blacklist_service.is_blacklisted(token)
                if is_blacklisted:
                    logging.warning(f"[gRPC] Token blacklisted: {token[:10]}...")
                    return self._deny_request("Token is blacklisted")
            except Exception as e:
                logging.error(f"[gRPC] Error checking blacklist: {e}")
                # Fail-open vs Fail-closed 정책 결정 필요. 여기선 일단 안전하게 Deny 하거나 Pass.
                # 보통 Auth 서버 에러면 Deny가 안전함.
                return self._deny_request("Internal Authorization Error")

        # 3. Response Construction
        return self._allow_request()

    def _extract_token(self, auth_header: str) -> Optional[str]:
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        return auth_header.split(" ")[1]

    def _allow_request(self):
        return external_auth_pb2.CheckResponse(
            status=status_pb2.Status(code=code_pb2.OK),
            ok_response=external_auth_pb2.OkHttpResponse(),
        )

    def _deny_request(self, message: str):
        return external_auth_pb2.CheckResponse(
            status=status_pb2.Status(code=code_pb2.PERMISSION_DENIED, message=message),
            denied_response=external_auth_pb2.DeniedHttpResponse(
                status=external_auth_pb2.HttpStatus(
                    code=external_auth_pb2.HttpStatusCode.Forbidden
                ),
                body=message,
            ),
        )
