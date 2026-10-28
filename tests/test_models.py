from io import BytesIO
import json
import os
import unittest
from unittest.mock import Mock, patch
import urllib.error

from crashlab.models import catalogue_summary, list_nvidia_models
from crashlab.provider import ProviderError


class ModelsTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"NEBIUS_API_KEY": "catalogue-test-key", "NEBIUS_MODEL": "nvidia/model-a"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_lists_only_safe_nvidia_ids_and_checks_configured_model(self):
        body = {"data": [{"id": "nvidia/model-a"}, {"id": "nvidia/model-a"}, {"id": "other/model"},
                         {"id": "nvidia/invalid\nline"}, {"id": 5}, None]}
        opener = Mock()
        opener.open.return_value = BytesIO(json.dumps(body).encode())
        with patch("crashlab.models.urllib.request.build_opener", return_value=opener):
            result = catalogue_summary()
        self.assertEqual(result["nvidia_models"], ["nvidia/model-a"])
        self.assertTrue(result["configured_model_available"])
        self.assertEqual(result["inference_requests"], 0)
        self.assertNotIn("catalogue-test-key", json.dumps(result))
        self.assertEqual(opener.open.call_args.args[0].full_url, "https://api.tokenfactory.nebius.com/v1/models")

    def test_missing_key_does_not_make_request(self):
        with patch.dict(os.environ, {"NEBIUS_API_KEY": ""}), \
                patch("crashlab.models.urllib.request.build_opener") as request:
            with self.assertRaises(ProviderError):
                list_nvidia_models()
        request.assert_not_called()

    def test_auth_error_does_not_include_provider_body(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://api.tokenfactory.nebius.com/v1/models",
                                                        401, "unauthorized", {}, BytesIO(b"private-body"))
        with patch("crashlab.models.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError) as error:
                list_nvidia_models()
        self.assertIn("HTTP 401", str(error.exception))
        self.assertNotIn("private-body", str(error.exception))
