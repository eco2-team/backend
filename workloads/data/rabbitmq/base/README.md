# RabbitMQ Cluster Base

`RabbitmqCluster` CR의 공통 스펙을 정의합니다.

- 기본 플러그인/Config(`rabbitmq_prometheus`, `cluster_partition_handling`, etc.)
- `secretBackend.externalSecret`를 통해 ExternalSecret에서 동기화한
  `rabbitmq-default-user` Secret을 참조
- `override.statefulSet`로 RabbitMQ 전용 노드에 스케줄링하고
  `sesacthon.io/infrastructure` taint를 허용

환경별(`dev`, `prod`) 오버레이는 replica/스토리지/리소스 요구사항을 patch 합니다.


