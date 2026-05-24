"""
Phase 1 — Step 1
Creates the IAM execution role for Bedrock Agent and Knowledge Base.
Run once before any other Phase 1 script.
"""
import json
import boto3
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[2]))
import config

iam = boto3.client("iam")
sts = boto3.client("sts", region_name=config.REGION)

def main():
    account_id = sts.get_caller_identity()["Account"]

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": account_id}
            }
        }]
    }

    try:
        role = iam.create_role(
            RoleName=config.ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for Bedrock Agent and Knowledge Base"
        )
        role_arn = role["Role"]["Arn"]
        print(f"Role created: {role_arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=config.ROLE_NAME)["Role"]["Arn"]
        print(f"Role already exists: {role_arn}")

    permissions = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeAgent",
                    "bedrock:Retrieve",
                    "bedrock:StartIngestionJob",
                    "bedrock:GetIngestionJob",
                    "bedrock:ListIngestionJobs"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::{config.S3_BUCKET_NAME}",
                    f"arn:aws:s3:::{config.S3_BUCKET_NAME}/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": ["aoss:APIAccessAll"],
                "Resource": "*"
            }
        ]
    }
    iam.put_role_policy(
        RoleName=config.ROLE_NAME,
        PolicyName="BedrockAgentPermissions",
        PolicyDocument=json.dumps(permissions)
    )
    print("Permissions attached.")
    config.save_ids({"role_arn": role_arn})

if __name__ == "__main__":
    main()
