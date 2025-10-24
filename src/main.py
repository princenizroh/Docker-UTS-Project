import asyncio
import logging
import json
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import uvicorn

from src.models import Event, PublishRequest, PublishResponse, Stats, EventsResponse
from src.dedup_store import DedupStore
from src.config import Config

# Setup logging
logging.basicConfig(level=Config.get_log_level(), format=Config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# Global variables
dedup_store: Optional[DedupStore] = None
event_queue: Optional[asyncio.Queue] = None
start_time: datetime = datetime.utcnow()
consumer_task: Optional[asyncio.Task] = None


async def event_consumer():
    """
    Background consumer yang memproses event dari queue.

    Consumer ini berjalan terus-menerus dan:
    1. Mengambil event dari queue
    2. Check apakah event duplikat
    3. Jika tidak duplikat, mark sebagai processed
    4. Update statistik

    Implementasi idempotency dan deduplication.
    """
    logger.info("Event consumer started")

    while True:
        try:
            # Get event from queue
            event: Event = await event_queue.get()

            # Check if duplicate
            is_dup = await dedup_store.is_duplicate(event.topic, event.event_id)

            if is_dup:
                # Event sudah pernah diproses, drop
                await dedup_store.increment_duplicate_dropped()
                logger.warning(
                    f"DUPLICATE DROPPED - topic: {event.topic}, "
                    f"event_id: {event.event_id}, source: {event.source}"
                )
            else:
                # Event baru, process
                payload_json = json.dumps(event.payload)
                success = await dedup_store.mark_processed(
                    event.topic,
                    event.event_id,
                    event.timestamp,
                    event.source,
                    payload_json,
                )

                if success:
                    await dedup_store.increment_unique_processed()
                    logger.info(
                        f"EVENT PROCESSED - topic: {event.topic}, "
                        f"event_id: {event.event_id}, source: {event.source}"
                    )
                else:
                    # Race condition: event sudah diproses saat kita check
                    await dedup_store.increment_duplicate_dropped()
                    logger.warning(
                        f"DUPLICATE DETECTED (race) - topic: {event.topic}, "
                        f"event_id: {event.event_id}"
                    )

            # Mark task as done
            event_queue.task_done()

        except Exception as e:
            logger.error(f"Error in event consumer: {str(e)}", exc_info=True)
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager untuk startup dan shutdown.
    """
    # Startup
    global dedup_store, event_queue, consumer_task, start_time

    logger.info("Starting Pub-Sub Log Aggregator...")
    Config.print_config()

    # Initialize dedup store
    dedup_store = DedupStore(db_path=Config.DB_PATH)
    logger.info("Dedup store initialized")

    # Initialize event queue
    event_queue = asyncio.Queue(maxsize=Config.QUEUE_MAX_SIZE)
    logger.info(f"Event queue initialized with max size: {Config.QUEUE_MAX_SIZE}")

    # Start consumer task
    consumer_task = asyncio.create_task(event_consumer())
    logger.info("Event consumer task started")

    # Record start time
    start_time = datetime.utcnow()

    logger.info("✓ Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Cancel consumer task
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    # Close dedup store
    if dedup_store:
        dedup_store.close()

    logger.info("✓ Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=Config.API_TITLE,
    version=Config.API_VERSION,
    description=Config.API_DESCRIPTION,
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """
    Root endpoint - informasi dasar API.
    """
    return {
        "service": "Pub-Sub Log Aggregator",
        "version": Config.API_VERSION,
        "status": "running",
        "endpoints": {
            "publish": "POST /publish",
            "events": "GET /events",
            "stats": "GET /stats",
            "health": "GET /health",
        },
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    uptime = (datetime.utcnow() - start_time).total_seconds()

    return {
        "status": "healthy",
        "uptime_seconds": uptime,
        "queue_size": event_queue.qsize() if event_queue else 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/publish", response_model=PublishResponse)
async def publish_events(request: PublishRequest):
    """
    Endpoint untuk publish event (single atau batch).

    Request body harus berisi list event dengan struktur:
    - topic: nama topic/kategori
    - event_id: ID unik untuk deduplication
    - timestamp: ISO8601 format
    - source: sumber event
    - payload: data event (dict)

    Sistem akan:
    1. Validasi semua event
    2. Masukkan ke queue untuk diproses
    3. Consumer akan handle idempotency dan deduplication

    Returns:
        PublishResponse dengan status dan jumlah event yang diterima
    """
    if not request.events:
        raise HTTPException(status_code=400, detail="Event list tidak boleh kosong")

    received_count = len(request.events)

    # Put events ke queue
    for event in request.events:
        try:
            await event_queue.put(event)
            await dedup_store.increment_received()

            if Config.ENABLE_DETAILED_LOGGING:
                logger.debug(
                    f"Event received - topic: {event.topic}, "
                    f"event_id: {event.event_id}, source: {event.source}"
                )
        except asyncio.QueueFull:
            logger.error("Event queue is full!")
            raise HTTPException(
                status_code=503, detail="Event queue is full, please try again later"
            )
        except Exception as e:
            logger.error(f"Error adding event to queue: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    logger.info(f"Received {received_count} event(s) for processing")

    return PublishResponse(
        status="accepted",
        received=received_count,
        message=f"Successfully received {received_count} event(s) for processing",
    )


@app.get("/events", response_model=EventsResponse)
async def get_events(topic: Optional[str] = Query(None, description="Filter by topic")):
    """
    Endpoint untuk mendapatkan list event yang sudah diproses.

    Query parameters:
    - topic (optional): filter berdasarkan topic tertentu

    Returns:
        EventsResponse dengan list event yang sudah diproses
    """
    try:
        events_data = await dedup_store.get_events(topic=topic)

        # Convert back to Event objects
        events = []
        for event_dict in events_data:
            # Parse payload from JSON string
            payload = json.loads(event_dict["payload"])

            events.append(
                Event(
                    topic=event_dict["topic"],
                    event_id=event_dict["event_id"],
                    timestamp=event_dict["timestamp"],
                    source=event_dict["source"],
                    payload=payload,
                )
            )

        logger.info(
            f"Retrieved {len(events)} event(s)"
            + (f" for topic: {topic}" if topic else "")
        )

        return EventsResponse(topic=topic, total=len(events), events=events)

    except Exception as e:
        logger.error(f"Error retrieving events: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving events: {str(e)}"
        )


@app.get("/stats", response_model=Stats)
async def get_stats():
    """
    Endpoint untuk mendapatkan statistik sistem.

    Returns:
        Stats object dengan:
        - received: total event yang diterima
        - unique_processed: total event unik yang diproses
        - duplicate_dropped: total duplikat yang di-drop
        - topics: jumlah topic unik
        - uptime: uptime sistem dalam detik
    """
    try:
        # Get stats from dedup store
        received, unique_processed, duplicate_dropped = await dedup_store.get_stats()
        topics_count = await dedup_store.get_unique_topics_count()
        uptime = (datetime.utcnow() - start_time).total_seconds()

        stats = Stats(
            received=received,
            unique_processed=unique_processed,
            duplicate_dropped=duplicate_dropped,
            topics=topics_count,
            uptime=uptime,
        )

        logger.debug(f"Stats retrieved: {stats.model_dump()}")

        return stats

    except Exception as e:
        logger.error(f"Error retrieving stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {str(e)}")


def main():
    """
    Entry point untuk menjalankan aplikasi.
    """
    logger.info(f"Starting server on {Config.HOST}:{Config.PORT}")

    uvicorn.run(
        "src.main:app",
        host=Config.HOST,
        port=Config.PORT,
        log_level=Config.LOG_LEVEL.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
