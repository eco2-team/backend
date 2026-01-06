"""ClassifyContext - Step 간 공유 Context."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassifyContext:
    """Step 간 공유되는 Context.

    모듈 의존 그래프가 아닌 데이터 흐름 그래프로 복잡도 감소.
    각 Step은 이 Context를 입력받아 업데이트 후 반환.
    """

    # === 입력 (필수) ===
    task_id: str
    user_id: str
    image_url: str

    # === 입력 (선택) ===
    user_input: str | None = None

    # === LLM 설정 ===
    llm_provider: str = "openai"
    llm_model: str = "gpt-5.1"

    # === Step 결과 ===
    classification: dict[str, Any] | None = None
    disposal_rules: dict[str, Any] | None = None
    final_answer: dict[str, Any] | None = None
    reward: dict[str, Any] | None = None

    # === 메타데이터 ===
    latencies: dict[str, float] = field(default_factory=dict)
    progress: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Celery Task 간 전달을 위한 dict 변환."""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "image_url": self.image_url,
            "user_input": self.user_input,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "classification_result": self.classification,
            "disposal_rules": self.disposal_rules,
            "final_answer": self.final_answer,
            "reward": self.reward,
            "metadata": self.latencies,
            "progress": self.progress,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassifyContext":
        """dict에서 Context 복원."""
        return cls(
            task_id=data.get("task_id", ""),
            user_id=data.get("user_id", ""),
            image_url=data.get("image_url", ""),
            user_input=data.get("user_input"),
            llm_provider=data.get("llm_provider", "openai"),
            llm_model=data.get("llm_model", "gpt-5.1"),
            classification=data.get("classification_result"),
            disposal_rules=data.get("disposal_rules"),
            final_answer=data.get("final_answer"),
            reward=data.get("reward"),
            latencies=data.get("metadata", {}),
            progress=data.get("progress", 0),
            error=data.get("error"),
        )
