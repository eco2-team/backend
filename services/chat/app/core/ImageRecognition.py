import os
import yaml
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# ==========================================
# 환경 변수 로드
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ==========================================
# YAML 로딩
# ==========================================
def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_prompt(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_json_data(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

ITEM_CLASS_PATH = "item_class_list.yaml"
SITUATION_TAG_PATH = "situation_tags.yaml"
VISION_PROMPT_PATH = "prompts/vision_classification_prompt.txt"
ANSWER_GENERATION_PROMPT_PATH = "prompts/answer_generation_prompt.txt"

item_class_yaml = load_yaml(ITEM_CLASS_PATH)
situation_tags_yaml = load_yaml(SITUATION_TAG_PATH)

item_class_text = yaml.dump(item_class_yaml, allow_unicode=True)
situation_tags_text = yaml.dump(situation_tags_yaml, allow_unicode=True)



# ==========================================
# GPT-5.1 Vision 호출 (responses API)
# ==========================================
def analyze_images(system_prompt: str, user_input_text: str, image_urls: list[str]):
    
    content_items = []
    system_items = []

    # 2) item_class_list.yaml
    system_items.append({
        "type": "input_text",
        "text": "아래는 item_class_list.yaml 내용입니다:\n\n" + item_class_text
    })

    # 3) situation_tags.yaml
    system_items.append({
        "type": "input_text",
        "text": "아래는 situation_tags.yaml 내용입니다:\n\n" + situation_tags_text
    })

    # 4) 시스템 프롬프트
    system_items.append({
        "type": "input_text",
        "text": system_prompt
    })
    
    # 1) 사용자 입력 텍스트
    content_items.append({
        "type": "input_text",
        "text": user_input_text
    })

    # 5) 이미지 URL → MUST USE input_image
    for url in image_urls:
        content_items.append({
            "type": "input_image",
            "image_url": url
        })

    # ===== Vision 호출 =====
    response = client.responses.create(
        model="gpt-5.1",
        input=[
            {
                "role": "user",
                "content": content_items
            },
            {
                "role": "system",
                "content": system_items
            }
        ]
    )

    return response.output_text


# ==========================================
# Lite RAG: 분류 결과 기반 JSON 파일 매칭
# ==========================================
def find_matching_json(classification_result: dict) -> str:
    """
    분류 결과를 기반으로 source/ 폴더에서 매칭되는 JSON 파일 경로를 반환

    Args:
        classification_result: Vision API의 분류 결과 JSON

    Returns:
        매칭된 JSON 파일 경로 (문자열), 매칭 실패 시 None
    """
    classification = classification_result.get("classification", {})
    major_category = classification.get("major_category")
    middle_category = classification.get("middle_category")

    # source 폴더 경로
    source_dir = Path("source")

    # 1) 재활용폐기물의 경우: {major_category}_{middle_category}.json
    if major_category == "재활용폐기물" and middle_category:
        filename = f"{major_category}_{middle_category}.json"
        file_path = source_dir / filename

        if file_path.exists():
            return str(file_path)

    # 2) 다른 카테고리의 경우: {major_category}.json
    if major_category:
        filename = f"{major_category}.json"
        file_path = source_dir / filename

        if file_path.exists():
            return str(file_path)

    # 3) 매칭 실패
    return None


# ==========================================
# 자연어 답변 생성 (GPT-5 Mini)
# ==========================================
def generate_answer(classification_result: dict, disposal_rules: dict) -> dict:
    """
    분류 결과와 배출 규정을 기반으로 자연어 안내문을 생성

    Args:
        classification_result: Vision API의 분류 결과 JSON
        disposal_rules: 매칭된 JSON 파일의 배출 규정

    Returns:
        자연어 안내문 JSON (dict):
        - disposal_steps: 배출 절차 단계별 설명
        - insufficiencies: 미흡한 항목 리스트
        - user_answer: 사용자 질문에 대한 답변
    """
    # 시스템 프롬프트 로드
    system_prompt = load_prompt(ANSWER_GENERATION_PROMPT_PATH)

    # disposal_rules에서 필요한 정보 추출
    disposal_common = disposal_rules.get("배출방법_공통", {})
    disposal_detail = disposal_rules.get("배출방법_세부", {})
    disposal_forbidden = disposal_rules.get("배출불가_품목_안내", {})

    # user message 데이터 구성
    user_data = {
        "classification": classification_result.get("classification", {}),
        "situation_tags": classification_result.get("situation_tags", []),
        "meta": classification_result.get("meta", {}),
        "lite_rag_result": {
            "배출방법_공통": disposal_common,
            "배출방법_세부": disposal_detail,
            "배출불가_품목_안내": disposal_forbidden
        }
    }
    print(classification_result.get("meta", {})) 

    # JSON 문자열로 변환
    user_message = json.dumps(user_data, ensure_ascii=False, indent=2)

    # GPT-5 Mini 호출
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    )

    # 응답을 JSON으로 파싱
    answer_text = response.choices[0].message.content
    answer_json = json.loads(answer_text)

    return answer_json


# ==========================================
# 실행 예시
# ==========================================

if __name__ == "__main__":

    # 이미지 URL 리스트 — 반드시 Direct Image URL
    image_urls = [
        # "https://i.postimg.cc/NfjDJ3Cd/image.png"
        "https://i.postimg.cc/4dLg2J2Y/seukeulinsyas-2025-11-20-ohu-11-26-26.png"
    ]

    user_input_text = "어떻게 분리수거해야하지?"

    # 프롬프트 파일 로드 및 YAML 데이터 치환
    raw_prompt = load_prompt(VISION_PROMPT_PATH)

    final_prompt = (
        raw_prompt
        .replace("{{ITEM_CLASS_YAML}}", item_class_text)
        .replace("{{SITUATION_TAG_YAML}}", situation_tags_text)
    )

    # 핵심: file_id가 아니라 URL 리스트를 전달
    result = analyze_images(final_prompt, user_input_text, image_urls)

    print("\n===== STEP1 분석 결과 =====\n")
    print(result)

    # JSON 파싱 및 매칭 테스트
    try:
        classification_result = json.loads(result)
        matched_json_path = find_matching_json(classification_result)

        print("\n===== STEP2 Lite RAG 매칭 =====\n")
        if matched_json_path:
            print(f"매칭된 JSON 파일: {matched_json_path}")

            # JSON 파일 로드
            disposal_rules = load_json_data(matched_json_path)

            # STEP3: 자연어 답변 생성
            print("\n===== STEP3 자연어 답변 생성 =====\n")
            answer = generate_answer(classification_result, disposal_rules)
            print(json.dumps(answer, ensure_ascii=False, indent=2))
        else:
            print("매칭된 JSON 파일을 찾을 수 없습니다.")
    except json.JSONDecodeError as e:
        print(f"\nJSON 파싱 오류: {e}")
