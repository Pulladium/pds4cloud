# Codebase Flow Diagrams

This document maps the main runtime flows across the React frontend, Spring gateway, FastAPI orchestrator, Kafka workers, storage, and external services.

## System Context

```mermaid
flowchart LR
  User[User browser]
  Frontend[React app<br/>frontend/nasa-front]
  Gateway[Spring gateway<br/>gateway]
  Orchtr[FastAPI orchestrator<br/>orchtr]
  Kafka[(Kafka topics)]
  GatewayDb[(Gateway job DB)]
  OrchtrDb[(Orchestrator DB)]
  ObjectStorage[(MinIO or GCS)]
  PDS[NASA PDS APIs and archives]
  Qdrant[(Qdrant)]
  Clip[CLIP service]
  OpenAI[OpenAI API]
  LangSmith[LangSmith]

  User --> Frontend
  Frontend --> Gateway
  Gateway --> Orchtr
  Gateway <--> GatewayDb
  Gateway <--> Kafka
  Orchtr <--> Kafka
  Orchtr <--> OrchtrDb
  Orchtr <--> ObjectStorage
  Orchtr --> PDS
  Orchtr <--> Qdrant
  Orchtr --> Clip
  Orchtr --> OpenAI
  Orchtr --> LangSmith
```

## Frontend Routes And API Boundary

```mermaid
flowchart TD
  App[App.jsx BrowserRouter]
  Nav[UserAppBar + AIControlPanelTabs]
  Auth[KeycloakProvider + apiFetch]

  App --> Missions[/missions]
  App --> Published[/gallery<br/>/published-projects]
  App --> Discover[/discover<br/>/discover/:id]
  App --> Projects[/my-projects<br/>/my-projects/:id]
  App --> Admin[/admin]
  App --> Vector[/vector-search]

  Nav --> App
  Auth --> Projects
  Auth --> Admin
  Auth --> Vector

  Discover -->|/api/discovery| Gateway[Spring gateway]
  Discover -->|/api/qdrant/add| Gateway
  Projects -->|/api/projects<br/>/api/jobs<br/>/api/models| Gateway
  Published -->|/api/projects/published| Gateway
  Admin -->|/api/admin/jobs<br/>/api/langsmith/stats| Gateway
  Vector -->|/api/qdrant/search| Gateway
```

## Authentication And Authorization

```mermaid
sequenceDiagram
  participant Browser
  participant React
  participant Gateway
  participant Keycloak

  Browser->>React: Open page
  React->>React: Initialize Keycloak adapter
  React->>React: Check login state and roles
  alt authenticated request
    React->>React: Refresh token if needed
    React->>Gateway: API request with Bearer token
    Gateway->>Keycloak: Validate JWT via resource server config
    Gateway->>Gateway: @PreAuthorize role check
  else not authenticated or wrong role
    React->>Browser: Show login or access denied
  end
```

## Gateway Routing

```mermaid
flowchart TD
  Req[Frontend request to /api/*]
  Gateway[GatewayProxyController or Job/Admin controller]

  Req --> Gateway
  Gateway --> Discovery{Path}
  Discovery -->|/api/discovery/**| PDS[NASA PDS API]
  Discovery -->|/api/projects/**| Orchtr[FastAPI orchtr]
  Discovery -->|/api/projects/published| Orchtr
  Discovery -->|/api/projects/:id/publish multipart| Orchtr
  Discovery -->|/api/qdrant/search or add| Orchtr
  Discovery -->|/api/models| Orchtr
  Discovery -->|/api/langsmith/**| Orchtr
  Discovery -->|/api/jobs/**| JobController[Gateway JobController]
  Discovery -->|/api/admin/jobs| AdminController[Gateway AdminController]

  JobController <--> JobDb[(Gateway job DB)]
  AdminController <--> JobDb
  JobController --> KafkaSubmitted[(Kafka: job.submitted)]
```

## Discovery And Static Cursor Pagination

```mermaid
flowchart TD
  DiscoverPage[DiscoverPage]
  Hook[usePds4Products]
  StaticIndex[/public/pds4-page-index.json/]
  GatewayDiscovery[/api/discovery/**]
  PDS[PDS search API]

  DiscoverPage --> Hook
  Hook --> StaticIndex
  Hook -->|page 1 or discovered cursor| GatewayDiscovery
  GatewayDiscovery --> PDS
  PDS --> GatewayDiscovery
  GatewayDiscovery --> Hook
  Hook --> DiscoverPage

  Script[scripts/build-pds4-page-index.mjs] -->|sequential cursor walk| GatewayDiscovery
  Script -->|writes page -> search-after table| StaticIndex
```

