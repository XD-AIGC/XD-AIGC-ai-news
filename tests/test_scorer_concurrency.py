"""Tests for AIScorer concurrency + client reuse (v2 backlog #1)."""

import asyncio
import json

import httpx
import pytest

from collectors.base import ContentItem, SourceType, Theme
from processor.scorer import AIScorer


def _make_item(idx: int, theme: Theme = Theme.AI) -> ContentItem:
    return ContentItem(
        id=str(idx),
        source_type=SourceType.RSS,
        title=f"Item {idx}",
        url=f"https://example.com/{idx}",
        content=f"content {idx}",
        theme=theme,
    )


def _ok_response_payload(score: float = 7.5) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "score": score,
                            "summary": "summary",
                            "categories": ["其他"],
                            "tags": ["t1"],
                            "reason": "ok",
                        }
                    )
                }
            }
        ]
    }


@pytest.mark.asyncio
async def test_process_items_runs_concurrently_under_semaphore(monkeypatch):
    """Items should run concurrently up to max_concurrent."""
    max_concurrent = 3
    in_flight = 0
    peak_in_flight = 0
    lock = asyncio.Lock()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak_in_flight
        async with lock:
            in_flight += 1
            peak_in_flight = max(peak_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return httpx.Response(200, json=_ok_response_payload())

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        AIScorer,
        "_build_client",
        lambda self: httpx.AsyncClient(transport=transport, timeout=5.0),
    )

    scorer = AIScorer({"api_key": "k", "max_concurrent": max_concurrent})
    items = [_make_item(i) for i in range(10)]
    await scorer.process_items(items)

    assert all(item.ai_score == 7.5 for item in items)
    assert peak_in_flight <= max_concurrent
    assert peak_in_flight == max_concurrent


@pytest.mark.asyncio
async def test_process_items_reuses_single_client(monkeypatch):
    """A single AsyncClient is built per process_items call, not per item."""
    build_count = 0

    def counting_build(self):
        nonlocal build_count
        build_count += 1
        return httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json=_ok_response_payload())
            ),
            timeout=5.0,
        )

    monkeypatch.setattr(AIScorer, "_build_client", counting_build)

    scorer = AIScorer({"api_key": "k", "max_concurrent": 5})
    items = [_make_item(i) for i in range(7)]
    await scorer.process_items(items)

    assert build_count == 1


@pytest.mark.asyncio
async def test_one_item_failure_does_not_break_others(monkeypatch):
    """A failing item is marked with score 0 / category 其他; others succeed."""

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_msg = body["messages"][1]["content"]
        if "Item 3" in user_msg:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, json=_ok_response_payload(score=8.0))

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        AIScorer,
        "_build_client",
        lambda self: httpx.AsyncClient(transport=transport, timeout=5.0),
    )

    scorer = AIScorer({"api_key": "k", "max_concurrent": 3})
    items = [_make_item(i) for i in range(5)]
    await scorer.process_items(items)

    failed = items[3]
    assert failed.ai_score == 0.0
    assert failed.ai_categories == ["其他"]

    for i, item in enumerate(items):
        if i == 3:
            continue
        assert item.ai_score == 8.0


@pytest.mark.asyncio
async def test_skip_already_scored_items(monkeypatch):
    """Items with ai_score already set are skipped (back-compat)."""
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_ok_response_payload())

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        AIScorer,
        "_build_client",
        lambda self: httpx.AsyncClient(transport=transport, timeout=5.0),
    )

    scorer = AIScorer({"api_key": "k", "max_concurrent": 3})
    items = [_make_item(i) for i in range(4)]
    items[0].ai_score = 9.0
    items[2].ai_score = 9.0
    await scorer.process_items(items, skip_scored=True)

    assert call_count == 2
    assert items[0].ai_score == 9.0
    assert items[2].ai_score == 9.0


@pytest.mark.asyncio
async def test_no_api_key_short_circuits(monkeypatch):
    """If api_key empty, no HTTP calls are made."""
    called = False

    def should_not_be_called(self):
        nonlocal called
        called = True
        raise AssertionError("client should not be built without api_key")

    monkeypatch.setattr(AIScorer, "_build_client", should_not_be_called)

    scorer = AIScorer({"api_key": ""})
    items = [_make_item(i) for i in range(3)]
    result = await scorer.process_items(items)

    assert called is False
    assert result is items
    assert all(item.ai_score is None for item in items)


def test_default_max_concurrent_is_5():
    scorer = AIScorer({"api_key": "k"})
    assert scorer.max_concurrent == 5


def test_max_concurrent_configurable():
    scorer = AIScorer({"api_key": "k", "max_concurrent": 10})
    assert scorer.max_concurrent == 10
