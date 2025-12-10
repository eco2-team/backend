# Waste Pipeline

`domains/_shared/waste_pipeline` 모듈은 Vision/텍스트 분류 결과를 재활용 규정과 결합해 최종 사용자 답변을 만들어내는 **공통 파이프라인**입니다. Scan과 Chat 서비스가 모두 이 모듈을 호출하며, Vision → Lite RAG → Answer 세 단계를 일관되게 실행합니다.

## 구성 요소
- `vision.py`: GPT Vision 모델을 호출해 이미지 + 사용자 입력을 중분류/소분류로 분류합니다.
- `text.py`: 텍스트만으로 동일한 분류 결과를 생성합니다.
- `rag.py`: 분류 결과를 기반으로 `data/source/*.json`에서 배출 규정을 찾습니다.
- `answer.py`: 분류 + 규정 정보를 바탕으로 최종 자연어 답변을 만듭니다.
- `pipeline.py`: 위 세 단계를 orchestration하여 최종 `WasteClassificationResult`를 반환합니다.
- `data/`: Prompt, 상황 태그, 품목 클래스, 규정 JSON이 저장된 정적 리소스 디렉터리입니다.

## 사용 예시

```python
from domains._shared.waste_pipeline import process_waste_classification

result = process_waste_classification(
    user_input_text="무색 페트병인데 라벨을 떼었어요.",
    image_url="https://example.com/pet-bottle.png",
    save_result=False,
    verbose=False,
)
print(result["final_answer"]["user_answer"])
```

텍스트-only 요청은 `process_text_classification()`을 호출하거나 Chat 서비스처럼 `_run_text_pipeline()`을 구현해 활용합니다.

## 환경 변수
- `OPENAI_API_KEY`: Vision/Text/Answer 단계에서 호출하는 OpenAI 클라이언트에 사용됩니다. Scan/Chat 두 서비스 모두 동일한 SSM Parameter를 ExternalSecret으로 주입합니다.

## CI 트리거 메모
- 2025-12-02: waste_pipeline 두 프롬프트/상황 태그 수정으로 Scan/Chat Docker 이미지를 재빌드해야 할 때 README를 업데이트해 CI를 트리거합니다.
