import sys
from pathlib import Path

# 테스트 실행 시 프로젝트 루트(backend)를 PYTHONPATH에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
