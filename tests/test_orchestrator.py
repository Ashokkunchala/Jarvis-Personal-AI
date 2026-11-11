from __future__ import annotations

import asyncio

import pytest

from jarvis.tools.orchestrator import ToolTask, ToolTaskOrchestrator
from jarvis.tools.registry import Risk, Tool, ToolRegistry


def _register(registry: ToolRegistry, name, handler, risk=Risk.SAFE):
    registry.register(Tool(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        handler=handler,
        risk=risk,
    ))


def test_task_plan_obeys_dependencies_and_emits_verified_results():
    async def scenario():
        registry = ToolRegistry()
        state = []

        async def first():
            state.append("first")
            return {"success": True, "value": 7}

        async def second():
            assert state == ["first"]
            state.append("second")
            return {"success": True, "value": 9}

        _register(registry, "first", first)
        _register(registry, "second", second)
        events = []
        results = await ToolTaskOrchestrator(registry).run(
            [ToolTask("second-step", "second", depends_on=("first-step",)),
             ToolTask("first-step", "first")],
            on_event=events.append,
        )
        assert results["first-step"].ok
        assert results["second-step"].ok
        assert state == ["first", "second"]
        assert [e["type"] for e in events].count("task_start") == 2
        assert all(e.get("success", True) for e in events if e["type"] == "task_end")

    asyncio.run(scenario())


def test_read_only_tasks_run_with_bounded_parallelism():
    async def scenario():
        registry = ToolRegistry()
        active = 0
        maximum = 0
        lock = asyncio.Lock()

        async def read():
            nonlocal active, maximum
            async with lock:
                active += 1
                maximum = max(maximum, active)
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1
            return {"success": True}

        for index in range(6):
            _register(registry, f"read_{index}", read)
        tasks = [ToolTask(str(i), f"read_{i}") for i in range(6)]
        results = await ToolTaskOrchestrator(registry, max_parallel=2).run(tasks)
        assert all(result.ok for result in results.values())
        assert maximum == 2

    asyncio.run(scenario())


def test_failed_dependency_skips_downstream_and_cycles_fail_before_actions():
    async def scenario():
        registry = ToolRegistry()
        calls = []

        async def fail():
            calls.append("fail")
            return {"success": False, "error": "no"}

        async def downstream():
            calls.append("downstream")
            return {"success": True}

        _register(registry, "fail", fail)
        _register(registry, "downstream", downstream)
        events = []
        result = await ToolTaskOrchestrator(registry).run(
            [ToolTask("a", "fail"), ToolTask("b", "downstream", depends_on=("a",))],
            on_event=events.append,
        )
        assert result["a"].ok is False
        assert result["b"].ok is False
        assert calls == ["fail"]
        assert any(event["type"] == "task_skipped" for event in events)
        with pytest.raises(ValueError, match="cycle"):
            await ToolTaskOrchestrator(registry).run(
                [ToolTask("x", "downstream", depends_on=("y",)),
                 ToolTask("y", "downstream", depends_on=("x",))]
            )
        assert calls == ["fail"]

    asyncio.run(scenario())


def test_retries_are_limited_to_transient_safe_actions():
    async def scenario():
        registry = ToolRegistry()
        attempts = 0

        async def unstable_read():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {"success": False, "error": "503 temporarily unavailable"}
            return {"success": True, "value": "recovered"}

        _register(registry, "unstable_read", unstable_read)
        events = []
        result = await ToolTaskOrchestrator(registry).run(
            [ToolTask("read", "unstable_read", retries=1)], on_event=events.append
        )
        assert result["read"].ok
        assert attempts == 2
        assert any(event["type"] == "task_retry" for event in events)

        _register(registry, "mutate", lambda: {"success": True}, risk=Risk.MEDIUM)
        with pytest.raises(ValueError, match="SAFE"):
            await ToolTaskOrchestrator(registry).run(
                [ToolTask("mutation", "mutate", retries=1)]
            )

    asyncio.run(scenario())


def test_brain_executes_safe_model_tool_batch_through_orchestrator():
    async def scenario():
        from jarvis.core.brain import JarvisBrain, TurnStats

        registry = ToolRegistry()
        active = 0
        maximum = 0
        lock = asyncio.Lock()

        async def read(value=0):
            nonlocal active, maximum
            async with lock:
                active += 1
                maximum = max(maximum, active)
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1
            return {"success": True, "value": value}

        _register(registry, "read", read)
        brain = JarvisBrain(api_key="schema-only")
        brain.registry = registry
        output = []
        results = []
        async for event in brain._execute_calls(
            [{"name": "read", "args": {"value": n}} for n in range(5)],
            confirm=None,
            auto_approve=False,
            stats=TurnStats(),
            results=results,
        ):
            output.append(event)
        assert maximum > 1
        assert [name for name, payload in results] == ["read"] * 5
        assert [payload["data"]["value"] for _, payload in results] == list(range(5))
        assert sum(event["type"] == "tool_start" for event in output) == 5
        assert sum(event["type"] == "tool_end" for event in output) == 5

    asyncio.run(scenario())


def test_cancellation_stops_pending_async_tool_and_emits_status():
    async def scenario():
        registry = ToolRegistry()
        started = asyncio.Event()
        completed = False

        async def wait_for_cancel():
            nonlocal completed
            started.set()
            await asyncio.Event().wait()
            completed = True

        _register(registry, "wait", wait_for_cancel)
        events = []
        run = asyncio.create_task(
            ToolTaskOrchestrator(registry).run(
                [ToolTask("waiting", "wait")], on_event=events.append
            )
        )
        await started.wait()
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert completed is False
        assert any(event["type"] == "task_cancelled" for event in events)

    asyncio.run(scenario())
