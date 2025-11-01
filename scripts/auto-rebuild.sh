#!/bin/bash
# 완전 자동 재구축 (확인 없이 진행)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 완전 자동 재구축 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  확인 프롬프트 없이 자동 실행됩니다!"
echo ""

# 자동 모드로 rebuild-cluster.sh 실행
export AUTO_MODE=true
"$SCRIPT_DIR/rebuild-cluster.sh"

echo ""
echo "✅ 자동 재구축 완료!"


