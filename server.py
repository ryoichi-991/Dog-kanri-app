import asyncio
import hashlib
import html
import io
import json
import os
import re
import secrets
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from mcp.server.fastmcp import FastMCP
from passlib.context import CryptContext
from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, and_, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pypdf import PdfReader
import pytesseract

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://app:app@db:5432/Dog_kanri_app")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "7"))
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
passwords = CryptContext(schemes=["argon2"], deprecated="auto")
MODULES = {
    "todo": ("Todoリスト", "日々の作業、期限、完了状況"),
    "calendar": ("カレンダー", "繁殖・健康・申請・販売の予定"),
    "legal": ("法令・行政書類", "定期報告、開始・更新・変更申請、法定帳簿"),
    "dogs": ("犬・血統書管理", "個体、マイクロチップ、血統書、親子関係"),
    "breeding": ("交配・近親交配率", "交配計画、係数計算、組み合わせ提案"),
    "births": ("出産・ヒート周期", "ヒート予測、交配日、出産、仔犬"),
    "health": ("健康・ワクチン", "体重、診療、予防接種、次回予定"),
    "genetics": ("遺伝子検査", "遺伝病検査結果と交配リスク"),
    "sales": ("仔犬販売管理", "問い合わせ、契約、説明、引渡し"),
}
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県",
    "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県", "海外",
]


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    admin = "admin"
    employee = "employee"
    customer = "customer"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SQLEnum(Role), default=Role.customer)  # 旧DB互換
    platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Membership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(SQLEnum(Role, name="membership_role"))


class Dog(Base):
    __tablename__ = "dogs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    call_name: Mapped[str] = mapped_column(String(100))
    registered_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    breed: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sex: Mapped[str] = mapped_column(String(10))
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    microchip_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pedigree_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    origin_registration_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    origin_registration_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    origin_registration_organization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    titles: Mapped[str | None] = mapped_column(Text, nullable=True)
    pedigree_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pedigree_organization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pedigree_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category: Mapped[str] = mapped_column(String(20), default="parent")
    status: Mapped[str] = mapped_column(String(30), default="resident")
    sire_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id"), nullable=True)
    dam_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PedigreeUpload(Base):
    __tablename__ = "pedigree_uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    file_data: Mapped[bytes] = mapped_column(LargeBinary)
    document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    registration_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), default="general")
    due_date: Mapped[date] = mapped_column(Date, index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    dog_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BreedingRecord(Base):
    __tablename__ = "breeding_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    sire_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    dam_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    mating_date: Mapped[date] = mapped_column(Date)
    coefficient: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Litter(Base):
    __tablename__ = "litters"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    breeding_id: Mapped[int | None] = mapped_column(ForeignKey("breeding_records.id"), nullable=True)
    dam_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    birth_date: Mapped[date] = mapped_column(Date)
    born_count: Mapped[int] = mapped_column(Integer, default=0)
    alive_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class HeatCycle(Base):
    __tablename__ = "heat_cycles"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class HealthRecord(Base):
    __tablename__ = "health_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    record_date: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(50))
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    clinic: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Vaccination(Base):
    __tablename__ = "vaccinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    vaccine_name: Mapped[str] = mapped_column(String(150))
    administered_on: Mapped[date] = mapped_column(Date)
    next_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    certificate_no: Mapped[str | None] = mapped_column(String(100), nullable=True)


class GeneticTest(Base):
    __tablename__ = "genetic_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    test_name: Mapped[str] = mapped_column(String(150))
    result: Mapped[str] = mapped_column(String(50))
    tested_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    laboratory: Mapped[str | None] = mapped_column(String(150), nullable=True)


class Medication(Base):
    __tablename__ = "medications"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    medicine_name: Mapped[str] = mapped_column(String(150))
    administered_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DiseaseHistory(Base):
    __tablename__ = "disease_histories"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    disease_name: Mapped[str] = mapped_column(String(150))
    diagnosed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    treatment_started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    treatment_ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class FoodHistory(Base):
    __tablename__ = "food_histories"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    name_kana: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PuppySale(Base):
    __tablename__ = "puppy_sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(150))
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inquiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    inquiry_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    next_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    handover_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deposit_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    microchip_transfer_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="inquiry")