## Project CRUD And Add Image

```mermaid
sequenceDiagram
  participant UI as React project UI
  participant Gateway
  participant Orchtr
  participant DB as Orchtr DB
  participant QFlow as Qdrant index flow

  UI->>Gateway: GET /api/projects
  Gateway->>Orchtr: proxy
  Orchtr->>DB: list projects for X-User-Id
  DB-->>Orchtr: projects
  Orchtr-->>UI: status not_started/published + image_count

  UI->>Gateway: POST /api/projects
  Gateway->>Orchtr: proxy
  Orchtr->>DB: enforce <= 3 unpublished projects
  Orchtr->>DB: create Project
  Orchtr-->>UI: created project

  UI->>Gateway: POST /api/projects/{id}/images
  Gateway->>Orchtr: proxy
  Orchtr->>DB: load project, enforce <= 5 images
  Orchtr->>QFlow: index_product(lid, thumb_url)
  QFlow-->>Orchtr: point_id / status
  Orchtr->>DB: create ProjectImage
  Orchtr-->>UI: image row

  UI->>Gateway: DELETE /api/projects/{id}
  Gateway->>Orchtr: proxy
  Orchtr->>DB: delete Project cascade data
  Orchtr-->>UI: 204
```

## Vector Indexing Flow

```mermaid
flowchart LR
  AddImage[Add image to project<br/>or Discover item index]
  IndexProduct[index_product]
  Fetch[fetch_image<br/>download thumbnail + PDS metadata]
  Embed[embed_clip<br/>CLIP image vector]
  Upsert[upsert_qdrant<br/>payload + vector]
  Qdrant[(Qdrant)]
  PDS[NASA PDS product metadata]
  Thumb[Thumbnail URL]
  Clip[CLIP service]

  AddImage --> IndexProduct
  IndexProduct --> Fetch
  Fetch --> Thumb
  Fetch --> PDS
  Fetch --> Embed
  Embed --> Clip
  Embed --> Upsert
  Upsert --> Qdrant
```

## Vector Search Flow

```mermaid
flowchart TD
  VectorPage[VectorSearchPage]
  SearchApi[/api/qdrant/search/]
  Router[orchtr routers/qdrant.py]
  Clip[CLIP text/image embedding]
  Qdrant[(Qdrant query_points)]
  Results[Result cards -> Discover item]

  VectorPage -->|text, image upload, or ref_lid| SearchApi
  SearchApi --> Router
  Router --> Clip
  Router --> Qdrant
  Qdrant --> Router
  Router --> SearchApi
  SearchApi --> VectorPage
  VectorPage --> Results
```

## Async Analysis Job Flow

```mermaid
sequenceDiagram
  participant UI as Project detail UI
  participant Gateway
  participant JobDB as Gateway job DB
  participant Kafka
  participant Dispatcher as orchtr dispatcher
  participant Worker as orchtr image workers
  participant Aggregator as orchtr aggregator
  participant Storage as Object storage

  UI->>Gateway: POST /api/jobs {projectId, images, model}
  Gateway->>JobDB: create Job(PENDING)
  Gateway->>Kafka: job.submitted
  Gateway-->>UI: job_id
  UI->>Gateway: poll GET /api/jobs/{job_id}

  Kafka->>Dispatcher: consume job.submitted
  Dispatcher->>Kafka: job.status PROCESSING_IMAGES 0/N
  Dispatcher->>Kafka: image.task per image

  Kafka->>Worker: consume image.task
  Worker->>Kafka: job.status image_progress processing
  Worker->>Worker: process_product(lid)
  Worker->>Kafka: job.status image_progress done/error
  Worker->>Kafka: image.result

  Kafka->>Aggregator: consume image.result
  Aggregator->>Kafka: job.status PROCESSING_IMAGES received/N
  Aggregator->>Storage: generate + upload PDF
  Aggregator->>Kafka: job.status COMPLETED with pdf_url/tokens/cost

  Kafka->>Gateway: JobStatusConsumer consumes job.status
  Gateway->>JobDB: update status, progress, pdf_url
  UI->>Gateway: poll sees status/progress/pdf_url
```

## Single Image Analysis Pipeline

