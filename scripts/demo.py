#!/usr/bin/env python3
"""
Demo script untuk testing Pub-Sub Log Aggregator
Mendemonstrasikan:
1. Publish events (single & batch)
2. Duplicate detection
3. Statistics tracking
4. Query events
"""

import asyncio
import httpx
import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any


BASE_URL = "http://localhost:8080"


def create_event(
    topic: str, event_id: str = None, payload: Dict[str, Any] = None
) -> Dict:
    """Create event object"""
    if event_id is None:
        event_id = f"evt-{uuid.uuid4()}"

    if payload is None:
        payload = {"message": "test event"}

    return {
        "topic": topic,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "demo-script",
        "payload": payload,
    }


async def publish_events(client: httpx.AsyncClient, events: List[Dict]) -> Dict:
    """Publish events to aggregator"""
    response = await client.post(f"{BASE_URL}/publish", json={"events": events})
    response.raise_for_status()
    return response.json()


async def get_stats(client: httpx.AsyncClient) -> Dict:
    """Get system statistics"""
    response = await client.get(f"{BASE_URL}/stats")
    response.raise_for_status()
    return response.json()


async def get_events(client: httpx.AsyncClient, topic: str = None) -> Dict:
    """Get processed events"""
    url = f"{BASE_URL}/events"
    if topic:
        url += f"?topic={topic}"

    response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def demo_single_event(client: httpx.AsyncClient):
    """Demo: Publish single event"""
    print("\n" + "=" * 60)
    print("DEMO 1: Single Event Publishing")
    print("=" * 60)

    event = create_event(
        topic="demo.single", payload={"user_id": "user123", "action": "login"}
    )

    print(f"\nPublishing event: {event['event_id']}")
    result = await publish_events(client, [event])
    print(f"Result: {json.dumps(result, indent=2)}")

    await asyncio.sleep(0.5)

    stats = await get_stats(client)
    print(f"\nStats after single event:")
    print(f"  Received: {stats['received']}")
    print(f"  Unique Processed: {stats['unique_processed']}")
    print(f"  Duplicates Dropped: {stats['duplicate_dropped']}")


async def demo_batch_events(client: httpx.AsyncClient):
    """Demo: Publish batch of events"""
    print("\n" + "=" * 60)
    print("DEMO 2: Batch Event Publishing")
    print("=" * 60)

    events = [
        create_event(
            topic="demo.batch", payload={"index": i, "data": f"batch event {i}"}
        )
        for i in range(10)
    ]

    print(f"\nPublishing {len(events)} events in batch...")
    result = await publish_events(client, events)
    print(f"Result: {json.dumps(result, indent=2)}")

    await asyncio.sleep(1)

    stats = await get_stats(client)
    print(f"\nStats after batch:")
    print(f"  Received: {stats['received']}")
    print(f"  Unique Processed: {stats['unique_processed']}")


async def demo_duplicate_detection(client: httpx.AsyncClient):
    """Demo: Duplicate event detection"""
    print("\n" + "=" * 60)
    print("DEMO 3: Duplicate Detection (Idempotency)")
    print("=" * 60)

    event = create_event(
        topic="demo.duplicate",
        event_id="evt-duplicate-test-001",
        payload={"message": "This will be sent 3 times"},
    )

    stats_before = await get_stats(client)

    print(f"\nSending same event 3 times:")
    print(f"Event ID: {event['event_id']}")

    for i in range(3):
        print(f"\n  Attempt {i + 1}:")
        result = await publish_events(client, [event])
        print(f"    Response: {result['status']}")
        await asyncio.sleep(0.3)

    await asyncio.sleep(1)

    stats_after = await get_stats(client)

    print(f"\nStats comparison:")
    print(f"  Before:")
    print(f"    Received: {stats_before['received']}")
    print(f"    Unique: {stats_before['unique_processed']}")
    print(f"    Duplicates: {stats_before['duplicate_dropped']}")
    print(f"  After:")
    print(f"    Received: {stats_after['received']}")
    print(f"    Unique: {stats_after['unique_processed']}")
    print(f"    Duplicates: {stats_after['duplicate_dropped']}")
    print(f"  Delta:")
    print(f"    Received: +{stats_after['received'] - stats_before['received']}")
    print(
        f"    Unique: +{stats_after['unique_processed'] - stats_before['unique_processed']}"
    )
    print(
        f"    Duplicates: +{stats_after['duplicate_dropped'] - stats_before['duplicate_dropped']}"
    )

    print(f"\n✓ Expected: 3 received, 1 unique, 2 duplicates")
    print(
        f"✓ Actual: +{stats_after['received'] - stats_before['received']} received, "
        f"+{stats_after['unique_processed'] - stats_before['unique_processed']} unique, "
        f"+{stats_after['duplicate_dropped'] - stats_before['duplicate_dropped']} duplicates"
    )


