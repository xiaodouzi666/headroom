"""In-memory ASGI upload abuse checks; no admission, provider or GPU work."""

import asyncio
import sqlite3
from contextlib import suppress

import httpx
import pytest
from starlette.requests import ClientDisconnect
from test_api import completed_worker
from test_api import settings as isolated_settings

from headroom.api import app as api_module
from headroom.api.app import create_app


@pytest.fixture
def application(tmp_path):
    settings = isolated_settings.__wrapped__(tmp_path)
    app = create_app(settings, worker=completed_worker)
    yield app
    app.state.store.close()


def assert_no_admissions(app):
    with sqlite3.connect(app.state.queue.admission_path) as connection:
        assert connection.execute("SELECT count(*) FROM admissions").fetchone()[0] == 0
    assert not app.state.queue.preparing and not app.state.queue.pending


async def assert_three_slots_reusable(client):
    released = asyncio.Event()
    started = [asyncio.Event() for _ in range(3)]

    async def body(index):
        started[index].set()
        await released.wait()
        yield b"{}"  # Invalid input deliberately stops before queue admission.

    tasks = [
        asyncio.create_task(client.post("/api/runs", content=body(index))) for index in range(3)
    ]
    try:
        async with asyncio.timeout(2):
            await asyncio.gather(*(event.wait() for event in started))
        fourth = await client.post("/api/runs", content=b"{}")
        assert fourth.status_code == 429 and "capacity" in fourth.text
    finally:
        released.set()
    responses = await asyncio.gather(*tasks)
    assert [response.status_code for response in responses] == [400, 400, 400]


def test_slow_upload_has_total_deadline_and_releases_slot(application):
    application.state.settings.upload_deadline_seconds = 0.04

    async def scenario():
        async def dripping():
            # Each chunk arrives promptly, but the whole request never completes.
            while True:
                yield b" "
                await asyncio.sleep(0.005)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            async with asyncio.timeout(2):
                response = await client.post("/api/runs", content=dripping())
            assert response.status_code == 408 and "deadline" in response.text
            application.state.settings.upload_deadline_seconds = 30
            await assert_three_slots_reusable(client)
        assert_no_admissions(application)

    asyncio.run(scenario())


def test_upload_capacity_is_bounded_before_admission(application):
    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            await assert_three_slots_reusable(client)
            assert (await client.post("/api/runs", content=b"{}")).status_code == 400
        assert_no_admissions(application)

    asyncio.run(scenario())


def test_cancelled_upload_releases_slot_without_consuming_admission(application):
    async def scenario():
        started = asyncio.Event()

        async def blocked():
            started.set()
            await asyncio.Event().wait()
            yield b"{}"

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            task = asyncio.create_task(client.post("/api/runs", content=blocked()))
            async with asyncio.timeout(2):
                await started.wait()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await assert_three_slots_reusable(client)
        assert_no_admissions(application)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["disconnect", "oversize"])
def test_failed_upload_releases_slot_without_consuming_admission(application, monkeypatch, failure):
    monkeypatch.setattr(api_module, "MAX_BODY_BYTES", 32)

    async def scenario():
        async def failed_body():
            if failure == "disconnect":
                raise ClientDisconnect()
            yield b"x" * 33

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            response = await client.post("/api/runs", content=failed_body())
            assert response.status_code == (400 if failure == "disconnect" else 413)
            await assert_three_slots_reusable(client)
        assert_no_admissions(application)

    asyncio.run(scenario())
