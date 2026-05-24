# Bedrock Production Support Chatbot

An AI-powered incident triage and resolution assistant for production support teams, built entirely with **AWS Bedrock + boto3 Python**. The chatbot answers questions about application features and resolves incidents by retrieving context from your indexed knowledge base.

---

## Project structure

```
bedrock-support-chatbot/
│
├── config.py                        # Central config — reads from .env
│
├── bedrock/
│   └── instruction.txt              # Agent system prompt (version-controlled)
│
├── lambda/
│   ├── chatbot_handler.py           # Chatbot API Lambda
│   └── ingest_handler.py           # KB ingestion trigger Lambda
│
├── scripts/
│   ├── phase1/                      # Run once — initial setup
│   │   ├── 01_create_iam_role.py
│   │   ├── 02_setup_s3_bucket.py
│   │   ├── 03_create_knowledge_base.py
│   │   ├── 04_create_agent.py
│   │   └── 05_deploy_lambda.py
│   │
│   └── phase2/                      # Continuous update pipeline
│       ├── 06_setup_auto_ingest.py
│       ├── 07_setup_weekly_sync.py
│       ├── 08_deploy_agent_update.py
│       ├── 09_setup_monitoring.py
│       └── 10_upload_incident.py
│
├── infra/
│   └── lambda_role.py              # Creates the Lambda execution role
│
├── docs/
│   ├── knowledge-base/             # Your documents live here
│   │   ├── app-features/
│   │   ├── incident-history/
│   │   └── runbooks/
│   └── templates/
│       └── incident-template.md    # Incident report template
│
├── tests/
│   └── test_chatbot_handler.py
│
├── requirements.txt
├── .env.example
└── .gitignore
```

> **`bedrock_ids.json`** is written automatically by the setup scripts and contains all resource IDs (KB ID, Agent ID, etc.). It is gitignored — never commit it.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | `python --version` |
| AWS account | Bedrock available in `us-east-1` / `us-west-2` |
| AWS credentials | IAM user or role with admin rights for initial setup |
| Bedrock model access | Enable **Claude 3 Sonnet** and **Titan Embeddings V2** in the Bedrock console |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-org/bedrock-support-chatbot.git
cd bedrock-support-chatbot

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=prod-support-kb-docs
```

The `BEDROCK_*` variables are populated automatically by the Phase 1 scripts.

### 3. Add your documents

Place your documents under `docs/knowledge-base/`:

```
docs/knowledge-base/
├── app-features/       ← feature guides, changelogs
├── incident-history/   ← past incident reports (.md)
└── runbooks/           ← SOPs and troubleshooting guides
```

Use the template at `docs/templates/incident-template.md` for incident reports.

### 4. Enable Bedrock model access

In the AWS Console → **Amazon Bedrock → Model access**:
- ✅ Anthropic Claude 3 Sonnet
- ✅ Amazon Titan Embeddings V2

---

## Phase 1 — Initial setup (run once)

Run the scripts in order. Each script saves its output IDs to `bedrock_ids.json` so subsequent scripts can pick them up automatically.

```bash
# Step 1 — IAM roles
python scripts/phase1/01_create_iam_role.py

# Step 1b — Lambda execution role
python infra/lambda_role.py

# Step 2 — S3 bucket + document upload
python scripts/phase1/02_setup_s3_bucket.py

# Step 3 — Knowledge Base + first ingestion (~5–15 min)
python scripts/phase1/03_create_knowledge_base.py

# Step 4 — Bedrock Agent
python scripts/phase1/04_create_agent.py

# Step 5 — Lambda + API Gateway
python scripts/phase1/05_deploy_lambda.py
```

After Step 5, your chatbot is live. Test it:

```bash
curl -X POST https://<your-api-id>.execute-api.us-east-1.amazonaws.com/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I resolve a DB connection timeout?", "session_id": "test-001"}'
```

---

## Phase 2 — Continuous updates (run once to wire up)

```bash
# Step 6 — Auto-ingest on S3 uploads
python scripts/phase2/06_setup_auto_ingest.py

# Step 7 — Weekly full re-sync (Sunday 02:00 UTC)
python scripts/phase2/07_setup_weekly_sync.py

# Step 9 — CloudWatch dashboard + alarms
python scripts/phase2/09_setup_monitoring.py
```

---

## Day-to-day operations

### Upload a new incident report

After an incident is resolved, create a `.md` file using the template and upload it:

```bash
python scripts/phase2/10_upload_incident.py \
  --file ./docs/knowledge-base/incident-history/my-incident.md \
  --service checkout \
  --severity P2
```

EventBridge fires automatically and re-ingests the knowledge base.

### Update the agent's system prompt

Edit `bedrock/instruction.txt`, then run:

```bash
python scripts/phase2/08_deploy_agent_update.py
```

This creates a new agent version and promotes the `production` alias.

### Roll back to a previous agent version

```bash
python scripts/phase2/08_deploy_agent_update.py --rollback-to 2
```

---

## CI/CD integration

In your CI pipeline (GitHub Actions, GitLab CI, etc.), set the following secrets/env vars:

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION
BEDROCK_AGENT_ID       # from bedrock_ids.json after Phase 1
BEDROCK_AGENT_ALIAS_ID
BEDROCK_ROLE_ARN
LAMBDA_ROLE_ARN
```

Then call `08_deploy_agent_update.py` on merge to `main` when `bedrock/instruction.txt` changes.

---

## Running tests

```bash
pytest tests/ -v
```

---

## Key files reference

| File | Purpose |
|---|---|
| `config.py` | All configuration in one place |
| `bedrock/instruction.txt` | Agent system prompt — edit and redeploy via `08_deploy_agent_update.py` |
| `bedrock_ids.json` | Auto-generated resource IDs — **gitignored** |
| `lambda/chatbot_handler.py` | Runtime chatbot Lambda |
| `lambda/ingest_handler.py` | KB ingestion trigger Lambda |
| `docs/templates/incident-template.md` | Incident report format for the support team |
# bedrock-support-chatbot
# bedrock-support-chatbot