async def demo_multiple_topics(client: httpx.AsyncClient):
    """Demo: Multiple topics"""
    print("\n" + "=" * 60)
    print("DEMO 4: Multiple Topics")
    print("=" * 60)

    topics = ["auth.login", "auth.logout", "payment.created", "payment.completed"]

    print(f"\nPublishing events to {len(topics)} different topics...")

    for topic in topics:
        events = [
            create_event(topic=topic, payload={"topic": topic, "index": i})
            for i in range(3)
        ]
        await publish_events(client, events)

    await asyncio.sleep(1)

    stats = await get_stats(client)
    print(f"\nStats:")
    print(f"  Topics: {stats['topics']}")
    print(f"  Total Events: {stats['unique_processed']}")

    print(f"\nEvents per topic:")
    for topic in topics:
        events = await get_events(client, topic=topic)
        print(f"  {topic}: {events['total']} events")


async def demo_high_volume(client: httpx.AsyncClient):
    """Demo: High volume with duplicates"""
    print("\n" + "=" * 60)
    print("DEMO 5: High Volume Test (1000 events, 20% duplicates)")
    print("=" * 60)

    print("\nGenerating events...")
    events = []

    for i in range(800):
        events.append(
            create_event(
                topic="demo.highvolume", payload={"index": i, "type": "unique"}
            )
        )

    for i in range(200):
        duplicate = create_event(
            topic="demo.highvolume",
            event_id=events[i]["event_id"],  
            payload={"index": i, "type": "duplicate"},
        )
        events.append(duplicate)

    print(f"Total events to send: {len(events)}")
    print(f"Expected unique: 800")
    print(f"Expected duplicates: 200")

    stats_before = await get_stats(client)

    batch_size = 100
    print(f"\nSending in batches of {batch_size}...")

    for i in range(0, len(events), batch_size):
        batch = events[i : i + batch_size]
        await publish_events(client, batch)
        print(
            f"  Sent batch {i // batch_size + 1}/{(len(events) + batch_size - 1) // batch_size}"
        )
        await asyncio.sleep(0.1)

    print("\nWaiting for processing...")
    await asyncio.sleep(3)

    stats_after = await get_stats(client)

    print(f"\nResults:")
    print(f"  Events sent: {len(events)}")
    print(f"  Received: +{stats_after['received'] - stats_before['received']}")
    print(
        f"  Unique processed: +{stats_after['unique_processed'] - stats_before['unique_processed']}"
    )
    print(
        f"  Duplicates dropped: +{stats_after['duplicate_dropped'] - stats_before['duplicate_dropped']}"
    )

    unique_delta = stats_after["unique_processed"] - stats_before["unique_processed"]
    dup_delta = stats_after["duplicate_dropped"] - stats_before["duplicate_dropped"]

    print(f"\n✓ Accuracy: {unique_delta}/800 unique = {unique_delta / 800 * 100:.1f}%")
    print(f"✓ Dedup rate: {dup_delta}/200 duplicates = {dup_delta / 200 * 100:.1f}%")


async def demo_query_events(client: httpx.AsyncClient):
    """Demo: Query processed events"""
    print("\n" + "=" * 60)
    print("DEMO 6: Query Processed Events")
    print("=" * 60)

    all_events = await get_events(client)
    print(f"\nTotal processed events: {all_events['total']}")

    if all_events["total"] > 0:
        print(f"\nSample events (first 5):")
        for i, event in enumerate(all_events["events"][:5]):
            print(f"\n  Event {i + 1}:")
            print(f"    Topic: {event['topic']}")
            print(f"    Event ID: {event['event_id']}")
            print(f"    Timestamp: {event['timestamp']}")
            print(f"    Source: {event['source']}")


async def main():
    """Main demo function"""
    print("\n" + "=" * 60)
    print("PUB-SUB LOG AGGREGATOR - DEMO SCRIPT")
    print("=" * 60)
    print(f"\nTarget: {BASE_URL}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            response.raise_for_status()
            print("✓ Server is healthy")
        except Exception as e:
            print(f"✗ Server not reachable: {e}")
            print("\nMake sure the server is running:")
            print("  docker run -p 8080:8080 uts-aggregator")
            print("  or")
            print("  python -m src.main")
            return

        try:
            await demo_single_event(client)
            await demo_batch_events(client)
            await demo_duplicate_detection(client)
            await demo_multiple_topics(client)
            await demo_high_volume(client)
            await demo_query_events(client)

            print("\n" + "=" * 60)
            print("FINAL STATISTICS")
            print("=" * 60)
            stats = await get_stats(client)
            print(f"\nTotal Received: {stats['received']}")
            print(f"Unique Processed: {stats['unique_processed']}")
            print(f"Duplicates Dropped: {stats['duplicate_dropped']}")
            print(f"Topics: {stats['topics']}")
            print(f"Uptime: {stats['uptime']:.1f}s")

            print(f"\n✓ Consistency check:")
            print(f"  received = unique + duplicates")
            print(
                f"  {stats['received']} = {stats['unique_processed']} + {stats['duplicate_dropped']}"
            )
            if (
                stats["received"]
                == stats["unique_processed"] + stats["duplicate_dropped"]
            ):
                print(f"  ✓ PASS: System is consistent!")
            else:
                print(f"  ✗ FAIL: Inconsistency detected!")

            print("\n" + "=" * 60)
            print("DEMO COMPLETED SUCCESSFULLY")
            print("=" * 60)

        except Exception as e:
            print(f"\n✗ Error during demo: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
