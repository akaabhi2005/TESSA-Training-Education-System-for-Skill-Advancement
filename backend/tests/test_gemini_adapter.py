"""Provider-boundary tests using fakes: no network or real keys required."""

from __future__ import annotations

import json
from types import SimpleNamespace

from pydantic import BaseModel

from app import llm


class _Answer(BaseModel):
    answer: str


class _Models:
    def __init__(self):
        self.generate_calls: list[dict] = []
        self.stream_calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.generate_calls.append(kwargs)
        return SimpleNamespace(text='{"answer":"grounded"}')

    def generate_content_stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        return iter([SimpleNamespace(text="first "), SimpleNamespace(text="second")])


def _install_fake_client(monkeypatch):
    models = _Models()
    client = SimpleNamespace(models=models)
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_get_client", lambda: client)
    # Pin the pool to SDK-served names. The real graph pool leads with a routed
    # model, and a provider test that quietly reached the gateway would be
    # testing the network rather than this adapter.
    monkeypatch.setattr(llm, "_models_for", lambda _: ("gemini-test", "gemini-test-fallback"))
    return models


def test_parse_uses_json_schema_and_cache(tmp_path, monkeypatch):
    models = _install_fake_client(monkeypatch)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)

    first = llm.parse(_Answer, "prompt", "system")
    second = llm.parse(_Answer, "prompt", "system")

    assert first == _Answer(answer="grounded")
    assert second == first
    assert len(models.generate_calls) == 1
    config = models.generate_calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["type"] == "object"


def test_stream_maps_assistant_to_gemini_model_role(monkeypatch):
    models = _install_fake_client(monkeypatch)

    chunks = list(
        llm.stream_text(
            [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
            "system",
        )
    )

    # Fragments are yielded exactly as the model produced them - the space
    # after "first" is the gap between two words, not padding to trim.
    assert chunks == ["first ", "second"]
    assert "".join(chunks) == "first second"
    assert models.stream_calls[0]["contents"] == [
        {"role": "user", "parts": [{"text": "hello"}]},
        {"role": "model", "parts": [{"text": "hi"}]},
    ]


def test_parse_uses_another_model_when_the_first_is_busy(tmp_path, monkeypatch):
    models = _install_fake_client(monkeypatch)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "_model_cooldowns", {})
    monkeypatch.setattr(llm, "_disabled_models", set())
    monkeypatch.setattr(llm, "_model_order", lambda *_: ("busy-model", "fallback-model"))

    def busy_then_success(**kwargs):
        models.generate_calls.append(kwargs)
        if len(models.generate_calls) == 1:
            raise RuntimeError("503 UNAVAILABLE: high demand")
        return SimpleNamespace(text='{"answer":"grounded"}')

    monkeypatch.setattr(models, "generate_content", busy_then_success)

    assert llm.parse(_Answer, "new prompt", "system") == _Answer(answer="grounded")
    assert [call["model"] for call in models.generate_calls] == ["busy-model", "fallback-model"]
    assert "busy-model" in llm._model_cooldowns


def test_model_specific_403_does_not_disable_all_gemini_requests(monkeypatch):
    models = _install_fake_client(monkeypatch)
    monkeypatch.setattr(llm, "_client_failed", False)
    monkeypatch.setattr(llm, "_model_cooldowns", {})
    monkeypatch.setattr(llm, "_disabled_models", set())
    monkeypatch.setattr(llm, "_models_for", lambda _: ("restricted-model", "working-model"))

    assert llm._record_failure("restricted-model", RuntimeError("403 permission denied"), "test")
    assert not llm._client_failed
    assert llm._model_order("graph", "any request") == ("working-model",)


def test_streamed_chunks_keep_the_spaces_between_them():
    """A chunk boundary on a space must not eat the space.

    Stripping each streamed fragment produced "The firstcourse in your path"
    in the assistant panel.
    """
    from app import llm

    class _Chunk:
        def __init__(self, text):
            self.text = text

    joined = "".join(
        llm._response_text(_Chunk(part), strip=False)
        for part in ["The first", " course", " in your path", " covers Docker", " & Azure."]
    )
    assert joined == "The first course in your path covers Docker & Azure."
    # A complete response is still tidied.
    assert llm._response_text(_Chunk("  answer  ")) == "answer"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self, *args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_fake_gateway(monkeypatch, handler):
    """Route the gateway's HTTP call to ``handler`` instead of the network."""
    monkeypatch.setattr(llm.settings, "airouter_api_key", "test-key")
    monkeypatch.setattr(llm.urllib.request, "urlopen", handler)


