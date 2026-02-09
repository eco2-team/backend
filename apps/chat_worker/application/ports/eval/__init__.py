"""Eval Pipeline Ports - 평가 파이프라인 추상화.

Protocol 기반 포트 정의 (A.4 Convention Decision):
- 신규 포트: Protocol (structural subtyping, 테스트 용이)
- 기존 포트: ABC 유지 (호환성), 향후 refactor/protocol-migration에서 일괄 전환

CQS(Command-Query Separation) 패턴 적용:
- EvalResultCommandGateway: 저장 (Command)
- EvalResultQueryGateway: 조회 (Query)
"""

from chat_worker.application.ports.eval.bars_evaluator import BARSEvaluator
from chat_worker.application.ports.eval.calibration_data_gateway import (
    CalibrationDataGateway,
)
from chat_worker.application.ports.eval.eval_result_command_gateway import (
    EvalResultCommandGateway,
)
from chat_worker.application.ports.eval.eval_result_query_gateway import (
    EvalResultQueryGateway,
)

__all__ = [
    "BARSEvaluator",
    "EvalResultCommandGateway",
    "EvalResultQueryGateway",
    "CalibrationDataGateway",
]
