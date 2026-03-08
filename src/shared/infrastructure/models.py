from sqlalchemy import Column, String
from shared.infrastructure.database import Base
from shared.domain.entities.whatsapp_message import WhatsappMessage

class WhatsappMessageOutcomeModel(Base):
    __tablename__ = "whatsapp_message_outcome"
    __table_args__ = {"schema": "whatsapp_messages"}

    id = Column(String(36), primary_key=True, index=True)
    cellphone = Column(String(50), nullable=False)
    message = Column(String, nullable=False)
    msg_type = Column(String(20), nullable=False, default="text")
    media_data = Column(String, nullable=True)
    media_mime_type = Column(String(100), nullable=True)
    media_filename = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False)
    message_code = Column(String(100), nullable=True)

    def to_domain(self) -> WhatsappMessage:
        return WhatsappMessage(
            id=self.id,
            cellphone=self.cellphone,
            message=self.message,
            msg_type=self.msg_type,
            media_data=self.media_data,
            media_mime_type=self.media_mime_type,
            media_filename=self.media_filename,
            status=self.status,
            message_code=self.message_code
        )

    @classmethod
    def from_domain(cls, entity: WhatsappMessage) -> "WhatsappMessageOutcomeModel":
        return cls(
            id=entity.id,
            cellphone=entity.cellphone,
            message=entity.message,
            msg_type=entity.msg_type,
            media_data=entity.media_data,
            media_mime_type=entity.media_mime_type,
            media_filename=entity.media_filename,
            status=entity.status,
            message_code=entity.message_code
        )

class WhatsappMessageIncomeModel(Base):
    __tablename__ = "whatsapp_message_income"
    __table_args__ = {"schema": "whatsapp_messages"}

    id = Column(String(36), primary_key=True, index=True)
    cellphone = Column(String(50), nullable=False)
    message = Column(String, nullable=True)
    msg_type = Column(String(20), nullable=False, default="text")
    media_data = Column(String, nullable=True)
    media_mime_type = Column(String(100), nullable=True)
    media_filename = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="RECEIVED")
    timestamp = Column(String(50), nullable=True)
