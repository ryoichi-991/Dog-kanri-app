Warning: truncated output (original token count: 193107)
Total output lines: 8544

import asyncio
import base64
import calendar
import csv
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import smtplib
import ssl
import subprocess
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from zoneinfo import ZoneInfo
from email.message import EmailMessage

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from mcp.server.fastmcp import FastMCP
from passlib.context import CryptContext
from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, and_, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, defer, mapped_column, sessionmaker

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pypdf import PdfReader
import pytesseract
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from cryptography.fernet import Fernet, InvalidToken

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
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category: Mapped[str] = mapped_column(String(50))
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    meal_amount_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    food_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    stool_condition: Mapped[str | None] = mapped_column(String(30), nullable=True)
    health_condition: Mapped[str | None] = mapped_column(String(30), nullable=True)
    physical_exam: Mapped[bool] = mapped_column(Boolean, default=False)
    blood_test: Mapped[bool] = mapped_column(Boolean, default=False)
    ultrasound: Mapped[bool] = mapped_column(Boolean, default=False)
    chest_xray: Mapped[bool] = mapped_column(Boolean, default=False)
    result_summary: Mapped[str | None] = mapped_column(String(30), nullable=True)
    next_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    attachment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attachment_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
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
    vaccine_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    dose_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clinic: Mapped[str | None] = mapped_column(String(150), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    lot_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reaction: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    certificate_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    certificate_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    certificate_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


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
    medication_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    clinic: Mapped[str | None] = mapped_column(String(150), nullable=True)
    owner_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    disease_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    recurrence: Mapped[bool] = mapped_column(Boolean, default=False)
    clinic: Mapped[str | None] = mapped_column(String(150), nullable=True)
    veterinarian: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_followup_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class HealthRecordShare(Base):
    __tablename__ = "health_record_shares"
    __table_args__ = (UniqueConstraint("record_type", "record_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    record_id: Mapped[int] = mapped_column(Integer, index=True)
    owner_visible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FoodHistory(Base):
    __tablename__ = "food_histories"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    food_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    amount_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    times_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    owner_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class OwnerHealthRecord(Base):
    __tablename__ = "owner_health_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    recorded_on: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(150))
    value: Mapped[str | None] = mapped_column(String(150), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    attachment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attachment_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    share_to_breeder: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyHealthScheduleCompletion(Base):
    __tablename__ = "family_health_schedule_completions"
    __table_args__ = (UniqueConstraint("user_id", "dog_id", "category", "title", "due_on", name="uq_family_health_schedule_completion"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    due_on: Mapped[date] = mapped_column(Date, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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
    post_group: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    photo_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyTimelineLike(Base):
    __tablename__ = "family_timeline_likes"
    __table_args__ = (UniqueConstraint("album_item_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    album_item_id: Mapped[int] = mapped_column(ForeignKey("family_dog_album_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FamilyTimelineLikeRead(Base):
    __tablename__ = "family_timeline_like_reads"
    __table_args__ = (UniqueConstraint("like_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    like_id: Mapped[int] = mapped_column(ForeignKey("family_timeline_likes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyTimelineComment(Base):
    __tablename__ = "family_timeline_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    album_item_id: Mapped[int] = mapped_column(ForeignKey("family_dog_album_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FamilyTimelineCommentRead(Base):
    __tablename__ = "family_timeline_comment_reads"
    __table_args__ = (UniqueConstraint("comment_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("family_timeline_comments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyTimelineReport(Base):
    __tablename__ = "family_timeline_reports"
    __table_args__ = (UniqueConstraint("reporter_id", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    album_item_id: Mapped[int | None] = mapped_column(ForeignKey("family_dog_album_items.id", ondelete="CASCADE"), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    reason: Mapped[str] = mapped_column(String(30))
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    admin_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FamilyUserRestriction(Base):
    __tablename__ = "family_user_restrictions"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    posting_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    likes_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    messages_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyModerationAudit(Base):
    __tablename__ = "family_moderation_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50))
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FamilyWithdrawalRequest(Base):
    __tablename__ = "family_withdrawal_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data_policy: Mapped[str] = mapped_column(String(30), default="retain")
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FamilyTermsVersion(Base):
    __tablename__ = "family_terms_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "document_type", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_type: Mapped[str] = mapped_column(String(30), index=True)
    version: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FamilyConsent(Base):
    __tablename__ = "family_consents"
    __table_args__ = (UniqueConstraint("terms_version_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    terms_version_id: Mapped[int] = mapped_column(ForeignKey("family_terms_versions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
    event_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    event_location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    event_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waitlist_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
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


class FamilyEventResponse(Base):
    __tablename__ = "family_event_responses"
    __table_args__ = (UniqueConstraint("announcement_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("family_announcements.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    dog_names: Mapped[str | None] = mapped_column(String(300), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FamilyEventReport(Base):
    __tablename__ = "family_event_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("family_announcements.id", ondelete="CASCADE"), unique=True, index=True)
    body: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyEventReportPhoto(Base):
    __tablename__ = "family_event_report_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("family_event_reports.id", ondelete="CASCADE"), index=True)
    photo_data: Mapped[bytes] = mapped_column(LargeBinary)
    photo_content_type: Mapped[str] = mapped_column(String(50), default="image/jpeg")
    photo_order: Mapped[int] = mapped_column(Integer, default=0)


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


class AccountEmailChangeAudit(Base):
    __tablename__ = "account_email_change_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    old_email: Mapped[str] = mapped_column(String(255))
    new_email: Mapped[str] = mapped_column(String(255))
    linked_customers_updated: Mapped[int] = mapped_column(Integer, default=0)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyNotificationSetting(Base):
    __tablename__ = "family_notification_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    messages: Mapped[bool] = mapped_column(Boolean, default=True)
    announcements: Mapped[bool] = mapped_column(Boolean, default=True)
    likes: Mapped[bool] = mapped_column(Boolean, default=True)
    anniversaries: Mapped[bool] = mapped_column(Boolean, default=True)
    health_vaccinations: Mapped[bool] = mapped_column(Boolean, default=True)
    health_checkups: Mapped[bool] = mapped_column(Boolean, default=True)
    health_medications: Mapped[bool] = mapped_column(Boolean, default=True)
    health_followups: Mapped[bool] = mapped_column(Boolean, default=True)
    line_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class FamilyPushSubscription(Base):
    __tablename__ = "family_push_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FamilyPushReceipt(Base):
    __tablename__ = "family_push_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class LineOfficialAccount(Base):
    __tablename__ = "line_official_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True)
    account_name: Mapped[str] = mapped_column(String(150))
    channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    channel_secret_encrypted: Mapped[str] = mapped_column(Text)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    webhook_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    bot_basic_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bot_display_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FamilyLineLink(Base):
    __tablename__ = "family_line_links"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"), UniqueConstraint("tenant_id", "line_user_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    line_user_id: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FamilyLineLinkToken(Base):
    __tablename__ = "family_line_link_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LineDelivery(Base):
    __tablename__ = "line_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FamilyBackupAudit(Base):
    __tablename__ = "family_backup_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(20), default="zip")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class MobileApiToken(Base):
    __tablename__ = "mobile_api_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(100), default="スマートフォン")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecuritySetting(Base):
    __tablename__ = "security_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuthThrottle(Base):
    __tablename__ = "auth_throttles"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OperationEvent(Base):
    __tablename__ = "operation_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    summary: Mapped[str] = mapped_column(String(300))
    details: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    recipient: Mapped[str] = mapped_column(String(255), index=True)
    purpose: Mapped[str] = mapped_column(String(50), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FamilyAnniversaryDismissal(Base):
    __tablename__ = "family_anniversary_dismissals"
    __table_args__ = (UniqueConstraint("user_id", "dog_id", "event_type", "event_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    event_date: Mapped[date] = mapped_column(Date)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def db():
    with SessionLocal() as session:
        yield session


def normalize_email(value: str) -> str:
    return value.strip().lower()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def auth_throttle_key(request: Request, scope: str, identity: str) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    address = forwarded or (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{scope}|{address}|{normalize_email(identity)}".encode()).hexdigest()


def auth_throttle_blocked(key: str, session: Session) -> bool:
    item = session.get(AuthThrottle, key)
    if not item: return False
    now = datetime.now(timezone.utc)
    blocked = item.blocked_until
    if blocked and (blocked if blocked.tzinfo else blocked.replace(tzinfo=timezone.utc)) > now:
        return True
    started = item.window_started_at if item.window_started_at.tzinfo else item.window_started_at.replace(tzinfo=timezone.utc)
    if started < now - timedelta(minutes=15):
        session.delete(item); session.commit()
    return False


def auth_throttle_failure(key: str, session: Session) -> None:
    now = datetime.now(timezone.utc); item = session.get(AuthThrottle, key)
    if not item:
        item = AuthThrottle(key_hash=key, failures=0, window_started_at=now); session.add(item)
    started = item.window_started_at if item.window_started_at.tzinfo else item.window_started_at.replace(tzinfo=timezone.utc)
    if started < now - timedelta(minutes=15): item.failures, item.window_started_at = 0, now
    item.failures += 1; item.updated_at = now
    if item.failures >= 5: item.blocked_until = now + timedelta(minutes=15)
    session.commit()


def auth_throttle_success(key: str, session: Session) -> None:
    item = session.get(AuthThrottle, key)
    if item: session.delete(item); session.commit()


def smtp_ready() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM_EMAIL"))


def send_email_content(recipient: str, subject: str, body: str) -> str | None:
    """送信成功時はNone、失敗時は安全に短縮した理由を返す。"""
    if not smtp_ready():
        return "メール配信サービスが未設定です"
    message = EmailMessage()
    message["From"] = f'{os.environ.get("SMTP_FROM_NAME", "ESTRELLA FAMILY")} <{os.environ["SMTP_FROM_EMAIL"]}>'
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    security = os.environ.get("SMTP_SECURITY", "starttls").lower()
    username, password = os.environ.get("SMTP_USERNAME"), os.environ.get("SMTP_PASSWORD")
    try:
        if security == "ssl":
            client = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(host, port, timeout=15)
            if security == "starttls":
                client.starttls(context=ssl.create_default_context())
        with client:
            if username:
                client.login(username, password or "")
            client.send_message(message)
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {str(exc)[:420]}"


def deliver_email(delivery: EmailDelivery, session: Session) -> bool:
    delivery.attempts += 1
    error = send_email_content(delivery.recipient, delivery.subject, delivery.body)
    if error:
        delivery.status, delivery.error = ("pending" if not smtp_ready() else "failed"), error
        if smtp_ready():
            record_operation(session, "email", "failed", "メール配信に失敗しました", delivery.tenant_id,
                f"delivery={delivery.id} purpose={delivery.purpose} error={error}")
        return False
    delivery.status, delivery.error, delivery.sent_at = "sent", None, datetime.now(timezone.utc)
    record_operation(session, "email", "success", "メールを配信しました", delivery.tenant_id,
        f"delivery={delivery.id} purpose={delivery.purpose}")
    return True


def queue_email(session: Session, recipient: str, purpose: str, subject: str, body: str, tenant_id: int | None = None, user_id: int | None = None, dedupe_key: str | None = None) -> EmailDelivery | None:
    if dedupe_key and session.scalar(select(EmailDelivery.id).where(EmailDelivery.dedupe_key == dedupe_key)):
        return None
    delivery = EmailDelivery(tenant_id=tenant_id, user_id=user_id, recipient=normalize_email(recipient), purpose=purpose,
                             subject=subject[:200], body=body, dedupe_key=dedupe_key)
    session.add(delivery)
    session.flush()
    deliver_email(delivery, session)
    return delivery


def email_notification_allowed(user: User, category: str, session: Session) -> bool:
    setting = family_notification_setting(user, session)
    return bool(setting.email_enabled and getattr(setting, category, False))


def line_cipher() -> Fernet | None:
    raw_key = os.environ.get("LINE_CREDENTIALS_KEY", "").strip().encode()
    try:
        return Fernet(raw_key) if raw_key else None
    except (ValueError, TypeError):
        return None


def line_encrypt(value: str) -> str:
    cipher = line_cipher()
    if not cipher:
        raise HTTPException(status_code=503, detail="LINE認証情報の暗号鍵が設定されていません")
    return cipher.encrypt(value.encode()).decode()


def line_decrypt(value: str) -> str:
    cipher = line_cipher()
    if not cipher:
        raise RuntimeError("LINE credentials key is unavailable")
    try:
        return cipher.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("LINE credentials could not be decrypted") from exc


def line_reply(account: LineOfficialAccount, reply_token: str, message: str) -> bool:
    try:
        access_token = line_decrypt(account.access_token_encrypted)
        payload = json.dumps({"replyToken": reply_token, "messages": [{"type": "text", "text": message[:5000]}]}, ensure_ascii=False).encode()
        request = UrlRequest("https://api.line.me/v2/bot/message/reply", data=payload, method="POST", headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, RuntimeError, TimeoutError):
        return False


def line_bot_info(account: LineOfficialAccount) -> tuple[dict[str, str] | None, str | None]:
    try:
        access_token = line_decrypt(account.access_token_encrypted)
        request = UrlRequest("https://api.line.me/v2/bot/info", method="GET", headers={"Authorization": f"Bearer {access_token}"})
        with urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                return None, f"LINE API status {response.status}"
            payload = json.loads(response.read())
        return {"displayName": str(payload.get("displayName", ""))[:150], "basicId": str(payload.get("basicId", ""))[:100]}, None
    except HTTPError as exc:
        return None, f"LINE API status {exc.code}"
    except (URLError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def send_line_push(user_id: int, tenant_id: int, category: str, message: str, url: str, dedupe_key: str, session: Session) -> bool:
    setting = session.scalar(select(FamilyNotificationSetting).where(FamilyNotificationSetting.user_id == user_id))
    account = session.scalar(select(LineOfficialAccount).where(LineOfficialAccount.tenant_id == tenant_id, LineOfficialAccount.active.is_(True)))
    link = session.scalar(select(FamilyLineLink).where(FamilyLineLink.tenant_id == tenant_id, FamilyLineLink.user_id == user_id, FamilyLineLink.active.is_(True)))
    if not setting or not setting.line_enabled or not account or not link:
        return False
    delivery = session.scalar(select(LineDelivery).where(LineDelivery.dedupe_key == dedupe_key))
    if delivery and delivery.status == "sent":
        return False
    if not delivery:
        delivery = LineDelivery(tenant_id=tenant_id, user_id=user_id, category=category[:40], dedupe_key=dedupe_key[:200],
                                message=message[:5000], target_url=url[:500])
        session.add(delivery); session.flush()
    else:
        delivery.message, delivery.target_url = message[:5000], url[:500]
    delivery.attempts = (delivery.attempts or 0) + 1
    try:
        access_token = line_decrypt(account.access_token_encrypted)
        full_url = f"{os.environ.get('APP_BASE_URL', 'https://dog-management.benefit-navi.com').rstrip('/')}{url}"
        text_body = f"{message}\n\n詳細を確認する\n{full_url}"[:5000]
        payload = json.dumps({"to": link.line_user_id, "messages": [{"type": "text", "text": text_body}]}, ensure_ascii=False).encode()
        request = UrlRequest("https://api.line.me/v2/bot/message/push", data=payload, method="POST", headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"LINE API status {response.status}")
        delivery.status, delivery.error, delivery.sent_at = "sent", None, datetime.now(timezone.utc)
        record_operation(session, "line", "success", "LINE通知を配信しました", tenant_id, f"user={user_id} category={category}")
        return True
    except (HTTPError, URLError, RuntimeError, TimeoutError) as exc:
        delivery.status, delivery.error = "failed", f"{type(exc).__name__}: {str(exc)[:420]}"
        record_operation(session, "line", "failed", "LINE通知の配信に失敗しました", tenant_id, f"user={user_id} category={category} error={type(exc).__name__}")
        return False


VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "")


def ensure_vapid_keys(session: Session) -> None:
    """環境変数がない場合だけ、DBへ永続化したP-256鍵を再利用する。"""
    global VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT
    if VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_SUBJECT:
        return
    stored = {item.key: item.value for item in session.scalars(select(SecuritySetting).where(
        SecuritySetting.key.in_(["vapid_public_key", "vapid_private_key", "vapid_subject"]))).all()}
    if not stored.get("vapid_public_key") or not stored.get("vapid_private_key"):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        private = ec.generate_private_key(ec.SECP256R1())
        private_der = private.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        public_point = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        stored["vapid_private_key"] = base64.urlsafe_b64encode(private_der).decode("ascii")
        stored["vapid_public_key"] = base64.urlsafe_b64encode(public_point).rstrip(b"=").decode("ascii")
    stored.setdefault("vapid_subject", f'mailto:{os.environ.get("SMTP_FROM_EMAIL", "admin@benefit-navi.com")}')
    for key, value in stored.items():
        item = session.get(SecuritySetting, key)
        if item: item.value, item.updated_at = value, datetime.now(timezone.utc)
        else: session.add(SecuritySetting(key=key, value=value))
    session.commit()
    VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT = stored["vapid_public_key"], stored["vapid_private_key"], stored["vapid_subject"]


def push_ready() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_SUBJECT)


def record_operation(session: Session, category: str, status_value: str, summary: str,
                     tenant_id: int | None = None, details: str | None = None) -> None:
    session.add(OperationEvent(tenant_id=tenant_id, category=category[:40], status=status_value[:20],
        summary=summary[:300], details=(details or "")[:1000] or None))


def send_web_push(user_id: int, category: str, title: str, body: str, url: str, dedupe_key: str, session: Session) -> int:
    setting = session.scalar(select(FamilyNotificationSetting).where(FamilyNotificationSetting.user_id == user_id))
    if not setting or not setting.push_enabled or not getattr(setting, category, False) or not push_ready():
        return 0
    if session.scalar(select(FamilyPushReceipt.id).where(FamilyPushReceipt.dedupe_key == dedupe_key)):
        return 0
    receipt = FamilyPushReceipt(user_id=user_id, dedupe_key=dedupe_key)
    session.add(receipt); session.flush()
    try:
        from pywebpush import webpush
    except ImportError:
        receipt.status = "unavailable"
        return 0
    sent = 0
    payload = json.dumps({"title": title[:120], "body": body[:300], "url": url}, ensure_ascii=False)
    subscriptions = session.scalars(select(FamilyPushSubscription).where(
        FamilyPushSubscription.user_id == user_id, FamilyPushSubscription.active.is_(True))).all()
    for subscription in subscriptions:
        try:
            webpush(subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
                    data=payload, vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_SUBJECT}, ttl=86400)
            subscription.last_success_at = datetime.now(timezone.utc); sent += 1
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None and getattr(response, "status_code", 0) in {404, 410}:
                subscription.active = False
            record_operation(session, "push", "failed", "ブラウザ通知の配信に失敗しました",
                details=f"user={user_id} endpoint_id={subscription.id} error={type(exc).__name__}")
    receipt.status = "sent" if sent else "failed"
    if sent:
        record_operation(session, "push", "success", f"ブラウザ通知を{sent}端末へ配信しました",
            details=f"user={user_id} category={category}")
    return sent


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


def page_usage_guide(title: str) -> str:
    """ログイン後の全画面と今後追加する画面へ、共通形式の操作説明を自動表示する。"""
    page_name = title.split("｜", 1)[0].strip()
    guides = [
        (("ホーム",), ["犬舎全体の登録状況と、優先して対応する予定を確認できます。", "期限超過・本日・7日以内の業務から各管理画面へ直接移動できます。"], ["要対応サマリーで期限超過がないか確認します。", "本日と7日以内の予定を優先度順に確認します。", "予定名またはクイック操作から対象画面を開きます。"], "表示内容は選択中の会社・犬舎だけに限定されます。作業前に画面上部の選択先を確認してください。"),
        (("カレンダー",), ["Todo、繁殖、健康、販売、法令の予定を1か所で確認できます。", "月・分類・状態で絞り込み、期限超過を早く見つけられます。"], ["表示する月を選びます。", "必要に応じて分類と状態を指定します。", "予定名を選び、元の管理画面で内容を確認・更新します。"], "自動表示される予測日は目安です。交配・出産・医療・行政の確定日は原記録で確認してください。"),
        (("通知配信履歴",), ["LINE・メール・ブラウザの配信結果をまとめて確認できます。", "条件検索、失敗通知の再送、CSV・PDF出力ができます。"], ["検索条件を指定して履歴を絞り込みます。", "失敗理由を確認し、設定修正後に必要な通知だけ再送します。", "必要に応じて表示条件のまま帳票を出力します。"], "再送はオーナーへ実際に通知されます。宛先と内容を確認してから操作してください。"),
        (("LINE公式", "LINE連携"), ["LINE公式アカウントの接続状態とオーナー連携を確認できます。", "接続診断、テスト通知、配信履歴の確認ができます。"], ["接続状態と最終Webhook受信日時を確認します。", "オーナーの連携状態を確認します。", "必要な場合だけテスト通知を実行します。"], "Channel secretやアクセストークンは第三者へ共有しないでください。"),
        (("健康", "体重", "ワクチン", "健診", "投薬", "病歴", "フード"), ["愛犬の健康記録、予定、共有データを確認・登録できます。", "検索、実施済み管理、カレンダー表示、帳票出力ができます。"], ["対象犬と健康カテゴリーを確認します。", "日付と内容を入力して記録します。", "必要な記録だけブリーダーまたはオーナーへ共有します。"], "健康記録は診断書ではありません。緊急時や判断に迷う場合は獣医師へ相談してください。"),
        (("ヒート", "交配", "遺伝子", "血統"), ["ヒート、交配計画、血統情報、遺伝子検査を管理できます。", "組み合わせの検討や近親交配分析に利用できます。"], ["対象犬と登録済み情報を確認します。", "日付・相手犬・検査結果などを入力します。", "分析結果と原資料を照合して計画を確定します。"], "自動計算や提案は判断材料です。血統書原本と獣医師・専門家の確認を優先してください。"),
        (("出産", "仔犬"), ["出産予定、出産記録、仔犬情報を登録・確認できます。", "母犬別の出産状況と仔犬の管理に利用できます。"], ["母犬と対象の出産記録を選びます。", "日付、頭数、仔犬情報を登録します。", "販売・健康・血統情報へ正しく連携されたか確認します。"], "出生数や個体の取り違えを防ぐため、登録後に母犬と日付を再確認してください。"),
        (("犬・血統書", "犬一覧", "在籍犬", "親犬", "販売犬", "譲渡済", "外部犬"), ["犬の基本情報、在籍区分、写真、血統書を管理できます。", "親犬・仔犬・販売犬・譲渡済犬などの状態を確認できます。"], ["対象犬を検索または一覧から選びます。", "登録・編集画面で必要項目を入力します。", "保存後に名前、性別、生年月日、在籍状態を確認します。"], "販売・譲渡・死亡などの状態変更は、一覧表示や帳票に影響します。対象犬を確認して操作してください。"),
        (("販売", "顧客", "商談", "契約", "引渡"), ["顧客、商談、契約、販売・引渡し状況を管理できます。", "進捗確認と必要書類の作成・出力に利用できます。"], ["顧客と対象犬を確認します。", "商談や契約の進捗を入力します。", "引渡し前に契約内容と必要書類を確認します。"], "個人情報を含むため、閲覧・出力したデータの取扱いに注意してください。"),
        (("法令", "行政", "帳簿", "届出"), ["動物取扱業に必要な記録や行政書類を確認・作成できます。", "登録情報をもとに帳票を出力できます。"], ["対象期間と提出先を確認します。", "不足している情報を登録します。", "出力後に原簿・提出要領と照合します。"], "自治体ごとに様式や提出要件が異なる場合があります。提出前に管轄行政機関へ確認してください。"),
        (("FAMILY", "オーナー", "メッセージ", "タイムライン", "お知らせ"), ["オーナーとの連携、情報共有、交流機能を管理できます。", "お知らせ、メッセージ、投稿、利用状況を確認できます。"], ["対象のオーナーまたは愛犬を確認します。", "公開範囲と通知先を確認して内容を登録します。", "送信・公開後の表示を確認します。"], "メッセージや投稿には個人情報・非公開情報を記載しすぎないよう注意してください。"),
        (("バックアップ", "データ出力"), ["犬舎データの出力、バックアップ、整合性確認ができます。", "保管や障害時の復旧準備に利用できます。"], ["出力対象と形式を確認します。", "ファイルを作成し、安全な場所へ保管します。", "定期的に検証機能でファイルの整合性を確認します。"], "出力ファイルには個人情報が含まれます。共有先と保管場所を限定してください。"),
    ]
    abilities = [f"「{page_name}」に関する情報を確認できます。", "表示されている入力欄やボタンから、権限に応じた登録・検索・変更ができます。"]
    steps = ["画面の対象と現在の状態を確認します。", "必要な項目を入力または選択して操作します。", "完了メッセージと更新後の内容を確認します。"]
    caution = "操作できる内容はアカウント権限により異なります。重要な変更は対象と内容を確認してから実行してください。"
    for keywords, specific_abilities, specific_steps, specific_caution in guides:
        if any(keyword in page_name for keyword in keywords):
            abilities, steps, caution = specific_abilities, specific_steps, specific_caution
            break
    ability_items = "".join(f"<li>{html.escape(item)}</li>" for item in abilities)
    step_items = "".join(f"<li>{html.escape(item)}</li>" for item in steps)
    return f'''<details class="page-guide"><summary>この画面の使い方を見る</summary><div class="page-guide-grid"><section><h3>この画面でできること</h3><ul>{ability_items}</ul></section><section><h3>基本的な使い方</h3><ol>{step_items}</ol></section><section><h3>操作上の注意</h3><p>{html.escape(caution)}</p></section></div></details>'''


def layout(title: str, body: str, user: User | None = None, owner_mode: bool = False, notification_count: int = 0) -> str:
    nav = ""
    body_class = "owner-view" if user and owner_mode else ("authenticated" if user else "guest")
    if user and owner_mode:
        notification_badge = f'<span class="nav-count">{notification_count}</span>' if notification_count else ""
        nav = f'''<aside class="owner-header"><a class="owner-brand" href="/family"><strong>ESTRELLA</strong><small>FAMILY</small></a>
        <nav><p class="owner-nav-label">ホーム</p><a href="/family"><span>⌂</span>うちの子</a><a href="/family/notifications"><span>●</span>通知{notification_badge}</a>
        <p class="owner-nav-label">交流</p><a href="/family/messages"><span>✉</span>メッセージ</a><a href="/family/announcements"><span>◇</span>お知らせ</a><a href="/family/timeline"><span>▦</span>タイムライン</a><a href="/family/anniversaries"><span>♡</span>記念日</a><a href="/family/relatives"><span>♢</span>兄弟・親戚犬</a><a href="/family/kennel"><span>♧</span>犬舎FAMILY会</a>
        <p class="owner-nav-label">設定</p><a href="/family/profile"><span>♙</span>プロフィール設定</a><a href="/family/notification-settings"><span>●</span>通知設定</a><a href="/family/line"><span>LINE</span>LINE連携</a><a href="/family/consents"><span>✓</span>規約・同意</a><a href="/family/devices"><span>▣</span>アプリ・端末</a><a href="/family/account"><span>↪</span>退会・引継ぎ</a></nav>
        <div class="owner-account"><span>{html.escape(user.name)}</span><form method="post" action="/logout"><button>ログアウト</button></form></div></aside>'''
    elif user:
        platform_link = '<a href="/platform/tenants"><span>◆</span>テナント管理</a>' if user.platform_admin else ""
        nav = f'''<aside class="sidebar">
        <a class="brand" href="/dashboard"><span class="brand-logo-wrap"><img class="brand-logo" src="https://estrella.dog/wp-content/uploads/2025/10/logo-1.svg" alt="ESTRELLA ロゴ"></span><span><strong>ESTRELLA</strong><small>Breeder Management</small></span></a>
        <nav aria-label="管理メニュー">
          <a class="nav-home" href="/dashboard"><span>⌂</span>管理画面TOP</a>
          <details class="nav-group" data-nav-group="daily"><summary><span>▦</span>日常業務</summary><div class="nav-group-links">
            <a href="/family"><span>♢</span>FAMILY</a><a href="/modules/todo"><span>✓</span>Todoリスト</a><a href="/modules/calendar"><span>▦</span>カレンダー</a>
          </div></details>
          <details class="nav-group" data-nav-group="dogs"><summary><span>🐕</span>犬の管理</summary><div class="nav-group-links">
            <a href="/modules/resident-dogs"><span>🐕</span>在籍犬一覧</a><a href="/modules/dog-list/puppy"><span>◌</span>仔犬一覧</a><a href="/modules/sale-dogs"><span>¥</span>販売犬一覧</a><a href="/modules/transferred-dogs"><span>↗</span>譲渡済一覧</a><a href="/modules/dog-list/parent"><span>♙</span>親犬一覧</a><a href="/modules/dog-list/external"><span>◇</span>外部犬一覧</a>
          </div></details>
          <details class="nav-group" data-nav-group="breeding"><summary><span>♡</span>繁殖と血統</summary><div class="nav-group-links">
            <a href="/modules/breeding"><span>♡</span>ヒート・交配管理</a><a href="/modules/births"><span>✦</span>出産管理</a><a href="/modules/genetics"><span>⌘</span>遺伝子・交配分析</a><a href="/modules/dogs"><span>●</span>犬・血統書管理</a>
          </div></details>
          <details class="nav-group" data-nav-group="business"><summary><span>＋</span>健康と販売</summary><div class="nav-group-links">
            <a href="/modules/health"><span>＋</span>健康管理</a><a href="/modules/sales"><span>¥</span>販売管理</a><a href="/modules/legal"><span>▤</span>法令・行政書類</a>
          </div></details>
          <details class="nav-group" data-nav-group="family-admin"><summary><span>♢</span>FAMILY管理</summary><div class="nav-group-links">
            <a href="/family/announcements/manage"><span>◇</span>FAMILYお知らせ</a><a href="/family/messages/manage"><span>✉</span>メッセージ管理</a><a href="/family/timeline/comments/manage"><span>💬</span>コメント管理</a><a href="/family/timeline/reports/manage"><span>!</span>タイムライン通報</a><a href="/family/safety/reports/manage"><span>⚑</span>プロフィール・メッセージ通報</a><a href="/family/restrictions/manage"><span>⊘</span>FAMILY利用停止</a><a href="/family/dashboard/manage"><span>▥</span>FAMILY集計</a><a href="/family/withdrawals/manage"><span>↪</span>退会申請</a><a href="/family/terms/manage"><span>✓</span>規約・同意管理</a><a href="/family/line/manage"><span>LINE</span>LINE公式設定</a><a href="/family/backups/manage"><span>⇩</span>データ出力</a>
          </div></details>
          <details class="nav-group" data-nav-group="system"><summary><span>⚙</span>システム設定</summary><div class="nav-group-links">
            <a href="/admin/users"><span>♙</span>ユーザー管理</a><a href="/admin/password-resets"><span>⌁</span>パスワード再設定</a><a href="/admin/notification-deliveries"><span>●</span>通知配信履歴</a><a href="/admin/email-deliveries"><span>✉</span>メール送信履歴</a><a href="/admin/operations"><span>◉</span>運用監視</a>{platform_link}
          </div></details>
        </nav>
        <div class="sidebar-user"><div class="avatar">{html.escape(user.name[:1])}</div><div><strong>{html.escape(user.name)}</strong><small>{"運営管理者" if user.platform_admin else "ユーザー"}</small></div><form method="post" action="/logout"><button title="ログアウト">↪</button></form></div>
        </aside>'''
    content = body
    if user and 'class="page-guide"' not in content:
        guide = page_usage_guide(title)
        heading_end = content.find("</h1>")
        content = content[:heading_end + 5] + guide + content[heading_end + 5:] if heading_end >= 0 else guide + content
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--wine:#704454;--rose:#b66f7c;--rose-light:#ead0d5;--cream:#faf6f3;--paper:#fffdfb;--ink:#3f3036;--muted:#816f76;--line:#eadfe1;--green:#718b75;--danger:#a94f55}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--cream);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;line-height:1.55}}.sidebar{{position:fixed;inset:0 auto 0 0;width:260px;background:linear-gradient(180deg,#68404f 0%,#55333f 100%);color:#fff;display:flex;flex-direction:column;z-index:10;box-shadow:6px 0 24px #4b26331a}}.brand{{height:84px;display:flex;align-items:center;gap:13px;padding:18px 22px;color:#fff;text-decoration:none;border-bottom:1px solid #ffffff1f}}.brand-mark{{display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:#f0d8dc;color:var(--wine);font-family:Georgia,serif;font-size:25px}}.brand strong{{display:block;letter-spacing:1.8px;font-family:Georgia,serif}}.brand small,.sidebar-user small{{display:block;color:#ead5da;font-size:11px}}.sidebar nav{{padding:12px 13px;overflow-y:auto;flex:1}}.sidebar nav a{{display:flex;align-items:center;gap:12px;color:#f8eef1;text-decoration:none;padding:10px 13px;border-radius:10px;font-size:14px;margin:2px 0}}.sidebar nav a:hover,.sidebar nav a.active{{background:#ffffff1c;color:#fff}}.sidebar nav a span{{width:20px;text-align:center;color:#eac3cb}}.nav-home{{font-weight:750;border-bottom:1px solid #ffffff1c;margin-bottom:10px!important}}.nav-group{{margin:5px 0;border:1px solid #ffffff16;border-radius:11px;overflow:hidden;background:#ffffff06}}.nav-group summary{{display:flex;align-items:center;gap:11px;padding:11px 13px;cursor:pointer;list-style:none;font-size:14px;font-weight:700;color:#fff;user-select:none}}.nav-group summary::-webkit-details-marker{{display:none}}.nav-group summary:after{{content:"＋";margin-left:auto;color:#dfc5cb;font-size:15px}}.nav-group[open] summary{{background:#ffffff12}}.nav-group[open] summary:after{{content:"−"}}.nav-group summary>span{{width:20px;text-align:center;color:#eac3cb}}.nav-group-links{{padding:4px 6px 7px;background:#321e2638}}.sidebar .nav-group-links a{{padding:8px 10px;font-size:13px}}.nav-label{{margin:14px 12px 5px;color:#cbaeb5;font-size:10px;letter-spacing:1.5px;font-weight:700}}.sidebar-user{{display:flex;align-items:center;gap:10px;padding:15px;border-top:1px solid #ffffff1f;background:#452934}}.sidebar-user .avatar{{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:#e7c6cc;color:var(--wine);font-weight:700}}.sidebar-user strong{{display:block;max-width:125px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}}.sidebar-user form{{margin-left:auto}}.sidebar-user button{{margin:0;padding:8px;background:transparent;color:#fff;font-size:18px}}main{{max-width:1280px;margin-left:260px;padding:38px 42px}}.card{{background:var(--paper);padding:34px;border:1px solid #f1e7e8;border-radius:20px;box-shadow:0 10px 35px #63404c0d}}h1{{margin:0 0 22px;font-size:28px;letter-spacing:.02em}}h2{{margin-top:34px;padding-bottom:8px;border-bottom:1px solid var(--line);font-size:20px}}label{{display:block;margin:15px 0 6px;font-size:13px;font-weight:650;color:#665159}}input,select,textarea{{width:100%;padding:11px 13px;border:1px solid #dacdd0;border-radius:10px;background:#fff;font-size:15px;color:var(--ink);outline:none}}input:focus,select:focus,textarea:focus{{border-color:var(--rose);box-shadow:0 0 0 3px #b66f7c18}}textarea{{min-height:84px;resize:vertical}}button,.button{{display:inline-block;margin-top:17px;padding:11px 18px;border:0;border-radius:10px;background:var(--rose);color:#fff;text-decoration:none;font-weight:650;cursor:pointer;box-shadow:0 4px 12px #b66f7c28}}button:hover,.button:hover{{filter:brightness(.95)}}.secondary{{background:#89747b}}.danger{{background:var(--danger)}}.success{{background:var(--green)}}.inline{{display:inline}}.inline button{{margin:3px;padding:7px 10px;font-size:12px}}.error{{background:#fff0f0;color:#963c43;padding:13px;border-left:4px solid var(--danger);border-radius:8px}}table{{width:100%;border-collapse:separate;border-spacing:0;margin-top:18px;font-size:14px;overflow:hidden}}th{{background:#f6edef;color:#694d57;font-size:12px;letter-spacing:.03em}}th,td{{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line)}}tr:hover td{{background:#fdf8f8}}.badge{{display:inline-block;padding:5px 10px;border-radius:99px;background:var(--rose-light);color:var(--wine);font-size:12px;font-weight:700}}.tenant{{padding:18px;background:#f7edef;border:1px solid #ecdadd;border-radius:14px;margin-bottom:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:18px}}.module{{position:relative;display:block;min-height:118px;padding:21px;border:1px solid var(--line);border-radius:15px;text-decoration:none;color:var(--ink);background:linear-gradient(145deg,#fff 0%,#fdf8f7 100%);transition:.2s}}.module:after{{content:"›";position:absolute;right:18px;top:15px;color:#c18a94;font-size:24px}}.module:hover{{transform:translateY(-2px);border-color:#d6a7af;box-shadow:0 9px 22px #70445414}}.module h3{{margin:0 25px 9px 0;font-size:17px;color:#66404e}}.module p{{margin:0;color:var(--muted);font-size:13px}}
.brand-logo-wrap{{width:48px;height:48px;flex:0 0 48px;overflow:hidden;display:grid;place-items:center}}.brand-logo{{display:block;width:48px;height:48px;object-fit:contain}}.title-crown{{display:inline-flex;align-items:center;gap:2px;margin:2px 5px 2px 0;font-size:20px;font-weight:800}}.title-crown small{{font-size:9px;color:var(--ink)}}.crown-silver{{color:#9da3aa;text-shadow:0 1px #fff}}.crown-gold{{color:#d4a72c;text-shadow:0 1px #fff}}.crown-rose{{color:#cf788b}}.crown-purple{{color:#9167a8}}.crown-blue{{color:#668caf}}.guest main{{max-width:760px;margin:45px auto;padding:24px}}
.owner-header{{position:fixed;inset:0 auto 0 0;z-index:20;width:260px;padding:0;background:linear-gradient(180deg,#68404f 0%,#55333f 100%);color:#fff;display:flex;flex-direction:column;box-shadow:6px 0 24px #4b263326}}.owner-brand{{min-height:92px;padding:23px 24px;color:#fff;text-decoration:none;font-family:Georgia,serif;letter-spacing:1.5px;white-space:nowrap;border-bottom:1px solid #ffffff1f;display:flex;flex-direction:column;justify-content:center}}.owner-brand strong{{font-size:19px}}.owner-brand small{{color:#e8d2d7;font-size:12px;letter-spacing:3px}}.owner-header nav{{display:block;flex:1;padding:12px 13px;overflow-y:auto}}.owner-header nav a{{display:flex;align-items:center;gap:11px;color:#f8eef1;text-decoration:none;padding:10px 13px;border-radius:10px;margin:2px 0;font-size:14px;white-space:nowrap}}.owner-header nav a span{{width:20px;text-align:center;color:#eac3cb}}.owner-header nav a:hover{{background:#ffffff17;color:#fff}}.owner-nav-label{{margin:15px 12px 5px;color:#cbaeb5;font-size:10px;letter-spacing:1.5px;font-weight:700}}.owner-account{{display:flex;align-items:center;gap:10px;padding:16px;background:#452934;border-top:1px solid #ffffff1f;font-size:13px}}.owner-account>span{{min-width:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.owner-account form{{margin:0}}.owner-account button{{margin:0;padding:8px 11px;background:#ffffff1c;box-shadow:none;font-size:12px}}.owner-view main{{margin:0 0 0 260px;max-width:none;padding:38px 42px}}.owner-view main>.card{{max-width:1180px;margin:0 auto}}
.nav-count{{display:inline-grid;place-items:center;min-width:19px;height:19px;margin-left:4px;padding:0 5px;border-radius:10px;background:#fff;color:var(--wine);font-size:11px;font-weight:800}}.notification-item{{display:block;margin:12px 0;padding:18px;border:1px solid var(--line);border-radius:14px;background:#fff;color:var(--ink);text-decoration:none}}.notification-item.unread{{border-left:5px solid var(--rose);background:#fffafb}}.notification-item p{{margin:5px 0}}.notification-kind{{display:inline-block;margin-right:7px;color:var(--wine);font-size:12px;font-weight:750}}
.timeline-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:22px 0}}.timeline-tile{{position:relative;display:block;aspect-ratio:1;overflow:hidden;background:#f1e7e9;color:#fff;text-decoration:none}}.timeline-tile img{{display:block;width:100%;height:100%;object-fit:cover;transition:transform .2s ease}}.timeline-tile:hover img{{transform:scale(1.025)}}.timeline-overlay{{position:absolute;inset:auto 0 0;padding:28px 10px 8px;background:linear-gradient(transparent,#2d1924cc);font-size:12px}}.timeline-overlay strong{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.timeline-stats{{display:flex;justify-content:space-between;gap:6px;margin-top:2px;font-size:11px}}
.family-photo-stage{{width:100%;min-height:260px;max-height:70vh;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:18px;background:linear-gradient(145deg,#f7edef,#fff);border:1px solid var(--line);margin-bottom:18px}}.family-dog-photo{{display:block;max-width:100%;max-height:70vh;width:auto;height:auto;object-fit:contain}}.family-dog-thumb{{display:block;width:100%;height:190px;object-fit:contain;border-radius:12px;margin-bottom:12px;background:#f7edef}}
.family-home-grid{{display:grid;gap:18px;margin-top:18px}}.family-home-card{{display:grid;grid-template-columns:minmax(260px,340px) 1fr;min-height:260px;padding:0;overflow:hidden;border:1px solid var(--line);border-radius:18px;text-decoration:none;color:var(--ink);background:#fff;box-shadow:0 8px 24px #7044540d;transition:.2s}}.family-home-card:hover{{transform:translateY(-2px);border-color:#d6a7af;box-shadow:0 12px 28px #70445418}}.family-home-photo{{display:flex;align-items:center;justify-content:center;min-height:260px;padding:14px;background:linear-gradient(145deg,#f3e7e9,#fbf5f4)}}.family-home-photo img{{display:block;width:100%;height:232px;object-fit:contain;border-radius:12px}}.family-home-photo-empty{{font-family:Georgia,serif;font-size:72px;color:#c59aa3}}.family-home-info{{display:flex;flex-direction:column;justify-content:center;padding:30px 34px}}.family-home-info h3{{margin:0 0 12px;font-size:25px;color:var(--wine)}}.family-home-info p{{margin:5px 0;color:var(--muted)}}.family-home-info .registered-name{{color:var(--ink);font-weight:650}}.family-home-info .badge{{align-self:flex-start;margin-top:12px}}.family-home-more{{margin-top:18px;color:var(--rose);font-weight:700}}
.album-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;margin:18px 0}}.album-item{{overflow:hidden;border:1px solid var(--line);border-radius:15px;background:#fff}}.album-item a{{display:flex;height:210px;align-items:center;justify-content:center;background:#f7edef}}.album-item img{{display:block;max-width:100%;max-height:210px;width:auto;height:auto;object-fit:contain}}.album-meta{{padding:13px}}.album-meta p{{margin:5px 0}}.album-meta form button{{margin-top:8px}}
.page-guide{{margin:14px 0 24px;border:1px solid #decbd0;border-radius:14px;background:#fffafa;overflow:hidden}}.page-guide summary{{padding:14px 17px;cursor:pointer;color:var(--wine);font-weight:750;list-style:none}}.page-guide summary::-webkit-details-marker{{display:none}}.page-guide summary:after{{content:"＋";float:right;font-size:18px}}.page-guide[open] summary{{border-bottom:1px solid var(--line);background:#f8edef}}.page-guide[open] summary:after{{content:"−"}}.page-guide-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:16px}}.page-guide-grid section{{padding:12px 14px;border-radius:11px;background:#fff}}.page-guide-grid h3{{margin:0 0 8px;color:var(--wine);font-size:14px}}.page-guide-grid ul,.page-guide-grid ol{{margin:0;padding-left:20px}}.page-guide-grid li,.page-guide-grid p{{margin:5px 0;font-size:13px;color:#665159}}
.calendar-mobile-only{{display:none}}.calendar-mobile-card{{padding:15px;border:1px solid var(--line);border-radius:14px;background:#fff;margin:10px 0}}.calendar-mobile-card h3{{margin:0 0 7px;font-size:16px}}.calendar-mobile-card p{{margin:4px 0}}
.priority-list{{display:grid;gap:8px;margin:16px 0}}.priority-item{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px;border:1px solid var(--line);border-radius:12px;background:#fff;color:var(--ink);text-decoration:none}}.priority-item:hover{{border-color:#d6a7af;background:#fffafa}}.priority-item span:first-child{{display:grid;gap:3px}}.priority-item small{{color:var(--muted)}}
.health-mobile-only{{display:none}}.health-toolbar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}.health-toolbar .button{{margin-top:0}}.health-mobile-card{{padding:15px;border:1px solid var(--line);border-radius:14px;background:#fff;margin:10px 0}}.health-mobile-card h3{{margin:0 0 7px;color:var(--wine);font-size:16px}}.health-mobile-card p{{margin:4px 0}}.health-mobile-card form button{{width:100%;min-height:46px;margin-top:12px}}.health-entry-form{{padding:18px;border:1px solid var(--line);border-radius:15px;background:#fffafb}}
@media(max-width:950px){{.timeline-grid{{grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}}}}
@media(max-width:850px){{.sidebar{{position:relative;width:100%;height:auto}}.sidebar nav{{display:block}}.sidebar .nav-group-links{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px}}.nav-home{{min-height:44px}}.sidebar-user{{display:none}}main{{margin-left:0;padding:20px 14px}}.card{{padding:22px}}.page-guide-grid{{grid-template-columns:1fr}}.brand{{height:70px}}.owner-header{{position:relative;inset:auto;width:100%;display:block;padding:14px;box-shadow:0 5px 20px #4b263326}}.owner-brand{{min-height:42px;padding:2px 4px;border:0;display:block}}.owner-brand strong{{font-size:16px}}.owner-brand small{{display:inline;margin-left:5px}}.owner-header nav{{display:grid;grid-template-columns:repeat(2,1fr);gap:3px;margin-top:10px;padding:0;overflow:visible}}.owner-nav-label{{grid-column:1/-1;margin:10px 4px 2px}}.owner-header nav a{{padding:8px 6px;text-align:left;font-size:12px;margin:0}}.owner-account{{position:absolute;right:12px;top:9px;padding:0;background:transparent;border:0}}.owner-account>span{{display:none}}.owner-account button{{font-size:11px;padding:6px 8px}}.owner-view main{{margin-left:0;padding:15px 10px}}.family-home-card{{grid-template-columns:1fr}}.family-home-photo{{min-height:220px}}.family-home-photo img{{height:220px}}.family-home-info{{padding:22px}}.family-home-info h3{{font-size:22px}}.timeline-grid{{gap:3px;margin-left:-10px;margin-right:-10px}}.timeline-overlay{{padding:20px 6px 5px;font-size:10px}}.timeline-stats{{font-size:9px}}}}
@media(max-width:700px){{.owner-view main{{padding:8px 0}}.owner-view main>.card{{padding:18px 14px;border-radius:0;border-left:0;border-right:0}}h1{{font-size:23px;line-height:1.35}}h2{{font-size:18px}}input,select,textarea{{font-size:16px;min-height:46px}}button,.button{{min-height:44px;padding:11px 14px}}.health-desktop-only,.calendar-desktop-only{{display:none!important}}.health-mobile-only,.calendar-mobile-only{{display:block}}.health-toolbar{{display:grid;grid-template-columns:1fr 1fr;gap:7px}}.health-toolbar .button{{display:flex;align-items:center;justify-content:center;text-align:center;font-size:12px;min-height:48px;padding:8px}}.priority-item{{align-items:flex-start;flex-direction:column}}.priority-item .badge{{align-self:flex-start}}.health-entry-form{{margin-left:-5px;margin-right:-5px;padding:15px 12px}}.health-entry-form>.grid{{grid-template-columns:1fr;gap:4px}}.health-entry-form>button{{position:sticky;bottom:8px;z-index:4;width:100%;min-height:52px;font-size:16px;box-shadow:0 7px 22px #55333f44}}.health-month-nav{{display:grid!important;grid-template-columns:1fr 1fr;gap:8px}}.health-month-nav h2{{grid-column:1/-1;grid-row:1;margin:0;text-align:center}}.health-month-nav .button{{margin-top:0;text-align:center}}}}
</style></head><body class="{body_class}">{nav}<main><div class="card">{content}</div></main><script>
(()=>{{const groups=[...document.querySelectorAll('.sidebar .nav-group')];if(!groups.length)return;const path=location.pathname;const links=[...document.querySelectorAll('.sidebar nav a[href]')];let active=links.find(a=>a.getAttribute('href')===path);if(!active)active=links.filter(a=>{{const href=a.getAttribute('href');return href!=='/family'&&href!=='/dashboard'&&path.startsWith(href+'/')}}).sort((a,b)=>b.getAttribute('href').length-a.getAttribute('href').length)[0];if(active){{active.classList.add('active');const current=active.closest('.nav-group');if(current)current.open=true}}groups.forEach(group=>{{const key='estrella-nav-'+group.dataset.navGroup;try{{if(!group.open&&localStorage.getItem(key)==='open')group.open=true}}catch(e){{}}group.addEventListener('toggle',()=>{{try{{localStorage.setItem(key,group.open?'open':'closed')}}catch(e){{}}}})}})}})();
</script></body></html>'''


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


@app.middleware("http")
async def security_headers_and_origin(request: Request, call_next):
    external_webhook = request.url.path.startswith("/line/webhook/")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith("/api/v1/") and not external_webhook:
        site = request.headers.get("sec-fetch-site", "")
        origin = request.headers.get("origin")
        expected_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        if site == "cross-site" or (origin and expected_host and origin.split("://", 1)[-1].rstrip("/") != expected_host):
            return JSONResponse({"detail": "安全のため、この操作を受け付けませんでした"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    return response


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
        conn.execute(text("ALTER TABLE IF EXISTS family_announcements ADD COLUMN IF NOT EXISTS event_time VARCHAR(5)"))
        conn.execute(text("ALTER TABLE IF EXISTS family_announcements ADD COLUMN IF NOT EXISTS event_location VARCHAR(300)"))
        conn.execute(text("ALTER TABLE IF EXISTS family_announcements ADD COLUMN IF NOT EXISTS event_capacity INTEGER"))
        conn.execute(text("ALTER TABLE IF EXISTS family_announcements ADD COLUMN IF NOT EXISTS response_deadline TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE IF EXISTS family_announcements ADD COLUMN IF NOT EXISTS waitlist_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS family_notification_settings ADD COLUMN IF NOT EXISTS email_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS family_notification_settings ADD COLUMN IF NOT EXISTS push_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS family_notification_settings ADD COLUMN IF NOT EXISTS health_vaccinations BOOLEAN NOT NULL DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE IF EXISTS family_notification_settings ADD COLUMN IF NOT EXISTS health_checkups BOOLEAN NOT NULL DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE IF EXISTS family_notification_settings ADD COLUMN IF NOT EXISTS health_medications BOOLEAN NOT NULL DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE IF EXISTS family_notification_settings ADD COLUMN IF NOT EXISTS health_followups BOOLEAN NOT NULL DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE IF EXISTS family_notification_settings ADD COLUMN IF NOT EXISTS line_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS line_official_accounts ADD COLUMN IF NOT EXISTS bot_basic_id VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS line_official_accounts ADD COLUMN IF NOT EXISTS bot_display_name VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS line_official_accounts ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE IF EXISTS line_official_accounts ADD COLUMN IF NOT EXISTS last_webhook_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE IF EXISTS line_official_accounts ADD COLUMN IF NOT EXISTS last_error VARCHAR(500)"))
        conn.execute(text("ALTER TABLE IF EXISTS family_dog_album_items ADD COLUMN IF NOT EXISTS post_group VARCHAR(36)"))
        conn.execute(text("ALTER TABLE IF EXISTS family_dog_album_items ADD COLUMN IF NOT EXISTS photo_order INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE IF EXISTS family_timeline_reports ALTER COLUMN album_item_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS meal_amount_g DOUBLE PRECISION"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS food_name VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS stool_condition VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS health_condition VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS physical_exam BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS blood_test BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS ultrasound BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS chest_xray BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS result_summary VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS next_due_on DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255)"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS attachment_content_type VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS health_records ADD COLUMN IF NOT EXISTS attachment_data BYTEA"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS vaccine_type VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS dose_number INTEGER"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS clinic VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS lot_no VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS reaction VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS notes TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS certificate_filename VARCHAR(255)"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS certificate_content_type VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS vaccinations ADD COLUMN IF NOT EXISTS certificate_data BYTEA"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS medication_type VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS purpose VARCHAR(200)"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS dosage VARCHAR(50)"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS frequency VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS started_on DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS ended_on DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS next_due_on DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS status VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS clinic VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS medications ADD COLUMN IF NOT EXISTS owner_notes TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS disease_category VARCHAR(50)"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS symptoms TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS status VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS recurrence BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS clinic VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS veterinarian VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS next_followup_on DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS disease_histories ADD COLUMN IF NOT EXISTS owner_notes TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS dog_id INTEGER REFERENCES dogs(id) ON DELETE CASCADE"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(150)"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS food_type VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS amount_g DOUBLE PRECISION"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS times_per_day INTEGER"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS status VARCHAR(30)"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS change_reason VARCHAR(300)"))
        conn.execute(text("ALTER TABLE IF EXISTS food_histories ADD COLUMN IF NOT EXISTS owner_notes TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_health_records ADD COLUMN IF NOT EXISTS next_due_on DATE"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_health_records ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255)"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_health_records ADD COLUMN IF NOT EXISTS attachment_content_type VARCHAR(100)"))
        conn.execute(text("ALTER TABLE IF EXISTS owner_health_records ADD COLUMN IF NOT EXISTS attachment_data BYTEA"))
        conn.execute(text("ALTER TABLE IF EXISTS line_deliveries ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE IF EXISTS line_deliveries ADD COLUMN IF NOT EXISTS message TEXT"))
        conn.execute(text("ALTER TABLE IF EXISTS line_deliveries ADD COLUMN IF NOT EXISTS target_url VARCHAR(500)"))
    with SessionLocal() as session:
        ensure_vapid_keys(session)
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


def dispatch_scheduled_emails():
    with SessionLocal() as session:
        if smtp_ready():
            pending = session.scalars(select(EmailDelivery).where(
                EmailDelivery.status.in_(["pending", "failed"]), EmailDelivery.purpose != "password_reset", EmailDelivery.attempts < 5,
            ).order_by(EmailDelivery.created_at).limit(100)).all()
            for delivery in pending:
                deliver_email(delivery, session)
        session.commit()
        settings = session.scalars(select(FamilyNotificationSetting).where(
            (FamilyNotificationSetting.email_enabled.is_(True) | FamilyNotificationSetting.push_enabled.is_(True) | FamilyNotificationSetting.line_enabled.is_(True)),
            (FamilyNotificationSetting.anniversaries.is_(True)
             | FamilyNotificationSetting.health_vaccinations.is_(True)
             | FamilyNotificationSetting.health_checkups.is_(True)
             | FamilyNotificationSetting.health_medications.is_(True)
             | FamilyNotificationSetting.health_followups.is_(True))
        )).all()
        base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
        for setting in settings:
            owner = session.get(User, setting.user_id)
            if not owner or not owner.active:
                continue
            for dog, event_type, event_date, days in (family_anniversary_notification_items(owner, session) if setting.anniversaries else []):
                label = "誕生日" if event_type == "birthday" else "お迎え記念日"
                timing = "本日" if days == 0 else ("明日" if days == 1 else "7日後")
                if setting.email_enabled:
                    queue_email(session, owner.email, "anniversary", f"【ESTRELLA FAMILY】{dog.call_name}の{label}が{timing}です",
                                f"{owner.name} 様\n\n{dog.call_name}の{label}は{event_date.strftime('%Y年%m月%d日')}です。大切な記念日をご確認ください。\n{base_url}/family/anniversaries",
                                dog.tenant_id, owner.id, f"anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}")
                send_web_push(owner.id, "anniversaries", f"{dog.call_name}の{label}が{timing}です", event_date.strftime("%Y年%m月%d日"),
                              "/family/anniversaries", f"push:anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}", session)
                send_line_push(owner.id, dog.tenant_id, "anniversaries", f"{dog.call_name}の{label}が{timing}です。\n日付：{event_date.strftime('%Y年%m月%d日')}",
                               "/family/anniversaries", f"line:anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}", session)
            health_groups = [
                ("health_vaccinations", "ワクチン", "vaccination", family_vaccine_due_items(owner, session)),
                ("health_checkups", "健診", "checkup", family_checkup_due_items(owner, session)),
                ("health_medications", "投薬", "medication", family_medication_due_items(owner, session)),
                ("health_followups", "再診・経過確認", "disease", family_disease_due_items(owner, session)),
            ]
            for setting_name, label, category, raw_items in health_groups:
                if not getattr(setting, setting_name, False):
                    continue
                for dog, title, due_on, days in family_health_notification_timing(raw_items):
                    timing = f"{days}日後" if days > 1 else ("明日" if days == 1 else ("本日" if days == 0 else f"{abs(days)}日超過"))
                    subject = f"【ESTRELLA FAMILY】{dog.call_name}の{label}予定が{timing}です"
                    message = f"{owner.name} 様\n\n{dog.call_name}の{label}予定をご確認ください。\n内容：{title}\n予定日：{due_on.strftime('%Y年%m月%d日')}（{timing}）\n\n実施後は健康管理画面で「実施済みにする」を押してください。\n{base_url}/family/dogs/{dog.id}/health/{category}"
                    title_key = hashlib.sha256(title.encode()).hexdigest()[:12]
                    dedupe = f"health:{owner.id}:{dog.id}:{category}:{due_on.isoformat()}:{days}:{title_key}"
                    if setting.email_enabled:
                        queue_email(session, owner.email, "health_reminder", subject, message, dog.tenant_id, owner.id, f"email:{dedupe}")
                    send_web_push(owner.id, setting_name, subject.removeprefix("【ESTRELLA FAMILY】"),
                                  f"{title}／予定日 {due_on.strftime('%Y年%m月%d日')}", f"/family/dogs/{dog.id}/health/{category}", f"push:{dedupe}", session)
                    send_line_push(owner.id, dog.tenant_id, setting_name,
                                   f"{dog.call_name}の{label}予定が{timing}です。\n内容：{title}\n予定日：{due_on.strftime('%Y年%m月%d日')}",
                                   f"/family/dogs/{dog.id}/health/{category}", f"line:{dedupe}", session)
        session.commit()


async def email_scheduler_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.to_thread(dispatch_scheduled_emails)
        except Exception:
            pass
        await asyncio.sleep(3600)


@app.on_event("startup")
async def start_email_scheduler():
    asyncio.create_task(email_scheduler_loop())


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
    return layout("ログイン", f'<h1>ログイン</h1>{notice}<form method="post"><label>メールアドレス</label><input name="email" type="email" required><label>パスワード</label><input name="password" type="password" required><button>ログイン</button></form><p><a href="/forgot-password">パスワードをお忘れの方</a></p>')


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    throttle_key = auth_throttle_key(request, "web-login", email)
    if auth_throttle_blocked(throttle_key, session):
        return HTMLResponse(layout("ログイン", '<p class="error">ログイン試行が多いため、15分後にもう一度お試しください。</p><a href="/login">戻る</a>'), status_code=429)
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not user.active or not passwords.verify(password, user.password_hash):
        auth_throttle_failure(throttle_key, session)
        return HTMLResponse(layout("ログイン", '<p class="error">メールアドレスまたはパスワードが違います。</p><a href="/login">戻る</a>'), status_code=401)
    auth_throttle_success(throttle_key, session)
    raw = secrets.token_urlsafe(32)
    session.add(LoginSession(token_hash=token_hash(raw), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    session.commit()
    has_tenant = bool(accessible_tenants(user, session))
    has_dog = session.scalar(select(DogOwnership.id).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True)).limit(1)) is not None
    response = RedirectResponse("/dashboard" if has_tenant or not has_dog else "/family", status_code=303)
    response.set_cookie("dog_session", raw, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=SESSION_DAYS * 86400)
    return response


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page():
    return layout("パスワード再設定", '''<h1>パスワードをお忘れの方</h1><p>登録メールアドレスを入力してください。安全確認後、犬舎から再設定方法をご案内します。</p>
    <form method="post"><label>登録メールアドレス</label><input type="email" name="email" required><button>再設定を申し込む</button></form><p><a href="/login">ログインへ戻る</a></p>''')


@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_request(request: Request, email: str = Form(...), session: Session = Depends(db)):
    throttle_key = auth_throttle_key(request, "forgot-password", email)
    if auth_throttle_blocked(throttle_key, session):
        return layout("受付完了", '<h1>受付しました</h1><p>登録状況にかかわらず、安全のため同じ案内を表示しています。</p><p><a href="/login">ログインへ戻る</a></p>')
    auth_throttle_failure(throttle_key, session)
    account = session.scalar(select(User).where(func.lower(User.email) == normalize_email(email), User.active.is_(True)))
    if account:
        recent = session.scalar(select(PasswordResetRequest).where(
            PasswordResetRequest.user_id == account.id, PasswordResetRequest.resolved_at.is_(None),
            PasswordResetRequest.requested_at >= datetime.now(timezone.utc) - timedelta(minutes=15),
        ))
        if not recent:
            reset_request = PasswordResetRequest(user_id=account.id)
            session.add(reset_request)
            if smtp_ready():
                raw_token = secrets.token_urlsafe(32)
                reset = PasswordResetToken(user_id=account.id, token_hash=token_hash(raw_token), expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
                session.add(reset)
                base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
                subject = "【ESTRELLA FAMILY】パスワード再設定"
                body = f"{account.name} 様\n\n以下のリンクから30分以内に新しいパスワードを設定してください。\n{base_url}/reset-password/{raw_token}\n\nお心当たりがない場合は、このメールを破棄してください。"
                error = send_email_content(account.email, subject, body)
                delivery = EmailDelivery(user_id=account.id, recipient=account.email, purpose="password_reset", subject=subject,
                                         body="セキュリティ保護のため再設定リンク本文は保存していません。", attempts=1,
                                         status="failed" if error else "sent", error=error, sent_at=None if error else datetime.now(timezone.utc))
                session.add(delivery)
                if not error:
                    reset_request.resolved_at = datetime.now(timezone.utc)
            session.commit()
    return layout("受付完了", '<h1>受付しました</h1><p>登録状況にかかわらず、安全のため同じ案内を表示しています。犬舎からの連絡をお待ちください。</p><p><a href="/login">ログインへ戻る</a></p>')


def active_password_reset(raw_token: str, session: Session) -> PasswordResetToken | None:
    reset = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(raw_token), PasswordResetToken.used_at.is_(None)))
    if not reset:
        return None
    expires = reset.expires_at if reset.expires_at.tzinfo else reset.expires_at.replace(tzinfo=timezone.utc)
    return reset if expires > datetime.now(timezone.utc) else None


@app.get("/reset-password/{raw_token}", response_class=HTMLResponse)
def reset_password_page(raw_token: str, session: Session = Depends(db)):
    if not active_password_reset(raw_token, session):
        return HTMLResponse(layout("リンクエラー", '<h1>再設定リンクを利用できません</h1><p>期限切れまたは使用済みです。犬舎へ再度お申し込みください。</p>'), status_code=400)
    return layout("新しいパスワード", f'''<h1>新しいパスワードを設定</h1><form method="post">
    <label>新しいパスワード（8文字以上）</label><input type="password" name="password" minlength="8" required>
    <label>確認入力</label><input type="password" name="password_confirm" minlength="8" required><button>パスワードを変更する</button></form>''')


@app.post("/reset-password/{raw_token}", response_class=HTMLResponse)
def reset_password_save(raw_token: str, password: str = Form(...), password_confirm: str = Form(...), session: Session = Depends(db)):
    reset = active_password_reset(raw_token, session)
    if not reset or len(password) < 8 or password != password_confirm:
        return HTMLResponse(layout("入力エラー", '<p class="error">リンク、パスワードの長さ、確認入力をご確認ください。</p>'), status_code=400)
    account = session.get(User, reset.user_id)
    account.password_hash = passwords.hash(password)
    reset.used_at = datetime.now(timezone.utc)
    requests = session.scalars(select(PasswordResetRequest).where(PasswordResetRequest.user_id == account.id, PasswordResetRequest.resolved_at.is_(None))).all()
    for request_item in requests:
        request_item.resolved_at = datetime.now(timezone.utc)
    session.execute(text("DELETE FROM login_sessions WHERE user_id = :user_id"), {"user_id": account.id})
    session.commit()
    return layout("変更完了", '<h1>パスワードを変更しました</h1><p>新しいパスワードでログインしてください。</p><p><a class="button" href="/login">ログインする</a></p>')


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


def dashboard_priority_items(tenant_id: int, session: Session) -> list[tuple[date, str, str, str]]:
    """選択中の犬舎で、未完了かつ7日以内に対応が必要な予定を返す。"""
    today = date.today(); limit_day = today + timedelta(days=7); items: list[tuple[date, str, str, str]] = []; keys: set[tuple[date, str]] = set()
    category_urls = {"breeding": "/modules/breeding", "health": "/modules/health", "sales": "/modules/sales", "customer": "/modules/sales", "legal": "/modules/legal"}
    category_labels = {"breeding": "繁殖", "health": "健康", "sales": "販売", "customer": "顧客", "legal": "法令", "care": "お世話", "general": "一般"}
    for task in session.scalars(select(TaskEvent).where(TaskEvent.tenant_id == tenant_id, TaskEvent.completed.is_(False), TaskEvent.due_date <= limit_day)).all():
        key = (task.due_date, task.title); keys.add(key)
        items.append((task.due_date, task.title, category_labels.get(task.category, "Todo"), category_urls.get(task.category, "/modules/todo")))
    for document in session.scalars(select(LegalDocument).where(LegalDocument.tenant_id == tenant_id, LegalDocument.due_date.is_not(None), LegalDocument.due_date <= limit_day, LegalDocument.status != "completed")).all():
        key = (document.due_date, document.document_type)
        if key not in keys: items.append((document.due_date, document.document_type, "法令", "/modules/legal"))
    items.sort(key=lambda item: (item[0], item[1]))
    return items[:50]


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
        priority_items = dashboard_priority_items(tenant.id, session); today = date.today()
        overdue_count = sum(1 for item in priority_items if item[0] < today); today_count = sum(1 for item in priority_items if item[0] == today); week_count = sum(1 for item in priority_items if today < item[0] <= today + timedelta(days=7))
        priority_rows = "".join(f'''<a class="priority-item" href="{url}"><span><strong>{html.escape(title)}</strong><small>{html.escape(category)}／{due}</small></span><span class="badge" style="{'background:#f4c9ca;color:#8d3037' if due < today else ('background:#ead0d5;color:#704454' if due == today else 'background:#f6e1b8;color:#755514')}">{f'{(today-due).days}日超過' if due < today else ('本日' if due == today else f'{(due-today).days}日後')}</span></a>''' for due, title, category, url in priority_items[:10])
        body += f'''<h2>{html.escape(tenant.name)} 業務ホーム</h2><section aria-label="要対応業務"><h2>今日の要対応</h2><div class="grid"><a class="module" href="/modules/calendar?calendar_state=overdue&show_all=true"><h3>期限超過</h3><p><strong class="{'error' if overdue_count else ''}">{overdue_count}件</strong></p></a><a class="module" href="/modules/calendar?month={today:%Y-%m}"><h3>本日の予定</h3><p><strong>{today_count}件</strong></p></a><a class="module" href="/modules/calendar"><h3>7日以内</h3><p><strong>{week_count}件</strong></p></a></div><div class="priority-list">{priority_rows or '<div class="tenant">7日以内または期限超過の要対応業務はありません。</div>'}</div><div class="health-toolbar"><a class="button" href="/modules/calendar">業務カレンダー</a><a class="button secondary" href="/modules/todo">Todoを登録</a><a class="button secondary" href="/modules/health">健康管理</a></div></section><h2>機能一覧</h2><div class="grid">{module_cards}</div>'''
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
def calendar_page(month: str = "", calendar_category: str = "", calendar_state: str = "", show_all: bool = False, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    try:
        first_day = datetime.strptime(month, "%Y-%m").date().replace(day=1) if month else date.today().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="表示月を確認してください")
    if first_day < date(2000, 1, 1) or first_day > date(2100, 12, 1): raise HTTPException(status_code=400, detail="表示月を確認してください")
    allowed_categories = {"", "todo", "breeding", "health", "sales", "legal"}; allowed_states = {"", "upcoming", "overdue", "completed"}
    if calendar_category not in allowed_categories or calendar_state not in allowed_states: raise HTTPException(status_code=400, detail="検索条件を確認してください")
    month_end = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    dogs = {dog.id: dog for dog in session.scalars(select(Dog).where(Dog.tenant_id == tenant.id)).all()}
    events: list[tuple[date, str, str, str, str, str]] = []
    event_keys: set[tuple[date, str, str]] = set()
    def add_event(day: date | None, title: str, category: str, source: str, url: str, completed: bool = False):
        if not day: return
        key = (day, title, category)
        if key in event_keys: return
        event_keys.add(key)
        state = "completed" if completed else ("overdue" if day < date.today() else "upcoming")
        events.append((day, title, category, state, source, url))
    for item in session.scalars(select(TaskEvent).where(TaskEvent.tenant_id == tenant.id)).all():
        task_category = item.category if item.category in {"breeding", "health", "legal", "sales"} else "todo"
        task_url = {"breeding": "/modules/breeding", "health": "/modules/health", "legal": "/modules/legal", "sales": "/modules/sales"}.get(task_category, "/modules/todo")
        add_event(item.due_date, item.title, task_category, "Todo", task_url, item.completed)
    for item in session.scalars(select(HeatCycle).where(HeatCycle.tenant_id == tenant.id)).all():
        dog = dogs.get(item.dog_id); add_event(item.start_date + timedelta(days=180), f"{dog.call_name if dog else '対象犬'} 次回ヒート予測", "breeding", "ヒート記録", "/modules/breeding")
    completed_breedings = set(session.scalars(select(Litter.breeding_id).where(Litter.tenant_id == tenant.id, Litter.breeding_id.is_not(None))).all())
    for item in session.scalars(select(BreedingRecord).where(BreedingRecord.tenant_id == tenant.id)).all():
        dog = dogs.get(item.dam_id); add_event(item.mating_date + timedelta(days=63), f"{dog.call_name if dog else '母犬'} 出産予定", "breeding", "交配記録", "/modules/births", item.id in completed_breedings)
    for item in session.scalars(select(Vaccination).where(Vaccination.tenant_id == tenant.id, Vaccination.next_due_on.is_not(None))).all():
        dog = dogs.get(item.dog_id); add_event(item.next_due_on, f"{dog.call_name if dog else '対象犬'} {item.vaccine_name}接種予定", "health", "ワクチン", "/modules/health/vaccinations")
    for item in session.scalars(select(HealthRecord).where(HealthRecord.tenant_id == tenant.id, HealthRecord.category == "checkup", HealthRecord.next_due_on.is_not(None))).all():
        dog = dogs.get(item.dog_id); add_event(item.next_due_on, f"{dog.call_name if dog else '対象犬'} 次回健診予定", "health", "健診", "/modules/health/checkups")
    for item in session.scalars(select(Medication).where(Medication.tenant_id == tenant.id, Medication.next_due_on.is_not(None), Medication.status != "completed")).all():
        dog = dogs.get(item.dog_id); add_event(item.next_due_on, f"{dog.call_name if dog else '対象犬'} {item.medicine_name}投薬予定", "health", "投薬", "/modules/health/medications")
    for item in session.scalars(select(DiseaseHistory).where(DiseaseHistory.tenant_id == tenant.id, DiseaseHistory.next_followup_on.is_not(None), DiseaseHistory.status != "recovered")).all():
        dog = dogs.get(item.dog_id); add_event(item.next_followup_on, f"{dog.call_name if dog else '対象犬'} {item.disease_name}再診・確認", "health", "再診・経過確認", "/modules/health/diseases")
    for item in session.scalars(select(LegalDocument).where(LegalDocument.tenant_id == tenant.id, LegalDocument.due_date.is_not(None))).all(): add_event(item.due_date, item.document_type, "legal", "法令・行政", "/modules/legal", item.status == "completed")
    events = [item for item in events if (show_all or first_day <= item[0] <= month_end) and (not calendar_category or item[2] == calendar_category) and (not calendar_state or item[3] == calendar_state)]
    events.sort(key=lambda item: (item[0], item[1]))
    category_labels = {"todo": "Todo", "breeding": "繁殖", "health": "健康", "sales": "販売・顧客", "legal": "法令"}; state_labels = {"upcoming": "予定", "overdue": "期限超過", "completed": "完了"}
    state_styles = {"upcoming": "background:#f6e1b8;color:#755514", "overdue": "background:#f4c9ca;color:#8d3037", "completed": "background:#d9eadb;color:#47634b"}
    rows = "".join(f'''<tr><td>{day}</td><td><a href="{url}">{html.escape(title)}</a></td><td>{category_labels[category]}</td><td>{html.escape(source)}</td><td><span class="badge" style="{state_styles[state]}">{state_labels[state]}</span></td></tr>''' for day, title, category, state, source, url in events)
    mobile_cards = "".join(f'''<article class="calendar-mobile-card"><h3><a href="{url}">{html.escape(title)}</a></h3><p>{day}　<span class="badge" style="{state_styles[state]}">{state_labels[state]}</span></p><p>{category_labels[category]}／{html.escape(source)}</p></article>''' for day, title, category, state, source, url in events)
    category_options = "".join(f'<option value="{value}" {"selected" if calendar_category == value else ""}>{label}</option>' for value, label in (("", "すべて"), ("todo", "Todo"), ("breeding", "繁殖"), ("health", "健康"), ("sales", "販売・顧客"), ("legal", "法令")))
    state_options = "".join(f'<option value="{value}" {"selected" if calendar_state == value else ""}>{label}</option>' for value, label in (("", "すべて"), ("upcoming", "予定"), ("overdue", "期限超過"), ("completed", "完了")))
    body = f'''<h1>業務カレンダー</h1><p>Todoに加え、ヒート予測・出産予定・健康予定・法令期限を登録データから自動表示します。</p><form method="get" action="/modules/calendar"><div class="grid"><div><label>表示月</label><input type="month" name="month" value="{first_day:%Y-%m}" required></div><div><label>分類</label><select name="calendar_category">{category_options}</select></div><div><label>状態</label><select name="calendar_state">{state_options}</select></div></div><label style="font-weight:400"><input type="checkbox" name="show_all" value="true" style="width:auto" {"checked" if show_all else ""}> 月を限定せず全期間を表示</label><button>カレンダーを表示</button> <a class="button secondary" href="/modules/calendar">今月へ戻る</a> <a class="button" href="/modules/todo">予定を手動登録</a></form><p><strong>{len(events)}件</strong>の予定を表示しています。</p><div class="calendar-desktop-only" style="overflow-x:auto"><table><tr><th>日付</th><th>予定</th><th>分類</th><th>登録元</th><th>状態</th></tr>{rows or '<tr><td colspan="5">条件に一致する予定はありません。</td></tr>'}</table></div><section class="calendar-mobile-only">{mobile_cards or '<div class="tenant">条件に一致する予定はありません。</div>'}</section>'''
    return layout("カレンダー", body, user)


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
…93107 tokens truncated…ています。FAMILYの他のメンバーには公開されません。変更が必要な場合は犬舎へご連絡ください。</small></p>
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


def family_unread_like_items(user: User, session: Session) -> list[tuple[FamilyTimelineLike, FamilyDogAlbumItem, Dog]]:
    """自分の投稿へ付いた、未確認のいいねを返す。"""
    visible_ids = set(family_timeline_items(user, session))
    if not visible_ids:
        return []
    return list(session.execute(
        select(FamilyTimelineLike, FamilyDogAlbumItem, Dog)
        .join(FamilyDogAlbumItem, FamilyDogAlbumItem.id == FamilyTimelineLike.album_item_id)
        .join(Dog, Dog.id == FamilyDogAlbumItem.dog_id)
        .outerjoin(FamilyTimelineLikeRead, and_(
            FamilyTimelineLikeRead.like_id == FamilyTimelineLike.id,
            FamilyTimelineLikeRead.user_id == user.id,
        ))
        .where(
            FamilyDogAlbumItem.id.in_(visible_ids), FamilyDogAlbumItem.uploaded_by_id == user.id,
            FamilyTimelineLike.user_id != user.id, FamilyTimelineLikeRead.id.is_(None),
        ).order_by(FamilyTimelineLike.created_at.desc()).limit(100)
    ).all())


def family_unread_comment_items(user: User, session: Session) -> list[tuple[FamilyTimelineComment, FamilyDogAlbumItem, Dog]]:
    """自分の投稿へ届いた、未確認のコメントを返す。"""
    visible_ids = set(family_timeline_items(user, session))
    if not visible_ids:
        return []
    return list(session.execute(
        select(FamilyTimelineComment, FamilyDogAlbumItem, Dog)
        .join(FamilyDogAlbumItem, FamilyDogAlbumItem.id == FamilyTimelineComment.album_item_id)
        .join(Dog, Dog.id == FamilyDogAlbumItem.dog_id)
        .outerjoin(FamilyTimelineCommentRead, and_(
            FamilyTimelineCommentRead.comment_id == FamilyTimelineComment.id,
            FamilyTimelineCommentRead.user_id == user.id,
        ))
        .where(
            FamilyDogAlbumItem.id.in_(visible_ids), FamilyDogAlbumItem.uploaded_by_id == user.id,
            FamilyTimelineComment.user_id != user.id, FamilyTimelineComment.deleted_at.is_(None),
            FamilyTimelineComment.hidden_at.is_(None), FamilyTimelineCommentRead.id.is_(None),
        ).order_by(FamilyTimelineComment.created_at.desc()).limit(100)
    ).all())


def family_anniversary_notification_items(user: User, session: Session) -> list[tuple[Dog, str, date, int]]:
    dogs = session.scalars(select(Dog).join(DogOwnership, DogOwnership.dog_id == Dog.id).where(
        DogOwnership.user_id == user.id, DogOwnership.active.is_(True), Dog.active.is_(True)
    )).all()
    today = date.today()
    items: list[tuple[Dog, str, date, int]] = []
    for dog in dogs:
        candidates: list[tuple[str, date]] = []
        if dog.birth_date:
            candidates.append(("birthday", next_family_anniversary(dog.birth_date.month, dog.birth_date.day, today)))
        handover = session.scalar(select(PuppySale.handover_date).where(PuppySale.dog_id == dog.id, PuppySale.handover_date.is_not(None)).order_by(PuppySale.handover_date.desc()).limit(1))
        if not handover:
            handover = session.scalar(select(DogTransfer.transferred_on).where(DogTransfer.dog_id == dog.id).order_by(DogTransfer.transferred_on.desc()).limit(1))
        if handover:
            candidates.append(("homecoming", next_family_anniversary(handover.month, handover.day, today)))
        for event_type, event_date in candidates:
            days = (event_date - today).days
            if days not in {0, 1, 7}:
                continue
            dismissed = session.scalar(select(FamilyAnniversaryDismissal.id).where(
                FamilyAnniversaryDismissal.user_id == user.id, FamilyAnniversaryDismissal.dog_id == dog.id,
                FamilyAnniversaryDismissal.event_type == event_type, FamilyAnniversaryDismissal.event_date == event_date,
            ))
            if not dismissed:
                items.append((dog, event_type, event_date, days))
    return items


def family_health_schedule_completed(user_id: int, dog_id: int, category: str, title: str, due_on: date, session: Session) -> bool:
    return session.scalar(select(FamilyHealthScheduleCompletion.id).where(
        FamilyHealthScheduleCompletion.user_id == user_id,
        FamilyHealthScheduleCompletion.dog_id == dog_id,
        FamilyHealthScheduleCompletion.category == category,
        FamilyHealthScheduleCompletion.title == title,
        FamilyHealthScheduleCompletion.due_on == due_on,
    )) is not None


def family_vaccine_due_items(user: User, session: Session) -> list[tuple[Dog, str, date, int]]:
    ownerships = session.scalars(select(DogOwnership).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True))).all()
    dog_ids = [item.dog_id for item in ownerships]
    if not dog_ids: return []
    dogs = {dog.id: dog for dog in session.scalars(select(Dog).where(Dog.id.in_(dog_ids), Dog.active.is_(True))).all()}
    today = date.today(); results: list[tuple[Dog, str, date, int]] = []
    owner_records = session.scalars(select(OwnerHealthRecord).where(OwnerHealthRecord.dog_id.in_(dog_ids), OwnerHealthRecord.category == "vaccination", OwnerHealthRecord.next_due_on.is_not(None))).all()
    for item in owner_records:
        days = (item.next_due_on - today).days
        if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "vaccination", item.title, item.next_due_on, session): results.append((dogs[item.dog_id], item.title, item.next_due_on, days))
    shares = session.scalars(select(HealthRecordShare).where(HealthRecordShare.dog_id.in_(dog_ids), HealthRecordShare.record_type == "vaccination", HealthRecordShare.owner_visible.is_(True))).all()
    shared_ids = [share.record_id for share in shares]
    if shared_ids:
        for item in session.scalars(select(Vaccination).where(Vaccination.id.in_(shared_ids), Vaccination.next_due_on.is_not(None))).all():
            days = (item.next_due_on - today).days
            if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "vaccination", item.vaccine_name, item.next_due_on, session): results.append((dogs[item.dog_id], item.vaccine_name, item.next_due_on, days))
    return sorted(results, key=lambda row: row[2])


def family_checkup_due_items(user: User, session: Session) -> list[tuple[Dog, str, date, int]]:
    ownerships = session.scalars(select(DogOwnership).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True))).all()
    dog_ids = [item.dog_id for item in ownerships]
    if not dog_ids: return []
    dogs = {dog.id: dog for dog in session.scalars(select(Dog).where(Dog.id.in_(dog_ids), Dog.active.is_(True))).all()}
    today = date.today(); results: list[tuple[Dog, str, date, int]] = []
    owner_records = session.scalars(select(OwnerHealthRecord).where(OwnerHealthRecord.dog_id.in_(dog_ids), OwnerHealthRecord.category == "checkup", OwnerHealthRecord.next_due_on.is_not(None))).all()
    for item in owner_records:
        days = (item.next_due_on - today).days
        if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "checkup", item.title, item.next_due_on, session): results.append((dogs[item.dog_id], item.title, item.next_due_on, days))
    shares = session.scalars(select(HealthRecordShare).where(HealthRecordShare.dog_id.in_(dog_ids), HealthRecordShare.record_type == "health", HealthRecordShare.owner_visible.is_(True))).all()
    shared_ids = [share.record_id for share in shares]
    if shared_ids:
        for item in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(shared_ids), HealthRecord.category == "checkup", HealthRecord.next_due_on.is_not(None))).all():
            days = (item.next_due_on - today).days
            if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "checkup", "健康診断", item.next_due_on, session): results.append((dogs[item.dog_id], "健康診断", item.next_due_on, days))
    return sorted(results, key=lambda row: row[2])


def family_medication_due_items(user: User, session: Session) -> list[tuple[Dog, str, date, int]]:
    ownerships = session.scalars(select(DogOwnership).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True))).all()
    dog_ids = [item.dog_id for item in ownerships]
    if not dog_ids: return []
    dogs = {dog.id: dog for dog in session.scalars(select(Dog).where(Dog.id.in_(dog_ids), Dog.active.is_(True))).all()}
    today = date.today(); results: list[tuple[Dog, str, date, int]] = []
    owner_records = session.scalars(select(OwnerHealthRecord).where(OwnerHealthRecord.dog_id.in_(dog_ids), OwnerHealthRecord.category == "medication", OwnerHealthRecord.next_due_on.is_not(None), OwnerHealthRecord.value != "終了")).all()
    for item in owner_records:
        days = (item.next_due_on - today).days
        if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "medication", item.title, item.next_due_on, session): results.append((dogs[item.dog_id], item.title, item.next_due_on, days))
    shares = session.scalars(select(HealthRecordShare).where(HealthRecordShare.dog_id.in_(dog_ids), HealthRecordShare.record_type == "medication", HealthRecordShare.owner_visible.is_(True))).all()
    shared_ids = [share.record_id for share in shares]
    if shared_ids:
        for item in session.scalars(select(Medication).where(Medication.id.in_(shared_ids), Medication.next_due_on.is_not(None), Medication.status != "completed")).all():
            days = (item.next_due_on - today).days
            if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "medication", item.medicine_name, item.next_due_on, session): results.append((dogs[item.dog_id], item.medicine_name, item.next_due_on, days))
    return sorted(results, key=lambda row: row[2])


def family_disease_due_items(user: User, session: Session) -> list[tuple[Dog, str, date, int]]:
    ownerships = session.scalars(select(DogOwnership).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True))).all()
    dog_ids = [item.dog_id for item in ownerships]
    if not dog_ids: return []
    dogs = {dog.id: dog for dog in session.scalars(select(Dog).where(Dog.id.in_(dog_ids), Dog.active.is_(True))).all()}
    today = date.today(); results: list[tuple[Dog, str, date, int]] = []
    owner_records = session.scalars(select(OwnerHealthRecord).where(OwnerHealthRecord.dog_id.in_(dog_ids), OwnerHealthRecord.category == "disease", OwnerHealthRecord.next_due_on.is_not(None), OwnerHealthRecord.value != "完治")).all()
    for item in owner_records:
        days = (item.next_due_on - today).days
        if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "disease", item.title, item.next_due_on, session): results.append((dogs[item.dog_id], item.title, item.next_due_on, days))
    shares = session.scalars(select(HealthRecordShare).where(HealthRecordShare.dog_id.in_(dog_ids), HealthRecordShare.record_type == "disease", HealthRecordShare.owner_visible.is_(True))).all()
    shared_ids = [share.record_id for share in shares]
    if shared_ids:
        for item in session.scalars(select(DiseaseHistory).where(DiseaseHistory.id.in_(shared_ids), DiseaseHistory.next_followup_on.is_not(None), DiseaseHistory.status != "recovered")).all():
            days = (item.next_followup_on - today).days
            if -90 <= days <= 30 and item.dog_id in dogs and not family_health_schedule_completed(user.id, item.dog_id, "disease", item.disease_name, item.next_followup_on, session): results.append((dogs[item.dog_id], item.disease_name, item.next_followup_on, days))
    return sorted(results, key=lambda row: row[2])


def family_notification_count(user: User, session: Session) -> int:
    setting = family_notification_setting(user, session)
    return ((len(family_unread_message_items(user, session)) if setting.messages else 0)
            + (len(family_unread_announcements(user, session)) if setting.announcements else 0)
            + ((len(family_unread_like_items(user, session)) + len(family_unread_comment_items(user, session))) if setting.likes else 0)
            + (len(family_anniversary_notification_items(user, session)) if setting.anniversaries else 0)
            + (len(family_health_notification_timing(family_vaccine_due_items(user, session))) if setting.health_vaccinations else 0)
            + (len(family_health_notification_timing(family_checkup_due_items(user, session))) if setting.health_checkups else 0)
            + (len(family_health_notification_timing(family_medication_due_items(user, session))) if setting.health_medications else 0)
            + (len(family_health_notification_timing(family_disease_due_items(user, session))) if setting.health_followups else 0))


def family_message_name(user_id: int, session: Session) -> str:
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == user_id))
    if profile and profile.profile_public and profile.show_nickname and profile.nickname:
        return profile.nickname
    return "FAMILYメンバー"


def family_action_disabled(user_id: int, tenant_id: int, action: str, session: Session) -> bool:
    restriction = session.scalar(select(FamilyUserRestriction).where(
        FamilyUserRestriction.user_id == user_id, FamilyUserRestriction.tenant_id == tenant_id))
    return bool(restriction and getattr(restriction, f"{action}_disabled", False))


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
    session.add(FamilyModerationAudit(tenant_id=tenant.id, admin_user_id=user.id, target_type="message", target_id=message.id, action=action, details=message.admin_note))
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
        report_link = f'<a href="/family/safety/report?target_type=message&amp;target_id={message.id}&amp;tenant_id={conversation.tenant_id}"><small>犬舎へ通報</small></a>' if not mine and not message.withdrawn_at else ""
        cards += f'''<article class="tenant" style="margin-left:{'18%' if mine else '0'};margin-right:{'0' if mine else '18%'}"><p><strong>{'あなた' if mine else html.escape(family_message_name(other_id, session))}</strong> <small>{message.sent_at.strftime('%Y-%m-%d %H:%M')}</small></p><p style="white-space:pre-wrap">{content}</p>{withdraw} {report_link}</article>'''
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
    if family_action_disabled(user.id, conversation.tenant_id, "messages", session):
        raise HTTPException(status_code=403, detail="犬舎によりメッセージ機能が停止されています")
    message_body = body.strip()
    if not message_body or len(message_body) > 1000:
        raise HTTPException(status_code=400, detail="メッセージは1〜1000文字で入力してください")
    if not conversation.active or family_message_blocked(conversation, session):
        raise HTTPException(status_code=403, detail="現在、この会話には送信できません")
    recipient_id = conversation.user2_id if conversation.user1_id == user.id else conversation.user1_id
    recipient = session.get(User, recipient_id)
    send_email = bool(recipient and email_notification_allowed(recipient, "messages", session))
    message = FamilyMessage(conversation_id=conversation.id, sender_id=user.id, body=message_body)
    session.add(message)
    session.flush()
    if send_email:
        base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
        preview = message_body[:120] + ("…" if len(message_body) > 120 else "")
        queue_email(session, recipient.email, "new_message", "【ESTRELLA FAMILY】新しいメッセージが届きました",
                    f"{recipient.name} 様\n\n{family_message_name(user.id, session)}さんからメッセージが届きました。\n\n{preview}\n\n確認する：{base_url}/family/messages/{conversation.id}",
                    conversation.tenant_id, recipient.id, f"message:{message.id}")
    if recipient and recipient.active:
        send_web_push(recipient.id, "messages", "新しいメッセージが届きました", preview if send_email else message_body[:120],
                      f"/family/messages/{conversation.id}", f"push:message:{message.id}", session)
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
        .options(defer(FamilyDogAlbumItem.photo_data))
        .join(Dog, Dog.id == FamilyDogAlbumItem.dog_id).join(Tenant, Tenant.id == Dog.tenant_id)
        .join(OwnerProfile, OwnerProfile.user_id == FamilyDogAlbumItem.uploaded_by_id)
        .where(FamilyDogAlbumItem.visibility.in_(["family", "relatives"]), Dog.active.is_(True),
               Tenant.active.is_(True), Tenant.deleted.is_(False), OwnerProfile.profile_public.is_(True),
               OwnerProfile.show_dogs.is_(True))
        .order_by(FamilyDogAlbumItem.created_at.desc(), FamilyDogAlbumItem.photo_order).limit(1000)
    ).all()
    visible: dict[int, tuple[FamilyDogAlbumItem, Dog, Tenant, OwnerProfile]] = {}
    shown_groups: set[str] = set()
    for item, dog, tenant, profile in records:
        allowed = item.uploaded_by_id == user.id
        if item.visibility == "family" and dog.tenant_id in tenant_ids:
            allowed = True
        if item.visibility == "relatives" and any(family_relationship(session, source, dog) for source in source_dogs):
            allowed = True
        if allowed:
            if item.post_group and item.post_group in shown_groups:
                continue
            if item.post_group:
                shown_groups.add(item.post_group)
            visible[item.id] = (item, dog, tenant, profile)
    return visible


@app.get("/family/timeline", response_class=HTMLResponse)
def family_timeline(kennel_id: int = 0, dog_id: int = 0, scope: str = "", page: int = 1,
                    user: User = Depends(require_user), session: Session = Depends(db)):
    visible = family_timeline_items(user, session)
    all_records = list(visible.values())
    kennels = {tenant.id: tenant.name for _, _, tenant, _ in all_records}
    dogs = {dog.id: dog.call_name for _, dog, _, _ in all_records if not kennel_id or dog.tenant_id == kennel_id}
    filtered = []
    for record in all_records:
        item, dog, tenant, _ = record
        if kennel_id and tenant.id != kennel_id:
            continue
        if dog_id and dog.id != dog_id:
            continue
        if scope == "mine" and item.uploaded_by_id != user.id:
            continue
        if scope in {"family", "relatives"} and item.visibility != scope:
            continue
        filtered.append(record)
    page_size = 48
    total = len(filtered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(page, 1), total_pages)
    page_records = filtered[(page - 1) * page_size:page * page_size]
    page_ids = [item.id for item, _, _, _ in page_records]
    like_counts = dict(session.execute(select(FamilyTimelineLike.album_item_id, func.count(FamilyTimelineLike.id)).where(
        FamilyTimelineLike.album_item_id.in_(page_ids)).group_by(FamilyTimelineLike.album_item_id)).all()) if page_ids else {}
    comment_counts = dict(session.execute(select(FamilyTimelineComment.album_item_id, func.count(FamilyTimelineComment.id)).where(
        FamilyTimelineComment.album_item_id.in_(page_ids), FamilyTimelineComment.deleted_at.is_(None),
        FamilyTimelineComment.hidden_at.is_(None)).group_by(FamilyTimelineComment.album_item_id)).all()) if page_ids else {}
    posts = ""
    for item, dog, tenant, profile in page_records:
        taken = item.taken_on.strftime("%Y年%m月%d日") if item.taken_on else item.created_at.date().strftime("%Y年%m月%d日")
        like_count, comment_count = like_counts.get(item.id, 0), comment_counts.get(item.id, 0)
        photo_count = session.scalar(select(func.count(FamilyDogAlbumItem.id)).where(FamilyDogAlbumItem.post_group == item.post_group)) if item.post_group else 1
        posts += f'''<a class="timeline-tile" href="/family/timeline/{item.id}">
        <img src="/family/timeline/{item.id}/photo" alt="{html.escape(dog.call_name)}の成長写真" loading="lazy">
        <span class="timeline-overlay"><strong>{html.escape(dog.call_name)}{'　▣ ' + str(photo_count) if photo_count > 1 else ''}</strong>
        <span class="timeline-stats"><span>{taken}</span><span>♥ {like_count}　💬 {comment_count}</span></span></span></a>'''
    if not posts:
        posts = '''<div class="tenant" style="grid-column:1/-1"><p>条件に一致する写真はありません。</p><p>絞り込み条件を変更してご確認ください。</p></div>'''
    kennel_options = '<option value="0">すべての犬舎</option>' + "".join(
        f'<option value="{key}" {"selected" if kennel_id == key else ""}>{html.escape(value)}</option>' for key, value in sorted(kennels.items(), key=lambda row: row[1]))
    dog_options = '<option value="0">すべての愛犬</option>' + "".join(
        f'<option value="{key}" {"selected" if dog_id == key else ""}>{html.escape(value)}</option>' for key, value in sorted(dogs.items(), key=lambda row: row[1]))
    scope_options = "".join(f'<option value="{key}" {"selected" if scope == key else ""}>{label}</option>' for key, label in [
        ("", "すべての公開投稿"), ("family", "同じ犬舎のFAMILY"), ("relatives", "兄弟・親戚犬"), ("mine", "自分の投稿")])
    base_params = {"kennel_id": kennel_id, "dog_id": dog_id, "scope": scope}
    prev_link = f'<a class="button secondary" href="/family/timeline?{urlencode({**base_params, "page": page - 1})}">新しい写真へ</a>' if page > 1 else ""
    next_link = f'<a class="button secondary" href="/family/timeline?{urlencode({**base_params, "page": page + 1})}">過去の写真へ</a>' if page < total_pages else ""
    pager = f'<div style="display:flex;justify-content:center;align-items:center;gap:12px;margin:22px 0">{prev_link}<span>{page} / {total_pages}ページ</span>{next_link}</div>' if total else ""
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>FAMILYタイムライン</h1>
    <p>同じ犬舎のFAMILYや兄弟・親戚犬が公開した成長写真を、新しい順に表示しています。</p>
    <p><a class="button success" href="/family/growth/add">＋ 成長記録を追加</a></p>
    <form method="get" action="/family/timeline" class="tenant"><div class="grid"><div><label>犬舎</label><select name="kennel_id">{kennel_options}</select></div><div><label>愛犬</label><select name="dog_id">{dog_options}</select></div><div><label>公開区分</label><select name="scope">{scope_options}</select></div></div><button>この条件で表示</button> <a class="button secondary" href="/family/timeline">条件を解除</a></form>
    <p><strong>{total}件</strong>の写真が見つかりました。</p><div class="timeline-grid">{posts}</div>{pager}
    <p><small>「自分だけ」に設定した写真はタイムラインには表示されません。</small></p>'''
    return family_layout("FAMILYタイムライン", body, user, session)


@app.get("/family/timeline/{item_id}", response_class=HTMLResponse)
def family_timeline_detail(item_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    record = family_timeline_items(user, session).get(item_id)
    if not record:
        raise HTTPException(status_code=404)
    item, dog, tenant, profile = record
    if item.uploaded_by_id == user.id:
        unread_likes = session.scalars(
            select(FamilyTimelineLike).outerjoin(FamilyTimelineLikeRead, and_(
                FamilyTimelineLikeRead.like_id == FamilyTimelineLike.id,
                FamilyTimelineLikeRead.user_id == user.id,
            )).where(FamilyTimelineLike.album_item_id == item.id, FamilyTimelineLike.user_id != user.id,
                     FamilyTimelineLikeRead.id.is_(None))
        ).all()
        for unread_like in unread_likes:
            session.add(FamilyTimelineLikeRead(like_id=unread_like.id, user_id=user.id))
        unread_comments = session.scalars(
            select(FamilyTimelineComment).outerjoin(FamilyTimelineCommentRead, and_(
                FamilyTimelineCommentRead.comment_id == FamilyTimelineComment.id,
                FamilyTimelineCommentRead.user_id == user.id,
            )).where(FamilyTimelineComment.album_item_id == item.id, FamilyTimelineComment.user_id != user.id,
                     FamilyTimelineComment.deleted_at.is_(None), FamilyTimelineComment.hidden_at.is_(None),
                     FamilyTimelineCommentRead.id.is_(None))
        ).all()
        for unread_comment in unread_comments:
            session.add(FamilyTimelineCommentRead(comment_id=unread_comment.id, user_id=user.id))
        if unread_likes or unread_comments:
            session.commit()
    owner_name = profile.nickname if profile.show_nickname and profile.nickname else "FAMILYメンバー"
    taken = item.taken_on.strftime("%Y年%m月%d日") if item.taken_on else item.created_at.date().strftime("%Y年%m月%d日")
    visibility = "同じ犬舎のFAMILYに公開" if item.visibility == "family" else "兄弟・親戚犬に公開"
    likes = session.execute(
        select(FamilyTimelineLike, OwnerProfile).outerjoin(OwnerProfile, OwnerProfile.user_id == FamilyTimelineLike.user_id)
        .where(FamilyTimelineLike.album_item_id == item.id).order_by(FamilyTimelineLike.created_at)
    ).all()
    liked = any(like.user_id == user.id for like, _ in likes)
    like_names = []
    for like, like_profile in likes[:10]:
        if like.user_id == user.id:
            like_names.append("あなた")
        elif like_profile and like_profile.profile_public and like_profile.show_nickname and like_profile.nickname:
            like_names.append(like_profile.nickname)
        else:
            like_names.append("FAMILYメンバー")
    more = f" ほか{len(likes) - 10}人" if len(likes) > 10 else ""
    liked_by = f'<p><small>{html.escape("、".join(like_names))}{more}</small></p>' if like_names else '<p><small>最初のいいねを送りましょう</small></p>'
    comment_rows = session.execute(
        select(FamilyTimelineComment, OwnerProfile).outerjoin(OwnerProfile, OwnerProfile.user_id == FamilyTimelineComment.user_id)
        .where(FamilyTimelineComment.album_item_id == item.id, FamilyTimelineComment.deleted_at.is_(None),
               FamilyTimelineComment.hidden_at.is_(None)).order_by(FamilyTimelineComment.created_at)
    ).all()
    comments = ""
    reported_targets = {(report.target_type, report.target_id) for report in session.scalars(
        select(FamilyTimelineReport).where(FamilyTimelineReport.reporter_id == user.id,
                                           FamilyTimelineReport.album_item_id == item.id)).all()}
    for comment, comment_profile in comment_rows:
        comment_name = "あなた" if comment.user_id == user.id else (comment_profile.nickname if comment_profile and comment_profile.profile_public and comment_profile.show_nickname and comment_profile.nickname else "FAMILYメンバー")
        delete_form = f'''<form class="inline" method="post" action="/family/timeline/{item.id}/comments/{comment.id}/delete"><button class="secondary" style="padding:5px 9px">削除</button></form>''' if comment.user_id == user.id else ""
        report_link = (f'<a href="/family/timeline/{item.id}/report?target_type=comment&amp;target_id={comment.id}"><small>犬舎へ通報</small></a>' if ("comment", comment.id) not in reported_targets else '<small>通報受付済み</small>') if comment.user_id != user.id else ""
        comments += f'''<div class="tenant" style="margin:10px 0;padding:12px"><p style="margin:0 0 5px"><strong>{html.escape(comment_name)}</strong> <small>{comment.created_at.strftime('%Y年%m月%d日 %H:%M')}</small></p><p style="white-space:pre-wrap;margin:0">{html.escape(comment.body)}</p>{delete_form} {report_link}</div>'''
    comments = comments or '<p><small>最初のコメントを送りましょう。</small></p>'
    caption = f'<p style="white-space:pre-wrap">{html.escape(item.caption)}</p>' if item.caption else ""
    post_photos = session.scalars(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.post_group == item.post_group).order_by(FamilyDogAlbumItem.photo_order)).all() if item.post_group else [item]
    photo_gallery = ''.join(f'<div class="family-photo-stage"><img class="family-dog-photo" src="/family/timeline/{photo_item.id}/photo" alt="{html.escape(dog.call_name)}の成長写真 {index + 1}"></div>' for index, photo_item in enumerate(post_photos))
    photo_report = ""
    if item.uploaded_by_id != user.id:
        photo_report = '<small>犬舎へ通報済み</small>' if ("photo", item.id) in reported_targets else f'<a href="/family/timeline/{item.id}/report?target_type=photo&amp;target_id={item.id}"><small>この投稿を犬舎へ通報</small></a>'
    body = f'''<a class="button secondary" href="/family/timeline">タイムラインへ戻る</a><article style="max-width:820px;margin:20px auto 0">
    <div style="display:flex;justify-content:space-between;gap:12px;align-items:start"><div><strong>{html.escape(owner_name)}</strong>
    <p style="margin:3px 0"><a href="/family/members/{profile.public_id}">{html.escape(dog.call_name)}</a>　<small>{html.escape(tenant.name)}</small></p></div>
    <span class="badge">{html.escape(visibility)}</span></div>
    {photo_gallery}
    {caption}<p><small>撮影日：{taken}</small>　{photo_report}</p>
    <form class="inline" method="post" action="/family/timeline/{item.id}/like?return_to=detail"><button class="{'secondary' if liked else ''}" aria-pressed="{'true' if liked else 'false'}">{'♥ いいね済み' if liked else '♡ いいね'}　{len(likes)}</button></form>{liked_by}
    <section style="margin-top:25px"><h2>コメント</h2>{comments}<form method="post" action="/family/timeline/{item.id}/comments"><label>コメント（300文字まで）</label><textarea name="body" maxlength="300" required></textarea><button>コメントを送る</button></form><p><small>コメントは同じ写真を閲覧できるFAMILYに表示されます。不適切な内容は犬舎管理者が非表示にできます。</small></p></section></article>'''
    return family_layout(f"{dog.call_name}｜FAMILYタイムライン", body, user, session)


TIMELINE_REPORT_REASONS = {
    "harassment": "嫌がらせ・攻撃的な内容",
    "privacy": "個人情報・プライバシー",
    "inappropriate": "不適切な写真・表現",
    "spam": "宣伝・迷惑行為",
    "other": "その他",
}


def family_timeline_report_target(item_id: int, target_type: str, target_id: int, user: User, session: Session):
    record = family_timeline_items(user, session).get(item_id)
    if not record or target_type not in {"photo", "comment"}:
        raise HTTPException(status_code=404)
    item, dog, tenant, _ = record
    if target_type == "photo":
        if target_id != item.id or item.uploaded_by_id == user.id:
            raise HTTPException(status_code=404)
    else:
        comment = session.scalar(select(FamilyTimelineComment).where(
            FamilyTimelineComment.id == target_id, FamilyTimelineComment.album_item_id == item.id,
            FamilyTimelineComment.deleted_at.is_(None), FamilyTimelineComment.hidden_at.is_(None)))
        if not comment or comment.user_id == user.id:
            raise HTTPException(status_code=404)
    return item, dog, tenant


@app.get("/family/timeline/{item_id}/report", response_class=HTMLResponse)
def family_timeline_report_page(item_id: int, target_type: str, target_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    _, dog, _ = family_timeline_report_target(item_id, target_type, target_id, user, session)
    existing = session.scalar(select(FamilyTimelineReport).where(
        FamilyTimelineReport.reporter_id == user.id, FamilyTimelineReport.target_type == target_type,
        FamilyTimelineReport.target_id == target_id))
    if existing:
        body = f'''<a class="button secondary" href="/family/timeline/{item_id}">投稿へ戻る</a><h1>通報受付済み</h1><div class="tenant"><p>この内容は犬舎へ連絡済みです。確認と対応をお待ちください。</p></div>'''
        return family_layout("通報受付済み｜FAMILY", body, user, session)
    options = "".join(f'<option value="{key}">{label}</option>' for key, label in TIMELINE_REPORT_REASONS.items())
    target_label = "投稿写真" if target_type == "photo" else "コメント"
    body = f'''<a class="button secondary" href="/family/timeline/{item_id}">投稿へ戻る</a><h1>犬舎へ通報</h1>
    <div class="tenant"><p><strong>{html.escape(dog.call_name)}の{target_label}</strong>について犬舎へ連絡します。</p><p>緊急性がある場合は、この機能だけでなく犬舎へ直接ご連絡ください。</p></div>
    <form method="post" action="/family/timeline/{item_id}/report"><input type="hidden" name="target_type" value="{target_type}"><input type="hidden" name="target_id" value="{target_id}"><label>理由</label><select name="reason" required>{options}</select><label>詳しい状況（任意・500文字まで）</label><textarea name="details" maxlength="500"></textarea><button>犬舎へ通報する</button></form>'''
    return family_layout("犬舎へ通報｜FAMILY", body, user, session)


@app.post("/family/timeline/{item_id}/report")
def family_timeline_report_create(item_id: int, target_type: str = Form(...), target_id: int = Form(...), reason: str = Form(...), details: str = Form(""), user: User = Depends(require_user), session: Session = Depends(db)):
    item, _, tenant = family_timeline_report_target(item_id, target_type, target_id, user, session)
    if reason not in TIMELINE_REPORT_REASONS:
        raise HTTPException(status_code=400, detail="通報理由を選択してください")
    existing = session.scalar(select(FamilyTimelineReport).where(
        FamilyTimelineReport.reporter_id == user.id, FamilyTimelineReport.target_type == target_type,
        FamilyTimelineReport.target_id == target_id))
    if not existing:
        session.add(FamilyTimelineReport(tenant_id=tenant.id, reporter_id=user.id, album_item_id=item.id,
                                         target_type=target_type, target_id=target_id, reason=reason,
                                         details=details.strip()[:500] or None))
        session.commit()
    return RedirectResponse(f"/family/timeline/{item_id}", status_code=303)


@app.post("/family/timeline/{item_id}/like")
def family_timeline_like_toggle(item_id: int, return_to: str = "", user: User = Depends(require_user), session: Session = Depends(db)):
    record = family_timeline_items(user, session).get(item_id)
    if not record:
        raise HTTPException(status_code=404)
    item, dog, tenant, _ = record
    if family_action_disabled(user.id, tenant.id, "likes", session):
        raise HTTPException(status_code=403, detail="犬舎によりいいね機能が停止されています")
    like = session.scalar(select(FamilyTimelineLike).where(
        FamilyTimelineLike.album_item_id == item_id, FamilyTimelineLike.user_id == user.id
    ))
    if like:
        session.delete(like)
    else:
        like = FamilyTimelineLike(album_item_id=item_id, user_id=user.id)
        session.add(like)
        session.flush()
        owner = session.get(User, item.uploaded_by_id)
        if owner and owner.id != user.id and email_notification_allowed(owner, "likes", session):
            base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
            queue_email(session, owner.email, "timeline_like", f"【ESTRELLA FAMILY】{dog.call_name}の写真にいいねが届きました",
                        f"{owner.name} 様\n\n{family_message_name(user.id, session)}さんが{dog.call_name}の写真にいいねしました。\n{base_url}/family/timeline/{item.id}",
                        tenant.id, owner.id, f"like:{like.id}")
        if owner and owner.id != user.id:
            send_web_push(owner.id, "likes", f"{dog.call_name}の写真にいいね", f"{family_message_name(user.id, session)}さんから届きました",
                          f"/family/timeline/{item.id}", f"push:like:{like.id}", session)
    session.commit()
    destination = f"/family/timeline/{item_id}" if return_to == "detail" else "/family/timeline"
    return RedirectResponse(destination, status_code=303)


@app.get("/family/timeline/{item_id}/photo")
def family_timeline_photo(item_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    visible = family_timeline_items(user, session)
    record = visible.get(item_id)
    item = session.get(FamilyDogAlbumItem, item_id)
    if not record and item and item.post_group:
        record = next((value for value in visible.values() if value[0].post_group == item.post_group), None)
    if not record or not item:
        raise HTTPException(status_code=404)
    return Response(content=item.photo_data, media_type=item.photo_content_type, headers={"Cache-Control": "private, max-age=300"})


@app.post("/family/timeline/{item_id}/comments")
def family_timeline_comment_create(item_id: int, body: str = Form(...), user: User = Depends(require_user), session: Session = Depends(db)):
    record = family_timeline_items(user, session).get(item_id)
    if not record:
        raise HTTPException(status_code=404)
    text = body.strip()
    if not text or len(text) > 300:
        raise HTTPException(status_code=400, detail="コメントは1〜300文字で入力してください")
    item, dog, tenant, _ = record
    if family_action_disabled(user.id, tenant.id, "posting", session):
        raise HTTPException(status_code=403, detail="犬舎によりコメント投稿が停止されています")
    comment = FamilyTimelineComment(album_item_id=item.id, user_id=user.id, body=text)
    session.add(comment)
    session.flush()
    owner = session.get(User, item.uploaded_by_id)
    if owner and owner.id != user.id and email_notification_allowed(owner, "likes", session):
        base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
        queue_email(session, owner.email, "timeline_comment", f"【ESTRELLA FAMILY】{dog.call_name}の写真にコメントが届きました",
                    f"{owner.name} 様\n\n{family_message_name(user.id, session)}さんが{dog.call_name}の写真にコメントしました。\n\n{text}\n\n{base_url}/family/timeline/{item.id}",
                    tenant.id, owner.id, f"comment:{comment.id}")
    if owner and owner.id != user.id:
        send_web_push(owner.id, "likes", f"{dog.call_name}の写真にコメント", text[:120],
                      f"/family/timeline/{item.id}", f"push:comment:{comment.id}", session)
    session.commit()
    return RedirectResponse(f"/family/timeline/{item_id}", status_code=303)


@app.post("/family/timeline/{item_id}/comments/{comment_id}/delete")
def family_timeline_comment_delete(item_id: int, comment_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if item_id not in family_timeline_items(user, session):
        raise HTTPException(status_code=404)
    comment = session.scalar(select(FamilyTimelineComment).where(
        FamilyTimelineComment.id == comment_id, FamilyTimelineComment.album_item_id == item_id,
        FamilyTimelineComment.user_id == user.id, FamilyTimelineComment.deleted_at.is_(None)))
    if not comment:
        raise HTTPException(status_code=404)
    comment.deleted_at = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f"/family/timeline/{item_id}", status_code=303)


@app.get("/family/timeline/comments/manage", response_class=HTMLResponse)
def family_timeline_comments_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    rows = session.execute(
        select(FamilyTimelineComment, FamilyDogAlbumItem, Dog).join(
            FamilyDogAlbumItem, FamilyDogAlbumItem.id == FamilyTimelineComment.album_item_id).join(
            Dog, Dog.id == FamilyDogAlbumItem.dog_id).where(Dog.tenant_id == tenant.id)
        .order_by(FamilyTimelineComment.created_at.desc()).limit(300)
    ).all()
    cards = ""
    for comment, item, dog in rows:
        state = "投稿者が削除" if comment.deleted_at else ("管理者が非表示" if comment.hidden_at else "表示中")
        action = "unhide" if comment.hidden_at else "hide"
        button = "再表示" if comment.hidden_at else "利用者画面から非表示"
        cards += f'''<article class="tenant"><p><strong>{html.escape(dog.call_name)}</strong> ／ {html.escape(family_message_name(comment.user_id, session))}　<span class="badge">{state}</span></p><p style="white-space:pre-wrap">{html.escape(comment.body)}</p><small>{comment.created_at.strftime('%Y-%m-%d %H:%M')}</small><form method="post" action="/family/timeline/comments/manage/{comment.id}"><label>管理メモ</label><input name="admin_note" maxlength="500" value="{html.escape(comment.admin_note or '')}"><button name="action" value="{action}">{button}</button></form></article>'''
    body = f'''<h1>タイムラインコメント管理</h1><div class="tenant"><p>トラブル対応のため原文と操作前の履歴を保持します。管理者は原文を書き換えず、公開状態と管理メモのみ変更できます。</p></div>{cards or '<p>コメントはまだありません。</p>'}'''
    return layout("タイムラインコメント管理", body, user)


@app.post("/family/timeline/comments/manage/{comment_id}")
def family_timeline_comment_moderate(comment_id: int, action: str = Form(...), admin_note: str = Form(""), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    comment = session.scalar(select(FamilyTimelineComment).join(
        FamilyDogAlbumItem, FamilyDogAlbumItem.id == FamilyTimelineComment.album_item_id).join(
        Dog, Dog.id == FamilyDogAlbumItem.dog_id).where(FamilyTimelineComment.id == comment_id, Dog.tenant_id == tenant.id))
    if not comment or action not in {"hide", "unhide"}:
        raise HTTPException(status_code=404)
    comment.hidden_at = datetime.now(timezone.utc) if action == "hide" else None
    comment.hidden_by_id = user.id if action == "hide" else None
    comment.admin_note = admin_note.strip()[:500] or None
    session.add(FamilyModerationAudit(tenant_id=tenant.id, admin_user_id=user.id, target_type="comment", target_id=comment.id, action=action, details=comment.admin_note))
    session.commit()
    return RedirectResponse("/family/timeline/comments/manage", status_code=303)


@app.get("/family/timeline/reports/manage", response_class=HTMLResponse)
def family_timeline_reports_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    reports = session.execute(
        select(FamilyTimelineReport, Dog).join(FamilyDogAlbumItem, FamilyDogAlbumItem.id == FamilyTimelineReport.album_item_id)
        .join(Dog, Dog.id == FamilyDogAlbumItem.dog_id).where(FamilyTimelineReport.tenant_id == tenant.id)
        .order_by(FamilyTimelineReport.status, FamilyTimelineReport.created_at.desc()).limit(300)
    ).all()
    cards = ""
    for report, dog in reports:
        reason = TIMELINE_REPORT_REASONS.get(report.reason, report.reason)
        target = "投稿写真" if report.target_type == "photo" else "コメント"
        status_label = {"open": "未対応", "reviewing": "確認中", "resolved": "対応済み", "dismissed": "対応不要"}.get(report.status, report.status)
        if report.target_type == "photo":
            target_preview = f'<div class="family-photo-stage"><img class="family-dog-photo" src="/family/timeline/reports/manage/{report.id}/photo" alt="通報対象写真"></div>'
        else:
            reported_comment = session.get(FamilyTimelineComment, report.target_id)
            target_preview = f'<div class="tenant"><strong>通報対象コメント原文</strong><p style="white-space:pre-wrap">{html.escape(reported_comment.body if reported_comment else "対象コメントは確認できません")}</p></div>'
        cards += f'''<article class="tenant"><p><span class="badge">{status_label}</span> <strong>{html.escape(dog.call_name)}／{target}</strong></p>{target_preview}<p><strong>理由：</strong>{html.escape(reason)}</p><p style="white-space:pre-wrap">{html.escape(report.details or "詳細なし")}</p><p><small>通報者：{html.escape(family_message_name(report.reporter_id, session))} ／ {report.created_at.strftime('%Y-%m-%d %H:%M')}</small></p><form method="post" action="/family/timeline/reports/manage/{report.id}"><label>対応状況</label><select name="status"><option value="open" {'selected' if report.status == 'open' else ''}>未対応</option><option value="reviewing" {'selected' if report.status == 'reviewing' else ''}>確認中</option><option value="resolved" {'selected' if report.status == 'resolved' else ''}>対応済み</option><option value="dismissed" {'selected' if report.status == 'dismissed' else ''}>対応不要</option></select><label>管理メモ（利用者には表示されません）</label><textarea name="admin_note" maxlength="500">{html.escape(report.admin_note or '')}</textarea><button>対応内容を保存</button></form></article>'''
    body = f'''<h1>タイムライン通報管理</h1><div class="tenant"><p>オーナー様から届いた写真・コメントへの通報です。対象内容を確認し、必要に応じてコメント管理から非表示にしてください。</p></div>{cards or '<p>通報はありません。</p>'}'''
    return layout("タイムライン通報管理", body, user)


@app.get("/family/timeline/reports/manage/{report_id}/photo")
def family_timeline_report_photo(report_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    _, tenant = access
    report = session.scalar(select(FamilyTimelineReport).where(FamilyTimelineReport.id == report_id,
                                                                FamilyTimelineReport.tenant_id == tenant.id))
    if not report:
        raise HTTPException(status_code=404)
    item = session.get(FamilyDogAlbumItem, report.album_item_id)
    if not item:
        raise HTTPException(status_code=404)
    return Response(content=item.photo_data, media_type=item.photo_content_type, headers={"Cache-Control": "private, max-age=300"})


@app.post("/family/timeline/reports/manage/{report_id}")
def family_timeline_report_update(report_id: int, status: str = Form(...), admin_note: str = Form(""), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    report = session.scalar(select(FamilyTimelineReport).where(FamilyTimelineReport.id == report_id,
                                                                FamilyTimelineReport.tenant_id == tenant.id))
    if not report or status not in {"open", "reviewing", "resolved", "dismissed"}:
        raise HTTPException(status_code=404)
    report.status = status
    report.admin_note = admin_note.strip()[:500] or None
    report.handled_by_id = user.id
    report.handled_at = datetime.now(timezone.utc)
    session.add(FamilyModerationAudit(tenant_id=tenant.id, admin_user_id=user.id, target_type="report",
        target_id=report.id, action=f"status:{status}", details=report.admin_note))
    session.commit()
    return RedirectResponse("/family/timeline/reports/manage", status_code=303)


@app.get("/family/safety/report", response_class=HTMLResponse)
def family_safety_report_page(target_type: str, target_id: int, tenant_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if tenant_id not in family_kennel_tenant_ids(user, session) or target_type not in {"profile", "message"}:
        raise HTTPException(status_code=404)
    if target_type == "profile":
        target = session.get(User, target_id)
        if not target or target.id == user.id or tenant_id not in family_kennel_tenant_ids(target, session): raise HTTPException(status_code=404)
        label = f"{family_message_name(target.id, session)}さんのプロフィール"
    else:
        message = session.get(FamilyMessage, target_id); conversation = session.get(FamilyConversation, message.conversation_id) if message else None
        if not message or not conversation or conversation.tenant_id != tenant_id or user.id not in {conversation.user1_id, conversation.user2_id} or message.sender_id == user.id: raise HTTPException(status_code=404)
        label = "受信メッセージ"
    options = "".join(f'<option value="{key}">{value}</option>' for key, value in TIMELINE_REPORT_REASONS.items())
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>犬舎へ通報</h1><div class="tenant"><p>{html.escape(label)}について犬舎へ連絡します。</p></div><form method="post"><input type="hidden" name="target_type" value="{target_type}"><input type="hidden" name="target_id" value="{target_id}"><input type="hidden" name="tenant_id" value="{tenant_id}"><label>理由</label><select name="reason">{options}</select><label>詳しい状況（500文字まで）</label><textarea name="details" maxlength="500"></textarea><button>犬舎へ通報する</button></form>'''
    return family_layout("犬舎へ通報", body, user, session)


@app.post("/family/safety/report")
def family_safety_report_create(target_type: str = Form(...), target_id: int = Form(...), tenant_id: int = Form(...), reason: str = Form(...), details: str = Form(""), user: User = Depends(require_user), session: Session = Depends(db)):
    family_safety_report_page(target_type, target_id, tenant_id, user, session)
    if reason not in TIMELINE_REPORT_REASONS: raise HTTPException(status_code=400)
    existing = session.scalar(select(FamilyTimelineReport.id).where(FamilyTimelineReport.reporter_id == user.id,
        FamilyTimelineReport.target_type == target_type, FamilyTimelineReport.target_id == target_id))
    if not existing:
        session.add(FamilyTimelineReport(tenant_id=tenant_id, reporter_id=user.id, album_item_id=None, target_type=target_type,
            target_id=target_id, reason=reason, details=details.strip()[:500] or None)); session.commit()
    return RedirectResponse("/family", status_code=303)


@app.get("/family/safety/reports/manage", response_class=HTMLResponse)
def family_safety_reports_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    reports = session.scalars(select(FamilyTimelineReport).where(FamilyTimelineReport.tenant_id == tenant.id,
        FamilyTimelineReport.target_type.in_(["profile", "message"])).order_by(FamilyTimelineReport.status, FamilyTimelineReport.created_at.desc())).all()
    cards = ""
    for report in reports:
        if report.target_type == "profile": content = f"プロフィール：{family_message_name(report.target_id, session)}"
        else:
            message = session.get(FamilyMessage, report.target_id); content = f"メッセージ原文：{message.body if message else '確認できません'}"
        cards += f'''<article class="tenant"><p><span class="badge">{html.escape(report.status)}</span> <strong>{html.escape(content)}</strong></p><p>理由：{html.escape(TIMELINE_REPORT_REASONS.get(report.reason, report.reason))}</p><p>{html.escape(report.details or '詳細なし')}</p><form method="post" action="/family/safety/reports/manage/{report.id}"><select name="status"><option value="open">未対応</option><option value="reviewing">確認中</option><option value="resolved">対応済み</option><option value="dismissed">対応不要</option></select><label>管理メモ</label><textarea name="admin_note" maxlength="500">{html.escape(report.admin_note or '')}</textarea><button>保存</button></form></article>'''
    return layout("プロフィール・メッセージ通報", f'''<h1>プロフィール・メッセージ通報</h1>{cards or '<p>通報はありません。</p>'}''', user)


@app.post("/family/safety/reports/manage/{report_id}")
def family_safety_report_update(report_id: int, status: str = Form(...), admin_note: str = Form(""), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access; report = session.scalar(select(FamilyTimelineReport).where(FamilyTimelineReport.id == report_id, FamilyTimelineReport.tenant_id == tenant.id))
    if not report or status not in {"open", "reviewing", "resolved", "dismissed"}: raise HTTPException(status_code=404)
    report.status, report.admin_note, report.handled_by_id, report.handled_at = status, admin_note.strip()[:500] or None, user.id, datetime.now(timezone.utc)
    session.add(FamilyModerationAudit(tenant_id=tenant.id, admin_user_id=user.id, target_type=report.target_type, target_id=report.target_id, action=f"report:{status}", details=report.admin_note)); session.commit()
    return RedirectResponse("/family/safety/reports/manage", status_code=303)


@app.get("/family/restrictions/manage", response_class=HTMLResponse)
def family_restrictions_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    owners = session.execute(select(User).join(DogOwnership, DogOwnership.user_id == User.id).where(
        DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True)).distinct().order_by(User.name)).scalars().all()
    cards = ""
    for owner in owners:
        restriction = session.scalar(select(FamilyUserRestriction).where(FamilyUserRestriction.tenant_id == tenant.id,
            FamilyUserRestriction.user_id == owner.id))
        cards += f'''<article class="tenant"><h3>{html.escape(owner.name)}</h3><p>{html.escape(owner.email)}</p><form method="post" action="/family/restrictions/manage/{owner.id}"><label><input style="width:auto" type="checkbox" name="posting_disabled" value="true" {'checked' if restriction and restriction.posting_disabled else ''}> 投稿・コメントを停止</label><label><input style="width:auto" type="checkbox" name="likes_disabled" value="true" {'checked' if restriction and restriction.likes_disabled else ''}> いいねを停止</label><label><input style="width:auto" type="checkbox" name="messages_disabled" value="true" {'checked' if restriction and restriction.messages_disabled else ''}> メッセージを停止</label><label>停止理由・管理メモ</label><textarea name="reason" maxlength="500">{html.escape(restriction.reason if restriction and restriction.reason else '')}</textarea><button>利用状態を保存</button></form></article>'''
    return layout("FAMILY利用停止", f'''<h1>FAMILY利用停止</h1><div class="tenant"><p>閲覧や愛犬データは残したまま、交流機能だけを個別に停止できます。すべての変更は操作履歴へ保存されます。</p></div>{cards or '<p>連携オーナーはいません。</p>'}''', user)


@app.post("/family/restrictions/manage/{owner_id}")
def family_restriction_save(owner_id: int, posting_disabled: bool = Form(False), likes_disabled: bool = Form(False), messages_disabled: bool = Form(False), reason: str = Form(""), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    linked = session.scalar(select(DogOwnership.id).where(DogOwnership.tenant_id == tenant.id,
        DogOwnership.user_id == owner_id, DogOwnership.active.is_(True)))
    if not linked: raise HTTPException(status_code=404)
    restriction = session.scalar(select(FamilyUserRestriction).where(FamilyUserRestriction.tenant_id == tenant.id,
        FamilyUserRestriction.user_id == owner_id))
    if not restriction:
        restriction = FamilyUserRestriction(tenant_id=tenant.id, user_id=owner_id, updated_by_id=user.id); session.add(restriction)
    restriction.posting_disabled, restriction.likes_disabled, restriction.messages_disabled = posting_disabled, likes_disabled, messages_disabled
    restriction.reason, restriction.updated_by_id, restriction.updated_at = reason.strip()[:500] or None, user.id, datetime.now(timezone.utc)
    session.add(FamilyModerationAudit(tenant_id=tenant.id, admin_user_id=user.id, target_type="user", target_id=owner_id,
        action="restriction_update", details=f"posting={posting_disabled}, likes={likes_disabled}, messages={messages_disabled}"))
    session.commit(); return RedirectResponse("/family/restrictions/manage", status_code=303)


@app.get("/family/account", response_class=HTMLResponse)
def family_account_page(user: User = Depends(require_user), session: Session = Depends(db)):
    records = session.execute(
        select(DogOwnership, Dog, Tenant).join(Dog, Dog.id == DogOwnership.dog_id).join(Tenant, Tenant.id == DogOwnership.tenant_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True)).order_by(Tenant.name, Dog.call_name)
    ).all()
    transfer_cards = ""
    for ownership, dog, tenant in records:
        if ownership.relationship != "primary":
            continue
        successors = session.execute(
            select(DogOwnership, User).join(User, User.id == DogOwnership.user_id)
            .where(DogOwnership.dog_id == dog.id, DogOwnership.tenant_id == tenant.id,
                   DogOwnership.active.is_(True), DogOwnership.relationship == "family", DogOwnership.user_id != user.id)
            .order_by(User.name)
        ).all()
        options = "".join(f'<option value="{item.id}">{html.escape(member.name)}（{html.escape(member.email)}）</option>' for item, member in successors)
        action = f'''<form method="post" action="/family/account/transfer"><input type="hidden" name="ownership_id" value="{ownership.id}">
        <label>新しい主オーナー</label><select name="successor_ownership_id" required>{options}</select>
        <label style="font-weight:400"><input style="width:auto" type="checkbox" name="confirmed" value="true" required> 主オーナーを変更することを確認しました</label><button>主オーナーを引き継ぐ</button></form>''' if options else '<p><small>先に犬舎からご家族をこの愛犬へ連携してもらうと、主オーナーを引き継げます。</small></p>'
        transfer_cards += f'<article class="tenant"><h3>{html.escape(dog.call_name)}｜{html.escape(tenant.name)}</h3>{action}</article>'
    tenant_ids = sorted({ownership.tenant_id for ownership, _, _ in records})
    tenant_options = "".join(f'<option value="{tenant.id}">{html.escape(tenant.name)}</option>' for tenant in session.scalars(select(Tenant).where(Tenant.id.in_(tenant_ids)).order_by(Tenant.name)).all()) if tenant_ids else ""
    requests = session.execute(select(FamilyWithdrawalRequest, Tenant).join(Tenant, Tenant.id == FamilyWithdrawalRequest.tenant_id)
        .where(FamilyWithdrawalRequest.user_id == user.id).order_by(FamilyWithdrawalRequest.requested_at.desc())).all()
    request_rows = "".join(f'<tr><td>{html.escape(tenant.name)}</td><td>{request.requested_at.strftime("%Y-%m-%d")}</td><td>{html.escape(request.status)}</td><td>{"保存" if request.data_policy == "retain" else "削除希望"}</td></tr>' for request, tenant in requests)
    withdrawal = f'''<form method="post" action="/family/account/withdraw"><label>退会する犬舎</label><select name="tenant_id" required>{tenant_options}</select>
    <label>投稿・プロフィールデータ</label><select name="data_policy"><option value="retain">思い出として保存する</option><option value="remove_personal">プロフィールと自分の投稿の削除を希望する</option></select>
    <label>退会理由（任意）</label><textarea name="reason" maxlength="500"></textarea>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="confirmed" value="true" required> 犬舎が内容を確認後、FAMILY連携が解除されることを理解しました</label><button class="danger">退会を申請する</button></form>''' if tenant_options else '<p>退会対象の犬舎連携はありません。</p>'
    body = f'''<h1>退会・主オーナー引継ぎ</h1><div class="tenant"><p>主オーナーを変更する場合は、退会申請より先に引継ぎを行ってください。</p></div>
    <h2>主オーナーを家族へ引き継ぐ</h2>{transfer_cards or '<p>引継ぎ可能な愛犬はありません。</p>'}<h2>FAMILY退会申請</h2>{withdrawal}
    <h2>申請履歴</h2><table><tr><th>犬舎</th><th>申請日</th><th>状態</th><th>データ</th></tr>{request_rows or '<tr><td colspan="4">申請はありません。</td></tr>'}</table>'''
    return family_layout("退会・引継ぎ｜FAMILY", body, user, session)


@app.post("/family/account/transfer")
def family_account_transfer(ownership_id: int = Form(...), successor_ownership_id: int = Form(...), confirmed: bool = Form(False), user: User = Depends(require_user), session: Session = Depends(db)):
    current = session.scalar(select(DogOwnership).where(DogOwnership.id == ownership_id, DogOwnership.user_id == user.id,
        DogOwnership.relationship == "primary", DogOwnership.active.is_(True)))
    successor = session.scalar(select(DogOwnership).where(DogOwnership.id == successor_ownership_id,
        DogOwnership.relationship == "family", DogOwnership.active.is_(True)))
    if not confirmed or not current or not successor or (current.tenant_id, current.dog_id) != (successor.tenant_id, successor.dog_id):
        raise HTTPException(status_code=400, detail="引継ぎ内容を確認できません")
    current.relationship, successor.relationship = "family", "primary"
    session.add(FamilyModerationAudit(tenant_id=current.tenant_id, admin_user_id=user.id, target_type="ownership",
        target_id=current.dog_id, action="primary_owner_transfer", details=f"from={user.id},to={successor.user_id}"))
    session.commit()
    return RedirectResponse("/family/account", status_code=303)


@app.post("/family/account/withdraw")
def family_account_withdraw(tenant_id: int = Form(...), data_policy: str = Form("retain"), reason: str = Form(""), confirmed: bool = Form(False), user: User = Depends(require_user), session: Session = Depends(db)):
    linked = session.scalar(select(DogOwnership.id).where(DogOwnership.tenant_id == tenant_id,
        DogOwnership.user_id == user.id, DogOwnership.active.is_(True)))
    if not confirmed or not linked or data_policy not in {"retain", "remove_personal"} or tenant_id not in family_kennel_tenant_ids(user, session):
        raise HTTPException(status_code=400, detail="退会申請の内容を確認してください")
    pending = session.scalar(select(FamilyWithdrawalRequest.id).where(FamilyWithdrawalRequest.tenant_id == tenant_id,
        FamilyWithdrawalRequest.user_id == user.id, FamilyWithdrawalRequest.status == "requested"))
    if not pending:
        session.add(FamilyWithdrawalRequest(tenant_id=tenant_id, user_id=user.id, data_policy=data_policy, reason=reason.strip()[:500] or None))
        session.commit()
    return RedirectResponse("/family/account", status_code=303)


@app.get("/family/withdrawals/manage", response_class=HTMLResponse)
def family_withdrawals_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    records = session.execute(select(FamilyWithdrawalRequest, User).join(User, User.id == FamilyWithdrawalRequest.user_id)
        .where(FamilyWithdrawalRequest.tenant_id == tenant.id).order_by(FamilyWithdrawalRequest.status, FamilyWithdrawalRequest.requested_at.desc())).all()
    cards = ""
    for request, owner in records:
        policy = "データ保存" if request.data_policy == "retain" else "プロフィール・本人投稿の削除希望"
        form = f'''<form method="post" action="/family/withdrawals/manage/{request.id}"><select name="action"><option value="approve">承認して連携解除</option><option value="reject">申請を差し戻す</option></select><label>管理メモ</label><textarea name="admin_note" maxlength="500"></textarea><button>処理する</button></form>''' if request.status == "requested" else ""
        cards += f'<article class="tenant"><h3>{html.escape(owner.name)}｜{html.escape(owner.email)}</h3><p><span class="badge">{html.escape(request.status)}</span> {policy}</p><p>{html.escape(request.reason or "理由なし")}</p>{form}</article>'
    return layout("FAMILY退会申請", f'<h1>FAMILY退会申請</h1>{cards or "<p>申請はありません。</p>"}', user)


@app.post("/family/withdrawals/manage/{request_id}")
def family_withdrawal_handle(request_id: int, action: str = Form(...), admin_note: str = Form(""), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    admin, tenant = access
    item = session.scalar(select(FamilyWithdrawalRequest).where(FamilyWithdrawalRequest.id == request_id,
        FamilyWithdrawalRequest.tenant_id == tenant.id, FamilyWithdrawalRequest.status == "requested"))
    if not item or action not in {"approve", "reject"}:
        raise HTTPException(status_code=404)
    if action == "approve":
        primary_count = session.scalar(select(func.count(DogOwnership.id)).where(DogOwnership.tenant_id == tenant.id,
            DogOwnership.user_id == item.user_id, DogOwnership.active.is_(True), DogOwnership.relationship == "primary")) or 0
        if primary_count:
            raise HTTPException(status_code=400, detail="主オーナーの愛犬があります。先に家族への引継ぎを行ってください")
        session.execute(text("UPDATE dog_ownerships SET active = FALSE WHERE tenant_id = :tenant_id AND user_id = :user_id"), {"tenant_id": tenant.id, "user_id": item.user_id})
        if item.data_policy == "remove_personal":
            dog_ids = select(Dog.id).where(Dog.tenant_id == tenant.id)
            for post in session.scalars(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.uploaded_by_id == item.user_id, FamilyDogAlbumItem.dog_id.in_(dog_ids))).all():
                session.delete(post)
            other_links = session.scalar(select(func.count(DogOwnership.id)).where(DogOwnership.user_id == item.user_id,
                DogOwnership.tenant_id != tenant.id, DogOwnership.active.is_(True))) or 0
            if not other_links:
                profile = session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == item.user_id))
                if profile:
                    profile.profile_public = False; profile.photo_data = None; profile.bio = None; profile.nickname = None
        item.status = "approved"
    else:
        item.status = "rejected"
    item.handled_by_id, item.handled_at, item.admin_note = admin.id, datetime.now(timezone.utc), admin_note.strip()[:500] or None
    session.add(FamilyModerationAudit(tenant_id=tenant.id, admin_user_id=admin.id, target_type="withdrawal", target_id=item.id,
        action=f"withdrawal_{action}", details=item.admin_note))
    session.commit()
    return RedirectResponse("/family/withdrawals/manage", status_code=303)


@app.get("/family/dashboard/manage", response_class=HTMLResponse)
def family_dashboard_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    owner_ids = select(DogOwnership.user_id).where(DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True)).distinct()
    owners = session.scalar(select(func.count()).select_from(owner_ids.subquery())) or 0
    dog_ids = select(Dog.id).where(Dog.tenant_id == tenant.id)
    posts = session.scalar(select(func.count(FamilyDogAlbumItem.id)).where(FamilyDogAlbumItem.dog_id.in_(dog_ids))) or 0
    open_reports = session.scalar(select(func.count(FamilyTimelineReport.id)).where(FamilyTimelineReport.tenant_id == tenant.id, FamilyTimelineReport.status.in_(["open", "reviewing"]))) or 0
    announcements = session.scalars(select(FamilyAnnouncement).where(FamilyAnnouncement.tenant_id == tenant.id, FamilyAnnouncement.active.is_(True))).all()
    unread = 0
    for announcement in announcements:
        read_count = session.scalar(select(func.count(FamilyAnnouncementRead.id)).where(FamilyAnnouncementRead.announcement_id == announcement.id,
            FamilyAnnouncementRead.user_id.in_(owner_ids))) or 0
        unread += max(owners - read_count, 0)
    event_ids = [item.id for item in announcements if item.event_date]
    attending = session.scalar(select(func.count(func.distinct(FamilyEventResponse.user_id))).where(FamilyEventResponse.announcement_id.in_(event_ids), FamilyEventResponse.status == "attending")) if event_ids else 0
    participation = round((attending or 0) * 100 / max(owners * len(event_ids), 1), 1) if event_ids else 0
    cards = f'''<div class="grid"><article class="tenant"><h2>{owners}</h2><p>登録オーナー</p></article><article class="tenant"><h2>{posts}</h2><p>アルバム投稿</p></article>
    <article class="tenant"><h2>{unread}</h2><p>お知らせ未読（延べ）</p></article><article class="tenant"><h2>{open_reports}</h2><p>未対応・確認中の通報</p></article><article class="tenant"><h2>{participation}%</h2><p>イベント参加率</p></article></div>'''
    recent = session.execute(select(FamilyModerationAudit, User).join(User, User.id == FamilyModerationAudit.admin_user_id)
        .where(FamilyModerationAudit.tenant_id == tenant.id).order_by(FamilyModerationAudit.created_at.desc()).limit(20)).all()
    rows = "".join(f'<tr><td>{audit.created_at.strftime("%Y-%m-%d %H:%M")}</td><td>{html.escape(admin.name)}</td><td>{html.escape(audit.action)}</td><td>{html.escape(audit.details or "－")}</td></tr>' for audit, admin in recent)
    return layout("FAMILY管理ダッシュボード", f'<h1>FAMILY管理ダッシュボード</h1>{cards}<h2>最近の管理操作</h2><table><tr><th>日時</th><th>担当者</th><th>操作</th><th>内容</th></tr>{rows or "<tr><td colspan=\"4\">履歴はありません。</td></tr>"}</table>', user)


FAMILY_DOCUMENT_TYPES = {"terms": "FAMILY利用規約", "message_monitoring": "メッセージ閲覧方針", "photo_privacy": "写真公開・個人情報方針"}


@app.get("/family/terms/manage", response_class=HTMLResponse)
def family_terms_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    versions = session.scalars(select(FamilyTermsVersion).where(FamilyTermsVersion.tenant_id == tenant.id).order_by(FamilyTermsVersion.published_at.desc())).all()
    rows = "".join(f'<tr><td>{html.escape(FAMILY_DOCUMENT_TYPES.get(item.document_type, item.document_type))}</td><td>{html.escape(item.version)}</td><td>{"公開中" if item.active else "旧版"}</td><td>{item.published_at.strftime("%Y-%m-%d")}</td></tr>' for item in versions)
    options = "".join(f'<option value="{key}">{value}</option>' for key, value in FAMILY_DOCUMENT_TYPES.items())
    consent_records = session.execute(select(FamilyConsent, FamilyTermsVersion, User)
        .join(FamilyTermsVersion, FamilyTermsVersion.id == FamilyConsent.terms_version_id)
        .join(User, User.id == FamilyConsent.user_id)
        .where(FamilyConsent.tenant_id == tenant.id).order_by(FamilyConsent.agreed_at.desc()).limit(100)).all()
    consent_rows = "".join(f'<tr><td>{consent.agreed_at.strftime("%Y-%m-%d %H:%M")}</td><td>{html.escape(owner.name)}</td><td>{html.escape(terms.title)}</td><td>{html.escape(terms.version)}</td></tr>' for consent, terms, owner in consent_records)
    body = f'''<h1>利用規約・同意管理</h1><div class="tenant"><p>新しい版を公開すると、同じ種類の旧版は自動的に終了し、オーナーへ再同意が表示されます。</p></div>
    <form method="post"><label>文書の種類</label><select name="document_type">{options}</select><label>版番号</label><input name="version" maxlength="30" placeholder="例：2026-09" required>
    <label>表示タイトル</label><input name="title" maxlength="150" required><label>本文</label><textarea name="body" rows="14" required></textarea><button>新しい版を公開する</button></form>
    <h2>公開履歴</h2><table><tr><th>種類</th><th>版</th><th>状態</th><th>公開日</th></tr>{rows or '<tr><td colspan="4">規約は未登録です。</td></tr>'}</table>
    <h2>同意履歴（最新100件）</h2><table><tr><th>同意日時</th><th>オーナー</th><th>文書</th><th>版</th></tr>{consent_rows or '<tr><td colspan="4">同意履歴はありません。</td></tr>'}</table>'''
    return layout("利用規約・同意管理", body, user)


@app.post("/family/terms/manage")
def family_terms_publish(document_type: str = Form(...), version: str = Form(...), title: str = Form(...), body: str = Form(...), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    version, title, body = version.strip(), title.strip(), body.strip()
    if document_type not in FAMILY_DOCUMENT_TYPES or not version or not title or not body:
        raise HTTPException(status_code=400, detail="規約の内容を確認してください")
    if session.scalar(select(FamilyTermsVersion.id).where(FamilyTermsVersion.tenant_id == tenant.id, FamilyTermsVersion.document_type == document_type, FamilyTermsVersion.version == version)):
        raise HTTPException(status_code=400, detail="同じ版番号がすでに登録されています")
    for old in session.scalars(select(FamilyTermsVersion).where(FamilyTermsVersion.tenant_id == tenant.id, FamilyTermsVersion.document_type == document_type, FamilyTermsVersion.active.is_(True))).all():
        old.active = False
    session.add(FamilyTermsVersion(tenant_id=tenant.id, document_type=document_type, version=version, title=title, body=body, created_by_id=user.id))
    session.commit()
    return RedirectResponse("/family/terms/manage", status_code=303)


@app.get("/family/consents", response_class=HTMLResponse)
def family_consents_page(user: User = Depends(require_user), session: Session = Depends(db)):
    tenant_ids = family_kennel_tenant_ids(user, session)
    versions = session.execute(select(FamilyTermsVersion, Tenant).join(Tenant, Tenant.id == FamilyTermsVersion.tenant_id)
        .where(FamilyTermsVersion.tenant_id.in_(tenant_ids), FamilyTermsVersion.active.is_(True)).order_by(Tenant.name, FamilyTermsVersion.document_type)).all() if tenant_ids else []
    cards = ""
    for item, tenant in versions:
        consent = session.scalar(select(FamilyConsent).where(FamilyConsent.terms_version_id == item.id, FamilyConsent.user_id == user.id))
        state = f'<span class="badge">同意済み {consent.agreed_at.strftime("%Y-%m-%d")}</span>' if consent else f'''<form method="post"><input type="hidden" name="terms_version_id" value="{item.id}"><label style="font-weight:400"><input style="width:auto" type="checkbox" name="accepted" value="true" required> 内容を確認し、同意します</label><button>同意を記録する</button></form>'''
        cards += f'<article class="tenant"><p><small>{html.escape(tenant.name)}｜第{html.escape(item.version)}版</small></p><h2>{html.escape(item.title)}</h2><div style="white-space:pre-wrap">{html.escape(item.body)}</div>{state}</article>'
    return family_layout("規約・同意｜FAMILY", f'<h1>規約・同意</h1>{cards or "<p>現在、確認が必要な規約はありません。</p>"}', user, session)


@app.post("/family/consents")
def family_consent_accept(request: Request, terms_version_id: int = Form(...), accepted: bool = Form(False), user: User = Depends(require_user), session: Session = Depends(db)):
    item = session.scalar(select(FamilyTermsVersion).where(FamilyTermsVersion.id == terms_version_id, FamilyTermsVersion.active.is_(True)))
    if not accepted or not item or item.tenant_id not in family_kennel_tenant_ids(user, session):
        raise HTTPException(status_code=400, detail="同意対象を確認できません")
    if not session.scalar(select(FamilyConsent.id).where(FamilyConsent.terms_version_id == item.id, FamilyConsent.user_id == user.id)):
        remote = request.client.host if request.client else "unknown"
        session.add(FamilyConsent(tenant_id=item.tenant_id, terms_version_id=item.id, user_id=user.id,
            ip_hash=hashlib.sha256(remote.encode()).hexdigest()))
        session.commit()
    return RedirectResponse("/family/consents", status_code=303)


def backup_json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def backup_model(item, exclude: set[str] | None = None) -> dict:
    excluded = exclude or set()
    return {column.name: backup_json_value(getattr(item, column.name)) for column in item.__table__.columns
            if column.name not in excluded and not column.name.endswith("_data")}


@app.get("/family/backups/manage", response_class=HTMLResponse)
def family_backups_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    records = session.execute(select(FamilyBackupAudit, User).join(User, User.id == FamilyBackupAudit.created_by_id)
        .where(FamilyBackupAudit.tenant_id == tenant.id).order_by(FamilyBackupAudit.created_at.desc()).limit(50)).all()
    rows = "".join(f'<tr><td>{audit.created_at.strftime("%Y-%m-%d %H:%M")}</td><td>{html.escape(actor.name)}</td><td>{audit.record_count}</td><td>{html.escape(audit.format.upper())}</td></tr>' for audit, actor in records)
    body = f'''<h1>FAMILYデータ出力・バックアップ</h1><div class="tenant"><p>選択中の犬舎に属するオーナー連携、愛犬、投稿、同意、監査履歴をZIPにまとめます。パスワードやログイントークンは含みません。</p></div>
    <form method="post" action="/family/backups/download"><label>安全確認のため管理者パスワードを入力</label><input type="password" name="admin_password" required autocomplete="current-password">
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="confirmed" value="true" required> 個人情報を含むファイルとして安全に保管します</label><button class="success">ZIPバックアップを作成・ダウンロード</button></form>
    <h2>バックアップ整合性確認</h2><form method="post" action="/family/backups/verify" enctype="multipart/form-data"><label>確認するZIPファイル</label><input type="file" name="backup_file" accept=".zip,application/zip" required><button class="secondary">破損・改ざんを確認</button></form>
    <h2>出力履歴</h2><table><tr><th>日時</th><th>実行者</th><th>レコード数</th><th>形式</th></tr>{rows or '<tr><td colspan="4">出力履歴はありません。</td></tr>'}</table>'''
    return layout("FAMILYデータ出力", body, user)


@app.post("/family/backups/download")
def family_backup_download(admin_password: str = Form(...), confirmed: bool = Form(False), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    if not confirmed or not passwords.verify(admin_password, user.password_hash):
        raise HTTPException(status_code=403, detail="管理者パスワードまたは確認項目を確認してください")
    ownerships = session.scalars(select(DogOwnership).where(DogOwnership.tenant_id == tenant.id)).all()
    owner_ids = sorted({item.user_id for item in ownerships})
    owners = session.scalars(select(User).where(User.id.in_(owner_ids)).order_by(User.id)).all() if owner_ids else []
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id).order_by(Dog.id)).all()
    dog_ids = [dog.id for dog in dogs]
    posts = session.scalars(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.dog_id.in_(dog_ids)).order_by(FamilyDogAlbumItem.id)).all() if dog_ids else []
    audits = session.scalars(select(FamilyModerationAudit).where(FamilyModerationAudit.tenant_id == tenant.id).order_by(FamilyModerationAudit.id)).all()
    consents = session.scalars(select(FamilyConsent).where(FamilyConsent.tenant_id == tenant.id).order_by(FamilyConsent.id)).all()
    terms = session.scalars(select(FamilyTermsVersion).where(FamilyTermsVersion.tenant_id == tenant.id).order_by(FamilyTermsVersion.id)).all()
    manifest = {"schema_version": 1, "tenant": backup_model(tenant), "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"owners": len(owners), "dogs": len(dogs), "ownerships": len(ownerships), "posts": len(posts), "audits": len(audits), "consents": len(consents)}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        datasets = {"owners.json": [backup_model(item, {"password_hash"}) for item in owners], "dogs.json": [backup_model(item) for item in dogs],
            "ownerships.json": [backup_model(item) for item in ownerships], "posts.json": [backup_model(item) for item in posts],
            "moderation_audits.json": [backup_model(item) for item in audits], "terms.json": [backup_model(item) for item in terms],
            "consents.json": [backup_model(item, {"ip_hash"}) for item in consents]}
        checksums = {}
        for filename, records in datasets.items():
            content = json.dumps(records, ensure_ascii=False, indent=2).encode()
            archive.writestr(filename, content); checksums[filename] = hashlib.sha256(content).hexdigest()
        owner_csv = io.StringIO(newline=""); writer = csv.writer(owner_csv); writer.writerow(["user_id", "name", "email", "active"])
        for owner in owners: writer.writerow([owner.id, owner.name, owner.email, owner.active])
        csv_content = ("\ufeff" + owner_csv.getvalue()).encode(); archive.writestr("owners.csv", csv_content)
        checksums["owners.csv"] = hashlib.sha256(csv_content).hexdigest()
        for post in posts:
            extension = "png" if post.photo_content_type == "image/png" else ("webp" if post.photo_content_type == "image/webp" else "jpg")
            photo_name = f"photos/post-{post.id}.{extension}"; archive.writestr(photo_name, post.photo_data)
            checksums[photo_name] = hashlib.sha256(post.photo_data).hexdigest()
        manifest["checksums"] = checksums
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    count = sum(manifest["counts"].values())
    session.add(FamilyBackupAudit(tenant_id=tenant.id, created_by_id=user.id, record_count=count)); session.commit()
    filename = f"family-backup-{tenant.id}-{date.today().isoformat()}.zip"
    return Response(content=output.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@app.post("/family/backups/verify", response_class=HTMLResponse)
async def family_backup_verify(backup_file: UploadFile = File(...), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    content = await backup_file.read(100 * 1024 * 1024 + 1)
    errors: list[str] = []
    if len(content) > 100 * 1024 * 1024:
        errors.append("ファイルサイズが100MBを超えています")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > 5000 or sum(item.file_size for item in infos) > 1024 * 1024 * 1024:
                errors.append("展開後の容量またはファイル数が安全上限を超えています")
            names = {item.filename for item in infos}
            if "manifest.json" not in names:
                errors.append("manifest.jsonがありません")
            else:
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get("schema_version") != 1 or manifest.get("tenant", {}).get("id") != tenant.id:
                    errors.append("選択中の犬舎のバックアップではありません")
                checksums = manifest.get("checksums") or {}
                if not checksums:
                    errors.append("整合性情報がない旧形式のバックアップです")
                for filename, expected in checksums.items():
                    if filename not in names or hashlib.sha256(archive.read(filename)).hexdigest() != expected:
                        errors.append(f"{filename}の整合性を確認できません")
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, TypeError, ValueError):
        errors.append("有効なFAMILYバックアップZIPではありません")
    result = "failed" if errors else "success"
    record_operation(session, "backup_verify", result, "バックアップ整合性確認", tenant.id,
        " / ".join(errors) if errors else f"file={backup_file.filename or 'backup.zip'}")
    session.commit()
    if errors:
        body = '<h1>整合性確認：問題あり</h1><p class="error">' + html.escape("／".join(errors)) + '</p>'
        return HTMLResponse(layout("バックアップ整合性確認", body + '<a class="button secondary" href="/family/backups/manage">戻る</a>', user), status_code=400)
    return layout("バックアップ整合性確認", '<h1>整合性確認：正常</h1><p>破損や内容の改変は検出されませんでした。</p><a class="button secondary" href="/family/backups/manage">戻る</a>', user)


def require_mobile_user(authorization: str | None = Header(None), session: Session = Depends(db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="認証が必要です")
    raw = authorization.removeprefix("Bearer ").strip()
    token = session.scalar(select(MobileApiToken).where(MobileApiToken.token_hash == token_hash(raw), MobileApiToken.revoked_at.is_(None)))
    if not token:
        raise HTTPException(status_code=401, detail="認証トークンが無効です")
    expires = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="認証トークンの期限が切れています")
    user = session.get(User, token.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="アカウントを利用できません")
    token.last_used_at = datetime.now(timezone.utc); session.commit()
    return user


@app.post("/api/v1/auth/token")
async def mobile_auth_token(request: Request, session: Session = Depends(db)):
    payload = await request.json()
    email, password = normalize_email(str(payload.get("email", ""))), str(payload.get("password", ""))
    throttle_key = auth_throttle_key(request, "mobile-login", email)
    if auth_throttle_blocked(throttle_key, session):
        raise HTTPException(status_code=429, detail="ログイン試行が多いため、15分後にもう一度お試しください")
    user = session.scalar(select(User).where(User.email == email, User.active.is_(True)))
    if not user or not password or not passwords.verify(password, user.password_hash):
        auth_throttle_failure(throttle_key, session)
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが違います")
    auth_throttle_success(throttle_key, session)
    raw = secrets.token_urlsafe(48)
    token = MobileApiToken(user_id=user.id, token_hash=token_hash(raw), device_name=str(payload.get("device_name", "スマートフォン"))[:100] or "スマートフォン",
        expires_at=datetime.now(timezone.utc) + timedelta(days=90))
    session.add(token); session.commit()
    return {"access_token": raw, "token_type": "bearer", "expires_in": 90 * 86400, "api_version": "v1"}


@app.post("/api/v1/auth/revoke")
def mobile_auth_revoke(authorization: str | None = Header(None), user: User = Depends(require_mobile_user), session: Session = Depends(db)):
    raw = (authorization or "").removeprefix("Bearer ").strip()
    token = session.scalar(select(MobileApiToken).where(MobileApiToken.token_hash == token_hash(raw), MobileApiToken.user_id == user.id))
    if token: token.revoked_at = datetime.now(timezone.utc); session.commit()
    return {"ok": True}


@app.get("/api/v1/me")
def mobile_me(user: User = Depends(require_mobile_user)):
    return {"id": user.id, "name": user.name, "email": user.email}


@app.get("/api/v1/dogs")
def mobile_dogs(user: User = Depends(require_mobile_user), session: Session = Depends(db)):
    records = session.execute(select(DogOwnership, Dog, Tenant).join(Dog, Dog.id == DogOwnership.dog_id).join(Tenant, Tenant.id == DogOwnership.tenant_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True), Tenant.active.is_(True), Tenant.deleted.is_(False)).order_by(Dog.call_name)).all()
    return {"dogs": [{"id": dog.id, "call_name": dog.call_name, "registered_name": dog.registered_name, "breed": dog.breed, "sex": dog.sex,
        "birth_date": dog.birth_date.isoformat() if dog.birth_date else None, "color": dog.color, "relationship": ownership.relationship,
        "tenant": {"id": tenant.id, "name": tenant.name}, "photo_url": f"/api/v1/dogs/{dog.id}/photo"} for ownership, dog, tenant in records]}


@app.get("/api/v1/dogs/{dog_id}/photo")
def mobile_dog_photo(dog_id: int, user: User = Depends(require_mobile_user), session: Session = Depends(db)):
    if not session.scalar(select(DogOwnership.id).where(DogOwnership.dog_id == dog_id, DogOwnership.user_id == user.id, DogOwnership.active.is_(True))):
        raise HTTPException(status_code=404)
    profile = session.scalar(select(FamilyDogProfile).where(FamilyDogProfile.dog_id == dog_id))
    if not profile or not profile.photo_data: raise HTTPException(status_code=404)
    return Response(content=profile.photo_data, media_type=profile.photo_content_type or "image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/v1/notifications")
def mobile_notifications(user: User = Depends(require_mobile_user), session: Session = Depends(db)):
    items = []
    for conversation, message in family_unread_message_items(user, session):
        items.append({"type": "message", "id": message.id, "title": "新着メッセージ", "body": message.body[:120], "created_at": message.sent_at.isoformat(), "url": f"/family/messages/{conversation.id}"})
    for announcement, tenant in family_unread_announcements(user, session):
        items.append({"type": "announcement", "id": announcement.id, "title": announcement.title, "body": tenant.name, "created_at": announcement.created_at.isoformat(), "url": f"/family/announcements/view/{announcement.id}"})
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"notifications": items[:100]}


@app.get("/api/v1/timeline")
def mobile_timeline(limit: int = 30, offset: int = 0, user: User = Depends(require_mobile_user), session: Session = Depends(db)):
    limit, offset = min(max(limit, 1), 100), max(offset, 0)
    records = sorted(family_timeline_items(user, session).values(), key=lambda value: value[0].created_at, reverse=True)
    page = records[offset:offset + limit]
    return {"items": [{"id": item.id, "dog": {"id": dog.id, "call_name": dog.call_name}, "tenant": {"id": tenant.id, "name": tenant.name},
        "caption": item.caption, "taken_on": item.taken_on.isoformat() if item.taken_on else None, "visibility": item.visibility,
        "created_at": item.created_at.isoformat(), "photo_url": f"/api/v1/timeline/{item.id}/photo"} for item, dog, tenant, _ in page],
        "limit": limit, "offset": offset, "has_more": offset + limit < len(records)}


@app.get("/api/v1/timeline/{item_id}/photo")
def mobile_timeline_photo(item_id: int, user: User = Depends(require_mobile_user), session: Session = Depends(db)):
    record = family_timeline_items(user, session).get(item_id)
    if not record: raise HTTPException(status_code=404)
    item = record[0]
    return Response(content=item.photo_data, media_type=item.photo_content_type, headers={"Cache-Control": "private, max-age=300"})


@app.get("/family/devices", response_class=HTMLResponse)
def family_devices(user: User = Depends(require_user), session: Session = Depends(db)):
    tokens = session.scalars(select(MobileApiToken).where(MobileApiToken.user_id == user.id).order_by(MobileApiToken.created_at.desc())).all()
    rows = "".join(f'<tr><td>{html.escape(token.device_name)}</td><td>{token.created_at.strftime("%Y-%m-%d")}</td><td>{token.last_used_at.strftime("%Y-%m-%d %H:%M") if token.last_used_at else "未使用"}</td><td>{"解除済み" if token.revoked_at else "連携中"}</td><td>{f"<form method=\"post\" action=\"/family/devices/{token.id}/revoke\"><button class=\"secondary\">解除</button></form>" if not token.revoked_at else "－"}</td></tr>' for token in tokens)
    body = f'''<h1>アプリ・通知端末</h1><div class="tenant"><p>将来のiOS／Androidアプリは、FAMILYと同じメールアドレス・パスワードで連携します。端末ごとに90日間有効な専用トークンを発行し、パスワード自体は端末へ保存しません。</p></div>
    <p><a class="button secondary" href="/family/notification-settings">ブラウザ通知を設定</a></p><h2>スマートフォンアプリ連携</h2><table><tr><th>端末</th><th>連携日</th><th>最終利用</th><th>状態</th><th>操作</th></tr>{rows or '<tr><td colspan="5">アプリ連携端末はありません。</td></tr>'}</table>'''
    return family_layout("アプリ・端末｜FAMILY", body, user, session)


@app.post("/family/devices/{token_id}/revoke")
def family_device_revoke(token_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    token = session.scalar(select(MobileApiToken).where(MobileApiToken.id == token_id, MobileApiToken.user_id == user.id))
    if not token: raise HTTPException(status_code=404)
    token.revoked_at = datetime.now(timezone.utc); session.commit()
    return RedirectResponse("/family/devices", status_code=303)


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
        common_tenant = min(family_kennel_tenant_ids(user, session) & family_kennel_tenant_ids(target_user, session))
        message_button = f'''<form method="post" action="/family/messages/start/{profile.public_id}"><button>メッセージを送る</button></form><p><a href="/family/safety/report?target_type=profile&amp;target_id={profile.user_id}&amp;tenant_id={common_tenant}"><small>このプロフィールを犬舎へ通報</small></a></p>'''
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
        try:
            email_change_target(owner.id, user, tenant, session)
            email_action = f'<a class="button secondary" href="/family/owners/{owner.id}/email">メール変更</a>'
        except HTTPException:
            email_action = '<span class="badge">運営管理者のみ変更可</span>'
        rows += f'''<tr><td>{html.escape(dog.call_name)}</td><td>{html.escape(owner.name)}</td><td>{html.escape(owner.email)}</td><td>{relation}</td>
        <td>{email_action} <form class="inline" method="post" action="/family/owners/{ownership.id}/remove"><button class="secondary">連携解除</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/admin/users">ユーザー管理へ戻る</a> <a class="button success" href="/family/invitations">オーナー様を招待</a>
    <h1>{html.escape(tenant.name)} オーナー連携</h1>
    <p>オーナーが登録したメールアドレスと犬を結び付けます。1人に複数頭、ご家族に同じ犬を連携できます。</p>
    <form method="post"><label>犬</label><select name="dog_id" required>{dog_options}</select>
    <label>登録済みオーナーのメールアドレス</label><input name="email" type="email" required>
    <label>関係</label><select name="relationship"><option value="primary">主オーナー</option><option value="family">ご家族</option></select>
    <button>犬とオーナーを連携</button></form>
    <h2>現在の連携</h2><table><tr><th>犬</th><th>オーナー</th><th>メール</th><th>関係</th><th>操作</th></tr>{rows}</table>'''
    return layout("オーナー連携", body, user)


def email_change_target(user_id: int, actor: User, tenant: Tenant, session: Session) -> tuple[User, set[int]]:
    target = session.get(User, user_id)
    if not target or not target.active or target.id == actor.id:
        raise HTTPException(status_code=404, detail="変更対象のアカウントが見つかりません")
    tenant_ids = set(session.scalars(select(DogOwnership.tenant_id).where(
        DogOwnership.user_id == target.id, DogOwnership.active.is_(True)
    )).all())
    tenant_ids.update(session.scalars(select(Membership.tenant_id).where(Membership.user_id == target.id)).all())
    if tenant.id not in tenant_ids:
        raise HTTPException(status_code=404, detail="この犬舎と関係するアカウントではありません")
    roles = set(session.scalars(select(Membership.role).where(Membership.user_id == target.id)).all())
    customer_only = not target.platform_admin and target.role == Role.customer and roles.issubset({Role.customer})
    if not actor.platform_admin and (tenant_ids != {tenant.id} or not customer_only):
        raise HTTPException(status_code=403, detail="複数犬舎に関係するアカウント、管理者・従業員のメール変更は運営管理者だけが行えます")
    return target, tenant_ids


@app.get("/family/owners/{user_id}/email", response_class=HTMLResponse)
def family_owner_email_edit(user_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    target, tenant_ids = email_change_target(user_id, actor, tenant, session)
    dogs = session.scalars(
        select(Dog.call_name).join(DogOwnership, DogOwnership.dog_id == Dog.id)
        .where(DogOwnership.user_id == target.id, DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))
        .order_by(Dog.call_name)
    ).all()
    histories = session.execute(
        select(AccountEmailChangeAudit, User).join(User, User.id == AccountEmailChangeAudit.changed_by_id)
        .where(AccountEmailChangeAudit.target_user_id == target.id).order_by(AccountEmailChangeAudit.changed_at.desc()).limit(20)
    ).all()
    history_rows = "".join(
        f'''<tr><td>{audit.changed_at.strftime('%Y-%m-%d %H:%M')}</td><td>{html.escape(audit.old_email)}</td>
        <td>{html.escape(audit.new_email)}</td><td>{html.escape(changer.name)}</td></tr>''' for audit, changer in histories
    )
    scope_notice = "複数犬舎に関係するため、運営管理者権限で変更します。" if len(tenant_ids) > 1 else "この犬舎だけに関係するオーナーアカウントです。"
    body = f'''<a class="button secondary" href="/family/owners">オーナー連携へ戻る</a><h1>登録メールアドレス変更</h1>
    <div class="tenant"><p><strong>オーナー：</strong>{html.escape(target.name)}</p><p><strong>愛犬：</strong>{html.escape("、".join(dogs) or "連携なし")}</p>
    <p><strong>現在：</strong>{html.escape(target.email)}</p><p><small>{scope_notice}</small></p></div>
    <div class="tenant"><p><strong>重要な操作です</strong></p><p>変更後は旧メールアドレスでログインできません。安全のため、このアカウントのログイン中セッションをすべて終了します。</p></div>
    <form method="post"><label>新しいメールアドレス</label><input type="email" name="new_email" required autocomplete="off">
    <label>確認のため、あなたの管理者パスワードを入力</label><input type="password" name="admin_password" required autocomplete="current-password">
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="confirmed" value="true" required> オーナー様本人から変更依頼を受け、内容を確認しました</label>
    <button class="danger">登録メールアドレスを変更する</button></form>
    <h2>変更履歴</h2><table><tr><th>変更日時</th><th>変更前</th><th>変更後</th><th>担当者</th></tr>{history_rows or '<tr><td colspan="4">変更履歴はありません。</td></tr>'}</table>'''
    return layout("登録メールアドレス変更", body, actor)


@app.post("/family/owners/{user_id}/email")
def family_owner_email_update(
    user_id: int, new_email: str = Form(...), admin_password: str = Form(...), confirmed: bool = Form(False),
    access=Depends(require_tenant_admin), session: Session = Depends(db),
):
    actor, tenant = access
    target, tenant_ids = email_change_target(user_id, actor, tenant, session)
    normalized = normalize_email(new_email)
    if not confirmed or not passwords.verify(admin_password, actor.password_hash):
        raise HTTPException(status_code=403, detail="管理者パスワードまたは確認項目を確認してください")
    if len(normalized) > 255 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=400, detail="新しいメールアドレスの形式を確認してください")
    duplicate = session.scalar(select(User.id).where(func.lower(User.email) == normalized, User.id != target.id).limit(1))
    if duplicate:
        raise HTTPException(status_code=400, detail="このメールアドレスは別のアカウントで使用されています")
    if normalized == normalize_email(target.email):
        raise HTTPException(status_code=400, detail="現在と同じメールアドレスです")
    old_email = target.email
    customer_ids = set(session.scalars(select(DogOwnership.customer_id).where(
        DogOwnership.user_id == target.id, DogOwnership.tenant_id.in_(tenant_ids),
        DogOwnership.customer_id.is_not(None), DogOwnership.active.is_(True),
    )).all())
    linked_customers = session.scalars(select(Customer).where(
        Customer.id.in_(customer_ids), func.lower(Customer.email) == normalize_email(old_email)
    )).all() if customer_ids else []
    target.email = normalized
    for customer in linked_customers:
        customer.email = normalized
    session.add(AccountEmailChangeAudit(
        tenant_id=tenant.id, target_user_id=target.id, changed_by_id=actor.id,
        old_email=old_email, new_email=normalized, linked_customers_updated=len(linked_customers),
    ))
    notice = f'''{target.name} 様

ESTRELLA FAMILYの登録メールアドレスが変更されました。
変更前：{old_email}
変更後：{normalized}

今後は新しいメールアドレスでログインしてください。お心当たりがない場合は、すぐに犬舎へご連絡ください。'''
    queue_email(session, old_email, "email_changed", "【ESTRELLA FAMILY】登録メールアドレス変更のお知らせ", notice, tenant.id, target.id)
    queue_email(session, normalized, "email_changed", "【ESTRELLA FAMILY】登録メールアドレス変更のお知らせ", notice, tenant.id, target.id)
    session.execute(text("DELETE FROM login_sessions WHERE user_id = :user_id"), {"user_id": target.id})
    session.commit()
    return RedirectResponse(f"/family/owners/{target.id}/email", status_code=303)


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


@app.get("/admin/password-resets", response_class=HTMLResponse)
def password_reset_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    related_ids = set(session.scalars(select(DogOwnership.user_id).where(DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))).all())
    related_ids.update(session.scalars(select(Membership.user_id).where(Membership.tenant_id == tenant.id)).all())
    records = session.execute(
        select(PasswordResetRequest, User).join(User, User.id == PasswordResetRequest.user_id)
        .where(PasswordResetRequest.user_id.in_(related_ids), PasswordResetRequest.resolved_at.is_(None))
        .order_by(PasswordResetRequest.requested_at.desc()).limit(100)
    ).all() if related_ids else []
    rows = ""
    for request_item, account in records:
        try:
            email_change_target(account.id, actor, tenant, session)
            action = f'<form method="post" action="/admin/password-resets/{request_item.id}/issue"><label>管理者パスワード</label><input type="password" name="admin_password" required><button>再設定リンクを発行</button></form>'
        except HTTPException:
            action = '<span class="badge">運営管理者のみ対応可</span>'
        rows += f'''<tr><td>{html.escape(account.name)}</td><td>{html.escape(account.email)}</td><td>{request_item.requested_at.strftime('%Y-%m-%d %H:%M')}</td><td>{action}</td></tr>'''
    body = f'''<h1>パスワード再設定申込み</h1><p>本人確認後に一度だけ使える再設定リンクを発行し、オーナー様へ安全な方法でお伝えください。有効期限は30分です。</p>
    <table><tr><th>お名前</th><th>登録メール</th><th>申込日時</th><th>対応</th></tr>{rows or '<tr><td colspan="4">未対応の申込みはありません。</td></tr>'}</table>'''
    return layout("パスワード再設定管理", body, actor)


@app.get("/admin/email-deliveries", response_class=HTMLResponse)
def email_deliveries_manage(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    related_ids = set(session.scalars(select(DogOwnership.user_id).where(DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))).all())
    condition = EmailDelivery.tenant_id == tenant.id
    if related_ids:
        condition = condition | EmailDelivery.user_id.in_(related_ids)
    records = session.scalars(select(EmailDelivery).where(condition).order_by(EmailDelivery.created_at.desc()).limit(200)).all()
    rows = ""
    for delivery in records:
        retry = f'<form method="post" action="/admin/email-deliveries/{delivery.id}/retry"><button class="secondary">再送</button></form>' if delivery.status != "sent" and delivery.purpose != "password_reset" else "－"
        rows += f'''<tr><td>{delivery.created_at.strftime('%Y-%m-%d %H:%M')}</td><td>{html.escape(delivery.recipient)}</td><td>{html.escape(delivery.subject)}</td>
        <td>{html.escape(delivery.status)}</td><td>{delivery.attempts}</td><td>{html.escape(delivery.error or "－")}</td><td>{retry}</td></tr>'''
    state = "送信可能" if smtp_ready() else "未設定（SMTP_HOST・SMTP_FROM_EMAIL等を設定してください）"
    body = f'''<h1>メール送信履歴</h1><div class="tenant"><p><strong>配信設定：</strong>{state}</p><p>失敗した通常通知は設定修正後に再送できます。パスワード再設定リンクは安全のため再送せず、新しいリンクを発行します。</p></div>
    <table><tr><th>作成日時</th><th>宛先</th><th>件名</th><th>状態</th><th>試行</th><th>エラー</th><th>操作</th></tr>{rows or '<tr><td colspan="7">送信履歴はありません。</td></tr>'}</table>'''
    return layout("メール送信履歴", body, actor)


def notification_delivery_export_items(tenant: Tenant, delivery_status: str, channel: str, notification_category: str,
                                       date_from: str, date_to: str, owner_keyword: str, session: Session):
    allowed_statuses = {"", "sent", "failed", "pending"}; allowed_channels = {"", "line", "email", "browser"}; allowed_categories = {"", "anniversary", "health", "test"}
    if delivery_status not in allowed_statuses or channel not in allowed_channels or notification_category not in allowed_categories:
        raise HTTPException(status_code=400, detail="検索条件を確認してください")
    try:
        start_filter = date.fromisoformat(date_from) if date_from else None; end_filter = date.fromisoformat(date_to) if date_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail="検索期間を確認してください")
    if start_filter and end_filter and start_filter > end_filter: raise HTTPException(status_code=400, detail="終了日は開始日以降にしてください")
    related_ids = set(session.scalars(select(DogOwnership.user_id).where(DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))).all())
    owners = {item.id: item.name for item in session.scalars(select(User).where(User.id.in_(related_ids))).all()} if related_ids else {}
    items: list[tuple[datetime, str, str, str, str, int, datetime | None, str]] = []
    line_categories = {"anniversaries", "health_vaccinations", "health_checkups", "health_medications", "health_followups", "test"}
    for delivery in session.scalars(select(LineDelivery).where(LineDelivery.tenant_id == tenant.id, LineDelivery.category.in_(line_categories)).order_by(LineDelivery.created_at.desc()).limit(500)).all():
        items.append((delivery.created_at, owners.get(delivery.user_id, "－") or "－", "LINE（主通知）", delivery.category, delivery.status, delivery.attempts or 0, delivery.sent_at, delivery.error or "－"))
    if related_ids:
        for delivery in session.scalars(select(EmailDelivery).where(EmailDelivery.user_id.in_(related_ids), EmailDelivery.purpose.in_(["health_reminder", "anniversary"])).order_by(EmailDelivery.created_at.desc()).limit(500)).all():
            items.append((delivery.created_at, owners.get(delivery.user_id, "－") or "－", "メール（予備）", delivery.purpose, delivery.status, delivery.attempts or 0, delivery.sent_at, delivery.error or "－"))
        for receipt in session.scalars(select(FamilyPushReceipt).where(FamilyPushReceipt.user_id.in_(related_ids), (FamilyPushReceipt.dedupe_key.like("push:health:%") | FamilyPushReceipt.dedupe_key.like("push:anniversary:%"))).order_by(FamilyPushReceipt.created_at.desc()).limit(500)).all():
            category = "anniversary" if "anniversary" in receipt.dedupe_key else "health"
            items.append((receipt.created_at, owners.get(receipt.user_id, "－") or "－", "ブラウザ（予備）", category, receipt.status, 1, receipt.created_at if receipt.status == "sent" else None, "－"))
    category_group = lambda value: "anniversary" if "anniversar" in value else ("test" if value == "test" else "health")
    channel_labels = {"line": "LINE（主通知）", "email": "メール（予備）", "browser": "ブラウザ（予備）"}; normalized_owner = owner_keyword.strip().lower()[:100]
    items = [item for item in items if (not delivery_status or item[4] == delivery_status) and (not channel or item[2] == channel_labels[channel]) and
             (not notification_category or category_group(item[3]) == notification_category) and (not start_filter or item[0].date() >= start_filter) and
             (not end_filter or item[0].date() <= end_filter) and (not normalized_owner or normalized_owner in item[1].lower())]
    items.sort(key=lambda item: item[0], reverse=True)
    return items[:1000]


@app.get("/admin/notification-deliveries", response_class=HTMLResponse)
def notification_deliveries_manage(retry: str = "", delivery_status: str = "", channel: str = "", notification_category: str = "",
                                   date_from: str = "", date_to: str = "", owner_keyword: str = "",
                                   access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    allowed_statuses = {"", "sent", "failed", "pending"}
    allowed_channels = {"", "line", "email", "browser"}
    allowed_categories = {"", "anniversary", "health", "test"}
    if delivery_status not in allowed_statuses or channel not in allowed_channels or notification_category not in allowed_categories:
        raise HTTPException(status_code=400, detail="検索条件を確認してください")
    try:
        start_filter = date.fromisoformat(date_from) if date_from else None
        end_filter = date.fromisoformat(date_to) if date_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail="検索期間を確認してください")
    if start_filter and end_filter and start_filter > end_filter:
        raise HTTPException(status_code=400, detail="終了日は開始日以降にしてください")
    normalized_owner = owner_keyword.strip().lower()[:100]
    related_ids = set(session.scalars(select(DogOwnership.user_id).where(
        DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))).all())
    owners = {item.id: item.name for item in session.scalars(select(User).where(User.id.in_(related_ids))).all()} if related_ids else {}
    items: list[tuple[datetime, str, str, str, str, int, datetime | None, str, str]] = []
    line_categories = {"anniversaries", "health_vaccinations", "health_checkups", "health_medications", "health_followups", "test"}
    line_records = session.scalars(select(LineDelivery).where(
        LineDelivery.tenant_id == tenant.id, LineDelivery.category.in_(line_categories)
    ).order_by(LineDelivery.created_at.desc()).limit(200)).all()
    for delivery in line_records:
        action = (f'''<form method="post" action="/admin/notification-deliveries/line/{delivery.id}/retry"><label style="font-weight:400;white-space:nowrap"><input type="checkbox" name="confirm_retry" value="true" style="width:auto" required> 再送確認</label><button class="secondary" style="margin:4px 0 0">LINE再送</button></form>'''
                  if delivery.status != "sent" and delivery.message and delivery.target_url else "－")
        items.append((delivery.created_at, owners.get(delivery.user_id, "－") or "－", "LINE（主通知）", delivery.category,
                      delivery.status, delivery.attempts or 0, delivery.sent_at, delivery.error or "－", action))
    if related_ids:
        email_records = session.scalars(select(EmailDelivery).where(
            EmailDelivery.user_id.in_(related_ids), EmailDelivery.purpose.in_(["health_reminder", "anniversary"])
        ).order_by(EmailDelivery.created_at.desc()).limit(200)).all()
        for delivery in email_records:
            action = (f'''<form method="post" action="/admin/notification-deliveries/email/{delivery.id}/retry"><label style="font-weight:400;white-space:nowrap"><input type="checkbox" name="confirm_retry" value="true" style="width:auto" required> 再送確認</label><button class="secondary" style="margin:4px 0 0">メール再送</button></form>'''
                      if delivery.status != "sent" and delivery.purpose != "password_reset" else "－")
            items.append((delivery.created_at, owners.get(delivery.user_id, "－") or "－", "メール（予備）", delivery.purpose,
                          delivery.status, delivery.attempts or 0, delivery.sent_at, delivery.error or "－", action))
        push_records = session.scalars(select(FamilyPushReceipt).where(
            FamilyPushReceipt.user_id.in_(related_ids),
            (FamilyPushReceipt.dedupe_key.like("push:health:%") | FamilyPushReceipt.dedupe_key.like("push:anniversary:%"))
        ).order_by(FamilyPushReceipt.created_at.desc()).limit(200)).all()
        for receipt in push_records:
            category = "anniversary" if "anniversary" in receipt.dedupe_key else "health"
            items.append((receipt.created_at, owners.get(receipt.user_id, "－") or "－", "ブラウザ（予備）", category,
                          receipt.status, 1, receipt.created_at if receipt.status == "sent" else None, "－", "－"))
    items.sort(key=lambda item: item[0], reverse=True)
    items = items[:300]
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    success_count = sum(1 for item in items if (item[0] if item[0].tzinfo else item[0].replace(tzinfo=timezone.utc)) >= since and item[4] == "sent")
    failed_count = sum(1 for item in items if (item[0] if item[0].tzinfo else item[0].replace(tzinfo=timezone.utc)) >= since and item[4] not in {"sent", "pending"})
    last_sent = max((item[6] for item in items if item[6]), default=None)
    labels = {"anniversaries": "記念日", "anniversary": "記念日", "health_vaccinations": "ワクチン", "health_checkups": "健診",
              "health_medications": "投薬", "health_followups": "再診・経過確認", "health_reminder": "健康予定", "health": "健康予定", "test": "テスト"}
    all_count = len(items)
    def category_group(value: str) -> str:
        if "anniversar" in value: return "anniversary"
        if value == "test": return "test"
        return "health"
    channel_labels = {"line": "LINE（主通知）", "email": "メール（予備）", "browser": "ブラウザ（予備）"}
    items = [item for item in items if
             (not delivery_status or item[4] == delivery_status) and
             (not channel or item[2] == channel_labels[channel]) and
             (not notification_category or category_group(item[3]) == notification_category) and
             (not start_filter or item[0].date() >= start_filter) and
             (not end_filter or item[0].date() <= end_filter) and
             (not normalized_owner or normalized_owner in item[1].lower())]
    status_options = "".join(f'<option value="{value}" {"selected" if delivery_status == value else ""}>{label}</option>' for value, label in (("", "すべて"), ("sent", "成功"), ("failed", "失敗"), ("pending", "保留")))
    channel_options = "".join(f'<option value="{value}" {"selected" if channel == value else ""}>{label}</option>' for value, label in (("", "すべて"), ("line", "LINE"), ("email", "メール"), ("browser", "ブラウザ")))
    category_options = "".join(f'<option value="{value}" {"selected" if notification_category == value else ""}>{label}</option>' for value, label in (("", "すべて"), ("health", "健康予定"), ("anniversary", "記念日"), ("test", "テスト")))
    export_query = urlencode({key: value for key, value in {"delivery_status": delivery_status, "channel": channel, "notification_category": notification_category, "date_from": date_from, "date_to": date_to, "owner_keyword": owner_keyword[:100]}.items() if value})
    csv_url = f'/admin/notification-deliveries/report.csv{f"?{export_query}" if export_query else ""}'; pdf_url = f'/admin/notification-deliveries/report.pdf{f"?{export_query}" if export_query else ""}'
    search_form = f'''<form method="get" action="/admin/notification-deliveries"><h2>配信履歴を検索</h2><div class="grid"><div><label>結果</label><select name="delivery_status">{status_options}</select></div><div><label>配信経路</label><select name="channel">{channel_options}</select></div><div><label>通知種類</label><select name="notification_category">{category_options}</select></div><div><label>開始日</label><input type="date" name="date_from" value="{html.escape(date_from)}"></div><div><label>終了日</label><input type="date" name="date_to" value="{html.escape(date_to)}"></div><div><label>オーナー名</label><input type="search" name="owner_keyword" value="{html.escape(owner_keyword[:100])}" maxlength="100" placeholder="氏名の一部"></div></div><button>履歴を検索</button> <a class="button secondary" href="/admin/notification-deliveries">条件をクリア</a> <a class="button secondary" href="{csv_url}">表示条件でCSV出力</a> <a class="button secondary" href="{pdf_url}">表示条件でPDF出力</a></form><p><strong>{len(items)}件</strong>／全{all_count}件を表示</p>'''
    rows = "".join(f'''<tr><td>{created.strftime("%Y-%m-%d %H:%M")}</td><td>{html.escape(owner)}</td><td>{html.escape(channel)}</td>
        <td>{html.escape(labels.get(category, category))}</td><td><span class="badge">{html.escape(status)}</span></td><td>{attempts}</td>
        <td>{sent_at.strftime("%Y-%m-%d %H:%M") if sent_at else "－"}</td><td>{html.escape(error)}</td><td>{action}</td></tr>'''
        for created, owner, channel, category, status, attempts, sent_at, error, action in items)
    retry_notice = {"sent": '<p class="tenant"><strong>再送に成功しました。</strong></p>', "failed": '<p class="error">再送に失敗しました。失敗理由と配信設定を確認してください。</p>'}.get(retry, "")
    body = f'''<h1>健康・記念日通知の配信履歴</h1>{retry_notice}<p>LINEを主通知、メールとブラウザ通知を予備経路としてまとめて確認します。</p>
    <div class="grid"><div class="tenant"><strong>24時間の成功</strong><h2>{success_count}件</h2></div>
    <div class="tenant"><strong>24時間の失敗</strong><h2 class="{'error' if failed_count else ''}">{failed_count}件</h2></div>
    <div class="tenant"><strong>最終配信日時</strong><h2>{last_sent.strftime("%Y-%m-%d %H:%M") if last_sent else "配信なし"}</h2></div>
    <div class="tenant"><strong>主通知</strong><h2>LINE</h2><small>メール・ブラウザは予備</small></div></div>
    <p><a class="button secondary" href="/family/line/manage">LINE公式設定</a> <a class="button secondary" href="/admin/email-deliveries">メール送信履歴</a></p>
    {search_form}
    <div style="overflow-x:auto"><table><tr><th>作成日時</th><th>オーナー</th><th>経路</th><th>種類</th><th>結果</th><th>試行</th><th>最終配信</th><th>失敗理由</th><th>操作</th></tr>
    {rows or '<tr><td colspan="9">条件に一致する配信履歴はありません。</td></tr>'}</table></div>'''
    return layout("通知配信履歴", body, actor)


@app.get("/admin/notification-deliveries/report.csv")
def notification_deliveries_report_csv(delivery_status: str = "", channel: str = "", notification_category: str = "", date_from: str = "", date_to: str = "", owner_keyword: str = "", access=Depends(require_tenant_admin), session: Session = Depends(db)):
    _, tenant = access
    items = notification_delivery_export_items(tenant, delivery_status, channel, notification_category, date_from, date_to, owner_keyword, session)
    labels = {"anniversaries": "記念日", "anniversary": "記念日", "health_vaccinations": "ワクチン", "health_checkups": "健診", "health_medications": "投薬", "health_followups": "再診・経過確認", "health_reminder": "健康予定", "health": "健康予定", "test": "テスト"}
    def safe_csv_cell(value) -> str:
        text_value = str(value or "").replace("\x00", "")
        return "'" + text_value if text_value.startswith(("=", "+", "-", "@")) else text_value
    output = io.StringIO(newline=""); writer = csv.writer(output); writer.writerow(["作成日時", "オーナー", "配信経路", "通知種類", "結果", "試行回数", "最終配信日時", "失敗理由"])
    for created, owner, delivery_channel, category, status_value, attempts, sent_at, error in items:
        writer.writerow([safe_csv_cell(value) for value in [created.strftime("%Y-%m-%d %H:%M"), owner, delivery_channel, labels.get(category, category), status_value, attempts, sent_at.strftime("%Y-%m-%d %H:%M") if sent_at else "", "" if error == "－" else error]])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="notification-deliveries-tenant-{tenant.id}.csv"', "Cache-Control": "private, no-store"})


@app.get("/admin/notification-deliveries/report.pdf")
def notification_deliveries_report_pdf(delivery_status: str = "", channel: str = "", notification_category: str = "", date_from: str = "", date_to: str = "", owner_keyword: str = "", access=Depends(require_tenant_admin), session: Session = Depends(db)):
    _, tenant = access
    items = notification_delivery_export_items(tenant, delivery_status, channel, notification_category, date_from, date_to, owner_keyword, session)
    labels = {"anniversaries": "記念日", "anniversary": "記念日", "health_vaccinations": "ワクチン", "health_checkups": "健診", "health_medications": "投薬", "health_followups": "再診・経過確認", "health_reminder": "健康予定", "health": "健康予定", "test": "テスト"}
    output = io.BytesIO(); pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5")); pdf = canvas.Canvas(output, pagesize=landscape(A4)); width, height = landscape(A4)
    conditions = (" / ".join(filter(None, [f"結果:{delivery_status}" if delivery_status else "", f"経路:{channel}" if channel else "", f"種類:{notification_category}" if notification_category else "", f"期間:{date_from or '指定なし'}〜{date_to or '指定なし'}" if date_from or date_to else "", f"オーナー:{owner_keyword[:30]}" if owner_keyword else ""])) or "すべて").replace("\n", " ").replace("\r", " ")
    def draw_header():
        pdf.setFont("HeiseiKakuGo-W5", 14); pdf.drawString(28, height - 30, f"{tenant.name} 通知配信履歴")
        pdf.setFont("HeiseiKakuGo-W5", 8); pdf.drawString(28, height - 45, f"出力日：{date.today():%Y年%m月%d日}　条件：{conditions[:100]}　件数：{len(items)}件")
        for x, label in zip([28, 112, 210, 305, 380, 435, 475, 565], ["作成日時", "オーナー", "経路", "種類", "結果", "試行", "最終配信", "失敗理由"]): pdf.drawString(x, height - 64, label)
    draw_header(); y = height - 80; pdf.setFont("HeiseiKakuGo-W5", 7)
    for created, owner, delivery_channel, category, status_value, attempts, sent_at, error in items:
        if y < 28: pdf.showPage(); draw_header(); y = height - 80; pdf.setFont("HeiseiKakuGo-W5", 7)
        values = [created.strftime("%Y-%m-%d %H:%M"), owner[:15], delivery_channel[:13], labels.get(category, category)[:10], status_value[:8], str(attempts), sent_at.strftime("%Y-%m-%d %H:%M") if sent_at else "－", error[:42]]
        for x, value in zip([28, 112, 210, 305, 380, 435, 475, 565], values): pdf.drawString(x, y, value)
        y -= 14
    pdf.save()
    return Response(content=output.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="notification-deliveries-tenant-{tenant.id}.pdf"', "Cache-Control": "private, no-store"})


@app.post("/admin/notification-deliveries/line/{delivery_id}/retry")
def notification_line_delivery_retry(delivery_id: int, confirm_retry: bool = Form(False), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    _, tenant = access
    if not confirm_retry:
        raise HTTPException(status_code=400, detail="再送の確認が必要です")
    delivery = session.get(LineDelivery, delivery_id)
    if not delivery or delivery.tenant_id != tenant.id or delivery.status == "sent" or not delivery.message or not delivery.target_url:
        raise HTTPException(status_code=404)
    sent = send_line_push(delivery.user_id, delivery.tenant_id, delivery.category, delivery.message, delivery.target_url, delivery.dedupe_key, session)
    session.commit()
    return RedirectResponse(f"/admin/notification-deliveries?retry={'sent' if sent else 'failed'}", status_code=303)


@app.post("/admin/notification-deliveries/email/{delivery_id}/retry")
def notification_email_delivery_retry(delivery_id: int, confirm_retry: bool = Form(False), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    _, tenant = access
    if not confirm_retry:
        raise HTTPException(status_code=400, detail="再送の確認が必要です")
    delivery = session.get(EmailDelivery, delivery_id)
    if not delivery or delivery.status == "sent" or delivery.purpose == "password_reset":
        raise HTTPException(status_code=404)
    related = delivery.tenant_id == tenant.id or (delivery.user_id and session.scalar(select(DogOwnership.id).where(
        DogOwnership.tenant_id == tenant.id, DogOwnership.user_id == delivery.user_id, DogOwnership.active.is_(True)
    )))
    if not related:
        raise HTTPException(status_code=404)
    sent = deliver_email(delivery, session)
    session.commit()
    return RedirectResponse(f"/admin/notification-deliveries?retry={'sent' if sent else 'failed'}", status_code=303)


@app.post("/admin/email-deliveries/{delivery_id}/retry")
def email_delivery_retry(delivery_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    delivery = session.get(EmailDelivery, delivery_id)
    if not delivery or delivery.status == "sent" or delivery.purpose == "password_reset":
        raise HTTPException(status_code=404)
    related = delivery.tenant_id == tenant.id or (delivery.user_id and session.scalar(select(DogOwnership.id).where(
        DogOwnership.tenant_id == tenant.id, DogOwnership.user_id == delivery.user_id, DogOwnership.active.is_(True)
    )))
    if not related:
        raise HTTPException(status_code=404)
    deliver_email(delivery, session)
    session.commit()
    return RedirectResponse("/admin/email-deliveries", status_code=303)


@app.get("/admin/operations", response_class=HTMLResponse)
def operations_dashboard(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    event_condition = (OperationEvent.tenant_id == tenant.id)
    if actor.platform_admin:
        event_condition = event_condition | OperationEvent.tenant_id.is_(None)
    events = session.scalars(select(OperationEvent).where(event_condition)
        .order_by(OperationEvent.created_at.desc()).limit(100)).all()
    failed_events = session.scalar(select(func.count(OperationEvent.id)).where(
        event_condition, OperationEvent.status == "failed", OperationEvent.created_at >= since)) or 0
    related_ids = set(session.scalars(select(DogOwnership.user_id).where(
        DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))).all())
    email_condition = (EmailDelivery.tenant_id == tenant.id)
    if related_ids:
        email_condition = email_condition | EmailDelivery.user_id.in_(related_ids)
    failed_emails = session.scalar(select(func.count(EmailDelivery.id)).where(
        email_condition, EmailDelivery.status == "failed", EmailDelivery.created_at >= since)) or 0
    active_push = session.scalar(select(func.count(FamilyPushSubscription.id)).where(
        FamilyPushSubscription.user_id.in_(related_ids), FamilyPushSubscription.active.is_(True))) or 0 if related_ids else 0
    last_backup = session.scalar(select(FamilyBackupAudit).where(FamilyBackupAudit.tenant_id == tenant.id)
        .order_by(FamilyBackupAudit.created_at.desc()).limit(1))
    rows = "".join(f'''<tr><td>{item.created_at.strftime("%Y-%m-%d %H:%M")}</td><td>{html.escape(item.category)}</td>
        <td><span class="badge">{html.escape(item.status)}</span></td><td>{html.escape(item.summary)}</td><td>{html.escape(item.details or "－")}</td></tr>''' for item in events)
    backup_state = last_backup.created_at.strftime("%Y-%m-%d %H:%M") if last_backup else "未作成"
    body = f'''<h1>運用監視</h1><p>通知、バックアップ、システム設定の状態をまとめて確認できます。</p>
    <div class="grid"><div class="tenant"><strong>メール配信</strong><h2>{"稼働中" if smtp_ready() else "設定待ち"}</h2><small>24時間の失敗 {failed_emails}件</small></div>
    <div class="tenant"><strong>ブラウザ通知</strong><h2>{"稼働中" if push_ready() else "停止"}</h2><small>有効端末 {active_push}台</small></div>
    <div class="tenant"><strong>運用イベント</strong><h2>{failed_events}件</h2><small>24時間の異常</small></div>
    <div class="tenant"><strong>最終バックアップ</strong><h2>{backup_state}</h2><small>出力履歴を基準に表示</small></div></div>
    <form method="post" action="/admin/operations/diagnose"><button class="secondary">今すぐシステム診断</button></form>
    <h2>運用イベント履歴</h2><table><tr><th>日時</th><th>分類</th><th>状態</th><th>概要</th><th>詳細</th></tr>{rows or '<tr><td colspan="5">運用イベントはありません。</td></tr>'}</table>'''
    return layout("運用監視", body, actor)


@app.post("/admin/operations/diagnose")
def operations_diagnose(access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    checks = {"database": True, "push": push_ready(), "email": smtp_ready()}
    status_value = "success" if checks["database"] and checks["push"] else "warning"
    record_operation(session, "diagnostic", status_value, "管理者がシステム診断を実行しました", tenant.id,
        json.dumps(checks, ensure_ascii=False))
    session.commit()
    return RedirectResponse("/admin/operations", status_code=303)


@app.post("/admin/password-resets/{request_id}/issue", response_class=HTMLResponse)
def password_reset_issue(request_id: int, admin_password: str = Form(...), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    actor, tenant = access
    request_item = session.get(PasswordResetRequest, request_id)
    if not request_item or request_item.resolved_at:
        raise HTTPException(status_code=404)
    account, _ = email_change_target(request_item.user_id, actor, tenant, session)
    if not passwords.verify(admin_password, actor.password_hash):
        raise HTTPException(status_code=403, detail="管理者パスワードが違います")
    raw_token = secrets.token_urlsafe(32)
    session.add(PasswordResetToken(user_id=account.id, token_hash=token_hash(raw_token), expires_at=datetime.now(timezone.utc) + timedelta(minutes=30), created_by_id=actor.id))
    request_item.resolved_at = datetime.now(timezone.utc)
    session.commit()
    base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
    link = f"{base_url}/reset-password/{raw_token}"
    body = f'''<a class="button secondary" href="/admin/password-resets">一覧へ戻る</a><h1>再設定リンクを発行しました</h1>
    <div class="tenant"><p>この画面を閉じると再表示できません。本人確認済みのオーナー様へお伝えください。</p>
    <label>有効期限30分のリンク</label><textarea readonly style="min-height:120px">{html.escape(link)}</textarea></div>'''
    return layout("再設定リンク発行", body, actor)


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
    return {"ok": True, "push_ready": push_ready(), "email_ready": smtp_ready(), "api_version": "v1"}


app.mount("/mcp", mcp.sse_app(mount_path="/mcp"))
