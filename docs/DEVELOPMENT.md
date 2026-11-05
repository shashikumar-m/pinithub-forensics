# Development Guide

## Prerequisites

- **Node.js** 20 LTS or later
- **Python** 3.11 or later
- **PostgreSQL** 15+ (or Docker)
- **npm** 10+ (bundled with Node.js)

## Initial Setup

### 1. Clone and install dependencies

```bash
npm install
```

This installs all workspace dependencies (web, api, shared).

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your database URL and Supabase keys
```

Minimum required for local dev without Supabase:
```env
NODE_ENV=development
PORT=4000
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/pinithub_forensics
DIRECT_URL=postgresql://postgres:postgres@localhost:5432/pinithub_forensics
```

### 3. Set up the database

Start PostgreSQL via Docker:
```bash
docker compose up postgres -d
```

Then apply the schema:
```bash
npm run db:generate
npm run db:push
```

Or use Prisma migrations:
```bash
npm run db:migrate
```

### 4. Install Python dependencies

```bash
cd services/forensics
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Services

### Frontend (port 5173)
```bash
npm run dev:web
```

### Node API (port 4000)
```bash
npm run dev:api
```

### Python Forensic Service (port 8001)
```bash
cd services/forensics
# Activate venv first
uvicorn app.main:app --reload --port 8001
```

### All via Docker
```bash
docker compose up --build
```

## Running Tests

### Frontend (Vitest)
```bash
npm run test:web
```

### Node API (Jest + Supertest)
```bash
npm run test:api
```

### Shared types (tsc)
```bash
npm run test:shared
```

### Python (pytest)
```bash
cd services/forensics
# Activate venv first
pytest
```

### All JS tests
```bash
npm run test
```

## Database Tools

### Prisma Studio (GUI for database)
```bash
npm --workspace @pinithub/api run db:studio
```

### Reset database
```bash
cd apps/api
npx prisma migrate reset
```

## Project Structure

```
pinithub-forensics/
├── apps/
│   ├── web/          # React frontend
│   └── api/          # Express API
├── services/
│   └── forensics/    # Python FastAPI service
├── packages/
│   └── shared/       # Shared TypeScript types
├── infra/
│   └── docker/       # Dockerfiles
├── docs/             # Documentation
├── tests/            # Integration tests
└── docker-compose.yml
```

## Environment Variables

See `.env.example` for all available configuration. Key variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection (pooler) |
| `DIRECT_URL` | Yes | — | PostgreSQL connection (direct) |
| `PORT` | No | 4000 | API server port |
| `MAX_UPLOAD_MB` | No | 25 | Max upload size |
| `CORS_ORIGINS` | No | localhost:5173 | Comma-separated allowed origins |
| `FORENSICS_SERVICE_URL` | No | localhost:8001 | Python service URL |
| `SUPABASE_URL` | No | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | No | — | Service-role key (server only!) |

## Common Issues

### Database connection fails
Ensure PostgreSQL is running. With Docker:
```bash
docker compose up postgres -d
```

### Frontend can't reach API
The Vite dev server proxies `/v1` to the API at port 4000. Ensure the
API is running, or set `VITE_API_URL` in the web app's env.

### Python service not reachable
Ensure uvicorn is running on port 8001. The API checks this in `/v1/ready`.
