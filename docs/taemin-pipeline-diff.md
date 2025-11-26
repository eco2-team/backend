# Taemin 님 파이프라인 커밋 추적 메모

> 참고 커밋 (origin/main 기준)
>
> - `a0feda2` – 이미지 분석(Vision) 모듈 추가  
> - `0fbf655` – Lite RAG 모듈 추가  
> - `a42270d` – 자연어 답변 생성 모듈 추가  
> - `6ce4198` – 통합 파이프라인 실행(main) 추가  
> - `ce63ebb` – 분류/상황 태그 YAML 추가  
> - `c8009c2` – 분리배출 규정 JSON 번들 업로드

아래는 각 커밋에서 제공한 파일/로직이 현재 워크트리에 어떻게 반영됐는지, 그리고 재배치 과정에서 발생한 diff 포인트를 정리한 내용이다.

---

## 1. Vision 모듈 (`a0feda2`)

| 항목 | 원본 (services/*) | 현재 경로 (domains/*) | Diff/비고 |
| --- | --- | --- | --- |
| Vision 호출 | `services/chat/app/core/vision.py` | `domains/chat/core/vision.py` | 모듈 import 기준을 상대 경로(`.utils`)로 수정, system/user message 구성은 동일. 이미지 URL은 `{"type": "input_image", "image_url": {"url": ...}}` 형태로 유지. |
| 프롬프트 | `services/chat/app/core/prompts/vision_classification_prompt.txt` | `domains/chat/core/prompts/vision_classification_prompt.txt` | 파일 내용 그대로 복제. |
| YAML 리소스 | `services/chat/app/core/item_class_list.yaml`, `situation_tags.yaml` | `domains/chat/core/` 동일 파일명 | diff 없음. |

## 2. Lite RAG 모듈 (`0fbf655`)

| 항목 | 원본 | 현재 | Diff/비고 |
| --- | --- | --- | --- |
| `rag.py` | `services/chat/app/core/rag.py` | `domains/chat/core/rag.py` | `SOURCE_DIR` 상수를 `.utils`에서 가져오도록 경로만 변경. 로직은 동일. |
| 규정 JSON | `services/chat/app/core/source/*.json` | `domains/chat/core/source/*.json` | 모든 JSON 파일을 동일 이름으로 복사. |

## 3. 자연어 답변 생성 (`a42270d`)

| 항목 | 원본 | 현재 | Diff/비고 |
| --- | --- | --- | --- |
| `answer.py` | `services/chat/app/core/answer.py` | `domains/chat/core/answer.py` | JSON 파싱 실패 시 예외를 발생시키도록 보강한 것 외에는 동일. 저장 경로는 `.utils`의 `save_json_result` 재사용. |
| 프롬프트 | `services/chat/app/core/prompts/answer_generation_prompt.txt` | `domains/chat/core/prompts/answer_generation_prompt.txt` | 내용 그대로 복사. |

## 4. 통합 파이프라인 (`6ce4198`)

| 항목 | 원본 | 현재 | Diff/비고 |
| --- | --- | --- | --- |
| 실행 스크립트 | `services/chat/app/core/main.py` | `domains/chat/core/pipeline.py` | 함수/CLI 구조는 동일하나, 재사용을 위해 `PipelineError` 예외와 `save_result` 옵션 등을 추가. package export를 위해 `domains/chat/core/__init__.py`에서 `process_waste_classification`을 노출. |

## 5. YAML / JSON 리소스 (`ce63ebb`, `c8009c2`)

모든 YAML 및 JSON 파일을 `domains/chat/core/`로 옮겨 동일한 계층 구조를 유지했다. 파일명(예: `재활용폐기물_플라스틱류.json`)과 내용은 원본과 동일함을 double-check 완료.

---

## 6. 서비스 연동에 대한 diff

| 서비스 | 원본 구조 | 현재 구조 | Diff/비고 |
| --- | --- | --- | --- |
| Chat API | `services/chat/app/services/chat.py` – Vision 파이프라인 미포함 | `domains/chat/services/chat.py` – `image_urls` 존재 시 `process_waste_classification` 실행 | 이미지가 포함된 요청에서만 파이프라인을 타도록 로직 추가. 응답에 `pipeline_result`를 포함하도록 모델/스키마 확장. |
| Scan API | 원본 Scan 서비스는 목업 응답 | `domains/scan/app/services/scan.py` – 동일 파이프라인 호출 | Scan 도메인에 파이프라인 전체를 연결하여 `ClassificationResponse.pipeline_result`에 Vision→RAG→Answer 결과를 담도록 변경. |

---

## 7. 참고 경로 요약

- 파이프라인/리소스: `domains/chat/core/**`
- Chat 서비스: `domains/chat/services/chat.py`
- Scan 서비스: `domains/scan/app/services/scan.py`
- 공유 스키마: `domains/_shared/schemas/waste.py`

위 경로들에서 diff가 발생한 지점은 모두 기록됐으며, 내용은 타민님 커밋과 동일한 구조/데이터를 유지하도록 이식되었음을 확인함.

