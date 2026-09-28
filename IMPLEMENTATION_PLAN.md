# Open WebUI Production Deployment & Implementation Plan

> **Target Environment:** Linux VPS (Ubuntu 22.04 / 24.04 LTS, 4 vCPU, 8 GB RAM)  
> **LLM Endpoint:** `https://ai.gcat.ir/v1` (OpenAI-compatible)  
> **Purpose:** Academic & Research AI Chatbot with RAG, LaTeX/KaTeX, Python Code Runner, ArXiv Tool, and Agentic Web Search.

---

## 1. System Architecture Overview

```text
[Students / Researchers Browser]
              │
              ▼ (HTTPS: 443 / Automatic Let's Encrypt SSL)
   ┌──────────────────────────────────────────────┐
   │         Caddy Server (Reverse Proxy)          │
   └──────────────────────┬───────────────────────┘
                          │ (Internal Docker Network : 8080)
   ┌──────────────────────▼───────────────────────┐
   │                  Open WebUI                  │
   │  - KaTeX / LaTeX Math Renderer               │
   │  - RAG Pipeline (Course Lecture Notes / PDFs)│
   │  - Python Code Interpreter (Pyodide)         │
   │  - Agentic Web Search & ArXiv Plugin         │
   │  - User Authentication & RBAC                │
   └──────────┬──────────────────────┬────────────┘
              │                      │
     (Data & State)             (API Calls)
              ▼                      ▼
┌──────────────────────────┐ ┌────────────────────────────────────────────┐
│ PostgreSQL 16 (pgvector) │ │ External API Gateway (https://ai.gcat.ir)  │
│ - Chat Histories & Users │ │ - LLMs: Gemini 3.7/3.8, Claude, DeepSeek   │
│ - Knowledge Metadata     │ │ - Embedding Model: text-embedding-3-small  │
└──────────────────────────┘ └────────────────────────────────────────────┘
```

---

## 2. Prerequisites & Assumptions

- A clean Linux VPS (Ubuntu 22.04 / 24.04 LTS) with root or sudo access.
- Domain name (e.g. `chat.example.com` or `ai.physics.sharif.edu`) with an **A record** pointing to the VPS public IP.
- The external OpenAI-compatible API key (provided in `.env`).

---

## 3. Step-by-Step Execution Plan for AI Agent

### Step 1: VPS Hardening & Base Environment Setup

Execute on the VPS terminal:

```bash
# Update and upgrade system packages non-interactively
sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Install prerequisite packages
sudo apt-get install -y curl wget git ufw htop ca-certificates gnupg lsb-release

# Configure UFW firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (Caddy ACME challenge)
sudo ufw allow 443/tcp   # HTTPS (Traffic)
echo "y" | sudo ufw enable
sudo ufw status

# Install official Docker and Docker Compose plugin
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
rm -f get-docker.sh

# Verify Docker installation
docker --version
docker compose version
```

---

### Step 2: Project Workspace Structure

Create the deployment directory `/opt/chat-assistant`:

```bash
sudo mkdir -p /opt/chat-assistant
sudo chown -R $USER:$USER /opt/chat-assistant
cd /opt/chat-assistant
mkdir -p data caddy_data caddy_config postgres_data
```

---

### Step 3: Configuration Files Generation

#### File 1: `/opt/chat-assistant/.env`
Create `.env` with all necessary variables:

```bash
cat << 'EOF' > /opt/chat-assistant/.env
# ==========================================
# OPEN WEBUI CORE & BRANDING
# ==========================================
WEBUI_NAME=سامانه هوشمند جزوات و پژوهش فیزیک
WEBUI_SECRET_KEY=generate_random_secure_secret_key_98374982374
WEBUI_AUTH=true
ENABLE_SIGNUP=true
DEFAULT_USER_ROLE=user
SHOW_ADMIN_DETAILS=false
ENABLE_COMMUNITY_SHARING=false

# ==========================================
# DATABASE (PostgreSQL)
# ==========================================
DATABASE_URL=postgresql://webui_user:StrongPostgresPass2026!@postgres:5432/openwebui

# ==========================================
# LLM ENDPOINT (ai.gcat.ir)
# ==========================================
OPENAI_API_BASE_URL=https://ai.gcat.ir/v1
OPENAI_API_KEY=${OPENAI_API_KEY:-your_api_key_here}

# ==========================================
# RAG & EMBEDDING CONFIGURATION
# ==========================================
RAG_EMBEDDING_ENGINE=openai
RAG_OPENAI_API_BASE_URL=https://ai.gcat.ir/v1
RAG_OPENAI_API_KEY=${OPENAI_API_KEY:-your_api_key_here}
RAG_EMBEDDING_MODEL=text-embedding-3-small
ENABLE_RAG_HYBRID_SEARCH=true
RAG_TOP_K=5
CHUNK_SIZE=1000
CHUNK_OVERLAP=150

# ==========================================
# CODE EXECUTION (Python Runner)
# ==========================================
ENABLE_CODE_INTERPRETER=true

# ==========================================
# WEB SEARCH & AGENTIC RESEARCH
# ==========================================
ENABLE_WEB_SEARCH=true
WEB_SEARCH_ENGINE=duckduckgo
WEB_SEARCH_RESULT_COUNT=5
EOF
```

> **Note for Agent:** Generate a genuine random 32-character hex string for `WEBUI_SECRET_KEY` using `openssl rand -hex 32`.

---

#### File 2: `/opt/chat-assistant/docker-compose.yml`
Create the multi-container configuration:

```yaml
cat << 'EOF' > /opt/chat-assistant/docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: chat-postgres
    restart: always
    environment:
      POSTGRES_USER: webui_user
      POSTGRES_PASSWORD: StrongPostgresPass2026!
      POSTGRES_DB: openwebui
    volumes:
      - ./postgres_data:/var/lib/postgresql/data
    networks:
      - app-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U webui_user -d openwebui"]
      interval: 5s
      timeout: 5s
      retries: 5

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: chat-webui
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - .env
    volumes:
      - ./data:/app/backend/data
    networks:
      - app-net

  caddy:
    image: caddy:2-alpine
    container_name: chat-caddy
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - ./caddy_data:/data
      - ./caddy_config:/config
    depends_on:
      - open-webui
    networks:
      - app-net

networks:
  app-net:
    driver: bridge
EOF
```

---

#### File 3: `/opt/chat-assistant/Caddyfile`
Replace `DOMAIN_PLACEHOLDER` with the actual assigned domain (e.g. `ai.example.com`):

```caddy
cat << 'EOF' > /opt/chat-assistant/Caddyfile
DOMAIN_PLACEHOLDER {
    reverse_proxy open-webui:8080 {
        header_up Host {host}
        header_up X-Real-IP {remote}
        header_up X-Forwarded-For {remote}
        header_up X-Forwarded-Proto {scheme}
    }
}
EOF
```

---

### Step 4: Service Launch & Verification

Execute to build and run all services:

```bash
cd /opt/chat-assistant
docker compose pull
docker compose up -d

# Check running containers
docker compose ps

# Check container logs for initialization status
docker compose logs open-webui --tail 50
docker compose logs postgres --tail 30
docker compose logs caddy --tail 30
```

#### Healthcheck Assertions:
1. `chat-postgres` status must be `healthy`.
2. `chat-webui` must show `Application startup complete.` and Uvicorn running on port 8080.
3. `chat-caddy` must successfully obtain Let's Encrypt certificate for the domain.
4. HTTP request verification:
   ```bash
   curl -I https://DOMAIN_PLACEHOLDER
   # Expected response: HTTP/2 200 or 302
   ```

---

### Step 5: Post-Deployment Admin Configuration

Once the web application is accessible at `https://DOMAIN_PLACEHOLDER`:

#### 1. First Account Onboarding (Super Admin)
- Navigate to `https://DOMAIN_PLACEHOLDER` in a browser.
- Register the first user account. This account automatically gains **Super Admin** role.

#### 2. Persian Typography & Visual Polish (Custom CSS)
- Navigate to: **Admin Panel** → **Settings** → **Interface** → **Custom CSS**.
- Paste the following CSS snippet and save:

```css
/* Load Vazirmatn Persian Font */
@import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');

*, body, button, input, textarea {
  font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
}

/* Fix RTL reading alignment for Persian mathematical & physics prose */
.chat-message, [dir="auto"] {
  text-align: start;
  unicode-bidi: plaintext;
}

/* LaTeX KaTeX container spacing */
.katex-display {
  margin: 1em 0 !important;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0.5em 0;
}
```

#### 3. Setup Dedicated Academic Models (Course Assistant)
1. Go to **Workspace** → **Knowledge**.
2. Click **Create Knowledge Base** (e.g. `مکانیک کوانتومی ۱` or `الکترودینامیک جکسون`).
3. Upload PDF course materials, lecture notes, or syllabi.
4. Go to **Workspace** → **Models** → **+ Add New Model**:
   - **Name:** `دستیار فیزیک کوانتومی`
   - **Base Model:** Select `agy/gemini-3.7-flash-medium` or `agy/claude-sonnet-4-6`.
   - **System Prompt:**
     ```text
     شما دستیار تخصصی دانشجویان فیزیک دانشگاه هستید. تمامی پاسخها باید دقیق، مستند و همراه با رندر کامل فرمولهای ریاضی با ساختار LaTeX ($...$ برای درونمتنی و $$...$$ برای بلوکی) باشد. در صورت وجود جزوات پیوستشده، پاسخهای خود را مستقیماً با استناد به مباحث جزوه فرمولبندی کنید.
     ```
   - **Knowledge:** Attach the created Knowledge Base.
   - Save the model.

#### 4. Enable ArXiv Tool for Research Students
1. Navigate to **Workspace** → **Tools**.
2. Click **+ Add Tool** or select **Discover from Community**.
3. Import the official **ArXiv Search** tool.
4. Enable the tool for researcher roles or attach it to research-oriented custom models (e.g. `دستیار پژوهش و مقالات`).

---

### Step 6: Automated Database & Data Backup Routine

Configure a daily cron job to dump the PostgreSQL database and compress knowledge vectors:

```bash
cat << 'EOF' | sudo tee /usr/local/bin/backup-openwebui.sh
#!/bin/bash
BACKUP_DIR="/var/backups/openwebui"
DATE=$(date +%Y-%m-%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# Dump PostgreSQL
docker exec chat-postgres pg_dump -U webui_user openwebui | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Snapshot files and uploaded documents
tar -czf "$BACKUP_DIR/data_$DATE.tar.gz" -C /opt/chat-assistant/data .

# Keep only last 14 days of backups
find "$BACKUP_DIR" -type f -mtime +14 -delete
EOF

sudo chmod +x /usr/local/bin/backup-openwebui.sh

# Add to crontab (runs every day at 03:30 AM)
(crontab -l 2>/dev/null; echo "30 3 * * * /usr/local/bin/backup-openwebui.sh") | crontab -
```

---

## 4. Verification Checklist for Agent

- [ ] UFW firewall is active (`22`, `80`, `443` open).
- [ ] Docker containers (`chat-postgres`, `chat-webui`, `chat-caddy`) are all status `Up`.
- [ ] Caddy reverse proxy terminates HTTPS with a valid certificate.
- [ ] Open WebUI connects to `ai.gcat.ir/v1` and models list correctly populated.
- [ ] PDF document upload in Knowledge Base generates vector embeddings without error.
- [ ] Chat query using `#` successfully cites text chunks from uploaded notes.
- [ ] Python code execution displays the interactive **Run** button and renders plots inline.
- [ ] Daily backup cron job is registered and tested with a manual run.
