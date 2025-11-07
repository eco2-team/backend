{{/*
Expand the name of the chart.
*/}}
{{- define "ecoeco-backend.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ecoeco-backend.fullname" -}}
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
{{- define "ecoeco-backend.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ecoeco-backend.labels" -}}
helm.sh/chart: {{ include "ecoeco-backend.chart" . }}
{{ include "ecoeco-backend.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ecoeco-backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ecoeco-backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "ecoeco-backend.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ecoeco-backend.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
API Service Name
*/}}
{{- define "ecoeco-backend.api.serviceName" -}}
{{- printf "%s-api-%s" (include "ecoeco-backend.fullname" .) .name }}
{{- end }}

{{/*
Worker Name
*/}}
{{- define "ecoeco-backend.worker.name" -}}
{{- printf "%s-worker-%s" (include "ecoeco-backend.fullname" .) .name }}
{{- end }}

