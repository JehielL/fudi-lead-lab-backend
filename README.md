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

Ejemplo de login:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"username":"admin@fudi.local","password":"admin"}'
```
