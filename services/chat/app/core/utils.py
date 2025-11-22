import os
import yaml
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# ==========================================
# 환경 변수 로드
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ==========================================
# 경로 상수
# ==========================================
ITEM_CLASS_PATH = "item_class_list.yaml"
SITUATION_TAG_PATH = "situation_tags.yaml"
VISION_PROMPT_PATH = "prompts/vision_classification_prompt.txt"
TEXT_CLASSIFICATION_PROMPT_PATH = "prompts/text_classification_prompt.txt"
ANSWER_GENERATION_PROMPT_PATH = "prompts/answer_generation_prompt.txt"
RESULTS_DIR = "results"

# ==========================================
# 유틸리티 함수
# ==========================================
def load_yaml(path: str):
    """YAML 파일 로드"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_prompt(path: str):
    """텍스트 프롬프트 파일 로드"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_json_data(path: str):
    """JSON 파일 로드"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_openai_client():
    """OpenAI 클라이언트 반환"""
    return client

def save_json_result(data: dict, filename_prefix: str = "result", subfolder: str = "") -> str:
    """
    JSON 데이터를 results/ 폴더에 타임스탬프와 함께 저장

    Args:
        data: 저장할 JSON 데이터 (dict)
        filename_prefix: 파일명 접두사 (기본값: "result")
        subfolder: results/ 아래의 하위 폴더 경로 (예: "vision/classification")

    Returns:
        저장된 파일 경로 (문자열)
    """
    # results 폴더 및 하위 폴더 생성 (없으면)
    if subfolder:
        results_dir = Path(RESULTS_DIR) / subfolder
    else:
        results_dir = Path(RESULTS_DIR)

    results_dir.mkdir(parents=True, exist_ok=True)

    # 타임스탬프 기반 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.json"
    file_path = results_dir / filename

    # JSON 저장
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return str(file_path)
