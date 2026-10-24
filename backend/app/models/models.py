from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Boolean,
    Numeric,
    Text,
    Date,
    ForeignKey,
    Computed,
    Index,
    text,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.core.database import Base
from app.core.config import settings

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Связи
    clients: Mapped[List["Client"]] = relationship(back_populates="manager")

class Client(Base):
    __tablename__ = 'clients'
    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    company_name: Mapped[str] = mapped_column(String(255))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    raw_manager_notes: Mapped[str] = mapped_column(Text)
    extracted_profile: Mapped[dict] = mapped_column(JSONB, server_default='{}')
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Связи
    manager: Mapped[Optional["User"]] = relationship(back_populates="clients")
    selections: Mapped[List["Selection"]] = relationship(back_populates="client", cascade="all, delete-orphan")

class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String(500))
    normalized_title: Mapped[str] = mapped_column(String(500))
    event_format: Mapped[str] = mapped_column(String(100))
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, server_default='false', default=False, nullable=False)
    venue: Mapped[Optional[str]] = mapped_column(String(255))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text)
    full_regulation_markdown: Mapped[Optional[str]] = mapped_column(Text)
    themes: Mapped[List[str]] = mapped_column(ARRAY(String), server_default='{}')
    source_urls: Mapped[list] = mapped_column(JSONB, server_default='[]')
    
    # Статус полноты данных (ready, needs_enrichment, archived) и предупреждения
    data_status: Mapped[str] = mapped_column(String(50), server_default='ready', default='ready')
    missing_data_warnings: Mapped[List[str]] = mapped_column(ARRAY(String), server_default='{}', default=list)
    
    # Генерация tsvector для FTS (Полнотекстовый поиск)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, 
        Computed("to_tsvector('russian', coalesce(canonical_title, '') || ' ' || coalesce(summary, ''))", persisted=True)
    )
    
    # Вектор эмбеддинга
    summary_embedding = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=True)

    __table_args__ = (
        CheckConstraint("city IS NOT NULL OR is_online = true", name="chk_events_city_or_online"),
        Index('idx_events_city_dates', 'city', 'start_date', postgresql_where=text('is_active = TRUE')),
        Index('idx_events_online', 'is_online', postgresql_where=text('is_active = TRUE AND is_online = TRUE')),
        Index('idx_events_fts', 'search_vector', postgresql_using='gin'),
        Index('idx_events_embedding', 'summary_embedding', postgresql_using='hnsw', postgresql_ops={'summary_embedding': 'vector_cosine_ops'}),
    )
    
    is_active: Mapped[bool] = mapped_column(Boolean, server_default='true')
    last_scraped_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Связи
    tariffs: Mapped[List["EventTariff"]] = relationship(back_populates="event", cascade="all, delete-orphan", lazy="selectin")
    chunks: Mapped[List["EventChunk"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    selection_items: Mapped[List["SelectionItem"]] = relationship(back_populates="event", cascade="all, delete-orphan")

class EventTariff(Base):
    __tablename__ = 'event_tariffs'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id', ondelete='CASCADE'))
    tariff_name: Mapped[str] = mapped_column(String(255))
    participation_role: Mapped[str] = mapped_column(String(50))
    base_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    early_bird_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    early_bird_deadline: Mapped[Optional[date]] = mapped_column(Date)
    is_vat_included: Mapped[bool] = mapped_column(Boolean, server_default='true')

    __table_args__ = (
        Index('idx_tariffs_event_price', 'event_id', 'base_price', 'early_bird_price'),
        Index('idx_tariffs_deadline', 'early_bird_deadline', postgresql_where=text('early_bird_deadline IS NOT NULL')),
    )

    included_benefits: Mapped[Optional[str]] = mapped_column(Text)

    # Связи
    event: Mapped["Event"] = relationship(back_populates="tariffs")

class EventChunk(Base):
    __tablename__ = 'event_chunks'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id', ondelete='CASCADE'))
    source_type: Mapped[str] = mapped_column(String(50))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, 
        Computed("to_tsvector('russian', content)", persisted=True)
    )

    __table_args__ = (
        Index('idx_chunks_event_id', 'event_id'),
        Index('idx_chunks_fts', 'search_vector', postgresql_using='gin'),
        Index('idx_chunks_embedding', 'embedding', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'}),
    )

    embedding = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=False)

    # Связи
    event: Mapped["Event"] = relationship(back_populates="chunks")

class Selection(Base):
    __tablename__ = 'selections'
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id', ondelete='CASCADE'))
    magic_token: Mapped[str] = mapped_column(UUID(as_uuid=True), unique=True, server_default=func.gen_random_uuid())
    status: Mapped[str] = mapped_column(String(50), server_default='draft')
    generated_pitch_text: Mapped[Optional[str]] = mapped_column(Text)
    total_budget_limit: Mapped[float] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Связи
    client: Mapped["Client"] = relationship(back_populates="selections")
    items: Mapped[List["SelectionItem"]] = relationship(back_populates="selection", cascade="all, delete-orphan", lazy="selectin")
    chat_messages: Mapped[List["ChatMessage"]] = relationship(back_populates="selection", cascade="all, delete-orphan")

class SelectionItem(Base):
    __tablename__ = 'selection_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey('selections.id', ondelete='CASCADE'))
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id', ondelete='CASCADE'))
    recommended_tariff_id: Mapped[Optional[int]] = mapped_column(ForeignKey('event_tariffs.id', ondelete='SET NULL'))
    bundle_group: Mapped[int] = mapped_column(Integer, server_default='1')
    ai_rationale: Mapped[Optional[str]] = mapped_column(Text)
    client_reaction: Mapped[str] = mapped_column(String(50), server_default='pending')
    client_comment: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Связи
    selection: Mapped["Selection"] = relationship(back_populates="items")
    event: Mapped["Event"] = relationship(back_populates="selection_items")
    recommended_tariff: Mapped[Optional["EventTariff"]] = relationship()

class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey('selections.id', ondelete='CASCADE'))
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id', ondelete='CASCADE'))
    sender_role: Mapped[str] = mapped_column(String(50))
    message_text: Mapped[str] = mapped_column(Text)
    needs_manager_attention: Mapped[bool] = mapped_column(Boolean, server_default='false')
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Связи
    selection: Mapped["Selection"] = relationship(back_populates="chat_messages")
    event: Mapped["Event"] = relationship()

class LLMCache(Base):
    __tablename__ = 'llm_cache'
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey('events.id', ondelete='CASCADE'))
    response_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Связи
    event: Mapped[Optional["Event"]] = relationship()