"""
Utility — creates the Lambda execution role needed by both Lambda functions.
Run before Phase 1 Step 5.
"""
import json
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

iam = boto3.client("iam")


def main():
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        role = iam.create_role(
            RoleName=config.LAMBDA_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Execution role for Bedrock chatbot and ingestion Lambdas"
        )
        role_arn = role["Role"]["Arn"]
        print(f"Lambda role created: {role_arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=config.LAMBDA_ROLE_NAME)["Role"]["Arn"]
        print(f"Lambda role already exists: {role_arn}")

    # Attach AWS-managed policies
    for policy_arn in [
        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    ]:
        iam.attach_role_policy(RoleName=config.LAMBDA_ROLE_NAME, PolicyArn=policy_arn)

    # Inline policy for Bedrock and CloudWatch
    inline = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeAgent",
                    "bedrock:StartIngestionJob",
                    "bedrock:GetIngestionJob",
                    "bedrock:ListIngestionJobs"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": ["cloudwatch:PutMetricData"],
                "Resource": "*"
            }
        ]
    }
    iam.put_role_policy(
        RoleName=config.LAMBDA_ROLE_NAME,
        PolicyName="LambdaBedrockAccess",
        PolicyDocument=json.dumps(inline)
    )
    print("Policies attached.")
    config.save_ids({"lambda_role_arn": role_arn})


if __name__ == "__main__":
    main()
