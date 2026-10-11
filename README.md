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
| 5 | Parsing, Normalization, Chunking | ⏳ Next |
| 4 | Celery & Async Processing | ⬜ Planned |
| 5 | Parsing, Normalization, Chunking | ⬜ Planned |
| 6 | Embeddings & Semantic Search | ⬜ Planned |
| 7 | LLM QA & Function Calling | ⬜ Planned |
| 8 | Frontend (Django Templates) | ⬜ Planned |
| 9 | Testing, Security, Performance | ⬜ Planned |
| 10 | Production Deployment | ⬜ Planned |

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
cd document-intellegence-platform

# Start infrastructure (PostgreSQL + pgvector, Redis)
docker compose -f docker-compose.dev.yml up -d

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env  # adjust DATABASE_URL / SECRET_KEY if needed

# Run database migrations
cd src
python manage.py migrate

# Start development server
python manage.py runserver
```

### Background processing (Celery)

Uploads are processed asynchronously. Start the worker alongside the dev server:

```bash
cd src
../venv/Scripts/activate  # or: source venv/bin/activate
celery -A config worker --pool=solo --loglevel=info   # Windows: solo pool
```

On Linux/macOS omit `--pool=solo`. Pipeline: upload → task `documents.tasks.process_document` → status `processing` → `ready` (visible live on the detail page, which auto-refreshes).

The app is then available at http://127.0.0.1:8000/ (redirects to login), with:
- Admin panel: `/admin/`
- Health check: `/healthz` (reports database + Redis status)
- Sign up / log in / log out: `/accounts/signup/`, `/accounts/login/`
- Documents: `/documents/` (upload, list, detail, delete with RBAC)

### Running Tests

```bash
cd src
python -m pytest accounts -q --no-cov
```

## 📝 License

MIT License - See [`LICENSE`](./LICENSE) file for details.

## 👤 Author

Teoman Ünal

---

**Note:** This project is under active development. Phases 0–5 are complete (scaffolding; Docker infra with PostgreSQL/pgvector + Redis; email auth with RBAC; secure upload with magic-byte validation; Celery async processing pipeline; PDF/Excel/CSV/TXT/Markdown parsing with normalization and overlapping chunking). Next up: Phase 6 — Embeddings & pgvector Semantic Search.
