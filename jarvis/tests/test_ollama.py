"""
Tests for OllamaClient.

The client has two methods:
  - chat(messages)       — synchronous, uses requests.post (imported lazily inside chat())
  - chat_stream(messages) — async, uses httpx

Because 'import requests' lives *inside* the chat() method body, we must patch
'requests.post' at the top-level requests module, not inside ollama_client.
"""
import unittest
from unittest.mock import patch, MagicMock
import requests
from jarvis.models.ollama_client import OllamaClient


class TestOllamaClientChat(unittest.TestCase):
    """Tests for the synchronous chat() method."""

    @patch('requests.post')
    def test_chat_success(self, mock_post):
        """A successful Ollama response should be returned as a plain string."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello, I am JARVIS."}
        }
        mock_post.return_value = mock_response

        client = OllamaClient()
        messages = [
            {"role": "system", "content": "You are JARVIS."},
            {"role": "user", "content": "Hello"},
        ]
        response = client.chat(messages)

        self.assertEqual(response, "Hello, I am JARVIS.")
        mock_post.assert_called_once_with(
            "http://localhost:11434/api/chat",
            json={"model": client.model, "messages": messages, "stream": False},
            timeout=120,
        )

    @patch('requests.post')
    def test_chat_connection_error_raises_runtime_error(self, mock_post):
        """A network failure should raise a RuntimeError with a helpful message."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        client = OllamaClient()
        messages = [{"role": "user", "content": "Hello"}]

        with self.assertRaises(RuntimeError) as ctx:
            client.chat(messages)

        self.assertIn("Ollama", str(ctx.exception))

    @patch('requests.post')
    def test_chat_returns_empty_string_if_no_content_key(self, mock_post):
        """If Ollama returns a response without a 'content' key, we get an empty string."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {}}
        mock_post.return_value = mock_response

        client = OllamaClient()
        result = client.chat([{"role": "user", "content": "ping"}])
        self.assertEqual(result, "")

    @patch('requests.post')
    def test_chat_http_error_raises_runtime_error(self, mock_post):
        """An HTTP error status should bubble up as a RuntimeError."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("503")
        mock_post.return_value = mock_response

        client = OllamaClient()
        with self.assertRaises(RuntimeError):
            client.chat([{"role": "user", "content": "hello"}])


class TestOllamaClientDefaults(unittest.TestCase):
    """Tests for OllamaClient configuration."""

    def test_default_base_url(self):
        client = OllamaClient()
        self.assertEqual(client.base_url, "http://localhost:11434")

    def test_custom_base_url(self):
        client = OllamaClient(base_url="http://my-server:11434")
        self.assertEqual(client.base_url, "http://my-server:11434")

    def test_model_comes_from_settings(self):
        """Model name should be taken from settings.local_model."""
        from jarvis.config import settings
        client = OllamaClient()
        self.assertEqual(client.model, settings.local_model)


if __name__ == "__main__":
    unittest.main()
