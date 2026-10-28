{{- define "gauntlet.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "gauntlet.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if contains (include "gauntlet.name" .) .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "gauntlet.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "gauntlet.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "gauntlet.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.api.tag | default .Chart.AppVersion | trunc 63 | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: gauntlet
{{- end }}

{{/* Selector labels for one component: pass (list $ "api"). */}}
{{- define "gauntlet.selectorLabels" -}}
{{- $root := index . 0 -}}
app.kubernetes.io/name: {{ include "gauntlet.name" $root }}
app.kubernetes.io/instance: {{ $root.Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end }}

{{/* An image reference: pass (list $ "api") or (list $ "web"). */}}
{{- define "gauntlet.image" -}}
{{- $root := index . 0 -}}
{{- $image := index $root.Values.image (index . 1) -}}
{{- printf "%s:%s" $image.repository ($image.tag | default $root.Chart.AppVersion) }}
{{- end }}

{{- define "gauntlet.apiHost" -}}
{{- printf "%s-api" (include "gauntlet.fullname" .) }}
{{- end }}

{{/* Pod settings shared by every workload. */}}
{{- define "gauntlet.podDefaults" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
securityContext:
  {{- toYaml .Values.podSecurityContext | nindent 2 }}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/* The backend's environment: the shared ConfigMap, then the secret. */}}
{{- define "gauntlet.backendEnv" -}}
envFrom:
  - configMapRef:
      name: {{ include "gauntlet.fullname" . }}
  - secretRef:
      name: {{ required "existingSecret must name the Secret that holds DATABASE_URL" .Values.existingSecret }}
{{- end }}
