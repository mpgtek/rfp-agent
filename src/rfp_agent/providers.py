"""Provider-neutral task routing. HTTP adapters target YOUR normalized bridge.

No native Jev or GPT Decisions wire protocol is assumed or advertised as tested.
All external outputs can only downgrade deterministic approval decisions.
"""
from __future__ import annotations

import json
import os
import time
import tomllib
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class Generator(Protocol):
    def generate(self, question: str, evidence: list[dict]) -> dict: ...


class DecisionEngine(Protocol):
    def evaluate(self, question: str, evidence: list[dict], answer: str) -> dict: ...


class ExtractiveGenerator:
    def generate(self, question, evidence):
        return {"answer": evidence[0]["answer"] if evidence else "", "revision_ids": [evidence[0]["revision"]] if evidence else []}


class JsonBridge:
    """A documented local contract, not a vendor endpoint implementation."""
    def __init__(self, settings, operation, transport=None):
        self.settings, self.operation = settings, operation
        if not settings.get("allow_network", False):
            raise ValueError("External adapter requires allow_network=true for this task")
        endpoint = settings.get("endpoint", "")
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Set a valid explicit bridge endpoint without embedded credentials")
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Remote bridge endpoints must use HTTPS")
        if not settings.get("model"):
            raise ValueError("External task model is required")
        self.transport = transport or self._http

    def _http(self, payload):
        headers = {"Content-Type": "application/json"}
        env = self.settings.get("api_key_env")
        if env:
            if not os.environ.get(env):
                raise ValueError("Configured API key environment variable is absent")
            headers["Authorization"] = "Bearer " + os.environ[env]
        request = Request(self.settings["endpoint"], data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urlopen(request, timeout=self.settings.get("timeout_seconds", 30)) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("Provider response too large")
            return json.loads(raw)

    def call(self, question, evidence, answer=None):
        result = self.transport({"contract": "rfp-agent.bridge.v1", "operation": self.operation,
            "provider": self.settings["provider"], "model": self.settings["model"],
            "input": {"question": question, "evidence": evidence, "answer": answer},
            "max_output_tokens": self.settings.get("max_output_tokens", 800)})
        if not isinstance(result, dict):
            raise ValueError("Provider response must be an object")
        return result


class BridgeGenerator(JsonBridge):
    def generate(self, question, evidence):
        result = self.call(question, evidence)
        answer, ids = result.get("answer"), result.get("revision_ids")
        if not isinstance(answer, str) or not isinstance(ids, list) or not ids or any(type(i) is not int for i in ids):
            raise ValueError("Generation requires answer and integer revision_ids")
        allowed = {e["revision"]: e for e in evidence}
        if any(i not in allowed for i in ids):
            raise ValueError("Unknown evidence revision")
        # Strict extractive MVP: each paragraph must be a verbatim span from cited evidence.
        paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
        if not paragraphs or any(not any(p in allowed[i]["answer"] for i in ids) for p in paragraphs):
            raise ValueError("Unsupported generated prose; only cited verbatim evidence spans accepted")
        return result


class BridgeDecision(JsonBridge):
    def evaluate(self, question, evidence, answer):
        result = self.call(question, evidence, answer)
        if any(type(result.get(k)) is not bool for k in ("supported", "requires_review")):
            raise ValueError("Decision requires boolean supported and requires_review")
        return result


class JevDecisionAdapter(BridgeDecision):
    """Optional Jev bridge adapter. Native API connection NOT implemented/tested."""


class GPTDecisionsAdapter(BridgeDecision):
    """Optional GPT Decisions bridge adapter. Native API connection NOT implemented/tested."""


@dataclass
class TaskRouter:
    config: dict = field(default_factory=dict)
    calls: int = 0
    usage: list = field(default_factory=list)

    @classmethod
    def load(cls, path=None):
        if not path:
            return cls()
        with open(path, "rb") as f:
            config = tomllib.load(f)
        for name, settings in config.get("tasks", {}).items():
            if name not in {"answer_generation", "equivalence", "verification"}:
                raise ValueError(f"Unknown task {name}")
            if settings.get("provider", "extractive") not in {"extractive", "disabled", "json_bridge", "jev_bridge", "gpt_decisions_bridge"}:
                raise ValueError("Unknown provider; use the documented bridge contract")
            provider = settings.get("provider", "extractive" if name == "answer_generation" else "disabled")
            if name == "answer_generation" and provider in {"jev_bridge", "gpt_decisions_bridge"}:
                raise ValueError("Decision adapters cannot generate answers")
            if name != "answer_generation" and provider == "extractive":
                raise ValueError("Extractive is only an answer-generation provider")
            timeout = settings.get("timeout_seconds", 30)
            if not isinstance(timeout, (float, int)) or not 0 < timeout <= 120:
                raise ValueError("timeout_seconds must be between 0 and 120")
        budget = config.get("limits", {}).get("max_external_calls", 0)
        if type(budget) is not int or budget < 0:
            raise ValueError("max_external_calls must be a nonnegative integer")
        return cls(config)

    def _invoke(self, task, question, evidence, answer=None):
        settings = self.config.get("tasks", {}).get(task, {})
        provider = settings.get("provider", "extractive" if task == "answer_generation" else "disabled")
        if provider == "disabled":
            if task == "answer_generation":
                return ExtractiveGenerator().generate(question, evidence)
            return {"supported": True, "requires_review": False}
        if provider == "extractive":
            if task != "answer_generation":
                raise ValueError("Extractive provider is only valid for answer_generation")
            return ExtractiveGenerator().generate(question, evidence)
        if self.calls >= self.config.get("limits", {}).get("max_external_calls", 0):
            raise ValueError("External call budget exhausted")
        self.calls += 1
        started = time.monotonic()
        adapter = BridgeGenerator if task == "answer_generation" else {
            "jev_bridge": JevDecisionAdapter, "gpt_decisions_bridge": GPTDecisionsAdapter,
            "json_bridge": BridgeDecision}[provider]
        try:
            bridge = adapter(settings, task)
            return bridge.generate(question, evidence) if task == "answer_generation" else bridge.evaluate(question, evidence, answer)
        finally:
            self.usage.append({"task": task, "provider": provider, "model": settings.get("model"),
                               "elapsed_seconds": round(time.monotonic() - started, 4),
                               "cost_usd": None, "tokens": None})

    def generate(self, question, evidence):
        return self._invoke("answer_generation", question, evidence)

    def evaluate(self, task, question, evidence, answer):
        return self._invoke(task, question, evidence, answer)
