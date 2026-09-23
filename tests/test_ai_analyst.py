import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx2 as httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError

from backend.ai_analyst import AnalysisUnavailable, build_analysis_prompt, generate_analysis
from backend.calculator import calculate_plan, load_data


class AnalystTests(unittest.TestCase):
    def setUp(self):
        self.decisions = load_data()["test_example"]["selections"]
        self.result = calculate_plan(self.decisions)
        self.config_patch = patch("backend.ai_analyst._configuration", return_value=("test-key", "test-model"))
        self.config = self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.client_patch = patch("backend.ai_analyst.OpenAI")
        self.factory = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.client = self.factory.return_value.__enter__.return_value
        self.client.responses.create.return_value = SimpleNamespace(status="completed", output_text=" Разбор по данным ")

    def test_prompt_contains_facts_and_does_not_mutate(self):
        original = copy.deepcopy(self.result)
        payload = json.loads(build_analysis_prompt(self.decisions, self.result))
        self.assertEqual(payload["calculation"]["score_exact"], "56.54307")
        self.assertEqual(payload["calculation"]["budget_spent"], 95)
        self.assertEqual(len(payload["calculation"]["comparison"]), 50)
        self.assertEqual(payload["selected_measures"][3]["territory"], "Весь город")
        self.assertEqual(payload["calculation"]["applied_synergies"][0]["synergy_id"], "M10_M12")
        self.assertEqual(self.result, original)
        self.assertNotIn("test-key", json.dumps(payload))

    def test_success_uses_responses_api(self):
        self.assertEqual(generate_analysis(self.decisions, self.result), "Разбор по данным")
        self.factory.assert_called_once_with(api_key="test-key", base_url="https://api.openai.com/v1", timeout=30.0, max_retries=0)
        arguments = self.client.responses.create.call_args.kwargs
        self.assertEqual(arguments["model"], "test-model")
        self.assertFalse(arguments["store"])
        self.assertEqual(arguments["max_output_tokens"], 900)
        self.client.responses.create.assert_called_once()

    def test_missing_key_does_not_call_api(self):
        self.config.return_value = ("", "test-model")
        with self.assertRaisesRegex(AnalysisUnavailable, "OPENAI_API_KEY"):
            generate_analysis(self.decisions, self.result)
        self.factory.assert_not_called()

    def test_empty_or_incomplete_response(self):
        for status, text in (("completed", " "), ("incomplete", "Оборванный разбор"), ("failed", "")):
            with self.subTest(status=status):
                self.client.responses.create.return_value = SimpleNamespace(status=status, output_text=text)
                with self.assertRaisesRegex(AnalysisUnavailable, "полный разбор"):
                    generate_analysis(self.decisions, self.result)

    def test_api_errors_are_sanitized(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        errors = [
            AuthenticationError("secret-marker", response=httpx.Response(401, request=request), body=None),
            RateLimitError("secret-marker", response=httpx.Response(429, request=request), body=None),
            APIStatusError("secret-marker", response=httpx.Response(500, request=request), body=None),
            APIConnectionError(message="secret-marker", request=request),
            APITimeoutError(request=request),
        ]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.client.responses.create.side_effect = error
                with self.assertRaises(AnalysisUnavailable) as raised:
                    generate_analysis(self.decisions, self.result)
                self.assertNotIn("secret-marker", str(raised.exception))
                self.assertNotIn("test-key", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
