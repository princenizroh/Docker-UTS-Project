# Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplication

Proyek UTS Sistem Terdistribusi - Implementasi log aggregator dengan mekanisme publish-subscribe, idempotent consumer, dan deduplication untuk mencegah pemrosesan duplikat event.

## 📋 Deskripsi

Sistem ini adalah layanan log aggregator berbasis Pub-Sub yang:
- ✅ Menerima event/log dari publisher (at-least-once delivery)
- ✅ Memproses event melalui consumer yang bersifat idempotent
- ✅ Melakukan deduplication untuk mencegah pemrosesan duplikat
- ✅ Menyimpan data secara persisten menggunakan SQLite
- ✅ Toleran terhadap restart/crash (persistent dedup store)
- ✅ Menyediakan API untuk monitoring dan retrieval

## 🏗️ Arsitektur
```

    ┌─────────────────────────────────────────────────────────────────┐

    │                        Docker Container                          │

    │                                                                   │

    │  ┌──────────────┐                                                │

    │  │   FastAPI    │◄─── HTTP POST /publish (batch events)         │

    │  │  API Layer   │                                                │

    │  │   (port:8000)│──── Response: 202 Accepted                    │

    │  └──────┬───────┘                                                │

    │         │ enqueue                                                │

    │         ▼                                                         │

    │  ┌──────────────┐                                                │

    │  │ asyncio.Queue│  ← Bounded buffer (maxsize=10000)             │

    │  │  (in-memory) │    Backpressure: 503 if full                  │

    │  └──────┬───────┘                                                │

    │         │ dequeue                                                │

    │         ▼                                                         │

    │  ┌──────────────────┐                                            │

    │  │ Background       │                                            │

    │  │ Consumer Task    │  ← Async event processing loop            │

    │  │ (asyncio.Task)   │    • Check duplicate                      │

    │  └──────┬───────────┘    • Mark processed                       │

    │         │                • Update stats                         │

    │         ▼                                                         │

    │  ┌──────────────────────────────────────────┐                   │

    │  │        DedupStore (SQLite)               │                   │

    │  │  ┌────────────────────────────────────┐  │                   │

    │  │  │  processed_events                  │  │                   │

    │  │  │  • topic, event_id (UNIQUE)        │  │                   │

    │  │  │  • timestamp, source, payload      │  │                   │

    │  │  │  • processed_at                    │  │                   │

    │  │  └────────────────────────────────────┘  │                   │

    │  │  ┌────────────────────────────────────┐  │                   │

    │  │  │  stats (single row)                │  │                   │

    │  │  │  • received, unique_processed      │  │                   │

    │  │  │  • duplicate_dropped               │  │                   │

    │  │  └────────────────────────────────────┘  │                   │

    │  └──────────────────────────────────────────┘                   │

    │                │                                                  │

    │                ▼                                                  │

    │         Volume Mount (/app/data)                                 │

    │         Persistent Storage                                       │

    └───────────────────────────────────────────────────────────────────┘

  

External Access:

  Publisher ──HTTP──> localhost:8000/publish

  Query API ──HTTP──> localhost:8000/stats

                      localhost:8000/events?topic=...

                      localhost:8000/health

```