def test_routed_model_asks_for_json_and_bounded_reasoning(tmp_path, monkeypatch):
    """The gateway serves reasoning models, and both bounds are load-bearing.

    Without a JSON response format they answer with fenced prose, and without a
    pinned effort they spend minutes thinking - either one fails the build
    inside a 60s function.
    """
    models = _install_fake_client(monkeypatch)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "_models_for", lambda _: ("vendor/routed-model",))

    sent: list[dict] = []

    def handler(request, timeout=None):
        sent.append({"body": json.loads(request.data), "timeout": timeout, "url": request.full_url})
        return _FakeResponse({"choices": [{"message": {"content": '{"answer":"grounded"}'}}]})

    _install_fake_gateway(monkeypatch, handler)

    assert llm.parse(_Answer, "prompt", "system") == _Answer(answer="grounded")
    assert not models.generate_calls, "a routed model must not touch the Gemini SDK"

    body = sent[0]["body"]
    assert body["model"] == "vendor/routed-model"
    assert body["response_format"]["json_schema"]["schema"]["type"] == "object"
    assert body["reasoning_effort"] == "minimal"
    # The caller's budget describes the answer; thinking is billed on top of it.
    assert body["max_tokens"] > 1600
    assert sent[0]["timeout"] == llm.settings.airouter_timeout


def test_rejected_gateway_key_falls_back_to_gemini(tmp_path, monkeypatch):
    """An exhausted gateway balance is a billing problem, not an outage."""
    models = _install_fake_client(monkeypatch)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "_client_failed", False)
    monkeypatch.setattr(llm, "_model_cooldowns", {})
    monkeypatch.setattr(llm, "_disabled_models", set())
    monkeypatch.setattr(llm, "_models_for", lambda _: ("vendor/routed-model", "gemini-test"))

    def handler(request, timeout=None):
        raise llm.urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    _install_fake_gateway(monkeypatch, handler)

    assert llm.parse(_Answer, "prompt", "system") == _Answer(answer="grounded")
    assert [call["model"] for call in models.generate_calls] == ["gemini-test"]
    assert "vendor/routed-model" in llm._disabled_models
    assert not llm._client_failed


def test_slow_gateway_cools_down_instead_of_retrying(tmp_path, monkeypatch):
    """A timeout is spent twice if the model stays in rotation: 15s, then 15s."""
    _install_fake_client(monkeypatch)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "_model_cooldowns", {})
    monkeypatch.setattr(llm, "_disabled_models", set())
    monkeypatch.setattr(llm, "_models_for", lambda _: ("vendor/routed-model", "gemini-test"))

    def handler(request, timeout=None):
        raise TimeoutError("The read operation timed out")

    _install_fake_gateway(monkeypatch, handler)

    assert llm.parse(_Answer, "prompt", "system") == _Answer(answer="grounded")
    assert "vendor/routed-model" in llm._model_cooldowns


def test_graph_pool_prefers_its_first_model_rather_than_rotating(monkeypatch):
    """The graph pool is ranked; the fast pool is interchangeable."""
    monkeypatch.setattr(llm, "_model_cooldowns", {})
    monkeypatch.setattr(llm, "_disabled_models", set())
    monkeypatch.setattr(llm, "_models_for", lambda _: ("ranked-first", "fallback-a", "fallback-b"))

    assert llm._model_order("graph", "any goal") == ("ranked-first", "fallback-a", "fallback-b")
    assert llm._model_order("graph", "another goal") == ("ranked-first", "fallback-a", "fallback-b")
    assert {llm._model_order("fast", f"request {n}")[0] for n in range(24)} != {"ranked-first"}


def test_routed_models_drop_out_without_a_gateway_key(monkeypatch):
    monkeypatch.setattr(llm.settings, "airouter_api_key", None)
    monkeypatch.setattr(llm.settings, "graph_models", "vendor/routed-model,gemini-a")
    monkeypatch.setattr(llm.settings, "model", "gemini-a")

    assert llm._models_for("graph") == ("gemini-a",)
