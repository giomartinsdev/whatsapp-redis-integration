import sys
import os
import time
import uuid
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.infrastructure.queue import RedisQueue
from shared.infrastructure.queue_config import (
    WHATSAPP_IN, WHATSAPP_IN_PROCESSING, WHATSAPP_IN_DLQ,
    WHATSAPP_OUT, WHATSAPP_OUT_PROCESSING, WHATSAPP_OUT_DLQ,
    MAX_RETRIES
)
from shared.infrastructure.database import SessionLocal, Base, engine
from shared.infrastructure.models import WhatsappMessageOutcomeModel, WhatsappMessageIncomeModel
from shared.domain.entities.whatsapp_message import WhatsappMessage
from shared.infrastructure.telemetry import setup_telemetry, attach_otel_to_loggers
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

setup_telemetry("whatsapp_worker", "1.0.0")
attach_otel_to_loggers("whatsapp_worker", "sqlalchemy.engine")

RequestsInstrumentor().instrument()
SQLAlchemyInstrumentor().instrument(engine=engine)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("whatsapp_worker")


class WhatsappWorker:
    def __init__(self):
        self._queue = RedisQueue()
        # Initialize database tables if they do not exist
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS whatsapp_messages"))
                conn.commit()
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}")

    def run(self):
        logger.info("=" * 60)
        logger.info("WhatsApp Worker Starting...")
        logger.info("=" * 60)

        import threading
        threading.Thread(target=self._process_incoming_loop, daemon=True).start()

        while True:
            try:
                raw_msg = self._queue.dequeue(WHATSAPP_OUT, WHATSAPP_OUT_PROCESSING, timeout=5)
                if not raw_msg:
                    continue

                msg = self._queue.parse_message(raw_msg)
                
                try:
                    self._process_message(msg)
                    self._queue.ack(WHATSAPP_OUT_PROCESSING, raw_msg)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    self._queue.nack(WHATSAPP_OUT_PROCESSING, WHATSAPP_OUT_DLQ, raw_msg, MAX_RETRIES)

            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(5)

    def _process_incoming_loop(self):
        while True:
            try:
                raw_msg = self._queue.dequeue(WHATSAPP_IN, WHATSAPP_IN_PROCESSING, timeout=5)
                if not raw_msg:
                    continue

                msg = self._queue.parse_message(raw_msg)
                db = SessionLocal()
                try:
                    income_model = WhatsappMessageIncomeModel(
                        id=str(uuid.uuid4()),
                        cellphone=msg.get("from", "Unknown"),
                        message=msg.get("body", ""),
                        msg_type=msg.get("type", "text"),
                        media_data=msg.get("media_data"),
                        media_mime_type=msg.get("media_mime_type"),
                        media_filename=msg.get("media_filename"),
                        status="RECEIVED",
                        timestamp=str(msg.get("timestamp", ""))
                    )
                    db.add(income_model)
                    db.commit()
                    self._queue.ack(WHATSAPP_IN_PROCESSING, raw_msg)
                    
                    # Forward to an outgoing queue for the rest of the architecture to consume
                    payload = {
                        "id": income_model.id,
                        "cellphone": income_model.cellphone,
                        "message": income_model.message,
                        "msg_type": income_model.msg_type,
                        "media_data": income_model.media_data,
                        "media_mime_type": income_model.media_mime_type,
                        "media_filename": income_model.media_filename,
                        "status": income_model.status,
                        "timestamp": income_model.timestamp
                    }
                    # It seems we were writing to 'whatsapp_messages:income', we'll just write back to WHATSAPP_OUT for outbound delivery
                    # Or maybe kept isolated. I'll maintain exactly what it was before: "whatsapp_messages:income".
                    self._queue.enqueue("whatsapp_messages:income", payload)
                    logger.info(f"Saved incoming message from {msg.get('from')} to DB and sent to whatsapp_messages:income queue.")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Error saving incoming message: {e}")
                    self._queue.nack(WHATSAPP_IN_PROCESSING, WHATSAPP_IN_DLQ, raw_msg, MAX_RETRIES)
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Incoming worker loop error: {e}")
                time.sleep(5)

    def _process_message(self, msg: dict):
        cellphone = msg.get("cellphone")
        message_text = msg.get("message")
        msg_type = msg.get("type", "text")
        media_data = msg.get("media_data")
        media_mime_type = msg.get("media_mime_type")
        media_filename = msg.get("media_filename")

        if not cellphone or not message_text:
            raise ValueError("Invalid message payload, missing cellphone or message")

        # Create Domain Entity
        whatsapp_msg = WhatsappMessage(
            cellphone=cellphone,
            message=message_text,
            msg_type=msg_type,
            media_data=media_data,
            media_mime_type=media_mime_type,
            media_filename=media_filename
        )

        db = SessionLocal()
        try:
            # Save PENDING state to Outcome DB Table
            model = WhatsappMessageOutcomeModel.from_domain(whatsapp_msg)
            db.add(model)
            db.commit()
            
            import requests
            
            logger.info(f"Sending WhatsApp message to {cellphone}: {message_text} of type {msg_type}")
            node_resp = requests.post("http://whatsapp_node:3000/send", json={
                "cellphone": cellphone,
                "message": message_text,
                "type": msg_type,
                "media_data": media_data,
                "media_mime_type": media_mime_type,
                "media_filename": media_filename
            })
            
            if node_resp.status_code == 200:
                data = node_resp.json()
                message_code = data.get("message_code", uuid.uuid4().hex[:8].upper())
                whatsapp_msg.mark_as_sent(message_code)
            else:
                whatsapp_msg.mark_as_failed()
                raise Exception(f"Node JS failed to send message: {node_resp.text}")

            # Update DB with new state
            model.status = whatsapp_msg.status
            model.message_code = whatsapp_msg.message_code
            db.commit()
            
            logger.info(f"Message outcome saved to DB for {cellphone}")

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

if __name__ == "__main__":
    worker = WhatsappWorker()
    worker.run()
