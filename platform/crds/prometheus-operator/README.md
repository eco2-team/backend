# Prometheus Operator CRDs

- Source: https://github.com/prometheus-operator/prometheus-operator (tag v0.73.1)
- 포함 CRD: Alertmanager, PodMonitor, Probe, Prometheus, PrometheusRule, ServiceMonitor, ThanosRuler
- `kube-prometheus-stack` Helm chart 56.21.1 (appVersion v0.73.1)와 호환되는 버전

Wave -1에서 `kubectl apply -k platform/crds/prometheus-operator` 실행 후 Helm Operator를 배포한다.
