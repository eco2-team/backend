#!/usr/bin/env bash
#
# 비어 있지 않은 S3 버킷(Versioning 활성화 포함)을 완전히 정리한 뒤 삭제할 때 사용.
# AWS CLI 공식 권장 방식(list-object-versions + delete-objects)을 반복 실행한다.
#
# 사용법:
#   ./scripts/utilities/empty-versioned-bucket.sh <bucket-name> [region]
#
# 예시:
#   ./scripts/utilities/empty-versioned-bucket.sh dev-sesacthon-dev-images ap-northeast-2
#
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <bucket-name> [region]" >&2
  exit 1
fi

BUCKET="$1"
REGION="${2:-ap-northeast-2}"

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI가 필요합니다. 먼저 설치/설정해주세요." >&2
  exit 1
fi

LIST_FILE="$(mktemp)"
DELETE_FILE="$(mktemp)"
trap 'rm -f "$LIST_FILE" "$DELETE_FILE"' EXIT

echo "🧹 Emptying bucket '${BUCKET}' in region '${REGION}'..."

TOTAL_DELETED=0
ITERATION=0

while true; do
  ITERATION=$((ITERATION + 1))
  aws s3api list-object-versions \
    --bucket "${BUCKET}" \
    --region "${REGION}" \
    >"${LIST_FILE}"

  COUNT=$(
    LIST_FILE="${LIST_FILE}" DELETE_FILE="${DELETE_FILE}" python3 <<'PY'
import json
import os

list_file = os.environ["LIST_FILE"]
delete_file = os.environ["DELETE_FILE"]

with open(list_file, "r", encoding="utf-8") as f:
    data = json.load(f)

objects = []
for section in ("Versions", "DeleteMarkers"):
    for item in data.get(section) or []:
        objects.append({"Key": item["Key"], "VersionId": item["VersionId"]})

if objects:
    with open(delete_file, "w", encoding="utf-8") as f:
        json.dump({"Objects": objects, "Quiet": False}, f)

print(len(objects))
PY
  )

  if [[ "${COUNT}" -eq 0 ]]; then
    echo "✅ Bucket is already empty (iteration ${ITERATION})."
    break
  fi

  echo "  - Iteration ${ITERATION}: deleting ${COUNT} objects..."
  aws s3api delete-objects \
    --bucket "${BUCKET}" \
    --region "${REGION}" \
    --delete "file://${DELETE_FILE}"

  TOTAL_DELETED=$((TOTAL_DELETED + COUNT))
done

echo "🎯 Finished. Total deleted objects/versions: ${TOTAL_DELETED}"