```mermaid
flowchart TD
  Start[process_product(lid, model, job_id)]
  Graph[LangGraph single_graph]
  Ingest[ingest_one]
  Transform[transform_one]
  Analyze[analyze_one]
  Result[analysis result]
  PDS[PDS registry + image archive]
  Storage[(Object storage)]
  OpenAI[OpenAI vision]
  LangSmith[LangSmith trace tag job:id]

  Start --> Graph
  Graph --> Ingest
  Ingest -->|resolve latest LID + metadata| PDS
  Ingest -->|download .IMG| PDS
  Ingest -->|raw .IMG + metadata JSON| Storage
  Ingest --> Transform
  Transform -->|download .IMG| Storage
  Transform -->|decode PDS IMG| Transform
  Transform -->|gray.jpg, rgb.jpg, array_summary.json| Storage
  Transform --> Analyze
  Analyze -->|download best image + metadata + array summary| Storage
  Analyze -->|image + scientific context| OpenAI
  Analyze -->|result.json| Storage
  Analyze --> Result
  Start -. job context .-> LangSmith
```

## Report And Publish Flow

```mermaid
sequenceDiagram
  participant Aggregator
  participant Storage
  participant UI as Project detail UI
  participant Gateway
  participant Orchtr
  participant Public as Published gallery

  Aggregator->>Storage: upload reports/{job_id}/report.pdf
  Aggregator-->>Gateway: job.status COMPLETED pdf_url
  UI->>Gateway: GET /api/jobs/project/{projectId}
  Gateway-->>UI: latest completed pdf_url
  UI->>Gateway: POST /api/projects/{id}/publish multipart(comment, pdf_url, images)
  Gateway->>Orchtr: proxy multipart
  Orchtr->>Storage: download pdf_url
  Orchtr->>Storage: upload published/{projectId}/report.pdf
  Orchtr->>Storage: upload up to 2 JPG/PNG images
  Orchtr->>Orchtr: set researcher_comment, published paths, published_at
  Public->>Gateway: GET /api/projects/published
  Gateway->>Orchtr: proxy public request
  Orchtr->>Storage: presigned PDF/image URLs
  Orchtr-->>Public: published cards
```

## Chat Flow

```mermaid
sequenceDiagram
  participant UI as ChatDrawer
  participant Gateway
  participant Orchtr
  participant DB as Orchtr DB
  participant Agent as LangGraph ReAct agent
  participant Qdrant
  participant OpenAI

  UI->>Gateway: GET /api/projects/{id}/chat/history
  Gateway->>Orchtr: proxy
  Orchtr->>DB: read ConversationMessage rows
  Orchtr-->>UI: history

  UI->>Gateway: POST /api/projects/{id}/chat/message
  Gateway->>Orchtr: proxy
  Orchtr->>DB: persist user message
  Orchtr->>DB: read project image LIDs + history
  Orchtr->>Agent: run_chat(project_lids, history)
  Agent->>Qdrant: get_project_images / find_similar_images
  Agent->>OpenAI: analyze_image or text reasoning
  Agent-->>Orchtr: reply + image_results
  Orchtr->>DB: persist assistant message
  Orchtr-->>UI: assistant response
```

## Admin And Observability Flow

```mermaid
flowchart LR
  AdminPage[AdminPanelPage]
  GatewayAdmin[/api/admin/jobs/]
  JobDb[(Gateway job DB)]
  LangSmithSection[LangSmithSection]
  LangSmithApi[/api/langsmith/stats/]
  OrchtrLangSmith[orchtr routers/langsmith.py]
  LangSmith[LangSmith runs]

  AdminPage --> GatewayAdmin
  GatewayAdmin --> JobDb
  JobDb --> GatewayAdmin
  GatewayAdmin --> AdminPage

  AdminPage --> LangSmithSection
  LangSmithSection --> LangSmithApi
  LangSmithApi --> OrchtrLangSmith
  OrchtrLangSmith --> LangSmith
  LangSmith --> OrchtrLangSmith
  OrchtrLangSmith --> LangSmithSection
```

## Storage Layout

```mermaid
flowchart TD
  Storage[(MinIO or GCS)]
  Raw[mastcamz/sol=SSSSS/*.IMG]
  Metadata[mastcamz/sol=SSSSS/*_metadata.json]
  Transformed[transformed/mastcamz/sol=SSSSS/photo_id/]
  Gray[gray.jpg]
  RGB[rgb.jpg]
  Array[array_summary.json]
  Analysis[analysis/mastcamz/sol=SSSSS/photo_id/result.json]
  Reports[reports/job_id/report.pdf]
  Published[published/project_id/report.pdf + images]

  Storage --> Raw
  Storage --> Metadata
  Storage --> Transformed
  Transformed --> Gray
  Transformed --> RGB
  Transformed --> Array
  Storage --> Analysis
  Storage --> Reports
  Storage --> Published
```
