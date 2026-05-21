# PDS4Cloud

Mars 2020 Mastcam-Z analysis system: React frontend, Spring Gateway, FastAPI/LangGraph orchestrator, Kafka, MinIO, Keycloak, CLIP service, Qdrant, OpenAI, and evaluation protocols.

## .env

Create `.env` in the repository root:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
QDRANT_URL=https://...
QDRANT_API_KEY=...

LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=pds4cloud
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=pds4cloud
VITE_LANGSMITH_URL=https://smith.langchain.com

STORAGE_BACKEND=minio
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=mars2020
MINIO_SECURE=false
PUBLIC_BASE_URL=http://localhost:8088
PUBLIC_OBJECT_BASE_URL=http://localhost:8088
CLIP_SERVICE_URL=http://clip-service:8001

SERVER_PORT=8080
PROXY_ORCHTR_BASE_URL=http://orchtr:8000
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=admin
KEYCLOAK_URL=http://frontend
KEYCLOAK_REALM=pds4cloud
KEYCLOAK_CLIENT_ID=react-client-certedu-api
KEYCLOAK_ISSUER_URI=http://localhost:8088/realms/pds4cloud
KEYCLOAK_JWK_SET_URI=http://keycloak:8080/realms/pds4cloud/protocol/openid-connect/certs
VITE_KEYCLOAK_URL=http://localhost:8088
VITE_GATEWAY_URL=

ORCHTR_URL=http://orchtr:8000
GATEWAY_URL=http://gateway:8080
EVAL_USERNAME=researcher
EVAL_PASSWORD=researcher
EVAL_USERS=researcher,researcher-2,researcher-3
EVAL_ADMIN_USERNAME=admin-user
EVAL_ADMIN_PASSWORD=admin

KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_NODE_ID=1
KAFKA_PROCESS_ROLES=broker,controller
KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:9093
KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER
KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT
KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1
KAFKA_AUTO_CREATE_TOPICS_ENABLE=true
KAFKA_NUM_PARTITIONS=6
CLUSTER_ID=4L6g3nShT-eMCtK--X86sw
```

## Run

```bash
docker compose --profile eval up -d --build
```

Open:

```text
http://localhost:8088
```

## Tests

```bash
pytest orchtr/tests evaluation/tests evaluation/protocols/retry_recovery_e2e/tests
(cd gateway && mvn test)
(cd frontend/nasa-front && npm install && node --test src/__tests__/*.test.js && npm run lint)
```

## Evaluation

Full default evaluation:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.run_all --clean
```

45-image large evaluation:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --cases evaluation/cases_45.yml
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --cases evaluation/cases_45.yml --apply
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.multi_user_project_45.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --cases evaluation/cases_45.yml --apply
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.sequential_reference_45.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.report
```
