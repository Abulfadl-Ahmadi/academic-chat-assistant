# 🎓 Academic LLM Chat Assistant & Research Hub

[![CI & Configuration Validation](https://github.com/Abulfadl-Ahmadi/academic-chat-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Abulfadl-Ahmadi/academic-chat-assistant/actions/workflows/ci.yml)
[![Docker Compose](https://img.shields.io/badge/docker--compose-v2-blue.svg)](https://docs.docker.com/compose/)
[![Open WebUI](https://img.shields.io/badge/Open%20WebUI-Production-darkgreen.svg)](https://github.com/open-webui/open-webui)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20pgvector-336791.svg)](https://github.com/pgvector/pgvector)
[![Caddy](https://img.shields.io/badge/Caddy-Auto%20HTTPS-black.svg)](https://caddyserver.com/)

A production-grade, self-hosted AI chatbot and research assistant designed for university students, educators, and academic researchers (specifically optimized for **Physics, Mathematics, and Engineering** disciplines).

---

## ⚡ Key Capabilities

* **📚 Course RAG & Knowledge Bases:** Direct semantic and keyword hybrid search over uploaded course syllabi, textbooks (Halliday, Griffiths, Jackson), and lecture PDFs with exact citation popups.
* **📐 Native LaTeX / KaTeX Rendering:** Flawless rendering of complex tensors, bra-ket notation ($\langle\psi|\hat{H}|\psi\rangle$), differential forms, and multi-line equations in both inline and block formats.
* **🐍 Interactive Python Code Runner:** In-browser execution (via Pyodide WebAssembly) allowing students to run `numpy`, `scipy`, and `matplotlib` code to visualize physics models and plots directly within the chat.
* **🌐 Agentic Web Search & Literature Discovery:** Multi-step autonomous research for literature reviews, fact-checking, and arXiv article retrieval.
* **🇮🇷 Persian Typography & Smart RTL:** Full RTL support with custom Vazirmatn font face integration and bidirectional text flow for Persian academic prose.
* **🔒 Production Security & RBAC:** Multi-user authentication, granular role-based access control, PostgreSQL 16 state storage, and automated Let's Encrypt SSL.

---

## 🏗️ Architecture

```text
[Students / Researchers Browser]
              │
              ▼ (HTTPS : 443 / Automatic Let's Encrypt SSL)
   ┌──────────────────────────────────────────────┐
   │         Caddy Server (Reverse Proxy)          │
   └──────────────────────┬───────────────────────┘
                          │ (Internal Docker Network : 8080)
   ┌──────────────────────▼───────────────────────┐
   │                  Open WebUI                  │
   │  - KaTeX Math Renderer & Pyodide Code Runner │
   │  - Document Chunking & Hybrid Search (BM25)  │
   │  - Persian Vazirmatn Typography & RTL Styles │
   └──────────┬──────────────────────┬────────────┘
              │                      │
     (State & Vectors)          (API Inferences)
              ▼                      ▼
┌──────────────────────────┐ ┌────────────────────────────────────────────┐
│ PostgreSQL 16 (pgvector) │ │ External API Gateway (https://ai.gcat.ir)  │
│ - Users, Chats & Presets │ │ - Reasoning LLMs (Gemini, Claude, DeepSeek)│
│ - Embeddings Metadata    │ │ - Vector Embeddings Model                  │
└──────────────────────────┘ └────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI for compose & script validation
├── custom/
│   └── custom.css               # Persian Vazirmatn typography & KaTeX styling
├── scripts/
│   ├── init-server.sh           # Automated VPS provisioner (UFW, Docker, folders)
│   └── backup.sh                # Automated PostgreSQL & data snapshot backup
├── .env.example                 # Configuration template with full documentation
├── Caddyfile                    # Caddy reverse proxy with automated SSL
├── docker-compose.yml           # Production multi-container composition
├── IMPLEMENTATION_PLAN.md       # Comprehensive implementation guide for autonomous agents
└── README.md                    # Project documentation
```

---

## 🚀 Quick Start Deployment

### 1. Provision the VPS (One-Shot)

Run the automated provisioning script on your clean Ubuntu 22.04 / 24.04 server:

```bash
chmod +x scripts/init-server.sh
./scripts/init-server.sh
```

### 2. Configure Environment

Copy the template and set your credentials:

```bash
cp .env.example .env
nano .env
```

Ensure `OPENAI_API_BASE_URL` and `OPENAI_API_KEY` point to your API gateway, and configure your target domain.

### 3. Launch Services

```bash
docker compose up -d
```

Check service logs:
```bash
docker compose logs -f
```

---

## 🎨 Post-Deployment Customization

### Apply Persian Typography & Math Stylesheet
1. Go to **Admin Panel** → **Settings** → **Interface** → **Custom CSS**.
2. Copy the contents of [`custom/custom.css`](custom/custom.css) into the box and save.

### Enable Python Code Execution
1. Go to **Admin Panel** → **Settings** → **Interface**.
2. Toggle on **Code Execution** (Pyodide).

### Course Assistants Setup (RAG)
1. Go to **Workspace** → **Knowledge** and upload lecture notes / textbooks.
2. Go to **Workspace** → **Models**, create a custom model (e.g. *Quantum Mechanics Assistant*), set the system prompt, and bind the Knowledge Base.

---

## 🛡️ Automated Backups

To enable automated daily snapshots of the database and uploaded knowledge files, add a crontab entry:

```bash
# Add backup job at 03:30 AM daily
(crontab -l 2>/dev/null; echo "30 3 * * * /opt/chat-assistant/scripts/backup.sh") | crontab -
```

---

## 📄 License

Distributed under the MIT License.
