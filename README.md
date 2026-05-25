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
├── infra/
│   └── cloudformation/
│       └── template.yml            # Full infrastructure as CloudFormation
│
├── scripts/
│   ├── deploy.py                   # Deploy / update / delete the CF stack
│   └── phase2/                     # Day-to-day operational scripts
│       ├── 08_deploy_agent_update.py
│       └── 10_upload_incident.py
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
S3_BUCKET_NAME=prod-support-kb-docs   # must be globally unique
```

`bedrock_ids.json` is written automatically after the stack deploys.

### 3. Add your documents

Place your documents under `docs/knowledge-base/` before deploying:

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

### 5. Deploy the stack

A single command provisions all AWS infrastructure via CloudFormation:

```bash
python scripts/deploy.py
```

This creates (in dependency order):
- IAM roles for Bedrock and Lambda
- S3 bucket with versioning and EventBridge notifications
- OpenSearch Serverless collection and vector index
- Bedrock Knowledge Base + S3 data source
- Bedrock Agent with `production` alias
- Lambda functions (chatbot + ingest)
- API Gateway HTTP API (`POST /chat`)
- EventBridge rules (S3 upload trigger + weekly Sunday sync)
- CloudWatch alarms and dashboard

First deploy takes **10–20 minutes** (OpenSearch collection creation + agent preparation).
Resource IDs are saved to `bedrock_ids.json` and the chat endpoint is printed on completion.

To tear everything down:

```bash
python scripts/deploy.py --delete
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
S3_BUCKET_NAME
SNS_ALERTS_ARN   # optional
```

On merge to `main`:
- Run `python scripts/deploy.py` to apply any infrastructure changes via CloudFormation.
- Run `python scripts/phase2/08_deploy_agent_update.py` when `bedrock/instruction.txt` changes.

---

## Running tests

```bash
pytest tests/ -v
```

---

## Key files reference

| File | Purpose |
|---|---|
| `infra/cloudformation/template.yml` | Full infrastructure definition — single source of truth |
| `scripts/deploy.py` | Deploy / update / delete the CloudFormation stack |
| `config.py` | Runtime configuration (read by operational scripts) |
| `bedrock/instruction.txt` | Agent system prompt — edit and redeploy via `08_deploy_agent_update.py` |
| `bedrock_ids.json` | Auto-generated resource IDs — **gitignored** |
| `lambda/chatbot_handler.py` | Chatbot Lambda source (also embedded inline in the CF template) |
| `lambda/ingest_handler.py` | Ingest Lambda source (also embedded inline in the CF template) |
| `docs/templates/incident-template.md` | Incident report format for the support team |
# bedrock-support-chatbot
# bedrock-support-chatbot
