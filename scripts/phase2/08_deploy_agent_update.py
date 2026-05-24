"""
Phase 2 — Step 8
Updates the Bedrock Agent with a new instruction, prepares it,
creates a new immutable version, and promotes the 'production'
alias to that version. Run after editing bedrock/instruction.txt.
Includes a rollback() helper.
"""
import sys
import time
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION   = config.REGION
ids      = config.load_ids()
AGENT_ID = ids.get("agent_id") or __import__("os").environ["BEDROCK_AGENT_ID"]
ALIAS_ID = ids.get("alias_id") or __import__("os").environ["BEDROCK_AGENT_ALIAS_ID"]
ROLE_ARN = ids.get("role_arn") or __import__("os").environ["BEDROCK_ROLE_ARN"]

bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)


def wait_for_agent(target_status: str, timeout_s: int = 120):
    for _ in range(timeout_s // 8):
        status = bedrock_agent.get_agent(agentId=AGENT_ID)[
            "agent"]["agentStatus"]
        print(f"  Agent status: {status}")
        if status == target_status:
            return
        time.sleep(8)
    raise TimeoutError(f"Agent did not reach {target_status}")


def deploy():
    instruction = config.load_instruction()

    # 1. Update DRAFT
    bedrock_agent.update_agent(
        agentId=AGENT_ID,
        agentName=config.AGENT_NAME,
        foundationModel=config.FOUNDATION_MODEL,
        instruction=instruction,
        agentResourceRoleArn=ROLE_ARN,
        idleSessionTTLInSeconds=1800
    )
    print("DRAFT updated.")

    # 2. Prepare
    bedrock_agent.prepare_agent(agentId=AGENT_ID)
    wait_for_agent("PREPARED")

    # 3. New version
    version_resp = bedrock_agent.create_agent_version(agentId=AGENT_ID)
    new_version  = version_resp["agentVersion"]["agentVersion"]
    print(f"New version: {new_version}")

    # 4. Promote alias
    bedrock_agent.update_agent_alias(
        agentId=AGENT_ID,
        agentAliasId=ALIAS_ID,
        agentAliasName=config.AGENT_ALIAS_NAME,
        routingConfiguration=[{"agentVersion": new_version}]
    )
    print(f"Production alias → version {new_version}")
    return new_version


def rollback(target_version: str):
    """Roll the production alias back to a previous version."""
    bedrock_agent.update_agent_alias(
        agentId=AGENT_ID,
        agentAliasId=ALIAS_ID,
        agentAliasName=config.AGENT_ALIAS_NAME,
        routingConfiguration=[{"agentVersion": target_version}]
    )
    print(f"Rolled back to version {target_version}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback-to", help="Roll back to this version number")
    args = parser.parse_args()

    if args.rollback_to:
        rollback(args.rollback_to)
    else:
        deploy()
