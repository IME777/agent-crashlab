from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch
import urllib.error

from crashlab.provider import ProviderError, submit_patch
from crashlab.tasks import get_task


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.task = get_task("capped-backoff")
        self.env = patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key-not-real", "NEBIUS_MODEL": "nvidia/test-model"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def response(self, *, usage=True, valid=True):
        result = {"model": "nvidia/test-model", "choices": [{"message": {"tool_calls":
                  [{"function": {"name": "submit_patch", "arguments": json.dumps({"source": self.task["solution"]})}}]
                  if valid else []}}]}
        if usage:
            result["usage"] = {"prompt_tokens": 123, "completion_tokens": 45}
        return BytesIO(json.dumps(result).encode())

    def test_real_request_contract_has_no_fixture_solution_or_acceptance_tests(self):
        with patch("crashlab.provider.urllib.request.urlopen", return_value=self.response()) as call:
            result = submit_patch(self.task, {}, "nebius")
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.tokenfactory.nebius.com/v1/chat/completions")
        self.assertEqual(payload["model"], "nvidia/test-model")
        self.assertEqual(payload["tool_choice"]["function"]["name"], "submit_patch")
        self.assertIn("ALL attribute access and object method calls are rejected", payload["messages"][1]["content"])
        self.assertNotIn(self.task["solution"], json.dumps(payload))
        self.assertNotIn(self.task["tests"], json.dumps(payload))
        self.assertTrue(result["live"])
        self.assertEqual(result["input_tokens"], 123)
        self.assertEqual(result["output_tokens"], 45)

    def test_missing_usage_is_explicitly_unknown(self):
        with patch("crashlab.provider.urllib.request.urlopen", return_value=self.response(usage=False)):
            result = submit_patch(self.task, {}, "nebius")
        self.assertFalse(result["usage_known"])
        self.assertEqual(result["input_tokens"], 0)

    def test_invalid_tool_response_preserves_known_token_usage(self):
        with patch("crashlab.provider.urllib.request.urlopen", return_value=self.response(valid=False)):
            with self.assertRaises(ProviderError) as error:
                submit_patch(self.task, {}, "nebius")
        self.assertEqual(error.exception.usage, {"input_tokens": 123, "output_tokens": 45})

    def test_http_error_is_retryable_and_does_not_log_body_or_credentials(self):
        error = urllib.error.HTTPError("https://api.tokenfactory.nebius.com", 429, "rate limit",
                                       {"Retry-After": "500"}, BytesIO(b"sensitive-provider-body"))
        with patch("crashlab.provider.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ProviderError) as failure:
                submit_patch(self.task, {}, "nebius")
        self.assertTrue(failure.exception.retryable)
        self.assertEqual(failure.exception.retry_after, 10)
        self.assertNotIn("sensitive-provider-body", str(failure.exception))
        self.assertNotIn("test-key-not-real", str(failure.exception))

    def test_auth_failure_does_not_retry(self):
        error = urllib.error.HTTPError("https://api.tokenfactory.nebius.com", 401, "auth", {}, None)
        with patch("crashlab.provider.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ProviderError) as failure:
                submit_patch(self.task, {}, "nebius")
        self.assertFalse(failure.exception.retryable)

    def test_invalid_json_is_a_provider_failure(self):
        with patch("crashlab.provider.urllib.request.urlopen", return_value=BytesIO(b"invalid")):
            with self.assertRaises(ProviderError):
                submit_patch(self.task, {}, "nebius")

    def test_fixture_never_calls_remote_provider(self):
        with patch("crashlab.provider.urllib.request.urlopen") as call:
            result = submit_patch(self.task, {}, "fixture")
        call.assert_not_called()
        self.assertFalse(result["live"])

    def test_run_model_is_pinned_even_if_environment_changes(self):
        with patch("crashlab.provider.urllib.request.urlopen", return_value=self.response()) as call:
            submit_patch(self.task, {}, "nebius", model="nvidia/pinned-model")
        self.assertEqual(json.loads(call.call_args.args[0].data)["model"], "nvidia/pinned-model")


if __name__ == "__main__":
    unittest.main()
