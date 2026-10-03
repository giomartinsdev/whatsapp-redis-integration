import json
import logging
import os
from typing import Optional

import redis

logger = logging.getLogger(__name__)

class RedisQueue:
    def __init__(self, url: Optional[str] = None) -> None:
        self._url = url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client = redis.from_url(self._url, decode_responses=True)
        logger.info(f"Connected to Redis at {self._url}")

    @property
    def client(self) -> redis.Redis:
        return self._client

    def enqueue(self, queue: str, message: dict, topic: Optional[str] = None) -> None:
        payload = json.dumps(message)
        if topic:
            self._client.publish(topic, payload)
            logger.debug(f"Published to topic {topic}: {message}")
        self._client.lpush(queue, payload)
        logger.debug(f"Enqueued to {queue}: {message}")

    def dequeue(self, queue: str, processing_queue: str, timeout: int = 5) -> Optional[str]:
        result = self._client.brpoplpush(queue, processing_queue, timeout=timeout)
        return result

    def parse_message(self, raw: str) -> dict:
        return json.loads(raw)

    def ack(self, processing_queue: str, raw_message: str) -> None:
        self._client.lrem(processing_queue, 1, raw_message)

    def nack(self, processing_queue: str, dlq: str, raw_message: str, max_retries: int = 3) -> None:
        self._client.lrem(processing_queue, 1, raw_message)
        msg = json.loads(raw_message)
        retry_count = msg.get("retry_count", 0)

        if retry_count < max_retries:
            msg["retry_count"] = retry_count + 1
            original_queue = processing_queue.replace("_processing", "_in")
            self._client.lpush(original_queue, json.dumps(msg))
            logger.warning(f"Retrying message (attempt {msg['retry_count']}/{max_retries})")
        else:
            msg["error_reason"] = "max_retries_exceeded"
            self._client.lpush(dlq, json.dumps(msg))
            logger.error(f"Message moved to DLQ {dlq}")

    def queue_length(self, queue: str) -> int:
        return self._client.llen(queue)
