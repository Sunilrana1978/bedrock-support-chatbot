"""
Phase 1 — Step 5
Zips and deploys the chatbot Lambda function, then wires
an HTTP API (API Gateway v2) endpoint to it.
"""
import io
import json
import time
import zipfile
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION = config.REGION
ids    = config.load_ids()
AGENT_ID    = ids.get("agent_id")  or __import__("os").environ["BEDROCK_AGENT_ID"]
ALIAS_ID    = ids.get("alias_id")  or __import__("os").environ["BEDROCK_AGENT_ALIAS_ID"]
LAMBDA_ROLE = ids.get("lambda_role_arn") or __import__("os").environ["LAMBDA_ROLE_ARN"]

lmb   = boto3.client("lambda", region_name=REGION)
apigw = boto3.client("apigatewayv2", region_name=REGION)

HANDLER_PATH = Path(__file__).parents[2] / "lambda" / "chatbot_handler.py"


def zip_lambda() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(str(HANDLER_PATH), "chatbot_handler.py")
    buf.seek(0)
    return buf.read()


def deploy_lambda() -> str:
    code = zip_lambda()
    try:
        func = lmb.create_function(
            FunctionName=config.CHATBOT_LAMBDA,
            Runtime="python3.12",
            Role=LAMBDA_ROLE,
            Handler="chatbot_handler.lambda_handler",
            Code={"ZipFile": code},
            Timeout=60,
            MemorySize=256,
            Environment={
                "Variables": {
                    "BEDROCK_AGENT_ID":       AGENT_ID,
                    "BEDROCK_AGENT_ALIAS_ID": ALIAS_ID,
                    "AWS_REGION_NAME":        REGION
                }
            }
        )
        func_arn = func["FunctionArn"]
        print(f"Lambda created: {func_arn}")
    except lmb.exceptions.ResourceConflictException:
        lmb.update_function_code(
            FunctionName=config.CHATBOT_LAMBDA,
            ZipFile=code
        )
        func_arn = lmb.get_function(
            FunctionName=config.CHATBOT_LAMBDA
        )["Configuration"]["FunctionArn"]
        print(f"Lambda updated: {func_arn}")
    # Wait for Lambda to be active
    time.sleep(5)
    return func_arn


def create_api(func_arn: str) -> str:
    api = apigw.create_api(
        Name=config.API_NAME,
        ProtocolType="HTTP",
        CorsConfiguration={
            "AllowOrigins": ["*"],
            "AllowMethods": ["POST"],
            "AllowHeaders": ["Content-Type"]
        }
    )
    api_id = api["ApiId"]

    integration = apigw.create_integration(
        ApiId=api_id,
        IntegrationType="AWS_PROXY",
        IntegrationUri=func_arn,
        PayloadFormatVersion="2.0"
    )
    apigw.create_route(
        ApiId=api_id,
        RouteKey="POST /chat",
        Target=f"integrations/{integration['IntegrationId']}"
    )
    apigw.create_stage(
        ApiId=api_id,
        StageName="$default",
        AutoDeploy=True
    )

    # Allow API Gateway to invoke Lambda
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    lmb.add_permission(
        FunctionName=config.CHATBOT_LAMBDA,
        StatementId="APIGatewayInvoke",
        Action="lambda:InvokeFunction",
        Principal="apigateway.amazonaws.com",
        SourceArn=(f"arn:aws:execute-api:{REGION}:{account_id}:"
                   f"{api_id}/*/*/chat")
    )

    endpoint = f"{api['ApiEndpoint']}/chat"
    print(f"API endpoint: {endpoint}")
    return endpoint


def main():
    func_arn = deploy_lambda()
    endpoint = create_api(func_arn)
    config.save_ids({"api_endpoint": endpoint})


if __name__ == "__main__":
    main()
