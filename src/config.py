import os
from typing import Optional


class Config:
    """
    Konfigurasi aplikasi untuk Log Aggregator.

    Menggunakan environment variables dengan fallback ke default values.
    Memudahkan deployment dan testing dengan berbagai konfigurasi.
    """

    # Server configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8080"))

    # Database configuration
    DB_PATH: str = os.getenv("DB_PATH", "dedup_store.db")

    # Logging configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Queue configuration
    QUEUE_MAX_SIZE: int = int(os.getenv("QUEUE_MAX_SIZE", "10000"))

    # Processing configuration
    BATCH_PROCESS_SIZE: int = int(os.getenv("BATCH_PROCESS_SIZE", "100"))
    PROCESS_INTERVAL: float = float(os.getenv("PROCESS_INTERVAL", "0.1"))

    # API configuration
    API_TITLE: str = "Pub-Sub Log Aggregator"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = """
    ## Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplication

    Sistem ini menerima event/log dari publisher dan memproses dengan:
    - **Idempotency**: Event dengan (topic, event_id) sama hanya diproses sekali
    - **Deduplication**: Deteksi dan drop event duplikat
    - **Persistence**: Data tetap ada setelah restart
    - **At-least-once delivery**: Toleran terhadap duplikasi

    ### Endpoints:
    - `POST /publish`: Publish event (single/batch)
    - `GET /events`: Get processed events (optional topic filter)
    - `GET /stats`: Get system statistics
    - `GET /health`: Health check
    """

    # Feature flags
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "true").lower() == "true"
    ENABLE_DETAILED_LOGGING: bool = (
        os.getenv("ENABLE_DETAILED_LOGGING", "true").lower() == "true"
    )

    @classmethod
    def get_log_level(cls) -> int:
        """
        Convert log level string ke logging constant.

        Returns:
            Logging level constant (e.g., logging.INFO)
        """
        import logging

        return getattr(logging, cls.LOG_LEVEL.upper(), logging.INFO)

    @classmethod
    def print_config(cls):
        """
        Print konfigurasi saat ini (untuk debugging).
        """
        print("=" * 50)
        print("Application Configuration")
        print("=" * 50)
        print(f"HOST: {cls.HOST}")
        print(f"PORT: {cls.PORT}")
        print(f"DB_PATH: {cls.DB_PATH}")
        print(f"LOG_LEVEL: {cls.LOG_LEVEL}")
        print(f"QUEUE_MAX_SIZE: {cls.QUEUE_MAX_SIZE}")
        print(f"ENABLE_METRICS: {cls.ENABLE_METRICS}")
        print("=" * 50)
