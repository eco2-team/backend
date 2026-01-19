"""Image Generation Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 GenerateImageCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): GenerateImageCommand - 정책/흐름
- Port: ImageGeneratorPort - Responses API 호출
- Port: ImageStoragePort - 이미지 업로드 (gRPC)

아키텍처 의사결정:
- 기존 Chat Completions 파이프라인 유지
- 이미지 생성 서브에이전트에서만 Responses API 사용
- multi-intent 라우팅 구조 그대로 활용
- 생성된 이미지는 gRPC로 S3에 업로드 후 CDN URL 사용
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.generate_image_command import (
    GenerateImageCommand,
    GenerateImageInput,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.image_generator import ImageGeneratorPort
    from chat_worker.application.ports.image_storage import ImageStoragePort

logger = logging.getLogger(__name__)


def create_image_generation_node(
    image_generator: "ImageGeneratorPort",
    event_publisher: "ProgressNotifierPort",
    image_storage: "ImageStoragePort | None" = None,
    default_size: str = "1024x1024",
    default_quality: str = "medium",
):
    """Image Generation 노드 생성.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)
    - 생성된 이미지 업로드 (gRPC)

    Args:
        image_generator: 이미지 생성 클라이언트 (Responses API)
        event_publisher: 이벤트 발행자 (SSE)
        image_storage: 이미지 저장소 클라이언트 (gRPC, optional)
        default_size: 기본 이미지 크기 (Config에서 주입)
        default_quality: 기본 이미지 품질 (Config에서 주입)

    Returns:
        LangGraph 노드 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = GenerateImageCommand(image_generator=image_generator)

    async def _image_generation_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. output → state 변환
        4. progress notify (UX)

        Args:
            state: 현재 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")
        # 사용자 메시지를 프롬프트로 사용 (다른 노드와 동일한 패턴)
        query = state.get("message", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="image_generation",
            status="processing",
            progress=50,
            message="이미지 생성 중",
        )

        # 1. state → input DTO 변환 (state에서 override 가능)
        # 캐릭터 참조 이미지 우선순위:
        # 1. detected_character (intent_node에서 직접 감지 - 가장 빠름)
        # 2. character_context.asset (character 노드에서 전달 - gRPC 호출 필요)
        reference_url = None
        character_code = None

        # 먼저 detected_character 확인 (intent_node에서 바로 감지된 것)
        detected_character = state.get("detected_character")
        if detected_character:
            reference_url = detected_character.get("image_url")
            character_code = detected_character.get("cdn_code")

        # detected_character가 없으면 character_context 확인
        if not reference_url:
            character_context = state.get("character_context") or {}
            character_asset = character_context.get("asset") if character_context else None
            if character_asset:
                reference_url = character_asset.get("image_url")
                character_code = character_asset.get("code")

        if reference_url:
            logger.info(
                "Using character reference image URL for generation",
                extra={
                    "job_id": job_id,
                    "character_code": character_code,
                    "reference_url": reference_url,
                    "source": "detected_character" if detected_character else "character_context",
                },
            )

        input_dto = GenerateImageInput(
            job_id=job_id,
            prompt=query,
            size=state.get("image_size") or default_size,
            quality=state.get("image_quality") or default_quality,
            reference_image_url=reference_url,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="image_generation",
                status="failed",
                result={"error": output.error_message},
                message="이미지 생성 실패",
            )
            return {
                "image_generation_context": create_error_context(
                    producer="image_generation",
                    job_id=job_id,
                    error=output.error_message or "이미지 생성 실패",
                ),
            }

        # 4. 이미지 업로드 (gRPC) - base64 data URL → CDN URL
        final_image_url = output.image_url
        if image_storage and output.image_url:
            try:
                # base64 data URL 파싱: data:image/png;base64,<base64_data>
                if output.image_url.startswith("data:") and "," in output.image_url:
                    # header와 data 분리
                    header, b64_data = output.image_url.split(",", 1)

                    # content_type 추출 검증
                    header_parts = header.split(":")
                    if len(header_parts) < 2:
                        raise ValueError(f"Invalid data URL header: {header}")

                    mime_parts = header_parts[1].split(";")
                    content_type = mime_parts[0]  # split은 항상 최소 1개 요소 반환

                    # base64 디코딩
                    image_bytes = base64.b64decode(b64_data)

                    logger.info(
                        "Uploading generated image via gRPC",
                        extra={
                            "job_id": job_id,
                            "content_type": content_type,
                            "size_bytes": len(image_bytes),
                        },
                    )

                    # gRPC로 업로드 (메타데이터 포함)
                    upload_metadata = {
                        "job_id": job_id,
                        "description": output.description or "",
                        "has_synthid": str(output.has_synthid).lower(),
                    }
                    if output.width:
                        upload_metadata["width"] = str(output.width)
                    if output.height:
                        upload_metadata["height"] = str(output.height)

                    upload_result = await image_storage.upload_bytes(
                        image_data=image_bytes,
                        content_type=content_type,
                        channel="generated",
                        uploader_id="chat_worker",
                        metadata=upload_metadata,
                    )

                    if upload_result.success and upload_result.cdn_url:
                        final_image_url = upload_result.cdn_url
                        logger.info(
                            "Image uploaded successfully",
                            extra={
                                "job_id": job_id,
                                "cdn_url": final_image_url,
                            },
                        )
                    else:
                        logger.warning(
                            "Image upload failed, using base64 fallback",
                            extra={
                                "job_id": job_id,
                                "error": upload_result.error,
                            },
                        )
            except Exception as e:
                logger.warning(
                    "Image upload error, using base64 fallback",
                    extra={
                        "job_id": job_id,
                        "error": str(e),
                    },
                )

        # Progress: 완료 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="image_generation",
            status="completed",
            progress=80,
            result={"image_url": final_image_url},
            message="이미지 생성 완료",
        )

        return {
            "image_generation_context": create_context(
                data={
                    "image_url": final_image_url,
                    "description": output.description,
                    "revised_prompt": output.revised_prompt,
                    "used_reference": reference_url is not None,
                    "character_code": character_code,
                    # 이미지 메타데이터
                    "width": output.width,
                    "height": output.height,
                    "has_synthid": output.has_synthid,
                },
                producer="image_generation",
                job_id=job_id,
            ),
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def image_generation_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (30000ms)
        - Retry (1회)
        - FAIL_OPEN 처리 (실패해도 진행)
        """
        return await executor.execute(
            node_name="image_generation",
            node_func=_image_generation_node_inner,
            state=state,
        )

    return image_generation_node
