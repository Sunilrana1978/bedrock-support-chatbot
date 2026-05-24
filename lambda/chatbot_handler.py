"""
Lambda handler — chatbot API endpoint.
Invoked via API Gateway POST /chat.
"""
import json
import logging
import os
import uuid

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=os.environ.get("AWS_REGION_NAME", "us-east-1")
)

AGENT_ID    = os.environ["BEDROCK_AGENT_ID"]
AGENT_ALIAS = os.environ["BEDROCK_AGENT_ALIAS_ID"]


def lambda_handler(event, context):
    body       = json.loads(event.get("body") or "{}")
    user_msg   = body.get("message", "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not user_msg:
        return _resp(400, {"error": "message field is required"})

    try:
        response = runtime.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS,
            sessionId=session_id,
            inputText=user_msg,
            enableTrace=False,
            sessionState={
                "promptSessionAttributes": {"source": "production-support-chatbot"}
            }
        )

        full_text = ""
        for chunk in response["completion"]:
            if "chunk" in chunk:
                full_text += chunk["chunk"]["bytes"].decode("utf-8")

        logger.info({"session": session_id, "chars": len(full_text)})
        return _resp(200, {"response": full_text, "session_id": session_id})

    except Exception as exc:
        logger.error(str(exc))
        return _resp(500, {"error": str(exc)})


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body)
    }
