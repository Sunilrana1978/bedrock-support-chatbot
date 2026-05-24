"""
Phase 1 — Step 4
Creates the Bedrock Agent, associates the Knowledge Base,
prepares it, snapshots a version, and creates the 'production' alias.
"""
import time
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION = config.REGION
ids    = config.load_ids()
ROLE_ARN = ids.get("role_arn") or __import__("os").environ["BEDROCK_ROLE_ARN"]
KB_ID    = ids.get("kb_id")   or __import__("os").environ["BEDROCK_KB_ID"]

bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)


def wait_for_agent(agent_id: str, target_status: str, timeout_s: int = 120):
    for _ in range(timeout_s // 8):
        status = bedrock_agent.get_agent(agentId=agent_id)[
            "agent"]["agentStatus"]
        print(f"  Agent status: {status}")
        if status == target_status:
            return
        if status in ("FAILED", "DELETING"):
            raise RuntimeError(f"Unexpected agent status: {status}")
        time.sleep(8)
    raise TimeoutError(f"Agent did not reach {target_status} within {timeout_s}s")


def main():
    instruction = config.load_instruction()

    # 1. Create agent
    print("Creating Bedrock Agent...")
    agent = bedrock_agent.create_agent(
        agentName=config.AGENT_NAME,
        foundationModel=config.FOUNDATION_MODEL,
        instruction=instruction,
        agentResourceRoleArn=ROLE_ARN,
        idleSessionTTLInSeconds=1800,
        description="Production support incident triage and resolution assistant"
    )
    agent_id = agent["agent"]["agentId"]
    print(f"Agent ID: {agent_id}")

    # 2. Associate Knowledge Base
    bedrock_agent.associate_agent_knowledge_base(
        agentId=agent_id,
        agentVersion="DRAFT",
        knowledgeBaseId=KB_ID,
        description="Production support documentation and incident history",
        knowledgeBaseState="ENABLED"
    )
    print("Knowledge Base associated.")

    # 3. Prepare
    bedrock_agent.prepare_agent(agentId=agent_id)
    wait_for_agent(agent_id, "PREPARED")

    # 4. Create versioned snapshot
    version_resp = bedrock_agent.create_agent_version(agentId=agent_id)
    version_num  = version_resp["agentVersion"]["agentVersion"]
    print(f"Agent version: {version_num}")

    # 5. Create 'production' alias
    alias = bedrock_agent.create_agent_alias(
        agentId=agent_id,
        agentAliasName=config.AGENT_ALIAS_NAME,
        routingConfiguration=[{"agentVersion": version_num}]
    )
    alias_id = alias["agentAlias"]["agentAliasId"]
    print(f"Alias ID: {alias_id}")

    config.save_ids({"agent_id": agent_id, "alias_id": alias_id})
    print("Done — Agent ready.")


if __name__ == "__main__":
    main()
