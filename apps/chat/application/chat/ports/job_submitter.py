"""Job Submitter Port - 작업 제출 추상화.

API는 작업 제출만 담당하고, 이벤트 발행은 Worker에서 수행.
이 분리로 "상태 변경의 주체 = Worker"가 명확해짐.
"""

from abc import ABC, abstractmethod


class JobSubmitterPort(ABC):
    """작업 제출 포트.

    책임:
    - Taskiq/RabbitMQ에 작업 enqueue만 담당
    - 이벤트 발행 X (Worker의 책임)
    """

    @abstractmethod
    async def submit(
        self,
        job_id: str,
        session_id: str,
        user_id: str,
        message: str,
        image_url: str | None = None,
        user_location: dict[str, float] | None = None,
        model: str | None = None,
    ) -> bool:
        """작업을 큐에 제출.

        Returns:
            성공 여부 (enqueue 성공 시 True)
        """
        pass
