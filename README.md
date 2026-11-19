# AI Engineering Company Project — Student Template

[![4Geeks Academy](https://img.shields.io/badge/4Geeks-Academy-blue)](https://4geeksacademy.com)
[![AI Engineering](https://img.shields.io/badge/track-AI%20Engineering-green)](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)

_Base template for transversal projects in the AI Engineering Career Program — 4Geeks Academy._

> _Instrucciones disponibles en español en [README.es.md](./README.es.md)._

---

## Purpose

This repository is the **starter template** for transversal projects. You will work on real company scenarios (Brasaland, TrackFlow, Nexova), building deliverables that map to course milestones (Web, Programming, Backend, Telemetry, RAG, Agents, Workflows, Real-time).

- Create a template from this repository.
- Replace the placeholder `CONTEXT.md` with your assigned company context.
- Use `skills/` and the directory-level `README.md` files as working guidance.

---

## Current status of the template

The repository currently provides a **base folder structure and documentation skeleton**. It does not include runnable apps or global scripts yet.

- `CONTEXT.md` is a placeholder and must be replaced with your assigned company context.
- There is no root `AGENTS.md` yet.
- Shared package metadata exists in `packages/shared/package.json` (`@repo/shared-types`), but no workspace runner is configured at root.

---

## Repository structure

```text
ai-engineering-company-project-monorepo/
├── README.md
├── README.es.md
├── CONTEXT.md                # Placeholder to be replaced with assigned context
├── agents/                   # Agent patterns/templates and tools docs
├── data/                     # raw, process, pipelines, eval
├── docs/                     # Project and architecture documentation
├── infra/                    # Docker, Terraform, deployment configs
├── internal/                 # CLIs, packaged migration scripts, internal utilities
├── mcps/                     # Model Context Protocol (MCP) Servers
├── packages/
│   └── shared/               # Shared package (@repo/shared-types)
├── scripts/                  # Script conventions/documentation
├── services/                 # APIs and background workers
├── shared/                   # Shared assets/conventions at repo level
├── skills/                   # Reusable agent skills
├── uis/                      # User interfaces (React, Next.js, Streamlit, HTML)
└── workflows/                # Automation/orchestration documentation
```

---

## How to start

1. **Use this repository as a template** and create your own project repo.
2. **Clone** your repository (or open it in Codespaces).
3. **Replace** `CONTEXT.md` with the full context for your assigned company.
4. **Review** each top-level folder `README.md` to understand intended responsibilities (`uis/`, `services/`, `data/`, `skills/`, etc.).
5. **Start implementing** milestone deliverables in `uis/` and `services/`, reusing `packages/shared/` and `data/` as needed.

---

## Async task queue (Celery + Redis)

Heavy operations are decoupled from the API through a Celery task queue backed
by Redis. The converted operation is the incident CSV analysis
(`POST /api/incidents/analyze` on the Analyzer API, port 8002), the slowest
synchronous operation in the request cycle before this milestone.

```
Client → Analyzer API (producer) → Redis (broker) → Celery worker (consumer) → Redis (result)
```

- The endpoint stages the upload and returns `202 Accepted` with a `task_id`
  immediately; it never waits for the analysis.
- `GET /tasks/{task_id}` reports `pending`, `started`, `success` (with the
  result), or `failure` (with the error).
- Tasks retry up to 3 times with exponential backoff on transient read
  failures; exhausted tasks land in the dead letter queue
  (`GET /tasks/dead-letter`, persisted in `task_queue.dead_letter_tasks`).
- Messages carry only the staged file path — never the file contents.

### Running the stack

```bash
docker compose up -d redis flower celery-worker analyzer-api
```

| Service | Port | Purpose |
|---|---|---|
| `redis` | 6379 | Broker + result backend (`noeviction` memory policy) |
| `flower` | 5555 | Queue monitoring UI (http://localhost:5555) |
| `celery-worker` | — | Separate process that consumes tasks (never inside the API) |
| `analyzer-api` | 8002 | FastAPI producer + `GET /tasks/{task_id}` status endpoint |

**Starting the worker** (inside Docker, recommended):

```bash
docker compose up -d celery-worker
```

**Stopping the worker:**

```bash
docker compose stop celery-worker
```

Stopping the API does not stop the worker or lose queued messages: Redis keeps
them until the worker acknowledges them after a successful run.

**Host development** (without Docker for the Python processes): start Redis
via `docker compose up -d redis`, then run from `backrooms/`:

```bash
uv run --project services celery -A services.task_queue.celery_app:celery_app worker --loglevel=info --pool=solo
```

The `REDIS_URL` and `DATABASE_URL` environment variables are read from the
repo-root `.env`.

**Demonstrating a retry and the dead letter queue:** upload a CSV, then delete
the staged file (`backrooms/services/APIs/uploads/{task_id}.csv`) before the
worker reads it. The worker retries 3 times with increasing backoff, records
the exhausted task in `task_queue.dead_letter_tasks`, and the failure appears
in Flower.

---

## Milestones (reference)

| Milestone | Focus        | Typical deliverables                        |
| --------- | ------------ | ------------------------------------------- |
| 0         | Prework      | Environment setup, first prompts            |
| 1         | Web          | Corporate website, forms, SEO               |
| 2         | Programming  | Business logic, scoring, calculations       |
| 3         | AI-driven UI | AI-generated interfaces                     |
| 4         | Next.js      | Portals, loyalty app, operations UI         |
| 5         | Backend      | Central API (locations, menus, sales, etc.) |
| 6         | Telemetry    | Data pipeline, dashboards                   |
| 7         | RAG & Memory | Semantic knowledge base, search             |
| 8         | Agents       | Support, onboarding, training agents        |
| 9         | Workflows    | n8n automations                             |
| 10        | Real-time    | Live dashboards, alerts, streaming          |

---

## Links

- [4Geeks Academy — AI Engineering](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)
- [How to start a coding project](https://4geeks.com/lesson/how-to-start-a-project)

---

## Contributors

This template was built as part of the 4Geeks Academy AI Engineering Career Program by [@marcogonzalo](https://www.linkedin.com/in/marcogonzalo) and [@alezanchezr](https://x.com/alesanchezr) and many other contributors. Find out more about our [AI Engineering Course](https://4geeksacademy.com/en/career-programs/ai-engineering), and [other courses](https://4geeksacademy.com/en/program-comparison).

You can find other templates and resources like this at the [4Geeks Academy GitHub page](https://github.com/4geeksacademy).

_This template is maintained by 4Geeks Academy for the AI Engineering track. For exclusive use in the programme._
