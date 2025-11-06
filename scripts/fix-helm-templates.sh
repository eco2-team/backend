#!/bin/bash
# Helm 템플릿 일괄 수정 스크립트

set -e

API_SERVICES=("auth" "userinfo" "location" "recycle-info" "chat-llm")

echo "🔧 Fixing API Deployment templates..."

for service in "${API_SERVICES[@]}"; do
    file="charts/growbin-backend/templates/api/${service}-deployment.yaml"
    
    if [[ ! -f "$file" ]]; then
        echo "⚠️  File not found: $file"
        continue
    fi
    
    echo "✅ Fixing: $file"
    
    # 1. NodeSelector 수정
    sed -i '' 's/{{- with .Values.api.common.nodeSelector }}/{{- if .Values.api.'"${service//\-/}"'.nodeSelector }}/' "$file"
    sed -i '' '/{{- if .Values.api.'"${service//\-/}"'.nodeSelector }}/,/{{- end }}/ s/{{- toYaml . | nindent 8 }}/{{- toYaml .Values.api.'"${service//\-/}"'.nodeSelector | nindent 8 }}/' "$file"
    
    # 2. Health Probes 교체
    # livenessProbe 블록 찾아서 교체
    perl -i -pe 'BEGIN{undef $/;} s/        \{\{- if \.Values\.api\.\w+\.livenessProbe \}\}\n        livenessProbe:\n          \{\{- toYaml \.Values\.api\.\w+\.livenessProbe \| nindent 10 \}\}\n        \{\{- end \}\}/        livenessProbe:\n          httpGet:\n            path: \/health\n            port: http\n          initialDelaySeconds: 30\n          periodSeconds: 10\n          timeoutSeconds: 5\n          failureThreshold: 3/smg' "$file"
    
    # readinessProbe 블록 찾아서 교체
    perl -i -pe 'BEGIN{undef $/;} s/        \{\{- if \.Values\.api\.\w+\.readinessProbe \}\}\n        readinessProbe:\n          \{\{- toYaml \.Values\.api\.\w+\.readinessProbe \| nindent 10 \}\}\n        \{\{- end \}\}/        readinessProbe:\n          httpGet:\n            path: \/ready\n            port: http\n          initialDelaySeconds: 5\n          periodSeconds: 5\n          timeoutSeconds: 3\n          failureThreshold: 3/smg' "$file"
    
done

echo "✅ All API templates fixed!"

