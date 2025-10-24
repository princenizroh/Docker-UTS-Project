import pytest
import asyncio
import os
import sys
from pathlib import Path
from httpx import AsyncClient
from contextlib import asynccontextmanager

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import app, lifespan
from models import Event


@pytest.fixture(scope="function")
async def client():
    """
    Fixture untuk AsyncClient untuk testing API dengan lifespan support.
    Manually trigger lifespan events.
    """
    # Manually run lifespan startup
    async with lifespan(app):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    # lifespan shutdown runs automatically when exiting context


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """
    Test root endpoint mengembalikan informasi dasar.
    """
    response = await client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "service" in data
    assert data["service"] == "Pub-Sub Log Aggregator"
    assert "version" in data
    assert "endpoints" in data


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """
    Test health check endpoint.
    """
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "queue_size" in data
    assert "timestamp" in data
    assert isinstance(data["uptime_seconds"], (int, float))


@pytest.mark.asyncio
async def test_publish_single_event(client):
    """
    Test publish single event.
    """
    event_data = {
        "events": [
            {
                "topic": "test.single",
                "event_id": "evt-single-001",
                "timestamp": "2025-10-24T10:00:00Z",
                "source": "test-client",
                "payload": {"message": "test single event"},
            }
        ]
    }

    response = await client.post("/publish", json=event_data)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "accepted"
    assert data["received"] == 1
    assert "message" in data


@pytest.mark.asyncio
async def test_publish_batch_events(client):
    """
    Test publish batch events.
    """
    event_data = {
        "events": [
            {
                "topic": "test.batch",
                "event_id": f"evt-batch-{i:03d}",
                "timestamp": f"2025-10-24T10:{i:02d}:00Z",
                "source": "test-client",
                "payload": {"index": i},
            }
            for i in range(10)
        ]
    }

    response = await client.post("/publish", json=event_data)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "accepted"
    assert data["received"] == 10


@pytest.mark.asyncio
async def test_publish_duplicate_events(client):
    """
    Test publish duplicate events.
    Sistem harus menerima semua, tapi hanya memproses unique.
    """
    event_data = {
        "events": [
            {
                "topic": "test.duplicate",
                "event_id": "evt-dup-001",
                "timestamp": "2025-10-24T10:00:00Z",
                "source": "test-client",
                "payload": {"message": "original"},
            }
        ]
    }

    # Send first time
    response1 = await client.post("/publish", json=event_data)
    assert response1.status_code == 200

    # Wait for processing
    await asyncio.sleep(0.5)

    # Send duplicate
    response2 = await client.post("/publish", json=event_data)
    assert response2.status_code == 200

    # Wait for processing
    await asyncio.sleep(0.5)

    # Check stats - should show 1 dropped
    stats_response = await client.get("/stats")
    stats = stats_response.json()

    # Both should be received
    assert stats["received"] >= 2
    # But duplicate should be dropped
    assert stats["duplicate_dropped"] >= 1


@pytest.mark.asyncio
async def test_publish_invalid_event_missing_fields(client):
    """
    Test publish dengan event invalid (missing fields).
    """
    invalid_event = {
        "events": [
            {
                "topic": "test.invalid",
                # Missing event_id, timestamp, source
                "payload": {"message": "invalid"},
            }
        ]
    }

    response = await client.post("/publish", json=invalid_event)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_publish_invalid_timestamp(client):
    """
    Test publish dengan timestamp invalid.
    """
    invalid_event = {
        "events": [
            {
                "topic": "test.invalid",
                "event_id": "evt-invalid-001",
                "timestamp": "not-a-valid-timestamp",
                "source": "test-client",
                "payload": {},
            }
        ]
    }

    response = await client.post("/publish", json=invalid_event)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_publish_empty_event_list(client):
    """
    Test publish dengan empty event list.
    """
    empty_data = {"events": []}

    response = await client.post("/publish", json=empty_data)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_events_all(client):
    """
    Test get all events.
    """
    # Publish some events first
    event_data = {
        "events": [
            {
                "topic": "test.get",
                "event_id": f"evt-get-{i:03d}",
                "timestamp": f"2025-10-24T10:{i:02d}:00Z",
                "source": "test-client",
                "payload": {"index": i},
            }
            for i in range(5)
        ]
    }

    await client.post("/publish", json=event_data)

    # Wait for processing
    await asyncio.sleep(1)

    # Get all events
    response = await client.get("/events")
    assert response.status_code == 200

    data = response.json()
    assert "events" in data
    assert "total" in data
    assert isinstance(data["events"], list)