class DogTransfer(Base):
    __tablename__ = "dog_transfers"
    __table_args__ = (UniqueConstraint("tenant_id", "dog_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    transferred_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DogOwnership(Base):
    __tablename__ = "dog_ownerships"
    __table_args__ = (UniqueConstraint("tenant_id", "dog_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    relationship: Mapped[str] = mapped_column(String(30), default="primary")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyDogProfile(Base):
    __tablename__ = "family_dog_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), unique=True, index=True)
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    introduction: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyDogAlbumItem(Base):
    __tablename__ = "family_dog_album_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    photo_data: Mapped[bytes] = mapped_column(LargeBinary)
    photo_content_type: Mapped[str] = mapped_column(String(50), default="image/jpeg")
    taken_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    caption: Mapped[str | None] = mapped_column(String(300), nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OwnerInvitation(Base):
    __tablename__ = "owner_invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    relationship: Mapped[str] = mapped_column(String(30), default="primary")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OwnerProfile(Base):
    __tablename__ = "owner_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(60), nullable=True)
    prefecture: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    profile_public: Mapped[bool] = mapped_column(Boolean, default=False)
    show_nickname: Mapped[bool] = mapped_column(Boolean, default=True)
    show_prefecture: Mapped[bool] = mapped_column(Boolean, default=False)
    show_bio: Mapped[bool] = mapped_column(Boolean, default=False)
    show_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    show_dogs: Mapped[bool] = mapped_column(Boolean, default=False)
    show_parents: Mapped[bool] = mapped_column(Boolean, default=False)
    show_relatives: Mapped[bool] = mapped_column(Boolean, default=False)
    instagram_username: Mapped[str | None] = mapped_column(String(30), nullable=True)
    show_instagram: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyAnnouncement(Base):
    __tablename__ = "family_announcements"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(Text)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FamilyAnnouncementRead(Base):
    __tablename__ = "family_announcement_reads"
    __table_args__ = (UniqueConstraint("announcement_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("family_announcements.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyConversation(Base):
    __tablename__ = "family_conversations"
    __table_args__ = (UniqueConstraint("tenant_id", "user1_id", "user2_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user1_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user2_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyMessage(Base):
    __tablename__ = "family_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("family_conversations.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(1000))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FamilyMessageRead(Base):
    __tablename__ = "family_message_reads"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("family_conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyMessageBlock(Base):
    __tablename__ = "family_message_blocks"
    __table_args__ = (UniqueConstraint("tenant_id", "blocker_id", "blocked_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    blocker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyMessageAudit(Base):
    __tablename__ = "family_message_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("family_conversations.id", ondelete="CASCADE"), index=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(50))
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class LegalDocument(Base):
    __tablename__ = "legal_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_type: Mapped[str] = mapped_column(String(100))
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def db():
    with SessionLocal() as session:
        yield session


def normalize_email(value: str) -> str:
    return value.strip().lower()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def platform_admin_exists(session: Session) -> bool:
    return session.scalar(select(User.id).where(User.platform_admin.is_(True)).limit(1)) is not None


def current_user(request: Request, session: Session = Depends(db)) -> User | None:
    token = request.cookies.get("dog_session")
    if not token:
        return None
    login = session.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash(token)))
    if not login:
        return None
    expires = login.expires_at if login.expires_at.tzinfo else login.expires_at.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        session.delete(login)
        session.commit()
        return None
    user = session.get(User, login.user_id)
    return user if user and user.active else None


def require_user(user: User | None = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def accessible_tenants(user: User, session: Session) -> list[Tenant]:
    query = select(Tenant).where(Tenant.active.is_(True), Tenant.deleted.is_(False)).order_by(Tenant.name)
    if not user.platform_admin:
        query = query.join(Membership).where(Membership.user_id == user.id)
    return list(session.scalars(query).all())


def selected_tenant(request: Request, user: User, session: Session) -> Tenant | None:
    tenants = accessible_tenants(user, session)
    if not tenants:
        return None
    try:
        requested = int(request.cookies.get("tenant_id", "0"))
    except ValueError:
        requested = 0
    return next((t for t in tenants if t.id == requested), tenants[0])


def tenant_role(user: User, tenant: Tenant | None, session: Session) -> Role | None:
    if user.platform_admin:
        return Role.admin
    if not tenant:
        return None
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant.id))
    return membership.role if membership else None


def require_tenant_admin(request: Request, user: User = Depends(require_user), session: Session = Depends(db)):
    tenant = selected_tenant(request, user, session)
    if not tenant or tenant_role(user, tenant, session) != Role.admin:
        raise HTTPException(status_code=403, detail="このテナントの管理権限がありません")
    return user, tenant


def require_tenant_user(request: Request, user: User = Depends(require_user), session: Session = Depends(db)):
    tenant = selected_tenant(request, user, session)
    if not tenant or tenant_role(user, tenant, session) is None:
        raise HTTPException(status_code=403, detail="利用できるテナントがありません")
    return user, tenant


def layout(title: str, body: str, user: User | None = None, owner_mode: bool = False, notification_count: int = 0) -> str:
    nav = ""
    body_class = "owner-view" if user and owner_mode else ("authenticated" if user else "guest")
    if user and owner_mode:
        notification_badge = f'<span class="nav-count">{notification_count}</span>' if notification_count else ""
        nav = f'''<header class="owner-header"><a class="owner-brand" href="/family"><strong>ESTRELLA FAMILY</strong></a>
        <nav><a href="/family">うちの子</a><a href="/family/notifications">通知{notification_badge}</a><a href="/family/messages">メッセージ</a><a href="/family/announcements">お知らせ</a><a href="/family/timeline">タイムライン</a><a href="/family/anniversaries">記念日</a><a href="/family/relatives">兄弟・親戚犬</a><a href="/family/kennel">犬舎FAMILY会</a><a href="/family/profile">プロフィール設定</a></nav>
        <div class="owner-account"><span>{html.escape(user.name)}</span><form method="post" action="/logout"><button>ログアウト</button></form></div></header>'''
    elif user:
        platform_link = '<a href="/platform/tenants"><span>◆</span>テナント管理</a>' if user.platform_admin else ""
        nav = f'''<aside class="sidebar">
        <a class="brand" href="/dashboard"><span class="brand-logo-wrap"><img class="brand-logo" src="https://estrella.dog/wp-content/uploads/2025/10/logo-1.svg" alt="ESTRELLA ロゴ"></span><span><strong>ESTRELLA</strong><small>Breeder Management</small></span></a>
        <nav>
          <p class="nav-label">メイン</p>
          <a href="/dashboard"><span>⌂</span>ダッシュボード</a>
          <a href="/family"><span>♢</span>FAMILY</a>
          <a href="/modules/todo"><span>✓</span>Todoリスト</a>
          <a href="/modules/calendar"><span>▦</span>カレンダー</a>
          <p class="nav-label">繁殖・生体</p>
          <a href="/modules/resident-dogs"><span>🐕</span>在籍犬一覧</a>
          <a href="/modules/dog-list/puppy"><span>◌</span>仔犬一覧</a>
          <a href="/modules/sale-dogs"><span>¥</span>販売犬一覧</a>
          <a href="/modules/transferred-dogs"><span>↗</span>譲渡済一覧</a>
          <a href="/modules/dog-list/parent"><span>♙</span>親犬一覧</a>
          <a href="/modules/dog-list/external"><span>◇</span>外部犬一覧</a>
          <a href="/modules/breeding"><span>♡</span>ヒート・交配管理</a>
          <a href="/modules/births"><span>✦</span>出産管理</a>
          <a href="/modules/genetics"><span>⌘</span>遺伝子・交配分析</a>
          <a href="/modules/dogs"><span>●</span>犬・血統書管理</a>
          <p class="nav-label">業務管理</p>
          <a href="/modules/health"><span>＋</span>健康管理</a>
          <a href="/modules/sales"><span>¥</span>販売管理</a>
          <a href="/modules/legal"><span>▤</span>法令・行政書類</a>
          <p class="nav-label">管理設定</p>
          <a href="/admin/users"><span>♙</span>ユーザー管理</a>
          <a href="/family/announcements/manage"><span>◇</span>FAMILYお知らせ</a>
          <a href="/family/messages/manage"><span>✉</span>メッセージ管理</a>
          {platform_link}
        </nav>
        <div class="sidebar-user"><div class="avatar">{html.escape(user.name[:1])}</div><div><strong>{html.escape(user.name)}</strong><small>{"運営管理者" if user.platform_admin else "ユーザー"}</small></div><form method="post" action="/logout"><button title="ログアウト">↪</button></form></div>
        </aside>'''
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--wine:#704454;--rose:#b66f7c;--rose-light:#ead0d5;--cream:#faf6f3;--paper:#fffdfb;--ink:#3f3036;--muted:#816f76;--line:#eadfe1;--green:#718b75;--danger:#a94f55}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--cream);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;line-height:1.55}}.sidebar{{position:fixed;inset:0 auto 0 0;width:260px;background:linear-gradient(180deg,#68404f 0%,#55333f 100%);color:#fff;display:flex;flex-direction:column;z-index:10;box-shadow:6px 0 24px #4b26331a}}.brand{{height:84px;display:flex;align-items:center;gap:13px;padding:18px 22px;color:#fff;text-decoration:none;border-bottom:1px solid #ffffff1f}}.brand-mark{{display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:#f0d8dc;color:var(--wine);font-family:Georgia,serif;font-size:25px}}.brand strong{{display:block;letter-spacing:1.8px;font-family:Georgia,serif}}.brand small,.sidebar-user small{{display:block;color:#ead5da;font-size:11px}}.sidebar nav{{padding:12px 13px;overflow-y:auto;flex:1}}.sidebar nav a{{display:flex;align-items:center;gap:12px;color:#f8eef1;text-decoration:none;padding:10px 13px;border-radius:10px;font-size:14px;margin:2px 0}}.sidebar nav a:hover{{background:#ffffff17;color:#fff}}.sidebar nav a span{{width:20px;text-align:center;color:#eac3cb}}.nav-label{{margin:14px 12px 5px;color:#cbaeb5;font-size:10px;letter-spacing:1.5px;font-weight:700}}.sidebar-user{{display:flex;align-items:center;gap:10px;padding:15px;border-top:1px solid #ffffff1f;background:#452934}}.sidebar-user .avatar{{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:#e7c6cc;color:var(--wine);font-weight:700}}.sidebar-user strong{{display:block;max-width:125px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}}.sidebar-user form{{margin-left:auto}}.sidebar-user button{{margin:0;padding:8px;background:transparent;color:#fff;font-size:18px}}main{{max-width:1280px;margin-left:260px;padding:38px 42px}}.card{{background:var(--paper);padding:34px;border:1px solid #f1e7e8;border-radius:20px;box-shadow:0 10px 35px #63404c0d}}h1{{margin:0 0 22px;font-size:28px;letter-spacing:.02em}}h2{{margin-top:34px;padding-bottom:8px;border-bottom:1px solid var(--line);font-size:20px}}label{{display:block;margin:15px 0 6px;font-size:13px;font-weight:650;color:#665159}}input,select,textarea{{width:100%;padding:11px 13px;border:1px solid #dacdd0;border-radius:10px;background:#fff;font-size:15px;color:var(--ink);outline:none}}input:focus,select:focus,textarea:focus{{border-color:var(--rose);box-shadow:0 0 0 3px #b66f7c18}}textarea{{min-height:84px;resize:vertical}}button,.button{{display:inline-block;margin-top:17px;padding:11px 18px;border:0;border-radius:10px;background:var(--rose);color:#fff;text-decoration:none;font-weight:650;cursor:pointer;box-shadow:0 4px 12px #b66f7c28}}button:hover,.button:hover{{filter:brightness(.95)}}.secondary{{background:#89747b}}.danger{{background:var(--danger)}}.success{{background:var(--green)}}.inline{{display:inline}}.inline button{{margin:3px;padding:7px 10px;font-size:12px}}.error{{background:#fff0f0;color:#963c43;padding:13px;border-left:4px solid var(--danger);border-radius:8px}}table{{width:100%;border-collapse:separate;border-spacing:0;margin-top:18px;font-size:14px;overflow:hidden}}th{{background:#f6edef;color:#694d57;font-size:12px;letter-spacing:.03em}}th,td{{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line)}}tr:hover td{{background:#fdf8f8}}.badge{{display:inline-block;padding:5px 10px;border-radius:99px;background:var(--rose-light);color:var(--wine);font-size:12px;font-weight:700}}.tenant{{padding:18px;background:#f7edef;border:1px solid #ecdadd;border-radius:14px;margin-bottom:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:18px}}.module{{position:relative;display:block;min-height:118px;padding:21px;border:1px solid var(--line);border-radius:15px;text-decoration:none;color:var(--ink);background:linear-gradient(145deg,#fff 0%,#fdf8f7 100%);transition:.2s}}.module:after{{content:"›";position:absolute;right:18px;top:15px;color:#c18a94;font-size:24px}}.module:hover{{transform:translateY(-2px);border-color:#d6a7af;box-shadow:0 9px 22px #70445414}}.module h3{{margin:0 25px 9px 0;font-size:17px;color:#66404e}}.module p{{margin:0;color:var(--muted);font-size:13px}}
.brand-logo-wrap{{width:48px;height:48px;flex:0 0 48px;overflow:hidden;display:grid;place-items:center}}.brand-logo{{display:block;width:48px;height:48px;object-fit:contain}}.title-crown{{display:inline-flex;align-items:center;gap:2px;margin:2px 5px 2px 0;font-size:20px;font-weight:800}}.title-crown small{{font-size:9px;color:var(--ink)}}.crown-silver{{color:#9da3aa;text-shadow:0 1px #fff}}.crown-gold{{color:#d4a72c;text-shadow:0 1px #fff}}.crown-rose{{color:#cf788b}}.crown-purple{{color:#9167a8}}.crown-blue{{color:#668caf}}.guest main{{max-width:760px;margin:45px auto;padding:24px}}
.owner-header{{position:sticky;top:0;z-index:20;min-height:68px;padding:11px 28px;background:#633b4a;color:#fff;display:flex;align-items:center;gap:28px;box-shadow:0 5px 20px #4b263326}}.owner-brand{{color:#fff;text-decoration:none;font-family:Georgia,serif;letter-spacing:1.3px;white-space:nowrap}}.owner-header nav{{display:flex;gap:7px;flex:1}}.owner-header nav a{{color:#f8eef1;text-decoration:none;padding:9px 12px;border-radius:9px}}.owner-header nav a:hover{{background:#ffffff17}}.owner-account{{display:flex;align-items:center;gap:10px;font-size:13px}}.owner-account form{{margin:0}}.owner-account button{{margin:0;padding:8px 12px;background:#ffffff1c;box-shadow:none}}.owner-view main{{margin:0 auto;max-width:1180px;padding:34px 28px}}
.nav-count{{display:inline-grid;place-items:center;min-width:19px;height:19px;margin-left:4px;padding:0 5px;border-radius:10px;background:#fff;color:var(--wine);font-size:11px;font-weight:800}}.notification-item{{display:block;margin:12px 0;padding:18px;border:1px solid var(--line);border-radius:14px;background:#fff;color:var(--ink);text-decoration:none}}.notification-item.unread{{border-left:5px solid var(--rose);background:#fffafb}}.notification-item p{{margin:5px 0}}.notification-kind{{display:inline-block;margin-right:7px;color:var(--wine);font-size:12px;font-weight:750}}
.family-photo-stage{{width:100%;min-height:260px;max-height:70vh;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:18px;background:linear-gradient(145deg,#f7edef,#fff);border:1px solid var(--line);margin-bottom:18px}}.family-dog-photo{{display:block;max-width:100%;max-height:70vh;width:auto;height:auto;object-fit:contain}}.family-dog-thumb{{display:block;width:100%;height:190px;object-fit:contain;border-radius:12px;margin-bottom:12px;background:#f7edef}}
.album-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;margin:18px 0}}.album-item{{overflow:hidden;border:1px solid var(--line);border-radius:15px;background:#fff}}.album-item a{{display:flex;height:210px;align-items:center;justify-content:center;background:#f7edef}}.album-item img{{display:block;max-width:100%;max-height:210px;width:auto;height:auto;object-fit:contain}}.album-meta{{padding:13px}}.album-meta p{{margin:5px 0}}.album-meta form button{{margin-top:8px}}
@media(max-width:850px){{.sidebar{{position:relative;width:100%;height:auto}}.sidebar nav{{display:grid;grid-template-columns:repeat(2,1fr)}}.nav-label{{grid-column:1/-1}}.sidebar-user{{display:none}}main{{margin-left:0;padding:20px 14px}}.card{{padding:22px}}.brand{{height:70px}}.owner-header{{position:relative;display:block;padding:14px}}.owner-header nav{{display:grid;grid-template-columns:repeat(2,1fr);gap:3px;margin-top:10px}}.owner-header nav a{{padding:8px 4px;text-align:center;font-size:12px}}.owner-account{{position:absolute;right:12px;top:9px}}.owner-account span{{display:none}}.owner-account button{{font-size:11px;padding:6px 8px}}.owner-view main{{padding:15px 10px}}}}
</style></head><body class="{body_class}">{nav}<main><div class="card">{body}</div></main></body></html>'''


def family_layout(title: str, body: str, user: User, session: Session) -> str:
    """運営管理者・犬舎スタッフ以外には業務用サイドバーを表示しない。"""
    has_business_role = user.platform_admin or session.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id,
            Membership.role.in_([Role.admin, Role.employee]),
        ).limit(1)
    ) is not None
    owner_mode = not has_business_role
    count = family_notification_count(user, session) if owner_mode else 0
    return layout(title, body, user, owner_mode=owner_mode, notification_count=count)


mcp = FastMCP("Dog-kanri-app")


@mcp.tool()
def db_now() -> str:
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT now()")).scalar())


app = FastAPI(title="Dog-kanri-app")


@app.on_event("startup")
def startup():
    # 既存DBへ安全に列を追加してから、新テーブルを作る。
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS platform_admin BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS category VARCHAR(20) NOT NULL DEFAULT 'parent'"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'resident'"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS titles TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS pedigree_country VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS pedigree_organization VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS pedigree_updated_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS breed VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS origin_registration_no VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS origin_registration_country VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS dogs ADD COLUMN IF NOT EXISTS origin_registration_organization VARCHAR(100)"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE IF EXISTS pedigree_uploads ADD COLUMN IF NOT EXISTS document_type VARCHAR(50)"))
        conn.execute(text("ALTER TABLE IF EXISTS pedigree_uploads ADD COLUMN IF NOT EXISTS registration_no VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS pedigree_uploads ADD COLUMN IF NOT EXISTS organization VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS pedigree_uploads ADD COLUMN IF NOT EXISTS country VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS pedigree_uploads ADD COLUMN IF NOT EXISTS issued_on DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS pedigree_uploads ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS inquiry_date DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS inquiry_channel VARCHAR(50)"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS next_action_date DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS contract_no VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS deposit_amount INTEGER"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS paid_amount INTEGER"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS explanation_completed BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS microchip_transfer_completed BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS puppy_sales ADD COLUMN IF NOT EXISTS notes TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_profiles ADD COLUMN IF NOT EXISTS show_dogs BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_profiles ADD COLUMN IF NOT EXISTS show_parents BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_profiles ADD COLUMN IF NOT EXISTS show_relatives BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_profiles ADD COLUMN IF NOT EXISTS instagram_username VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_profiles ADD COLUMN IF NOT EXISTS show_instagram BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS dog_transfers ADD COLUMN IF NOT EXISTS amount INTEGER"))
    with SessionLocal() as session:
        # 旧管理者がいる場合は最初の1人を運営管理者へ自動昇格する。
        if not platform_admin_exists(session):
            legacy = session.scalar(select(User).where(User.role == Role.admin).order_by(User.id).limit(1))
            if legacy:
                legacy.platform_admin = True
                session.commit()
        # 旧ユーザーを消さず、初期テナントへ所属させる。
        users = list(session.scalars(select(User)).all())
        if users and not session.scalar(select(Tenant.id).limit(1)):
            tenant = Tenant(name="初期テナント")
            session.add(tenant)
            session.flush()
            for user in users:
                session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=user.role))
            session.commit()


@app.get("/", response_class=HTMLResponse)
def index(user: User | None = Depends(current_user), session: Session = Depends(db)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    if not platform_admin_exists(session):
        return RedirectResponse("/setup", status_code=303)
    return layout("Dog管理アプリ", '<h1>Dog管理アプリ</h1><p>複数の会社・犬舎を安全に管理します。</p><a class="button" href="/login">ログイン</a>　<a href="/register">お客様登録</a>')


@app.get("/setup", response_class=HTMLResponse)
def setup_page(session: Session = Depends(db)):
    if platform_admin_exists(session):
        return RedirectResponse("/login", status_code=303)
    return layout("初期設定", '<h1>初期運営管理者登録</h1><form method="post"><label>お名前</label><input name="name" required maxlength="100"><label>メールアドレス</label><input name="email" type="email" required><label>最初の会社・犬舎名</label><input name="tenant_name" required maxlength="150"><label>パスワード（8文字以上）</label><input name="password" type="password" minlength="8" required><button>登録する</button></form>')


@app.post("/setup", response_class=HTMLResponse)
def setup(name: str = Form(...), email: str = Form(...), tenant_name: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    if len(password) < 8:
        return layout("エラー", '<p class="error">パスワードは8文字以上にしてください。</p><a href="/setup">戻る</a>')
    session.execute(text("SELECT pg_advisory_xact_lock(20260824)"))
    if platform_admin_exists(session):
        session.rollback()
        return RedirectResponse("/login", status_code=303)
    email = normalize_email(email)
    if session.scalar(select(User).where(User.email == email)):
        session.rollback()
        return layout("エラー", '<p class="error">このメールアドレスは既に登録されています。</p>')
    user = User(name=name.strip(), email=email, password_hash=passwords.hash(password), role=Role.admin, platform_admin=True)
    tenant = Tenant(name=tenant_name.strip())
    session.add_all([user, tenant])
    session.flush()
    session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=Role.admin))
    session.commit()
    return RedirectResponse("/login?setup=1", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page():
    return layout("お客様登録", '<h1>お客様登録</h1><p>登録後、テナント管理者から所属追加を受けてください。</p><form method="post"><label>お名前</label><input name="name" required maxlength="100"><label>メールアドレス</label><input name="email" type="email" required><label>パスワード（8文字以上）</label><input name="password" type="password" minlength="8" required><button>登録する</button></form>')


@app.post("/register", response_class=HTMLResponse)
def register(name: str = Form(...), email: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    email = normalize_email(email)
    if len(password) < 8 or session.scalar(select(User).where(User.email == email)):
        return layout("登録エラー", '<p class="error">メールアドレスの重複、またはパスワードの長さを確認してください。</p><a href="/register">戻る</a>')
    session.add(User(name=name.strip(), email=email, password_hash=passwords.hash(password), role=Role.customer))
    session.commit()
    return RedirectResponse("/login?registered=1", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(registered: int = 0, setup: int = 0):
    notice = "<p>初期設定が完了しました。</p>" if setup else ("<p>登録が完了しました。</p>" if registered else "")
    return layout("ログイン", f'<h1>ログイン</h1>{notice}<form method="post"><label>メールアドレス</label><input name="email" type="email" required><label>パスワード</label><input name="password" type="password" required><button>ログイン</button></form>')


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not user.active or not passwords.verify(password, user.password_hash):
        return HTMLResponse(layout("ログイン", '<p class="error">メールアドレスまたはパスワードが違います。</p><a href="/login">戻る</a>'))
    raw = secrets.token_urlsafe(32)
    session.add(LoginSession(token_hash=token_hash(raw), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    session.commit()
    has_tenant = bool(accessible_tenants(user, session))
    has_dog = session.scalar(select(DogOwnership.id).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True)).limit(1)) is not None
    response = RedirectResponse("/dashboard" if has_tenant or not has_dog else "/family", status_code=303)
    response.set_cookie("dog_session", raw, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=SESSION_DAYS * 86400)
    return response


@app.post("/logout")
def logout(request: Request, session: Session = Depends(db)):
    raw = request.cookies.get("dog_session")
    if raw:
        login_session = session.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash(raw)))
        if login_session:
            session.delete(login_session)
            session.commit()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("dog_session")
    response.delete_cookie("tenant_id")
    return response


@app.post("/tenant/switch")
def switch_tenant(tenant_id: int = Form(...), user: User = Depends(require_user), session: Session = Depends(db)):
    if not any(t.id == tenant_id for t in accessible_tenants(user, session)):
        raise HTTPException(status_code=403, detail="このテナントへ切り替える権限がありません")
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("tenant_id", str(tenant_id), httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(require_user), session: Session = Depends(db)):
    tenants = accessible_tenants(user, session)
    if not tenants and session.scalar(select(DogOwnership.id).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True)).limit(1)) is not None:
        return RedirectResponse("/family", status_code=303)
    tenant = selected_tenant(request, user, session)
    options = "".join(f'<option value="{t.id}" {"selected" if tenant and t.id == tenant.id else ""}>{html.escape(t.name)}</option>' for t in tenants)
    switcher = f'<div class="tenant"><form method="post" action="/tenant/switch"><label>表示する会社・犬舎</label><select name="tenant_id">{options}</select><button>切り替える</button></form></div>' if tenants else '<p class="error">所属テナントがありません。管理者へ連絡してください。</p>'
    role = tenant_role(user, tenant, session)
    label = "運営管理者" if user.platform_admin else ({Role.admin: "管理者", Role.employee: "従業員", Role.customer: "お客様"}.get(role, "未所属"))
    dog_count = session.scalar(select(func.count(Dog.id)).where(Dog.tenant_id == tenant.id, Dog.active.is_(True))) if tenant else 0
    module_cards = ""
    if tenant:
        for key, (title, description) in MODULES.items():
            extra = f"（登録 {dog_count}頭）" if key == "dogs" else ""
            module_cards += f'<a class="module" href="/modules/{key}"><h3>{title}</h3><p>{description}{extra}</p></a>'
    body = f'<h1>{html.escape(user.name)}さん、こんにちは</h1>{switcher}<p><span class="badge">{label}</span></p>'
    if tenant:
        body += f'<h2>{html.escape(tenant.name)} 業務ホーム</h2><div class="grid">{module_cards}</div>'
    return layout("ホーム", body, user)


@app.get("/modules/todo", response_class=HTMLResponse)
def todo_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    tasks = session.scalars(select(TaskEvent).where(TaskEvent.tenant_id == tenant.id).order_by(TaskEvent.completed, TaskEvent.due_date)).all()
    category_labels = {"general": "一般", "care": "お世話", "customer": "お客様対応", "breeding": "繁殖", "health": "健康", "legal": "申請"}
    rows = ""
    for task in tasks:
        state = "完了" if task.completed else "未実施"
        rows += f'<tr><td>{task.due_date}</td><td>{html.escape(task.title)}</td><td>{category_labels.get(task.category, task.category)}</td><td>{state}</td><td><form class="inline" method="post" action="/modules/todo/{task.id}/toggle"><button class="{"secondary" if task.completed else "success"}">{"未完了に戻す" if task.completed else "完了"}</button></form></td></tr>'
    body = f'''<h1>Todoリスト</h1><form method="post"><div class="grid"><div><label>予定日</label><input type="date" name="due_date" required></div><div><label>タイトル</label><input name="title" required></div><div><label>カテゴリー</label><select name="category"><option value="general">一般</option><option value="care">お世話</option><option value="customer">お客様対応</option><option value="breeding">繁殖</option><option value="health">健康</option><option value="legal">申請</option></select></div></div><label>メモ</label><textarea name="notes"></textarea><button>予定を追加</button></form><table><tr><th>日付</th><th>内容</th><th>分類</th><th>状態</th><th>操作</th></tr>{rows}</table>'''
    return layout("Todoリスト", body, user)


@app.post("/modules/todo")
def todo_create(title: str = Form(...), due_date: str = Form(...), category: str = Form("general"), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    if category not in {"general", "care", "customer", "breeding", "health", "legal"}:
        raise HTTPException(status_code=400)
    session.add(TaskEvent(tenant_id=tenant.id, title=title.strip(), due_date=date.fromisoformat(due_date), category=category, notes=notes.strip() or None))
    session.commit()
    return RedirectResponse("/modules/todo", status_code=303)


@app.post("/modules/todo/{task_id}/toggle")
def todo_toggle(task_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    task = session.scalar(select(TaskEvent).where(TaskEvent.id == task_id, TaskEvent.tenant_id == tenant.id))
    if not task:
        raise HTTPException(status_code=404)
    task.completed = not task.completed
    session.commit()
    return RedirectResponse("/modules/todo", status_code=303)


@app.get("/modules/calendar", response_class=HTMLResponse)
def calendar_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    tasks = session.scalars(select(TaskEvent).where(TaskEvent.tenant_id == tenant.id).order_by(TaskEvent.due_date)).all()
    rows = "".join(f'<tr><td>{t.due_date}</td><td>{html.escape(t.title)}</td><td>{html.escape(t.category)}</td><td>{"完了" if t.completed else "予定"}</td></tr>' for t in tasks)
    return layout("カレンダー", f'<h1>カレンダー</h1><p>今後、ヒート・交配・出産・ワクチン・申請期限も自動表示されます。</p><table><tr><th>日付</th><th>予定</th><th>分類</th><th>状態</th></tr>{rows}</table><a class="button" href="/modules/todo">予定を登録</a>', user)


@app.get("/modules/breeding", response_class=HTMLResponse)
def breeding_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    females = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.sex == "female", Dog.active.is_(True)).order_by(Dog.call_name)).all()
    males = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.sex == "male", Dog.active.is_(True)).order_by(Dog.call_name)).all()
    heats = session.scalars(select(HeatCycle).where(HeatCycle.tenant_id == tenant.id).order_by(HeatCycle.start_date.desc())).all()
    breedings = session.scalars(select(BreedingRecord).where(BreedingRecord.tenant_id == tenant.id).order_by(BreedingRecord.mating_date.desc())).all()
    female_options = "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in females)
    male_options = "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in males)
    heat_rows = ""
    for heat in heats:
        dog = session.get(Dog, heat.dog_id)
        heat_rows += f"<tr><td>{html.escape(dog.call_name)}</td><td>{heat.start_date}</td><td>{heat.start_date + timedelta(days=180)}</td></tr>"
    breeding_rows = ""
    for record in breedings:
        sire, dam = session.get(Dog, record.sire_id), session.get(Dog, record.dam_id)
        coefficient = f"{record.coefficient:.2f}%" if record.coefficient is not None else "-"
        breeding_rows += f"<tr><td>{html.escape(dam.call_name)}</td><td>{html.escape(sire.call_name)}</td><td>{record.mating_date}</td><td>{record.mating_date + timedelta(days=63)}</td><td>{coefficient}</td><td>{html.escape(record.status)}</td></tr>"
    body = f'''<h1>交配・ヒート管理</h1>
    <h2>ヒート記録</h2><form method="post" action="/modules/breeding/heat"><div class="grid"><div><label>母犬</label><select name="dog_id" required>{female_options}</select></div><div><label>ヒート開始日</label><input name="start_date" type="date" required></div></div><label>メモ</label><textarea name="notes"></textarea><button>ヒートを登録</button></form>
    <table><tr><th>母犬</th><th>開始日</th><th>次回予測</th></tr>{heat_rows}</table>
    <h2>交配記録</h2><form method="post" action="/modules/breeding/mating"><div class="grid"><div><label>母犬</label><select name="dam_id" required>{female_options}</select></div><div><label>父犬</label><select name="sire_id" required>{male_options}</select></div><div><label>1回目交配日</label><input name="mating_date" type="date" required></div><div><label>交配方法</label><select name="method"><option value="natural">自然交配</option><option value="artificial">人工授精</option></select></div></div><label>メモ</label><textarea name="notes"></textarea><button>交配を登録</button></form>
    <table><tr><th>母犬</th><th>父犬</th><th>交配日</th><th>出産予定日</th><th>近親交配率</th><th>状態</th></tr>{breeding_rows}</table>
    <h2>交配シミュレーション</h2><form method="post" action="/modules/breeding/simulation"><div class="grid"><div><label>母犬</label><select name="dam_id">{female_options}</select></div><div><label>父犬</label><select name="sire_id">{male_options}</select></div></div><button>近親交配率と遺伝病リスクを計算</button></form>'''
    return layout("交配・ヒート管理", body, user)


@app.post("/modules/breeding/heat")
def heat_create(dog_id: int = Form(...), start_date: str = Form(...), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = session.scalar(select(Dog).where(Dog.id == dog_id, Dog.tenant_id == tenant.id, Dog.sex == "female"))
    if not dog:
        raise HTTPException(status_code=400, detail="母犬が見つかりません")
    started = date.fromisoformat(start_date)
    session.add(HeatCycle(tenant_id=tenant.id, dog_id=dog.id, start_date=started, notes=notes.strip() or None))
    session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} 次回ヒート予測", category="breeding", due_date=started + timedelta(days=180)))
    session.commit()
    return RedirectResponse("/modules/breeding", status_code=303)


@app.post("/modules/breeding/mating")
def mating_create(dam_id: int = Form(...), sire_id: int = Form(...), mating_date: str = Form(...), method: str = Form("natural"), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dam = session.scalar(select(Dog).where(Dog.id == dam_id, Dog.tenant_id == tenant.id, Dog.sex == "female"))
    sire = session.scalar(select(Dog).where(Dog.id == sire_id, Dog.tenant_id == tenant.id, Dog.sex == "male"))
    if not dam or not sire or dam.id == sire.id or method not in {"natural", "artificial"}:
        raise HTTPException(status_code=400, detail="交配情報を確認してください")
    mated = date.fromisoformat(mating_date)
    note = f"交配方法: {'自然交配' if method == 'natural' else '人工授精'}"
    if notes.strip():
        note += "\n" + notes.strip()
    coefficient = offspring_coefficient(session, tenant.id, sire.id, dam.id) * 100
    session.add(BreedingRecord(tenant_id=tenant.id, sire_id=sire.id, dam_id=dam.id, mating_date=mated, coefficient=coefficient, status="mated", notes=note))
    session.add(TaskEvent(tenant_id=tenant.id, dog_id=dam.id, title=f"{dam.call_name} 出産予定", category="breeding", due_date=mated + timedelta(days=63)))
    session.commit()
    return RedirectResponse("/modules/breeding", status_code=303)


@app.post("/modules/breeding/simulation", response_class=HTMLResponse)
def breeding_simulation(dam_id: int = Form(...), sire_id: int = Form(...), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dam = tenant_dog(session, tenant.id, dam_id)
    sire = tenant_dog(session, tenant.id, sire_id)
    if dam.sex != "female" or sire.sex != "male":
        raise HTTPException(status_code=400)
    coefficient = offspring_coefficient(session, tenant.id, sire.id, dam.id) * 100
    risks = genetic_risks(session, tenant.id, sire.id, dam.id)
    risk_html = "".join(f"<li>{html.escape(message)}</li>" for message in risks) or "<li>両親で共通する遺伝子検査情報がありません。</li>"
    level = "比較的低い" if coefficient < 6.25 else ("注意が必要" if coefficient < 12.5 else "高い")
    body = f'<h1>交配シミュレーション結果</h1><p>{html.escape(sire.call_name)} × {html.escape(dam.call_name)}</p><div class="tenant"><h2>予定仔犬の近親交配率：{coefficient:.2f}%</h2><p>判定：{level}</p></div><h2>遺伝病リスク</h2><ul>{risk_html}</ul><p>血統や検査情報が未登録の場合、結果は過小評価される可能性があります。最終判断には獣医師・遺伝学の専門家への確認が必要です。</p><a class="button secondary" href="/modules/breeding">戻る</a>'
    return layout("交配シミュレーション", body, user)


@app.get("/modules/births", response_class=HTMLResponse)
def births_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dams = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.sex == "female").order_by(Dog.call_name)).all()
    options = "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in dams)
    litters = session.scalars(select(Litter).where(Litter.tenant_id == tenant.id).order_by(Litter.birth_date.desc())).all()
    rows = ""
    for litter in litters:
        dam = session.get(Dog, litter.dam_id)
        rows += f"<tr><td>{litter.birth_date}</td><td>{html.escape(dam.call_name)}</td><td>{litter.born_count}</td><td>{litter.alive_count}</td><td>{html.escape(litter.notes or '-')}</td></tr>"
    body = f'''<h1>出産管理</h1><form method="post"><div class="grid"><div><label>母犬</label><select name="dam_id" required>{options}</select></div><div><label>出産日</label><input name="birth_date" type="date" required></div><div><label>出生頭数</label><input name="born_count" type="number" min="0" required></div><div><label>生存頭数</label><input name="alive_count" type="number" min="0" required></div></div><label>メモ</label><textarea name="notes"></textarea><button>出産を登録</button></form><table><tr><th>出産日</th><th>母犬</th><th>出生</th><th>生存</th><th>メモ</th></tr>{rows}</table>'''
    return layout("出産管理", body, user)


@app.post("/modules/births")
def litter_create(dam_id: int = Form(...), birth_date: str = Form(...), born_count: int = Form(...), alive_count: int = Form(...), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dam = session.scalar(select(Dog).where(Dog.id == dam_id, Dog.tenant_id == tenant.id, Dog.sex == "female"))
    if not dam or born_count < 0 or alive_count < 0 or alive_count > born_count:
        raise HTTPException(status_code=400, detail="出産情報を確認してください")
    born = date.fromisoformat(birth_date)
    session.add(Litter(tenant_id=tenant.id, dam_id=dam.id, birth_date=born, born_count=born_count, alive_count=alive_count, notes=notes.strip() or None))
    related = session.scalar(select(BreedingRecord).where(BreedingRecord.tenant_id == tenant.id, BreedingRecord.dam_id == dam.id, BreedingRecord.mating_date <= born).order_by(BreedingRecord.mating_date.desc()))
    if related:
        related.status = "delivered"
    session.commit()
    return RedirectResponse("/modules/births", status_code=303)


PEDIGREE_LABELS = [
    "登録する犬", "父犬", "母犬", "父方祖父", "父方祖母", "母方祖父", "母方祖母",
    "父方祖父の父", "父方祖父の母", "父方祖母の父", "父方祖母の母",
    "母方祖父の父", "母方祖父の母", "母方祖母の父", "母方祖母の母",
]
PEDIGREE_EXCLUDE = {
    "PEDIGREE", "CERTIFICATE", "JAPAN KENNEL CLUB", "MINIATURE SCHNAUZER",
    "BREED", "SEX", "COLOR", "DATE OF BIRTH", "OWNER", "BREEDER", "REGISTRATION",
}
TITLE_PATTERNS = [
    ("junior_international_champion", r"\b(?:J\.?\s*INT\.?\s*CH\.?|JUNIOR\s+INTERNATIONAL\s+CHAMPION|J\.?C\.?I\.?B\.?|CIB-J)\b"),
    ("international_veteran_champion", r"\b(?:CIB-V|INTERNATIONAL\s+VETERAN\s+CHAMPION)\b"),
    ("international_show_champion", r"\b(?:C\.?I\.?E\.?)\b"),
    ("international_champion", r"\b(?:INT\.?\s*CH\.?|INTERNATIONAL\s+(?:BEAUTY\s+)?CHAMPION|C\.?I\.?B\.?)\b"),
    ("junior_champion", r"\b(?:J\.?\s*CH\.?|JR\.?\s*CH\.?|JUNIOR\s+CHAMPION)\b"),
    ("veteran_champion", r"\b(?:V\.?\s*CH\.?|VETERAN\s+CHAMPION)\b"),
    ("grand_champion", r"\b(?:GCH|GR\.?\s*CH\.?|GRAND\s+CHAMPION)\b"),
    ("champion", r"(?<![A-Z.])\b(?:CH\.?|CHAMPION)\b"),
]
TITLE_LABELS = {
    "champion": ("CH", "silver", "チャンピオン"),
    "international_champion": ("INT.CH", "gold", "インターチャンピオン"),
    "junior_champion": ("J.CH", "rose", "ジュニアチャンピオン"),
    "junior_international_champion": ("J.INT.CH", "purple", "ジュニアインターチャンピオン"),
    "international_veteran_champion": ("CIB-V", "purple", "インターナショナルベテランチャンピオン"),
    "international_show_champion": ("C.I.E.", "gold", "インターナショナルショーチャンピオン"),
    "veteran_champion": ("V.CH", "rose", "ベテランチャンピオン"),
    "grand_champion": ("G.CH", "blue", "グランドチャンピオン"),
}

# JKC公式の3代祖血統証明書に記載される番号と領域。番号検出が一つ失敗しても、
# 後続の犬が別の親族欄へずれないよう各欄を独立して読み取る。
JKC_SLOT_BOXES = {
    1: (.055, .300, .505, .405), 2: (.055, .625, .505, .735),
    3: (.075, .235, .505, .325), 4: (.075, .385, .505, .485),
    5: (.075, .535, .505, .665), 6: (.075, .720, .505, .840),
    7: (.535, .195, .970, .300), 8: (.535, .285, .970, .375),
    9: (.535, .355, .970, .450), 10: (.535, .430, .970, .530),
    11: (.535, .505, .970, .610), 12: (.535, .585, .970, .685),
    13: (.535, .680, .970, .790), 14: (.535, .775, .970, .900),
}


def extract_title_keys(value: str) -> list[str]:
    """長い称号から先に消費し、J.CH/INT.CH内のCHを二重計上しない。"""
    remaining = value.upper().replace("／", "/")
    found: list[str] = []
    for key, pattern in TITLE_PATTERNS:
        if re.search(pattern, remaining, re.IGNORECASE):
            found.append(key)
            remaining = re.sub(pattern, " ", remaining, flags=re.IGNORECASE)
    return found


def title_marks(value: str | None) -> str:
    keys = [key for key in (value or "").split(",") if key in TITLE_LABELS]
    return "".join(f'<span class="title-crown crown-{TITLE_LABELS[key][1]}" title="{TITLE_LABELS[key][2]}">♛<small>{TITLE_LABELS[key][0]}</small></span>' for key in keys)


def split_name_titles(value: str) -> tuple[str, list[str]]:
    titles = extract_title_keys(value)
    name = value
    for key, pattern in TITLE_PATTERNS:
        name = re.sub(pattern, " ", name, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", name).strip(" ,-./"), titles


def ocr_image(image: Image.Image, psm: int = 11) -> str:
    available = set(pytesseract.get_languages(config=""))
    requested = ["eng", "jpn", "deu", "fra", "ita", "spa", "por", "nld", "pol", "ces", "hun", "rus"]
    languages = "+".join(code for code in requested if code in available) or "eng"
    prepared = ImageEnhance.Contrast(image.convert("L")).enhance(1.8).filter(ImageFilter.SHARPEN)
    return pytesseract.image_to_string(prepared, lang=languages, config=f"--psm {psm}", timeout=70)


def ocr_spatial_records(image: Image.Image, box: tuple[float, float, float, float] = (0, 0, 1, 1)) -> list[tuple[float, float, str]]:
    """全面OCRの座標を保ったまま、指定範囲内の行を返す。"""
    # JKCの犬名・番号・称号欄は英字で構成される。jpnとの混在認識は英字行を
    # 落とすことがあるため、配置解析だけはeng固定で実行する。
    languages = "eng"
    data = pytesseract.image_to_data(image, lang=languages, config="--psm 11", output_type=pytesseract.Output.DICT, timeout=70)
    width, height = image.size
    left, top, right, bottom = box
    grouped: dict[tuple[int, int, int], list[tuple[int, int, str]]] = {}
    for index, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        x, y, w, h = data["left"][index], data["top"][index], data["width"][index], data["height"][index]
        center_x, center_y = (x + w / 2) / width, (y + h / 2) / height
        if left <= center_x <= right and top <= center_y <= bottom:
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            grouped.setdefault(key, []).append((x, y, word))
    records = []
    for words in grouped.values():
        ordered = sorted(words)
        first_x = ordered[0][0] / width
        text_value = " ".join(word for _, _, word in ordered)
        line_y = min(item[1] for item in ordered) / height
        records.append((first_x, line_y, text_value))
    return sorted(records, key=lambda item: (item[1], item[0]))


def ocr_spatial_lines(image: Image.Image, box: tuple[float, float, float, float]) -> list[str]:
    return [record[2] for record in ocr_spatial_records(image, box)]


def normalize_jkc_number(value: str) -> str:
    value = value.upper().replace("—", "-").replace("–", "-").replace("−", "-").replace("－", "-").replace("／", "/")
    value = re.sub(r"\b(?:IKC|JKO)\b", "JKC", value)
    # JKC-MS -05878/21 のような原本上の空白や、全角記号を許容して
    # 保存時だけ JKC-MS-05878/21 の統一形式にする。
    match = re.search(
        r"(?:JKC|KC)\s*[- ]?\s*([A-Z]{1,4})\s*[- ]?\s*(\d{5})\s*/\s*(\d{2})(?:\s*[- ]?\s*([I1]))?",
        value,
    )
    if not match:
        return ""
    suffix = match.group(4)
    suffix = "I" if suffix == "1" else suffix
    return f"JKC-{match.group(1)}-{match.group(2)}/{match.group(3)}" + (f"-{suffix}" if suffix else "")


def jkc_root_registration_number(image: Image.Image) -> str:
    """祖先番号を混ぜないよう、本犬の登録番号欄だけを拡大して認識する。"""
    width, height = image.size
    crop = image.crop((int(width * .02), int(height * .17), int(width * .34), int(height * .215)))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS)
    value = pytesseract.image_to_string(crop, lang="eng", config="--psm 6", timeout=70)
    return normalize_jkc_number(value)


def jkc_root_sex_birth(image: Image.Image) -> dict[str, str]:
    """本犬の性別・生年月日欄だけを拡大し、祖先の生年月日混入を防ぐ。"""
    width, height = image.size
    crop = image.crop((int(width * .04), int(height * .205), int(width * .33), int(height * .25)))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS)
    value = pytesseract.image_to_string(crop, lang="eng", config="--psm 6", timeout=70).upper()
    result: dict[str, str] = {}
    if re.search(r"\b(?:FEMALE|REMALE|EMALE)\b", value):
        result["sex"] = "female"
    elif re.search(r"\bMALE\b", value):
        result["sex"] = "male"
    birth = re.search(r"(20\d{2})\s*4[A-Z0-9]?\s*(1[0-2]|[1-9])\s*[A-Z]?\s*(3[01]|[12]\d|[1-9])", value)
    if birth:
        year, month, day = map(int, birth.groups())
        try:
            result["birth_date"] = date(year, month, day).isoformat()
        except ValueError:
            pass
    return result


def jkc_root_breed(image: Image.Image) -> str:
    """JKC本犬欄の犬種だけを拡大し、途中で切れた全面OCRより優先する。"""
    width, height = image.size
    crop = image.crop((int(width * .02), int(height * .13), int(width * .45), int(height * .20)))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS)
    value = pytesseract.image_to_string(crop, lang="eng", config="--psm 6", timeout=70).upper()
    # 小さな英字ラベル Breed は BRE / PEE / EU に崩れやすい。一方、右側の
    # 犬種名は大きく明瞭なため、JKCの犬種専用領域内に限って各崩れを許容する。
    match = re.search(r"(?:BRE(?:ED|EDS)?|PEE|EU)[^A-Z\n]{0,8}([A-Z][A-Z .'-]{2,60})", value)
    if not match:
        # MINIATUREは細い活字のためMINIATU!/MINTAT等へ分割されやすい。
        # SCHNAUZERとの組み合わせを確認できる場合のみ公式表記へ補正する。
        spatial_value = " ".join(ocr_spatial_lines(image, (.02, .12, .42, .20))).upper()
        combined = value + " " + spatial_value
        if "SCHNAUZER" in combined and re.search(r"MINI|MINT", combined):
            return "MINIATURE SCHNAUZER"
        return ""
    breed = re.sub(r"\s{2,}", " ", match.group(1)).strip(" .-")
    parts = breed.split()
    # 左隣の日本語ラベルの断片が単独1文字（例: "S MINIATURE ..."）で
    # 混ざることがあるため、犬種本体が複数語ある場合だけ除去する。
    if len(parts) >= 3 and len(parts[0]) == 1:
        breed = " ".join(parts[1:])
    return breed if breed not in {"BREED", "NAME OF DOG"} else ""


def normalize_pedigree_color(value: str) -> str:
    """血統書の正式表記・略記・OCRの空白揺れを管理用表記へ統一する。"""
    upper = re.sub(r"[|_]", " ", value.upper())
    upper = re.sub(r"\s+", " ", upper)
    if re.search(r"SALT\s*(?:&|AND)?\s*PEPPER|SLT\s*PPR|PPR\s*SLT", upper):
        return "SALT & PEPPER"
    if re.search(r"BLACK\s*(?:&|AND)?\s*SILVER|BLK\s*SLV[ER]*|SLV[ER]*\s*BLK", upper):
        return "BLACK & SILVER"
    if re.search(r"\bBLACK\b|\bBLK\b", upper):
        return "BLACK"
    if re.search(r"\bWHITE\b|\bWHT\b", upper):
        return "WHITE"
    return ""


def jkc_root_metadata(image: Image.Image, records: list[tuple[float, float, str]] | None = None) -> dict[str, str]:
    """本犬欄だけを読み、祖先欄の番号や団体名を混入させない。"""
    def lines_in(box: tuple[float, float, float, float]) -> list[str]:
        if records is None:
            return ocr_spatial_lines(image, box)
        left, top, right, bottom = box
        return [value for x, y, value in records if left <= x <= right and top <= y <= bottom]

    lines = lines_in((.02, .08, .68, .28))
    value = "\n".join(lines)
    result = {"organization": "JKC", "country": "日本"}
    trusted_identity = jkc_root_sex_birth(image)

    trusted_breed = jkc_root_breed(image)
    breed_match = re.search(r"(?:^|\n)\s*(?:BREED|犬種)\s*[:：]?\s*([A-Z][A-Z .'-]{2,60})", value, re.IGNORECASE)
    if trusted_breed:
        result["breed"] = trusted_breed
    elif breed_match:
        breed = re.sub(r"\s{2,}", " ", breed_match.group(1)).strip(" .-").upper()
        if breed not in {"BREED", "NAME OF DOG"}:
            result["breed"] = breed

    names = []
    for line in lines:
        upper = line.upper()
        if re.search(r"\bOF\b.*\bJP\b|\bJP\b.*\bOF\b", upper) and "NAME OF DOG" not in upper:
            cleaned = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9') -]+$", "", upper)
            if len(cleaned) >= 8:
                names.append(cleaned)
    if names:
        result["registered_name"] = max(names, key=len)

    number = jkc_root_registration_number(image) or normalize_jkc_number(value)
    if number:
        result["pedigree_no"] = number
    chip = re.search(r"\bID\s*([0-9 ]{15,20})", value, re.IGNORECASE)
    if chip:
        digits = re.sub(r"\D", "", chip.group(1))
        if len(digits) == 15:
            result["microchip_no"] = digits

    upper_value = value.upper()
    root_color = normalize_pedigree_color(upper_value)
    if root_color:
        result["color"] = root_color
    # FEMALEの先頭Fは、罫線や日本語ラベルの影響でR/Eとして誤認されやすい。
    # MALEより先に判定し、FEMALEの一部を牡と誤判定しない。
    if re.search(r"\b(?:FEMALE|REMALE|EMALE)\b", upper_value):
        result["sex"] = "female"
    elif re.search(r"\bMALE\b", upper_value):
        result["sex"] = "male"

    # 日本語ラベル「年・月・日」はOCRで 47/48・A/H・0/H に崩れやすい。
    # 年マーカーの2文字を月に混ぜないJKC専用パターンを最優先する。
    birth = re.search(r"(20\d{2})\s*(?:年|4\d?)\s*(1[0-2]|[1-9])\s*(?:月|[AH])?\s*(3[01]|[12]\d|[1-9])\s*(?:日|[HO0])?", value)
    if not birth:
        birth = re.search(r"(20\d{2})\s*年\s*(1[0-2]|[1-9])\s*月\s*(3[01]|[12]\d|[1-9])\s*日", value)
    if birth:
        year, month, day = map(int, birth.groups())
        try:
            result["birth_date"] = date(year, month, day).isoformat()
        except ValueError:
            pass
    result.update(trusted_identity)
    # 本犬の称号は犬名の直上だけから取得する。広い本人情報領域には
    # 右側7番祖先のINT.CH等が入り得るため、本人へ誤付与しない。
    root_title_lines = lines_in((.25, .035, .76, .115))
    title_keys = extract_title_keys("\n".join(root_title_lines))
    if title_keys:
        result["titles"] = ",".join(title_keys)
    return result


def jkc_slot_text(image: Image.Image) -> str:
    """JKCの番号付き15欄を独立解析し、欠落による血縁位置の連鎖ずれを防ぐ。"""
    records = ocr_spatial_records(image)
    metadata = jkc_root_metadata(image, records)
    results: list[str] = [f"[[PEDIGREE_META]] {json.dumps(metadata, ensure_ascii=False)}"]

    def crop_text(box: tuple[float, float, float, float], psm: int = 6) -> str:
        width, height = image.size
        left, top, right, bottom = box
        # 3倍化と単一ブロック解析で、全面OCRが落とした父母欄も再試行する。
        crop = image.crop((int(width * max(0, left - .04)), int(height * top), int(width * right), int(height * bottom)))
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
        prepared = ImageEnhance.Contrast(crop.convert("L")).enhance(1.8).filter(ImageFilter.SHARPEN)
        return pytesseract.image_to_string(prepared, lang="eng", config=f"--psm {psm}", timeout=70)

    def details_from_text(value: str) -> tuple[str, list[str], str]:
        lines = [re.sub(r"\s{2,}", " ", line).strip(" |") for line in value.splitlines() if line.strip()]
        reg_index = next((i for i, line in enumerate(lines) if normalize_jkc_number(line)), None)
        if reg_index is None:
            return "", [], normalize_pedigree_color(value)
        possible = []
        for candidate in lines[max(0, reg_index - 3):reg_index]:
            candidate = candidate.rsplit("|", 1)[-1]
            candidate = re.sub(r"^[^A-Z]+", "", candidate.upper())
            clean_name, _ = split_name_titles(candidate)
            upper = clean_name.upper()
            if len(clean_name) >= 5 and re.search(r"[A-Z]{4}", upper) and not any(word in upper for word in PEDIGREE_EXCLUDE) and not re.search(r"\b(?:SIRE|DAM|CDI?|DNA|SLT|PPR|BLK)\b", upper):
                possible.append(upper)
        title_context = "\n".join(lines[max(0, reg_index - 5):reg_index])
        name = possible[-1] if possible else ""
        if not name:
            # 表の罫線が | や ] として犬名先頭に付着したケース。
            compact = "\n".join(lines)
            direct = re.search(r"(?:^|\n)[^A-Z\n]*([A-Z][A-Z0-9'’* .-]{4,})\n[^\n]*(?:JKC|KC)\s*-?\s*MS", compact)
            if direct:
                name = direct.group(1).strip(" .-")
        return name, extract_title_keys(title_context), normalize_pedigree_color(value)

    def details_for(box: tuple[float, float, float, float]) -> tuple[str, list[str], str]:
        left, top, right, bottom = box
        local = [record for record in records if left <= record[0] <= right and top <= record[1] <= bottom]
        registration_lines = [record for record in local if normalize_jkc_number(record[2])]
        if registration_lines:
            reg_y = registration_lines[0][1]
            before_registration = [record for record in local if record[1] < reg_y]
            color_records = [record[2] for record in local if record[1] > reg_y]
        else:
            # 登録番号だけが読めない場合も、欄上部の犬名は回収する。
            before_registration = [record for record in local if record[1] < top + (bottom - top) * .58]
            color_records = [record[2] for record in local]
        possible = []
        for _, candidate_y, candidate in before_registration:
            candidate = candidate.rsplit("|", 1)[-1]
            clean_name, _ = split_name_titles(candidate)
            upper = clean_name.upper()
            if len(clean_name) >= 5 and re.search(r"[A-Z]{4}", upper) and not any(word in upper for word in PEDIGREE_EXCLUDE) and not re.search(r"\b(?:SIRE|DAM|CDI?|DNA|SLT|PPR|BLK|MALE|FEMALE|G\.?G\.?)\b", upper) and not re.fullmatch(r"[A-Z. ]*CH[A-Z0-9/., ()-]*", upper):
                possible.append((candidate_y, clean_name))
        # 登録番号に最も近い直前行が犬名。長さ優先だと隣接欄の文字を選びやすい。
        name = max(possible, key=lambda item: item[0])[1] if possible else ""
        name_y = max((item[0] for item in possible), default=bottom)
        title_context = "\n".join(record[2] for record in local if record[1] < name_y)
        titles = extract_title_keys(title_context)
        # 前の世代欄の毛色が矩形上端へ入る場合があるため、本犬の登録番号より
        # 下にある毛色を優先し、隣接犬の色を取り込まない。
        local_color = normalize_pedigree_color("\n".join(color_records))
        # 全面座標OCRで名前と毛色が取れた欄は再OCRしない。従来は全14欄を
        # 常に拡大OCRしていたため、低性能な本番環境で処理上限に達していた。
        fallback_color = ""
        if not name or not local_color:
            cropped_text = crop_text(box)
            fallback_name, fallback_titles, fallback_color = details_from_text(cropped_text)
            if not name:
                name = fallback_name
            for key in fallback_titles:
                if key not in titles:
                    titles.append(key)
        return name, titles, local_color or fallback_color

    if metadata.get("registered_name"):
        root_titles = [key for key in metadata.get("titles", "").split(",") if key in TITLE_LABELS]
        results.append(f"[[PEDIGREE_SLOT_0]] {metadata['registered_name']} || {','.join(root_titles)} || {metadata.get('color', '')}")
    for index, box in JKC_SLOT_BOXES.items():
        name, title_keys, dog_color = details_for(box)
        if not name:
            retry = crop_text(box, psm=11)
            retry_lines = [line.strip() for line in retry.upper().splitlines() if line.strip()]
            reg_index = next((i for i, line in enumerate(retry_lines) if normalize_jkc_number(line)), None)
            if reg_index is not None and reg_index > 0:
                retry_names = []
                for raw_name in retry_lines[max(0, reg_index - 4):reg_index]:
                    raw_name = raw_name.rsplit("|", 1)[-1]
                    raw_name = re.sub(r"^[^A-Z]+", "", raw_name)
                    if len(raw_name) >= 5 and re.search(r"[A-Z]{4}", raw_name) and not re.search(r"\b(?:CH|SIRE|DAM|DNA|SLT|PPR)\b", raw_name):
                        retry_names.append(raw_name)
                if retry_names:
                    name = max(retry_names, key=len).strip(" .-")
                    title_keys = extract_title_keys("\n".join(retry_lines[:reg_index - 1]))
        # 縦罫線を I と誤認した犬名だけを安全に補正する。
        name = re.sub(r"(?<=[A-Z])\](?=[A-Z])", "I", name.upper())
        # JKC犬舎名の所有格 JP’S は、細いアポストロフィが °・*・' と
        # 認識されやすい。意味が一意に定まる JP + 記号 + S だけを正規化する。
        name = re.sub(r"\bJP\s*[“”°*'`´’‘]{1,3}\s*S\b", "JP’S", name, flags=re.IGNORECASE)
        # 同じ血統書内の本犬名に完全一致する語列があれば、OCRで分断された
        # "NI INA" のような空白だけを原表記へ戻す。
        root_name = metadata.get("registered_name", "")
        compact_name = re.sub(r"[^A-Z0-9]", "", name)
        root_words = root_name.split()
        for start in range(len(root_words)):
            candidate = " ".join(root_words[start:])
            if compact_name and re.sub(r"[^A-Z0-9]", "", candidate) == compact_name:
                name = candidate
                break
        if name:
            results.append(f"[[PEDIGREE_SLOT_{index}]] {name} || {','.join(title_keys)} || {dog_color}")
    return "\n".join(results)


def imported_dog_certificate_text(image: Image.Image, full_text: str) -> str:
    """JKC輸入犬登録証明書は父母だけの書式なので、15欄OCRを実行しない。"""
    upper = full_text.upper().replace("°", "’").replace("*", "’")
    metadata: dict[str, str] = {"organization": "JKC", "country": "日本"}
    jkc = re.search(r"JKC\s*[-— ]?\s*([A-Z]{1,4})\s*[-— ]?\s*(\d{4,6})\s*/\s*(\d{2})(?:\s*[-— ]?\s*([A-Z1I]))?", upper)
    if jkc:
        suffix = jkc.group(4)
        suffix = "I" if suffix == "1" else suffix
        metadata["pedigree_no"] = f"JKC-{jkc.group(1)}-{jkc.group(2)}/{jkc.group(3)}" + (f"-{suffix}" if suffix else "")
    width, height = image.size
    identity_crop = image.crop((int(width * .25), int(height * .30), int(width * .78), int(height * .40)))
    identity_crop = identity_crop.resize((identity_crop.width * 3, identity_crop.height * 3), Image.Resampling.LANCZOS)
    identity_text = pytesseract.image_to_string(identity_crop, lang="eng", config="--psm 6", timeout=30).upper()
    chip = re.search(r"\b(?:ID|1D)\s*([0-9]{15})\b", identity_text) or re.search(r"\b(?:ID|1D)\s*([0-9]{15})\b", upper)
    if chip:
        metadata["microchip_no"] = chip.group(1)
    breed = re.search(r"\bMINIATURE\s+SCHNAUZER\b", upper)
    if breed:
        metadata["breed"] = "MINIATURE SCHNAUZER"
    if re.search(r"\b(?:FEMALE|REMALE|EMALE)\b", upper):
        metadata["sex"] = "female"
    elif re.search(r"\bMALE\b", upper):
        metadata["sex"] = "male"
    birth = re.search(r"(20\d{2})\s*(?:年|4[A-Z0-9]?)?\s*(1[0-2]|[1-9])\s*(?:月|A)?\s*(3[01]|[12]\d|[1-9])\s*(?:日|H)?", full_text, re.IGNORECASE)
    if birth:
        try:
            metadata["birth_date"] = date(*map(int, birth.groups())).isoformat()
        except ValueError:
            pass
    dog_name = ""
    name_match = re.search(r"(?:CH\s*\([^\n)]{2,6}\)\s*)?\n?\s*([A-Z][A-Z0-9'’ .-]{5,80})\s*\n\s*(?:BREED|Breed)", upper, re.IGNORECASE)
    if name_match:
        dog_name = name_match.group(1).strip(" .-")
    if not dog_name:
        name_match = re.search(r"(?:PLASMA|[A-Z]{3,})[- ][A-Z0-9'’ -]{3,}\b", upper)
        dog_name = name_match.group(0).strip(" .-") if name_match else ""
    dog_name = re.sub(r"\bJP\s*[°*'`´’‘]\s*S\b", "JP’S", dog_name)
    dog_name = re.sub(r"\bMS\s*[°*'`´’‘]\s*S\b", "MS’S", dog_name)
    root_titles = extract_title_keys(upper.split(dog_name, 1)[0][-100:] if dog_name and dog_name in upper else "")

    def parent_after(label: str) -> tuple[str, list[str], str]:
        end_label = "DAM" if label == "SIRE" else "JAPAN KENNEL CLUB"
        section_match = re.search(rf"\b{label}\b([\s\S]*?)(?=\b{end_label}\b)", upper)
        section = section_match.group(1) if section_match else ""
        match = re.search(r"([A-Z][A-Z0-9'’ .-]{5,80})\s*\n\s*KATH\d+", section)
        if not match:
            return "", [], ""
        name = re.sub(r"\bMS\s*[°*'`´’‘]\s*S\b", "MS’S", match.group(1).strip(" .-"))
        context = section[:match.start(1)]
        color_match = re.search(r"\b(?:BLK|BLACK|SLT\s+PPR|BLK\s+SLVR)\b", section[match.end():])
        return name, extract_title_keys(context), normalize_pedigree_color(color_match.group(0) if color_match else "")

    results = [f"[[PEDIGREE_META]] {json.dumps(metadata, ensure_ascii=False)}"]
    if dog_name:
        results.append(f"[[PEDIGREE_SLOT_0]] {dog_name} || {','.join(root_titles)} || {normalize_pedigree_color(upper)}")
    for index, label in ((1, "SIRE"), (2, "DAM")):
        name, titles, color = parent_after(label)
        if name:
            results.append(f"[[PEDIGREE_SLOT_{index}]] {name} || {','.join(titles)} || {color}")
    return "\n".join(results)


def extract_pedigree_text(path: Path, content_type: str) -> str:
    """PDFまたは写真から文字を抽出する。スキャンPDFは1ページ目を画像化してOCRする。"""
    if content_type == "application/pdf" or path.suffix.lower() == ".pdf":
        try:
            text_value = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages[:2])
            if len(text_value.strip()) >= 80:
                return text_value
        except Exception:
            pass
        extract_prefix = str(path.with_suffix("")) + "-embedded"
        subprocess.run(["pdfimages", "-f", "1", "-l", "1", "-j", str(path), extract_prefix], check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        extracted = sorted(path.parent.glob(Path(extract_prefix).name + "-*"))
        if extracted:
            image_path = extracted[0]
        else:
            output_prefix = str(path.with_suffix("")) + "-page"
            subprocess.run(["pdftoppm", "-f", "1", "-singlefile", "-jpeg", "-r", "300", str(path), output_prefix], check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            image_path = Path(output_prefix + ".jpg")
    else:
        image_path = path
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        full_text = ocr_image(image, psm=11)
        if re.search(r"REGISTRATION\s+CERTIFICATE\s+FOR\s+IMPORTED\s+DOG|輸入犬登録証明書", full_text, re.IGNORECASE):
            full_text += "\n" + imported_dog_certificate_text(image, full_text)
        elif re.search(r"JAPAN\s+KENNEL\s+CLUB|JKC[-— ]?MS", full_text, re.IGNORECASE):
            full_text += "\n" + jkc_slot_text(image)
        return full_text


PEDIGREE_DOCUMENT_TYPES = {
    "domestic_pedigree": "国内血統証明書",
    "import_registration": "輸入犬登録証明書（日本）",
    "export_pedigree": "出生国・輸出血統証明書",
    "updated_pedigree": "更新後の血統証明書",
    "other": "その他",
}


def pedigree_document_metadata(raw_text: str, metadata: dict[str, str]) -> dict[str, str]:
    """原本単位の番号を判定する。犬本体の国内番号と海外番号は混ぜない。"""
    upper = raw_text.upper().replace("’", "'")
    is_import = "REGISTRATION CERTIFICATE FOR IMPORTED DOG" in upper or "輸入犬登録証明書" in raw_text
    is_export = "CERTIFIED EXPORT PEDIGREE" in upper or "EXPORT PEDIGREE" in upper
    kath = re.search(r"\bKATH\s*[- ]?\s*(\d{7,12})\b", upper)
    jkc = re.search(r"\bJKC\s*[-— ]?\s*([A-Z]{1,4})\s*[-— ]?\s*(\d{4,6})\s*/\s*(\d{2})(?:\s*[-— ]?\s*([A-Z1]))?", upper)
    # 国内の通常血統書へOCRが推測した -K/-P 等を付けない。
    # 輸入犬登録証明書で明記される -I（OCRでは -1）だけを許可する。
    suffix = (jkc.group(4) or "").upper() if jkc else ""
    if suffix == "1" and is_import:
        suffix = "I"
    if suffix != "I" or not is_import:
        suffix = ""
    jkc_no = f"JKC-{jkc.group(1)}-{jkc.group(2)}/{jkc.group(3)}" + (f"-{suffix}" if suffix else "") if jkc else ""
    trusted_jkc = metadata.get("pedigree_no", "")
    if trusted_jkc.upper().startswith("JKC-") and (not jkc_no or len(trusted_jkc) > len(jkc_no)):
        jkc_no = trusted_jkc
    kath_no = f"KATH{kath.group(1)}" if kath else ""
    if is_import:
        return {"type": "import_registration", "registration_no": jkc_no or metadata.get("pedigree_no", ""), "organization": "JKC", "country": "日本", "domestic_no": jkc_no, "origin_no": kath_no, "origin_country": "タイ", "origin_organization": "KCTH", "primary": "true"}
    if is_export or kath_no:
        return {"type": "export_pedigree", "registration_no": kath_no or metadata.get("pedigree_no", ""), "organization": "KCTH", "country": "タイ", "domestic_no": "", "origin_no": kath_no, "origin_country": "タイ", "origin_organization": "KCTH", "primary": "false"}
    organization = metadata.get("organization", "")
    country = metadata.get("country", "")
    return {"type": "domestic_pedigree", "registration_no": jkc_no or metadata.get("pedigree_no", ""), "organization": organization, "country": country, "domestic_no": jkc_no or metadata.get("pedigree_no", ""), "origin_no": "", "origin_country": "", "origin_organization": "", "primary": "true" if organization.upper() == "JKC" else "false"}


def pedigree_candidates(raw_text: str) -> tuple[dict[str, str], list[str], list[list[str]], list[str]]:
    """OCR結果から本人情報と血統名候補を作る。最終確定前に必ず編集画面を表示する。"""
    clean = re.sub(r"[\t ]+", " ", raw_text.replace("\r", "\n"))
    metadata: dict[str, str] = {}
    trusted_metadata: dict[str, str] = {}
    trusted_match = re.search(r"\[\[PEDIGREE_META\]\]\s*(\{[^\n]+\})", clean)
    if trusted_match:
        try:
            trusted_metadata = {str(key): str(value) for key, value in json.loads(trusted_match.group(1)).items()}
        except (json.JSONDecodeError, TypeError):
            trusted_metadata = {}
    patterns = {
        "breed": r"(?:BREED|犬種)\s*[:：]?\s*([A-Z][A-Z .'-]{2,60})",
        "pedigree_no": r"(?:REG(?:ISTRATION)?\.?\s*(?:NO\.?|NUMBER)?|登録番号)\s*[:：]?\s*([A-Z0-9\-/]+)",
        "microchip_no": r"(?:MICROCHIP|マイクロチップ)\s*(?:NO\.?)?\s*[:：]?\s*([0-9]{10,20})",
        "birth_date": r"(?:DATE OF BIRTH|BORN|生年月日)\s*[:：]?\s*(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        "color": r"(?:COLOR|COLOUR|毛色)\s*[:：]?\s*([A-Z& ]{3,30})",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            metadata[key] = match.group(1).strip().replace(".", "-").replace("/", "-") if key == "birth_date" else match.group(1).strip()
    # "Registered"の末尾など、番号ではない英字だけの誤抽出を破棄する。
    if "pedigree_no" in metadata and not re.search(r"\d", metadata["pedigree_no"]):
        metadata.pop("pedigree_no")
    if "pedigree_no" in metadata and re.search(r"(?:J|I)?KC", metadata["pedigree_no"], re.IGNORECASE):
        normalized_jkc = normalize_jkc_number(metadata["pedigree_no"])
        if normalized_jkc:
            metadata["pedigree_no"] = normalized_jkc
        else:
            metadata.pop("pedigree_no")
    if "pedigree_no" not in metadata:
        match = re.search(r"\b(JKC[-— ]?MS\s*[-—]?\s*\d{5}/\d{2})\b", clean, re.IGNORECASE)
        if match:
            metadata["pedigree_no"] = re.sub(r"\s+", "", match.group(1)).replace("—", "-")
    if "microchip_no" not in metadata:
        match = re.search(r"\bID\s*([0-9]{15})\b", clean, re.IGNORECASE)
        if match:
            metadata["microchip_no"] = match.group(1)
    if "birth_date" not in metadata:
        match = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", clean)
        if match:
            metadata["birth_date"] = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    organizations = ["JKC", "FCI", "AKC", "KC", "VDH", "ENCI", "LOF", "RSCE", "CBKC", "CKC", "ANKC", "NZKC"]
    found_orgs = [org for org in organizations if re.search(rf"\b{re.escape(org)}\b", clean, re.IGNORECASE)]
    if found_orgs:
        metadata["organization"] = " / ".join(found_orgs)
    countries = {
        "JAPAN": "日本", "UNITED STATES": "アメリカ", "USA": "アメリカ", "GERMANY": "ドイツ",
        "ITALY": "イタリア", "FRANCE": "フランス", "SPAIN": "スペイン", "PORTUGAL": "ポルトガル",
        "NETHERLANDS": "オランダ", "POLAND": "ポーランド", "CZECH": "チェコ", "HUNGARY": "ハンガリー",
        "RUSSIA": "ロシア", "THAILAND": "タイ", "INDONESIA": "インドネシア", "AUSTRALIA": "オーストラリア",
    }
    for token, country in countries.items():
        if token in clean.upper():
            metadata["country"] = country
            break
    metadata.update({key: value for key, value in trusted_metadata.items() if key != "registered_name" and key != "titles"})

    slots: dict[int, tuple[str, list[str], str]] = {}
    for match in re.finditer(r"\[\[PEDIGREE_SLOT_(\d{1,2})\]\][ \t]*([^\n]*)", clean):
        index = int(match.group(1))
        if 0 <= index <= 14:
            parts = [part.strip() for part in match.group(2).split("||", 2)]
            name = parts[0] if parts else ""
            title_values = [key for key in (parts[1].split(",") if len(parts) > 1 else []) if key in TITLE_LABELS]
            dog_color = normalize_pedigree_color(parts[2]) if len(parts) > 2 else ""
            slots[index] = (name, title_values, dog_color)

    candidates: list[str] = []
    candidate_titles: list[list[str]] = []
    candidate_colors: list[str] = []
    seen: set[str] = set()
    for line in clean.splitlines():
        if line.startswith("[[PEDIGREE_SLOT_"):
            continue
        value = re.sub(r"^[\d②-⑮()\[\].:：\-\s]+", "", line).strip(" |;,")
        value = re.sub(r"\s{2,}.*$", "", value).strip()
        upper = value.upper()
        if not (4 <= len(value) <= 80) or not re.search(r"[A-Z]{3}", upper):
            continue
        if any(word in upper for word in PEDIGREE_EXCLUDE) or re.fullmatch(r"[A-Z]{0,5}[\d\-/ ]+", upper):
            continue
        name, titles = split_name_titles(value)
        normalized = re.sub(r"[^A-Z0-9]", "", name.upper())
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(name)
            candidate_titles.append(titles)
            candidate_colors.append("")
    if slots:
        ordered_names = [slots.get(index, ("", [], ""))[0] for index in range(15)]
        ordered_titles = [slots.get(index, ("", [], ""))[1] for index in range(15)]
        ordered_colors = [slots.get(index, ("", [], ""))[2] for index in range(15)]
        return metadata, ordered_names, ordered_titles, ordered_colors
    return metadata, candidates[:15], candidate_titles[:15], candidate_colors[:15]


def tenant_dog(session: Session, tenant_id: int, dog_id: int) -> Dog:
    dog = session.scalar(select(Dog).where(Dog.id == dog_id, Dog.tenant_id == tenant_id))
    if not dog:
        raise HTTPException(status_code=400, detail="対象犬が見つかりません")
    return dog


def reuse_registered_pedigree(
    session: Session,
    tenant_id: int,
    names: list[str],
    titles: list[list[str]],
    colors: list[str],
) -> tuple[list[str], list[list[str]], list[str], str]:
    """父母が登録済みなら、人が確認済みの血統を同腹犬へ再利用する。"""
    if len(names) < 3 or not names[1] or not names[2]:
        return names, titles, colors, ""

    def find_registered(name: str, sex: str) -> Dog | None:
        return session.scalar(
            select(Dog).where(
                Dog.tenant_id == tenant_id,
                Dog.sex == sex,
                func.lower(Dog.registered_name) == name.strip().lower(),
            ).limit(1)
        )

    sire = find_registered(names[1], "male")
    dam = find_registered(names[2], "female")
    if not sire or not dam:
        return names, titles, colors, ""

    def copy_node(index: int, dog: Dog | None) -> None:
        if not dog or index > 14:
            return
        names[index] = dog.registered_name or dog.call_name
        titles[index] = [key for key in (dog.titles or "").split(",") if key in TITLE_LABELS]
        colors[index] = dog.color or ""
        copy_node(2 * index + 1, session.get(Dog, dog.sire_id) if dog.sire_id else None)
        copy_node(2 * index + 2, session.get(Dog, dog.dam_id) if dog.dam_id else None)

    copy_node(1, sire)
    copy_node(2, dam)
    return names, titles, colors, "父母が一致した登録済み血統を再利用しました。先祖情報も原本と照合してください。"


def pedigree_relationship(session: Session, tenant_id: int, first_id: int, second_id: int) -> float:
    dogs = {dog.id: dog for dog in session.scalars(select(Dog).where(Dog.tenant_id == tenant_id)).all()}
    memo: dict[tuple[int, int], float] = {}
    visiting: set[tuple[int, int]] = set()

    def relationship(a_id: int | None, b_id: int | None) -> float:
        if not a_id or not b_id or a_id not in dogs or b_id not in dogs:
            return 0.0
        key = tuple(sorted((a_id, b_id)))
        if key in memo:
            return memo[key]
        if key in visiting:
            return 0.0
        visiting.add(key)
        a, b = dogs[a_id], dogs[b_id]
        if a_id == b_id:
            value = 1.0 + (0.5 * relationship(a.sire_id, a.dam_id) if a.sire_id and a.dam_id else 0.0)
        elif a.sire_id or a.dam_id:
            value = 0.5 * relationship(a.sire_id, b_id) + 0.5 * relationship(a.dam_id, b_id)
        elif b.sire_id or b.dam_id:
            value = 0.5 * relationship(a_id, b.sire_id) + 0.5 * relationship(a_id, b.dam_id)
        else:
            value = 0.0
        visiting.discard(key)
        memo[key] = value
        return value

    return relationship(first_id, second_id)


def offspring_coefficient(session: Session, tenant_id: int, sire_id: int, dam_id: int) -> float:
    return 0.5 * pedigree_relationship(session, tenant_id, sire_id, dam_id)


def genetic_risks(session: Session, tenant_id: int, sire_id: int, dam_id: int) -> list[str]:
    tests = session.scalars(select(GeneticTest).where(GeneticTest.tenant_id == tenant_id, GeneticTest.dog_id.in_([sire_id, dam_id]))).all()
    by_test: dict[str, dict[int, str]] = {}
    for test in tests:
        by_test.setdefault(test.test_name, {})[test.dog_id] = test.result
    messages = []
    for name, results in by_test.items():
        sire, dam = results.get(sire_id), results.get(dam_id)
        if not sire or not dam:
            messages.append(f"{name}: 片親の検査情報が不足")
        elif sire == "carrier" and dam == "carrier":
            messages.append(f"{name}: アフェクテッド25%・キャリア50%の可能性")
        elif "affected" in {sire, dam} and "carrier" in {sire, dam}:
            messages.append(f"{name}: アフェクテッド50%の可能性")
        elif sire == "affected" and dam == "affected":
            messages.append(f"{name}: アフェクテッド100%の可能性")
        elif "affected" in {sire, dam}:
            messages.append(f"{name}: 全頭キャリアとなる可能性")
        else:
            messages.append(f"{name}: アフェクテッド発症リスクは低い組み合わせ")
    return messages


@app.get("/modules/health", response_class=HTMLResponse)
def health_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    options = "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in dogs)
    health = session.scalars(select(HealthRecord).where(HealthRecord.tenant_id == tenant.id).order_by(HealthRecord.record_date.desc()).limit(30)).all()
    vaccines = session.scalars(select(Vaccination).where(Vaccination.tenant_id == tenant.id).order_by(Vaccination.administered_on.desc()).limit(30)).all()
    medications = session.scalars(select(Medication).where(Medication.tenant_id == tenant.id).order_by(Medication.administered_on.desc()).limit(30)).all()
    diseases = session.scalars(select(DiseaseHistory).where(DiseaseHistory.tenant_id == tenant.id).order_by(DiseaseHistory.diagnosed_on.desc()).limit(30)).all()
    foods = session.scalars(select(FoodHistory).where(FoodHistory.tenant_id == tenant.id).order_by(FoodHistory.started_on.desc())).all()
    health_rows = "".join(f"<tr><td>{r.record_date}</td><td>{html.escape(session.get(Dog,r.dog_id).call_name)}</td><td>{html.escape(r.category)}</td><td>{r.weight_kg or '-'}</td><td>{html.escape(r.notes or '-')}</td></tr>" for r in health)
    vaccine_rows = "".join(f"<tr><td>{v.administered_on}</td><td>{html.escape(session.get(Dog,v.dog_id).call_name)}</td><td>{html.escape(v.vaccine_name)}</td><td>{v.next_due_on or '-'}</td></tr>" for v in vaccines)
    medication_rows = "".join(f"<tr><td>{m.administered_on}</td><td>{html.escape(session.get(Dog,m.dog_id).call_name)}</td><td>{html.escape(m.medicine_name)}</td><td>{html.escape(m.notes or '-')}</td></tr>" for m in medications)
    disease_rows = "".join(f"<tr><td>{d.diagnosed_on or '-'}</td><td>{html.escape(session.get(Dog,d.dog_id).call_name)}</td><td>{html.escape(d.disease_name)}</td><td>{html.escape(d.details or '-')}</td></tr>" for d in diseases)
    food_rows = "".join(f"<tr><td>{html.escape(f.name)}</td><td>{f.started_on}</td><td>{f.ended_on or '-'}</td></tr>" for f in foods)
    body = f'''<h1>健康管理</h1>
    <h2>体重・健康診断</h2><form method="post" action="/modules/health/record"><div class="grid"><div><label>対象犬</label><select name="dog_id">{options}</select></div><div><label>記録日</label><input type="date" name="record_date" required></div><div><label>種類</label><select name="category"><option value="weight">体重</option><option value="checkup">健康診断</option><option value="treatment">診療</option></select></div><div><label>体重（kg）</label><input type="number" step="0.01" min="0" name="weight_kg"></div><div><label>動物病院</label><input name="clinic"></div></div><label>結果・メモ</label><textarea name="notes"></textarea><button>記録する</button></form><table><tr><th>日付</th><th>犬</th><th>種類</th><th>体重kg</th><th>メモ</th></tr>{health_rows}</table>
    <h2>ワクチン</h2><form method="post" action="/modules/health/vaccine"><div class="grid"><div><label>対象犬</label><select name="dog_id">{options}</select></div><div><label>ワクチン名</label><input name="vaccine_name" required></div><div><label>接種日</label><input type="date" name="administered_on" required></div><div><label>次回予定日</label><input type="date" name="next_due_on"></div><div><label>証明書番号</label><input name="certificate_no"></div></div><button>接種を記録</button></form><table><tr><th>接種日</th><th>犬</th><th>ワクチン</th><th>次回予定</th></tr>{vaccine_rows}</table>
    <h2>投薬</h2><form method="post" action="/modules/health/medication"><div class="grid"><div><label>対象犬</label><select name="dog_id">{options}</select></div><div><label>薬剤名</label><input name="medicine_name" required></div><div><label>投薬日</label><input type="date" name="administered_on" required></div></div><label>メモ</label><textarea name="notes"></textarea><button>投薬を記録</button></form><table><tr><th>日付</th><th>犬</th><th>薬剤</th><th>メモ</th></tr>{medication_rows}</table>
    <h2>病歴</h2><form method="post" action="/modules/health/disease"><div class="grid"><div><label>対象犬</label><select name="dog_id">{options}</select></div><div><label>疾患名</label><input name="disease_name" required></div><div><label>診断日</label><input type="date" name="diagnosed_on"></div><div><label>治療開始日</label><input type="date" name="treatment_started_on"></div><div><label>治療終了日</label><input type="date" name="treatment_ended_on"></div></div><label>診断・治療内容</label><textarea name="details"></textarea><button>病歴を登録</button></form><table><tr><th>診断日</th><th>犬</th><th>疾患</th><th>内容</th></tr>{disease_rows}</table>
    <h2>フード履歴</h2><form method="post" action="/modules/health/food"><div class="grid"><div><label>フード名</label><input name="name" required></div><div><label>利用開始日</label><input type="date" name="started_on" required></div><div><label>利用終了日</label><input type="date" name="ended_on"></div></div><button>フードを登録</button></form><table><tr><th>フード</th><th>開始</th><th>終了</th></tr>{food_rows}</table>'''
    return layout("健康管理", body, user)


@app.post("/modules/health/record")
def health_create(dog_id: int = Form(...), record_date: str = Form(...), category: str = Form(...), weight_kg: str = Form(""), clinic: str = Form(""), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if category not in {"weight", "checkup", "treatment"}:
        raise HTTPException(status_code=400)
    weight = float(weight_kg) if weight_kg else None
    session.add(HealthRecord(tenant_id=tenant.id, dog_id=dog.id, record_date=date.fromisoformat(record_date), category=category, weight_kg=weight, clinic=clinic.strip() or None, notes=notes.strip() or None))
    session.commit()
    return RedirectResponse("/modules/health", status_code=303)


@app.post("/modules/health/vaccine")
def vaccine_create(dog_id: int = Form(...), vaccine_name: str = Form(...), administered_on: str = Form(...), next_due_on: str = Form(""), certificate_no: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    next_due = date.fromisoformat(next_due_on) if next_due_on else None
    session.add(Vaccination(tenant_id=tenant.id, dog_id=dog.id, vaccine_name=vaccine_name.strip(), administered_on=date.fromisoformat(administered_on), next_due_on=next_due, certificate_no=certificate_no.strip() or None))
    if next_due:
        session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} {vaccine_name.strip()}接種予定", category="health", due_date=next_due))
    session.commit()
    return RedirectResponse("/modules/health", status_code=303)


@app.post("/modules/health/medication")
def medication_create(dog_id: int = Form(...), medicine_name: str = Form(...), administered_on: str = Form(...), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    session.add(Medication(tenant_id=tenant.id, dog_id=dog.id, medicine_name=medicine_name.strip(), administered_on=date.fromisoformat(administered_on), notes=notes.strip() or None))
    session.commit()
    return RedirectResponse("/modules/health", status_code=303)


@app.post("/modules/health/disease")
def disease_create(dog_id: int = Form(...), disease_name: str = Form(...), diagnosed_on: str = Form(""), treatment_started_on: str = Form(""), treatment_ended_on: str = Form(""), details: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    parse = lambda value: date.fromisoformat(value) if value else None
    started, ended = parse(treatment_started_on), parse(treatment_ended_on)
    if started and ended and ended < started:
        raise HTTPException(status_code=400, detail="治療終了日は開始日以降にしてください")
    session.add(DiseaseHistory(tenant_id=tenant.id, dog_id=dog.id, disease_name=disease_name.strip(), diagnosed_on=parse(diagnosed_on), treatment_started_on=started, treatment_ended_on=ended, details=details.strip() or None))
    session.commit()
    return RedirectResponse("/modules/health", status_code=303)


@app.post("/modules/health/food")
def food_create(name: str = Form(...), started_on: str = Form(...), ended_on: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    started = date.fromisoformat(started_on)
    ended = date.fromisoformat(ended_on) if ended_on else None
    if ended and ended < started:
        raise HTTPException(status_code=400, detail="利用終了日は開始日以降にしてください")
    session.add(FoodHistory(tenant_id=tenant.id, name=name.strip(), started_on=started, ended_on=ended))
    session.commit()
    return RedirectResponse("/modules/health", status_code=303)


@app.post("/modules/dogs/pedigree/scan", response_class=HTMLResponse)
async def pedigree_scan(pedigree_file: UploadFile = File(...), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    allowed = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    suffix = Path(pedigree_file.filename or "").suffix.lower()
    if pedigree_file.content_type not in allowed or suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        return HTMLResponse(layout("読み取りエラー", '<h1>読み取りできませんでした</h1><p class="error">PDF・JPG・PNG・WebPのいずれかを選択してください。</p><a class="button secondary" href="/modules/dogs">戻る</a>', user), status_code=400)
    content = await pedigree_file.read(15 * 1024 * 1024 + 1)
    if not content or len(content) > 15 * 1024 * 1024:
        return HTMLResponse(layout("読み取りエラー", '<h1>読み取りできませんでした</h1><p class="error">ファイルは15MB以下にしてください。</p><a class="button secondary" href="/modules/dogs">戻る</a>', user), status_code=400)
    try:
        with tempfile.TemporaryDirectory(prefix="pedigree-") as tmp:
            source = Path(tmp) / f"source{suffix}"
            source.write_bytes(content)
            # OCRはCPU負荷が高いためイベントループ外で実行し、処理中も
            # ヘルスチェックや他画面へのアクセスを止めない。
            raw_text = await asyncio.to_thread(extract_pedigree_text, source, pedigree_file.content_type or "")
        metadata, candidates, detected_titles, detected_colors = pedigree_candidates(raw_text)
        document_metadata = pedigree_document_metadata(raw_text, metadata)
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError) as exc:
        return HTMLResponse(layout("読み取りエラー", f'<h1>読み取りできませんでした</h1><p class="error">画像が不鮮明、または対応できないPDFです。撮り直すか別形式でお試しください。</p><p><small>{html.escape(type(exc).__name__)}</small></p><a class="button secondary" href="/modules/dogs">戻る</a>', user), status_code=422)

    upload = PedigreeUpload(tenant_id=tenant.id, filename=(pedigree_file.filename or f"pedigree{suffix}")[:255], content_type=pedigree_file.content_type or "application/octet-stream", file_data=content)
    session.add(upload)
    session.commit()
    names = (candidates + [""] * 15)[:15]
    titles_by_dog = (detected_titles + [[] for _ in range(15)])[:15]
    colors_by_dog = (detected_colors + [""] * 15)[:15]
    names, titles_by_dog, colors_by_dog, reused_notice = reuse_registered_pedigree(
        session, tenant.id, names, titles_by_dog, colors_by_dog
    )
    def title_select(index: int) -> str:
        options = "".join(f'<option value="{key}" {"selected" if key in titles_by_dog[index] else ""}>{label[2]}</option>' for key, label in TITLE_LABELS.items())
        return f'<label>タイトル（複数選択可）</label><select name="title_{index}" multiple size="5">{options}</select>'
    pedigree_fields = "".join(
        f'<div class="review-field"><label>{PEDIGREE_LABELS[index]}（{"牡" if index % 2 else "牝" if index else "本人"}）</label><input name="ancestor_{index}" value="{html.escape(name)}" maxlength="200" {"required" if index == 0 else ""}>{f"<label>毛色</label><input name=\"ancestor_color_{index}\" value=\"{html.escape(colors_by_dog[index])}\" maxlength=\"100\" placeholder=\"例：SALT &amp; PEPPER\">" if index else ""}{title_select(index)}<label class="review-check"><input type="checkbox" name="verified_fields" value="ancestor_{index}" {"required" if name else ""}> <span>{"原本と照合済み" if name else "未読（入力する場合は照合してください）"}</span></label></div>'
        for index, name in enumerate(names)
    )
    existing_dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.category != "external").order_by(Dog.call_name)).all()
    detected_chip = metadata.get("microchip_no", "")
    detected_domestic_no = document_metadata.get("domestic_no", "")
    detected_origin_no = document_metadata.get("origin_no", "")
    matched_dog_id = next((
        dog.id for dog in existing_dogs
        if (detected_chip and dog.microchip_no == detected_chip)
        or (detected_domestic_no and dog.pedigree_no == detected_domestic_no)
        or (detected_origin_no and dog.origin_registration_no == detected_origin_no)
    ), None)
    existing_options = '<option value="">新しい犬として登録</option>' + "".join(
        f'<option value="{dog.id}" {"selected" if dog.id == matched_dog_id else ""}>{html.escape(dog.call_name)}／{html.escape(dog.registered_name or "血統名未登録")}／国内番号：{html.escape(dog.pedigree_no or "未登録")}／海外番号：{html.escape(dog.origin_registration_no or "未登録")}／MC：{html.escape(dog.microchip_no or "未登録")}</option>'
        for dog in existing_dogs
    )
    sex_value = metadata.get("sex", "")
    sex_options = f'<option value="" {"selected" if not sex_value else ""}>選択してください</option><option value="male" {"selected" if sex_value == "male" else ""}>牡</option><option value="female" {"selected" if sex_value == "female" else ""}>牝</option>'
    document_type_options = "".join(f'<option value="{key}" {"selected" if document_metadata["type"] == key else ""}>{label}</option>' for key, label in PEDIGREE_DOCUMENT_TYPES.items())
    matched_notice = '<p class="tenant"><strong>同じマイクロチップ番号または登録番号の犬を見つけたため、上書き対象に選択しました。</strong> 別の犬の場合は選択を変更してください。</p>' if matched_dog_id else ''
    lineage_notice = f'<p class="tenant"><strong>登録済み血統を再利用</strong><br>{html.escape(reused_notice)}</p>' if reused_notice else ''
    body = f'''<style>.review-field{{padding:12px;border:1px solid #eadadd;border-radius:12px;background:#fffafb}}.review-check{{display:flex;align-items:center;gap:8px;margin-top:10px;color:#8b3f53}}.review-check input{{width:auto;accent-color:#b66f7c}}#pedigree-submit:disabled{{background:#b9adb1;cursor:not-allowed;box-shadow:none}}</style><h1>血統書の読み取り結果</h1><p><span class="badge">確認付き半自動登録</span></p><p class="error"><strong>OCR結果は未確定です。</strong> 読めない文字を推測して正式登録しません。原本と照合して修正し、各「原本と照合済み」を選択してください。</p>{matched_notice}{lineage_notice}
    <form id="pedigree-review-form" method="post" action="/modules/dogs/pedigree/import"><input type="hidden" name="upload_id" value="{upload.id}"><h2>新規登録または上書き更新</h2><label for="existing-dog-search">登録犬を検索</label><input id="existing-dog-search" type="search" placeholder="呼び名・血統書名・国内番号・海外番号・マイクロチップ番号を入力" autocomplete="off"><p id="existing-dog-result" style="margin:6px 0;color:#765f68;font-size:12px"></p><label for="existing-dog-select">登録方法</label><select id="existing-dog-select" name="existing_dog_id">{existing_options}</select><p><small>同一犬の海外血統書と日本の輸入犬登録証明書は、同じ登録犬を選んでください。マイクロチップ番号が一致する場合は自動選択します。</small></p><h2>今回アップロードした書類</h2><div class="grid"><div><label>書類の種類</label><select name="document_type">{document_type_options}</select></div><div class="review-field"><label>この書類に記載された登録番号</label><input name="document_registration_no" value="{html.escape(document_metadata['registration_no'])}"><label class="review-check"><input type="checkbox" name="verified_fields" value="document_registration_no" required> 原本と照合済み</label></div><div><label>発行団体</label><input name="document_organization" value="{html.escape(document_metadata['organization'])}"></div><div><label>発行国</label><input name="document_country" value="{html.escape(document_metadata['country'])}"></div><div><label>発行日</label><input type="date" name="document_issued_on"></div></div><h2>登録する犬の情報</h2><div class="grid"><div><label>呼び名</label><input name="call_name" value="{html.escape(names[0])}" required maxlength="100"></div><div class="review-field"><label>犬種（自由入力可）</label><input name="breed" value="{html.escape(metadata.get('breed',''))}" maxlength="150" placeholder="例：MINIATURE SCHNAUZER"><label class="review-check"><input type="checkbox" name="verified_fields" value="breed" required> 原本と照合済み</label></div><div class="review-field"><label>性別</label><select name="sex" required>{sex_options}</select><label class="review-check"><input type="checkbox" name="verified_fields" value="sex" required> 原本と照合済み</label></div><div><label>区分</label><select name="category"><option value="parent">親犬</option><option value="puppy">子犬</option><option value="external">外部犬</option></select></div><div class="review-field"><label>生年月日</label><input type="date" name="birth_date" value="{html.escape(metadata.get('birth_date',''))}"><label class="review-check"><input type="checkbox" name="verified_fields" value="birth_date" required> 原本と照合済み</label></div><div class="review-field"><label>毛色</label><input name="color" value="{html.escape(metadata.get('color',''))}"><label class="review-check"><input type="checkbox" name="verified_fields" value="color" required> 原本と照合済み</label></div><div class="review-field"><label>国内メイン番号（JKC）</label><input name="pedigree_no" value="{html.escape(document_metadata['domestic_no'])}" placeholder="例：JKC-MS-07782/25-I"><label class="review-check"><input type="checkbox" name="verified_fields" value="pedigree_no" required> 原本と照合済み</label></div><div><label>出生国・海外登録番号</label><input name="origin_registration_no" value="{html.escape(document_metadata['origin_no'])}" placeholder="例：KATH116090377"></div><div><label>マイクロチップ番号</label><input name="microchip_no" value="{html.escape(metadata.get('microchip_no',''))}"></div><div><label>出生国</label><input name="origin_registration_country" value="{html.escape(document_metadata['origin_country'])}"></div><div><label>海外発行団体</label><input name="origin_registration_organization" value="{html.escape(document_metadata['origin_organization'])}"></div><input type="hidden" name="pedigree_country" value="日本"><input type="hidden" name="pedigree_organization" value="JKC"></div><h2>血統名・タイトル・親子関係</h2><p><small>読み取れなかった先祖は空欄のままで構いません。入力されている各個体は、犬名・毛色・タイトルを原本と照合してください。</small></p><div class="grid">{pedigree_fields}</div><button id="pedigree-submit" disabled>未確認の項目があります</button> <a class="button secondary" href="/modules/dogs">キャンセル</a></form>
    <script>(function(){{const search=document.getElementById('existing-dog-search');const select=document.getElementById('existing-dog-select');const result=document.getElementById('existing-dog-result');const dogs=Array.from(select.options).slice(1).map(option=>({{value:option.value,text:option.textContent}}));function render(){{const keyword=search.value.trim().toLocaleLowerCase('ja');const matches=keyword?dogs.filter(dog=>dog.text.toLocaleLowerCase('ja').includes(keyword)):dogs;const selected=select.value;select.replaceChildren(new Option('新しい犬として登録',''),...matches.map(dog=>new Option(dog.text,dog.value)));if(matches.some(dog=>dog.value===selected))select.value=selected;result.textContent=keyword?matches.length+'頭が見つかりました':dogs.length+'頭から検索できます';}}search.addEventListener('input',render);render();const form=document.getElementById('pedigree-review-form');const submit=document.getElementById('pedigree-submit');function reviewState(){{for(let index=0;index<15;index++){{const field=form.querySelector('[name="ancestor_'+index+'"]');const check=form.querySelector('input[value="ancestor_'+index+'"]');if(field&&check){{check.required=Boolean(field.value.trim());check.parentElement.querySelector('span').textContent=check.required?'原本と照合済み':'未読（入力する場合は照合してください）';}}}}const checks=Array.from(form.querySelectorAll('input[name="verified_fields"]:required'));const ready=checks.every(check=>check.checked);submit.disabled=!ready;submit.textContent=ready?'確認した内容で登録・更新する':'未確認の項目があります';}}form.addEventListener('change',reviewState);form.addEventListener('input',reviewState);reviewState();}})();</script>
    <details><summary>読み取った元の文字を確認</summary><pre style="white-space:pre-wrap;background:#f7edef;padding:15px;border-radius:10px;max-height:300px;overflow:auto">{html.escape(raw_text[:12000])}</pre></details>'''
    return layout("血統書読み取り確認", body, user)


@app.post("/modules/dogs/pedigree/import")
def pedigree_import(
    call_name: str = Form(...), sex: str = Form(...), category: str = Form("parent"),
    upload_id: int = Form(...),
    breed: str = Form(""), birth_date: str = Form(""), color: str = Form(""), pedigree_no: str = Form(""), microchip_no: str = Form(""),
    existing_dog_id: str = Form(""), pedigree_country: str = Form(""), pedigree_organization: str = Form(""),
    origin_registration_no: str = Form(""), origin_registration_country: str = Form(""), origin_registration_organization: str = Form(""),
    document_type: str = Form("other"), document_registration_no: str = Form(""), document_country: str = Form(""),
    document_organization: str = Form(""), document_issued_on: str = Form(""),
    verified_fields: list[str] = Form([]),
    ancestor_0: str = Form(...), ancestor_1: str = Form(""), ancestor_2: str = Form(""),
    ancestor_3: str = Form(""), ancestor_4: str = Form(""), ancestor_5: str = Form(""), ancestor_6: str = Form(""),
    ancestor_7: str = Form(""), ancestor_8: str = Form(""), ancestor_9: str = Form(""), ancestor_10: str = Form(""),
    ancestor_11: str = Form(""), ancestor_12: str = Form(""), ancestor_13: str = Form(""), ancestor_14: str = Form(""),
    ancestor_color_1: str = Form(""), ancestor_color_2: str = Form(""), ancestor_color_3: str = Form(""),
    ancestor_color_4: str = Form(""), ancestor_color_5: str = Form(""), ancestor_color_6: str = Form(""),
    ancestor_color_7: str = Form(""), ancestor_color_8: str = Form(""), ancestor_color_9: str = Form(""),
    ancestor_color_10: str = Form(""), ancestor_color_11: str = Form(""), ancestor_color_12: str = Form(""),
    ancestor_color_13: str = Form(""), ancestor_color_14: str = Form(""),
    title_0: list[str] = Form([]), title_1: list[str] = Form([]), title_2: list[str] = Form([]),
    title_3: list[str] = Form([]), title_4: list[str] = Form([]), title_5: list[str] = Form([]), title_6: list[str] = Form([]),
    title_7: list[str] = Form([]), title_8: list[str] = Form([]), title_9: list[str] = Form([]), title_10: list[str] = Form([]),
    title_11: list[str] = Form([]), title_12: list[str] = Form([]), title_13: list[str] = Form([]), title_14: list[str] = Form([]),
    access=Depends(require_tenant_user), session: Session = Depends(db),
):
    user, tenant = access
    if sex not in {"male", "female"} or category not in {"parent", "puppy", "external"} or document_type not in PEDIGREE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="犬の情報を確認してください")
    names = [value.strip() for value in [ancestor_0, ancestor_1, ancestor_2, ancestor_3, ancestor_4, ancestor_5, ancestor_6, ancestor_7, ancestor_8, ancestor_9, ancestor_10, ancestor_11, ancestor_12, ancestor_13, ancestor_14]]
    raw_colors = [color, ancestor_color_1, ancestor_color_2, ancestor_color_3, ancestor_color_4, ancestor_color_5, ancestor_color_6, ancestor_color_7, ancestor_color_8, ancestor_color_9, ancestor_color_10, ancestor_color_11, ancestor_color_12, ancestor_color_13, ancestor_color_14]
    colors = [normalize_pedigree_color(value) or value.strip() for value in raw_colors]
    titles = [title_0, title_1, title_2, title_3, title_4, title_5, title_6, title_7, title_8, title_9, title_10, title_11, title_12, title_13, title_14]
    titles = [[key for key in values if key in TITLE_LABELS] for values in titles]
    if not names[0]:
        raise HTTPException(status_code=400, detail="登録する犬の血統書名が必要です")
    verified = set(verified_fields)
    required_reviews = {"document_registration_no", "breed", "sex", "birth_date", "color", "pedigree_no", "ancestor_0"}
    required_reviews.update(f"ancestor_{index}" for index, name in enumerate(names[1:], start=1) if name)
    missing_reviews = sorted(required_reviews - verified)
    if missing_reviews:
        raise HTTPException(status_code=400, detail="原本との照合が完了していない項目があります")
    submitted_pedigree_no = pedigree_no.strip()
    normalized_pedigree_no = normalize_jkc_number(submitted_pedigree_no) if submitted_pedigree_no else ""
    if submitted_pedigree_no and not normalized_pedigree_no:
        raise HTTPException(status_code=400, detail="国内メイン番号を確認してください（例：JKC-MS-05878/21）")
    pedigree_no = normalized_pedigree_no
    # 書類番号もJKC番号なら同じ表記へ統一する。海外番号は入力値を保持する。
    normalized_document_no = normalize_jkc_number(document_registration_no)
    if normalized_document_no:
        document_registration_no = normalized_document_no
    if birth_date:
        try:
            parsed_birth_date = date.fromisoformat(birth_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="生年月日を確認してください")
        if parsed_birth_date > date.today() or parsed_birth_date.year < 1980:
            raise HTTPException(status_code=400, detail="生年月日の年・月・日を原本で確認してください")
    else:
        parsed_birth_date = None

    nodes: dict[int, Dog] = {}
    for index in range(14, -1, -1):
        name = names[index]
        if not name:
            continue
        if index == 0 and existing_dog_id:
            try:
                update_id = int(existing_dog_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="更新対象を確認してください")
            existing = session.scalar(select(Dog).where(Dog.id == update_id, Dog.tenant_id == tenant.id))
            if not existing:
                raise HTTPException(status_code=400, detail="更新対象の犬が見つかりません")
        else:
            existing = session.scalar(select(Dog).where(Dog.tenant_id == tenant.id, func.lower(Dog.registered_name) == name.lower()).limit(1))
        node_sex = sex if index == 0 else ("male" if index % 2 == 1 else "female")
        if existing:
            node = existing
        else:
            node = Dog(tenant_id=tenant.id, call_name=call_name.strip() if index == 0 else name, registered_name=name, breed=breed.strip() or None, sex=node_sex, category=category if index == 0 else "external", status="resident" if index == 0 else "transferred")
            session.add(node)
            session.flush()
        if titles[index] or index == 0:
            node.titles = ",".join(titles[index]) or None
        if breed.strip() and not node.breed:
            node.breed = breed.strip()
        if colors[index]:
            node.color = colors[index]
        sire, dam = nodes.get(2 * index + 1), nodes.get(2 * index + 2)
        if sire:
            node.sire_id = sire.id
        if dam:
            node.dam_id = dam.id
        nodes[index] = node

    root = nodes[0]
    root.call_name = call_name.strip()
    root.registered_name = names[0]
    root.breed = breed.strip() or root.breed
    root.sex = sex
    root.category = category
    # 血統書の上書き更新で「販売済」「譲渡済」などの運用状態を在舎中へ戻さない。
    if not existing_dog_id:
        root.status = "resident"
    root.birth_date = parsed_birth_date or root.birth_date
    root.color = colors[0] or root.color
    # 国内番号と出生国番号は別管理。海外血統書の追加で既存JKC番号を上書きしない。
    root.pedigree_no = pedigree_no.strip() or root.pedigree_no
    root.origin_registration_no = origin_registration_no.strip() or root.origin_registration_no
    root.origin_registration_country = origin_registration_country.strip() or root.origin_registration_country
    root.origin_registration_organization = origin_registration_organization.strip() or root.origin_registration_organization
    root.microchip_no = microchip_no.strip() or root.microchip_no
    if pedigree_no.strip():
        root.pedigree_country = pedigree_country.strip() or root.pedigree_country
        root.pedigree_organization = pedigree_organization.strip() or root.pedigree_organization
    root.pedigree_updated_at = datetime.now(timezone.utc)
    upload = session.scalar(select(PedigreeUpload).where(PedigreeUpload.id == upload_id, PedigreeUpload.tenant_id == tenant.id))
    if not upload or upload.dog_id is not None:
        raise HTTPException(status_code=400, detail="アップロードした血統書データが見つかりません")
    upload.dog_id = root.id
    upload.document_type = document_type
    upload.registration_no = document_registration_no.strip() or None
    upload.organization = document_organization.strip() or None
    upload.country = document_country.strip() or None
    try:
        upload.issued_on = date.fromisoformat(document_issued_on) if document_issued_on else None
    except ValueError:
        raise HTTPException(status_code=400, detail="書類の発行日を確認してください")
    upload.is_primary = document_type in {"domestic_pedigree", "import_registration", "updated_pedigree"} and bool(root.pedigree_no)
    if upload.is_primary:
        for previous in session.scalars(select(PedigreeUpload).where(PedigreeUpload.tenant_id == tenant.id, PedigreeUpload.dog_id == root.id, PedigreeUpload.id != upload.id)).all():
            previous.is_primary = False
    session.commit()
    return RedirectResponse("/modules/dogs", status_code=303)


@app.get("/modules/dogs", response_class=HTMLResponse)
def dogs_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    archived_count = session.scalar(select(func.count(Dog.id)).where(Dog.tenant_id == tenant.id, Dog.active.is_(False))) or 0
    can_archive = tenant_role(user, tenant, session) == Role.admin
    sire_options = '<option value="">未登録</option>' + "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in dogs if d.sex == "male")
    dam_options = '<option value="">未登録</option>' + "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in dogs if d.sex == "female")
    category_labels = {"parent": "親犬", "puppy": "子犬", "external": "外部犬"}
    status_labels = {"resident": "在舎中", "reserved": "予約済", "delivered": "販売済", "retired": "引退", "transferred": "譲渡済"}
    sales_by_dog = {sale.dog_id: sale for sale in session.scalars(select(PuppySale).where(PuppySale.tenant_id == tenant.id).order_by(PuppySale.id)).all()}
    rows = ""
    for d in dogs:
        sale = sales_by_dog.get(d.id)
        buyer = session.get(Customer, sale.customer_id) if sale and sale.customer_id else None
        buyer_name = buyer.name if buyer else sale.customer_name if sale else "-"
        dog_name = html.escape(d.registered_name or d.call_name)
        archive_link = f" <a class='button danger' href='/modules/dogs/{d.id}/archive-confirm'>登録解除</a>" if can_archive else ""
        rows += f"<tr><td><a href='/modules/dogs/{d.id}'><strong>{dog_name}</strong></a><br><small>{html.escape(d.call_name)}</small></td><td>{title_marks(d.titles) or '-'}</td><td>{category_labels.get(d.category, d.category)}</td><td>{html.escape(d.breed or '-')}</td><td>{html.escape(d.registered_name or '-')}</td><td>{'牡' if d.sex == 'male' else '牝'}</td><td>{html.escape(d.pedigree_organization or '-')}<br><small>{html.escape(d.pedigree_country or '')}</small></td><td>{d.pedigree_updated_at.date() if d.pedigree_updated_at else '-'}</td><td>{status_labels.get(d.status, d.status)}</td><td>{html.escape(buyer_name)}</td><td><a class='button secondary' href='/modules/dogs/{d.id}/edit'>編集</a>{archive_link}</td></tr>"
    archived_link = f'''<p><a class="button secondary" href="/modules/archived-dogs">登録解除済み一覧（{archived_count}頭）</a></p>''' if can_archive else ""
    body = f'''<h1>犬・血統書管理</h1><p>{html.escape(tenant.name)}の登録中の犬だけが表示されます。</p>{archived_link}
    <div class="tenant"><h2 style="margin-top:0">国内・海外血統書から自動登録／更新</h2><p>JKC・FCI・AKC・KC・VDHなどのPDFまたは写真を多言語で読み取り、本人から曾祖父母まで最大15頭を登録します。新しい血統書を読み込めば、既存犬を選んで上書き更新できます。</p><form method="post" action="/modules/dogs/pedigree/scan" enctype="multipart/form-data"><label>血統書ファイル（PDF・JPG・PNG・WebP／15MBまで）</label><input type="file" name="pedigree_file" accept="application/pdf,image/jpeg,image/png,image/webp" required><button>読み取って登録・更新する</button></form><p><small>写真は真上から、影や反射が入らないように撮影すると精度が上がります。登録前に必ず読み取り結果をご確認ください。</small></p></div>
    <p>{title_marks('champion')}チャンピオン　{title_marks('international_champion')}インターチャンピオン　{title_marks('junior_champion')}Jr.チャンピオン　{title_marks('junior_international_champion')}Jr.インターチャンピオン　{title_marks('grand_champion')}グランドチャンピオン</p>
    <h2>手入力で犬を登録</h2>
    <form method="post"><div class="grid"><div><label>区分</label><select name="category"><option value="parent">親犬</option><option value="puppy">子犬</option><option value="external">外部犬</option></select></div><div><label>呼び名</label><input name="call_name" required></div><div><label>犬種（自由入力可）</label><input name="breed" maxlength="150" placeholder="例：ミックス（シュナウザー×プードル）"></div><div><label>血統書名</label><input name="registered_name"></div><div><label>性別</label><select name="sex"><option value="male">牡</option><option value="female">牝</option></select></div><div><label>状態</label><select name="status"><option value="resident">在舎中</option><option value="reserved">予約済</option><option value="delivered">販売済</option><option value="retired">引退</option><option value="transferred">譲渡済</option></select></div><div><label>生年月日</label><input name="birth_date" type="date"></div><div><label>毛色</label><input name="color"></div><div><label>父犬</label><select name="sire_id">{sire_options}</select></div><div><label>母犬</label><select name="dam_id">{dam_options}</select></div><div><label>マイクロチップ番号</label><input name="microchip_no"></div><div><label>血統書番号</label><input name="pedigree_no"></div></div><p><small>血統書がないミックス犬も、犬種を任意の名称で入力して登録できます。</small></p><button>犬を登録</button></form>
    <table><tr><th>呼び名</th><th>タイトル</th><th>区分</th><th>犬種</th><th>血統書名</th><th>性別</th><th>発行団体・国</th><th>血統書更新日</th><th>状態</th><th>販売先</th><th>操作</th></tr>{rows}</table>'''
    return layout("犬・血統書管理", body, user)


@app.get("/modules/dogs/{dog_id}/archive-confirm", response_class=HTMLResponse)
def dog_archive_confirm(dog_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if not dog.active:
        return RedirectResponse("/modules/archived-dogs", status_code=303)
    body = f'''<h1>登録解除の確認</h1><div class="tenant"><h2 style="margin-top:0">{html.escape(dog.call_name)}</h2><p>{html.escape(dog.registered_name or "血統書名未登録")}</p></div><p class="error">この犬を登録解除すると、通常の犬一覧・在籍犬一覧・仔犬／親犬一覧から非表示になります。</p><p>健康・繁殖・血統・販売などの履歴は削除されず、後から復元できます。</p><form method="post" action="/modules/dogs/{dog.id}/archive"><button class="danger">登録解除する</button> <a class="button secondary" href="/modules/dogs">キャンセル</a></form>'''
    return layout("登録解除の確認", body, user)


@app.post("/modules/dogs/{dog_id}/archive")
def dog_archive(dog_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    dog.active = False
    session.commit()
    return RedirectResponse("/modules/dogs", status_code=303)


@app.get("/modules/archived-dogs", response_class=HTMLResponse)
def archived_dogs_page(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(False)).order_by(Dog.call_name)).all()
    rows = "".join(
        f'''<tr><td><strong>{html.escape(dog.call_name)}</strong><br><small>{html.escape(dog.registered_name or "血統書名未登録")}</small></td><td>{html.escape(dog.breed or "-")}</td><td>{"牡" if dog.sex == "male" else "牝"}</td><td>{html.escape(dog.pedigree_no or "-")}</td><td><form class="inline" method="post" action="/modules/dogs/{dog.id}/restore"><button class="success">復元する</button></form></td></tr>'''
        for dog in dogs
    )
    body = f'''<h1>登録解除済みの犬</h1><p>登録解除した犬を復元できます。関連する健康・繁殖・血統・販売履歴は保持されています。</p><table><tr><th>犬名</th><th>犬種</th><th>性別</th><th>血統書番号</th><th>操作</th></tr>{rows or '<tr><td colspan="5">登録解除済みの犬はいません。</td></tr>'}</table><p><a class="button secondary" href="/modules/dogs">犬・血統書管理へ戻る</a></p>'''
    return layout("登録解除済みの犬", body, user)


@app.post("/modules/dogs/{dog_id}/restore")
def dog_restore(dog_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    dog.active = True
    session.commit()
    return RedirectResponse("/modules/archived-dogs", status_code=303)


@app.get("/modules/resident-dogs", response_class=HTMLResponse)
def resident_dogs_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True), Dog.status.in_(["resident", "reserved"]), Dog.category != "external").order_by(Dog.birth_date.desc(), Dog.call_name)).all()
    # 出産管理の記録と、母犬に紐づく仔犬の誕生日を統合する。同じ日付は
    # 同一の出産として数えるため、両方に登録されていても二重計上しない。
    birth_dates_by_dam: dict[int, set[date]] = {}
    litter_records = session.scalars(select(Litter).where(Litter.tenant_id == tenant.id)).all()
    for litter in litter_records:
        birth_dates_by_dam.setdefault(litter.dam_id, set()).add(litter.birth_date)
    registered_puppies = session.scalars(select(Dog).where(
        Dog.tenant_id == tenant.id,
        Dog.category == "puppy",
        Dog.dam_id.is_not(None),
        Dog.birth_date.is_not(None),
    )).all()
    for puppy in registered_puppies:
        birth_dates_by_dam.setdefault(puppy.dam_id, set()).add(puppy.birth_date)
    males = sum(dog.sex == "male" for dog in dogs)
    females = sum(dog.sex == "female" for dog in dogs)
    parents = sum(dog.category == "parent" for dog in dogs)
    puppies = sum(dog.category == "puppy" for dog in dogs)
    metrics = f'''<div class="grid"><div class="module"><h3>在籍合計</h3><p><strong style="font-size:28px">{len(dogs)}</strong>頭</p></div><div class="module"><h3>牡／牝</h3><p><strong>{males}</strong>頭 ／ <strong>{females}</strong>頭</p></div><div class="module"><h3>親犬</h3><p><strong style="font-size:28px">{parents}</strong>頭</p></div><div class="module"><h3>子犬</h3><p><strong style="font-size:28px">{puppies}</strong>頭</p></div></div>'''
    rows = ""
    today = date.today()
    for dog in dogs:
        if dog.birth_date:
            months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
            age = f"{months // 12}歳{months % 12}か月" if months >= 12 else f"{max(months, 0)}か月"
        else:
            age = "-"
        sire = session.get(Dog, dog.sire_id) if dog.sire_id else None
        dam = session.get(Dog, dog.dam_id) if dog.dam_id else None
        category = {"parent":"親犬", "puppy":"子犬"}.get(dog.category, dog.category)
        state = "予約済" if dog.status == "reserved" else "在舎中"
        lifetime_births = len(birth_dates_by_dam.get(dog.id, set())) if dog.sex == "female" else None
        birth_count = f'''<strong>{lifetime_births}</strong>回''' if lifetime_births is not None else "対象外"
        rows += f'''<tr><td><a href="/modules/dogs/{dog.id}"><strong>{html.escape(dog.call_name)}</strong></a><br><small>{html.escape(dog.registered_name or "血統名未登録")}</small></td><td>{title_marks(dog.titles) or "-"}</td><td>{"牡" if dog.sex == "male" else "牝"}</td><td>{category}</td><td>{html.escape(dog.breed or "-")}</td><td>{dog.birth_date or "-"}<br><small>{age}</small></td><td>{html.escape(dog.color or "-")}</td><td>{html.escape(sire.registered_name or sire.call_name) if sire else "-"}</td><td>{html.escape(dam.registered_name or dam.call_name) if dam else "-"}</td><td>{birth_count}</td><td><span class="badge">{state}</span></td><td><a class="button secondary" href="/modules/dogs/{dog.id}/edit">編集</a></td></tr>'''
    body = f'''<h1>在籍犬一覧</h1><p>{html.escape(tenant.name)}で現在管理している在舎中・予約済みの犬を表示しています。</p>{metrics}<table><tr><th>犬名</th><th>タイトル</th><th>性別</th><th>区分</th><th>犬種</th><th>生年月日・年齢</th><th>毛色</th><th>父犬</th><th>母犬</th><th>生涯出産回数</th><th>状態</th><th>操作</th></tr>{rows or '<tr><td colspan="12">在籍犬はまだ登録されていません。</td></tr>'}</table>'''
    return layout("在籍犬一覧", body, user)


@app.get("/modules/transferred-dogs", response_class=HTMLResponse)
def transferred_dogs_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(
        Dog.tenant_id == tenant.id,
        Dog.active.is_(True),
        Dog.status == "transferred",
        Dog.category != "external",
    ).order_by(Dog.birth_date.desc(), Dog.call_name)).all()
    transfers = session.scalars(select(DogTransfer).where(DogTransfer.tenant_id == tenant.id).order_by(DogTransfer.id)).all()
    transfers_by_dog = {transfer.dog_id: transfer for transfer in transfers}
    male_count = sum(dog.sex == "male" for dog in dogs)
    female_count = sum(dog.sex == "female" for dog in dogs)
    puppy_count = sum(dog.category == "puppy" for dog in dogs)
    parent_count = sum(dog.category == "parent" for dog in dogs)
    metrics = f'''<div class="grid"><div class="module"><h3>譲渡済合計</h3><p><strong style="font-size:28px">{len(dogs)}</strong>頭</p></div><div class="module"><h3>牡／牝</h3><p><strong>{male_count}</strong>頭 ／ <strong>{female_count}</strong>頭</p></div><div class="module"><h3>仔犬</h3><p><strong style="font-size:28px">{puppy_count}</strong>頭</p></div><div class="module"><h3>親犬</h3><p><strong style="font-size:28px">{parent_count}</strong>頭</p></div></div>'''
    rows = ""
    for dog in dogs:
        transfer = transfers_by_dog.get(dog.id)
        customer = session.get(Customer, transfer.customer_id) if transfer and transfer.customer_id else None
        recipient = customer.name if customer else "未登録"
        sire = session.get(Dog, dog.sire_id) if dog.sire_id else None
        dam = session.get(Dog, dog.dam_id) if dog.dam_id else None
        category = {"parent": "親犬", "puppy": "仔犬"}.get(dog.category, dog.category)
        handover_date = transfer.transferred_on if transfer else "-"
        transfer_amount = f"¥{transfer.amount:,}" if transfer and transfer.amount is not None else "-"
        transfer_label = "譲渡先を変更" if transfer else "譲渡先を登録"
        rows += f'''<tr><td><a href="/modules/dogs/{dog.id}"><strong>{html.escape(dog.call_name)}</strong></a><br><small>{html.escape(dog.registered_name or "血統名未登録")}</small></td><td>{category}</td><td>{"牡" if dog.sex == "male" else "牝"}</td><td>{html.escape(dog.breed or "-")}</td><td>{dog.birth_date or "-"}</td><td>{html.escape(dog.color or "-")}</td><td>{html.escape(sire.registered_name or sire.call_name) if sire else "-"}</td><td>{html.escape(dam.registered_name or dam.call_name) if dam else "-"}</td><td>{html.escape(recipient)}</td><td>{handover_date}</td><td>{transfer_amount}</td><td><a class="button" href="/modules/transferred-dogs/{dog.id}">{transfer_label}</a> <a class="button secondary" href="/modules/dogs/{dog.id}">詳細</a></td></tr>'''
    body = f'''<h1>譲渡済一覧</h1><p>{html.escape(tenant.name)}で「譲渡済」に設定した犬を表示しています。血統参照用の外部犬は含みません。</p><p><small>有償で販売した仔犬は「販売犬一覧」で管理し、無償・有償を問わない譲渡はこの画面で確認できます。</small></p>{metrics}<table><tr><th>犬名</th><th>区分</th><th>性別</th><th>犬種</th><th>生年月日</th><th>毛色</th><th>父犬</th><th>母犬</th><th>譲渡先</th><th>譲渡日</th><th>譲渡金額</th><th>操作</th></tr>{rows or '<tr><td colspan="12">譲渡済みの犬はいません。</td></tr>'}</table>'''
    return layout("譲渡済一覧", body, user)


@app.get("/modules/transferred-dogs/{dog_id}", response_class=HTMLResponse)
def dog_transfer_page(dog_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if not dog.active or dog.category == "external":
        raise HTTPException(status_code=404, detail="譲渡先を登録できる犬ではありません")
    transfer = session.scalar(select(DogTransfer).where(DogTransfer.tenant_id == tenant.id, DogTransfer.dog_id == dog.id))
    customers = session.scalars(select(Customer).where(Customer.tenant_id == tenant.id).order_by(Customer.name)).all()
    selected_customer_id = transfer.customer_id if transfer else None
    customer_options = '<option value="">新しい譲渡先を入力する</option>' + "".join(
        f'<option value="{customer.id}" {"selected" if customer.id == selected_customer_id else ""}>{html.escape(customer.name)}／{html.escape(customer.phone or customer.email or "連絡先未登録")}</option>'
        for customer in customers
    )
    selected_customer = session.get(Customer, selected_customer_id) if selected_customer_id else None
    registered_customer = ""
    if selected_customer:
        registered_customer = f'''<div class="tenant"><strong>現在の譲渡先</strong><p>{html.escape(selected_customer.name)}　{html.escape(selected_customer.phone or "")}<br>{html.escape(selected_customer.email or "")}<br>{html.escape(selected_customer.postal_code or "")} {html.escape(selected_customer.address or "")}</p></div>'''
    body = f'''<h1>譲渡先の登録</h1><div class="tenant"><h2 style="margin-top:0">{html.escape(dog.call_name)}</h2><p>{html.escape(dog.registered_name or "血統名未登録")}／{"牡" if dog.sex == "male" else "牝"}／{html.escape(dog.breed or "犬種未登録")}</p></div>{registered_customer}
    <form method="post" action="/modules/transferred-dogs/{dog.id}"><h2>登録済みのお客様を選ぶ</h2><label>譲渡先</label><select name="customer_id">{customer_options}</select><p><small>登録済みのお客様を選んだ場合、下の新規入力欄は使用しません。</small></p>
    <h2>新しい譲渡先を登録する</h2><div class="grid"><div><label>お名前</label><input name="customer_name" maxlength="150"></div><div><label>フリガナ</label><input name="customer_name_kana" maxlength="150"></div><div><label>電話番号</label><input name="customer_phone" type="tel" maxlength="50"></div><div><label>メールアドレス</label><input name="customer_email" type="email" maxlength="255"></div><div><label>郵便番号</label><input name="customer_postal_code" maxlength="20"></div><div><label>住所</label><input name="customer_address" maxlength="300"></div></div>
    <h2>譲渡情報</h2><div class="grid"><div><label>譲渡日</label><input name="transferred_on" type="date" value="{transfer.transferred_on if transfer else date.today()}" required></div><div><label>譲渡金額（円）</label><input name="amount" type="number" min="0" step="1" value="{transfer.amount if transfer and transfer.amount is not None else ""}" placeholder="無料の場合は0または空欄"><small>円単位・半角数字で入力してください。</small></div><div><label>譲渡理由</label><select name="reason"><option value="">選択してください</option>{''.join(f'<option value="{value}" {"selected" if transfer and transfer.reason == value else ""}>{value}</option>' for value in ["引退犬の譲渡", "繁殖犬の譲渡", "無償譲渡", "有償譲渡", "共同所有", "その他"])}</select></div></div><label>メモ</label><textarea name="notes" placeholder="譲渡時の取り決め、名義変更、健康状態など">{html.escape(transfer.notes or "") if transfer else ""}</textarea><button>譲渡先情報を保存する</button> <a class="button secondary" href="/modules/transferred-dogs">キャンセル</a></form>'''
    return layout("譲渡先の登録", body, user)


@app.post("/modules/transferred-dogs/{dog_id}")
def dog_transfer_save(
    dog_id: int,
    customer_id: str = Form(""), customer_name: str = Form(""), customer_name_kana: str = Form(""),
    customer_phone: str = Form(""), customer_email: str = Form(""), customer_postal_code: str = Form(""),
    customer_address: str = Form(""), transferred_on: str = Form(...), amount: str = Form(""), reason: str = Form(""), notes: str = Form(""),
    access=Depends(require_tenant_user), session: Session = Depends(db),
):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if not dog.active or dog.category == "external":
        raise HTTPException(status_code=400, detail="譲渡先を登録できる犬ではありません")
    try:
        transfer_date = date.fromisoformat(transferred_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="譲渡日を確認してください")
    if transfer_date > date.today():
        raise HTTPException(status_code=400, detail="未来の日付は譲渡日に登録できません")
    try:
        transfer_amount = int(amount) if amount.strip() else None
    except ValueError:
        raise HTTPException(status_code=400, detail="譲渡金額は円単位の数字で入力してください")
    if transfer_amount is not None and transfer_amount < 0:
        raise HTTPException(status_code=400, detail="譲渡金額は0円以上で入力してください")
    if customer_id:
        try:
            selected_customer_id = int(customer_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="譲渡先を確認してください")
        customer = session.scalar(select(Customer).where(Customer.id == selected_customer_id, Customer.tenant_id == tenant.id))
        if not customer:
            raise HTTPException(status_code=400, detail="譲渡先が見つかりません")
    else:
        if not customer_name.strip():
            raise HTTPException(status_code=400, detail="登録済みのお客様を選ぶか、新しい譲渡先のお名前を入力してください")
        customer = Customer(
            tenant_id=tenant.id, name=customer_name.strip(), name_kana=customer_name_kana.strip() or None,
            phone=customer_phone.strip() or None, email=normalize_email(customer_email) if customer_email.strip() else None,
            postal_code=customer_postal_code.strip() or None, address=customer_address.strip() or None,
            notes="譲渡先登録画面から作成",
        )
        session.add(customer)
        session.flush()
    transfer = session.scalar(select(DogTransfer).where(DogTransfer.tenant_id == tenant.id, DogTransfer.dog_id == dog.id))
    if transfer:
        transfer.customer_id = customer.id
        transfer.transferred_on = transfer_date
        transfer.amount = transfer_amount
        transfer.reason = reason.strip() or None
        transfer.notes = notes.strip() or None
        transfer.updated_at = datetime.now(timezone.utc)
    else:
        session.add(DogTransfer(
            tenant_id=tenant.id, dog_id=dog.id, customer_id=customer.id, transferred_on=transfer_date,
            amount=transfer_amount, reason=reason.strip() or None, notes=notes.strip() or None,
        ))
    dog.status = "transferred"
    session.commit()
    return RedirectResponse("/modules/transferred-dogs", status_code=303)


@app.get("/modules/dog-list/{category}", response_class=HTMLResponse)
def categorized_dogs_page(category: str, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    labels = {"puppy": "仔犬一覧", "parent": "親犬一覧", "external": "外部犬一覧"}
    if category not in labels:
        raise HTTPException(status_code=404)
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True), Dog.category == category).order_by(Dog.birth_date.desc(), Dog.registered_name, Dog.call_name)).all()
    status_labels = {"resident":"在舎中", "reserved":"予約済", "delivered":"販売済", "retired":"引退", "transferred":"譲渡済"}
    male_count = sum(dog.sex == "male" for dog in dogs)
    female_count = sum(dog.sex == "female" for dog in dogs)
    resident_count = sum(dog.status in {"resident", "reserved"} for dog in dogs)
    rows = ""
    for dog in dogs:
        sire = session.get(Dog, dog.sire_id) if dog.sire_id else None
        dam = session.get(Dog, dog.dam_id) if dog.dam_id else None
        sale = session.scalar(select(PuppySale).where(PuppySale.tenant_id == tenant.id, PuppySale.dog_id == dog.id).order_by(PuppySale.id.desc())) if category == "puppy" else None
        customer = session.get(Customer, sale.customer_id) if sale and sale.customer_id else None
        buyer_name = customer.name if customer else sale.customer_name if sale else "-"
        rows += f'''<tr><td><a href="/modules/dogs/{dog.id}"><strong>{html.escape(dog.call_name)}</strong></a><br><small>{html.escape(dog.registered_name or "血統名未登録")}</small></td><td>{title_marks(dog.titles) or "-"}</td><td>{"牡" if dog.sex == "male" else "牝"}</td><td>{html.escape(dog.breed or "-")}</td><td>{dog.birth_date or "-"}</td><td>{html.escape(dog.color or "-")}</td><td>{html.escape(dog.pedigree_no or "-")}</td><td>{html.escape(sire.registered_name or sire.call_name) if sire else "-"}</td><td>{html.escape(dam.registered_name or dam.call_name) if dam else "-"}</td><td><span class="badge">{status_labels.get(dog.status, dog.status)}</span></td>{f'<td>{html.escape(buyer_name)}</td>' if category == 'puppy' else ''}<td><a class="button secondary" href="/modules/dogs/{dog.id}/edit">編集</a></td></tr>'''
    buyer_header = "<th>販売先</th>" if category == "puppy" else ""
    columns = 12 if category == "puppy" else 11
    metrics = f'''<div class="grid"><div class="module"><h3>登録頭数</h3><p><strong style="font-size:28px">{len(dogs)}</strong>頭</p></div><div class="module"><h3>牡</h3><p><strong style="font-size:28px">{male_count}</strong>頭</p></div><div class="module"><h3>牝</h3><p><strong style="font-size:28px">{female_count}</strong>頭</p></div><div class="module"><h3>在舎・予約中</h3><p><strong style="font-size:28px">{resident_count}</strong>頭</p></div></div>'''
    description = "血統参照・交配検討のために登録した犬です。" if category == "external" else "登録済みの犬を状態にかかわらず表示しています。"
    body = f'''<h1>{labels[category]}</h1><p>{html.escape(tenant.name)} — {description}</p>{metrics}<table><tr><th>犬名</th><th>タイトル</th><th>性別</th><th>犬種</th><th>生年月日</th><th>毛色</th><th>血統書番号</th><th>父犬</th><th>母犬</th><th>状態</th>{buyer_header}<th>操作</th></tr>{rows or f'<tr><td colspan="{columns}">登録犬はいません。</td></tr>'}</table>'''
    return layout(labels[category], body, user)


@app.get("/modules/sale-dogs", response_class=HTMLResponse)
def sale_dogs_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    puppies = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True), Dog.category == "puppy").order_by(Dog.dam_id, Dog.birth_date.desc(), Dog.call_name)).all()
    sales = session.scalars(select(PuppySale).where(PuppySale.tenant_id == tenant.id).order_by(PuppySale.id)).all()
    sales_by_dog = {sale.dog_id: sale for sale in sales}
    dog_states = {"resident":"販売中", "reserved":"予約済", "delivered":"販売済", "retired":"引退", "transferred":"譲渡済"}
    sale_states = {
        "inquiry":"問い合わせ", "visit":"見学予定", "consideration":"検討中", "reserved":"予約済み",
        "contracted":"契約済み", "paid":"入金済み", "handed_over":"販売完了", "cancelled":"キャンセル",
    }
    groups: dict[int | None, list[Dog]] = {}
    for puppy in puppies:
        groups.setdefault(puppy.dam_id, []).append(puppy)
    available = sum(puppy.status == "resident" for puppy in puppies)
    reserved = sum(puppy.status == "reserved" for puppy in puppies)
    sold = sum(puppy.status == "delivered" for puppy in puppies)
    planned_total = sum((sales_by_dog.get(puppy.id).price or 0) for puppy in puppies if sales_by_dog.get(puppy.id) and sales_by_dog.get(puppy.id).status != "cancelled")
    metrics = f'''<div class="grid"><div class="module"><h3>販売中</h3><p><strong style="font-size:28px">{available}</strong>頭</p></div><div class="module"><h3>予約済</h3><p><strong style="font-size:28px">{reserved}</strong>頭</p></div><div class="module"><h3>販売済</h3><p><strong style="font-size:28px">{sold}</strong>頭</p></div><div class="module"><h3>販売登録額</h3><p><strong style="font-size:24px">¥{planned_total:,}</strong></p></div></div>'''
    sections = ""
    for dam_id, group in groups.items():
        dam = session.get(Dog, dam_id) if dam_id else None
        dam_name = dam.registered_name or dam.call_name if dam else "母犬未登録"
        litters: dict[date | None, list[Dog]] = {}
        for puppy in group:
            litters.setdefault(puppy.birth_date, []).append(puppy)
        known_birth_dates = sorted((birth_date for birth_date in litters if birth_date is not None))
        birth_numbers = {birth_date: index for index, birth_date in enumerate(known_birth_dates, start=1)}
        litter_panels = ""
        ordered_birth_dates = sorted(known_birth_dates, reverse=True) + ([None] if None in litters else [])
        for birth_date in ordered_birth_dates:
            litter = litters[birth_date]
            rows = ""
            litter_sold = sum(puppy.status == "delivered" for puppy in litter)
            litter_reserved = sum(puppy.status == "reserved" for puppy in litter)
            litter_available = sum(puppy.status == "resident" for puppy in litter)
            for puppy in litter:
                sale = sales_by_dog.get(puppy.id)
                customer = session.get(Customer, sale.customer_id) if sale and sale.customer_id else None
                buyer = customer.name if customer else sale.customer_name if sale else "-"
                remaining = max((sale.price or 0) - (sale.paid_amount or 0), 0) if sale else 0
                rows += f'''<tr><td><a href="/modules/dogs/{puppy.id}"><strong>{html.escape(puppy.call_name)}</strong></a><br><small>{html.escape(puppy.registered_name or "血統名未登録")}</small></td><td>{"牡" if puppy.sex == "male" else "牝"}</td><td>{html.escape(puppy.color or "-")}</td><td><span class="badge">{dog_states.get(puppy.status, puppy.status)}</span></td><td>{sale_states.get(sale.status, sale.status) if sale else "未登録"}</td><td>{html.escape(buyer)}</td><td>{f'¥{sale.price:,}' if sale and sale.price is not None else "-"}</td><td>{f'¥{remaining:,}' if sale else "-"}</td><td>{sale.handover_date if sale and sale.handover_date else "-"}</td><td><a class="button secondary" href="/modules/dogs/{puppy.id}">詳細</a> <a class="button" href="/modules/sales">販売管理</a></td></tr>'''
            if birth_date:
                birth_label = f'''第{birth_numbers[birth_date]}回出産　{birth_date.strftime("%Y年%m月%d日")}'''
            else:
                birth_label = "出産日未登録"
            state_summary = f'''販売中 {litter_available}頭／予約済 {litter_reserved}頭／販売済 {litter_sold}頭'''
            litter_panels += f'''<details class="litter-panel"><summary><span><strong>{birth_label}</strong><span class="badge">{len(litter)}頭</span></span><small>{state_summary}　クリックして詳細を表示</small></summary><div class="litter-table"><table><tr><th>仔犬</th><th>性別</th><th>毛色</th><th>犬の状態</th><th>商談段階</th><th>販売先</th><th>価格</th><th>残金</th><th>引渡し日</th><th>管理</th></tr>{rows}</table></div></details>'''
        sections += f'''<div class="tenant dam-section"><h2 style="margin-top:0">母犬：{html.escape(dam_name)}</h2><p class="dam-summary">出産 {len(known_birth_dates)}回・登録仔犬 {len(group)}頭</p>{litter_panels}</div>'''
    body = f'''<style>
    .dam-section{{margin-bottom:22px}} .dam-summary{{color:#765f68;margin-top:-8px}}
    .litter-panel{{border:1px solid #ead9df;border-radius:12px;margin:10px 0;background:#fff}}
    .litter-panel summary{{cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:16px 18px;list-style:none;background:#fbf3f6;border-radius:12px}}
    .litter-panel summary::-webkit-details-marker{{display:none}} .litter-panel summary:after{{content:"＋";font-size:22px;color:#a85f76}}
    .litter-panel[open] summary:after{{content:"−"}} .litter-panel summary span{{display:flex;align-items:center;gap:10px}}
    .litter-panel summary small{{margin-left:auto;color:#765f68;text-align:right}} .litter-table{{padding:8px 14px 14px;overflow-x:auto}}
    @media(max-width:760px){{.litter-panel summary{{align-items:flex-start;flex-direction:column}}.litter-panel summary small{{margin-left:0;text-align:left}}}}
    </style><h1>販売犬一覧</h1><p>{html.escape(tenant.name)}の販売犬を、母犬・出産回ごとに整理しています。出産回をクリックすると仔犬と販売情報を確認できます。</p>{metrics}{sections or '<div class="tenant"><p>販売管理対象の仔犬はまだ登録されていません。</p></div>'}<p><a class="button" href="/modules/sales">顧客・商談・契約・入金を管理する</a></p>'''
    return layout("販売犬一覧", body, user)


@app.post("/modules/dogs")
def dog_create(call_name: str = Form(...), registered_name: str = Form(""), breed: str = Form(""), sex: str = Form(...), category: str = Form("parent"), status: str = Form("resident"), birth_date: str = Form(""), color: str = Form(""), sire_id: str = Form(""), dam_id: str = Form(""), microchip_no: str = Form(""), pedigree_no: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    if sex not in {"male", "female"}:
        raise HTTPException(status_code=400)
    parsed_birth = date.fromisoformat(birth_date) if birth_date else None
    if category not in {"parent", "puppy", "external"} or status not in {"resident", "reserved", "delivered", "retired", "transferred"}:
        raise HTTPException(status_code=400)
    sire = tenant_dog(session, tenant.id, int(sire_id)) if sire_id else None
    dam = tenant_dog(session, tenant.id, int(dam_id)) if dam_id else None
    if (sire and sire.sex != "male") or (dam and dam.sex != "female"):
        raise HTTPException(status_code=400, detail="父犬・母犬を確認してください")
    session.add(Dog(tenant_id=tenant.id, call_name=call_name.strip(), registered_name=registered_name.strip() or None, breed=breed.strip() or None, sex=sex, category=category, status=status, birth_date=parsed_birth, color=color.strip() or None, sire_id=sire.id if sire else None, dam_id=dam.id if dam else None, microchip_no=microchip_no.strip() or None, pedigree_no=pedigree_no.strip() or None))
    session.commit()
    return RedirectResponse("/modules/dogs", status_code=303)


def pedigree_flow_chart(session: Session, tenant_id: int, root: Dog) -> str:
    """4世代15頭を固定グリッドへ配置し、親子関係をSVG線で結ぶ。"""
    nodes: dict[int, Dog | None] = {0: root}
    for index in range(7):
        node = nodes.get(index)
        nodes[index * 2 + 1] = session.scalar(select(Dog).where(Dog.id == node.sire_id, Dog.tenant_id == tenant_id)) if node and node.sire_id else None
        nodes[index * 2 + 2] = session.scalar(select(Dog).where(Dog.id == node.dam_id, Dog.tenant_id == tenant_id)) if node and node.dam_id else None

    x_positions = {0: 15, 1: 260, 2: 505, 3: 750}
    y_positions = {
        0: [390], 1: [170, 610], 2: [60, 280, 500, 720],
        3: [5, 115, 225, 335, 445, 555, 665, 775],
    }
    positions: dict[int, tuple[int, int]] = {}
    cards = ""
    for index in range(15):
        level = 0 if index == 0 else 1 if index <= 2 else 2 if index <= 6 else 3
        offset = index - (2 ** level - 1)
        x, y = x_positions[level], y_positions[level][offset]
        positions[index] = (x, y)
        dog = nodes.get(index)
        label = "登録犬" if index == 0 else PEDIGREE_LABELS[index]
        if dog:
            name = html.escape(dog.registered_name or dog.call_name)
            call_name = f'<small>{html.escape(dog.call_name)}</small>' if dog.registered_name and dog.call_name != dog.registered_name else ""
            marks = title_marks(dog.titles)
            card = f'''<a class="pedigree-node" style="left:{x}px;top:{y}px" href="/modules/dogs/{dog.id}"><span class="pedigree-role">{label}</span><strong>{name}</strong>{call_name}<span class="pedigree-sex">{"牡" if dog.sex == "male" else "牝"}</span><span class="pedigree-color">毛色：{html.escape(dog.color or "未登録")}</span><span class="pedigree-titles">{marks or "称号なし"}</span></a>'''
        else:
            card = f'''<div class="pedigree-node missing" style="left:{x}px;top:{y}px"><span class="pedigree-role">{label}</span><strong>未登録</strong><span class="pedigree-titles">－</span></div>'''
        cards += card

    lines = ""
    for parent_index in range(7):
        x1, y1 = positions[parent_index]
        for ancestor_index in (parent_index * 2 + 1, parent_index * 2 + 2):
            x2, y2 = positions[ancestor_index]
            start_x, start_y = x1 + 205, y1 + 53
            end_x, end_y = x2, y2 + 53
            middle_x = (start_x + end_x) // 2
            lines += f'''<path d="M {start_x} {start_y} H {middle_x} V {end_y} H {end_x}"/>'''
    return f'''<div class="pedigree-scroll"><div class="pedigree-canvas"><svg class="pedigree-lines" viewBox="0 0 970 885" aria-hidden="true">{lines}</svg>{cards}</div></div>'''


@app.get("/modules/dogs/{dog_id}", response_class=HTMLResponse)
def dog_detail_page(dog_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    status_labels = {"resident":"在舎中", "reserved":"予約済", "delivered":"販売済", "retired":"引退", "transferred":"譲渡済"}
    category_labels = {"parent":"親犬", "puppy":"子犬", "external":"外部犬"}
    sale = session.scalar(select(PuppySale).where(PuppySale.tenant_id == tenant.id, PuppySale.dog_id == dog.id).order_by(PuppySale.id.desc()))
    customer = session.get(Customer, sale.customer_id) if sale and sale.customer_id else None
    buyer = customer.name if customer else sale.customer_name if sale else None
    uploads = session.scalars(select(PedigreeUpload).where(PedigreeUpload.tenant_id == tenant.id, PedigreeUpload.dog_id == dog.id).order_by(PedigreeUpload.uploaded_at.desc())).all()
    upload_views = ""
    for index, item in enumerate(uploads):
        source = f"/modules/dogs/{dog.id}/pedigree-files/{item.id}"
        preview = f'<img src="{source}" alt="血統書" style="max-width:100%;max-height:900px;object-fit:contain">' if item.content_type.startswith("image/") else f'<iframe src="{source}" title="血統書PDF" style="width:100%;height:800px;border:1px solid #eadde1;border-radius:10px"></iframe>' if item.content_type == "application/pdf" else ""
        kind = PEDIGREE_DOCUMENT_TYPES.get(item.document_type or "other", "その他")
        primary = ' <span class="badge">国内メイン</span>' if item.is_primary else ''
        upload_views += f'<details {"open" if index == 0 else ""}><summary>{html.escape(kind)}／{html.escape(item.registration_no or "番号未登録")}{primary}</summary><p>{html.escape(item.organization or "団体未登録")}／{html.escape(item.country or "国未登録")}／発行日 {item.issued_on or "未登録"}／保存日 {item.uploaded_at.date()}</p><p><a class="button secondary" href="{source}" target="_blank">原本を別画面で開く</a></p>{preview}</details>'
    document_section = f'''<style>
    .pedigree-documents details{{margin:10px 0;border:1px solid #dfc8ce;border-radius:12px;background:#fff;overflow:hidden;transition:border-color .18s,box-shadow .18s,transform .18s}}
    .pedigree-documents details:hover{{border-color:#b66f7c;box-shadow:0 6px 16px #70445420;transform:translateY(-1px)}}
    .pedigree-documents details[open]{{border-color:#c9919c;box-shadow:0 5px 15px #70445417}}
    .pedigree-documents summary{{position:relative;display:block;padding:15px 48px 15px 17px;cursor:pointer;font-weight:750;color:#63404c;background:#fff;transition:background .18s,color .18s;list-style:none}}
    .pedigree-documents summary::-webkit-details-marker{{display:none}}.pedigree-documents summary:hover{{background:#f8e9ed;color:#8f4f60}}
    .pedigree-documents summary:after{{content:'›';position:absolute;right:18px;top:50%;font-size:26px;line-height:1;transform:translateY(-50%) rotate(90deg);transition:transform .18s;color:#b66f7c}}
    .pedigree-documents details[open] summary:after{{transform:translateY(-50%) rotate(-90deg)}}
    .pedigree-documents .document-hint{{margin:4px 0 10px;color:#806b72;font-size:12px}}
    .pedigree-documents details>p,.pedigree-documents details>img,.pedigree-documents details>iframe{{margin-left:17px;margin-right:17px;max-width:calc(100% - 34px)}}
    </style><div class="tenant pedigree-documents"><h2 style="margin-top:0">アップロード済み血統書</h2><p class="document-hint">各項目をクリックすると、保存した血統書原本を表示できます。</p>{upload_views or '<p>血統書原本はまだ保存されていません。</p>'}</div>'''
    flow = pedigree_flow_chart(session, tenant.id, dog)
    info = [
        ("呼び名", dog.call_name), ("血統書名", dog.registered_name or "－"), ("犬種", dog.breed or "－"),
        ("性別", "牡" if dog.sex == "male" else "牝"), ("区分", category_labels.get(dog.category, dog.category)),
        ("状態", status_labels.get(dog.status, dog.status)), ("生年月日", str(dog.birth_date or "－")),
        ("毛色", dog.color or "－"), ("国内メイン番号（JKC）", dog.pedigree_no or "－"),
        ("出生国・海外登録番号", dog.origin_registration_no or "－"),
        ("出生国", dog.origin_registration_country or "－"), ("海外発行団体", dog.origin_registration_organization or "－"),
        ("マイクロチップ番号", dog.microchip_no or "－"), ("発行団体", dog.pedigree_organization or "－"),
        ("発行国", dog.pedigree_country or "－"), ("販売先", buyer or "－"),
    ]
    info_html = "".join(f'''<div><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>''' for label, value in info)
    body = f'''<style>
    .detail-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:20px}}.detail-head .button{{margin-top:0}}
    .dog-facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:1px;background:#eadde1;border:1px solid #eadde1;border-radius:14px;overflow:hidden;margin:18px 0 30px}}
    .dog-facts div{{background:#fff;padding:14px}}.dog-facts dt{{font-size:12px;color:#765f68;font-weight:700}}.dog-facts dd{{margin:5px 0 0;font-weight:650}}
    .pedigree-scroll{{overflow-x:auto;overflow-y:hidden;padding:10px 0 24px;width:100%}}.pedigree-canvas{{position:relative;width:970px;height:885px;min-width:970px;margin:0 auto;background:linear-gradient(90deg,#fff 0%,#fffafc 100%);border:1px solid #f0e1e5;border-radius:16px}}
    .pedigree-lines{{position:absolute;inset:0;width:970px;height:885px;pointer-events:none}}.pedigree-lines path{{fill:none;stroke:#c990a0;stroke-width:2;vector-effect:non-scaling-stroke}}
    .pedigree-node{{position:absolute;width:205px;height:106px;padding:6px 9px;border:1px solid #dfc8ce;border-radius:10px;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#49323a;text-decoration:none;box-shadow:0 4px 12px #69404c12;overflow:hidden;text-align:center}}
    .pedigree-node:hover{{border-color:#b66f7c;background:#fff8fa}}.pedigree-node.missing{{opacity:.55;border-style:dashed}}.pedigree-role{{font-size:10px;color:#9a6d79;font-weight:700}}.pedigree-node strong{{font-size:11px;line-height:1.2;margin:2px 0;overflow-wrap:anywhere;max-width:100%}}.pedigree-node small{{font-size:9px;color:#806b72}}.pedigree-sex{{font-size:10px}}.pedigree-color{{font-size:9px;color:#765f68;line-height:1.2;margin-top:1px}}.pedigree-titles{{font-size:9px;min-height:18px;margin-top:1px;white-space:nowrap}}.pedigree-titles .title-crown{{font-size:14px;margin:0 2px}}
    @media(max-width:1100px){{.pedigree-canvas{{margin:0}}}}
    </style><div class="detail-head"><div><h1>{html.escape(dog.call_name)}の詳細</h1><p>{title_marks(dog.titles)} <strong>{html.escape(dog.registered_name or dog.call_name)}</strong></p></div><a class="button" href="/modules/dogs/{dog.id}/edit">編集する</a></div>
    <dl class="dog-facts">{info_html}</dl><h2>血統構成フローチャート</h2><p><small>各個体をクリックすると、その犬の詳細ページを開きます。王冠は登録されている称号を表します。</small></p>{flow}{document_section}<p><a class="button secondary" href="/modules/resident-dogs">在籍犬一覧へ戻る</a></p>'''
    return layout(f"{dog.call_name}の詳細", body, user)


@app.get("/modules/dogs/{dog_id}/edit", response_class=HTMLResponse)
def dog_edit_page(dog_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    customers = session.scalars(select(Customer).where(Customer.tenant_id == tenant.id).order_by(Customer.name)).all()
    sale = session.scalar(select(PuppySale).where(PuppySale.tenant_id == tenant.id, PuppySale.dog_id == dog.id).order_by(PuppySale.id.desc()))
    selected_customer_id = sale.customer_id if sale else None
    customer_options = '<option value="">販売先を選択しない</option>' + "".join(
        f'<option value="{customer.id}" {"selected" if customer.id == selected_customer_id else ""}>{html.escape(customer.name)}／{html.escape(customer.phone or customer.email or "連絡先未登録")}</option>'
        for customer in customers
    )
    category_options = "".join(f'<option value="{key}" {"selected" if dog.category == key else ""}>{label}</option>' for key, label in {"parent":"親犬", "puppy":"子犬", "external":"外部犬"}.items())
    status_options = "".join(f'<option value="{key}" {"selected" if dog.status == key else ""}>{label}</option>' for key, label in {"resident":"在舎中", "reserved":"予約済", "delivered":"販売済", "retired":"引退", "transferred":"譲渡済"}.items())
    sex_options = f'<option value="male" {"selected" if dog.sex == "male" else ""}>牡</option><option value="female" {"selected" if dog.sex == "female" else ""}>牝</option>'
    possible_parents = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.id != dog.id).order_by(Dog.registered_name, Dog.call_name)).all()
    sire_options = '<option value="">未登録</option>' + "".join(f'<option value="{parent.id}" {"selected" if dog.sire_id == parent.id else ""}>{html.escape(parent.registered_name or parent.call_name)}</option>' for parent in possible_parents if parent.sex == "male")
    dam_options = '<option value="">未登録</option>' + "".join(f'<option value="{parent.id}" {"selected" if dog.dam_id == parent.id else ""}>{html.escape(parent.registered_name or parent.call_name)}</option>' for parent in possible_parents if parent.sex == "female")
    selected_titles = set((dog.titles or "").split(","))
    title_options = "".join(f'<option value="{key}" {"selected" if key in selected_titles else ""}>{label[2]}（{label[0]}）</option>' for key, label in TITLE_LABELS.items())
    sire = session.get(Dog, dog.sire_id) if dog.sire_id else None
    dam = session.get(Dog, dog.dam_id) if dog.dam_id else None
    grands = [session.get(Dog, parent_id) if parent_id else None for parent_id in [sire.sire_id if sire else None, sire.dam_id if sire else None, dam.sire_id if dam else None, dam.dam_id if dam else None]]
    pedigree_summary = f'''<div class="tenant"><h2 style="margin-top:0">血統構成</h2><div class="grid"><div><label>本犬</label><strong>{html.escape(dog.registered_name or dog.call_name)}</strong></div><div><label>父犬</label>{html.escape(sire.registered_name or sire.call_name) if sire else "未登録"}</div><div><label>母犬</label>{html.escape(dam.registered_name or dam.call_name) if dam else "未登録"}</div><div><label>父方祖父</label>{html.escape(grands[0].registered_name or grands[0].call_name) if grands[0] else "未登録"}</div><div><label>父方祖母</label>{html.escape(grands[1].registered_name or grands[1].call_name) if grands[1] else "未登録"}</div><div><label>母方祖父</label>{html.escape(grands[2].registered_name or grands[2].call_name) if grands[2] else "未登録"}</div><div><label>母方祖母</label>{html.escape(grands[3].registered_name or grands[3].call_name) if grands[3] else "未登録"}</div></div></div>'''
    uploads = session.scalars(select(PedigreeUpload).where(PedigreeUpload.tenant_id == tenant.id, PedigreeUpload.dog_id == dog.id).order_by(PedigreeUpload.uploaded_at.desc())).all()
    upload_views = ""
    for index, item in enumerate(uploads):
        source = f"/modules/dogs/{dog.id}/pedigree-files/{item.id}"
        preview = f'<img src="{source}" alt="血統書" style="max-width:100%;max-height:900px;object-fit:contain">' if item.content_type.startswith("image/") else f'<iframe src="{source}" title="血統書PDF" style="width:100%;height:800px;border:1px solid #eadde1;border-radius:10px"></iframe>' if item.content_type == "application/pdf" else ""
        kind = PEDIGREE_DOCUMENT_TYPES.get(item.document_type or "other", "その他")
        primary = ' <span class="badge">国内メイン</span>' if item.is_primary else ''
        upload_views += f'<details {"open" if index == 0 else ""}><summary>{html.escape(kind)}／{html.escape(item.registration_no or "番号未登録")}{primary}</summary><p>{html.escape(item.organization or "団体未登録")}／{html.escape(item.country or "国未登録")}／発行日 {item.issued_on or "未登録"}／保存日 {item.uploaded_at.date()}</p><p><a class="button secondary" href="{source}" target="_blank">原本を別画面で開く</a></p>{preview}</details>'
    document_section = f'''<style>
    .pedigree-documents details{{margin:10px 0;border:1px solid #dfc8ce;border-radius:12px;background:#fff;overflow:hidden;transition:border-color .18s,box-shadow .18s,transform .18s}}
    .pedigree-documents details:hover{{border-color:#b66f7c;box-shadow:0 6px 16px #70445420;transform:translateY(-1px)}}.pedigree-documents details[open]{{border-color:#c9919c}}
    .pedigree-documents summary{{position:relative;display:block;padding:15px 48px 15px 17px;cursor:pointer;font-weight:750;color:#63404c;transition:background .18s,color .18s;list-style:none}}
    .pedigree-documents summary::-webkit-details-marker{{display:none}}.pedigree-documents summary:hover{{background:#f8e9ed;color:#8f4f60}}
    .pedigree-documents summary:after{{content:'›';position:absolute;right:18px;top:50%;font-size:26px;transform:translateY(-50%) rotate(90deg);transition:transform .18s;color:#b66f7c}}
    .pedigree-documents details[open] summary:after{{transform:translateY(-50%) rotate(-90deg)}}
    .pedigree-documents .document-hint{{margin:4px 0 10px;color:#806b72;font-size:12px}}
    .pedigree-documents details>p,.pedigree-documents details>img,.pedigree-documents details>iframe{{margin-left:17px;margin-right:17px;max-width:calc(100% - 34px)}}
    </style><div class="tenant pedigree-documents"><h2 style="margin-top:0">アップロードした血統書原本</h2><p class="document-hint">各項目をクリックすると、保存した血統書原本を表示できます。</p>{upload_views or "<p>この犬には原本ファイルがまだ保存されていません。次回の血統書読み込みから自動保存されます。</p>"}</div>'''
    body = f'''<h1>犬・血統書の詳細／編集</h1><p>{title_marks(dog.titles)} <strong>{html.escape(dog.registered_name or dog.call_name)}</strong></p>{document_section}{pedigree_summary}
    <form method="post"><h2>基本情報・血統書情報</h2><div class="grid"><div><label>呼び名</label><input name="call_name" value="{html.escape(dog.call_name)}" required></div><div><label>犬種（自由入力可）</label><input name="breed" value="{html.escape(dog.breed or '')}" maxlength="150" placeholder="例：ミックス（シュナウザー×プードル）"></div><div><label>血統書名</label><input name="registered_name" value="{html.escape(dog.registered_name or '')}"></div><div><label>性別</label><select name="sex">{sex_options}</select></div><div><label>区分</label><select name="category">{category_options}</select></div><div><label>現在の状態</label><select name="status">{status_options}</select></div><div><label>生年月日</label><input type="date" name="birth_date" value="{dog.birth_date or ''}"></div><div><label>毛色</label><input name="color" value="{html.escape(dog.color or '')}"></div><div><label>国内メイン番号（JKC）</label><input name="pedigree_no" value="{html.escape(dog.pedigree_no or '')}" placeholder="例：JKC-MS-07782/25-I"></div><div><label>出生国・海外登録番号</label><input name="origin_registration_no" value="{html.escape(dog.origin_registration_no or '')}" placeholder="例：KATH116090377"></div><div><label>マイクロチップ番号</label><input name="microchip_no" value="{html.escape(dog.microchip_no or '')}"></div><div><label>国内発行団体</label><input name="pedigree_organization" value="{html.escape(dog.pedigree_organization or '')}"></div><div><label>国内発行国</label><input name="pedigree_country" value="{html.escape(dog.pedigree_country or '')}"></div><div><label>出生国</label><input name="origin_registration_country" value="{html.escape(dog.origin_registration_country or '')}"></div><div><label>海外発行団体</label><input name="origin_registration_organization" value="{html.escape(dog.origin_registration_organization or '')}"></div><div><label>父犬</label><select name="sire_id">{sire_options}</select></div><div><label>母犬</label><select name="dam_id">{dam_options}</select></div><div><label>引渡し日</label><input type="date" name="handover_date" value="{sale.handover_date if sale and sale.handover_date else ''}"></div></div>
    <label>タイトル（複数選択可）</label><select name="titles" multiple size="8">{title_options}</select><p><small>Macは⌘キー、WindowsはCtrlキーを押しながら選択すると複数指定できます。</small></p>
    <h2>販売先のお客様</h2><label>登録済みのお客様から選択</label><select name="customer_id">{customer_options}</select>
    <details><summary>新しいお客様をここで登録する</summary><div class="grid"><div><label>お客様名</label><input name="customer_name"></div><div><label>電話番号</label><input name="customer_phone"></div><div><label>メールアドレス</label><input type="email" name="customer_email"></div><div><label>住所</label><input name="customer_address"></div></div></details>
    <p><small>新しいお客様名を入力した場合は、登録済みのお客様の選択より優先されます。「販売済」にすると販売管理にも販売完了として反映します。</small></p><button>変更を保存</button> <a class="button secondary" href="/modules/dogs">キャンセル</a></form>'''
    return layout("犬の編集", body, user)


@app.get("/modules/dogs/{dog_id}/pedigree-files/{upload_id}")
def pedigree_file(dog_id: int, upload_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    tenant_dog(session, tenant.id, dog_id)
    upload = session.scalar(select(PedigreeUpload).where(PedigreeUpload.id == upload_id, PedigreeUpload.dog_id == dog_id, PedigreeUpload.tenant_id == tenant.id))
    if not upload:
        raise HTTPException(status_code=404, detail="血統書原本が見つかりません")
    return Response(content=upload.file_data, media_type=upload.content_type)


@app.post("/modules/dogs/{dog_id}/edit")
def dog_edit(
    dog_id: int, call_name: str = Form(...), category: str = Form(...), status_value: str = Form(..., alias="status"),
    registered_name: str = Form(""), breed: str = Form(""), sex: str = Form(...), birth_date: str = Form(""), color: str = Form(""),
    pedigree_no: str = Form(""), origin_registration_no: str = Form(""), microchip_no: str = Form(""), pedigree_organization: str = Form(""), pedigree_country: str = Form(""),
    origin_registration_country: str = Form(""), origin_registration_organization: str = Form(""),
    sire_id: str = Form(""), dam_id: str = Form(""), titles: list[str] = Form([]),
    customer_id: str = Form(""), customer_name: str = Form(""), customer_phone: str = Form(""),
    customer_email: str = Form(""), customer_address: str = Form(""), handover_date: str = Form(""),
    access=Depends(require_tenant_user), session: Session = Depends(db),
):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if sex not in {"male", "female"} or category not in {"parent", "puppy", "external"} or status_value not in {"resident", "reserved", "delivered", "retired", "transferred"}:
        raise HTTPException(status_code=400, detail="犬の区分・状態を確認してください")
    sire = tenant_dog(session, tenant.id, int(sire_id)) if sire_id else None
    dam = tenant_dog(session, tenant.id, int(dam_id)) if dam_id else None
    if (sire and (sire.sex != "male" or sire.id == dog.id)) or (dam and (dam.sex != "female" or dam.id == dog.id)):
        raise HTTPException(status_code=400, detail="父犬・母犬を確認してください")
    dog.call_name, dog.registered_name, dog.sex = call_name.strip(), registered_name.strip() or None, sex
    dog.breed = breed.strip() or None
    dog.category, dog.status = category, status_value
    dog.birth_date = date.fromisoformat(birth_date) if birth_date else None
    dog.color, dog.pedigree_no = color.strip() or None, pedigree_no.strip() or None
    dog.origin_registration_no = origin_registration_no.strip() or None
    dog.origin_registration_country = origin_registration_country.strip() or None
    dog.origin_registration_organization = origin_registration_organization.strip() or None
    dog.microchip_no = microchip_no.strip() or None
    dog.pedigree_organization, dog.pedigree_country = pedigree_organization.strip() or None, pedigree_country.strip() or None
    dog.sire_id, dog.dam_id = sire.id if sire else None, dam.id if dam else None
    dog.titles = ",".join(key for key in titles if key in TITLE_LABELS) or None
    customer = None
    if customer_name.strip():
        customer = Customer(tenant_id=tenant.id, name=customer_name.strip(), email=normalize_email(customer_email) if customer_email else None, phone=customer_phone.strip() or None, address=customer_address.strip() or None)
        session.add(customer)
        session.flush()
    elif customer_id:
        try:
            selected_id = int(customer_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="販売先のお客様を確認してください")
        customer = session.scalar(select(Customer).where(Customer.id == selected_id, Customer.tenant_id == tenant.id))
        if not customer:
            raise HTTPException(status_code=400, detail="販売先のお客様が見つかりません")
    sale = session.scalar(select(PuppySale).where(PuppySale.tenant_id == tenant.id, PuppySale.dog_id == dog.id).order_by(PuppySale.id.desc()))
    if customer:
        if not sale:
            sale = PuppySale(tenant_id=tenant.id, dog_id=dog.id, customer_id=customer.id, customer_name=customer.name, customer_email=customer.email)
            session.add(sale)
        else:
            sale.customer_id, sale.customer_name, sale.customer_email = customer.id, customer.name, customer.email
        if status_value == "delivered":
            sale.status = "handed_over"
            sale.handover_date = date.fromisoformat(handover_date) if handover_date else sale.handover_date
        elif status_value == "reserved" and sale.status in {"inquiry", "visit", "consideration"}:
            sale.status = "reserved"
    session.commit()
    return RedirectResponse("/modules/dogs", status_code=303)


@app.get("/modules/genetics", response_class=HTMLResponse)
def genetics_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id).order_by(Dog.call_name)).all()
    options = "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in dogs)
    tests = session.scalars(select(GeneticTest).where(GeneticTest.tenant_id == tenant.id).order_by(GeneticTest.tested_on.desc())).all()
    labels = {"clear": "クリア", "carrier": "キャリア", "affected": "アフェクテッド", "unknown": "不明"}
    rows = "".join(f"<tr><td>{html.escape(session.get(Dog,t.dog_id).call_name)}</td><td>{html.escape(t.test_name)}</td><td>{labels.get(t.result,t.result)}</td><td>{t.tested_on or '-'}</td><td>{html.escape(t.laboratory or '-')}</td></tr>" for t in tests)
    body = f'''<h1>遺伝子検査・遺伝病管理</h1><form method="post"><div class="grid"><div><label>対象犬</label><select name="dog_id">{options}</select></div><div><label>検査名・遺伝病名</label><input name="test_name" required></div><div><label>結果</label><select name="result"><option value="clear">クリア</option><option value="carrier">キャリア</option><option value="affected">アフェクテッド</option><option value="unknown">不明</option></select></div><div><label>検査日</label><input type="date" name="tested_on"></div><div><label>検査機関</label><input name="laboratory"></div></div><button>検査結果を登録</button></form><table><tr><th>犬</th><th>検査</th><th>結果</th><th>検査日</th><th>検査機関</th></tr>{rows}</table>'''
    return layout("遺伝子検査", body, user)


@app.post("/modules/genetics")
def genetics_create(dog_id: int = Form(...), test_name: str = Form(...), result: str = Form(...), tested_on: str = Form(""), laboratory: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if result not in {"clear", "carrier", "affected", "unknown"}:
        raise HTTPException(status_code=400)
    session.add(GeneticTest(tenant_id=tenant.id, dog_id=dog.id, test_name=test_name.strip(), result=result, tested_on=date.fromisoformat(tested_on) if tested_on else None, laboratory=laboratory.strip() or None))
    session.commit()
    return RedirectResponse("/modules/genetics", status_code=303)


SALE_STAGES = {
    "inquiry": "問い合わせ", "visit": "見学予定", "consideration": "検討中", "reserved": "予約済み",
    "contracted": "契約済み", "paid": "入金済み", "handed_over": "販売完了", "cancelled": "キャンセル",
}


@app.get("/modules/sales", response_class=HTMLResponse)
def sales_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    customers = session.scalars(select(Customer).where(Customer.tenant_id == tenant.id).order_by(Customer.created_at.desc())).all()
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.category.in_(["puppy", "parent"]), Dog.active.is_(True)).order_by(Dog.call_name)).all()
    cases = session.scalars(select(PuppySale).where(PuppySale.tenant_id == tenant.id).order_by(PuppySale.id.desc())).all()
    customer_options = "".join(f'<option value="{c.id}">{html.escape(c.name)}／{html.escape(c.phone or c.email or "連絡先未登録")}</option>' for c in customers)
    dog_options = "".join(f'<option value="{d.id}">{html.escape(d.call_name)}／{html.escape(d.registered_name or "血統名未登録")}</option>' for d in dogs)
    active_count = sum(case.status not in {"handed_over", "cancelled"} for case in cases)
    contracted_count = sum(case.status in {"contracted", "paid"} for case in cases)
    sales_total = sum(case.price or 0 for case in cases if case.status != "cancelled")
    unpaid_total = sum(max((case.price or 0) - (case.paid_amount or 0), 0) for case in cases if case.status not in {"cancelled", "handed_over"})
    metrics = f'''<div class="grid"><div class="module"><h3>進行中の商談</h3><p><strong style="font-size:28px">{active_count}</strong>件</p></div><div class="module"><h3>契約・入金待ち</h3><p><strong style="font-size:28px">{contracted_count}</strong>件</p></div><div class="module"><h3>販売予定額</h3><p><strong style="font-size:24px">¥{sales_total:,}</strong></p></div><div class="module"><h3>未入金額</h3><p><strong style="font-size:24px">¥{unpaid_total:,}</strong></p></div></div>'''
    case_cards = ""
    for sale in cases:
        dog = session.get(Dog, sale.dog_id)
        customer = session.get(Customer, sale.customer_id) if sale.customer_id else None
        stage_options = "".join(f'<option value="{key}" {"selected" if sale.status == key else ""}>{label}</option>' for key, label in SALE_STAGES.items())
        remaining = max((sale.price or 0) - (sale.paid_amount or 0), 0)
        case_cards += f'''<div class="tenant"><h3>{html.escape(dog.call_name if dog else "犬未登録")} × {html.escape(customer.name if customer else sale.customer_name)}</h3><p><span class="badge">{SALE_STAGES.get(sale.status, sale.status)}</span>　残金 ¥{remaining:,}</p><form method="post" action="/modules/sales/{sale.id}/update"><div class="grid"><div><label>進捗</label><select name="status">{stage_options}</select></div><div><label>次回対応日</label><input type="date" name="next_action_date" value="{sale.next_action_date or ''}"></div><div><label>契約番号</label><input name="contract_no" value="{html.escape(sale.contract_no or '')}"></div><div><label>契約日</label><input type="date" name="contract_date" value="{sale.contract_date or ''}"></div><div><label>販売価格</label><input type="number" min="0" name="price" value="{sale.price or 0}"></div><div><label>予約金</label><input type="number" min="0" name="deposit_amount" value="{sale.deposit_amount or 0}"></div><div><label>入金済額</label><input type="number" min="0" name="paid_amount" value="{sale.paid_amount or 0}"></div><div><label>引渡し日</label><input type="date" name="handover_date" value="{sale.handover_date or ''}"></div></div><label><input style="width:auto" type="checkbox" name="explanation_completed" value="true" {"checked" if sale.explanation_completed else ""}> 対面説明・契約書確認済み</label><label><input style="width:auto" type="checkbox" name="microchip_transfer_completed" value="true" {"checked" if sale.microchip_transfer_completed else ""}> マイクロチップ変更手続き済み</label><label>商談・契約メモ</label><textarea name="notes">{html.escape(sale.notes or '')}</textarea><button>案件を更新</button></form></div>'''
    customer_rows = "".join(f'<tr><td>{html.escape(c.name)}</td><td>{html.escape(c.phone or "-")}</td><td>{html.escape(c.email or "-")}</td><td>{html.escape(c.address or "-")}</td></tr>' for c in customers)
    body = f'''<h1>仔犬販売・顧客管理</h1>{metrics}<h2>新しいお客様を登録</h2><form method="post" action="/modules/sales/customers"><div class="grid"><div><label>氏名</label><input name="name" required></div><div><label>フリガナ</label><input name="name_kana"></div><div><label>電話番号</label><input name="phone"></div><div><label>メール</label><input type="email" name="email"></div><div><label>郵便番号</label><input name="postal_code"></div><div><label>住所</label><input name="address"></div></div><label>顧客メモ</label><textarea name="notes"></textarea><button>お客様を登録</button></form>
    <h2>新しい販売・商談案件</h2>{'<form method="post" action="/modules/sales/cases"><div class="grid"><div><label>対象犬</label><select name="dog_id">'+dog_options+'</select></div><div><label>お客様</label><select name="customer_id">'+customer_options+'</select></div><div><label>問い合わせ日</label><input type="date" name="inquiry_date" value="'+str(date.today())+'"></div><div><label>問い合わせ経路</label><select name="inquiry_channel"><option>Instagram</option><option>ホームページ</option><option>みんなのブリーダー</option><option>紹介</option><option>電話</option><option>その他</option></select></div><div><label>次回対応日</label><input type="date" name="next_action_date"></div><div><label>販売予定価格</label><input type="number" min="0" name="price"></div></div><label>商談メモ</label><textarea name="notes"></textarea><button>商談を開始</button></form>' if customers and dogs else '<p class="error">商談を登録するには、お客様と対象犬を先に登録してください。</p>'}
    <h2>商談・契約・引渡し案件</h2>{case_cards or '<p>販売案件はまだありません。</p>'}<h2>顧客一覧</h2><table><tr><th>氏名</th><th>電話</th><th>メール</th><th>住所</th></tr>{customer_rows}</table>'''
    return layout("仔犬販売・顧客管理", body, user)


@app.post("/modules/sales/customers")
def customer_create(name: str = Form(...), name_kana: str = Form(""), email: str = Form(""), phone: str = Form(""), postal_code: str = Form(""), address: str = Form(""), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    session.add(Customer(tenant_id=tenant.id, name=name.strip(), name_kana=name_kana.strip() or None, email=normalize_email(email) if email else None, phone=phone.strip() or None, postal_code=postal_code.strip() or None, address=address.strip() or None, notes=notes.strip() or None))
    session.commit()
    return RedirectResponse("/modules/sales", status_code=303)


@app.post("/modules/sales/cases")
def sale_create(dog_id: int = Form(...), customer_id: int = Form(...), inquiry_date: str = Form(...), inquiry_channel: str = Form(""), next_action_date: str = Form(""), price: str = Form(""), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    customer = session.scalar(select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant.id))
    if not customer:
        raise HTTPException(status_code=400, detail="お客様が見つかりません")
    next_date = date.fromisoformat(next_action_date) if next_action_date else None
    sale = PuppySale(tenant_id=tenant.id, dog_id=dog.id, customer_id=customer.id, customer_name=customer.name, customer_email=customer.email, inquiry_date=date.fromisoformat(inquiry_date), inquiry_channel=inquiry_channel.strip() or None, next_action_date=next_date, price=int(price) if price else None, notes=notes.strip() or None)
    session.add(sale)
    if next_date:
        session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{customer.name}様へ販売商談フォロー", category="sales", due_date=next_date))
    session.commit()
    return RedirectResponse("/modules/sales", status_code=303)


@app.post("/modules/sales/{sale_id}/update")
def sale_update(sale_id: int, status_value: str = Form(..., alias="status"), next_action_date: str = Form(""), contract_no: str = Form(""), contract_date: str = Form(""), price: int = Form(0), deposit_amount: int = Form(0), paid_amount: int = Form(0), handover_date: str = Form(""), explanation_completed: bool = Form(False), microchip_transfer_completed: bool = Form(False), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    sale = session.scalar(select(PuppySale).where(PuppySale.id == sale_id, PuppySale.tenant_id == tenant.id))
    if not sale or status_value not in SALE_STAGES or min(price, deposit_amount, paid_amount) < 0:
        raise HTTPException(status_code=400, detail="販売案件を確認してください")
    sale.status = status_value
    sale.next_action_date = date.fromisoformat(next_action_date) if next_action_date else None
    sale.contract_no = contract_no.strip() or None
    sale.contract_date = date.fromisoformat(contract_date) if contract_date else None
    sale.price, sale.deposit_amount, sale.paid_amount = price, deposit_amount, paid_amount
    sale.handover_date = date.fromisoformat(handover_date) if handover_date else None
    sale.explanation_completed, sale.microchip_transfer_completed = explanation_completed, microchip_transfer_completed
    sale.notes = notes.strip() or None
    dog = tenant_dog(session, tenant.id, sale.dog_id)
    if status_value in {"reserved", "contracted", "paid"}:
        dog.status = "reserved"
    elif status_value == "handed_over":
        dog.status = "delivered"
    elif status_value == "cancelled" and dog.status == "reserved":
        dog.status = "resident"
    if sale.next_action_date:
        session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{sale.customer_name}様へ販売案件対応", category="sales", due_date=sale.next_action_date))
    session.commit()
    return RedirectResponse("/modules/sales", status_code=303)


@app.get("/modules/{module_key}", response_class=HTMLResponse)
def module_page(module_key: str, access=Depends(require_tenant_user), session: Session = Depends(db)):
    if module_key not in MODULES or module_key in {"dogs", "todo", "calendar", "breeding", "births", "health", "genetics", "sales"}:
        raise HTTPException(status_code=404)
    user, tenant = access
    title, description = MODULES[module_key]
    details = {
        "legal": "定期報告、第一種動物取扱業の開始・更新・変更書類、法定帳簿を作成・保存します。",
        "breeding": "父犬・母犬、交配日、妊娠状況、近親交配率を記録し、将来は血統から組み合わせを提案します。",
        "births": "ヒート開始日、交配予定、出産予定、出生頭数、仔犬の状態を管理します。",
        "health": "体重、診療、投薬、健康診断、ワクチンと次回接種日を管理します。",
        "genetics": "遺伝病ごとのクリア・キャリア・アフェクテッド等の結果と検査機関を管理します。",
        "sales": "問い合わせから契約、法定説明、代金、引渡し、アフターフォローまで管理します。",
    }
    body = f'<h1>{title}</h1><p><span class="badge">{html.escape(tenant.name)}</span></p><p>{description}</p><div class="tenant"><strong>この機能で行うこと</strong><p>{details[module_key]}</p></div><p>専用データベースは作成済みです。入力・帳票画面を順次追加します。</p><a class="button secondary" href="/dashboard">業務ホームへ戻る</a>'
    return layout(title, body, user)


@app.get("/platform/tenants", response_class=HTMLResponse)
def tenant_list(user: User = Depends(require_user), session: Session = Depends(db)):
    if not user.platform_admin:
        raise HTTPException(status_code=403)
    tenants = session.scalars(select(Tenant).order_by(Tenant.name)).all()
    rows = ""
    for tenant in tenants:
        if tenant.deleted:
            state = '<span class="badge">削除済み</span>'
            actions = f'<form class="inline" method="post" action="/platform/tenants/{tenant.id}/action"><input type="hidden" name="action" value="restore"><button class="success">復元</button></form>'
        else:
            state = '<span class="badge">実行中</span>' if tenant.active else '<span class="badge">停止中</span>'
            switch_action = f'<form class="inline" method="post" action="/platform/tenants/{tenant.id}/action"><input type="hidden" name="action" value="select"><button>表示・実行</button></form>' if tenant.active else ""
            toggle = ('stop', '停止', 'secondary') if tenant.active else ('start', '再開', 'success')
            actions = switch_action + f'<form class="inline" method="post" action="/platform/tenants/{tenant.id}/action"><input type="hidden" name="action" value="{toggle[0]}"><button class="{toggle[2]}">{toggle[1]}</button></form><form class="inline" method="post" action="/platform/tenants/{tenant.id}/action" onsubmit="return confirm(\'このテナントを削除扱いにしますか？データは復元できます。\')"><input type="hidden" name="action" value="delete"><button class="danger">削除</button></form>'
        rows += f"<tr><td>{html.escape(tenant.name)}</td><td>{state}</td><td>{actions}</td></tr>"
    return layout("テナント管理", f'<h1>テナント管理</h1><form method="post"><label>新しい会社・犬舎名</label><input name="name" required maxlength="150"><button>作成する</button></form><table><tr><th>会社・犬舎</th><th>状態</th><th>操作</th></tr>{rows}</table>', user)


@app.post("/platform/tenants")
def tenant_create(name: str = Form(...), user: User = Depends(require_user), session: Session = Depends(db)):
    if not user.platform_admin:
        raise HTTPException(status_code=403)
    if session.scalar(select(Tenant).where(Tenant.name == name.strip())):
        return HTMLResponse(layout("エラー", '<p class="error">同じ名前のテナントがあります。</p><a href="/platform/tenants">戻る</a>', user))
    session.add(Tenant(name=name.strip()))
    session.commit()
    return RedirectResponse("/platform/tenants", status_code=303)


@app.post("/platform/tenants/{tenant_id}/action")
def tenant_action(tenant_id: int, action: str = Form(...), user: User = Depends(require_user), session: Session = Depends(db)):
    if not user.platform_admin:
        raise HTTPException(status_code=403)
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="テナントが見つかりません")
    if action == "select" and tenant.active and not tenant.deleted:
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie("tenant_id", str(tenant.id), httponly=True, secure=COOKIE_SECURE, samesite="lax")
        return response
    if action == "stop" and not tenant.deleted:
        tenant.active = False
    elif action == "start" and not tenant.deleted:
        tenant.active = True
    elif action == "delete":
        tenant.active = False
        tenant.deleted = True
    elif action == "restore":
        tenant.deleted = False
        tenant.active = True
    else:
        raise HTTPException(status_code=400, detail="無効な操作です")
    session.commit()
    return RedirectResponse("/platform/tenants", status_code=303)


@app.get("/family", response_class=HTMLResponse)
def family_home(user: User = Depends(require_user), session: Session = Depends(db)):
    records = session.execute(
        select(DogOwnership, Dog, Tenant)
        .join(Dog, Dog.id == DogOwnership.dog_id)
        .join(Tenant, Tenant.id == DogOwnership.tenant_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True))
        .order_by(Tenant.name, Dog.call_name)
    ).all()
    cards = ""
    for ownership, dog, tenant in records:
        sex = {"male": "牡", "female": "牝"}.get(dog.sex, dog.sex)
        relation = "主オーナー" if ownership.relationship == "primary" else "ご家族"
        family_profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog.id))
        photo = f'<img class="family-dog-thumb" src="/family/dogs/{dog.id}/photo" alt="{html.escape(dog.call_name)}">' if family_profile and family_profile.photo_data else ''
        cards += f'''<a class="module" href="/family/dogs/{dog.id}">
          {photo}
          <h3>{html.escape(dog.call_name)}</h3>
          <p>{html.escape(dog.registered_name or "血統書名未登録")}</p>
          <p>{html.escape(dog.breed or "犬種未登録")} ／ {html.escape(sex)} ／ {html.escape(dog.color or "毛色未登録")}</p>
          <p>{html.escape(tenant.name)}　<span class="badge">{relation}</span></p>
        </a>'''
    if not cards:
        cards = '<div class="tenant"><p>まだ犬が連携されていません。</p><p>犬舎へ、登録したメールアドレスをお知らせください。</p></div>'
    body = f'''<h1>FAMILY ホーム</h1>
    <p>犬舎からあなたに連携された「うちの子」だけを表示しています。</p>
    <p><a class="button" href="/family/notifications">通知</a> <a class="button" href="/family/messages">メッセージ</a> <a class="button" href="/family/announcements">犬舎からのお知らせ</a> <a class="button" href="/family/timeline">FAMILYタイムライン</a> <a class="button" href="/family/anniversaries">誕生日・お迎え記念日</a> <a class="button" href="/family/relatives">兄弟・親戚犬を見る</a> <a class="button" href="/family/kennel">同じ犬舎のFAMILY会</a> <a class="button secondary" href="/family/profile">公開プロフィール設定</a></p>
    <div class="grid">{cards}</div>'''
    return family_layout("FAMILY", body, user, session)


@app.get("/family/notifications", response_class=HTMLResponse)
def family_notifications(user: User = Depends(require_user), session: Session = Depends(db)):
    items: list[tuple[datetime, str]] = []
    for conversation, message in family_unread_message_items(user, session):
        other_id = conversation.user2_id if conversation.user1_id == user.id else conversation.user1_id
        preview = message.body[:80] + ("…" if len(message.body) > 80 else "")
        card = f'''<a class="notification-item unread" href="/family/messages/{conversation.id}">
        <span class="notification-kind">新着メッセージ</span><span class="badge">未読</span>
        <p><strong>{html.escape(family_message_name(other_id, session))}さんから届きました</strong></p>
        <p>{html.escape(preview)}</p><small>{message.sent_at.strftime('%Y年%m月%d日 %H:%M')}</small></a>'''
        items.append((message.sent_at, card))
    for announcement, tenant in family_unread_announcements(user, session):
        event = f" ／ 開催日 {announcement.event_date.strftime('%Y年%m月%d日')}" if announcement.event_date else ""
        card = f'''<a class="notification-item unread" href="/family/announcements/view/{announcement.id}">
        <span class="notification-kind">犬舎からのお知らせ</span><span class="badge">未読</span>
        <p><strong>{html.escape(announcement.title)}</strong></p><p>{html.escape(tenant.name)}{event}</p>
        <small>{announcement.created_at.strftime('%Y年%m月%d日 %H:%M')}</small></a>'''
        items.append((announcement.created_at, card))
    cards = "".join(card for _, card in sorted(items, key=lambda item: item[0], reverse=True))
    if not cards:
        cards = '<div class="tenant"><p>新しい通知はありません。</p><p><small>新着メッセージと犬舎からのお知らせを、ここでまとめて確認できます。</small></p></div>'
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>通知</h1>
    <p>未読のメッセージと、まだ確認していない犬舎からのお知らせです。</p>{cards}
    <p><a class="button secondary" href="/family/anniversaries">誕生日・お迎え記念日を確認</a></p>'''
    return family_layout("通知｜FAMILY", body, user, session)


def next_family_anniversary(month: int, day: int, today: date) -> date:
    """今年または来年の記念日を返す。2月29日は平年には2月28日として祝う。"""
    def occurrence(year: int) -> date:
        try:
            return date(year, month, day)
        except ValueError:
            return date(year, 2, 28)

    candidate = occurrence(today.year)
    return candidate if candidate >= today else occurrence(today.year + 1)


@app.get("/family/anniversaries", response_class=HTMLResponse)
def family_anniversaries(user: User = Depends(require_user), session: Session = Depends(db)):
    records = session.execute(
        select(DogOwnership, Dog, Tenant).join(Dog, Dog.id == DogOwnership.dog_id)
        .join(Tenant, Tenant.id == DogOwnership.tenant_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True), Dog.active.is_(True),
               Tenant.active.is_(True), Tenant.deleted.is_(False))
        .order_by(Dog.call_name)
    ).all()
    today = date.today()
    events: list[tuple[int, str]] = []
    missing_handover: list[str] = []
    for ownership, dog, tenant in records:
        profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog.id))
        photo = f'<img class="family-dog-thumb" src="/family/dogs/{dog.id}/photo" alt="{html.escape(dog.call_name)}">' if profile and profile.photo_data else ""
        if dog.birth_date:
            upcoming = next_family_anniversary(dog.birth_date.month, dog.birth_date.day, today)
            days = (upcoming - today).days
            turning = upcoming.year - dog.birth_date.year
            timing = "今日です！" if days == 0 else f"あと{days}日"
            events.append((days, f'''<a class="module" href="/family/dogs/{dog.id}">{photo}<h3>🎂 {html.escape(dog.call_name)}の誕生日</h3>
            <p>{upcoming.strftime('%Y年%m月%d日')}（{timing}）</p><p><strong>{turning}歳</strong>になります</p><p>{html.escape(tenant.name)}</p></a>'''))

        handover = session.scalar(
            select(PuppySale.handover_date).where(PuppySale.tenant_id == dog.tenant_id, PuppySale.dog_id == dog.id,
                                                   PuppySale.handover_date.is_not(None))
            .order_by(PuppySale.handover_date.desc()).limit(1)
        )
        if not handover:
            handover = session.scalar(
                select(DogTransfer.transferred_on).where(DogTransfer.tenant_id == dog.tenant_id, DogTransfer.dog_id == dog.id)
                .order_by(DogTransfer.transferred_on.desc()).limit(1)
            )
        if handover:
            upcoming = next_family_anniversary(handover.month, handover.day, today)
            days = (upcoming - today).days
            years = upcoming.year - handover.year
            timing = "今日です！" if days == 0 else f"あと{days}日"
            events.append((days, f'''<a class="module" href="/family/dogs/{dog.id}">{photo}<h3>🏠 {html.escape(dog.call_name)}のお迎え記念日</h3>
            <p>{upcoming.strftime('%Y年%m月%d日')}（{timing}）</p><p><strong>{years}周年</strong>です</p><p>お迎え日：{handover.strftime('%Y年%m月%d日')}</p></a>'''))
        else:
            missing_handover.append(html.escape(dog.call_name))

    cards = "".join(card for _, card in sorted(events, key=lambda event: event[0]))
    if not cards:
        cards = '<div class="tenant"><p>表示できる記念日がまだありません。</p><p>犬の生年月日や、販売・譲渡管理の引渡し日を登録すると自動表示されます。</p></div>'
    notice = f'''<div class="tenant"><strong>お迎え日の登録待ち</strong><p>{"、".join(missing_handover)}</p>
    <p><small>犬舎側の販売管理または譲渡先管理で引渡し日を登録すると、お迎え記念日が表示されます。</small></p></div>''' if missing_handover else ""
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>誕生日・お迎え記念日</h1>
    <p>うちの子の大切な記念日を、近い順に表示しています。</p><div class="grid">{cards}</div>{notice}'''
    return family_layout("誕生日・お迎え記念日｜FAMILY", body, user, session)


@app.get("/family/announcements", response_class=HTMLResponse)
def family_announcements(user: User = Depends(require_user), session: Session = Depends(db)):
    tenant_ids = family_kennel_tenant_ids(user, session)
    records = session.execute(
        select(FamilyAnnouncement, Tenant).join(Tenant, Tenant.id == FamilyAnnouncement.tenant_id)
        .where(FamilyAnnouncement.tenant_id.in_(tenant_ids), FamilyAnnouncement.active.is_(True),
               Tenant.active.is_(True), Tenant.deleted.is_(False))
        .order_by(FamilyAnnouncement.created_at.desc()).limit(100)
    ).all() if tenant_ids else []
    cards = ""
    for announcement, tenant in records:
        event = f'<p><span class="badge">開催日：{announcement.event_date.strftime("%Y年%m月%d日")}</span></p>' if announcement.event_date else ""
        cards += f'''<article class="tenant"><p><strong>{html.escape(tenant.name)}</strong>　<small>{announcement.created_at.date().strftime("%Y年%m月%d日")}掲載</small></p>
        <h2 style="margin-top:8px">{html.escape(announcement.title)}</h2>{event}
        <div style="white-space:pre-wrap">{html.escape(announcement.body)}</div><p><a class="button secondary" href="/family/announcements/view/{announcement.id}">詳しく見る</a></p></article>'''
    if not cards:
        cards = '<div class="tenant"><p>現在、犬舎からのお知らせはありません。</p></div>'
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>犬舎からのお知らせ</h1>
    <p>愛犬を迎えた犬舎からの、FAMILY会・イベント・大切なご案内を表示しています。</p>{cards}'''
    return family_layout("犬舎からのお知らせ｜FAMILY", body, user, session)


@app.get("/family/announcements/view/{announcement_id}", response_class=HTMLResponse)
def family_announcement_detail(announcement_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    tenant_ids = family_kennel_tenant_ids(user, session)
    record = session.execute(
        select(FamilyAnnouncement, Tenant).join(Tenant, Tenant.id == FamilyAnnouncement.tenant_id)
        .where(FamilyAnnouncement.id == announcement_id, FamilyAnnouncement.tenant_id.in_(tenant_ids),
               FamilyAnnouncement.active.is_(True), Tenant.active.is_(True), Tenant.deleted.is_(False))
    ).first() if tenant_ids else None
    if not record:
        raise HTTPException(status_code=404, detail="お知らせが見つかりません")
    announcement, tenant = record
    read = session.scalar(select(FamilyAnnouncementRead).where(
        FamilyAnnouncementRead.announcement_id == announcement.id,
        FamilyAnnouncementRead.user_id == user.id,
    ))
    if read:
        read.read_at = datetime.now(timezone.utc)
    else:
        session.add(FamilyAnnouncementRead(announcement_id=announcement.id, user_id=user.id))
    session.commit()
    event = f'<p><span class="badge">開催日：{announcement.event_date.strftime("%Y年%m月%d日")}</span></p>' if announcement.event_date else ""
    body = f'''<a class="button secondary" href="/family/announcements">お知らせ一覧へ戻る</a>
    <h1>{html.escape(announcement.title)}</h1><p><strong>{html.escape(tenant.name)}</strong>　<small>{announcement.created_at.date().strftime('%Y年%m月%d日')}掲載</small></p>
    {event}<div class="tenant" style="white-space:pre-wrap">{html.escape(announcement.body)}</div>'''
    return family_layout(f"{announcement.title}｜FAMILY", body, user, session)


@app.get("/family/announcements/manage", response_class=HTMLResponse)
def family_announcements_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    announcements = session.scalars(
        select(FamilyAnnouncement).where(FamilyAnnouncement.tenant_id == tenant.id)
        .order_by(FamilyAnnouncement.created_at.desc()).limit(100)
    ).all()
    rows = ""
    for announcement in announcements:
        state = "公開中" if announcement.active else "掲載停止"
        action = "stop" if announcement.active else "start"
        action_label = "掲載を停止" if announcement.active else "再公開"
        event = announcement.event_date.strftime("%Y-%m-%d") if announcement.event_date else "－"
        rows += f'''<tr><td>{html.escape(announcement.title)}</td><td>{event}</td><td>{state}</td><td>{announcement.created_at.date()}</td>
        <td><form class="inline" method="post" action="/family/announcements/manage/{announcement.id}/action"><input type="hidden" name="action" value="{action}"><button class="secondary">{action_label}</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/dashboard">ダッシュボードへ戻る</a><h1>{html.escape(tenant.name)} FAMILYお知らせ管理</h1>
    <p>この犬舎から愛犬を迎えたオーナー様だけに表示されます。</p>
    <form method="post"><label>タイトル（150文字まで）</label><input name="title" maxlength="150" required placeholder="例：ESTRELLA FAMILY会開催のお知らせ">
    <label>開催日（イベントの場合）</label><input type="date" name="event_date">
    <label>お知らせ内容（2,000文字まで）</label><textarea name="body" maxlength="2000" required placeholder="日時、会場、持ち物、参加方法などをご案内ください。"></textarea>
    <button>お知らせを公開する</button></form><h2>掲載履歴</h2>
    <table><tr><th>タイトル</th><th>開催日</th><th>状態</th><th>掲載日</th><th>操作</th></tr>{rows or '<tr><td colspan="5">お知らせはまだありません。</td></tr>'}</table>'''
    return layout("FAMILYお知らせ管理", body, user)


@app.post("/family/announcements/manage")
def family_announcement_create(title: str = Form(...), body: str = Form(...), event_date: str = Form(""), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    title, body = title.strip(), body.strip()
    if not title or len(title) > 150 or not body or len(body) > 2000:
        raise HTTPException(status_code=400, detail="タイトルとお知らせ内容の文字数を確認してください")
    try:
        parsed_event_date = date.fromisoformat(event_date) if event_date else None
    except ValueError:
        raise HTTPException(status_code=400, detail="開催日を確認してください")
    session.add(FamilyAnnouncement(tenant_id=tenant.id, title=title, body=body, event_date=parsed_event_date, created_by_id=user.id))
    session.commit()
    return RedirectResponse("/family/announcements/manage", status_code=303)


@app.post("/family/announcements/manage/{announcement_id}/action")
def family_announcement_action(announcement_id: int, action: str = Form(...), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    announcement = session.scalar(select(FamilyAnnouncement).where(FamilyAnnouncement.id == announcement_id, FamilyAnnouncement.tenant_id == tenant.id))
    if not announcement:
        raise HTTPException(status_code=404, detail="お知らせが見つかりません")
    if action == "stop":
        announcement.active = False
    elif action == "start":
        announcement.active = True
    else:
        raise HTTPException(status_code=400, detail="操作を確認してください")
    session.commit()
    return RedirectResponse("/family/announcements/manage", status_code=303)


@app.get("/family/dogs/{dog_id}", response_class=HTMLResponse)
def family_dog_detail(dog_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    record = session.execute(
        select(DogOwnership, Dog, Tenant)
        .join(Dog, Dog.id == DogOwnership.dog_id)
        .join(Tenant, Tenant.id == DogOwnership.tenant_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.dog_id == dog_id, DogOwnership.active.is_(True))
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="閲覧できる犬が見つかりません")
    ownership, dog, tenant = record
    sex = {"male": "牡", "female": "牝"}.get(dog.sex, dog.sex)
    birth = dog.birth_date.strftime("%Y年%m月%d日") if dog.birth_date else "未登録"
    status_label = {"resident": "在舎中", "reserved": "予約済", "sold": "販売済", "transferred": "譲渡済"}.get(dog.status, dog.status)
    relation = "主オーナー" if ownership.relationship == "primary" else "ご家族"
    profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog.id))
    sire = session.get(Dog, dog.sire_id) if dog.sire_id else None
    dam = session.get(Dog, dog.dam_id) if dog.dam_id else None
    age = "未登録"
    if dog.birth_date:
        today = date.today()
        months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
        age = f"{months // 12}歳{months % 12}か月" if months >= 12 else f"{max(months, 0)}か月"
    photo = f'<div class="family-photo-stage"><img class="family-dog-photo" src="/family/dogs/{dog.id}/photo" alt="{html.escape(dog.call_name)}"></div>' if profile and profile.photo_data else '<div class="tenant" style="text-align:center;padding:55px">愛犬の写真はまだ登録されていません。</div>'
    introduction = f'<div class="tenant"><strong>オーナー様からの紹介</strong><p style="white-space:pre-wrap">{html.escape(profile.introduction)}</p></div>' if profile and profile.introduction else ''
    album_items = session.scalars(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.dog_id == dog.id).order_by(FamilyDogAlbumItem.taken_on.desc(), FamilyDogAlbumItem.created_at.desc())).all()
    album_cards = ""
    visibility_labels = {"private": "非公開", "relatives": "親戚犬まで", "family": "FAMILY全体"}
    for item in album_items:
        if item.visibility == "private" and item.uploaded_by_id != user.id:
            continue
        taken = item.taken_on.strftime("%Y年%m月%d日") if item.taken_on else "撮影日未設定"
        delete_button = f'<form method="post" action="/family/dogs/{dog.id}/album/{item.id}/delete"><button class="danger">削除</button></form>' if item.uploaded_by_id == user.id else ''
        album_cards += f'''<article class="album-item"><a href="/family/dogs/{dog.id}/album/{item.id}/photo" target="_blank"><img src="/family/dogs/{dog.id}/album/{item.id}/photo" alt="{html.escape(item.caption or dog.call_name)}"></a>
        <div class="album-meta"><p><strong>{taken}</strong> <span class="badge">{visibility_labels.get(item.visibility, "非公開")}</span></p><p>{html.escape(item.caption or "コメントなし")}</p>{delete_button}</div></article>'''
    album_section = f'''<h2>成長アルバム</h2><p>写真を押すと大きく表示できます。</p><div class="album-grid">{album_cards or '<p>成長アルバムの写真はまだありません。</p>'}</div>
    <div class="tenant"><h3>成長記録を追加</h3><form method="post" action="/family/dogs/{dog.id}/album" enctype="multipart/form-data">
    <label>写真（JPG・PNG・WebP／8MBまで）</label><input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required>
    <label>撮影日</label><input type="date" name="taken_on">
    <label>コメント（300文字まで）</label><textarea name="caption" maxlength="300" placeholder="初めてのお散歩、1歳のお誕生日など"></textarea>
    <label>公開範囲</label><select name="visibility"><option value="private">非公開（自分だけ）</option><option value="relatives">親戚犬のオーナーまで</option><option value="family">FAMILY全体</option></select>
    <button>アルバムへ追加</button></form></div>'''
    edit_form = f'''<h2>愛犬プロフィール写真・紹介文</h2><form method="post" action="/family/dogs/{dog.id}/profile" enctype="multipart/form-data">
    <label>メイン写真（JPG・PNG・WebP／8MBまで）</label><input type="file" name="photo" accept="image/jpeg,image/png,image/webp">
    <label>愛犬の紹介（300文字まで）</label><textarea name="introduction" maxlength="300" placeholder="性格や好きなことなどをご紹介ください。">{html.escape(profile.introduction if profile and profile.introduction else '')}</textarea>
    <button>愛犬プロフィールを保存</button></form>
    {f'<form method="post" action="/family/dogs/{dog.id}/photo/delete"><button class="danger">写真を削除</button></form>' if profile and profile.photo_data else ''}''' if ownership.relationship == "primary" else '<p><small>写真と紹介文は主オーナーが変更できます。</small></p>'
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a>
    <h1>{html.escape(dog.call_name)}</h1><p><span class="badge">{relation}</span> {title_marks(dog.titles)}</p>
    {photo}{introduction}
    <div class="tenant"><strong>{html.escape(tenant.name)}</strong>から共有されています。</div>
    <table><tr><th>血統書名</th><td>{html.escape(dog.registered_name or "未登録")}</td></tr>
    <tr><th>犬種</th><td>{html.escape(dog.breed or "未登録")}</td></tr>
    <tr><th>性別</th><td>{html.escape(sex)}</td></tr><tr><th>生年月日・年齢</th><td>{birth}（{age}）</td></tr>
    <tr><th>毛色</th><td>{html.escape(dog.color or "未登録")}</td></tr><tr><th>現在の状態</th><td>{html.escape(status_label)}</td></tr>
    <tr><th>父犬</th><td>{html.escape((sire.registered_name or sire.call_name) if sire else "未登録")} {title_marks(sire.titles) if sire else ''}</td></tr>
    <tr><th>母犬</th><td>{html.escape((dam.registered_name or dam.call_name) if dam else "未登録")} {title_marks(dam.titles) if dam else ''}</td></tr></table>
    {album_section}{edit_form}<p>この画面では犬舎の顧客情報、金額、マイクロチップ番号などの非公開情報は表示しません。</p>'''
    return family_layout(f"{dog.call_name}｜FAMILY", body, user, session)


def family_owned_dog(dog_id: int, user: User, session: Session):
    return session.execute(
        select(DogOwnership, Dog).join(Dog, Dog.id == DogOwnership.dog_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.dog_id == dog_id, DogOwnership.active.is_(True))
    ).first()


@app.get("/family/dogs/{dog_id}/photo")
def family_dog_photo(dog_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=404)
    profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog_id))
    if not profile or not profile.photo_data:
        raise HTTPException(status_code=404)
    return Response(content=profile.photo_data, media_type=profile.photo_content_type or "image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@app.post("/family/dogs/{dog_id}/profile")
async def family_dog_profile_save(dog_id: int, introduction: str = Form(""), photo: UploadFile | None = File(None), user: User = Depends(require_user), session: Session = Depends(db)):
    record = family_owned_dog(dog_id, user, session)
    if not record or record[0].relationship != "primary":
        raise HTTPException(status_code=403, detail="主オーナーだけが愛犬プロフィールを変更できます")
    introduction = introduction.strip()
    if len(introduction) > 300:
        raise HTTPException(status_code=400, detail="紹介文は300文字以内で入力してください")
    profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog_id))
    if not profile:
        profile = FamilyDogProfile(dog_id=dog_id, updated_by_id=user.id)
        session.add(profile)
    if photo and photo.filename:
        content = await photo.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="写真は8MB以下にしてください")
        try:
            with Image.open(io.BytesIO(content)) as source:
                if source.width * source.height > 25_000_000:
                    raise ValueError("image dimensions are too large")
                image = ImageOps.exif_transpose(source)
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                if image.mode in {"RGBA", "LA"}:
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=88, optimize=True)
        except Exception:
            raise HTTPException(status_code=400, detail="JPG・PNG・WebP形式の写真を選択してください")
        profile.photo_data, profile.photo_content_type = output.getvalue(), "image/jpeg"
    profile.introduction, profile.updated_by_id, profile.updated_at = introduction or None, user.id, datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f"/family/dogs/{dog_id}", status_code=303)


@app.post("/family/dogs/{dog_id}/photo/delete")
def family_dog_photo_delete(dog_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    record = family_owned_dog(dog_id, user, session)
    if not record or record[0].relationship != "primary":
        raise HTTPException(status_code=403)
    profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog_id))
    if profile:
        profile.photo_data, profile.photo_content_type = None, None
        profile.updated_by_id, profile.updated_at = user.id, datetime.now(timezone.utc)
        session.commit()
    return RedirectResponse(f"/family/dogs/{dog_id}", status_code=303)


@app.post("/family/dogs/{dog_id}/album")
async def family_dog_album_add(dog_id: int, photo: UploadFile = File(...), taken_on: str = Form(""), caption: str = Form(""), visibility: str = Form("private"), user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=403, detail="この犬のアルバムへ追加できません")
    caption = caption.strip()
    if len(caption) > 300 or visibility not in {"private", "relatives", "family"}:
        raise HTTPException(status_code=400, detail="コメントまたは公開範囲を確認してください")
    try:
        taken_date = date.fromisoformat(taken_on) if taken_on else None
    except ValueError:
        raise HTTPException(status_code=400, detail="撮影日を確認してください")
    content = await photo.read(8 * 1024 * 1024 + 1)
    if not content or len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="8MB以下の写真を選択してください")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.width * source.height > 25_000_000:
                raise ValueError("image dimensions are too large")
            image = ImageOps.exif_transpose(source)
            image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
    except Exception:
        raise HTTPException(status_code=400, detail="JPG・PNG・WebP形式の写真を選択してください")
    session.add(FamilyDogAlbumItem(dog_id=dog_id, uploaded_by_id=user.id, photo_data=output.getvalue(), photo_content_type="image/jpeg", taken_on=taken_date, caption=caption or None, visibility=visibility))
    session.commit()
    return RedirectResponse(f"/family/dogs/{dog_id}", status_code=303)


@app.get("/family/dogs/{dog_id}/album/{item_id}/photo")
def family_dog_album_photo(dog_id: int, item_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=404)
    item = session.scalar(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.id == item_id, FamilyDogAlbumItem.dog_id == dog_id))
    if not item or (item.visibility == "private" and item.uploaded_by_id != user.id):
        raise HTTPException(status_code=404)
    return Response(content=item.photo_data, media_type=item.photo_content_type, headers={"Cache-Control": "private, max-age=300"})


@app.post("/family/dogs/{dog_id}/album/{item_id}/delete")
def family_dog_album_delete(dog_id: int, item_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=404)
    item = session.scalar(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.id == item_id, FamilyDogAlbumItem.dog_id == dog_id, FamilyDogAlbumItem.uploaded_by_id == user.id))
    if not item:
        raise HTTPException(status_code=404)
    session.delete(item)
    session.commit()
    return RedirectResponse(f"/family/dogs/{dog_id}", status_code=303)


def owner_profile_for(user: User, session: Session) -> OwnerProfile:
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    if not profile:
        profile = OwnerProfile(user_id=user.id, public_id=secrets.token_urlsafe(12))
        session.add(profile)
        session.commit()
    return profile


@app.get("/family/profile", response_class=HTMLResponse)
def family_profile_edit(user: User = Depends(require_user), session: Session = Depends(db)):
    profile = owner_profile_for(user, session)
    prefecture_options = '<option value="">未設定</option>' + "".join(
        f'<option value="{value}" {"selected" if profile.prefecture == value else ""}>{value}</option>' for value in PREFECTURES
    )
    checked = lambda value: "checked" if value else ""
    photo = f'<img src="/family/profile/photo" alt="プロフィール写真" style="width:150px;height:150px;object-fit:cover;border-radius:50%;border:4px solid #ead0d5">' if profile.photo_data else '<p>プロフィール写真は未登録です。</p>'
    public_url = f'/family/members/{profile.public_id}'
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>プロフィール設定</h1>
    <h2>アカウント設定</h2>
    <p>ログアウトボタンの横など、ご本人の画面に表示される名前です。公開プロフィールのニックネームとは別に管理されます。</p>
    <form method="post" enctype="multipart/form-data">
    <label>アカウント名（100文字まで）</label><input name="account_name" value="{html.escape(user.name)}" maxlength="100" required placeholder="例：内山 良一">
    <h2>公開プロフィール設定</h2>
    <p>プロフィール全体と、各項目の公開範囲をご自身で設定できます。非公開項目は他のメンバーに表示されません。</p>
    <div class="tenant">{photo}<p><a href="{public_url}">公開状態を確認する</a></p></div>
    <label>ニックネーム</label><input name="nickname" value="{html.escape(profile.nickname or '')}" maxlength="60" placeholder="例：りょう">
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_nickname" value="true" {checked(profile.show_nickname)}> ニックネームを公開する</label>
    <label>都道府県</label><select name="prefecture">{prefecture_options}</select>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_prefecture" value="true" {checked(profile.show_prefecture)}> 都道府県を公開する</label>
    <label>自己紹介（500文字まで）</label><textarea name="bio" maxlength="500" placeholder="愛犬との暮らしや、ご自身についてご紹介ください。">{html.escape(profile.bio or '')}</textarea>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_bio" value="true" {checked(profile.show_bio)}> 自己紹介を公開する</label>
    <label>Instagram（ユーザーネームまたはプロフィールURL）</label><input name="instagram" value="{html.escape(profile.instagram_username or '')}" maxlength="100" placeholder="例：@estrella_dog または https://www.instagram.com/estrella_dog/">
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_instagram" value="true" {checked(profile.show_instagram)}> Instagramを公開する</label>
    <p><small>公開すると、プロフィールからInstagramを別画面で開けます。パスワードは入力しないでください。</small></p>
    <label>プロフィール写真（JPG・PNG・WebP／8MBまで）</label><input name="photo" type="file" accept="image/jpeg,image/png,image/webp">
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_photo" value="true" {checked(profile.show_photo)}> プロフィール写真を公開する</label>
    <h2>愛犬・血統の公開設定</h2>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_dogs" value="true" {checked(profile.show_dogs)}> 連携されている愛犬を公開する</label>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_parents" value="true" {checked(profile.show_parents)}> 愛犬の父犬・母犬も公開する</label>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="show_relatives" value="true" {checked(profile.show_relatives)}> 同腹兄弟・親戚犬を自動表示する</label>
    <p><small>父母を公開しても、血統書番号・マイクロチップ番号・所有者情報は表示されません。</small></p>
    <div class="tenant"><label style="font-size:16px"><input style="width:auto" type="checkbox" name="profile_public" value="true" {checked(profile.profile_public)}> プロフィール全体を犬舎FAMILY会へ公開する</label>
    <p><small>ここをオフにすると、各項目がオンでもプロフィール全体が非公開になります。</small></p></div>
    <button>設定を保存</button></form>
    {f'<form method="post" action="/family/profile/photo/delete"><button class="danger">登録写真を削除</button></form>' if profile.photo_data else ''}'''
    return family_layout("公開プロフィール設定", body, user, session)


@app.post("/family/profile")
async def family_profile_save(
    account_name: str = Form(""), nickname: str = Form(""), prefecture: str = Form(""), bio: str = Form(""), instagram: str = Form(""), photo: UploadFile | None = File(None),
    profile_public: bool = Form(False), show_nickname: bool = Form(False), show_prefecture: bool = Form(False),
    show_bio: bool = Form(False), show_photo: bool = Form(False), show_dogs: bool = Form(False), show_parents: bool = Form(False),
    show_relatives: bool = Form(False), show_instagram: bool = Form(False),
    user: User = Depends(require_user), session: Session = Depends(db),
):
    normalized_account_name = " ".join(account_name.split())
    if not normalized_account_name or len(normalized_account_name) > 100:
        return HTMLResponse(family_layout("名前の入力エラー", '<p class="error">アカウント名は1文字以上100文字以内で入力してください。</p><a class="button secondary" href="/family/profile">戻る</a>', user, session), status_code=400)
    if prefecture and prefecture not in PREFECTURES:
        raise HTTPException(status_code=400, detail="都道府県を確認してください")
    if len(nickname.strip()) > 60 or len(bio.strip()) > 500:
        raise HTTPException(status_code=400, detail="プロフィールの文字数を確認してください")
    instagram_value = instagram.strip().rstrip("/")
    instagram_match = re.fullmatch(r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})", instagram_value, re.IGNORECASE)
    instagram_username = instagram_match.group(1) if instagram_match else instagram_value.removeprefix("@")
    if instagram_username and not re.fullmatch(r"[A-Za-z0-9._]{1,30}", instagram_username):
        return HTMLResponse(family_layout("Instagram入力エラー", '<p class="error">Instagramのユーザーネーム、または instagram.com のプロフィールURLを入力してください。</p><a class="button secondary" href="/family/profile">戻る</a>', user, session), status_code=400)
    profile = owner_profile_for(user, session)
    if photo and photo.filename:
        content = await photo.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            return HTMLResponse(family_layout("写真エラー", '<p class="error">写真は8MB以下にしてください。</p><a class="button secondary" href="/family/profile">戻る</a>', user, session), status_code=400)
        try:
            with Image.open(io.BytesIO(content)) as source:
                if source.width * source.height > 25_000_000:
                    raise ValueError("image dimensions are too large")
                image = ImageOps.exif_transpose(source)
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                if image.mode in {"RGBA", "LA"}:
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=86, optimize=True)
        except Exception:
            return HTMLResponse(family_layout("写真エラー", '<p class="error">JPG・PNG・WebP形式の写真を選択してください。</p><a class="button secondary" href="/family/profile">戻る</a>', user, session), status_code=400)
        profile.photo_data = output.getvalue()
        profile.photo_content_type = "image/jpeg"
    eligible = user.platform_admin or session.scalar(select(Membership.id).where(Membership.user_id == user.id).limit(1)) is not None \
        or session.scalar(select(DogOwnership.id).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True)).limit(1)) is not None
    if profile_public and not eligible:
        return HTMLResponse(family_layout("公開設定エラー", '<p class="error">プロフィールを公開できるのは、犬舎に所属している方または犬と連携済みのオーナー様です。</p><a class="button secondary" href="/family/profile">戻る</a>', user, session), status_code=403)
    user.name = normalized_account_name
    profile.nickname = nickname.strip() or None
    profile.prefecture = prefecture or None
    profile.bio = bio.strip() or None
    profile.instagram_username = instagram_username or None
    profile.profile_public, profile.show_nickname = profile_public, show_nickname
    profile.show_prefecture, profile.show_bio, profile.show_photo = show_prefecture, show_bio, show_photo
    profile.show_dogs, profile.show_parents = show_dogs, show_parents and show_dogs
    profile.show_relatives = show_relatives and show_dogs
    profile.show_instagram = show_instagram and bool(instagram_username)
    profile.updated_at = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse("/family/profile", status_code=303)


@app.get("/family/profile/photo")
def family_profile_own_photo(user: User = Depends(require_user), session: Session = Depends(db)):
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    if not profile or not profile.photo_data:
        raise HTTPException(status_code=404)
    return Response(content=profile.photo_data, media_type=profile.photo_content_type or "image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@app.post("/family/profile/photo/delete")
def family_profile_photo_delete(user: User = Depends(require_user), session: Session = Depends(db)):
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    if profile:
        profile.photo_data, profile.photo_content_type, profile.show_photo = None, None, False
        profile.updated_at = datetime.now(timezone.utc)
        session.commit()
    return RedirectResponse("/family/profile", status_code=303)


@app.get("/family/members", response_class=HTMLResponse)
def family_member_list(user: User = Depends(require_user), session: Session = Depends(db)):
    return RedirectResponse("/family/kennel", status_code=303)


def family_ancestor_depths(session: Session, dog: Dog, max_depth: int = 3) -> dict[int, int]:
    """同一テナント内の祖先IDと近さを返す。循環・誤登録でも無限再帰しない。"""
    depths: dict[int, int] = {}
    frontier = [(dog.sire_id, 1), (dog.dam_id, 1)]
    while frontier:
        dog_id, depth = frontier.pop(0)
        if not dog_id or depth > max_depth or (dog_id in depths and depths[dog_id] <= depth):
            continue
        ancestor = session.get(Dog, dog_id)
        if not ancestor or ancestor.tenant_id != dog.tenant_id:
            continue
        depths[dog_id] = depth
        frontier.extend([(ancestor.sire_id, depth + 1), (ancestor.dam_id, depth + 1)])
    return depths


def family_relationship(session: Session, source: Dog, candidate: Dog) -> tuple[str, str] | None:
    """公開用の関係分類。同腹を最優先し、次に直系・片親・共通祖先を判定する。"""
    if source.id == candidate.id or source.tenant_id != candidate.tenant_id:
        return None
    same_sire = bool(source.sire_id and source.sire_id == candidate.sire_id)
    same_dam = bool(source.dam_id and source.dam_id == candidate.dam_id)
    if same_sire and same_dam:
        if source.birth_date and source.birth_date == candidate.birth_date:
            return "litter", "同腹兄弟"
        return "relative", "父母が同じきょうだい（別の出産）"
    source_ancestors = family_ancestor_depths(session, source)
    candidate_ancestors = family_ancestor_depths(session, candidate)
    if source.id in candidate_ancestors or candidate.id in source_ancestors:
        return "relative", "親子・直系の親戚犬"
    if same_sire:
        return "relative", "父犬が同じきょうだい"
    if same_dam:
        return "relative", "母犬が同じきょうだい"
    common = set(source_ancestors) & set(candidate_ancestors)
    if common:
        nearest = min(common, key=lambda dog_id: source_ancestors[dog_id] + candidate_ancestors[dog_id])
        ancestor = session.get(Dog, nearest)
        ancestor_name = ancestor.registered_name or ancestor.call_name if ancestor else "共通祖先"
        return "relative", f"{ancestor_name}を共通祖先に持つ親戚犬"
    return None


def family_relative_matches(user: User, session: Session) -> dict[int, tuple[int, str, str, Dog, OwnerProfile]]:
    """閲覧者の愛犬と、公開に同意した他オーナーの親戚犬を照合する。"""
    source_dogs = session.scalars(
        select(Dog).join(DogOwnership, DogOwnership.dog_id == Dog.id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True), Dog.active.is_(True))
    ).all()
    candidates = session.execute(
        select(Dog, OwnerProfile).join(DogOwnership, DogOwnership.dog_id == Dog.id)
        .join(OwnerProfile, OwnerProfile.user_id == DogOwnership.user_id).join(Tenant, Tenant.id == DogOwnership.tenant_id)
        .where(DogOwnership.active.is_(True), Dog.active.is_(True), OwnerProfile.profile_public.is_(True),
               OwnerProfile.show_dogs.is_(True), OwnerProfile.show_relatives.is_(True), OwnerProfile.user_id != user.id,
               Tenant.active.is_(True), Tenant.deleted.is_(False))
    ).all()
    matches: dict[int, tuple[int, str, str, Dog, OwnerProfile]] = {}
    for candidate, profile in candidates:
        for source in source_dogs:
            relationship = family_relationship(session, source, candidate)
            if not relationship:
                continue
            group, label = relationship
            priority = 0 if group == "litter" else 1
            current = matches.get(candidate.id)
            if not current or priority < current[0]:
                matches[candidate.id] = (priority, group, f"{source.call_name}と{label}", candidate, profile)
    return matches


def family_kennel_tenant_ids(user: User, session: Session) -> set[int]:
    """閲覧者が所属する、または愛犬を迎えた犬舎だけを返す。"""
    tenant_ids = set(session.scalars(
        select(DogOwnership.tenant_id).join(Tenant, Tenant.id == DogOwnership.tenant_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True),
               Tenant.active.is_(True), Tenant.deleted.is_(False))
    ).all())
    tenant_ids.update(session.scalars(
        select(Membership.tenant_id).join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user.id, Tenant.active.is_(True), Tenant.deleted.is_(False))
    ).all())
    if user.platform_admin:
        tenant_ids.update(session.scalars(
            select(Tenant.id).where(Tenant.active.is_(True), Tenant.deleted.is_(False))
        ).all())
    return tenant_ids


def family_unread_message_items(user: User, session: Session) -> list[tuple[FamilyConversation, FamilyMessage]]:
    """利用者宛ての、会話ごとの最新未読メッセージを返す。"""
    conversations = session.scalars(
        select(FamilyConversation).where(
            (FamilyConversation.user1_id == user.id) | (FamilyConversation.user2_id == user.id)
        )
    ).all()
    unread: list[tuple[FamilyConversation, FamilyMessage]] = []
    for conversation in conversations:
        latest = session.scalar(
            select(FamilyMessage).where(
                FamilyMessage.conversation_id == conversation.id,
                FamilyMessage.sender_id != user.id,
                FamilyMessage.withdrawn_at.is_(None),
                FamilyMessage.hidden_at.is_(None),
            ).order_by(FamilyMessage.sent_at.desc()).limit(1)
        )
        if not latest:
            continue
        read = session.scalar(select(FamilyMessageRead).where(
            FamilyMessageRead.conversation_id == conversation.id,
            FamilyMessageRead.user_id == user.id,
        ))
        if not read or latest.sent_at > read.last_read_at:
            unread.append((conversation, latest))
    return sorted(unread, key=lambda item: item[1].sent_at, reverse=True)


def family_unread_announcements(user: User, session: Session) -> list[tuple[FamilyAnnouncement, Tenant]]:
    tenant_ids = family_kennel_tenant_ids(user, session)
    if not tenant_ids:
        return []
    return list(session.execute(
        select(FamilyAnnouncement, Tenant).join(Tenant, Tenant.id == FamilyAnnouncement.tenant_id)
        .outerjoin(FamilyAnnouncementRead, and_(
            FamilyAnnouncementRead.announcement_id == FamilyAnnouncement.id,
            FamilyAnnouncementRead.user_id == user.id,
        ))
        .where(
            FamilyAnnouncement.tenant_id.in_(tenant_ids), FamilyAnnouncement.active.is_(True),
            Tenant.active.is_(True), Tenant.deleted.is_(False), FamilyAnnouncementRead.id.is_(None),
        ).order_by(FamilyAnnouncement.created_at.desc()).limit(100)
    ).all())


def family_notification_count(user: User, session: Session) -> int:
    return len(family_unread_message_items(user, session)) + len(family_unread_announcements(user, session))


def family_message_name(user_id: int, session: Session) -> str:
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == user_id))
    if profile and profile.profile_public and profile.show_nickname and profile.nickname:
        return profile.nickname
    return "FAMILYメンバー"


def family_message_conversation(conversation_id: int, user: User, session: Session) -> FamilyConversation:
    conversation = session.get(FamilyConversation, conversation_id)
    if not conversation or user.id not in {conversation.user1_id, conversation.user2_id}:
        raise HTTPException(status_code=404)
    return conversation


def family_message_blocked(conversation: FamilyConversation, session: Session) -> bool:
    return session.scalar(
        select(FamilyMessageBlock.id).where(
            FamilyMessageBlock.tenant_id == conversation.tenant_id,
            FamilyMessageBlock.blocker_id.in_([conversation.user1_id, conversation.user2_id]),
            FamilyMessageBlock.blocked_id.in_([conversation.user1_id, conversation.user2_id]),
        )
    ) is not None


FAMILY_MESSAGE_NOTICE = "安全管理およびトラブル対応のため、必要な場合に限り、犬舎管理者がメッセージ履歴を確認することがあります。"


@app.get("/family/messages/manage", response_class=HTMLResponse)
def family_messages_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    conversations = session.scalars(
        select(FamilyConversation).where(FamilyConversation.tenant_id == tenant.id)
        .order_by(FamilyConversation.created_at.desc())
    ).all()
    rows = ""
    for conversation in conversations:
        latest = session.scalar(select(FamilyMessage).where(FamilyMessage.conversation_id == conversation.id).order_by(FamilyMessage.sent_at.desc()))
        preview = "メッセージなし" if not latest else ("送信取消済み" if latest.withdrawn_at else latest.body[:40])
        rows += f'''<tr><td>{html.escape(family_message_name(conversation.user1_id, session))}</td>
        <td>{html.escape(family_message_name(conversation.user2_id, session))}</td><td>{html.escape(preview)}</td>
        <td>{"利用中" if conversation.active else "停止中"}</td><td><a class="button secondary" href="/family/messages/manage/{conversation.id}">履歴を確認</a></td></tr>'''
    body = f'''<h1>FAMILYメッセージ管理</h1><div class="tenant"><p>{FAMILY_MESSAGE_NOTICE}</p>
    <p>履歴を開いた操作も記録されます。原文は変更せず、不適切な投稿の非表示と管理メモのみ行えます。</p></div>
    <table><tr><th>参加者1</th><th>参加者2</th><th>最新</th><th>状態</th><th>操作</th></tr>{rows or '<tr><td colspan="5">会話はまだありません。</td></tr>'}</table>'''
    return layout("FAMILYメッセージ管理", body, user)


@app.get("/family/messages/manage/{conversation_id}", response_class=HTMLResponse)
def family_messages_manage_detail(conversation_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    conversation = session.scalar(select(FamilyConversation).where(FamilyConversation.id == conversation_id, FamilyConversation.tenant_id == tenant.id))
    if not conversation:
        raise HTTPException(status_code=404)
    session.add(FamilyMessageAudit(conversation_id=conversation.id, admin_user_id=user.id, action="view", details="管理者が履歴を閲覧"))
    session.commit()
    messages = session.scalars(select(FamilyMessage).where(FamilyMessage.conversation_id == conversation.id).order_by(FamilyMessage.sent_at)).all()
    cards = ""
    for message in messages:
        states = " / ".join(value for value in ["送信取消済み" if message.withdrawn_at else "", "非表示" if message.hidden_at else ""] if value) or "表示中"
        cards += f'''<article class="tenant"><p><strong>{html.escape(family_message_name(message.sender_id, session))}</strong>　{message.sent_at.strftime('%Y-%m-%d %H:%M')}　<span class="badge">{states}</span></p>
        <p style="white-space:pre-wrap">{html.escape(message.body)}</p>
        <form method="post" action="/family/messages/manage/{conversation.id}/messages/{message.id}/moderate">
        <label>管理メモ</label><input name="admin_note" maxlength="500" value="{html.escape(message.admin_note or '')}">
        <button name="action" value="{'unhide' if message.hidden_at else 'hide'}">{'再表示' if message.hidden_at else '利用者画面から非表示'}</button></form></article>'''
    body = f'''<a class="button secondary" href="/family/messages/manage">一覧へ戻る</a><h1>メッセージ履歴</h1>
    <p>{html.escape(family_message_name(conversation.user1_id, session))} ↔ {html.escape(family_message_name(conversation.user2_id, session))}</p>
    <form method="post" action="/family/messages/manage/{conversation.id}/state"><button name="active" value="{'true' if not conversation.active else 'false'}">{'利用を再開' if not conversation.active else 'この会話を停止'}</button></form>{cards or '<p>メッセージはありません。</p>'}'''
    return layout("メッセージ履歴", body, user)


@app.post("/family/messages/manage/{conversation_id}/state")
def family_messages_manage_state(conversation_id: int, active: str = Form(...), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    conversation = session.scalar(select(FamilyConversation).where(FamilyConversation.id == conversation_id, FamilyConversation.tenant_id == tenant.id))
    if not conversation:
        raise HTTPException(status_code=404)
    conversation.active = active == "true"
    session.add(FamilyMessageAudit(conversation_id=conversation.id, admin_user_id=user.id, action="resume" if conversation.active else "suspend", details="会話状態を変更"))
    session.commit()
    return RedirectResponse(f"/family/messages/manage/{conversation.id}", status_code=303)


@app.post("/family/messages/manage/{conversation_id}/messages/{message_id}/moderate")
def family_message_moderate(conversation_id: int, message_id: int, action: str = Form(...), admin_note: str = Form(""), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    conversation = session.scalar(select(FamilyConversation).where(FamilyConversation.id == conversation_id, FamilyConversation.tenant_id == tenant.id))
    message = session.scalar(select(FamilyMessage).where(FamilyMessage.id == message_id, FamilyMessage.conversation_id == conversation_id))
    if not conversation or not message or action not in {"hide", "unhide"}:
        raise HTTPException(status_code=404)
    message.hidden_at = datetime.now(timezone.utc) if action == "hide" else None
    message.hidden_by_id = user.id if action == "hide" else None
    message.admin_note = admin_note.strip()[:500] or None
    session.add(FamilyMessageAudit(conversation_id=conversation.id, admin_user_id=user.id, action=action, details=f"message_id={message.id}"))
    session.commit()
    return RedirectResponse(f"/family/messages/manage/{conversation.id}", status_code=303)


@app.get("/family/messages", response_class=HTMLResponse)
def family_messages(user: User = Depends(require_user), session: Session = Depends(db)):
    conversations = session.scalars(
        select(FamilyConversation).where((FamilyConversation.user1_id == user.id) | (FamilyConversation.user2_id == user.id))
        .order_by(FamilyConversation.created_at.desc())
    ).all()
    cards = ""
    for conversation in conversations:
        other_id = conversation.user2_id if conversation.user1_id == user.id else conversation.user1_id
        latest = session.scalar(select(FamilyMessage).where(FamilyMessage.conversation_id == conversation.id).order_by(FamilyMessage.sent_at.desc()))
        read = session.scalar(select(FamilyMessageRead).where(FamilyMessageRead.conversation_id == conversation.id, FamilyMessageRead.user_id == user.id))
        unread = bool(latest and latest.sender_id != user.id and (not read or latest.sent_at > read.last_read_at))
        preview = "まだメッセージはありません" if not latest else ("送信が取り消されました" if latest.withdrawn_at else ("管理者により非表示" if latest.hidden_at else latest.body[:55]))
        cards += f'''<a class="module" href="/family/messages/{conversation.id}"><h3>{html.escape(family_message_name(other_id, session))} {'<span class="badge">未読</span>' if unread else ''}</h3>
        <p>{html.escape(preview)}</p><p><small>{'利用中' if conversation.active else '犬舎により停止中'}</small></p></a>'''
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>メッセージ</h1>
    <div class="tenant"><p>{FAMILY_MESSAGE_NOTICE}</p><p>送信後の原文編集はできません。必要な場合は送信取消をご利用ください。</p></div>
    <div class="grid">{cards or '<p>会話はまだありません。公開プロフィールの「メッセージを送る」から開始できます。</p>'}</div>'''
    return family_layout("メッセージ｜FAMILY", body, user, session)


@app.post("/family/messages/start/{public_id}")
def family_message_start(public_id: str, user: User = Depends(require_user), session: Session = Depends(db)):
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.public_id == public_id, OwnerProfile.profile_public.is_(True)))
    if not profile or profile.user_id == user.id:
        raise HTTPException(status_code=400, detail="この相手とは会話を開始できません")
    shared = family_kennel_tenant_ids(user, session) & family_kennel_tenant_ids(session.get(User, profile.user_id), session)
    if not shared:
        raise HTTPException(status_code=403, detail="同じ犬舎のFAMILY間でのみ利用できます")
    tenant_id = sorted(shared)[0]
    user1_id, user2_id = sorted([user.id, profile.user_id])
    conversation = session.scalar(select(FamilyConversation).where(FamilyConversation.tenant_id == tenant_id, FamilyConversation.user1_id == user1_id, FamilyConversation.user2_id == user2_id))
    if not conversation:
        conversation = FamilyConversation(tenant_id=tenant_id, user1_id=user1_id, user2_id=user2_id)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    return RedirectResponse(f"/family/messages/{conversation.id}", status_code=303)


@app.get("/family/messages/{conversation_id}", response_class=HTMLResponse)
def family_message_detail(conversation_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    conversation = family_message_conversation(conversation_id, user, session)
    other_id = conversation.user2_id if conversation.user1_id == user.id else conversation.user1_id
    read = session.scalar(select(FamilyMessageRead).where(FamilyMessageRead.conversation_id == conversation.id, FamilyMessageRead.user_id == user.id))
    if read:
        read.last_read_at = datetime.now(timezone.utc)
    else:
        session.add(FamilyMessageRead(conversation_id=conversation.id, user_id=user.id))
    session.commit()
    messages = session.scalars(select(FamilyMessage).where(FamilyMessage.conversation_id == conversation.id).order_by(FamilyMessage.sent_at)).all()
    cards = ""
    for message in messages:
        mine = message.sender_id == user.id
        if message.hidden_at:
            content = "管理者により非表示になりました"
        elif message.withdrawn_at:
            content = "送信が取り消されました"
        else:
            content = html.escape(message.body)
        withdraw = f'<form method="post" action="/family/messages/{conversation.id}/{message.id}/withdraw"><button class="secondary">送信取消</button></form>' if mine and not message.withdrawn_at and not message.hidden_at else ""
        cards += f'''<article class="tenant" style="margin-left:{'18%' if mine else '0'};margin-right:{'0' if mine else '18%'}"><p><strong>{'あなた' if mine else html.escape(family_message_name(other_id, session))}</strong> <small>{message.sent_at.strftime('%Y-%m-%d %H:%M')}</small></p><p style="white-space:pre-wrap">{content}</p>{withdraw}</article>'''
    blocked = family_message_blocked(conversation, session)
    send_form = f'''<form method="post" action="/family/messages/{conversation.id}"><label>メッセージ（1000文字まで）</label><textarea name="body" maxlength="1000" required></textarea><button>送信する</button></form>''' if conversation.active and not blocked else '<div class="tenant"><p>現在、この会話には送信できません。</p></div>'
    own_block = session.scalar(select(FamilyMessageBlock).where(FamilyMessageBlock.tenant_id == conversation.tenant_id, FamilyMessageBlock.blocker_id == user.id, FamilyMessageBlock.blocked_id == other_id))
    body = f'''<a class="button secondary" href="/family/messages">メッセージ一覧へ戻る</a><h1>{html.escape(family_message_name(other_id, session))}さん</h1>
    <p><small>{FAMILY_MESSAGE_NOTICE}</small></p>{cards or '<p>最初のメッセージを送ってみましょう。</p>'}{send_form}
    <form method="post" action="/family/messages/{conversation.id}/block"><button class="secondary">{'ブロックを解除' if own_block else 'この相手をブロック'}</button></form>'''
    return family_layout("メッセージ｜FAMILY", body, user, session)


@app.post("/family/messages/{conversation_id}")
def family_message_send(conversation_id: int, body: str = Form(...), user: User = Depends(require_user), session: Session = Depends(db)):
    conversation = family_message_conversation(conversation_id, user, session)
    message_body = body.strip()
    if not message_body or len(message_body) > 1000:
        raise HTTPException(status_code=400, detail="メッセージは1〜1000文字で入力してください")
    if not conversation.active or family_message_blocked(conversation, session):
        raise HTTPException(status_code=403, detail="現在、この会話には送信できません")
    session.add(FamilyMessage(conversation_id=conversation.id, sender_id=user.id, body=message_body))
    session.commit()
    return RedirectResponse(f"/family/messages/{conversation.id}", status_code=303)


@app.post("/family/messages/{conversation_id}/{message_id}/withdraw")
def family_message_withdraw(conversation_id: int, message_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    family_message_conversation(conversation_id, user, session)
    message = session.scalar(select(FamilyMessage).where(FamilyMessage.id == message_id, FamilyMessage.conversation_id == conversation_id, FamilyMessage.sender_id == user.id))
    if not message:
        raise HTTPException(status_code=404)
    message.withdrawn_at = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f"/family/messages/{conversation_id}", status_code=303)


@app.post("/family/messages/{conversation_id}/block")
def family_message_block(conversation_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    conversation = family_message_conversation(conversation_id, user, session)
    other_id = conversation.user2_id if conversation.user1_id == user.id else conversation.user1_id
    block = session.scalar(select(FamilyMessageBlock).where(FamilyMessageBlock.tenant_id == conversation.tenant_id, FamilyMessageBlock.blocker_id == user.id, FamilyMessageBlock.blocked_id == other_id))
    if block:
        session.delete(block)
    else:
        session.add(FamilyMessageBlock(tenant_id=conversation.tenant_id, blocker_id=user.id, blocked_id=other_id))
    session.commit()
    return RedirectResponse(f"/family/messages/{conversation.id}", status_code=303)


@app.get("/family/kennel", response_class=HTMLResponse)
def family_kennel_page(user: User = Depends(require_user), session: Session = Depends(db)):
    """同じ犬舎から迎えた、公開に同意済みのFAMILYを犬舎別に表示する。"""
    tenant_ids = family_kennel_tenant_ids(user, session)
    if not tenant_ids:
        body = '''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>犬舎FAMILY会</h1>
        <div class="tenant"><p>愛犬または犬舎との連携がまだありません。</p><p>犬舎へ、登録したメールアドレスをお知らせください。</p></div>'''
        return family_layout("犬舎FAMILY会", body, user, session)

    records = session.execute(
        select(Tenant, OwnerProfile, Dog).join(DogOwnership, DogOwnership.tenant_id == Tenant.id)
        .join(Dog, Dog.id == DogOwnership.dog_id).join(OwnerProfile, OwnerProfile.user_id == DogOwnership.user_id)
        .where(Tenant.id.in_(tenant_ids), Tenant.active.is_(True), Tenant.deleted.is_(False),
               DogOwnership.active.is_(True), Dog.active.is_(True), OwnerProfile.profile_public.is_(True),
               OwnerProfile.show_dogs.is_(True))
        .order_by(Tenant.name, OwnerProfile.updated_at.desc(), Dog.call_name)
    ).all()
    grouped: dict[int, dict] = {}
    for tenant, profile, dog in records:
        tenant_group = grouped.setdefault(tenant.id, {"tenant": tenant, "members": {}})
        member = tenant_group["members"].setdefault(profile.id, {"profile": profile, "dogs": {}})
        member["dogs"][dog.id] = dog

    sections = ""
    for group in grouped.values():
        tenant, member_cards = group["tenant"], ""
        for member in group["members"].values():
            profile, dogs = member["profile"], list(member["dogs"].values())
            member_name = profile.nickname if profile.show_nickname and profile.nickname else "FAMILYメンバー"
            location = profile.prefecture if profile.show_prefecture and profile.prefecture else "地域非公開"
            photo = f'<img src="/family/members/{profile.public_id}/photo" alt="" style="width:72px;height:72px;object-fit:cover;border-radius:50%;margin-bottom:10px">' if profile.show_photo and profile.photo_data else '<div style="width:72px;height:72px;border-radius:50%;display:grid;place-items:center;background:#ead0d5;font-size:26px;margin-bottom:10px">♡</div>'
            dog_names = "、".join(html.escape(dog.call_name) for dog in dogs[:4])
            if len(dogs) > 4:
                dog_names += f" ほか{len(dogs) - 4}頭"
            own_badge = ' <span class="badge">あなた</span>' if profile.user_id == user.id else ""
            instagram = f'<p>Instagram：@{html.escape(profile.instagram_username)}</p>' if profile.show_instagram and profile.instagram_username else ""
            member_cards += f'''<a class="module" href="/family/members/{profile.public_id}">{photo}<h3>{html.escape(member_name)}{own_badge}</h3>
            <p>{html.escape(location)}</p>{instagram}<p><strong>愛犬：</strong>{dog_names}</p><p><span class="badge">{len(dogs)}頭</span></p></a>'''
        sections += f'''<section class="tenant"><h2 style="margin-top:0">{html.escape(tenant.name)} FAMILY会</h2>
        <p>同じ犬舎から愛犬を迎えた、公開中のオーナー様です。</p><div class="grid">{member_cards or '<p>公開中のメンバーはまだいません。</p>'}</div></section>'''
    if not sections:
        tenant_names = session.scalars(select(Tenant.name).where(Tenant.id.in_(tenant_ids)).order_by(Tenant.name)).all()
        sections = "".join(f'<section class="tenant"><h2 style="margin-top:0">{html.escape(name)} FAMILY会</h2><p>公開中のメンバーはまだいません。</p></section>' for name in tenant_names)
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>犬舎FAMILY会</h1>
    <p>血縁にかかわらず、同じ犬舎から愛犬を迎えたFAMILY同士がつながるページです。公開を許可したプロフィールと愛犬だけを表示します。</p>{sections}
    <p><small>表示内容は各オーナー様の公開プロフィール設定に従います。</small></p>'''
    return family_layout("犬舎FAMILY会｜FAMILY", body, user, session)


def family_timeline_items(user: User, session: Session) -> dict[int, tuple[FamilyDogAlbumItem, Dog, Tenant, OwnerProfile]]:
    """閲覧者に公開できる成長アルバム投稿を返す。"""
    source_dogs = session.scalars(
        select(Dog).join(DogOwnership, DogOwnership.dog_id == Dog.id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True), Dog.active.is_(True))
    ).all()
    tenant_ids = family_kennel_tenant_ids(user, session)
    records = session.execute(
        select(FamilyDogAlbumItem, Dog, Tenant, OwnerProfile)
        .join(Dog, Dog.id == FamilyDogAlbumItem.dog_id).join(Tenant, Tenant.id == Dog.tenant_id)
        .join(OwnerProfile, OwnerProfile.user_id == FamilyDogAlbumItem.uploaded_by_id)
        .where(FamilyDogAlbumItem.visibility.in_(["family", "relatives"]), Dog.active.is_(True),
               Tenant.active.is_(True), Tenant.deleted.is_(False), OwnerProfile.profile_public.is_(True),
               OwnerProfile.show_dogs.is_(True))
        .order_by(FamilyDogAlbumItem.created_at.desc()).limit(200)
    ).all()
    visible: dict[int, tuple[FamilyDogAlbumItem, Dog, Tenant, OwnerProfile]] = {}
    for item, dog, tenant, profile in records:
        allowed = item.uploaded_by_id == user.id
        if item.visibility == "family" and dog.tenant_id in tenant_ids:
            allowed = True
        if item.visibility == "relatives" and any(family_relationship(session, source, dog) for source in source_dogs):
            allowed = True
        if allowed:
            visible[item.id] = (item, dog, tenant, profile)
    return visible


@app.get("/family/timeline", response_class=HTMLResponse)
def family_timeline(user: User = Depends(require_user), session: Session = Depends(db)):
    visible = family_timeline_items(user, session)
    posts = ""
    for item, dog, tenant, profile in list(visible.values())[:50]:
        owner_name = profile.nickname if profile.show_nickname and profile.nickname else "FAMILYメンバー"
        taken = item.taken_on.strftime("%Y年%m月%d日") if item.taken_on else item.created_at.date().strftime("%Y年%m月%d日")
        visibility = "同じ犬舎のFAMILYに公開" if item.visibility == "family" else "兄弟・親戚犬に公開"
        caption = f'<p style="white-space:pre-wrap">{html.escape(item.caption)}</p>' if item.caption else ""
        posts += f'''<article class="tenant" style="max-width:760px;margin:0 auto 22px">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:start"><div><strong>{html.escape(owner_name)}</strong>
        <p style="margin:3px 0"><a href="/family/members/{profile.public_id}">{html.escape(dog.call_name)}</a>　<small>{html.escape(tenant.name)}</small></p></div>
        <span class="badge">{html.escape(visibility)}</span></div>
        <a href="/family/timeline/{item.id}/photo" target="_blank" style="display:flex;align-items:center;justify-content:center;min-height:240px;max-height:520px;background:#fff;border-radius:14px;overflow:hidden;margin-top:12px">
        <img src="/family/timeline/{item.id}/photo" alt="{html.escape(dog.call_name)}の成長写真" style="display:block;max-width:100%;max-height:520px;width:auto;height:auto;object-fit:contain"></a>
        {caption}<p><small>撮影日：{taken}</small></p></article>'''
    if not posts:
        posts = '''<div class="tenant"><p>タイムラインに表示できる写真はまだありません。</p>
        <p>「うちの子」から愛犬を開き、成長アルバムへ写真を追加してください。公開範囲を「同じ犬舎のFAMILY」または「兄弟・親戚犬」にすると表示されます。</p></div>'''
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>FAMILYタイムライン</h1>
    <p>同じ犬舎のFAMILYや兄弟・親戚犬が公開した成長写真を、新しい順に表示しています。</p>{posts}
    <p><small>「自分だけ」に設定した写真はタイムラインには表示されません。</small></p>'''
    return family_layout("FAMILYタイムライン", body, user, session)


@app.get("/family/timeline/{item_id}/photo")
def family_timeline_photo(item_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    record = family_timeline_items(user, session).get(item_id)
    if not record:
        raise HTTPException(status_code=404)
    item = record[0]
    return Response(content=item.photo_data, media_type=item.photo_content_type, headers={"Cache-Control": "private, max-age=300"})


@app.get("/family/relatives", response_class=HTMLResponse)
def family_relatives_page(user: User = Depends(require_user), session: Session = Depends(db)):
    matches = family_relative_matches(user, session)
    litter_cards, relative_cards = "", ""
    for _, group, label, dog, profile in sorted(matches.values(), key=lambda value: (value[0], value[3].call_name)):
        owner_name = profile.nickname if profile.show_nickname and profile.nickname else "FAMILYメンバー"
        family_profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog.id))
        dog_photo = f'<img class="family-dog-thumb" src="/family/relatives/dogs/{dog.id}/photo" alt="{html.escape(dog.call_name)}">' if family_profile and family_profile.photo_data else ''
        album_items = session.scalars(
            select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.dog_id == dog.id, FamilyDogAlbumItem.visibility.in_(["relatives", "family"]))
            .order_by(FamilyDogAlbumItem.taken_on.desc(), FamilyDogAlbumItem.created_at.desc()).limit(3)
        ).all()
        shared_photos = "".join(
            f'<a href="/family/relatives/album/{item.id}/photo" target="_blank"><img src="/family/relatives/album/{item.id}/photo" alt="共有写真" style="width:76px;height:76px;object-fit:contain;background:#f7edef;border-radius:9px"></a>' for item in album_items
        )
        card = f'''<article class="module">{dog_photo}<h3>{html.escape(dog.call_name)}</h3><p>{html.escape(dog.registered_name or "血統書名未登録")}</p>
        <p><span class="badge">{html.escape(label)}</span></p><p>{html.escape(dog.breed or "犬種未登録")} ／ {html.escape(dog.color or "毛色未登録")}</p>
        <p>オーナー：<a href="/family/members/{profile.public_id}">{html.escape(owner_name)}</a></p>{f'<div style="display:flex;gap:7px;margin-top:12px">{shared_photos}</div>' if shared_photos else ''}</article>'''
        if group == "litter":
            litter_cards += card
        else:
            relative_cards += card
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>兄弟・親戚犬とのつながり</h1>
    <p>登録された血統データから関係を自動判定し、公開に同意したオーナー様と愛犬だけを表示します。</p>
    <h2>同腹兄弟</h2><div class="grid">{litter_cards or '<p>現在、公開中の同腹兄弟はいません。</p>'}</div>
    <h2>親戚犬</h2><div class="grid">{relative_cards or '<p>現在、公開中の親戚犬はいません。</p>'}</div>
    <p><small>血統書に父犬・母犬・先祖が正しく登録されているほど、より正確に判定できます。</small></p>'''
    return family_layout("兄弟・親戚犬｜FAMILY", body, user, session)


@app.get("/family/relatives/dogs/{dog_id}/photo")
def family_relative_dog_photo(dog_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if dog_id not in family_relative_matches(user, session):
        raise HTTPException(status_code=404)
    profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog_id))
    if not profile or not profile.photo_data:
        raise HTTPException(status_code=404)
    return Response(content=profile.photo_data, media_type=profile.photo_content_type or "image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@app.get("/family/relatives/album/{item_id}/photo")
def family_relative_album_photo(item_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    item = session.scalar(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.id == item_id, FamilyDogAlbumItem.visibility.in_(["relatives", "family"])))
    if not item or item.dog_id not in family_relative_matches(user, session):
        raise HTTPException(status_code=404)
    return Response(content=item.photo_data, media_type=item.photo_content_type, headers={"Cache-Control": "private, max-age=300"})


@app.get("/family/members/{public_id}", response_class=HTMLResponse)
def family_member_detail(public_id: str, user: User = Depends(require_user), session: Session = Depends(db)):
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.public_id == public_id, OwnerProfile.profile_public.is_(True)))
    if not profile:
        return HTMLResponse(family_layout("非公開プロフィール", '<h1>プロフィールは非公開です</h1><p>現在、このプロフィールは公開されていません。</p><a class="button secondary" href="/family/kennel">犬舎FAMILY会へ戻る</a>', user, session), status_code=404)
    title = profile.nickname if profile.show_nickname and profile.nickname else "FAMILYメンバー"
    photo = f'<img src="/family/members/{profile.public_id}/photo" alt="プロフィール写真" style="width:180px;height:180px;object-fit:cover;border-radius:50%;border:5px solid #ead0d5">' if profile.show_photo and profile.photo_data else ""
    prefecture = f'<p><span class="badge">{html.escape(profile.prefecture)}</span></p>' if profile.show_prefecture and profile.prefecture else ""
    bio = f'<div class="tenant" style="white-space:pre-wrap">{html.escape(profile.bio)}</div>' if profile.show_bio and profile.bio else ""
    instagram = f'''<p><a class="button" href="https://www.instagram.com/{html.escape(profile.instagram_username)}/" target="_blank" rel="noopener noreferrer">Instagram @{html.escape(profile.instagram_username)} を見る ↗</a></p>''' if profile.show_instagram and profile.instagram_username else ""
    message_button = ""
    target_user = session.get(User, profile.user_id)
    if profile.user_id != user.id and target_user and family_kennel_tenant_ids(user, session) & family_kennel_tenant_ids(target_user, session):
        message_button = f'''<form method="post" action="/family/messages/start/{profile.public_id}"><button>メッセージを送る</button></form>'''
    dogs_section = ""
    records = []
    if profile.show_dogs:
        records = session.execute(
            select(DogOwnership, Dog, Tenant).join(Dog, Dog.id == DogOwnership.dog_id).join(Tenant, Tenant.id == DogOwnership.tenant_id)
            .where(DogOwnership.user_id == profile.user_id, DogOwnership.active.is_(True), Dog.active.is_(True), Tenant.active.is_(True), Tenant.deleted.is_(False))
            .order_by(Dog.call_name)
        ).all()
        dog_cards = ""
        for ownership, dog, tenant in records:
            sex = {"male": "牡", "female": "牝"}.get(dog.sex, dog.sex)
            relation = "主オーナー" if ownership.relationship == "primary" else "ご家族"
            parent_html = ""
            if profile.show_parents:
                parent_cards = ""
                for label, parent_id in (("父犬", dog.sire_id), ("母犬", dog.dam_id)):
                    parent = session.get(Dog, parent_id) if parent_id else None
                    if parent and parent.tenant_id == dog.tenant_id:
                        parent_name = parent.registered_name or parent.call_name
                        parent_cards += f'''<div class="tenant" style="margin:0"><strong>{label}</strong><p>{html.escape(parent_name)}</p>
                        <p>{title_marks(parent.titles) or "称号なし"}</p><p><small>毛色：{html.escape(parent.color or "未登録")}</small></p></div>'''
                    else:
                        parent_cards += f'<div class="tenant" style="margin:0"><strong>{label}</strong><p>未登録</p></div>'
                parent_html = f'<h3 style="margin-top:18px">父母</h3><div class="grid">{parent_cards}</div>'
            dog_cards += f'''<section class="tenant"><p><span class="badge">{relation}</span> <small>{html.escape(tenant.name)}</small></p>
            <h2 style="margin-top:8px">{html.escape(dog.call_name)}</h2><p>{html.escape(dog.registered_name or "血統書名未登録")}</p>
            <p>{title_marks(dog.titles) or "称号なし"}</p><p>{html.escape(dog.breed or "犬種未登録")} ／ {html.escape(sex)} ／ {html.escape(dog.color or "毛色未登録")}</p>{parent_html}</section>'''
        dogs_section = f'<h2>愛犬</h2>{dog_cards or "<p>公開できる愛犬はまだ登録されていません。</p>"}'
    relatives_section = ""
    if profile.show_dogs and profile.show_relatives and records:
        source_dogs = {dog.id: dog for _, dog, _ in records}
        candidates = session.execute(
            select(Dog, OwnerProfile).join(DogOwnership, DogOwnership.dog_id == Dog.id)
            .join(OwnerProfile, OwnerProfile.user_id == DogOwnership.user_id).join(Tenant, Tenant.id == DogOwnership.tenant_id)
            .where(DogOwnership.active.is_(True), Dog.active.is_(True), OwnerProfile.profile_public.is_(True),
                   OwnerProfile.show_dogs.is_(True), OwnerProfile.id != profile.id, Tenant.active.is_(True), Tenant.deleted.is_(False))
            .order_by(Dog.call_name)
        ).all()
        matches: dict[int, tuple[int, str, str, Dog, OwnerProfile]] = {}
        for candidate, candidate_profile in candidates:
            if candidate.id in source_dogs:
                continue
            for source in source_dogs.values():
                relationship = family_relationship(session, source, candidate)
                if not relationship:
                    continue
                group, label = relationship
                priority = 0 if group == "litter" else 1
                current = matches.get(candidate.id)
                if not current or priority < current[0]:
                    matches[candidate.id] = (priority, group, f"{source.call_name}と{label}", candidate, candidate_profile)
        litter_cards, relative_cards = "", ""
        for _, group, label, dog, candidate_profile in sorted(matches.values(), key=lambda value: (value[0], value[3].call_name)):
            member_name = candidate_profile.nickname if candidate_profile.show_nickname and candidate_profile.nickname else "FAMILYメンバー"
            card = f'''<a class="module" href="/family/members/{candidate_profile.public_id}"><h3>{html.escape(dog.call_name)}</h3>
            <p>{html.escape(dog.registered_name or "血統書名未登録")}</p><p><span class="badge">{html.escape(label)}</span></p>
            <p>{html.escape(dog.breed or "犬種未登録")} ／ {html.escape(dog.color or "毛色未登録")}</p><p>オーナー：{html.escape(member_name)}</p></a>'''
            if group == "litter":
                litter_cards += card
            else:
                relative_cards += card
        if litter_cards or relative_cards:
            relatives_section = f'''<h2>同腹兄弟・親戚犬</h2>
            {f'<h3>同腹兄弟</h3><div class="grid">{litter_cards}</div>' if litter_cards else ''}
            {f'<h3>親戚犬</h3><div class="grid">{relative_cards}</div>' if relative_cards else ''}'''
        else:
            relatives_section = '<h2>同腹兄弟・親戚犬</h2><p>現在、公開中のFAMILYメンバーには該当する犬がいません。</p>'
    body = f'''<a class="button secondary" href="/family/kennel">犬舎FAMILY会へ戻る</a><h1>{html.escape(title)}</h1>{photo}{prefecture}{instagram}{message_button}{bio}{dogs_section}{relatives_section}
    <p><small>このページには、ご本人が公開を許可した項目だけを表示しています。</small></p>'''
    return family_layout(f"{title}｜FAMILY", body, user, session)


@app.get("/family/members/{public_id}/photo")
def family_member_photo(public_id: str, user: User = Depends(require_user), session: Session = Depends(db)):
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.public_id == public_id, OwnerProfile.profile_public.is_(True), OwnerProfile.show_photo.is_(True)))
    if not profile or not profile.photo_data:
        raise HTTPException(status_code=404)
    return Response(content=profile.photo_data, media_type=profile.photo_content_type or "image/jpeg", headers={"Cache-Control": "private, max-age=300"})


def active_owner_invitation(raw_token: str, session: Session) -> OwnerInvitation | None:
    invitation = session.scalar(select(OwnerInvitation).where(OwnerInvitation.token_hash == token_hash(raw_token)))
    if not invitation or invitation.accepted_at or invitation.revoked_at:
        return None
    expires = invitation.expires_at if invitation.expires_at.tzinfo else invitation.expires_at.replace(tzinfo=timezone.utc)
    return invitation if expires > datetime.now(timezone.utc) else None


def owner_invitation_admin_body(user: User, tenant: Tenant, session: Session, invite_url: str = "", invite_email: str = "") -> str:
    dogs = session.scalars(
        select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True), Dog.category != "external").order_by(Dog.call_name)
    ).all()
    dog_options = "".join(f'<option value="{dog.id}">{html.escape(dog.call_name)}（{html.escape(dog.registered_name or "血統書名未登録")}）</option>' for dog in dogs)
    generated = ""
    if invite_url:
        subject = quote(f"【{tenant.name}】オーナー登録のご案内")
        message = quote(f"{tenant.name}からオーナー登録のご案内です。\n\n以下の専用URLを開き、登録を完了してください。\n{invite_url}\n\nこのURLは7日間・1回のみ利用できます。")
        mailto = f"mailto:{quote(invite_email)}?subject={subject}&body={message}"
        generated = f'''<div class="tenant"><h2>招待URLを発行しました</h2><p>このURLは7日間・1回のみ利用できます。</p>
        <input id="invite-url" readonly value="{html.escape(invite_url)}"><button type="button" onclick="navigator.clipboard.writeText(document.getElementById('invite-url').value);this.textContent='コピーしました'">URLをコピー</button>
        <a class="button success" href="{html.escape(mailto)}">メールアプリで登録案内を送る</a><p><small>メールアプリが開いたら、内容を確認して送信してください。</small></p></div>'''
    records = session.execute(
        select(OwnerInvitation, Dog).join(Dog, Dog.id == OwnerInvitation.dog_id)
        .where(OwnerInvitation.tenant_id == tenant.id).order_by(OwnerInvitation.created_at.desc()).limit(100)
    ).all()
    rows = ""
    now = datetime.now(timezone.utc)
    for invitation, dog in records:
        expires = invitation.expires_at if invitation.expires_at.tzinfo else invitation.expires_at.replace(tzinfo=timezone.utc)
        if invitation.accepted_at:
            state = "登録完了"
        elif invitation.revoked_at:
            state = "取消済み"
        elif expires <= now:
            state = "期限切れ"
        else:
            state = "招待中"
        relation = "主オーナー" if invitation.relationship == "primary" else "ご家族"
        action = f'<form class="inline" method="post" action="/family/invitations/{invitation.id}/revoke"><button class="secondary">取り消す</button></form>' if state == "招待中" else "－"
        rows += f'<tr><td>{html.escape(dog.call_name)}</td><td>{html.escape(invitation.email)}</td><td>{relation}</td><td>{state}</td><td>{expires.date()}</td><td>{action}</td></tr>'
    return f'''<a class="button secondary" href="/family/owners">オーナー連携へ戻る</a><h1>{html.escape(tenant.name)} オーナー招待</h1>
    <p>犬とオーナー様を選び、専用の登録案内を発行します。</p>{generated}
    <form method="post"><label>犬</label><select name="dog_id" required>{dog_options}</select>
    <label>招待するメールアドレス</label><input name="email" type="email" required>
    <label>関係</label><select name="relationship"><option value="primary">主オーナー</option><option value="family">ご家族</option></select>
    <button>期限付き招待URLを発行</button></form><h2>招待履歴</h2>
    <table><tr><th>犬</th><th>メール</th><th>関係</th><th>状態</th><th>期限</th><th>操作</th></tr>{rows or '<tr><td colspan="6">招待履歴はありません。</td></tr>'}</table>'''


@app.get("/family/invitations", response_class=HTMLResponse)
def family_invitations(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    return layout("オーナー招待", owner_invitation_admin_body(user, tenant, session), user)


@app.post("/family/invitations", response_class=HTMLResponse)
def family_invitation_create(request: Request, dog_id: int = Form(...), email: str = Form(...), relationship: str = Form("primary"), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    if relationship not in {"primary", "family"}:
        raise HTTPException(status_code=400, detail="関係の指定が正しくありません")
    dog = tenant_dog(session, tenant.id, dog_id)
    if not dog.active or dog.category == "external":
        raise HTTPException(status_code=400, detail="この犬は招待に使用できません")
    normalized = normalize_email(email)
    previous = session.scalars(select(OwnerInvitation).where(
        OwnerInvitation.tenant_id == tenant.id, OwnerInvitation.dog_id == dog.id,
        OwnerInvitation.email == normalized, OwnerInvitation.accepted_at.is_(None), OwnerInvitation.revoked_at.is_(None),
    )).all()
    now = datetime.now(timezone.utc)
    for invitation in previous:
        invitation.revoked_at = now
    raw_token = secrets.token_urlsafe(32)
    session.add(OwnerInvitation(tenant_id=tenant.id, dog_id=dog.id, email=normalized, relationship=relationship,
                                token_hash=token_hash(raw_token), expires_at=now + timedelta(days=7), created_by_id=user.id))
    session.commit()
    public_base_url = os.environ.get("PUBLIC_BASE_URL", str(request.base_url)).rstrip("/")
    if public_base_url.startswith("http://") and request.headers.get("x-forwarded-proto") == "https":
        public_base_url = "https://" + public_base_url.removeprefix("http://")
    invite_url = public_base_url + f"/family/invite/{raw_token}"
    return layout("招待URL発行完了", owner_invitation_admin_body(user, tenant, session, invite_url, normalized), user)


@app.post("/family/invitations/{invitation_id}/revoke")
def family_invitation_revoke(invitation_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    invitation = session.scalar(select(OwnerInvitation).where(OwnerInvitation.id == invitation_id, OwnerInvitation.tenant_id == tenant.id))
    if not invitation:
        raise HTTPException(status_code=404, detail="招待が見つかりません")
    if not invitation.accepted_at:
        invitation.revoked_at = datetime.now(timezone.utc)
        session.commit()
    return RedirectResponse("/family/invitations", status_code=303)


@app.get("/family/invite/{raw_token}", response_class=HTMLResponse)
def family_invite_page(raw_token: str, viewer: User | None = Depends(current_user), session: Session = Depends(db)):
    invitation = active_owner_invitation(raw_token, session)
    if not invitation:
        return layout("招待URLエラー", '<h1>この招待URLは利用できません</h1><p class="error">期限切れ、使用済み、または取り消された招待です。犬舎へ再発行をご依頼ください。</p>')
    dog, tenant = session.get(Dog, invitation.dog_id), session.get(Tenant, invitation.tenant_id)
    if not dog or not tenant:
        raise HTTPException(status_code=404)
    account = session.scalar(select(User).where(User.email == invitation.email))
    if viewer and viewer.email != invitation.email:
        form = '<p class="error">現在ログイン中のアカウントは、招待先のメールアドレスと異なります。一度ログアウトしてから招待URLを開いてください。</p>'
    elif viewer:
        form = '<p>ログイン中のアカウントで連携できます。</p><button>招待を受け取る</button>'
    elif account:
        form = f'<p>{html.escape(invitation.email)} の登録済みアカウントへ連携します。</p><label>パスワード</label><input name="password" type="password" required><button>ログインして招待を受け取る</button>'
    else:
        form = f'<p>{html.escape(invitation.email)} でオーナーアカウントを作成します。</p><label>お名前</label><input name="name" required maxlength="100"><label>パスワード（8文字以上）</label><input name="password" type="password" minlength="8" required><button>登録して招待を受け取る</button>'
    body = f'''<h1>{html.escape(tenant.name)}からのご招待</h1><div class="tenant"><h2>{html.escape(dog.call_name)}</h2><p>{html.escape(dog.registered_name or "血統書名未登録")}</p></div>
    <form method="post" action="/family/invite/{html.escape(raw_token)}/accept">{form}</form>'''
    return family_layout("オーナー登録のご案内", body, viewer, session) if viewer else layout("オーナー登録のご案内", body)


@app.post("/family/invite/{raw_token}/accept")
def family_invite_accept(raw_token: str, request: Request, name: str = Form(""), password: str = Form(""), viewer: User | None = Depends(current_user), session: Session = Depends(db)):
    invitation = active_owner_invitation(raw_token, session)
    if not invitation:
        return HTMLResponse(layout("招待URLエラー", '<p class="error">この招待URLは期限切れ、使用済み、または取り消されています。</p>'), status_code=400)
    owner = viewer
    if owner and owner.email != invitation.email:
        return HTMLResponse(family_layout("アカウントエラー", '<p class="error">招待先とは異なるアカウントでログインしています。</p>', owner, session), status_code=403)
    if not owner:
        owner = session.scalar(select(User).where(User.email == invitation.email))
        if owner:
            if not owner.active or not password or not passwords.verify(password, owner.password_hash):
                return HTMLResponse(layout("ログインエラー", f'<p class="error">パスワードが違います。</p><a class="button secondary" href="/family/invite/{html.escape(raw_token)}">戻る</a>'), status_code=400)
        else:
            if len(password) < 8 or not name.strip():
                return HTMLResponse(layout("登録エラー", f'<p class="error">お名前と8文字以上のパスワードを入力してください。</p><a class="button secondary" href="/family/invite/{html.escape(raw_token)}">戻る</a>'), status_code=400)
            owner = User(name=name.strip(), email=invitation.email, password_hash=passwords.hash(password), role=Role.customer)
            session.add(owner)
            session.flush()
    customer = session.scalar(select(Customer).where(Customer.tenant_id == invitation.tenant_id, func.lower(Customer.email) == invitation.email).limit(1))
    ownership = session.scalar(select(DogOwnership).where(DogOwnership.tenant_id == invitation.tenant_id, DogOwnership.dog_id == invitation.dog_id, DogOwnership.user_id == owner.id))
    if ownership:
        ownership.relationship, ownership.active = invitation.relationship, True
        ownership.customer_id = customer.id if customer else ownership.customer_id
    else:
        session.add(DogOwnership(tenant_id=invitation.tenant_id, dog_id=invitation.dog_id, user_id=owner.id,
                                 customer_id=customer.id if customer else None, relationship=invitation.relationship))
    invitation.accepted_at = datetime.now(timezone.utc)
    raw_session = None
    if not viewer:
        raw_session = secrets.token_urlsafe(32)
        session.add(LoginSession(token_hash=token_hash(raw_session), user_id=owner.id, expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    session.commit()
    response = RedirectResponse("/family", status_code=303)
    if raw_session:
        response.set_cookie("dog_session", raw_session, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=SESSION_DAYS * 86400)
    return response


@app.get("/family/owners", response_class=HTMLResponse)
def family_owner_links(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(
        select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True), Dog.category != "external").order_by(Dog.call_name)
    ).all()
    dog_options = "".join(f'<option value="{dog.id}">{html.escape(dog.call_name)}（{html.escape(dog.registered_name or "血統書名未登録")}）</option>' for dog in dogs)
    records = session.execute(
        select(DogOwnership, Dog, User)
        .join(Dog, Dog.id == DogOwnership.dog_id)
        .join(User, User.id == DogOwnership.user_id)
        .where(DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))
        .order_by(Dog.call_name, User.name)
    ).all()
    rows = ""
    for ownership, dog, owner in records:
        relation = "主オーナー" if ownership.relationship == "primary" else "ご家族"
        rows += f'''<tr><td>{html.escape(dog.call_name)}</td><td>{html.escape(owner.name)}</td><td>{html.escape(owner.email)}</td><td>{relation}</td>
        <td><form class="inline" method="post" action="/family/owners/{ownership.id}/remove"><button class="secondary">連携解除</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/admin/users">ユーザー管理へ戻る</a> <a class="button success" href="/family/invitations">オーナー様を招待</a>
    <h1>{html.escape(tenant.name)} オーナー連携</h1>
    <p>オーナーが登録したメールアドレスと犬を結び付けます。1人に複数頭、ご家族に同じ犬を連携できます。</p>
    <form method="post"><label>犬</label><select name="dog_id" required>{dog_options}</select>
    <label>登録済みオーナーのメールアドレス</label><input name="email" type="email" required>
    <label>関係</label><select name="relationship"><option value="primary">主オーナー</option><option value="family">ご家族</option></select>
    <button>犬とオーナーを連携</button></form>
    <h2>現在の連携</h2><table><tr><th>犬</th><th>オーナー</th><th>メール</th><th>関係</th><th>操作</th></tr>{rows}</table>'''
    return layout("オーナー連携", body, user)


@app.post("/family/owners")
def family_owner_link_add(dog_id: int = Form(...), email: str = Form(...), relationship: str = Form("primary"), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    if relationship not in {"primary", "family"}:
        raise HTTPException(status_code=400, detail="関係の指定が正しくありません")
    dog = tenant_dog(session, tenant.id, dog_id)
    if not dog.active or dog.category == "external":
        raise HTTPException(status_code=400, detail="この犬はオーナー連携できません")
    normalized = normalize_email(email)
    owner = session.scalar(select(User).where(User.email == normalized, User.active.is_(True)))
    if not owner:
        return HTMLResponse(layout("連携エラー", '<p class="error">このメールアドレスのアカウントがありません。先にオーナー様に「お客様登録」をしていただいてください。</p><a class="button secondary" href="/family/owners">戻る</a>', user), status_code=400)
    customer = session.scalar(select(Customer).where(Customer.tenant_id == tenant.id, func.lower(Customer.email) == normalized).limit(1))
    ownership = session.scalar(select(DogOwnership).where(DogOwnership.tenant_id == tenant.id, DogOwnership.dog_id == dog.id, DogOwnership.user_id == owner.id))
    if ownership:
        ownership.relationship = relationship
        ownership.customer_id = customer.id if customer else ownership.customer_id
        ownership.active = True
    else:
        session.add(DogOwnership(tenant_id=tenant.id, dog_id=dog.id, user_id=owner.id, customer_id=customer.id if customer else None, relationship=relationship))
    session.commit()
    return RedirectResponse("/family/owners", status_code=303)


@app.post("/family/owners/{ownership_id}/remove")
def family_owner_link_remove(ownership_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    ownership = session.scalar(select(DogOwnership).where(DogOwnership.id == ownership_id, DogOwnership.tenant_id == tenant.id))
    if not ownership:
        raise HTTPException(status_code=404, detail="連携が見つかりません")
    ownership.active = False
    session.commit()
    return RedirectResponse("/family/owners", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def user_list(request: Request, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    memberships = session.scalars(select(Membership).where(Membership.tenant_id == tenant.id)).all()
    rows = ""
    for member in memberships:
        account = session.get(User, member.user_id)
        rows += f"<tr><td>{html.escape(account.name)}</td><td>{html.escape(account.email)}</td><td>{member.role.value}</td></tr>"
    body = f'<h1>{html.escape(tenant.name)}のユーザー</h1><a class="button" href="/family/owners">オーナーと犬を連携</a><form method="post"><label>登録済みユーザーのメールアドレス</label><input name="email" type="email" required><label>権限</label><select name="role"><option value="employee">従業員</option><option value="customer">お客様</option><option value="admin">管理者</option></select><button>所属を追加</button></form><table><tr><th>名前</th><th>メール</th><th>権限</th></tr>{rows}</table>'
    return layout("ユーザー管理", body, user)


@app.post("/admin/users")
def membership_add(email: str = Form(...), role: Role = Form(...), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    account = session.scalar(select(User).where(User.email == normalize_email(email)))
    if not account:
        return HTMLResponse(layout("エラー", '<p class="error">先にお客様登録またはユーザー登録をしてください。</p><a href="/admin/users">戻る</a>', user))
    member = session.scalar(select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == account.id))
    if member:
        member.role = role
    else:
        session.add(Membership(tenant_id=tenant.id, user_id=account.id, role=role))
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/health")
def health():
    return {"ok": True}


app.mount("/mcp", mcp.sse_app(mount_path="/mcp"))
