{{- define "alb.stub.fullname" -}}
{{- printf "%s-%s" .Release.Name "alb-controller-stub" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "alb.stub.labels" -}}
app.kubernetes.io/name: aws-load-balancer-controller-stub
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: Helm
{{- end -}}

