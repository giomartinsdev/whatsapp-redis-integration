from dataclasses import dataclass, field
import uuid
from typing import Optional

@dataclass
class WhatsappMessage:
    cellphone: str
    message: str
    msg_type: str = "text"
    media_data: Optional[str] = None
    media_mime_type: Optional[str] = None
    media_filename: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "PENDING"
    message_code: Optional[str] = None

    def mark_as_sent(self, message_code: str):
        self.status = "SENT"
        self.message_code = message_code

    def mark_as_failed(self):
        self.status = "FAILED"
