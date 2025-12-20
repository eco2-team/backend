"""Integration tests for Chat domain.

실제 OpenAI API를 호출하는 통합 테스트입니다.

Requirements:
    - OPENAI_API_KEY 환경변수 설정 필요
    - pip install pytest-asyncio httpx

Run:
    # API 키 설정 (AWS SSM에서 가져오기)
    export OPENAI_API_KEY=$(aws ssm get-parameter \
        --name "/dev/shared/openai-api-key" \
        --with-decryption \
        --query "Parameter.Value" \
        --output text)

    # 테스트 실행
    pytest domains/chat/tests/integration/ -v -s
"""
