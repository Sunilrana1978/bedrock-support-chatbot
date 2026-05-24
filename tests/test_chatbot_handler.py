"""
Unit tests for the chatbot Lambda handler.
Run with: pytest tests/
"""
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Stub boto3 before importing the handler
boto3_mock = MagicMock()
sys.modules.setdefault("boto3", boto3_mock)

import importlib
import os

os.environ["BEDROCK_AGENT_ID"]       = "test-agent-id"
os.environ["BEDROCK_AGENT_ALIAS_ID"] = "test-alias-id"
os.environ["AWS_REGION_NAME"]        = "us-east-1"


class TestChatbotHandler(unittest.TestCase):

    def _make_event(self, message: str, session_id: str = "sess-1") -> dict:
        return {"body": json.dumps({"message": message, "session_id": session_id})}

    def test_missing_message_returns_400(self):
        import lambda.chatbot_handler as handler
        with patch.object(handler, "runtime", MagicMock()):
            result = handler.lambda_handler({"body": "{}"}, None)
        self.assertEqual(result["statusCode"], 400)

    def test_successful_response(self):
        import lambda.chatbot_handler as handler
        mock_runtime = MagicMock()
        mock_runtime.invoke_agent.return_value = {
            "completion": [
                {"chunk": {"bytes": b"Check the connection pool settings."}},
                {"chunk": {"bytes": b" Restart the service after."}}
            ]
        }
        with patch.object(handler, "runtime", mock_runtime):
            result = handler.lambda_handler(
                self._make_event("DB timeout — what should I check?"), None
            )
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertIn("connection pool", body["response"])
        self.assertEqual(body["session_id"], "sess-1")

    def test_agent_error_returns_500(self):
        import lambda.chatbot_handler as handler
        mock_runtime = MagicMock()
        mock_runtime.invoke_agent.side_effect = Exception("Throttled")
        with patch.object(handler, "runtime", mock_runtime):
            result = handler.lambda_handler(
                self._make_event("Any question"), None
            )
        self.assertEqual(result["statusCode"], 500)


if __name__ == "__main__":
    unittest.main()
