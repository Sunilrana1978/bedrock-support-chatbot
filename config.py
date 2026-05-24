"""
config.py — Single source of truth for all configuration.
Loaded by every script. Values come from .env (local) or
environment variables (CI/CD).
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── AWS ──────────────────────────────────────────────────────────────────
REGION     = os.getenv("AWS_REGION", "us-east-1")
ACCOUNT_ID: str = ""   # populated at runtime via STS

# ── S3 ───────────────────────────────────────────────────────────────────
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "prod-support-kb-docs")
S3_FOLDERS     = ["app-features", "incident-history", "runbooks"]

# ── Bedrock models ────────────────────────────────────────────────────────
EMBEDDING_MODEL_ARN = (
    f"arn:aws:bedrock:{REGION}::foundation-model/"
    "amazon.titan-embed-text-v2:0"
)
FOUNDATION_MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"

# ── Resource names ────────────────────────────────────────────────────────
ROLE_NAME          = "BedrockAgentRole"
LAMBDA_ROLE_NAME   = "LambdaBedrockRole"
KB_NAME            = "prod-support-kb"
DS_NAME            = "s3-docs-source"
AGENT_NAME         = "prod-support-triage-bot"
AGENT_ALIAS_NAME   = "production"
COLLECTION_NAME    = "prod-support-kb"
VECTOR_INDEX_NAME  = "prod-support-index"
CHATBOT_LAMBDA     = "bedrock-support-chatbot"
INGEST_LAMBDA      = "bedrock-kb-ingest"
API_NAME           = "bedrock-chatbot-api"
DASHBOARD_NAME     = "BedrockSupportChatbot"

# ── IDs file (written by Phase 1 scripts, gitignored) ────────────────────
IDS_FILE = Path(__file__).parent / "bedrock_ids.json"

def load_ids() -> dict:
    if IDS_FILE.exists():
        with open(IDS_FILE) as f:
            return json.load(f)
    return {}

def save_ids(data: dict):
    existing = load_ids()
    existing.update(data)
    with open(IDS_FILE, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"IDs saved → {IDS_FILE}")

# ── Agent instruction (loaded from bedrock/instruction.txt) ───────────────
INSTRUCTION_FILE = Path(__file__).parent / "bedrock" / "instruction.txt"

def load_instruction() -> str:
    with open(INSTRUCTION_FILE) as f:
        return f.read().strip()

# ── SNS ───────────────────────────────────────────────────────────────────
SNS_ALERTS_ARN = os.getenv("SNS_ALERTS_ARN", "")