```

## 🚀 Fitur Utama

### 1. Idempotency
Event dengan kombinasi `(topic, event_id)` yang sama hanya akan diproses sekali, meskipun diterima berkali-kali.

### 2. Deduplication
Sistem secara otomatis mendeteksi dan men-drop event duplikat dengan logging yang jelas.

### 3. Persistence
Dedup store menggunakan SQLite yang persisten, sehingga setelah restart container, event yang sudah diproses tidak akan diproses ulang.

### 4. At-least-once Delivery
Sistem dirancang untuk toleran terhadap duplikasi yang mungkin terjadi dari retry mechanism.

### 5. RESTful API
- `POST /publish` - Publish event (single atau batch)
- `GET /events?topic=...` - Retrieve processed events (optional filter)
- `GET /stats` - System statistics
- `GET /health` - Health check
- `GET /` - API information

## 📦 Struktur Project

```
UTS-Project/
├── src/
│   ├── main.py           # FastAPI application & event consumer
│   ├── models.py         # Pydantic models untuk Event, Stats, dll
│   ├── dedup_store.py    # Persistent deduplication store (SQLite)
│   └── config.py         # Application configuration
├── tests/
│   ├── test_dedup.py     # Unit tests untuk deduplication
│   └── test_api.py       # Integration tests untuk API
├── Dockerfile            # Docker image configuration
├── docker-compose.yml    # Multi-service orchestration (bonus)
├── requirements.txt      # Python dependencies
├── README.md            # This file
└── report.md            # Laporan teori (T1-T8)


```

## 🛠️ Teknologi Stack

- **Python 3.11** - Programming language
- **FastAPI** - Web framework untuk REST API
- **Pydantic** - Data validation
- **SQLite** - Persistent dedup store
- **asyncio** - Async event processing
- **pytest** - Testing framework
- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration

## 📥 Installation & Setup

### Prerequisites
- Docker (version 20.10+)
- Docker Compose (optional, for bonus)
- Python 3.11+ (jika ingin run tanpa Docker)

### Option 1: Docker (Recommended)

#### Build Image
```bash
docker build -t uts-aggregator .
```

#### Run Container
```bash
docker run -p 8080:8080 uts-aggregator
```

#### Run dengan Persistent Storage
```bash
docker run -p 8080:8080 -v $(pwd)/data:/app/data -e DB_PATH=/app/data/dedup_store.db uts-aggregator
```

### Option 2: Docker Compose (Bonus)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

Docker Compose akan menjalankan:
- **aggregator** service di port 8080
- **publisher** service di port 8081
- Internal network untuk komunikasi
- Persistent volumes untuk data

### Option 3: Local Development (Tanpa Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Run application
python -m src.main

# Or dengan environment variables
HOST=0.0.0.0 PORT=8080 LOG_LEVEL=DEBUG python -m src.main
```

## 🧪 Running Tests

### With Docker
```bash
# Build test image
docker build -t uts-aggregator-test .

# Run tests
docker run --rm uts-aggregator-test pytest tests/ -v
```

### Local
```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_dedup.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Test Coverage
- ✅ `test_dedup.py` - 9 tests untuk deduplication functionality
- ✅ `test_api.py` - 10+ tests untuk API endpoints

## 📡 API Usage

### 1. Publish Event (Single)

```bash
curl -X POST http://localhost:8080/publish \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {
        "topic": "user.login",
        "event_id": "evt-001",
        "timestamp": "2024-01-15T10:00:00Z",
        "source": "auth-service",
        "payload": {
          "user_id": "user123",
          "ip": "192.168.1.1"
        }
      }
    ]
  }'
```

OR 
```powershell
curl -X POST http://localhost:8080/publish -H "Content-Type: application/json" -d "@test_single_event.json" | ConvertFrom-Json | ConvertTo-Json
```

### 2. Publish Batch Events

```bash
curl -X POST http://localhost:8080/publish \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {
        "topic": "user.login",
        "event_id": "evt-001",
        "timestamp": "2024-01-15T10:00:00Z",
        "source": "auth-service",
        "payload": {"user_id": "user123"}
      },
      {
        "topic": "user.logout",
        "event_id": "evt-002",
        "timestamp": "2024-01-15T10:05:00Z",
        "source": "auth-service",
        "payload": {"user_id": "user123"}
      }
    ]
  }'
