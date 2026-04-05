# IntentFlow

**Autonomous Enterprise Complaint Resolution Engine**

IntentFlow is a production-grade, AI-powered system that autonomously resolves enterprise IT support tickets using a multi-agent pipeline with voice intake, RAG-powered knowledge retrieval, safety auditing, and self-healing execution.

## Architecture

```
Customer Voice/Chat → Router Agent (Triage + Stress Detection)
                    → Empathy Engine (Validation Therapy)
                    → Knowledge Agent (RAG + Plan Generation)
                    → Judge Agent (Safety + Confidence Scoring)
                    → Action Agent (CRM Execution)
                    → Learner Agent (Self-Healing)
                    → SLA Monitor (Background)
```

## Features

- **Voice-First Intake**: Whisper STT transcribes voice complaints with stress detection
- **Empathy Engine**: Clinical validation therapy reduces customer frustration before resolution
- **Intelligent Triage**: Classifies intent (16 categories) and assigns priority automatically
- **RAG Knowledge Base**: 15 pre-loaded IT support articles with ChromaDB vector search
- **Autonomous Execution**: Executes resolution plans via CRM API calls
- **Self-Healing**: Detects failed endpoints and finds alternative paths automatically
- **Safety Judge**: Policy evaluation, cosine alignment, and confidence scoring
- **SLA Monitor**: Background breach detection with auto-escalation
- **Full Audit Trail**: Every step, decision, and latency logged for compliance

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + Python 3.11 |
| LLM | Groq API (free) — Llama 3.3 70B + Gemma 2 9B |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, local) |
| Vector DB | ChromaDB (persistent) |
| Voice STT | faster-whisper (local, CPU) |
| Database | SQLite + SQLAlchemy |
| Auth | JWT + bcrypt |
| Frontend | React + Vite |
| Deployment | Docker + Render (free) |

## Quick Start

### 1. Clone & Setup

```bash
cd d:\startup
copy .env.example .env
# Edit .env with your GROQ_API_KEY
```

### 2. Install Backend Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Backend

```bash
python app.py
# → http://localhost:8000
```

### 4. Start Frontend (Development)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 5. First Use

1. Open `http://localhost:5173`
2. Click **Register** and create an account
3. Start chatting or use the 🎤 microphone button
4. Try: *"I can't log in to my account, this is ridiculous"*

## API Endpoints

### Auth
- `POST /auth/register` — Create account
- `POST /auth/login` — Sign in
- `GET /auth/me` — Current user

### Tickets
- `POST /tickets` — Submit complaint → runs full pipeline
- `GET /tickets` — List tickets
- `GET /tickets/{id}` — Ticket detail + audit trail

### Voice
- `POST /voice/transcribe` — Audio → text
- `POST /voice/submit` — Audio → text → ticket

### Dashboard (Admin/Agent)
- `GET /metrics/overview` — KPI summary
- `GET /metrics/by-intent` — Intent distribution
- `GET /metrics/by-priority` — Priority distribution
- `GET /metrics/sla` — SLA compliance

### Admin
- `GET /admin/users` — List users
- `PUT /admin/users/{id}/role` — Change role
- `POST /admin/knowledge` — Add KB article

## Deployment to Render

### Option A: Render Blueprint

1. Push to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your repo
4. Add environment variable: `GROQ_API_KEY`
5. Deploy

### Option B: Docker

```bash
# Build frontend first
cd frontend && npm run build && cd ..

# Build & run
docker build -t intentflow .
docker run -p 8000:8000 --env-file .env intentflow
```

## Project Structure

```
├── app.py                  # FastAPI entry point
├── config.py               # Environment configuration
├── database.py             # SQLAlchemy models
├── auth.py                 # JWT + bcrypt
├── llm_client.py           # Groq + Ollama client
├── agents/
│   ├── router_agent.py     # Intent triage + stress detection
│   ├── empathy_engine.py   # Validation therapy
│   ├── knowledge_agent.py  # RAG + plan generation
│   ├── judge_agent.py      # Safety audit + confidence
│   ├── action_agent.py     # CRM execution
│   └── learner_agent.py    # Self-healing
├── rag/
│   ├── embeddings.py       # Local sentence-transformers
│   ├── retriever.py        # ChromaDB vector store
│   └── seed_kb.py          # 15 KB articles
├── audit/logger.py         # Structured audit trail
├── sla/monitor.py          # Background SLA checker
├── orchestration/pipeline.py # 7-phase pipeline
├── routers/                # FastAPI routers
├── frontend/               # React + Vite app
├── Dockerfile              # Multi-stage build
└── render.yaml             # Render deployment
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | **Yes** | — | Free API key from console.groq.com |
| `JWT_SECRET` | **Yes** | — | Random secret for JWT tokens |
| `DATABASE_URL` | No | `sqlite:///./intentflow.db` | Database connection |
| `WHISPER_MODEL` | No | `tiny` | Whisper model size |
| `AUTO_THRESHOLD` | No | `75` | Min confidence for autonomous execution |
| `ASSISTED_THRESHOLD` | No | `45` | Min confidence for assisted mode |

## Making an Admin User

After registering, promote yourself to admin via Python:

```python
from database import SessionLocal, User
db = SessionLocal()
user = db.query(User).filter_by(email="your@email.com").first()
user.role = "admin"
db.commit()
```

Or use the API (if you're already admin):
```bash
curl -X PUT http://localhost:8000/admin/users/<user_id>/role \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

## License

MIT
