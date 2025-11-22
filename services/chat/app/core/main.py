import json
from vision import analyze_images
from text_classifier import classify_text
from rag import get_disposal_rules
from answer import generate_answer

# ==========================================
# 전체 파이프라인 실행 함수
# ==========================================
def process_waste_classification(user_input_text: str, image_urls: list[str], save_results: bool = True) -> dict:
    """
    폐기물 분리배출 안내 전체 파이프라인 실행

    Args:
        user_input_text: 사용자 입력 텍스트
        image_urls: 분석할 이미지 URL 리스트
        save_results: API 호출 결과를 각각 저장할지 여부 (기본값: True)

    Returns:
        최종 결과 JSON (dict):
        {
            "classification_result": {...},
            "disposal_rules": {...},
            "final_answer": {...}
        }
    """
    print("\n" + "="*50)
    print("STEP 1: 이미지 분석 및 분류")
    print("="*50)

    # STEP 1: 이미지 분석
    result_text = analyze_images(user_input_text, image_urls, save_result=save_results)
    print(f"\n분석 결과:\n{result_text}")

    # JSON 파싱
    try:
        classification_result = json.loads(result_text)
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 파싱 오류: {e}")
        return {
            "error": "JSON 파싱 실패",
            "raw_result": result_text
        }

    print("\n" + "="*50)
    print("STEP 2: Lite RAG - 배출 규정 매칭")
    print("="*50)

    # STEP 2: 배출 규정 조회
    disposal_rules = get_disposal_rules(classification_result)

    if not disposal_rules:
        print("\n⚠️  매칭된 배출 규정을 찾을 수 없습니다. 분류 결과만으로 답변을 생성합니다.")
        disposal_rules = {}  # 빈 딕셔너리로 계속 진행
    else:
        print(f"\n✅ 배출 규정 매칭 성공")

    print(f"대분류: {classification_result.get('classification', {}).get('major_category')}")
    print(f"중분류: {classification_result.get('classification', {}).get('middle_category')}")
    print(f"소분류: {classification_result.get('classification', {}).get('minor_category')}")

    print("\n" + "="*50)
    print("STEP 3: 자연어 답변 생성")
    print("="*50)

    # STEP 3: 답변 생성
    final_answer = generate_answer(classification_result, disposal_rules, save_result=save_results, pipeline_type="vision")

    print("\n✅ 답변 생성 완료")

    # 최종 결과 반환
    return {
        "classification_result": classification_result,
        "disposal_rules": disposal_rules,
        "final_answer": final_answer
    }

# ==========================================
# 텍스트 기반 파이프라인 실행 함수
# ==========================================
def process_text_classification(user_input_text: str, save_results: bool = False) -> dict:
    """
    텍스트 기반 폐기물 분리배출 안내 전체 파이프라인 실행

    Args:
        user_input_text: 사용자 입력 텍스트
        save_results: API 호출 결과를 각각 저장할지 여부 (기본값: False)

    Returns:
        최종 결과 JSON (dict):
        {
            "classification_result": {...},
            "disposal_rules": {...},
            "final_answer": {...}
        }
    """
    print("\n" + "="*50)
    print("STEP 1: 텍스트 분석 및 분류")
    print("="*50)

    # STEP 1: 텍스트 분류
    result_text = classify_text(user_input_text, save_result=save_results)
    print(f"\n분석 결과:\n{result_text}")

    # JSON 파싱
    try:
        classification_result = json.loads(result_text)
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 파싱 오류: {e}")
        return {
            "error": "JSON 파싱 실패",
            "raw_result": result_text
        }

    print("\n" + "="*50)
    print("STEP 2: Lite RAG - 배출 규정 매칭")
    print("="*50)

    # STEP 2: 배출 규정 조회
    disposal_rules = get_disposal_rules(classification_result)

    if not disposal_rules:
        print("\n⚠️  매칭된 배출 규정을 찾을 수 없습니다. 분류 결과만으로 답변을 생성합니다.")
        disposal_rules = {}  # 빈 딕셔너리로 계속 진행
    else:
        print(f"\n✅ 배출 규정 매칭 성공")

    print(f"대분류: {classification_result.get('classification', {}).get('major_category')}")
    print(f"중분류: {classification_result.get('classification', {}).get('middle_category')}")
    print(f"소분류: {classification_result.get('classification', {}).get('minor_category')}")

    print("\n" + "="*50)
    print("STEP 3: 자연어 답변 생성")
    print("="*50)

    # STEP 3: 답변 생성
    final_answer = generate_answer(classification_result, disposal_rules, save_result=save_results, pipeline_type="text")

    print("\n✅ 답변 생성 완료")

    # 최종 결과 반환
    return {
        "classification_result": classification_result,
        "disposal_rules": disposal_rules,
        "final_answer": final_answer
    }

# ==========================================
# 메인 실행부
# ==========================================
if __name__ == "__main__":
    # 테스트용 입력 데이터
    # 여기서 이미지 URL과 사용자 입력을 수정하여 테스트할 수 있습니다

    image_urls = [
        # "https://i.postimg.cc/NfjDJ3Cd/image.png"
        # "https://i.postimg.cc/8CG49MqS/seukeulinsyas-2025-11-20-ohu-11-38-57.png"
        "https://i.postimg.cc/xdzLgC6Z/seukeulinsyas-2025-11-21-ojeon-12-11-20.png"
        # "https://i.postimg.cc/JhNCyn05/seukeulinsyas-2025-11-21-ohu-10-51-54.png"
    ]

    user_input_text = "골판지는 어떻게 분류해야할까?"
    # user_input_text = "달걀껍질은 음식물 쓰레기야?"
    

    print("\n🌱 Eco² 분리배출 AI 파이프라인 시작")
    print(f"📝 사용자 입력: {user_input_text}")
    print(f"🖼️  이미지 개수: {len(image_urls)}개")

    # 전체 파이프라인 실행
    # result = process_waste_classification(user_input_text, image_urls)
    result = process_text_classification(user_input_text)

    # 최종 결과 출력
    print("\n" + "="*50)
    print("📋 최종 결과")
    print("="*50)

    if "error" in result:
        print(f"\n❌ 오류 발생: {result['error']}")
    else:
        print("\n✅ 처리 완료!")
        print("\n[답변]")
        print(json.dumps(result["final_answer"], ensure_ascii=False, indent=2))

    # 전체 결과를 JSON 파일로 저장 (선택사항)
    # with open("result.json", "w", encoding="utf-8") as f:
    #     json.dump(result, f, ensure_ascii=False, indent=2)