```

```powershell
curl -X POST http://localhost:8080/publish -H "Content-Type: application/json" -d "@test_batch_event.json" | ConvertFrom-Json | ConvertTo-Json
```


### 3. Get All Events

```bash
curl http://localhost:8080/events
```

### 4. Get Events by Topic

```bash
curl http://localhost:8080/events?topic=user.login
```

### 5. Get Statistics

```bash
curl http://localhost:8080/stats
```

Response:
```json
{
  "received": 1000,
  "unique_processed": 800,
  "duplicate_dropped": 200,
  "topics": 5,
  "uptime": 3600.5
}
```

### 6. Health Check

```bash
curl http://localhost:8080/health
```

## 🔬 Testing Deduplication

```powershell
curl -X POST http://localhost:8080/publish -H "Content-Type: application/json" -d "@test_duplicate.json" | ConvertFrom-Json | ConvertTo-Json
```
  

Expected output:
- `received`: 5
- `unique_processed`: 2
- `duplicate_dropped`: 3

## 🧪 Performance Testing

### Load Test dengan 5000+ Events

```bash
python scripts/load_test.py
```

Atau manual dengan curl:

```bash
curl http://localhost:8080/stats
```

## 🔍 Monitoring & Logging

### View Logs (Docker)
```bash
# Follow logs
docker logs -f <container-id>

# Last 100 lines
docker logs --tail 100 <container-id>

# With timestamp
docker logs -t <container-id>
```

### Log Format
```
2024-01-15 10:00:00 - dedup_store - INFO - Event marked as processed: topic=user.login, event_id=evt-001
2024-01-15 10:00:01 - dedup_store - WARNING - Duplicate event detected: topic=user.login, event_id=evt-001
2024-01-15 10:00:02 - main - INFO - EVENT PROCESSED - topic: user.logout, event_id: evt-002, source: auth-service
2024-01-15 10:00:03 - main - WARNING - DUPLICATE DROPPED - topic: user.login, event_id: evt-001, source: auth-service
```

## 🔧 Configuration

Environment variables yang tersedia:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8080` | Server port |
| `DB_PATH` | `dedup_store.db` | Path ke SQLite database |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `QUEUE_MAX_SIZE` | `10000` | Max size untuk internal event queue |
| `ENABLE_METRICS` | `true` | Enable metrics collection |

## 🎯 Design Decisions

### 1. SQLite untuk Dedup Store
**Keputusan**: Menggunakan SQLite sebagai persistent storage untuk dedup store.

**Alasan**:
- Embedded database, tidak perlu service eksternal
- ACID compliance untuk consistency
- Built-in UNIQUE constraint untuk deduplication
- Lightweight dan cukup untuk local deployment
- Support untuk concurrent access dengan locking

### 2. asyncio.Queue untuk Internal Pipeline
**Keputusan**: Menggunakan asyncio.Queue untuk internal event processing.

**Alasan**:
- Non-blocking I/O untuk high throughput
- Built-in backpressure mechanism
- Decoupling antara receive dan process
- Mudah untuk testing dan monitoring

### 3. (topic, event_id) sebagai Dedup Key
**Keputusan**: Kombinasi topic dan event_id sebagai unique key.

**Alasan**:
- Topic isolation: event yang sama bisa ada di topic berbeda
- Flexibility: memungkinkan same event_id untuk different contexts
- Scalability: index per-topic lebih efisien

### 4. At-least-once Delivery Semantic
**Keputusan**: Sistem dirancang untuk at-least-once, bukan exactly-once.

**Alasan**:
- Exactly-once sangat sulit dan mahal di distributed systems
- At-least-once + idempotency = practically exactly-once
- Lebih resilient terhadap network issues dan retries


## 📊 Metrik Evaluasi

### 1. Throughput
- Target: >= 1000 events/second
- Measurement: Total events processed / time

### 2. Latency
- Publish endpoint: < 10ms (acceptance time)
- End-to-end processing: < 100ms per event

### 3. Duplicate Rate
- Accuracy: 100% (no false negatives)
- All duplicates should be detected and dropped

### 4. Availability
- Target: 99.9% uptime
- Graceful degradation under load


---

**Note**: Project ini dijalankan 100% lokal di dalam container. Tidak ada komunikasi dengan service eksternal.