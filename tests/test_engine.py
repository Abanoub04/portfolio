"""Tests for the agent engine and the action log (Stage 2).

They always use the fake model, so no API key is needed and nothing is paid.
Run from the project root with:   python -m unittest -v
"""

import os
import tempfile
import unittest
from unittest import mock

import config
from agents.action_log import ActionLog
from agents.base_agent import Agent, AgentError
from agents.models import FakeModel, RealModel, create_model
from tools.demo_tools import COUNT_ROWS_TOOL


def add_numbers(a, b):
    return a + b


ADD_TOOL = {
    "name": "add_numbers",
    "description": "Add two numbers.",
    "input_schema": {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
    "function": add_numbers,
}


# Remove the API key for every test, so the fake model is always used.
@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        # Write logs to a temporary folder, not to the real logs/ folder.
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log = ActionLog(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_agent(self, script, tools=(ADD_TOOL,)):
        return Agent("Tester", "You are a test agent.", list(tools), self.log, fake_script=script)

    def log_text(self):
        return self.log.path.read_text(encoding="utf-8")

    def test_tool_is_called_and_result_goes_back_to_model(self):
        agent = self.make_agent([
            {"tool": "add_numbers", "input": {"a": 2, "b": 3}},
            {"text": "The answer is 5."},
        ])
        answer = agent.run("What is 2 + 3?")

        self.assertEqual(answer, "The answer is 5.")
        # On its second call, the model must have received the tool result "5".
        second_call = agent.model.received[1]
        tool_result = second_call[-1]["content"][0]
        self.assertEqual(tool_result["type"], "tool_result")
        self.assertEqual(tool_result["content"], "5")
        self.assertEqual(tool_result["tool_use_id"], "fake_call_1")

    def test_every_action_is_logged(self):
        agent = self.make_agent([
            {"tool": "add_numbers", "input": {"a": 1, "b": 1}},
            {"text": "Done."},
        ])
        agent.run("Add 1 and 1.")

        log = self.log_text()
        for action in ["START", "TOOL CALL", "TOOL RESULT", "FINISH"]:
            self.assertIn(f"| {action}", log)
        self.assertIn("Tester", log)
        self.assertIn('add_numbers {"a": 1, "b": 1}', log)

    def test_unknown_tool_is_reported_not_crashed(self):
        agent = self.make_agent([
            {"tool": "delete_everything", "input": {}},
            {"text": "OK, I can't do that."},
        ])
        answer = agent.run("Try a tool that doesn't exist.")

        self.assertEqual(answer, "OK, I can't do that.")
        tool_result = agent.model.received[1][-1]["content"][0]
        self.assertTrue(tool_result["is_error"])
        self.assertIn("Unknown tool", tool_result["content"])
        self.assertIn("| TOOL ERROR", self.log_text())

    def test_failing_tool_is_reported_not_crashed(self):
        agent = self.make_agent(
            [{"tool": "count_rows", "input": {"file_name": "missing.csv"}}, {"text": "File not found."}],
            tools=[COUNT_ROWS_TOOL],
        )
        agent.run("Count rows in missing.csv")

        tool_result = agent.model.received[1][-1]["content"][0]
        self.assertTrue(tool_result["is_error"])
        self.assertIn("FileNotFoundError", tool_result["content"])

    def test_demo_tool_cannot_leave_data_folder(self):
        with self.assertRaises(FileNotFoundError):
            COUNT_ROWS_TOOL["function"]("../config.py")

    def test_demo_tool_counts_rows(self):
        self.assertEqual(COUNT_ROWS_TOOL["function"]("budget.csv"), {"file": "budget.csv", "rows": 7})

    def test_safety_brake_stops_endless_loop(self):
        endless = [{"tool": "add_numbers", "input": {"a": 1, "b": 1}}] * (config.MAX_STEPS + 5)
        agent = self.make_agent(endless)

        with self.assertRaises(AgentError):
            agent.run("Keep going forever.")
        self.assertIn("| ERROR", self.log_text())


class ModelChoiceTests(unittest.TestCase):
    def test_fake_model_without_api_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertIsInstance(create_model(), FakeModel)

    def test_real_model_with_api_key(self):
        # Only creates the client - no API call is made.
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-not-real"}):
            self.assertIsInstance(create_model(), RealModel)


if __name__ == "__main__":
    unittest.main()
