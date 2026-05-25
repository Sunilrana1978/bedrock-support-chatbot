#!/usr/bin/env bash
# deploy.sh — Package Lambda functions and deploy the CloudFormation stack.
#
# Usage:
#   ./scripts/deploy.sh           # create or update the stack
#   ./scripts/deploy.sh --delete  # delete the stack
#
# Prerequisites: aws CLI, python3, zip

set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────

# Load .env if present
if [ -f .env ]; then
  set -o allexport
  # shellcheck disable=SC1091
  source <(grep -v '^#' .env | grep -v '^$')
  set +o allexport
fi

STACK_NAME="bedrock-support-chatbot"
REGION="${AWS_REGION:-us-east-1}"
KB_BUCKET="${S3_BUCKET_NAME:-prod-support-kb-docs}"
SNS_ARN="${SNS_ALERTS_ARN:-}"
TEMPLATE="infra/cloudformation/template.yml"

ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account --output text --region "$REGION")

# Separate bucket for CF artifacts (Lambda zips, packaged template).
# Override with ARTIFACTS_BUCKET env var if needed.
ARTIFACTS_BUCKET="${ARTIFACTS_BUCKET:-cf-artifacts-${ACCOUNT_ID}-${REGION}}"

# ── Delete mode ───────────────────────────────────────────────────────────────

if [ "${1:-}" = "--delete" ]; then
  echo "==> Deleting stack '${STACK_NAME}'…"
  aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

  echo "==> Waiting for deletion to complete…"
  aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

  echo "Stack deleted."
  exit 0
fi

# ── Step 1: Create the artifacts bucket (idempotent) ─────────────────────────

echo "==> [1/6] Ensuring artifacts bucket '${ARTIFACTS_BUCKET}' exists…"
if ! aws s3api head-bucket --bucket "$ARTIFACTS_BUCKET" --region "$REGION" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket \
      --bucket "$ARTIFACTS_BUCKET" \
      --region "$REGION"
  else
    aws s3api create-bucket \
      --bucket "$ARTIFACTS_BUCKET" \
      --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi
  echo "    Bucket created."
else
  echo "    Bucket already exists."
fi

# ── Step 2: Package and upload Lambda functions ───────────────────────────────

echo "==> [2/6] Packaging Lambda functions…"

# chatbot handler  →  lambda/chatbot.zip
(cd lambda && zip -q /tmp/chatbot.zip chatbot_handler.py)
aws s3 cp /tmp/chatbot.zip "s3://${ARTIFACTS_BUCKET}/lambda/chatbot.zip" \
  --region "$REGION"
echo "    Uploaded chatbot_handler.py → s3://${ARTIFACTS_BUCKET}/lambda/chatbot.zip"

# ingest handler  →  lambda/ingest.zip
(cd lambda && zip -q /tmp/ingest.zip ingest_handler.py)
aws s3 cp /tmp/ingest.zip "s3://${ARTIFACTS_BUCKET}/lambda/ingest.zip" \
  --region "$REGION"
echo "    Uploaded ingest_handler.py → s3://${ARTIFACTS_BUCKET}/lambda/ingest.zip"

# AOSS custom-resource handler  →  lambda/aoss_index_creator.zip
(cd lambda && zip -q /tmp/aoss_index_creator.zip aoss_index_creator.py)
aws s3 cp /tmp/aoss_index_creator.zip \
  "s3://${ARTIFACTS_BUCKET}/lambda/aoss_index_creator.zip" \
  --region "$REGION"
echo "    Uploaded aoss_index_creator.py → s3://${ARTIFACTS_BUCKET}/lambda/aoss_index_creator.zip"

# ── Step 3: Build CloudFormation parameters JSON ─────────────────────────────
# Python handles the multiline AgentInstruction safely.

echo "==> [3/6] Building parameters file…"
PARAMS_FILE=$(mktemp /tmp/cf-params.XXXXXX.json)

python3 - <<PYEOF
import json, os
from pathlib import Path

instruction = Path("bedrock/instruction.txt").read_text().strip()
params = [
    {"ParameterKey": "S3BucketName",    "ParameterValue": "${KB_BUCKET}"},
    {"ParameterKey": "ArtifactsBucket", "ParameterValue": "${ARTIFACTS_BUCKET}"},
    {"ParameterKey": "AgentInstruction","ParameterValue": instruction},
    {"ParameterKey": "SNSAlertsArn",    "ParameterValue": "${SNS_ARN}"},
]
print(json.dumps(params, indent=2))
PYEOF
) > "$PARAMS_FILE"

