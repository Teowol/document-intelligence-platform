# AI-Powered Research & Document Intelligence Platform

A secure platform where users can upload **PDF, Excel, CSV, TXT, and Markdown** files, perform **semantic search**, and receive **grounded question-answering** responses sourced exclusively from their own documents.

## 🎯 Key Features

- 📄 **Multi-Format Support:** PDF, Excel, CSV, TXT, Markdown
- 🔍 **Semantic Search:** Meaning-based search powered by OpenAI embeddings + pgvector
- 🤖 **Grounded QA:** LLM-powered answers with function calling, sourced from your documents
- 🔐 **Access Control (RBAC):** Users can only access documents they're authorized to view
- ⚡ **Asynchronous Processing:** File parsing, chunking, and embedding run in the background via Celery

## 🏗️ Technology Stack

- **Backend:** Python 3.12+ · Django 5.2 LTS
- **Database:** PostgreSQL 16 + pgvector
- **Cache & Message Broker:** Redis 7
- **Async Task Processing:** Celery 5 + django-celery-beat
- **LLM:** OpenAI (gpt-4o-mini + text-embedding-3-small)
- **Server:** Gunicorn + NGINX
- **Containerization:** Docker Compose

## 📅 Roadmap & Progress

The project is developed in phases:

| Phase | Title | Status |
|-------|-------|--------|
| 0 | Environment Setup & Django Scaffolding | ✅ Done |
| 1 | Docker, PostgreSQL/pgvector, Redis, `/healthz` | ✅ Done |
| 2 | User Management, Authentication (allauth), RBAC | ✅ Done |
| 3 | Document Model & Secure Upload | ✅ Done |
| 4 | Celery & Async Processing | ✅ Done |
| 5 | Parsing, Normalization, Chunking | ✅ Done |
| 6 | Embeddings & Semantic Search | ✅ Done |
| 7 | LLM QA & Function Calling | ✅ Done |
| 8 | Frontend (Django Templates) | ✅ Done¹ |
| 9 | Testing, Security, Performance | ✅ Done |
| 10 | Ready to Deploy (Production) ² | ✅ Done |

¹ Frontend temeli tamamlandı; istenen ek stiller/özellikler bir dizi
  iyileştirme olarak sona ertelendi ("Frontend Sprint") — hâlâ sürüyor.
² Öğrenim amaçlı proje: gerçek bir sunucuya deploy edilmiyor; Faz 10,
  projenin üretim ortamına hazır bir kuruluma sahip olmasını kapsar — tek
  komutla ayağa kalkabilir, üretim rehberi `deploy/` klasöründedir.

**Durum:** Tüm 10 faz (0–10) tamamlandı. Frontend geliştirmesi ve istenen
ek özellikler hâlâ devam eden bir "Frontend Sprint" olarak yürütülüyor.

For detailed roadmap, see [`document_intelligence_platform_roadmap.md`](./document_intelligence_platform_roadmap.md)

## 🚀 Quick Start

### Requirements

- Python 3.12+
- Docker & Docker Compose
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/Teowol/document-intelligence-platform.git
cd document-intelligence-platform

# Start infrastructure (PostgreSQL + pgvector, Redis)
docker compose -f docker-compose.dev.yml up -d

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env  # adjust DATABASE_URL / SECRET_KEY / OPENAI_API_KEY if needed

# Run database migrations
cd src
python manage.py migrate

# Start development server
python manage.py runserver --insecure
```

### Background processing (Celery)

Uploads are processed asynchronously. Start the worker alongside the dev server:

```bash
cd src
../venv/Scripts/activate  # or: source venv/bin/activate
celery -A config worker --pool=solo --loglevel=info   # Windows: solo pool
```

For local development, set `CELERY_TASK_DEFAULT_QUEUE=documents-local` in
`.env` (as in `.env.example`). Start this local worker alongside Django;
the development Compose file provides only PostgreSQL and Redis. Docker
production workers use the separate `documents` queue because they cannot
read files uploaded to the Windows checkout. Restart Django and the local
worker after changing the queue setting.

On Linux/macOS omit `--pool=solo`. Pipeline: upload → task `documents.tasks.process_document` (parse + chunk) → status `processing` → `ready`, then `documents.tasks.embed_document` computes embeddings via OpenAI so documents become semantically searchable. The detail page auto-refreshes and shows the chunk preview live.

The app is then available at http://127.0.0.1:8000/ (redirects to login), with:
- Admin panel: `/admin/`
- Health check: `/healthz` (reports database + Redis status)
- Sign up / log in / log out: `/accounts/signup/`, `/accounts/login/`
- Documents: `/documents/` (upload, list, detail, delete with RBAC)
- Semantic search: `/documents/search/` (meaning-based, permission-scoped)
- Ask your documents: `/documents/ask/?q=...` (grounded QA with citations)

### Running Tests

```bash
cd src
python -m pytest accounts documents -q --no-cov
```

The suite covers ~52 tests: RBAC/upload validation (accounts + documents), parsing/chunking for all 5 file types, Celery status transitions, and permission-scoped semantic search.

## 📝 License

MIT License - See [`LICENSE`](./LICENSE) file for details.

## 👤 Author

Teoman Ünal

---

**Note:** This project is under active development. Phases 0–10 are complete: scaffolding; Docker infra (PostgreSQL/pgvector + Redis); email auth with RBAC; secure upload with magic-byte validation; Celery async pipeline; PDF/Excel/CSV/TXT/Markdown parsing + chunking; OpenAI embeddings + pgvector HNSW semantic search (permission-scoped); grounded QA with LLM function calling & citations; a full polished frontend — parchment (light) / plum-indigo (dark) themes, TR/EN language switch, dashboard, document grid, and custom 403/404/500 pages; plus hardened tests/security/performance (69 tests, `check --deploy` clean, Redis KPI caching + rate limiting, JSON logging, query-count guards, index migrations, latency baseline); and a production-ready stack (`docker compose up -d --build` with nginx + gunicorn + Celery + Flower + backups + CI).

**Frontend devam ediyor:** Tüm planlı fazlar tamamlandı; frontend geliştirmesi ve ek istenen özellikler hâlâ bir "Frontend Sprint" olarak sürüyor.
