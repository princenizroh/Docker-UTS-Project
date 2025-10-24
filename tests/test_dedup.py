import pytest
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dedup_store import DedupStore
from models import Event


@pytest.fixture
async def dedup_store():
    """
    Fixture untuk membuat dedup store untuk testing.
    Menggunakan database terpisah untuk testing.
    """
    db_path = "test_dedup.db"

    # Remove existing test database
    if os.path.exists(db_path):
        os.remove(db_path)

    store = DedupStore(db_path=db_path)

    yield store

    # Cleanup
    store.close()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_dedup_basic(dedup_store):
    """
    Test basic deduplication functionality.
    Event yang sama tidak boleh diproses dua kali.
    """
    topic = "test.topic"
    event_id = "evt-001"
    timestamp = "2025-10-24T10:00:00Z"
    source = "test-source"
    payload = '{"key": "value"}'

    # First event should not be duplicate
    is_dup = await dedup_store.is_duplicate(topic, event_id)
    assert is_dup == False, "First event should not be duplicate"

    # Mark as processed
    success = await dedup_store.mark_processed(
        topic, event_id, timestamp, source, payload
    )
    assert success == True, "First event should be marked successfully"

    # Second check should be duplicate
    is_dup = await dedup_store.is_duplicate(topic, event_id)
    assert is_dup == True, "Second check should show duplicate"

    # Try to mark again should fail
    success = await dedup_store.mark_processed(
        topic, event_id, timestamp, source, payload
    )
    assert success == False, "Duplicate event should not be marked again"


@pytest.mark.asyncio
async def test_dedup_different_topics(dedup_store):
    """
    Test deduplication dengan topic berbeda.
    Event dengan event_id sama tapi topic berbeda harus dianggap berbeda.
    """
    event_id = "evt-001"
    timestamp = "2025-10-24T10:00:00Z"
    source = "test-source"
    payload = '{"key": "value"}'

    # Mark event di topic1
    success1 = await dedup_store.mark_processed(
        "topic1", event_id, timestamp, source, payload
    )
    assert success1 == True

    # Mark event dengan event_id sama di topic2 harus berhasil
    success2 = await dedup_store.mark_processed(
        "topic2", event_id, timestamp, source, payload
    )
    assert success2 == True

    # Check keduanya berbeda
    is_dup1 = await dedup_store.is_duplicate("topic1", event_id)
    is_dup2 = await dedup_store.is_duplicate("topic2", event_id)

    assert is_dup1 == True
    assert is_dup2 == True


@pytest.mark.asyncio
async def test_dedup_multiple_events(dedup_store):
    """
    Test deduplication dengan multiple events.
    """
    events = [
        ("topic1", "evt-001"),
        ("topic1", "evt-002"),
        ("topic1", "evt-003"),
        ("topic2", "evt-001"),
        ("topic2", "evt-002"),
    ]

    timestamp = "2025-10-24T10:00:00Z"
    source = "test-source"
    payload = '{"key": "value"}'

    # Mark all events
    for topic, event_id in events:
        success = await dedup_store.mark_processed(
            topic, event_id, timestamp, source, payload
        )
        assert success == True

    # Try to mark again, all should fail
    for topic, event_id in events:
        success = await dedup_store.mark_processed(
            topic, event_id, timestamp, source, payload
        )
        assert success == False, f"Event {topic}/{event_id} should be duplicate"


@pytest.mark.asyncio
async def test_dedup_persistence(dedup_store):
    """
    Test persistence dedup store.
    Setelah restart, dedup store harus tetap ingat event yang sudah diproses.
    """
    topic = "test.topic"
    event_id = "evt-persistent"
    timestamp = "2025-10-24T10:00:00Z"
    source = "test-source"
    payload = '{"key": "value"}'

    db_path = dedup_store.db_path

    # Mark event
    success = await dedup_store.mark_processed(
        topic, event_id, timestamp, source, payload
    )
    assert success == True

    # Close store (simulate restart)
    dedup_store.close()

    # Create new store with same database
    new_store = DedupStore(db_path=db_path)

    # Check if event still marked as duplicate
    is_dup = await new_store.is_duplicate(topic, event_id)
    assert is_dup == True, "Event should still be duplicate after restart"

    # Try to mark again should fail
    success = await new_store.mark_processed(
        topic, event_id, timestamp, source, payload
    )
    assert success == False, "Event should not be marked again after restart"

    new_store.close()


