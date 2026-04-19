# Fudi Lead Lab Backend

Backend base en FastAPI para la app interna de captación y análisis de leads de FÜDI.

## Desarrollo local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000`.

## Variables de entorno

La configuración se carga desde variables de entorno o desde un archivo `.env` en la raíz del repo.

```env
APP_NAME="Fudi Lead Lab API"
ENVIRONMENT=local
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

JWT_SECRET_KEY=change-me-in-env
JWT_ACCESS_TOKEN_MINUTES=60

ADMIN_USERNAME=admin@fudi.local
ADMIN_PASSWORD=admin
ADMIN_DISPLAY_NAME="Fudi Admin"

MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=fudi_lead_lab

REDIS_URL=redis://localhost:6379/0

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET=fudi-lead-lab
```

## Endpoints PR1-BE-FOUNDATION

- `GET /api/v1/health`
- `GET /api/v1/health/dependencies`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

## Endpoints PR2-BE-LEAD-DOMAIN

Todos los endpoints de leads requieren `Authorization: Bearer <token>`.

- `GET /api/v1/leads`
- `POST /api/v1/leads`
- `GET /api/v1/leads/{id}`
- `PATCH /api/v1/leads/{id}`
- `GET /api/v1/leads/{id}/sources`
- `GET /api/v1/leads/{id}/activity`
- `POST /api/v1/leads/{id}/activity`
- `GET /api/v1/leads/{id}/status-history`
- `POST /api/v1/leads/{id}/status-transition`
- `GET /api/v1/leads/{id}/score`
- `POST /api/v1/leads/{id}/score/recompute`
- `POST /api/v1/leads/{id}/enrich`
- `GET /api/v1/leads/{id}/enrichment`
- `GET /api/v1/leads/{id}/feature-snapshots`
- `GET /api/v1/leads/{id}/page-snapshots`

Filtros de listado:

- `q`
- `pipelineStatus`
- `city`
- `district`
- `minPriorityScore`
- `maxPriorityScore`
- `page`
- `pageSize`
- `sortBy`
- `sortDirection`

## Endpoints PR3-BE-DISCOVERY-ENGINE

Todos requieren `Authorization: Bearer <token>`.

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{id}`
- `POST /api/v1/jobs/discovery/run`
- `POST /api/v1/jobs/{id}/retry`
- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `PATCH /api/v1/sources/{id}`
- `GET /api/v1/discovery/raw-items`
- `GET /api/v1/discovery/raw-items/{id}`
- `GET /api/v1/ops/summary`

Ejemplo de source local:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/sources `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"sourceKey":"madrid-seed","sourceType":"local_seed","name":"Madrid Seed","config":{"seedItems":[{"name":"Casa Demo","city":"Madrid","district":"Centro","priorityScore":70}]}}'
```

Ejemplo de ejecución manual:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/jobs/discovery/run `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"sourceKey":"madrid-seed"}'
```

Ejemplo de login:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"username":"admin@fudi.local","password":"admin"}'
```

## Endpoints PR5-BE-ENRICHMENT-AND-FEATURE-EXTRACTION

Todos requieren `Authorization: Bearer <token>`.

- `POST /api/v1/leads/{id}/enrich`
- `GET /api/v1/leads/{id}/enrichment`
- `GET /api/v1/leads/{id}/feature-snapshots`
- `GET /api/v1/leads/{id}/page-snapshots`

El enrichment analiza la web principal del lead cuando existe, guarda `page_snapshots`, crea `feature_snapshots` con señales estructuradas y recalcula el score base con evidencia trazable.

## Endpoints PR6-BE-DEDUP-AND-CONSOLIDATION

Todos requieren `Authorization: Bearer <token>`.

- `GET /api/v1/dedup/candidates`
- `GET /api/v1/dedup/clusters`
- `GET /api/v1/dedup/clusters/{id}`
- `POST /api/v1/dedup/clusters/{id}/merge`
- `POST /api/v1/dedup/clusters/{id}/ignore`
- `POST /api/v1/dedup/clusters/{id}/distinct`
- `POST /api/v1/dedup/recompute`

La recomputación genera candidatos por similitud de nombre normalizado, web, teléfono, email, dirección y ubicación. El merge manual conserva trazabilidad en `merge_events`.

## Endpoints PR7-BE-ML-TRAINING-FOUNDATION

Todos requieren `Authorization: Bearer <token>`.

- `POST /api/v1/models/train`
- `GET /api/v1/models`
- `GET /api/v1/models/{id}`
- `POST /api/v1/models/{id}/activate`
- `GET /api/v1/models/runs`

El training usa `feature_snapshots` y leads activos para entrenar modelos iniciales de `newness`, `digital_gap`, `fit` y `contactability` con scikit-learn. Si el dataset local todavía es pequeño o no tiene variación suficiente, registra un baseline trazable para no bloquear el flujo operativo.

## Endpoints PR8-BE-ML-INFERENCE-AND-LIVE-SCORING

Todos requieren `Authorization: Bearer <token>`.

- `POST /api/v1/leads/{id}/predict`
- `POST /api/v1/leads/predict/batch`
- `GET /api/v1/leads/{id}/predictions`
- `GET /api/v1/models/active`
- `POST /api/v1/models/active`
- `GET /api/v1/predictions/runs`

La inferencia usa el modelo activo por tipo, registra `prediction_runs`, actualiza `scoreBreakdown` y deja metadata de modelo en el lead. Enrichment y merge de duplicados intentan disparar inferencia automática cuando hay modelos activos disponibles.