echo "    Parameters written to ${PARAMS_FILE}"

# ── Step 4: Create or update the CloudFormation stack ────────────────────────

echo "==> [4/6] Deploying CloudFormation stack '${STACK_NAME}'…"

STACK_EXISTS=false
if aws cloudformation describe-stacks \
     --stack-name "$STACK_NAME" \
     --region "$REGION" \
     --output text > /dev/null 2>&1; then
  STACK_EXISTS=true
fi

if $STACK_EXISTS; then
  echo "    Stack exists — running update-stack…"
  if aws cloudformation update-stack \
       --stack-name "$STACK_NAME" \
       --template-body "file://${TEMPLATE}" \
       --parameters "file://${PARAMS_FILE}" \
       --capabilities CAPABILITY_NAMED_IAM \
       --region "$REGION" 2>&1 | grep -q "No updates are to be performed"; then
    echo "    No changes detected — stack is up to date."
    SKIP_WAIT=true
  else
    SKIP_WAIT=false
  fi

  if [ "${SKIP_WAIT:-false}" = "false" ]; then
    echo "==> [5/6] Waiting for stack update to complete…"
    aws cloudformation wait stack-update-complete \
      --stack-name "$STACK_NAME" \
      --region "$REGION"
  fi
else
  echo "    New stack — running create-stack…"
  aws cloudformation create-stack \
    --stack-name "$STACK_NAME" \
    --template-body "file://${TEMPLATE}" \
    --parameters "file://${PARAMS_FILE}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --on-failure ROLLBACK \
    --region "$REGION"

  echo "==> [5/6] Waiting for stack creation to complete (10–20 min first time)…"
  aws cloudformation wait stack-create-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"
fi

echo "    Stack deployed successfully."

# ── Step 5: Retrieve outputs ──────────────────────────────────────────────────

echo "==> [5/6] Retrieving stack outputs…"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs" \
  --output table

# Save outputs to bedrock_ids.json via Python
python3 - <<PYEOF
import json, subprocess
raw = subprocess.check_output([
    "aws", "cloudformation", "describe-stacks",
    "--stack-name", "${STACK_NAME}",
    "--region", "${REGION}",
    "--query", "Stacks[0].Outputs",
    "--output", "json"
])
outputs = {o["OutputKey"]: o["OutputValue"] for o in json.loads(raw)}
ids = {
    "api_endpoint": outputs.get("ApiEndpoint"),
    "kb_id":        outputs.get("KnowledgeBaseId"),
    "ds_id":        outputs.get("DataSourceId"),
    "agent_id":     outputs.get("AgentId"),
    "alias_id":     outputs.get("AgentAliasId"),
    "bucket":       outputs.get("BucketName"),
}
from pathlib import Path
ids_file = Path("bedrock_ids.json")
existing = json.loads(ids_file.read_text()) if ids_file.exists() else {}
existing.update(ids)
ids_file.write_text(json.dumps(existing, indent=2))
print(f"IDs saved to bedrock_ids.json")
print(f"Chat endpoint: {ids['api_endpoint']}")
PYEOF

# ── Step 6: Upload documents and trigger initial ingestion ────────────────────

echo "==> [6/6] Uploading knowledge-base documents to S3…"
aws s3 sync docs/knowledge-base/ "s3://${KB_BUCKET}/" \
  --region "$REGION" \
  --exclude ".DS_Store" \
  --exclude "*.gitkeep"

echo "    Triggering initial KB ingestion…"
KB_ID=$(python3 -c "import json; print(json.load(open('bedrock_ids.json'))['kb_id'])")
DS_ID=$(python3 -c "import json; print(json.load(open('bedrock_ids.json'))['ds_id'])")

aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "$KB_ID" \
  --data-source-id "$DS_ID" \
  --region "$REGION"

echo ""
echo "==> Deployment complete."
echo "    Monitor ingestion progress in the AWS Bedrock console (takes 5–15 min)."
echo "    Test the chatbot:"
API_ENDPOINT=$(python3 -c "import json; print(json.load(open('bedrock_ids.json'))['api_endpoint'])")
echo "    curl -X POST ${API_ENDPOINT} \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"message\": \"How do I resolve a DB connection timeout?\"}'"

# Cleanup temp files
rm -f "$PARAMS_FILE" /tmp/chatbot.zip /tmp/ingest.zip /tmp/aoss_index_creator.zip