@pytest.mark.asyncio
async def test_stats_tracking(dedup_store):
    """
    Test tracking statistik.
    """
    # Initial stats should be 0
    received, unique, dropped = await dedup_store.get_stats()
    assert received == 0
    assert unique == 0
    assert dropped == 0

    # Increment received
    await dedup_store.increment_received()
    await dedup_store.increment_received()
    await dedup_store.increment_received()

    # Increment unique processed
    await dedup_store.increment_unique_processed()
    await dedup_store.increment_unique_processed()

    # Increment dropped
    await dedup_store.increment_duplicate_dropped()

    # Check stats
    received, unique, dropped = await dedup_store.get_stats()
    assert received == 3
    assert unique == 2
    assert dropped == 1


@pytest.mark.asyncio
async def test_get_events(dedup_store):
    """
    Test retrieving events.
    """
    # Add some events
    events = [
        ("topic1", "evt-001", "2025-10-24T10:00:00Z", "source1", '{"data": 1}'),
        ("topic1", "evt-002", "2025-10-24T10:01:00Z", "source1", '{"data": 2}'),
        ("topic2", "evt-003", "2025-10-24T10:02:00Z", "source2", '{"data": 3}'),
    ]

    for topic, event_id, timestamp, source, payload in events:
        await dedup_store.mark_processed(topic, event_id, timestamp, source, payload)

    # Get all events
    all_events = await dedup_store.get_events()
    assert len(all_events) == 3

    # Get events for topic1
    topic1_events = await dedup_store.get_events(topic="topic1")
    assert len(topic1_events) == 2
    for event in topic1_events:
        assert event["topic"] == "topic1"

    # Get events for topic2
    topic2_events = await dedup_store.get_events(topic="topic2")
    assert len(topic2_events) == 1
    assert topic2_events[0]["topic"] == "topic2"
    assert topic2_events[0]["event_id"] == "evt-003"


@pytest.mark.asyncio
async def test_unique_topics_count(dedup_store):
    """
    Test counting unique topics.
    """
    # Initially should be 0
    count = await dedup_store.get_unique_topics_count()
    assert count == 0

    # Add events to different topics
    await dedup_store.mark_processed(
        "topic1", "evt-001", "2025-10-24T10:00:00Z", "source", "{}"
    )
    await dedup_store.mark_processed(
        "topic1", "evt-002", "2025-10-24T10:01:00Z", "source", "{}"
    )
    await dedup_store.mark_processed(
        "topic2", "evt-003", "2025-10-24T10:02:00Z", "source", "{}"
    )
    await dedup_store.mark_processed(
        "topic3", "evt-004", "2025-10-24T10:03:00Z", "source", "{}"
    )

    # Should have 3 unique topics
    count = await dedup_store.get_unique_topics_count()
    assert count == 3


@pytest.mark.asyncio
async def test_concurrent_dedup(dedup_store):
    """
    Test concurrent access untuk deduplication.
    Simulasi race condition.
    """
    topic = "test.topic"
    event_id = "evt-concurrent"
    timestamp = "2025-10-24T10:00:00Z"
    source = "test-source"
    payload = '{"key": "value"}'

    # Try to mark the same event concurrently
    tasks = [
        dedup_store.mark_processed(topic, event_id, timestamp, source, payload)
        for _ in range(10)
    ]

    results = await asyncio.gather(*tasks)

    # Only one should succeed
    success_count = sum(1 for r in results if r == True)
    assert success_count == 1, "Only one concurrent mark should succeed"

    # All others should fail
    fail_count = sum(1 for r in results if r == False)
    assert fail_count == 9, "Nine concurrent marks should fail"