@pytest.mark.asyncio
async def test_get_events_by_topic(client):
    """
    Test get events filtered by topic.
    """
    # Publish events to different topics
    event_data = {
        "events": [
            {
                "topic": "test.topic1",
                "event_id": f"evt-topic1-{i:03d}",
                "timestamp": f"2025-10-24T10:{i:02d}:00Z",
                "source": "test-client",
                "payload": {"topic": 1, "index": i},
            }
            for i in range(3)
        ]
        + [
            {
                "topic": "test.topic2",
                "event_id": f"evt-topic2-{i:03d}",
                "timestamp": f"2025-10-24T11:{i:02d}:00Z",
                "source": "test-client",
                "payload": {"topic": 2, "index": i},
            }
            for i in range(3)
        ]
    }

    await client.post("/publish", json=event_data)

    # Wait for processing
    await asyncio.sleep(1)

    # Get events for topic1
    response = await client.get("/events?topic=test.topic1")
    assert response.status_code == 200

    data = response.json()
    assert data["topic"] == "test.topic1"

    # All events should be from topic1
    for event in data["events"]:
        assert event["topic"] == "test.topic1"


@pytest.mark.asyncio
async def test_get_stats(client):
    """
    Test get statistics endpoint.
    """
    response = await client.get("/stats")
    assert response.status_code == 200

    data = response.json()

    # Check all required fields
    assert "received" in data
    assert "unique_processed" in data
    assert "duplicate_dropped" in data
    assert "topics" in data
    assert "uptime" in data

    # Check types
    assert isinstance(data["received"], int)
    assert isinstance(data["unique_processed"], int)
    assert isinstance(data["duplicate_dropped"], int)
    assert isinstance(data["topics"], int)
    assert isinstance(data["uptime"], (int, float))

    # Basic sanity checks
    assert data["received"] >= 0
    assert data["unique_processed"] >= 0
    assert data["duplicate_dropped"] >= 0
    assert data["uptime"] >= 0


@pytest.mark.asyncio
async def test_stats_consistency(client):
    """
    Test consistency of stats.
    received = unique_processed + duplicate_dropped
    """
    # Publish some events
    event_data = {
        "events": [
            {
                "topic": "test.stats",
                "event_id": f"evt-stats-{i:03d}",
                "timestamp": f"2025-10-24T10:{i:02d}:00Z",
                "source": "test-client",
                "payload": {"index": i},
            }
            for i in range(5)
        ]
    }

    await client.post("/publish", json=event_data)
    await asyncio.sleep(1)

    # Get initial stats
    response = await client.get("/stats")
    stats1 = response.json()

    # Publish same events again (duplicates)
    await client.post("/publish", json=event_data)
    await asyncio.sleep(1)

    # Get stats again
    response = await client.get("/stats")
    stats2 = response.json()

    # Check that duplicate_dropped increased
    assert stats2["duplicate_dropped"] > stats1["duplicate_dropped"]

    # Check consistency: received = unique_processed + duplicate_dropped
    assert (
        stats2["received"] == stats2["unique_processed"] + stats2["duplicate_dropped"]
    )


@pytest.mark.asyncio
async def test_event_schema_validation(client):
    """
    Test event schema validation dengan berbagai invalid inputs.
    """
    # Test empty topic
    invalid_events = [
        {
            "events": [
                {
                    "topic": "",
                    "event_id": "evt-001",
                    "timestamp": "2025-10-24T10:00:00Z",
                    "source": "test",
                    "payload": {},
                }
            ]
        },
        # Test empty event_id
        {
            "events": [
                {
                    "topic": "test",
                    "event_id": "",
                    "timestamp": "2025-10-24T10:00:00Z",
                    "source": "test",
                    "payload": {},
                }
            ]
        },
    ]

    for invalid_event in invalid_events:
        response = await client.post("/publish", json=invalid_event)
        assert response.status_code in [400, 422], (
            f"Should reject invalid event: {invalid_event}"
        )


@pytest.mark.asyncio
async def test_large_batch_performance(client):
    """
    Test performance dengan large batch.
    Minimal 1000 events harus bisa diproses dalam waktu wajar.
    """
    import time

    # Create large batch
    event_data = {
        "events": [
            {
                "topic": f"test.perf.topic{i % 10}",
                "event_id": f"evt-perf-{i:05d}",
                "timestamp": f"2025-10-24T{(i // 3600) % 24:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z",
                "source": "test-client",
                "payload": {"index": i, "data": f"test data {i}"},
            }
            for i in range(1000)
        ]
    }

    start_time = time.time()
    response = await client.post("/publish", json=event_data)
    publish_time = time.time() - start_time

    assert response.status_code == 200
    assert response.json()["received"] == 1000

    # Publishing should be fast (acceptance, not processing)
    assert publish_time < 5.0, f"Publishing took too long: {publish_time}s"

    # Wait for processing
    await asyncio.sleep(3)

    # Check stats
    stats_response = await client.get("/stats")
    stats = stats_response.json()

    # Should have processed all events
    assert stats["unique_processed"] >= 1000
