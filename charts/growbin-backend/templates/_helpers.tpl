{{/*
Expand the name of the chart.
*/}}
{{- define "growbin-backend.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "growbin-backend.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "growbin-backend.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "growbin-backend.labels" -}}
helm.sh/chart: {{ include "growbin-backend.chart" . }}
{{ include "growbin-backend.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "growbin-backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "growbin-backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "growbin-backend.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "growbin-backend.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
API Service Name
*/}}
{{- define "growbin-backend.api.serviceName" -}}
{{- printf "%s-api-%s" (include "growbin-backend.fullname" .) .name }}
{{- end }}

{{/*
Worker Name
*/}}
{{- define "growbin-backend.worker.name" -}}
{{- printf "%s-worker-%s" (include "growbin-backend.fullname" .) .name }}
{{- end }}

