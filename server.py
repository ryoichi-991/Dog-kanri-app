import asyncio
import base64
import calendar
import csv
import hashlib
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


def layout(title: str, body: str, user: User | None = None, owner_mode: bool = False, notification_count: int = 0) -> str:
    nav = ""
    body_class = "owner-view" if user and owner_mode else ("authenticated" if user else "guest")
    if user and owner_mode:
        notification_badge = f'<span class="nav-count">{notification_count}</span>' if notification_count else ""
        nav = f'''<aside class="owner-header"><a class="owner-brand" href="/family"><strong>ESTRELLA</strong><small>FAMILY</small></a>
        <nav><p class="owner-nav-label">ホーム</p><a href="/family"><span>⌂</span>うちの子</a><a href="/family/notifications"><span>●</span>通知{notification_badge}</a>
        <p class="owner-nav-label">交流</p><a href="/family/messages"><span>✉</span>メッセージ</a><a href="/family/announcements"><span>◇</span>お知らせ</a><a href="/family/timeline"><span>▦</span>タイムライン</a><a href="/family/anniversaries"><span>♡</span>記念日</a><a href="/family/relatives"><span>♢</span>兄弟・親戚犬</a><a href="/family/kennel"><span>♧</span>犬舎FAMILY会</a>
        <p class="owner-nav-label">設定</p><a href="/family/profile"><span>♙</span>プロフィール設定</a><a href="/family/consents"><span>✓</span>規約・同意</a><a href="/family/devices"><span>▣</span>アプリ・端末</a><a href="/family/account"><span>↪</span>退会・引継ぎ</a></nav>
        <div class="owner-account"><span>{html.escape(user.name)}</span><form method="post" action="/logout"><button>ログアウト</button></form></div></aside>'''
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
          <a href="/family/timeline/comments/manage"><span>💬</span>コメント管理</a>
          <a href="/family/timeline/reports/manage"><span>!</span>タイムライン通報</a>
          <a href="/family/safety/reports/manage"><span>⚑</span>プロフィール・メッセージ通報</a>
          <a href="/family/restrictions/manage"><span>⊘</span>FAMILY利用停止</a>
          <a href="/family/dashboard/manage"><span>▥</span>FAMILY集計</a>
          <a href="/family/withdrawals/manage"><span>↪</span>退会申請</a>
          <a href="/family/terms/manage"><span>✓</span>規約・同意管理</a>
          <a href="/family/backups/manage"><span>⇩</span>データ出力</a>
          <a href="/admin/password-resets"><span>⌁</span>パスワード再設定</a>
          <a href="/admin/email-deliveries"><span>✉</span>メール送信履歴</a>
          <a href="/admin/operations"><span>◉</span>運用監視</a>
          {platform_link}
        </nav>
        <div class="sidebar-user"><div class="avatar">{html.escape(user.name[:1])}</div><div><strong>{html.escape(user.name)}</strong><small>{"運営管理者" if user.platform_admin else "ユーザー"}</small></div><form method="post" action="/logout"><button title="ログアウト">↪</button></form></div>
        </aside>'''
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--wine:#704454;--rose:#b66f7c;--rose-light:#ead0d5;--cream:#faf6f3;--paper:#fffdfb;--ink:#3f3036;--muted:#816f76;--line:#eadfe1;--green:#718b75;--danger:#a94f55}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--cream);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;line-height:1.55}}.sidebar{{position:fixed;inset:0 auto 0 0;width:260px;background:linear-gradient(180deg,#68404f 0%,#55333f 100%);color:#fff;display:flex;flex-direction:column;z-index:10;box-shadow:6px 0 24px #4b26331a}}.brand{{height:84px;display:flex;align-items:center;gap:13px;padding:18px 22px;color:#fff;text-decoration:none;border-bottom:1px solid #ffffff1f}}.brand-mark{{display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:#f0d8dc;color:var(--wine);font-family:Georgia,serif;font-size:25px}}.brand strong{{display:block;letter-spacing:1.8px;font-family:Georgia,serif}}.brand small,.sidebar-user small{{display:block;color:#ead5da;font-size:11px}}.sidebar nav{{padding:12px 13px;overflow-y:auto;flex:1}}.sidebar nav a{{display:flex;align-items:center;gap:12px;color:#f8eef1;text-decoration:none;padding:10px 13px;border-radius:10px;font-size:14px;margin:2px 0}}.sidebar nav a:hover{{background:#ffffff17;color:#fff}}.sidebar nav a span{{width:20px;text-align:center;color:#eac3cb}}.nav-label{{margin:14px 12px 5px;color:#cbaeb5;font-size:10px;letter-spacing:1.5px;font-weight:700}}.sidebar-user{{display:flex;align-items:center;gap:10px;padding:15px;border-top:1px solid #ffffff1f;background:#452934}}.sidebar-user .avatar{{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:#e7c6cc;color:var(--wine);font-weight:700}}.sidebar-user strong{{display:block;max-width:125px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}}.sidebar-user form{{margin-left:auto}}.sidebar-user button{{margin:0;padding:8px;background:transparent;color:#fff;font-size:18px}}main{{max-width:1280px;margin-left:260px;padding:38px 42px}}.card{{background:var(--paper);padding:34px;border:1px solid #f1e7e8;border-radius:20px;box-shadow:0 10px 35px #63404c0d}}h1{{margin:0 0 22px;font-size:28px;letter-spacing:.02em}}h2{{margin-top:34px;padding-bottom:8px;border-bottom:1px solid var(--line);font-size:20px}}label{{display:block;margin:15px 0 6px;font-size:13px;font-weight:650;color:#665159}}input,select,textarea{{width:100%;padding:11px 13px;border:1px solid #dacdd0;border-radius:10px;background:#fff;font-size:15px;color:var(--ink);outline:none}}input:focus,select:focus,textarea:focus{{border-color:var(--rose);box-shadow:0 0 0 3px #b66f7c18}}textarea{{min-height:84px;resize:vertical}}button,.button{{display:inline-block;margin-top:17px;padding:11px 18px;border:0;border-radius:10px;background:var(--rose);color:#fff;text-decoration:none;font-weight:650;cursor:pointer;box-shadow:0 4px 12px #b66f7c28}}button:hover,.button:hover{{filter:brightness(.95)}}.secondary{{background:#89747b}}.danger{{background:var(--danger)}}.success{{background:var(--green)}}.inline{{display:inline}}.inline button{{margin:3px;padding:7px 10px;font-size:12px}}.error{{background:#fff0f0;color:#963c43;padding:13px;border-left:4px solid var(--danger);border-radius:8px}}table{{width:100%;border-collapse:separate;border-spacing:0;margin-top:18px;font-size:14px;overflow:hidden}}th{{background:#f6edef;color:#694d57;font-size:12px;letter-spacing:.03em}}th,td{{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line)}}tr:hover td{{background:#fdf8f8}}.badge{{display:inline-block;padding:5px 10px;border-radius:99px;background:var(--rose-light);color:var(--wine);font-size:12px;font-weight:700}}.tenant{{padding:18px;background:#f7edef;border:1px solid #ecdadd;border-radius:14px;margin-bottom:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:18px}}.module{{position:relative;display:block;min-height:118px;padding:21px;border:1px solid var(--line);border-radius:15px;text-decoration:none;color:var(--ink);background:linear-gradient(145deg,#fff 0%,#fdf8f7 100%);transition:.2s}}.module:after{{content:"›";position:absolute;right:18px;top:15px;color:#c18a94;font-size:24px}}.module:hover{{transform:translateY(-2px);border-color:#d6a7af;box-shadow:0 9px 22px #70445414}}.module h3{{margin:0 25px 9px 0;font-size:17px;color:#66404e}}.module p{{margin:0;color:var(--muted);font-size:13px}}
.brand-logo-wrap{{width:48px;height:48px;flex:0 0 48px;overflow:hidden;display:grid;place-items:center}}.brand-logo{{display:block;width:48px;height:48px;object-fit:contain}}.title-crown{{display:inline-flex;align-items:center;gap:2px;margin:2px 5px 2px 0;font-size:20px;font-weight:800}}.title-crown small{{font-size:9px;color:var(--ink)}}.crown-silver{{color:#9da3aa;text-shadow:0 1px #fff}}.crown-gold{{color:#d4a72c;text-shadow:0 1px #fff}}.crown-rose{{color:#cf788b}}.crown-purple{{color:#9167a8}}.crown-blue{{color:#668caf}}.guest main{{max-width:760px;margin:45px auto;padding:24px}}
.owner-header{{position:fixed;inset:0 auto 0 0;z-index:20;width:260px;padding:0;background:linear-gradient(180deg,#68404f 0%,#55333f 100%);color:#fff;display:flex;flex-direction:column;box-shadow:6px 0 24px #4b263326}}.owner-brand{{min-height:92px;padding:23px 24px;color:#fff;text-decoration:none;font-family:Georgia,serif;letter-spacing:1.5px;white-space:nowrap;border-bottom:1px solid #ffffff1f;display:flex;flex-direction:column;justify-content:center}}.owner-brand strong{{font-size:19px}}.owner-brand small{{color:#e8d2d7;font-size:12px;letter-spacing:3px}}.owner-header nav{{display:block;flex:1;padding:12px 13px;overflow-y:auto}}.owner-header nav a{{display:flex;align-items:center;gap:11px;color:#f8eef1;text-decoration:none;padding:10px 13px;border-radius:10px;margin:2px 0;font-size:14px;white-space:nowrap}}.owner-header nav a span{{width:20px;text-align:center;color:#eac3cb}}.owner-header nav a:hover{{background:#ffffff17;color:#fff}}.owner-nav-label{{margin:15px 12px 5px;color:#cbaeb5;font-size:10px;letter-spacing:1.5px;font-weight:700}}.owner-account{{display:flex;align-items:center;gap:10px;padding:16px;background:#452934;border-top:1px solid #ffffff1f;font-size:13px}}.owner-account>span{{min-width:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.owner-account form{{margin:0}}.owner-account button{{margin:0;padding:8px 11px;background:#ffffff1c;box-shadow:none;font-size:12px}}.owner-view main{{margin:0 0 0 260px;max-width:none;padding:38px 42px}}.owner-view main>.card{{max-width:1180px;margin:0 auto}}
.nav-count{{display:inline-grid;place-items:center;min-width:19px;height:19px;margin-left:4px;padding:0 5px;border-radius:10px;background:#fff;color:var(--wine);font-size:11px;font-weight:800}}.notification-item{{display:block;margin:12px 0;padding:18px;border:1px solid var(--line);border-radius:14px;background:#fff;color:var(--ink);text-decoration:none}}.notification-item.unread{{border-left:5px solid var(--rose);background:#fffafb}}.notification-item p{{margin:5px 0}}.notification-kind{{display:inline-block;margin-right:7px;color:var(--wine);font-size:12px;font-weight:750}}
.timeline-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:22px 0}}.timeline-tile{{position:relative;display:block;aspect-ratio:1;overflow:hidden;background:#f1e7e9;color:#fff;text-decoration:none}}.timeline-tile img{{display:block;width:100%;height:100%;object-fit:cover;transition:transform .2s ease}}.timeline-tile:hover img{{transform:scale(1.025)}}.timeline-overlay{{position:absolute;inset:auto 0 0;padding:28px 10px 8px;background:linear-gradient(transparent,#2d1924cc);font-size:12px}}.timeline-overlay strong{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.timeline-stats{{display:flex;justify-content:space-between;gap:6px;margin-top:2px;font-size:11px}}
.family-photo-stage{{width:100%;min-height:260px;max-height:70vh;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:18px;background:linear-gradient(145deg,#f7edef,#fff);border:1px solid var(--line);margin-bottom:18px}}.family-dog-photo{{display:block;max-width:100%;max-height:70vh;width:auto;height:auto;object-fit:contain}}.family-dog-thumb{{display:block;width:100%;height:190px;object-fit:contain;border-radius:12px;margin-bottom:12px;background:#f7edef}}
.family-home-grid{{display:grid;gap:18px;margin-top:18px}}.family-home-card{{display:grid;grid-template-columns:minmax(260px,340px) 1fr;min-height:260px;padding:0;overflow:hidden;border:1px solid var(--line);border-radius:18px;text-decoration:none;color:var(--ink);background:#fff;box-shadow:0 8px 24px #7044540d;transition:.2s}}.family-home-card:hover{{transform:translateY(-2px);border-color:#d6a7af;box-shadow:0 12px 28px #70445418}}.family-home-photo{{display:flex;align-items:center;justify-content:center;min-height:260px;padding:14px;background:linear-gradient(145deg,#f3e7e9,#fbf5f4)}}.family-home-photo img{{display:block;width:100%;height:232px;object-fit:contain;border-radius:12px}}.family-home-photo-empty{{font-family:Georgia,serif;font-size:72px;color:#c59aa3}}.family-home-info{{display:flex;flex-direction:column;justify-content:center;padding:30px 34px}}.family-home-info h3{{margin:0 0 12px;font-size:25px;color:var(--wine)}}.family-home-info p{{margin:5px 0;color:var(--muted)}}.family-home-info .registered-name{{color:var(--ink);font-weight:650}}.family-home-info .badge{{align-self:flex-start;margin-top:12px}}.family-home-more{{margin-top:18px;color:var(--rose);font-weight:700}}
.album-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;margin:18px 0}}.album-item{{overflow:hidden;border:1px solid var(--line);border-radius:15px;background:#fff}}.album-item a{{display:flex;height:210px;align-items:center;justify-content:center;background:#f7edef}}.album-item img{{display:block;max-width:100%;max-height:210px;width:auto;height:auto;object-fit:contain}}.album-meta{{padding:13px}}.album-meta p{{margin:5px 0}}.album-meta form button{{margin-top:8px}}
@media(max-width:950px){{.timeline-grid{{grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}}}}
@media(max-width:850px){{.sidebar{{position:relative;width:100%;height:auto}}.sidebar nav{{display:grid;grid-template-columns:repeat(2,1fr)}}.nav-label{{grid-column:1/-1}}.sidebar-user{{display:none}}main{{margin-left:0;padding:20px 14px}}.card{{padding:22px}}.brand{{height:70px}}.owner-header{{position:relative;inset:auto;width:100%;display:block;padding:14px;box-shadow:0 5px 20px #4b263326}}.owner-brand{{min-height:42px;padding:2px 4px;border:0;display:block}}.owner-brand strong{{font-size:16px}}.owner-brand small{{display:inline;margin-left:5px}}.owner-header nav{{display:grid;grid-template-columns:repeat(2,1fr);gap:3px;margin-top:10px;padding:0;overflow:visible}}.owner-nav-label{{grid-column:1/-1;margin:10px 4px 2px}}.owner-header nav a{{padding:8px 6px;text-align:left;font-size:12px;margin:0}}.owner-account{{position:absolute;right:12px;top:9px;padding:0;background:transparent;border:0}}.owner-account>span{{display:none}}.owner-account button{{font-size:11px;padding:6px 8px}}.owner-view main{{margin-left:0;padding:15px 10px}}.family-home-card{{grid-template-columns:1fr}}.family-home-photo{{min-height:220px}}.family-home-photo img{{height:220px}}.family-home-info{{padding:22px}}.family-home-info h3{{font-size:22px}}.timeline-grid{{gap:3px;margin-left:-10px;margin-right:-10px}}.timeline-overlay{{padding:20px 6px 5px;font-size:10px}}.timeline-stats{{font-size:9px}}}}
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


@app.middleware("http")
async def security_headers_and_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith("/api/v1/"):
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
            (FamilyNotificationSetting.email_enabled.is_(True) | FamilyNotificationSetting.push_enabled.is_(True)),
            FamilyNotificationSetting.anniversaries.is_(True)
        )).all()
        base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
        for setting in settings:
            owner = session.get(User, setting.user_id)
            if not owner or not owner.active:
                continue
            for dog, event_type, event_date, days in family_anniversary_notification_items(owner, session):
                label = "誕生日" if event_type == "birthday" else "お迎え記念日"
                timing = "本日" if days == 0 else ("明日" if days == 1 else "7日後")
                if setting.email_enabled:
                    queue_email(session, owner.email, "anniversary", f"【ESTRELLA FAMILY】{dog.call_name}の{label}が{timing}です",
                                f"{owner.name} 様\n\n{dog.call_name}の{label}は{event_date.strftime('%Y年%m月%d日')}です。大切な記念日をご確認ください。\n{base_url}/family/anniversaries",
                                dog.tenant_id, owner.id, f"anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}")
                send_web_push(owner.id, "anniversaries", f"{dog.call_name}の{label}が{timing}です", event_date.strftime("%Y年%m月%d日"),
                              "/family/anniversaries", f"push:anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}", session)
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
    category_labels = {"puppy": "子犬", "parent": "親犬", "external": "外部犬"}
    status_labels = {"resident": "在籍中", "reserved": "予約済み（在籍中）", "retired": "引退（在籍中）", "delivered": "販売済み", "transferred": "譲渡済み"}
    options = "".join(
        f'<option value="{d.id}" data-nonresident="{str(d.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [d.call_name, d.registered_name, d.breed, category_labels.get(d.category, d.category), status_labels.get(d.status, d.status)])))}">'
        f'{html.escape(d.call_name)}｜{html.escape(category_labels.get(d.category, d.category))}'
        f'｜{html.escape(status_labels.get(d.status, d.status))}{"｜" + html.escape(d.registered_name) if d.registered_name else ""}</option>' for d in dogs
    )

    def dog_picker(key: str) -> str:
        return f'''<div class="dog-picker"><label for="{key}-dog-search">対象犬を検索</label>
        <input id="{key}-dog-search" class="dog-search" type="search" data-dog-select="{key}-dog-select" placeholder="呼び名・血統書名・犬種・区分で検索" autocomplete="off">
        <label class="dog-search-all"><input type="checkbox" data-dog-all="{key}-dog-select"> 販売済み・譲渡済みの犬も検索する</label>
        <small class="dog-search-count">全{len(dogs)}頭から選択</small>
        <label for="{key}-dog-select">対象犬</label><select id="{key}-dog-select" name="dog_id" required>{options}</select></div>'''

    dog_search_script = '''<style>.dog-picker{grid-column:span 2;min-width:0}.dog-picker .dog-search,.dog-picker select{max-width:100%}.dog-search-all{display:flex;align-items:center;gap:7px;margin:8px 0 3px;font-weight:500}.dog-search-all input{width:auto;margin:0}.dog-search-count{display:block;margin-top:5px;color:#806b72}.dog-picker select{margin-top:2px}@media(max-width:700px){.dog-picker{grid-column:1/-1}}</style>
    <script>document.querySelectorAll('.dog-search').forEach(function(input){
      var select=document.getElementById(input.dataset.dogSelect); var original=Array.from(select.options).map(function(option){return option.cloneNode(true)}); var count=input.parentElement.querySelector('.dog-search-count'); var includeAll=input.parentElement.querySelector('[data-dog-all]');
      function filterDogs(){var query=input.value.trim().toLowerCase(); var current=select.value; var matches=original.filter(function(option){var statusMatch=includeAll.checked || option.dataset.nonresident!=='true'; var textMatch=!query || (option.dataset.search || option.textContent).toLowerCase().includes(query); return statusMatch && textMatch}); select.replaceChildren.apply(select,matches.map(function(option){return option.cloneNode(true)})); if(matches.some(function(option){return option.value===current}))select.value=current; count.textContent=(includeAll.checked?'在籍犬以外を含む ':'在籍犬 ') + matches.length+'頭から選択';}
      input.addEventListener('input',filterDogs); includeAll.addEventListener('change',filterDogs); filterDogs();
    });</script>'''
    health = session.scalars(select(HealthRecord).where(HealthRecord.tenant_id == tenant.id).order_by(HealthRecord.record_date.desc()).limit(30)).all()
    vaccines = session.scalars(select(Vaccination).where(Vaccination.tenant_id == tenant.id).order_by(Vaccination.administered_on.desc()).limit(30)).all()
    medications = session.scalars(select(Medication).where(Medication.tenant_id == tenant.id).order_by(Medication.administered_on.desc()).limit(30)).all()
    diseases = session.scalars(select(DiseaseHistory).where(DiseaseHistory.tenant_id == tenant.id).order_by(DiseaseHistory.diagnosed_on.desc()).limit(30)).all()
    foods = session.scalars(select(FoodHistory).where(FoodHistory.tenant_id == tenant.id).order_by(FoodHistory.started_on.desc())).all()
    owner_shared_count = session.scalar(select(func.count(OwnerHealthRecord.id)).where(OwnerHealthRecord.tenant_id == tenant.id, OwnerHealthRecord.share_to_breeder.is_(True))) or 0
    health_rows = "".join(f"<tr><td>{r.record_date}</td><td>{html.escape(session.get(Dog,r.dog_id).call_name)}</td><td>{html.escape(r.category)}</td><td>{r.weight_kg or '-'}</td><td>{html.escape(r.notes or '-')}</td></tr>" for r in health)
    vaccine_rows = "".join(f"<tr><td>{v.administered_on}</td><td>{html.escape(session.get(Dog,v.dog_id).call_name)}</td><td>{html.escape(v.vaccine_name)}</td><td>{v.next_due_on or '-'}</td></tr>" for v in vaccines)
    medication_rows = "".join(f"<tr><td>{m.administered_on}</td><td>{html.escape(session.get(Dog,m.dog_id).call_name)}</td><td>{html.escape(m.medicine_name)}</td><td>{html.escape(m.notes or '-')}</td></tr>" for m in medications)
    disease_rows = "".join(f"<tr><td>{d.diagnosed_on or '-'}</td><td>{html.escape(session.get(Dog,d.dog_id).call_name)}</td><td>{html.escape(d.disease_name)}</td><td>{html.escape(d.details or '-')}</td></tr>" for d in diseases)
    food_rows = "".join(f"<tr><td>{html.escape(f.name)}</td><td>{f.started_on}</td><td>{f.ended_on or '-'}</td></tr>" for f in foods)
    current_year = date.today().year
    parent_ids = [dog.id for dog in dogs if dog.category == "parent" and dog.status not in {"delivered", "transferred"}]
    rabies_vaccinated_ids = set(session.scalars(select(Vaccination.dog_id).where(Vaccination.tenant_id == tenant.id,
        Vaccination.vaccine_type == "rabies", Vaccination.administered_on >= date(current_year, 1, 1))).all())
    mixed_vaccinated_ids = set(session.scalars(select(Vaccination.dog_id).where(Vaccination.tenant_id == tenant.id,
        Vaccination.vaccine_type == "mixed", Vaccination.administered_on >= date(current_year, 1, 1))).all())
    checked_ids = set(session.scalars(select(HealthRecord.dog_id).where(HealthRecord.tenant_id == tenant.id,
        HealthRecord.category == "checkup", HealthRecord.record_date >= date(current_year, 1, 1))).all())
    body = f'''<h1>健康管理</h1><p>犬ごとの健康状態と、未接種・未受診をまとめて確認できます。</p>
    <div class="grid"><a class="module" href="/modules/health/weights"><h3>体重管理</h3><p>子犬・親犬の体重推移を記録</p></a>
    <a class="module" href="/modules/health/vaccinations"><h3>ワクチン管理</h3><p>狂犬病 未接種 {len(set(parent_ids) - rabies_vaccinated_ids)}頭 ／ 混合 未接種 {len(set(parent_ids) - mixed_vaccinated_ids)}頭</p></a>
    <a class="module" href="/modules/health/checkups"><h3>健診管理</h3><p>今年度未受診 {len(set(parent_ids) - checked_ids)}頭</p></a>
    <a class="module" href="/modules/health/medications"><h3>投薬管理</h3><p>投薬記録 {len(medications)}件</p></a>
    <a class="module" href="/modules/health/diseases"><h3>病歴管理</h3><p>病歴記録 {len(diseases)}件</p></a>
    <a class="module" href="/modules/health/foods"><h3>フード管理</h3><p>利用履歴 {len(foods)}件</p></a>
    <a class="module" href="/modules/health/owner-records"><h3>オーナー共有記録</h3><p>共有中 {owner_shared_count}件（閲覧専用）</p></a></div>
    <h2 id="checks">簡易健康記録</h2><form method="post" action="/modules/health/record"><div class="grid">{dog_picker("health")}<div><label>記録日</label><input type="date" name="record_date" required></div><div><label>種類</label><select name="category"><option value="weight">体重</option><option value="treatment">診療</option></select></div><div><label>体重（kg）</label><input type="number" step="0.01" min="0" name="weight_kg"></div><div><label>動物病院</label><input name="clinic"></div></div><label>結果・メモ</label><textarea name="notes"></textarea><button>記録する</button></form><table><tr><th>日付</th><th>犬</th><th>種類</th><th>体重kg</th><th>メモ</th></tr>{health_rows}</table>
    {dog_search_script}'''
    return layout("健康管理", body, user)


def health_share_for(session: Session, record_type: str, record_id: int):
    return session.scalar(select(HealthRecordShare).where(
        HealthRecordShare.record_type == record_type, HealthRecordShare.record_id == record_id
    ))


@app.get("/modules/health/owner-records", response_class=HTMLResponse)
def health_owner_records_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    records = session.scalars(select(OwnerHealthRecord).where(
        OwnerHealthRecord.tenant_id == tenant.id, OwnerHealthRecord.share_to_breeder.is_(True)
    ).order_by(OwnerHealthRecord.recorded_on.desc(), OwnerHealthRecord.id.desc())).all()
    category_labels = {"weight": "体重", "vaccination": "ワクチン", "checkup": "健診", "medication": "投薬", "disease": "病歴", "food": "フード", "other": "その他"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id); owner = session.get(User, item.owner_id)
        if not dog: continue
        attachment = f'<a class="button secondary" href="/modules/health/owner-records/{item.id}/attachment" target="_blank">証明書・添付を見る</a>' if item.attachment_data else ""
        rows += f'''<tr><td>{item.recorded_on}</td><td>{html.escape(dog.call_name)}</td><td>{category_labels.get(item.category, "その他")}</td><td>{html.escape(item.title)}</td><td>{html.escape(item.value or "-")}</td><td style="white-space:pre-wrap">{html.escape(item.details or "-")}<br>{attachment}</td><td>{html.escape(owner.name if owner else "オーナー")}</td><td><span class="badge">閲覧のみ</span></td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">健康管理へ戻る</a><h1>オーナー共有記録</h1>
    <div class="tenant"><p>オーナー様が「ブリーダーへ共有する」に設定した健康記録です。</p><p>共有先：<strong>{html.escape(tenant.name)}</strong> ／ ブリーダー側から変更・削除はできません。</p></div>
    <div style="overflow-x:auto"><table><tr><th>記録日</th><th>犬</th><th>カテゴリー</th><th>記録内容</th><th>数値・補足</th><th>詳細</th><th>入力者</th><th>権限</th></tr>{rows or '<tr><td colspan="8">オーナー様から共有された記録はまだありません。</td></tr>'}</table></div>'''
    return layout("オーナー共有記録", body, user)


@app.get("/modules/health/owner-records/{record_id}/attachment")
def health_owner_record_attachment(record_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    _, tenant = access
    item = session.scalar(select(OwnerHealthRecord).where(OwnerHealthRecord.id == record_id, OwnerHealthRecord.tenant_id == tenant.id, OwnerHealthRecord.share_to_breeder.is_(True)))
    if not item or not item.attachment_data: raise HTTPException(status_code=404, detail="共有された証明書が見つかりません")
    return Response(content=item.attachment_data, media_type=item.attachment_content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store", "Content-Disposition": f"inline; filename*=UTF-8''{quote(item.attachment_filename or 'document')}"})


@app.get("/modules/health/weights", response_class=HTMLResponse)
def health_weights_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.birth_date.desc(), Dog.call_name)).all()
    records = session.scalars(select(HealthRecord).where(
        HealthRecord.tenant_id == tenant.id, HealthRecord.category == "weight"
    ).order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())).all()
    by_dog: dict[int, list[HealthRecord]] = {}
    for item in records:
        by_dog.setdefault(item.dog_id, []).append(item)
    foods = session.scalars(select(FoodHistory).where(
        FoodHistory.tenant_id == tenant.id
    ).order_by(FoodHistory.ended_on.is_(None).desc(), FoodHistory.started_on.desc(), FoodHistory.name)).all()
    food_names = list(dict.fromkeys(food.name for food in foods))
    food_options = '<option value="">選択してください</option>' + "".join(
        f'<option value="{html.escape(name)}">{html.escape(name)}</option>' for name in food_names
    )
    now_local = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%dT%H:%M")

    def recorded_time(item: HealthRecord) -> str:
        if item.recorded_at:
            value = item.recorded_at
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")
        return item.record_date.isoformat()

    def condition_detail(item: HealthRecord) -> str:
        parts = []
        if item.meal_amount_g is not None:
            parts.append(f"食事 {item.meal_amount_g:g}g")
        if item.food_name:
            parts.append(f"フード：{html.escape(item.food_name)}")
        if item.stool_condition:
            parts.append(f"うんち：{html.escape(item.stool_condition)}")
        if item.health_condition:
            parts.append(f"健康：{html.escape(item.health_condition)}")
        return "<br>".join(parts) or "-"

    def dog_card(dog: Dog) -> str:
            items = by_dog.get(dog.id, [])
            rows = ""
            for item in items[:10]:
                share = health_share_for(session, "health", item.id)
                is_shared = bool(share and share.owner_visible)
                rows += f'''<tr><td>{recorded_time(item)}</td><td>{item.weight_kg if item.weight_kg is not None else "-"} kg</td><td>{condition_detail(item)}</td><td>{html.escape(item.notes or "-")}</td><td>
                <form method="post" action="/modules/health/shares/health/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if is_shared else 'true'}"><button class="secondary">{'共有中（非公開にする）' if is_shared else 'オーナーへ共有'}</button></form></td></tr>'''
            latest = f"最新 {items[0].weight_kg} kg（{items[0].record_date}）" if items else "記録はまだありません"
            return f'''<section class="tenant"><h3>{html.escape(dog.call_name)}</h3><p>{latest}</p>
            <details><summary>記録を追加・履歴を見る</summary><form method="post" action="/modules/health/record">
            <input type="hidden" name="dog_id" value="{dog.id}"><input type="hidden" name="category" value="weight"><input type="hidden" name="return_to" value="weights">
            <label>測定日時</label><input type="datetime-local" name="recorded_at" value="{now_local}" required><label>体重（kg）</label><input type="number" step="0.01" min="0.01" name="weight_kg" required>
            <div class="grid"><div><label>食事量（g）</label><input type="number" step="0.1" min="0" name="meal_amount_g" placeholder="例：80"></div><div><label>フード名</label><select name="food_name">{food_options}</select></div>
            <div><label>うんちの状態</label><select name="stool_condition"><option value="">選択してください</option><option>良好</option><option>やわらかい</option><option>下痢</option><option>硬い</option><option>出ていない</option></select></div>
            <div><label>健康状態</label><select name="health_condition"><option value="">選択してください</option><option>良好</option><option>少し悪い</option><option>悪い</option></select></div></div>
            <label>メモ</label><textarea name="notes" placeholder="食欲や体調など"></textarea><label><input type="checkbox" name="owner_visible" checked> オーナーページにも共有する</label><button>体重を記録</button></form>
            <table><tr><th>測定日時</th><th>体重</th><th>食事・状態</th><th>メモ</th><th>共有</th></tr>{rows or '<tr><td colspan="5">記録はまだありません。</td></tr>'}</table></details></section>'''

    def dog_cards(category: str):
        targets = [dog for dog in dogs if dog.category == category]
        if not targets:
            return '<p>対象の犬は登録されていません。</p>'
        if category != "puppy":
            return "".join(dog_card(dog) for dog in targets)
        groups: dict[tuple[int | None, int | None, date | None], list[Dog]] = {}
        for dog in targets:
            groups.setdefault((dog.dam_id, dog.sire_id, dog.birth_date), []).append(dog)
        output = ""
        for (dam_id, sire_id, birth_date), siblings in groups.items():
            dam = session.get(Dog, dam_id) if dam_id else None
            sire = session.get(Dog, sire_id) if sire_id else None
            title = f"{birth_date or '出生日未登録'}生まれ　母犬：{html.escape(dam.call_name) if dam else '未登録'} ／ 父犬：{html.escape(sire.call_name) if sire else '未登録'}"
            output += f'<section class="weight-litter"><h3>{title}</h3><p>兄弟 {len(siblings)}頭</p><div class="weight-siblings">' + "".join(dog_card(dog) for dog in siblings) + "</div></section>"
        return output

    body = f'''<a class="button secondary" href="/modules/health">健康管理へ戻る</a><h1>体重管理</h1>
    <p>体重は愛犬に紐づいて保存されます。共有中の記録は、販売・譲渡後も連携されたオーナーが確認できます。</p>
    <style>.weight-litter{{margin:20px 0;padding:20px;border:1px solid #eadadd;border-radius:16px;background:#fffafb}}.weight-litter>h3{{margin:0;color:#68404f}}.weight-litter>p{{margin:5px 0 14px;color:#806b72}}.weight-siblings{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}}.weight-siblings .tenant{{margin:0;min-width:0}}@media(max-width:700px){{.weight-siblings{{grid-template-columns:1fr}}.weight-siblings table{{display:block;overflow-x:auto}}}}</style>
    <h2>子犬</h2>{dog_cards("puppy")}<h2>親犬</h2>{dog_cards("parent")}'''
    return layout("体重管理", body, user)


@app.get("/modules/health/checkups", response_class=HTMLResponse)
def health_checkups_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(HealthRecord).where(HealthRecord.tenant_id == tenant.id, HealthRecord.category == "checkup").order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())).all()
    category_labels = {"puppy": "子犬", "parent": "親犬", "external": "外部犬"}
    status_labels = {"resident": "在籍中", "reserved": "予約済み（在籍中）", "retired": "引退（在籍中）", "delivered": "販売済み", "transferred": "譲渡済み"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}｜{category_labels.get(dog.category, dog.category)}｜{status_labels.get(dog.status, dog.status)}{"｜" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    resident_parents = [dog for dog in dogs if dog.category == "parent" and dog.status not in {"delivered", "transferred"}]
    year_start = date(date.today().year, 1, 1)
    checked_ids = {item.dog_id for item in records if item.record_date >= year_start}
    unchecked = [dog for dog in resident_parents if dog.id not in checked_ids]
    checked = [dog for dog in resident_parents if dog.id in checked_ids]
    upcoming = [item for item in records if item.next_due_on and date.today() <= item.next_due_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_due_on and item.next_due_on < date.today()]
    result_labels = {"normal": "異常なし", "followup": "経過観察", "recheck": "再検査", "treatment": "治療・受診が必要"}

    def names(items: list[Dog]) -> str:
        return "、".join(html.escape(dog.call_name) for dog in items) or "該当なし"

    def tests(item: HealthRecord) -> str:
        labels = []
        if item.physical_exam: labels.append("触診")
        if item.blood_test: labels.append("血液検査")
        if item.ultrasound: labels.append("エコー")
        if item.chest_xray: labels.append("胸部X線")
        return "・".join(labels) or "項目未登録"

    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog: continue
        share = health_share_for(session, "health", item.id); shared = bool(share and share.owner_visible)
        attachment = f'<a href="/modules/health/checkups/{item.id}/attachment" target="_blank">結果を見る</a>' if item.attachment_data else "-"
        rows += f'''<tr><td>{item.record_date}</td><td>{html.escape(dog.call_name)}</td><td>{tests(item)}</td><td>{result_labels.get(item.result_summary or "", "未設定")}</td><td>{item.next_due_on or "-"}</td><td>{attachment}</td><td><form method="post" action="/modules/health/shares/health/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'共有中（非公開にする）' if shared else 'オーナーへ共有'}</button></form></td></tr>'''

    body = f'''<a class="button secondary" href="/modules/health">健康管理へ戻る</a><h1>健診管理</h1><p>年度内の未受診・受診済みを分類し、検査項目と結果を犬ごとに管理します。</p>
    <div class="grid"><section class="tenant"><h3>今年度未受診</h3><strong>{len(unchecked)}頭</strong><p>{names(unchecked)}</p></section><section class="tenant"><h3>今年度受診済み</h3><strong>{len(checked)}頭</strong><p>{names(checked)}</p></section><section class="tenant"><h3>30日以内の予定</h3><strong>{len(upcoming)}件</strong></section><section class="tenant"><h3>期限超過</h3><strong>{len(overdue)}件</strong></section></div>
    <h2>健診記録を追加</h2><form method="post" action="/modules/health/checkup" enctype="multipart/form-data"><div class="grid"><div class="dog-picker"><label>対象犬を検索</label><input class="dog-search" type="search" data-dog-select="checkup-dog" placeholder="呼び名・血統書名・犬種・区分で検索"><label class="dog-search-all"><input type="checkbox"> 販売済み・譲渡済みの犬も検索する</label><small class="dog-search-count"></small><label>対象犬</label><select id="checkup-dog" name="dog_id" required>{options}</select></div>
    <div><label>受診日</label><input type="date" name="record_date" value="{date.today()}" required></div><div><label>動物病院</label><input name="clinic"></div><div><label>結果区分</label><select name="result_summary" required><option value="normal">異常なし</option><option value="followup">経過観察</option><option value="recheck">再検査</option><option value="treatment">治療・受診が必要</option></select></div><div><label>次回健診予定日</label><input type="date" name="next_due_on"></div></div>
    <fieldset><legend>健診項目（1つ以上選択）</legend><div class="grid"><label><input style="width:auto" type="checkbox" name="physical_exam" value="true"> 触診</label><label><input style="width:auto" type="checkbox" name="blood_test" value="true"> 血液検査</label><label><input style="width:auto" type="checkbox" name="ultrasound" value="true"> エコー</label><label><input style="width:auto" type="checkbox" name="chest_xray" value="true"> 胸部X線</label></div></fieldset>
    <label>所見・結果</label><textarea name="notes"></textarea><label>検査結果（画像・PDF、8MBまで）</label><input type="file" name="attachment_file" accept="image/jpeg,image/png,image/webp,application/pdf"><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> オーナーページにも共有する</label><button>健診を記録</button></form>
    <h2>健診履歴</h2><div style="overflow-x:auto"><table><tr><th>受診日</th><th>犬</th><th>健診項目</th><th>結果</th><th>次回予定</th><th>添付</th><th>共有</th></tr>{rows or '<tr><td colspan="7">健診記録はまだありません。</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}fieldset{{margin-top:18px;border:1px solid #eadfe1;border-radius:12px}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style>
    <script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'在籍犬以外を含む ':'在籍犬 ')+matches.length+'頭から選択'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("健診管理", body, user)


@app.post("/modules/health/checkup")
async def health_checkup_create(dog_id: int = Form(...), record_date: str = Form(...), clinic: str = Form(""), result_summary: str = Form(...), next_due_on: str = Form(""), physical_exam: bool = Form(False), blood_test: bool = Form(False), ultrasound: bool = Form(False), chest_xray: bool = Form(False), notes: str = Form(""), owner_visible: bool = Form(False), attachment_file: UploadFile | None = File(None), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access; dog = tenant_dog(session, tenant.id, dog_id)
    if result_summary not in {"normal", "followup", "recheck", "treatment"} or not any([physical_exam, blood_test, ultrasound, chest_xray]):
        raise HTTPException(status_code=400, detail="健診項目と結果を確認してください")
    attachment_data = None
    if attachment_file and attachment_file.filename:
        if attachment_file.content_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
            raise HTTPException(status_code=400, detail="検査結果はJPEG・PNG・WebP・PDFに対応しています")
        attachment_data = await attachment_file.read(8 * 1024 * 1024 + 1)
        if len(attachment_data) > 8 * 1024 * 1024: raise HTTPException(status_code=413, detail="検査結果は8MB以下にしてください")
    due = date.fromisoformat(next_due_on) if next_due_on else None
    item = HealthRecord(tenant_id=tenant.id, dog_id=dog.id, record_date=date.fromisoformat(record_date), category="checkup", clinic=clinic.strip() or None, notes=notes.strip() or None, physical_exam=physical_exam, blood_test=blood_test, ultrasound=ultrasound, chest_xray=chest_xray, result_summary=result_summary, next_due_on=due, attachment_filename=((attachment_file.filename or "")[:255] or None) if attachment_file and attachment_data else None, attachment_content_type=attachment_file.content_type if attachment_file and attachment_data else None, attachment_data=attachment_data)
    session.add(item); session.flush()
    if owner_visible: session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="health", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    if due: session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} 次回健診予定", category="health", due_date=due))
    session.commit(); return RedirectResponse("/modules/health/checkups", status_code=303)


@app.get("/modules/health/checkups/{record_id}/attachment")
def health_checkup_attachment(record_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    _, tenant = access; item = session.scalar(select(HealthRecord).where(HealthRecord.id == record_id, HealthRecord.tenant_id == tenant.id, HealthRecord.category == "checkup"))
    if not item or not item.attachment_data: raise HTTPException(status_code=404, detail="検査結果が見つかりません")
    return Response(content=item.attachment_data, media_type=item.attachment_content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store"})


@app.post("/modules/health/record")
def health_create(dog_id: int = Form(...), record_date: str = Form(""), recorded_at: str = Form(""), category: str = Form(...), weight_kg: str = Form(""), meal_amount_g: str = Form(""), food_name: str = Form(""), stool_condition: str = Form(""), health_condition: str = Form(""), clinic: str = Form(""), notes: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if category not in {"weight", "checkup", "treatment"}:
        raise HTTPException(status_code=400)
    measured_at = datetime.fromisoformat(recorded_at).replace(tzinfo=ZoneInfo("Asia/Tokyo")) if recorded_at else None
    measured_date = measured_at.date() if measured_at else date.fromisoformat(record_date)
    weight = float(weight_kg) if weight_kg else None
    meal_amount = float(meal_amount_g) if meal_amount_g else None
    if stool_condition not in {"", "良好", "やわらかい", "下痢", "硬い", "出ていない"}:
        raise HTTPException(status_code=400, detail="うんちの状態を確認してください")
    if health_condition not in {"", "良好", "少し悪い", "悪い"}:
        raise HTTPException(status_code=400, detail="健康状態を確認してください")
    item = HealthRecord(tenant_id=tenant.id, dog_id=dog.id, record_date=measured_date, recorded_at=measured_at,
        category=category, weight_kg=weight, meal_amount_g=meal_amount, food_name=food_name.strip() or None,
        stool_condition=stool_condition or None, health_condition=health_condition or None,
        clinic=clinic.strip() or None, notes=notes.strip() or None)
    session.add(item)
    session.flush()
    if owner_visible:
        session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="health", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    session.commit()
    return RedirectResponse("/modules/health/weights" if return_to == "weights" else "/modules/health", status_code=303)


@app.post("/modules/health/shares/{record_type}/{record_id}")
def health_share_update(record_type: str, record_id: int, owner_visible: bool = Form(False), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    model = {"health": HealthRecord, "vaccination": Vaccination, "medication": Medication, "disease": DiseaseHistory, "food": FoodHistory}.get(record_type)
    if not model:
        raise HTTPException(status_code=400, detail="共有対象を確認してください")
    item = session.scalar(select(model).where(model.id == record_id, model.tenant_id == tenant.id))
    if not item:
        raise HTTPException(status_code=404, detail="健康記録が見つかりません")
    share = health_share_for(session, record_type, record_id)
    if not share:
        share = HealthRecordShare(tenant_id=tenant.id, dog_id=item.dog_id, record_type=record_type, record_id=record_id, updated_by_id=user.id)
        session.add(share)
    share.owner_visible = owner_visible
    share.updated_by_id = user.id
    share.updated_at = datetime.now(timezone.utc)
    session.commit()
    destination = ("/modules/health/checkups" if record_type == "health" and getattr(item, "category", "") == "checkup" else "/modules/health/weights") if record_type == "health" else ("/modules/health/vaccinations" if record_type == "vaccination" else ("/modules/health/medications" if record_type == "medication" else ("/modules/health/diseases" if record_type == "disease" else ("/modules/health/foods" if record_type == "food" else "/modules/health"))))
    return RedirectResponse(destination, status_code=303)


@app.get("/modules/health/vaccinations", response_class=HTMLResponse)
def health_vaccinations_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(Vaccination).where(Vaccination.tenant_id == tenant.id).order_by(Vaccination.administered_on.desc(), Vaccination.id.desc())).all()
    category_labels = {"puppy": "子犬", "parent": "親犬", "external": "外部犬"}
    status_labels = {"resident": "在籍中", "reserved": "予約済み（在籍中）", "retired": "引退（在籍中）", "delivered": "販売済み", "transferred": "譲渡済み"}
    options = "".join(
        f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">'
        f'{html.escape(dog.call_name)}｜{category_labels.get(dog.category, dog.category)}｜{status_labels.get(dog.status, dog.status)}'
        f'{"｜" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs
    )
    resident_parents = [dog for dog in dogs if dog.category == "parent" and dog.status not in {"delivered", "transferred"}]
    year_start = date(date.today().year, 1, 1)
    rabies_ids = {item.dog_id for item in records if item.administered_on >= year_start and item.vaccine_type == "rabies"}
    mixed_ids = {item.dog_id for item in records if item.administered_on >= year_start and item.vaccine_type == "mixed"}
    missing_rabies = [dog for dog in resident_parents if dog.id not in rabies_ids]
    missing_mixed = [dog for dog in resident_parents if dog.id not in mixed_ids]
    upcoming = [item for item in records if item.next_due_on and date.today() <= item.next_due_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_due_on and item.next_due_on < date.today()]
    type_labels = {"rabies": "狂犬病", "mixed": "混合ワクチン", "other": "その他"}

    def dose_label(value: int | None) -> str:
        return "追加接種" if value and value >= 4 else (f"{value}回目" if value else "-")

    def dog_names(items: list[Dog]) -> str:
        return "、".join(html.escape(dog.call_name) for dog in items) or "該当なし"

    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog:
            continue
        share = health_share_for(session, "vaccination", item.id)
        shared = bool(share and share.owner_visible)
        certificate = f'<a href="/modules/health/vaccinations/{item.id}/certificate" target="_blank">証明書を見る</a>' if item.certificate_data else "-"
        rows += f'''<tr><td>{item.administered_on}</td><td>{html.escape(dog.call_name)}</td><td>{type_labels.get(item.vaccine_type or "other", "その他")}</td><td>{html.escape(item.vaccine_name)}</td><td>{dose_label(item.dose_number)}</td><td>{item.next_due_on or "-"}</td><td>{certificate}</td><td>
        <form method="post" action="/modules/health/shares/vaccination/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'共有中（非公開にする）' if shared else 'オーナーへ共有'}</button></form></td></tr>'''

    body = f'''<a class="button secondary" href="/modules/health">健康管理へ戻る</a><h1>ワクチン管理</h1>
    <p>狂犬病と混合ワクチンを別々に判定し、子犬期の接種順と次回予定も管理します。</p>
    <div class="grid"><section class="tenant"><h3>狂犬病・今年度未接種</h3><strong>{len(missing_rabies)}頭</strong><p>{dog_names(missing_rabies)}</p></section>
    <section class="tenant"><h3>混合・今年度未接種</h3><strong>{len(missing_mixed)}頭</strong><p>{dog_names(missing_mixed)}</p></section>
    <section class="tenant"><h3>30日以内の予定</h3><strong>{len(upcoming)}件</strong></section><section class="tenant"><h3>期限超過</h3><strong>{len(overdue)}件</strong></section></div>
    <h2>接種記録を追加</h2><form method="post" action="/modules/health/vaccine" enctype="multipart/form-data"><div class="grid">
    <div class="dog-picker"><label>対象犬を検索</label><input class="dog-search" type="search" data-dog-select="vaccination-dog" placeholder="呼び名・血統書名・犬種・区分で検索"><label class="dog-search-all"><input type="checkbox"> 販売済み・譲渡済みの犬も検索する</label><small class="dog-search-count"></small><label>対象犬</label><select id="vaccination-dog" name="dog_id" required>{options}</select></div>
    <div><label>ワクチン区分</label><select name="vaccine_type" required><option value="rabies">狂犬病</option><option value="mixed">混合ワクチン</option><option value="other">その他</option></select></div>
    <div><label>ワクチン名</label><input name="vaccine_name" required></div><div><label>子犬期の接種順（任意）</label><select name="dose_number"><option value="">入力なし</option><option value="1">1回目</option><option value="2">2回目</option><option value="3">3回目</option><option value="4">追加接種</option></select><small>成犬の定期接種では入力不要です。</small></div>
    <div><label>接種日</label><input type="date" name="administered_on" value="{date.today()}" required></div><div><label>次回接種予定日</label><input type="date" name="next_due_on"></div>
    <div><label>動物病院</label><input name="clinic"></div><div><label>メーカー</label><input name="manufacturer"></div><div><label>製造番号・ロット番号</label><input name="lot_no"></div><div><label>証明書番号</label><input name="certificate_no"></div>
    <div><label>副反応</label><select name="reaction"><option value="none">なし</option><option value="mild">軽い症状あり</option><option value="severe">強い症状あり</option><option value="unknown">不明</option></select></div><div><label>証明書（画像・PDF、8MBまで）</label><input type="file" name="certificate_file" accept="image/jpeg,image/png,image/webp,application/pdf"></div></div>
    <label>メモ</label><textarea name="notes"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> オーナーページにも共有する</label><input type="hidden" name="return_to" value="vaccinations"><button>接種を記録</button></form>
    <h2>接種履歴</h2><div style="overflow-x:auto"><table><tr><th>接種日</th><th>犬</th><th>区分</th><th>ワクチン</th><th>回数</th><th>次回予定</th><th>証明書</th><th>共有</th></tr>{rows or '<tr><td colspan="8">接種記録はまだありません。</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style>
    <script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'在籍犬以外を含む ':'在籍犬 ')+matches.length+'頭から選択'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("ワクチン管理", body, user)


@app.get("/modules/health/vaccinations/{vaccination_id}/certificate")
def vaccination_certificate(vaccination_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    _, tenant = access
    item = session.scalar(select(Vaccination).where(Vaccination.id == vaccination_id, Vaccination.tenant_id == tenant.id))
    if not item or not item.certificate_data:
        raise HTTPException(status_code=404, detail="証明書が見つかりません")
    return Response(content=item.certificate_data, media_type=item.certificate_content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store"})


@app.post("/modules/health/vaccine")
async def vaccine_create(dog_id: int = Form(...), vaccine_name: str = Form(...), administered_on: str = Form(...), next_due_on: str = Form(""), certificate_no: str = Form(""), vaccine_type: str = Form("other"), dose_number: str = Form(""), clinic: str = Form(""), manufacturer: str = Form(""), lot_no: str = Form(""), reaction: str = Form("unknown"), notes: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), certificate_file: UploadFile | None = File(None), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if vaccine_type not in {"rabies", "mixed", "other"} or reaction not in {"none", "mild", "severe", "unknown"}:
        raise HTTPException(status_code=400, detail="ワクチン情報を確認してください")
    if dose_number not in {"", "1", "2", "3", "4"}:
        raise HTTPException(status_code=400, detail="子犬期の接種順を確認してください")
    next_due = date.fromisoformat(next_due_on) if next_due_on else None
    file_data = None
    if certificate_file and certificate_file.filename:
        allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        if certificate_file.content_type not in allowed:
            raise HTTPException(status_code=400, detail="証明書はJPEG・PNG・WebP・PDFに対応しています")
        file_data = await certificate_file.read(8 * 1024 * 1024 + 1)
        if len(file_data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="証明書は8MB以下にしてください")
    item = Vaccination(tenant_id=tenant.id, dog_id=dog.id, vaccine_name=vaccine_name.strip(), vaccine_type=vaccine_type,
        dose_number=int(dose_number) if dose_number else None, administered_on=date.fromisoformat(administered_on), next_due_on=next_due,
        certificate_no=certificate_no.strip() or None, clinic=clinic.strip() or None, manufacturer=manufacturer.strip() or None,
        lot_no=lot_no.strip() or None, reaction=reaction, notes=notes.strip() or None,
        certificate_filename=((certificate_file.filename or "")[:255] or None) if certificate_file and file_data else None,
        certificate_content_type=certificate_file.content_type if certificate_file and file_data else None, certificate_data=file_data)
    session.add(item)
    session.flush()
    if owner_visible:
        session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="vaccination", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    if next_due:
        session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} {vaccine_name.strip()}接種予定", category="health", due_date=next_due))
    session.commit()
    return RedirectResponse("/modules/health/vaccinations" if return_to == "vaccinations" else "/modules/health", status_code=303)


@app.get("/modules/health/medications", response_class=HTMLResponse)
def health_medications_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(Medication).where(Medication.tenant_id == tenant.id).order_by(Medication.administered_on.desc(), Medication.id.desc())).all()
    category_labels = {"puppy": "子犬", "parent": "親犬", "external": "外部犬"}; status_labels = {"resident": "在籍中", "reserved": "予約済み（在籍中）", "retired": "引退（在籍中）", "delivered": "販売済み", "transferred": "譲渡済み"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}｜{category_labels.get(dog.category, dog.category)}｜{status_labels.get(dog.status, dog.status)}{"｜" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    counts: dict[int, int] = {}
    for item in records: counts[item.dog_id] = counts.get(item.dog_id, 0) + 1

    def age(dog: Dog) -> str:
        if not dog.birth_date: return "未登録"
        today = date.today(); months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
        return f"{months // 12}歳{months % 12}か月" if months >= 12 else f"{max(months, 0)}か月"

    resident_dogs = [dog for dog in dogs if dog.status not in {"delivered", "transferred"}]
    dog_rows = "".join(f'<tr><td>{html.escape(dog.call_name)}</td><td>{age(dog)}</td><td>{dog.birth_date or "未登録"}</td><td>{counts.get(dog.id, 0)}回</td></tr>' for dog in resident_dogs)
    ongoing = [item for item in records if item.status == "ongoing"]
    upcoming = [item for item in records if item.next_due_on and date.today() <= item.next_due_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_due_on and item.next_due_on < date.today() and item.status != "completed"]
    type_labels = {"treatment": "治療薬", "prevention": "予防薬", "supplement": "サプリメント", "other": "その他"}; status_text = {"single": "単回", "ongoing": "継続中", "completed": "終了"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog: continue
        share = health_share_for(session, "medication", item.id); shared = bool(share and share.owner_visible)
        rows += f'''<tr><td>{item.administered_on}</td><td>{html.escape(dog.call_name)}</td><td>{html.escape(item.medicine_name)}</td><td>{type_labels.get(item.medication_type or "other", "その他")}</td><td>{html.escape(item.dosage or "-")}</td><td>{html.escape(item.frequency or "-")}</td><td>{status_text.get(item.status or "single", "単回")}</td><td>{item.next_due_on or "-"}</td><td><form method="post" action="/modules/health/shares/medication/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'共有中（非公開にする）' if shared else 'オーナーへ共有'}</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">健康管理へ戻る</a><h1>投薬管理</h1><p>犬ごとの投薬回数と、継続中・単回・終了した薬を管理します。</p>
    <div class="grid"><section class="tenant"><h3>継続中</h3><strong>{len(ongoing)}件</strong></section><section class="tenant"><h3>30日以内の予定</h3><strong>{len(upcoming)}件</strong></section><section class="tenant"><h3>期限超過</h3><strong>{len(overdue)}件</strong></section><section class="tenant"><h3>投薬記録</h3><strong>{len(records)}件</strong></section></div>
    <h2>犬ごとの投薬回数</h2><div style="overflow-x:auto"><table><tr><th>対象犬</th><th>年齢</th><th>誕生日</th><th>投薬回数</th></tr>{dog_rows or '<tr><td colspan="4">対象犬はいません。</td></tr>'}</table></div>
    <h2>投薬記録を追加</h2><form method="post" action="/modules/health/medication"><div class="grid"><div class="dog-picker"><label>対象犬を検索</label><input class="dog-search" type="search" data-dog-select="medication-dog" placeholder="呼び名・血統書名・犬種・区分で検索"><label class="dog-search-all"><input type="checkbox"> 販売済み・譲渡済みの犬も検索する</label><small class="dog-search-count"></small><label>対象犬</label><select id="medication-dog" name="dog_id" required>{options}</select></div>
    <div><label>薬剤名</label><input name="medicine_name" required></div><div><label>区分</label><select name="medication_type"><option value="treatment">治療薬</option><option value="prevention">予防薬</option><option value="supplement">サプリメント</option><option value="other">その他</option></select></div><div><label>記録日</label><input type="date" name="administered_on" value="{date.today()}" required></div><div><label>目的・対象症状</label><input name="purpose"></div><div><label>1回量</label><input name="dosage" placeholder="例：1錠、2.5ml"></div><div><label>投薬頻度</label><input name="frequency" placeholder="例：1日2回、毎月1回"></div><div><label>開始日</label><input type="date" name="started_on"></div><div><label>終了日</label><input type="date" name="ended_on"></div><div><label>次回予定日</label><input type="date" name="next_due_on"></div><div><label>状態</label><select name="medication_status"><option value="single">単回</option><option value="ongoing">継続中</option><option value="completed">終了</option></select></div><div><label>動物病院</label><input name="clinic"></div></div>
    <label>オーナーへ共有する説明</label><textarea name="owner_notes"></textarea><label>犬舎内部メモ（オーナーには表示されません）</label><textarea name="notes"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> オーナーページにも共有する</label><input type="hidden" name="return_to" value="medications"><button>投薬を記録</button></form>
    <h2>投薬履歴</h2><div style="overflow-x:auto"><table><tr><th>記録日</th><th>犬</th><th>薬剤</th><th>区分</th><th>1回量</th><th>頻度</th><th>状態</th><th>次回予定</th><th>共有</th></tr>{rows or '<tr><td colspan="9">投薬記録はまだありません。</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style><script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'在籍犬以外を含む ':'在籍犬 ')+matches.length+'頭から選択'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("投薬管理", body, user)


@app.post("/modules/health/medication")
def medication_create(dog_id: int = Form(...), medicine_name: str = Form(...), administered_on: str = Form(...), medication_type: str = Form("treatment"), purpose: str = Form(""), dosage: str = Form(""), frequency: str = Form(""), started_on: str = Form(""), ended_on: str = Form(""), next_due_on: str = Form(""), medication_status: str = Form("single"), clinic: str = Form(""), owner_notes: str = Form(""), notes: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if not medicine_name.strip() or medication_type not in {"treatment", "prevention", "supplement", "other"} or medication_status not in {"single", "ongoing", "completed"}:
        raise HTTPException(status_code=400, detail="投薬情報を確認してください")
    try:
        recorded = date.fromisoformat(administered_on)
        parse = lambda value: date.fromisoformat(value) if value else None
        started, ended, due = parse(started_on), parse(ended_on), parse(next_due_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="投薬日を確認してください")
    if started and ended and ended < started: raise HTTPException(status_code=400, detail="終了日は開始日以降にしてください")
    item = Medication(tenant_id=tenant.id, dog_id=dog.id, medicine_name=medicine_name.strip(), administered_on=recorded, medication_type=medication_type, purpose=purpose.strip() or None, dosage=dosage.strip() or None, frequency=frequency.strip() or None, started_on=started, ended_on=ended, next_due_on=due, status=medication_status, clinic=clinic.strip() or None, owner_notes=owner_notes.strip() or None, notes=notes.strip() or None)
    session.add(item); session.flush()
    if owner_visible: session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="medication", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    if due: session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} {medicine_name.strip()}投薬予定", category="health", due_date=due))
    session.commit()
    return RedirectResponse("/modules/health/medications" if return_to == "medications" else "/modules/health", status_code=303)


@app.get("/modules/health/diseases", response_class=HTMLResponse)
def health_diseases_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(DiseaseHistory).where(DiseaseHistory.tenant_id == tenant.id).order_by(DiseaseHistory.diagnosed_on.desc(), DiseaseHistory.id.desc())).all()
    category_labels = {"puppy": "子犬", "parent": "親犬", "external": "外部犬"}; status_labels = {"resident": "在籍中", "reserved": "予約済み（在籍中）", "retired": "引退（在籍中）", "delivered": "販売済み", "transferred": "譲渡済み"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}｜{category_labels.get(dog.category, dog.category)}｜{status_labels.get(dog.status, dog.status)}{"｜" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    counts: dict[int, int] = {}
    for item in records: counts[item.dog_id] = counts.get(item.dog_id, 0) + 1

    def age(dog: Dog) -> str:
        if not dog.birth_date: return "未登録"
        today = date.today(); months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
        return f"{months // 12}歳{months % 12}か月" if months >= 12 else f"{max(months, 0)}か月"

    resident_dogs = [dog for dog in dogs if dog.status not in {"delivered", "transferred"}]
    dog_rows = "".join(f'<tr><td>{html.escape(dog.call_name)}</td><td>{age(dog)}</td><td>{dog.birth_date or "未登録"}</td><td>{counts.get(dog.id, 0)}回</td></tr>' for dog in resident_dogs)
    active = [item for item in records if item.status in {"treatment", "followup", "chronic"}]
    recurring = [item for item in records if item.recurrence]
    upcoming = [item for item in records if item.next_followup_on and date.today() <= item.next_followup_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_followup_on and item.next_followup_on < date.today() and item.status != "recovered"]
    status_text = {"treatment": "治療中", "followup": "経過観察", "recovered": "完治", "chronic": "慢性"}; disease_types = {"digestive": "消化器", "respiratory": "呼吸器", "skin": "皮膚", "orthopedic": "整形・関節", "cardiac": "循環器", "urinary": "泌尿器", "reproductive": "生殖器", "infectious": "感染症", "other": "その他"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog: continue
        share = health_share_for(session, "disease", item.id); shared = bool(share and share.owner_visible)
        rows += f'''<tr><td>{item.diagnosed_on or "-"}</td><td>{html.escape(dog.call_name)}</td><td>{html.escape(item.disease_name)}</td><td>{disease_types.get(item.disease_category or "other", "その他")}</td><td>{status_text.get(item.status or "followup", "経過観察")}</td><td>{'再発' if item.recurrence else '-'}</td><td>{item.next_followup_on or '-'}</td><td><form method="post" action="/modules/health/shares/disease/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'共有中（非公開にする）' if shared else 'オーナーへ共有'}</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">健康管理へ戻る</a><h1>病歴管理</h1><p>犬ごとの罹患記録回数と、治療中・経過観察・完治・慢性の状態を管理します。</p>
    <div class="grid"><section class="tenant"><h3>治療・観察・慢性</h3><strong>{len(active)}件</strong></section><section class="tenant"><h3>再発記録</h3><strong>{len(recurring)}件</strong></section><section class="tenant"><h3>30日以内の再診</h3><strong>{len(upcoming)}件</strong></section><section class="tenant"><h3>期限超過</h3><strong>{len(overdue)}件</strong></section></div>
    <h2>犬ごとの罹患記録回数</h2><div style="overflow-x:auto"><table><tr><th>対象犬</th><th>年齢</th><th>誕生日</th><th>罹患回数</th></tr>{dog_rows or '<tr><td colspan="4">対象犬はいません。</td></tr>'}</table></div>
    <h2>病歴を追加</h2><form method="post" action="/modules/health/disease"><div class="grid"><div class="dog-picker"><label>対象犬を検索</label><input class="dog-search" type="search" data-dog-select="disease-dog" placeholder="呼び名・血統書名・犬種・区分で検索"><label class="dog-search-all"><input type="checkbox"> 販売済み・譲渡済みの犬も検索する</label><small class="dog-search-count"></small><label>対象犬</label><select id="disease-dog" name="dog_id" required>{options}</select></div>
    <div><label>疾患名</label><input name="disease_name" required></div><div><label>分類</label><select name="disease_category">{''.join(f'<option value="{key}">{label}</option>' for key, label in disease_types.items())}</select></div><div><label>診断日</label><input type="date" name="diagnosed_on" value="{date.today()}" required></div><div><label>状態</label><select name="disease_status"><option value="treatment">治療中</option><option value="followup">経過観察</option><option value="recovered">完治</option><option value="chronic">慢性</option></select></div><div><label>治療開始日</label><input type="date" name="treatment_started_on"></div><div><label>治療終了日</label><input type="date" name="treatment_ended_on"></div><div><label>次回診察・確認日</label><input type="date" name="next_followup_on"></div><div><label>動物病院</label><input name="clinic"></div><div><label>担当獣医師</label><input name="veterinarian"></div></div>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="recurrence" value="true"> 同じ疾患の再発として記録する</label><label>症状</label><textarea name="symptoms"></textarea><label>オーナーへ共有する説明</label><textarea name="owner_notes"></textarea><label>犬舎内部メモ（オーナーには表示されません）</label><textarea name="details"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> オーナーページにも共有する</label><input type="hidden" name="return_to" value="diseases"><button>病歴を登録</button></form>
    <h2>病歴一覧</h2><div style="overflow-x:auto"><table><tr><th>診断日</th><th>犬</th><th>疾患</th><th>分類</th><th>状態</th><th>再発</th><th>次回</th><th>共有</th></tr>{rows or '<tr><td colspan="8">病歴記録はまだありません。</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style><script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'在籍犬以外を含む ':'在籍犬 ')+matches.length+'頭から選択'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("病歴管理", body, user)


@app.post("/modules/health/disease")
def disease_create(dog_id: int = Form(...), disease_name: str = Form(...), diagnosed_on: str = Form(""), treatment_started_on: str = Form(""), treatment_ended_on: str = Form(""), disease_category: str = Form("other"), symptoms: str = Form(""), disease_status: str = Form("followup"), recurrence: bool = Form(False), clinic: str = Form(""), veterinarian: str = Form(""), next_followup_on: str = Form(""), owner_notes: str = Form(""), details: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    try:
        parse = lambda value: date.fromisoformat(value) if value else None
        diagnosed, started, ended, followup = parse(diagnosed_on), parse(treatment_started_on), parse(treatment_ended_on), parse(next_followup_on)
    except ValueError: raise HTTPException(status_code=400, detail="病歴の日付を確認してください")
    if started and ended and ended < started:
        raise HTTPException(status_code=400, detail="治療終了日は開始日以降にしてください")
    valid_categories = {"digestive", "respiratory", "skin", "orthopedic", "cardiac", "urinary", "reproductive", "infectious", "other"}
    if not disease_name.strip() or disease_category not in valid_categories or disease_status not in {"treatment", "followup", "recovered", "chronic"}: raise HTTPException(status_code=400, detail="病歴情報を確認してください")
    item = DiseaseHistory(tenant_id=tenant.id, dog_id=dog.id, disease_name=disease_name.strip(), diagnosed_on=diagnosed, treatment_started_on=started, treatment_ended_on=ended, disease_category=disease_category, symptoms=symptoms.strip() or None, status=disease_status, recurrence=recurrence, clinic=clinic.strip() or None, veterinarian=veterinarian.strip() or None, next_followup_on=followup, owner_notes=owner_notes.strip() or None, details=details.strip() or None)
    session.add(item); session.flush()
    if owner_visible: session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="disease", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    if followup: session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} {disease_name.strip()}再診・確認", category="health", due_date=followup))
    session.commit()
    return RedirectResponse("/modules/health/diseases" if return_to == "diseases" else "/modules/health", status_code=303)


@app.get("/modules/health/foods", response_class=HTMLResponse)
def health_foods_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(FoodHistory).where(FoodHistory.tenant_id == tenant.id).order_by(FoodHistory.started_on.desc(), FoodHistory.id.desc())).all()
    category_labels = {"puppy": "子犬", "parent": "親犬", "external": "外部犬"}; status_labels = {"resident": "在籍中", "reserved": "予約済み（在籍中）", "retired": "引退（在籍中）", "delivered": "販売済み", "transferred": "譲渡済み"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}｜{category_labels.get(dog.category, dog.category)}｜{status_labels.get(dog.status, dog.status)}{"｜" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    counts: dict[int, int] = {}
    for item in records:
        if item.dog_id: counts[item.dog_id] = counts.get(item.dog_id, 0) + 1

    def age(dog: Dog) -> str:
        if not dog.birth_date: return "未登録"
        today = date.today(); months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
        return f"{months // 12}歳{months % 12}か月" if months >= 12 else f"{max(months, 0)}か月"

    resident_dogs = [dog for dog in dogs if dog.status not in {"delivered", "transferred"}]
    dog_rows = "".join(f'<tr><td>{html.escape(dog.call_name)}</td><td>{age(dog)}</td><td>{dog.birth_date or "未登録"}</td><td>{counts.get(dog.id, 0)}回</td></tr>' for dog in resident_dogs)
    ongoing = [item for item in records if item.dog_id and (item.status or "ongoing") == "ongoing" and not item.ended_on]
    completed = [item for item in records if item.dog_id and ((item.status or "") == "completed" or item.ended_on)]
    type_labels = {"dry": "ドライ", "wet": "ウェット", "raw": "生食", "prescription": "療法食", "supplement": "サプリメント", "other": "その他"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id) if item.dog_id else None
        shared = False
        if dog:
            share = health_share_for(session, "food", item.id); shared = bool(share and share.owner_visible)
        amount = f"{item.amount_g:g}g" if item.amount_g is not None else "-"
        frequency = f"1日{item.times_per_day}回" if item.times_per_day else "-"
        share_cell = f'''<form method="post" action="/modules/health/shares/food/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'共有中（非公開にする）' if shared else 'オーナーへ共有'}</button></form>''' if dog else "旧記録"
        rows += f'''<tr><td>{html.escape(dog.call_name) if dog else "犬未設定"}</td><td>{html.escape(item.name)}</td><td>{type_labels.get(item.food_type or "other", "その他")}</td><td>{amount}</td><td>{frequency}</td><td>{item.started_on}</td><td>{item.ended_on or "継続中"}</td><td>{html.escape(item.change_reason or "-")}</td><td>{share_cell}</td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">健康管理へ戻る</a><h1>フード管理</h1><p>犬ごとのフード利用期間、給与量、変更履歴を管理します。</p>
    <div class="grid"><section class="tenant"><h3>利用中</h3><strong>{len(ongoing)}件</strong></section><section class="tenant"><h3>終了済み</h3><strong>{len(completed)}件</strong></section><section class="tenant"><h3>利用履歴</h3><strong>{len(records)}件</strong></section></div>
    <h2>犬ごとのフード変更回数</h2><div style="overflow-x:auto"><table><tr><th>対象犬</th><th>年齢</th><th>誕生日</th><th>利用履歴</th></tr>{dog_rows or '<tr><td colspan="4">対象犬はいません。</td></tr>'}</table></div>
    <h2>フード利用記録を追加</h2><form method="post" action="/modules/health/food"><div class="grid"><div class="dog-picker"><label>対象犬を検索</label><input class="dog-search" type="search" data-dog-select="food-dog" placeholder="呼び名・血統書名・犬種・区分で検索"><label class="dog-search-all"><input type="checkbox"> 販売済み・譲渡済みの犬も検索する</label><small class="dog-search-count"></small><label>対象犬</label><select id="food-dog" name="dog_id" required>{options}</select></div>
    <div><label>フード名</label><input name="name" required></div><div><label>メーカー</label><input name="manufacturer"></div><div><label>種類</label><select name="food_type">{''.join(f'<option value="{key}">{label}</option>' for key, label in type_labels.items())}</select></div><div><label>1日量（g）</label><input type="number" step="0.1" min="0.1" name="amount_g"></div><div><label>1日の給与回数</label><input type="number" min="1" max="10" name="times_per_day"></div><div><label>利用開始日</label><input type="date" name="started_on" value="{date.today()}" required></div><div><label>利用終了日</label><input type="date" name="ended_on"></div><div><label>状態</label><select name="food_status"><option value="ongoing">利用中</option><option value="completed">終了</option></select></div><div><label>変更・終了理由</label><input name="change_reason" placeholder="例：成犬用へ切替、食いつき低下"></div></div>
    <label>オーナーへ共有する説明</label><textarea name="owner_notes"></textarea><label>犬舎内部メモ（オーナーには表示されません）</label><textarea name="notes"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> オーナーページにも共有する</label><input type="hidden" name="return_to" value="foods"><button>フード利用記録を登録</button></form>
    <h2>フード利用履歴</h2><div style="overflow-x:auto"><table><tr><th>犬</th><th>フード</th><th>種類</th><th>1日量</th><th>回数</th><th>開始</th><th>終了・状態</th><th>変更理由</th><th>共有</th></tr>{rows or '<tr><td colspan="9">フード利用記録はまだありません。</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style><script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'在籍犬以外を含む ':'在籍犬 ')+matches.length+'頭から選択'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("フード管理", body, user)


@app.post("/modules/health/food")
def food_create(dog_id: int = Form(...), name: str = Form(...), started_on: str = Form(...), ended_on: str = Form(""), manufacturer: str = Form(""), food_type: str = Form("dry"), amount_g: str = Form(""), times_per_day: str = Form(""), food_status: str = Form("ongoing"), change_reason: str = Form(""), owner_notes: str = Form(""), notes: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    try:
        started = date.fromisoformat(started_on)
        ended = date.fromisoformat(ended_on) if ended_on else None
    except ValueError: raise HTTPException(status_code=400, detail="フード利用日を確認してください")
    if ended and ended < started:
        raise HTTPException(status_code=400, detail="利用終了日は開始日以降にしてください")
    if not name.strip() or food_type not in {"dry", "wet", "raw", "prescription", "supplement", "other"} or food_status not in {"ongoing", "completed"}:
        raise HTTPException(status_code=400, detail="フード情報を確認してください")
    if food_status == "completed" and not ended:
        raise HTTPException(status_code=400, detail="終了済みの場合は利用終了日を入力してください")
    try:
        amount = float(amount_g) if amount_g else None
        times = int(times_per_day) if times_per_day else None
    except ValueError:
        raise HTTPException(status_code=400, detail="給与量・回数を確認してください")
    if (amount is not None and amount <= 0) or (times is not None and not 1 <= times <= 10):
        raise HTTPException(status_code=400, detail="給与量・回数を確認してください")
    item = FoodHistory(tenant_id=tenant.id, dog_id=dog.id, name=name.strip(), manufacturer=manufacturer.strip() or None, food_type=food_type, amount_g=amount, times_per_day=times, started_on=started, ended_on=ended, status=food_status, change_reason=change_reason.strip() or None, owner_notes=owner_notes.strip() or None, notes=notes.strip() or None)
    session.add(item); session.flush()
    if owner_visible: session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="food", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    session.commit()
    return RedirectResponse("/modules/health/foods" if return_to == "foods" else "/modules/health", status_code=303)


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
        photo = f'<img src="/family/dogs/{dog.id}/photo" alt="{html.escape(dog.call_name)}">' if family_profile and family_profile.photo_data else f'<span class="family-home-photo-empty">{html.escape(dog.call_name[:1])}</span>'
        cards += f'''<a class="family-home-card" href="/family/dogs/{dog.id}">
          <span class="family-home-photo">{photo}</span>
          <span class="family-home-info"><h3>{html.escape(dog.call_name)}</h3>
          <p class="registered-name">{html.escape(dog.registered_name or "血統書名未登録")}</p>
          <p>{html.escape(dog.breed or "犬種未登録")} ／ {html.escape(sex)} ／ {html.escape(dog.color or "毛色未登録")}</p>
          <p>{html.escape(tenant.name)}</p><span class="badge">{relation}</span><span class="family-home-more">プロフィールを見る →</span></span>
        </a>'''
    if not cards:
        cards = '<div class="tenant"><p>まだ犬が連携されていません。</p><p>犬舎へ、登録したメールアドレスをお知らせください。</p></div>'
    body = f'''<h1>FAMILY ホーム</h1>
    <p>犬舎からあなたに連携された「うちの子」だけを表示しています。</p>
    <h2>うちの子</h2>
    <div class="family-home-grid">{cards}</div>'''
    return family_layout("FAMILY", body, user, session)


def family_health_notification_timing(items: list[tuple[Dog, str, date, int]]) -> list[tuple[Dog, str, date, int]]:
    """予定日は7日前・前日・当日、未完了の期限超過は継続表示する。"""
    return [item for item in items if item[3] < 0 or item[3] in {0, 1, 7}]


@app.get("/family/notifications", response_class=HTMLResponse)
def family_notifications(user: User = Depends(require_user), session: Session = Depends(db)):
    items: list[tuple[datetime, str]] = []
    settings = family_notification_setting(user, session)
    for conversation, message in (family_unread_message_items(user, session) if settings.messages else []):
        other_id = conversation.user2_id if conversation.user1_id == user.id else conversation.user1_id
        preview = message.body[:80] + ("…" if len(message.body) > 80 else "")
        card = f'''<a class="notification-item unread" href="/family/messages/{conversation.id}">
        <span class="notification-kind">新着メッセージ</span><span class="badge">未読</span>
        <p><strong>{html.escape(family_message_name(other_id, session))}さんから届きました</strong></p>
        <p>{html.escape(preview)}</p><small>{message.sent_at.strftime('%Y年%m月%d日 %H:%M')}</small></a>'''
        items.append((message.sent_at, card))
    for announcement, tenant in (family_unread_announcements(user, session) if settings.announcements else []):
        event = f" ／ 開催日 {announcement.event_date.strftime('%Y年%m月%d日')}" if announcement.event_date else ""
        card = f'''<a class="notification-item unread" href="/family/announcements/view/{announcement.id}">
        <span class="notification-kind">犬舎からのお知らせ</span><span class="badge">未読</span>
        <p><strong>{html.escape(announcement.title)}</strong></p><p>{html.escape(tenant.name)}{event}</p>
        <small>{announcement.created_at.strftime('%Y年%m月%d日 %H:%M')}</small></a>'''
        items.append((announcement.created_at, card))
    for like, item, dog in (family_unread_like_items(user, session) if settings.likes else []):
        liker_name = family_message_name(like.user_id, session)
        card = f'''<a class="notification-item unread" href="/family/timeline/{item.id}">
        <span class="notification-kind">タイムライン</span><span class="badge">未読</span>
        <p><strong>{html.escape(liker_name)}さんが{html.escape(dog.call_name)}の写真に「いいね」しました</strong></p>
        <small>{like.created_at.strftime('%Y年%m月%d日 %H:%M')}</small></a>'''
        items.append((like.created_at, card))
    for comment, item, dog in (family_unread_comment_items(user, session) if settings.likes else []):
        commenter_name = family_message_name(comment.user_id, session)
        preview = comment.body[:80] + ("…" if len(comment.body) > 80 else "")
        card = f'''<a class="notification-item unread" href="/family/timeline/{item.id}">
        <span class="notification-kind">タイムライン</span><span class="badge">未読</span>
        <p><strong>{html.escape(commenter_name)}さんが{html.escape(dog.call_name)}の写真にコメントしました</strong></p>
        <p>{html.escape(preview)}</p><small>{comment.created_at.strftime('%Y年%m月%d日 %H:%M')}</small></a>'''
        items.append((comment.created_at, card))
    for dog, event_type, event_date, days in (family_anniversary_notification_items(user, session) if settings.anniversaries else []):
        label = "誕生日" if event_type == "birthday" else "お迎え記念日"
        timing = "今日です" if days == 0 else ("明日です" if days == 1 else "7日後です")
        pseudo_time = datetime.combine(event_date, datetime.min.time(), tzinfo=ZoneInfo("Asia/Tokyo"))
        card = f'''<a class="notification-item unread" href="/family/anniversaries/notice/{dog.id}/{event_type}/{event_date.isoformat()}">
        <span class="notification-kind">大切な記念日</span><span class="badge">{days}日前</span>
        <p><strong>{html.escape(dog.call_name)}の{label}が{timing}</strong></p><small>{event_date.strftime('%Y年%m月%d日')}</small></a>'''
        items.append((pseudo_time, card))
    for dog, title, due_on, days in (family_health_notification_timing(family_vaccine_due_items(user, session)) if settings.health_vaccinations else []):
        timing = f"あと{days}日" if days >= 0 else f"{abs(days)}日超過"
        pseudo_time = datetime.combine(due_on, datetime.min.time(), tzinfo=ZoneInfo("Asia/Tokyo"))
        card = f'''<a class="notification-item unread" href="/family/dogs/{dog.id}/health/vaccination"><span class="notification-kind">ワクチン予定</span><span class="badge">{timing}</span><p><strong>{html.escape(dog.call_name)}の{html.escape(title)}予定を確認してください</strong></p><small>{due_on.strftime('%Y年%m月%d日')}</small></a>'''
        items.append((pseudo_time, card))
    for dog, title, due_on, days in (family_health_notification_timing(family_checkup_due_items(user, session)) if settings.health_checkups else []):
        timing = f"あと{days}日" if days >= 0 else f"{abs(days)}日超過"
        pseudo_time = datetime.combine(due_on, datetime.min.time(), tzinfo=ZoneInfo("Asia/Tokyo"))
        card = f'''<a class="notification-item unread" href="/family/dogs/{dog.id}/health/checkup"><span class="notification-kind">健診予定</span><span class="badge">{timing}</span><p><strong>{html.escape(dog.call_name)}の{html.escape(title)}予定を確認してください</strong></p><small>{due_on.strftime('%Y年%m月%d日')}</small></a>'''
        items.append((pseudo_time, card))
    for dog, title, due_on, days in (family_health_notification_timing(family_medication_due_items(user, session)) if settings.health_medications else []):
        timing = f"あと{days}日" if days >= 0 else f"{abs(days)}日超過"
        pseudo_time = datetime.combine(due_on, datetime.min.time(), tzinfo=ZoneInfo("Asia/Tokyo"))
        card = f'''<a class="notification-item unread" href="/family/dogs/{dog.id}/health/medication"><span class="notification-kind">投薬予定</span><span class="badge">{timing}</span><p><strong>{html.escape(dog.call_name)}の{html.escape(title)}投薬予定を確認してください</strong></p><small>{due_on.strftime('%Y年%m月%d日')}</small></a>'''
        items.append((pseudo_time, card))
    for dog, title, due_on, days in (family_health_notification_timing(family_disease_due_items(user, session)) if settings.health_followups else []):
        timing = f"あと{days}日" if days >= 0 else f"{abs(days)}日超過"
        pseudo_time = datetime.combine(due_on, datetime.min.time(), tzinfo=ZoneInfo("Asia/Tokyo"))
        card = f'''<a class="notification-item unread" href="/family/dogs/{dog.id}/health/disease"><span class="notification-kind">再診予定</span><span class="badge">{timing}</span><p><strong>{html.escape(dog.call_name)}の{html.escape(title)}再診・確認予定です</strong></p><small>{due_on.strftime('%Y年%m月%d日')}</small></a>'''
        items.append((pseudo_time, card))
    cards = "".join(card for _, card in sorted(items, key=lambda item: item[0], reverse=True))
    if not cards:
        cards = '<div class="tenant"><p>新しい通知はありません。</p><p><small>新着メッセージ、犬舎からのお知らせ、写真への「いいね」をここでまとめて確認できます。</small></p></div>'
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a><h1>通知</h1>
    <p>未読のメッセージ、犬舎からのお知らせ、成長写真への「いいね」をまとめて表示しています。</p>{cards}
    <p><a class="button secondary" href="/family/anniversaries">誕生日・お迎え記念日を確認</a> <a class="button secondary" href="/family/notification-settings">通知設定</a></p>'''
    return family_layout("通知｜FAMILY", body, user, session)


def family_notification_setting(user: User, session: Session) -> FamilyNotificationSetting:
    setting = session.scalar(select(FamilyNotificationSetting).where(FamilyNotificationSetting.user_id == user.id))
    if not setting:
        setting = FamilyNotificationSetting(user_id=user.id)
        session.add(setting)
        session.flush()
    return setting


@app.get("/family/notification-settings", response_class=HTMLResponse)
def family_notification_settings_page(user: User = Depends(require_user), session: Session = Depends(db)):
    setting = family_notification_setting(user, session)
    checked = lambda value: "checked" if value else ""
    body = f'''<a class="button secondary" href="/family/notifications">通知へ戻る</a><h1>通知設定</h1><form method="post">
    <div class="tenant"><label><input style="width:auto" type="checkbox" name="email_enabled" value="true" {checked(setting.email_enabled)}> 登録メールアドレスでも通知を受け取る</label>
    <p><small>メール配信サービスの設定後に送信されます。画面内通知はこの設定にかかわらず利用できます。</small></p></div>
    <div class="tenant"><label><input style="width:auto" type="checkbox" name="push_enabled" value="true" {checked(setting.push_enabled)}> この端末へプッシュ通知を送る</label>
    <p><button type="button" id="push-register" class="secondary">ブラウザ通知を許可する</button> <span id="push-state"></span></p><p><small>iPhoneではホーム画面へ追加したFAMILYから設定してください。</small></p></div>
    <label><input style="width:auto" type="checkbox" name="messages" value="true" {checked(setting.messages)}> 新着メッセージ</label>
    <label><input style="width:auto" type="checkbox" name="announcements" value="true" {checked(setting.announcements)}> 犬舎からのお知らせ</label>
    <label><input style="width:auto" type="checkbox" name="likes" value="true" {checked(setting.likes)}> 成長写真へのいいね</label>
    <label><input style="width:auto" type="checkbox" name="anniversaries" value="true" {checked(setting.anniversaries)}> 誕生日・お迎え記念日（7日前・前日・当日）</label>
    <h2>健康予定の通知</h2><p>各予定の7日前・前日・当日と、実施済みにしていない期限超過を通知します。</p>
    <label><input style="width:auto" type="checkbox" name="health_vaccinations" value="true" {checked(setting.health_vaccinations)}> ワクチン予定</label>
    <label><input style="width:auto" type="checkbox" name="health_checkups" value="true" {checked(setting.health_checkups)}> 健診予定</label>
    <label><input style="width:auto" type="checkbox" name="health_medications" value="true" {checked(setting.health_medications)}> 投薬予定</label>
    <label><input style="width:auto" type="checkbox" name="health_followups" value="true" {checked(setting.health_followups)}> 再診・経過確認予定</label>
    <button>通知設定を保存</button></form><form method="post" action="/family/push-test"><button class="secondary">この端末へテスト通知を送る</button></form><p><small>オフにしてもデータは削除されず、各画面から確認できます。</small></p>
    <script>const vapid={json.dumps(VAPID_PUBLIC_KEY)};function b64(s){{const p='='.repeat((4-s.length%4)%4),v=(s+p).replace(/-/g,'+').replace(/_/g,'/'),r=atob(v);return Uint8Array.from([...r].map(c=>c.charCodeAt(0)))}}
    document.getElementById('push-register').onclick=async()=>{{const state=document.getElementById('push-state');try{{if(!vapid)throw new Error('通知サーバーの設定準備中です');const reg=await navigator.serviceWorker.register('/family-push-worker.js');const permission=await Notification.requestPermission();if(permission!=='granted')throw new Error('ブラウザで通知が許可されませんでした');const sub=await reg.pushManager.subscribe({{userVisibleOnly:true,applicationServerKey:b64(vapid)}});const res=await fetch('/family/push-subscriptions',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(sub)}});if(!res.ok)throw new Error('端末登録に失敗しました');state.textContent='通知端末を登録しました';}}catch(e){{state.textContent=e.message}}}};</script>'''
    return family_layout("通知設定｜FAMILY", body, user, session)


@app.post("/family/notification-settings")
def family_notification_settings_save(messages: bool = Form(False), announcements: bool = Form(False), likes: bool = Form(False), anniversaries: bool = Form(False), health_vaccinations: bool = Form(False), health_checkups: bool = Form(False), health_medications: bool = Form(False), health_followups: bool = Form(False), email_enabled: bool = Form(False), push_enabled: bool = Form(False), user: User = Depends(require_user), session: Session = Depends(db)):
    setting = family_notification_setting(user, session)
    setting.messages, setting.announcements, setting.likes, setting.anniversaries = messages, announcements, likes, anniversaries
    setting.health_vaccinations, setting.health_checkups = health_vaccinations, health_checkups
    setting.health_medications, setting.health_followups = health_medications, health_followups
    setting.email_enabled = email_enabled
    setting.push_enabled = push_enabled
    session.commit()
    return RedirectResponse("/family/notification-settings", status_code=303)


@app.get("/family-push-worker.js")
def family_push_worker():
    script = '''self.addEventListener("push",event=>{let data={title:"ESTRELLA FAMILY",body:"新しいお知らせがあります",url:"/family/notifications"};try{data={...data,...event.data.json()}}catch(e){}event.waitUntil(self.registration.showNotification(data.title,{body:data.body,icon:"/favicon.ico",data:{url:data.url}}))});self.addEventListener("notificationclick",event=>{event.notification.close();event.waitUntil(clients.matchAll({type:"window",includeUncontrolled:true}).then(items=>{for(const item of items){if("focus" in item){item.navigate(event.notification.data.url);return item.focus()}}return clients.openWindow(event.notification.data.url)}))});'''
    return Response(content=script, media_type="application/javascript", headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.post("/family/push-subscriptions")
async def family_push_subscription_create(request: Request, user: User = Depends(require_user), session: Session = Depends(db)):
    payload = await request.json()
    endpoint, keys = str(payload.get("endpoint", "")), payload.get("keys") or {}
    p256dh, auth = str(keys.get("p256dh", "")), str(keys.get("auth", ""))
    if not endpoint.startswith("https://") or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="通知端末情報を確認できません")
    subscription = session.scalar(select(FamilyPushSubscription).where(FamilyPushSubscription.endpoint == endpoint))
    if subscription:
        subscription.user_id, subscription.p256dh, subscription.auth, subscription.active = user.id, p256dh, auth, True
    else:
        session.add(FamilyPushSubscription(user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth,
            user_agent=(request.headers.get("user-agent") or "")[:300] or None))
    setting = family_notification_setting(user, session); setting.push_enabled = True
    session.commit()
    return JSONResponse({"ok": True})


@app.post("/family/push-test", response_class=HTMLResponse)
def family_push_test(user: User = Depends(require_user), session: Session = Depends(db)):
    key = f"push:test:{user.id}:{datetime.now(timezone.utc).isoformat()}"
    sent = send_web_push(user.id, "messages", "ESTRELLA FAMILY テスト通知", "ブラウザ通知は正常に設定されています。", "/family/notifications", key, session)
    session.commit()
    if not sent:
        return HTMLResponse(family_layout("通知テスト｜FAMILY", '<h1>通知を送信できませんでした</h1><p class="error">先に「ブラウザ通知を許可する」を押し、新着メッセージとプッシュ通知をオンにして保存してください。</p><a class="button secondary" href="/family/notification-settings">通知設定へ戻る</a>', user, session), status_code=400)
    return family_layout("通知テスト｜FAMILY", '<h1>テスト通知を送信しました</h1><p>この端末に通知が表示されることをご確認ください。</p><a class="button secondary" href="/family/notification-settings">通知設定へ戻る</a>', user, session)


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


@app.get("/family/anniversaries/notice/{dog_id}/{event_type}/{event_date}")
def family_anniversary_notice_open(dog_id: int, event_type: str, event_date: str, user: User = Depends(require_user), session: Session = Depends(db)):
    if event_type not in {"birthday", "homecoming"} or not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=404)
    try:
        parsed = date.fromisoformat(event_date)
    except ValueError:
        raise HTTPException(status_code=404)
    existing = session.scalar(select(FamilyAnniversaryDismissal).where(
        FamilyAnniversaryDismissal.user_id == user.id, FamilyAnniversaryDismissal.dog_id == dog_id,
        FamilyAnniversaryDismissal.event_type == event_type, FamilyAnniversaryDismissal.event_date == parsed,
    ))
    if not existing:
        session.add(FamilyAnniversaryDismissal(user_id=user.id, dog_id=dog_id, event_type=event_type, event_date=parsed))
        session.commit()
    return RedirectResponse("/family/anniversaries", status_code=303)


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
    event_details = []
    if announcement.event_date:
        event_details.append(f"開催日：{announcement.event_date.strftime('%Y年%m月%d日')}")
    if announcement.event_time:
        event_details.append(f"開始時刻：{announcement.event_time}")
    if announcement.event_location:
        event_details.append(f"開催場所：{html.escape(announcement.event_location)}")
    if announcement.event_capacity:
        event_details.append(f"定員：{announcement.event_capacity}名")
    event = f'<div class="tenant"><p><strong>イベント情報</strong></p><p>{"<br>".join(event_details)}</p></div>' if event_details else ""
    response_form = ""
    if announcement.event_date:
        deadline = announcement.response_deadline or (datetime(
            announcement.event_date.year, announcement.event_date.month, announcement.event_date.day,
            9, 0, tzinfo=ZoneInfo("Asia/Tokyo"),
        ) - timedelta(days=1))
        if not deadline.tzinfo:
            deadline = deadline.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
        else:
            deadline = deadline.astimezone(ZoneInfo("Asia/Tokyo"))
        response_open = datetime.now(ZoneInfo("Asia/Tokyo")) < deadline
        deadline_label = deadline.strftime("%Y年%m月%d日 午前9時")
        response = session.scalar(select(FamilyEventResponse).where(
            FamilyEventResponse.announcement_id == announcement.id, FamilyEventResponse.user_id == user.id
        ))
        owned_dogs = session.scalars(
            select(Dog).join(DogOwnership, DogOwnership.dog_id == Dog.id)
            .where(DogOwnership.user_id == user.id, DogOwnership.tenant_id == announcement.tenant_id,
                   DogOwnership.active.is_(True), Dog.active.is_(True)).order_by(Dog.call_name)
        ).all()
        selected_names = set((response.dog_names or "").split("、")) if response else set()
        dog_checks = "".join(
            f'<label style="display:inline-flex;align-items:center;gap:6px;margin-right:16px"><input type="checkbox" name="dog_ids" value="{dog.id}" style="width:auto" {'checked' if dog.call_name in selected_names else ''}>{html.escape(dog.call_name)}</label>'
            for dog in owned_dogs
        ) or '<p><small>この犬舎と連携された愛犬はありません。</small></p>'
        current = {"attending": "参加", "waitlisted": "キャンセル待ち", "maybe": "検討中", "declined": "不参加"}.get(response.status, "未回答") if response else "未回答"
        form = f'''<form method="post" action="/family/announcements/view/{announcement.id}/response">
        <label>参加について</label><select name="response_status" required>
        <option value="attending" {'selected' if response and response.status == 'attending' else ''}>参加します</option>
        <option value="maybe" {'selected' if response and response.status == 'maybe' else ''}>検討中</option>
        <option value="declined" {'selected' if response and response.status == 'declined' else ''}>参加しません</option></select>
        <label>参加人数</label><input type="number" name="party_size" min="1" max="20" value="{response.party_size if response else 1}" required>
        <label>一緒に参加する愛犬</label><div>{dog_checks}</div>
        <label>犬舎への連絡事項（500文字まで）</label><textarea name="note" maxlength="500">{html.escape(response.note or '') if response else ''}</textarea>
        <button>回答を保存する</button></form>''' if response_open else '''<div class="tenant"><p><strong>回答受付は終了しました。</strong></p><p>変更が必要な場合は犬舎へ直接ご連絡ください。</p></div>'''
        response_form = f'''<section class="tenant"><h2 style="margin-top:0">イベント参加回答</h2><p>現在の回答：<span class="badge">{current}</span></p>
        <p><strong>回答期限：{deadline_label}</strong></p>{form}
        <p><small>回答期限までは何度でも変更できます。定員到達後は、設定されている場合にキャンセル待ちとなります。</small></p></section>'''
    activity = ""
    report = session.scalar(select(FamilyEventReport).where(FamilyEventReport.announcement_id == announcement.id))
    if report:
        attending = session.scalar(select(FamilyEventResponse.id).where(FamilyEventResponse.announcement_id == announcement.id,
            FamilyEventResponse.user_id == user.id, FamilyEventResponse.status == "attending"))
        photos = session.scalars(select(FamilyEventReportPhoto).where(FamilyEventReportPhoto.report_id == report.id).order_by(FamilyEventReportPhoto.photo_order)).all() if attending else []
        gallery = ''.join(f'<img src="/family/announcements/reports/photos/{photo.id}" alt="イベント写真" style="width:100%;height:220px;object-fit:contain;background:#f7edef;border-radius:12px">' for photo in photos)
        limited = '<p><small>集合写真はイベント参加者限定で公開しています。</small></p>' if not attending else ""
        activity = f'''<section class="tenant"><h2 style="margin-top:0">イベント活動報告</h2><div style="white-space:pre-wrap">{html.escape(report.body)}</div>{limited}<div class="grid">{gallery}</div></section>'''
    body = f'''<a class="button secondary" href="/family/announcements">お知らせ一覧へ戻る</a>
    <h1>{html.escape(announcement.title)}</h1><p><strong>{html.escape(tenant.name)}</strong>　<small>{announcement.created_at.date().strftime('%Y年%m月%d日')}掲載</small></p>
    {event}<div class="tenant" style="white-space:pre-wrap">{html.escape(announcement.body)}</div>{activity}{response_form}'''
    return family_layout(f"{announcement.title}｜FAMILY", body, user, session)


@app.get("/family/announcements/reports/photos/{photo_id}")
def family_event_report_photo(photo_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    record = session.execute(select(FamilyEventReportPhoto, FamilyEventReport, FamilyAnnouncement)
        .join(FamilyEventReport, FamilyEventReport.id == FamilyEventReportPhoto.report_id)
        .join(FamilyAnnouncement, FamilyAnnouncement.id == FamilyEventReport.announcement_id)
        .where(FamilyEventReportPhoto.id == photo_id)).first()
    if not record:
        raise HTTPException(status_code=404)
    photo, report, announcement = record
    allowed = announcement.tenant_id in family_kennel_tenant_ids(user, session) and session.scalar(select(FamilyEventResponse.id).where(
        FamilyEventResponse.announcement_id == announcement.id, FamilyEventResponse.user_id == user.id,
        FamilyEventResponse.status == "attending"))
    if not allowed:
        raise HTTPException(status_code=404)
    return Response(content=photo.photo_data, media_type=photo.photo_content_type, headers={"Cache-Control": "private, max-age=300"})


@app.post("/family/announcements/view/{announcement_id}/response")
def family_event_response_save(
    announcement_id: int, response_status: str = Form(...), party_size: int = Form(1),
    dog_ids: list[int] = Form([]), note: str = Form(""),
    user: User = Depends(require_user), session: Session = Depends(db),
):
    tenant_ids = family_kennel_tenant_ids(user, session)
    announcement = session.scalar(select(FamilyAnnouncement).where(
        FamilyAnnouncement.id == announcement_id, FamilyAnnouncement.tenant_id.in_(tenant_ids),
        FamilyAnnouncement.active.is_(True), FamilyAnnouncement.event_date.is_not(None),
    )) if tenant_ids else None
    if not announcement:
        raise HTTPException(status_code=404, detail="回答できるイベントが見つかりません")
    deadline = announcement.response_deadline or (datetime(
        announcement.event_date.year, announcement.event_date.month, announcement.event_date.day,
        9, 0, tzinfo=ZoneInfo("Asia/Tokyo"),
    ) - timedelta(days=1))
    if not deadline.tzinfo:
        deadline = deadline.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    else:
        deadline = deadline.astimezone(ZoneInfo("Asia/Tokyo"))
    if datetime.now(ZoneInfo("Asia/Tokyo")) >= deadline:
        raise HTTPException(status_code=403, detail="回答期限を過ぎています。変更が必要な場合は犬舎へ直接ご連絡ください")
    if response_status not in {"attending", "maybe", "declined"} or not 1 <= party_size <= 20 or len(note.strip()) > 500:
        raise HTTPException(status_code=400, detail="回答内容を確認してください")
    dogs = session.scalars(
        select(Dog).join(DogOwnership, DogOwnership.dog_id == Dog.id)
        .where(Dog.id.in_(dog_ids), DogOwnership.user_id == user.id,
               DogOwnership.tenant_id == announcement.tenant_id, DogOwnership.active.is_(True), Dog.active.is_(True))
        .order_by(Dog.call_name)
    ).all() if dog_ids else []
    response = session.scalar(select(FamilyEventResponse).where(
        FamilyEventResponse.announcement_id == announcement.id, FamilyEventResponse.user_id == user.id
    ))
    if not response:
        response = FamilyEventResponse(announcement_id=announcement.id, user_id=user.id)
        session.add(response)
    final_status = response_status
    if response_status == "attending" and announcement.event_capacity:
        reserved = session.scalar(select(func.coalesce(func.sum(FamilyEventResponse.party_size), 0)).where(
            FamilyEventResponse.announcement_id == announcement.id, FamilyEventResponse.status == "attending",
            FamilyEventResponse.user_id != user.id,
        )) or 0
        if reserved + party_size > announcement.event_capacity:
            if announcement.waitlist_enabled:
                final_status = "waitlisted"
            else:
                raise HTTPException(status_code=400, detail="定員に達しているため参加受付できません")
    response.status = final_status
    response.party_size = party_size
    response.dog_names = "、".join(dog.call_name for dog in dogs) or None
    response.note = note.strip() or None
    response.updated_at = datetime.now(timezone.utc)
    session.flush()
    promoted: list[FamilyEventResponse] = []
    if announcement.event_capacity and announcement.waitlist_enabled:
        attending_total = session.scalar(select(func.coalesce(func.sum(FamilyEventResponse.party_size), 0)).where(
            FamilyEventResponse.announcement_id == announcement.id, FamilyEventResponse.status == "attending",
        )) or 0
        waiting = session.scalars(select(FamilyEventResponse).where(
            FamilyEventResponse.announcement_id == announcement.id, FamilyEventResponse.status == "waitlisted",
        ).order_by(FamilyEventResponse.updated_at)).all()
        for waiting_response in waiting:
            if attending_total + waiting_response.party_size <= announcement.event_capacity:
                waiting_response.status = "attending"
                attending_total += waiting_response.party_size
                promoted.append(waiting_response)
    response_owner = session.get(User, user.id)
    if response_owner and email_notification_allowed(response_owner, "announcements", session):
        status_label = {"attending": "参加", "waitlisted": "キャンセル待ち", "maybe": "検討中", "declined": "不参加"}.get(response.status, response.status)
        queue_email(session, response_owner.email, "event_response", f"【ESTRELLA FAMILY】{announcement.title}の回答を受け付けました",
                    f"{response_owner.name} 様\n\n回答：{status_label}\n参加人数：{response.party_size}名\n愛犬：{response.dog_names or 'なし'}\n\n回答期限まではFAMILYのお知らせ画面から変更できます。",
                    announcement.tenant_id, response_owner.id)
    for promoted_response in promoted:
        promoted_owner = session.get(User, promoted_response.user_id)
        if promoted_owner and email_notification_allowed(promoted_owner, "announcements", session):
            queue_email(session, promoted_owner.email, "event_promoted", f"【ESTRELLA FAMILY】{announcement.title}の参加枠をご用意できました",
                        f"{promoted_owner.name} 様\n\nキャンセル待ちから「参加」へ繰り上がりました。参加人数：{promoted_response.party_size}名",
                        announcement.tenant_id, promoted_owner.id)
    session.commit()
    return RedirectResponse(f"/family/announcements/view/{announcement.id}", status_code=303)


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
        responses = session.scalar(select(func.count(FamilyEventResponse.id)).where(FamilyEventResponse.announcement_id == announcement.id)) if announcement.event_date else 0
        response_link = f'<a class="button secondary" href="/family/announcements/manage/{announcement.id}/responses">回答 {responses}件</a>' if announcement.event_date else "－"
        rows += f'''<tr><td>{html.escape(announcement.title)}</td><td>{event}</td><td>{state}</td><td>{announcement.created_at.date()}</td><td>{response_link}</td>
        <td><form class="inline" method="post" action="/family/announcements/manage/{announcement.id}/action"><input type="hidden" name="action" value="{action}"><button class="secondary">{action_label}</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/dashboard">ダッシュボードへ戻る</a><h1>{html.escape(tenant.name)} FAMILYお知らせ管理</h1>
    <p>この犬舎から愛犬を迎えたオーナー様だけに表示されます。</p>
    <form method="post"><label>タイトル（150文字まで）</label><input name="title" maxlength="150" required placeholder="例：ESTRELLA FAMILY会開催のお知らせ">
    <label>開催日（イベントの場合）</label><input type="date" name="event_date">
    <div class="grid"><div><label>開始時刻</label><input type="time" name="event_time"></div><div><label>定員（名）</label><input type="number" name="event_capacity" min="1" max="10000"></div></div>
    <label>開催場所</label><input name="event_location" maxlength="300" placeholder="会場名・住所など">
    <label>回答期限（未指定の場合は開催日前日の午前9時）</label><input type="datetime-local" name="response_deadline">
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="waitlist_enabled" value="true"> 定員到達後はキャンセル待ちで受け付ける</label>
    <label>お知らせ内容（2,000文字まで）</label><textarea name="body" maxlength="2000" required placeholder="日時、会場、持ち物、参加方法などをご案内ください。"></textarea>
    <button>お知らせを公開する</button></form><h2>掲載履歴</h2>
    <table><tr><th>タイトル</th><th>開催日</th><th>状態</th><th>掲載日</th><th>参加回答</th><th>操作</th></tr>{rows or '<tr><td colspan="6">お知らせはまだありません。</td></tr>'}</table>'''
    return layout("FAMILYお知らせ管理", body, user)


@app.get("/family/announcements/manage/{announcement_id}/responses", response_class=HTMLResponse)
def family_event_responses_manage(announcement_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    announcement = session.scalar(select(FamilyAnnouncement).where(
        FamilyAnnouncement.id == announcement_id, FamilyAnnouncement.tenant_id == tenant.id,
        FamilyAnnouncement.event_date.is_not(None),
    ))
    if not announcement:
        raise HTTPException(status_code=404, detail="イベントが見つかりません")
    records = session.execute(
        select(FamilyEventResponse, User).join(User, User.id == FamilyEventResponse.user_id)
        .where(FamilyEventResponse.announcement_id == announcement.id)
        .order_by(FamilyEventResponse.status, User.name)
    ).all()
    labels = {"attending": "参加", "waitlisted": "キャンセル待ち", "maybe": "検討中", "declined": "不参加"}
    rows = ""
    attending_people = 0
    for response, owner in records:
        if response.status == "attending":
            attending_people += response.party_size
        rows += f'''<tr><td>{html.escape(owner.name)}</td><td>{labels.get(response.status, response.status)}</td>
        <td>{response.party_size}名</td><td>{html.escape(response.dog_names or "－")}</td><td style="white-space:pre-wrap">{html.escape(response.note or "－")}</td>
        <td>{response.updated_at.strftime('%Y-%m-%d %H:%M')}</td></tr>'''
    summary = {status: sum(1 for response, _ in records if response.status == status) for status in labels}
    body = f'''<a class="button secondary" href="/family/announcements/manage">お知らせ管理へ戻る</a><h1>{html.escape(announcement.title)} 参加回答</h1>
    <p>開催日：{announcement.event_date.strftime('%Y年%m月%d日')}</p><div class="grid">
    <div class="module"><h3>参加</h3><p><strong>{summary['attending']}組／{attending_people}名</strong></p></div>
    <div class="module"><h3>キャンセル待ち</h3><p><strong>{summary['waitlisted']}組</strong></p></div>
    <div class="module"><h3>検討中</h3><p><strong>{summary['maybe']}組</strong></p></div>
    <div class="module"><h3>不参加</h3><p><strong>{summary['declined']}組</strong></p></div></div>
    <p><a class="button" href="/family/announcements/manage/{announcement.id}/report">活動報告を作成</a> <a class="button secondary" href="/family/announcements/manage/{announcement.id}/responses.csv">CSV出力</a> <a class="button secondary" href="/family/announcements/manage/{announcement.id}/responses.pdf">PDF出力</a></p>
    <table><tr><th>オーナー</th><th>回答</th><th>人数</th><th>愛犬</th><th>連絡事項</th><th>更新日時</th></tr>
    {rows or '<tr><td colspan="6">回答はまだありません。</td></tr>'}</table>'''
    return layout("イベント参加回答", body, user)


@app.get("/family/announcements/manage/{announcement_id}/report", response_class=HTMLResponse)
def family_event_report_manage(announcement_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    announcement = session.scalar(select(FamilyAnnouncement).where(FamilyAnnouncement.id == announcement_id,
        FamilyAnnouncement.tenant_id == tenant.id, FamilyAnnouncement.event_date.is_not(None)))
    if not announcement:
        raise HTTPException(status_code=404)
    report = session.scalar(select(FamilyEventReport).where(FamilyEventReport.announcement_id == announcement.id))
    count = session.scalar(select(func.count(FamilyEventReportPhoto.id)).where(FamilyEventReportPhoto.report_id == report.id)) if report else 0
    body = f'''<a class="button secondary" href="/family/announcements/manage/{announcement.id}/responses">参加回答へ戻る</a><h1>イベント活動報告</h1><p>{html.escape(announcement.title)}</p><form method="post" enctype="multipart/form-data"><label>開催報告（2,000文字まで）</label><textarea name="body" maxlength="2000" required>{html.escape(report.body if report else '')}</textarea><label>参加者限定写真（最大10枚・各8MBまで）</label><input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple><p><small>現在 {count or 0}枚。新しい写真を選択すると既存写真を置き換えます。</small></p><button>活動報告を公開する</button></form>'''
    return layout("イベント活動報告", body, user)


@app.post("/family/announcements/manage/{announcement_id}/report")
async def family_event_report_save(announcement_id: int, body: str = Form(...), photos: list[UploadFile] = File([]), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    announcement = session.scalar(select(FamilyAnnouncement).where(FamilyAnnouncement.id == announcement_id,
        FamilyAnnouncement.tenant_id == tenant.id, FamilyAnnouncement.event_date.is_not(None)))
    body = body.strip()
    if not announcement or not body or len(body) > 2000 or len([p for p in photos if p.filename]) > 10:
        raise HTTPException(status_code=400, detail="活動報告の内容を確認してください")
    report = session.scalar(select(FamilyEventReport).where(FamilyEventReport.announcement_id == announcement.id))
    if not report:
        report = FamilyEventReport(announcement_id=announcement.id, body=body, created_by_id=user.id); session.add(report); session.flush()
    report.body, report.updated_at = body, datetime.now(timezone.utc)
    selected = [p for p in photos if p.filename]
    if selected:
        for old in session.scalars(select(FamilyEventReportPhoto).where(FamilyEventReportPhoto.report_id == report.id)).all(): session.delete(old)
        for position, photo in enumerate(selected):
            content = await photo.read(8 * 1024 * 1024 + 1)
            if not content or len(content) > 8 * 1024 * 1024: raise HTTPException(status_code=400, detail="写真は1枚8MB以下にしてください")
            try:
                with Image.open(io.BytesIO(content)) as source:
                    image = ImageOps.exif_transpose(source); image.thumbnail((1800, 1800), Image.Resampling.LANCZOS); image = image.convert("RGB"); output = io.BytesIO(); image.save(output, "JPEG", quality=88, optimize=True)
            except Exception: raise HTTPException(status_code=400, detail="写真形式を確認してください")
            session.add(FamilyEventReportPhoto(report_id=report.id, photo_data=output.getvalue(), photo_order=position))
    session.commit()
    return RedirectResponse(f"/family/announcements/manage/{announcement.id}/report", status_code=303)


def family_event_export_records(announcement_id: int, tenant_id: int, session: Session):
    announcement = session.scalar(select(FamilyAnnouncement).where(
        FamilyAnnouncement.id == announcement_id, FamilyAnnouncement.tenant_id == tenant_id,
        FamilyAnnouncement.event_date.is_not(None)))
    if not announcement:
        raise HTTPException(status_code=404, detail="イベントが見つかりません")
    records = session.execute(select(FamilyEventResponse, User).join(User, User.id == FamilyEventResponse.user_id)
        .where(FamilyEventResponse.announcement_id == announcement.id).order_by(FamilyEventResponse.status, User.name)).all()
    return announcement, records


@app.get("/family/announcements/manage/{announcement_id}/responses.csv")
def family_event_responses_csv(announcement_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    _, tenant = access
    announcement, records = family_event_export_records(announcement_id, tenant.id, session)
    labels = {"attending": "参加", "waitlisted": "キャンセル待ち", "maybe": "検討中", "declined": "不参加"}
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["オーナー", "回答", "人数", "愛犬", "連絡事項", "更新日時"])
    for response, owner in records:
        writer.writerow([owner.name, labels.get(response.status, response.status), response.party_size,
                         response.dog_names or "", response.note or "", response.updated_at.strftime("%Y-%m-%d %H:%M")])
    filename = f"event-{announcement.id}-participants.csv"
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/family/announcements/manage/{announcement_id}/responses.pdf")
def family_event_responses_pdf(announcement_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    _, tenant = access
    announcement, records = family_event_export_records(announcement_id, tenant.id, session)
    labels = {"attending": "参加", "waitlisted": "キャンセル待ち", "maybe": "検討中", "declined": "不参加"}
    output = io.BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    pdf = canvas.Canvas(output, pagesize=landscape(A4))
    width, height = landscape(A4)
    def header():
        pdf.setFont("HeiseiKakuGo-W5", 15); pdf.drawString(35, height - 35, f"{announcement.title} 参加者名簿")
        pdf.setFont("HeiseiKakuGo-W5", 9); pdf.drawString(35, height - 52, f"開催日：{announcement.event_date.strftime('%Y年%m月%d日')}　出力日：{date.today().strftime('%Y年%m月%d日')}")
        pdf.drawString(35, height - 72, "オーナー"); pdf.drawString(175, height - 72, "回答"); pdf.drawString(275, height - 72, "人数"); pdf.drawString(320, height - 72, "愛犬"); pdf.drawString(500, height - 72, "連絡事項")
    header(); y = height - 90
    for response, owner in records:
        if y < 35:
            pdf.showPage(); header(); y = height - 90
        values = [owner.name[:22], labels.get(response.status, response.status), f"{response.party_size}名", (response.dog_names or "－")[:28], (response.note or "－")[:45]]
        for x, value in zip([35, 175, 275, 320, 500], values):
            pdf.drawString(x, y, value)
        y -= 18
    pdf.save()
    return Response(content=output.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="event-{announcement.id}-participants.pdf"'})


@app.post("/family/announcements/manage")
def family_announcement_create(title: str = Form(...), body: str = Form(...), event_date: str = Form(""), event_time: str = Form(""), event_location: str = Form(""), event_capacity: str = Form(""), response_deadline: str = Form(""), waitlist_enabled: bool = Form(False), access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    title, body = title.strip(), body.strip()
    if not title or len(title) > 150 or not body or len(body) > 2000:
        raise HTTPException(status_code=400, detail="タイトルとお知らせ内容の文字数を確認してください")
    try:
        parsed_event_date = date.fromisoformat(event_date) if event_date else None
        if event_time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", event_time):
            raise ValueError
        parsed_capacity = int(event_capacity) if event_capacity else None
        if parsed_capacity is not None and not 1 <= parsed_capacity <= 10000:
            raise ValueError
        parsed_deadline = datetime.fromisoformat(response_deadline).replace(tzinfo=ZoneInfo("Asia/Tokyo")) if response_deadline else None
    except ValueError:
        raise HTTPException(status_code=400, detail="開催日・時刻・定員・回答期限を確認してください")
    if not parsed_event_date and any([event_time, event_location.strip(), parsed_capacity, parsed_deadline, waitlist_enabled]):
        raise HTTPException(status_code=400, detail="イベント情報を設定する場合は開催日が必要です")
    announcement = FamilyAnnouncement(tenant_id=tenant.id, title=title, body=body, event_date=parsed_event_date,
                                      event_time=event_time or None, event_location=event_location.strip()[:300] or None,
                                      event_capacity=parsed_capacity, response_deadline=parsed_deadline,
                                      waitlist_enabled=waitlist_enabled, created_by_id=user.id)
    session.add(announcement)
    session.flush()
    owner_ids = set(session.scalars(select(DogOwnership.user_id).where(DogOwnership.tenant_id == tenant.id, DogOwnership.active.is_(True))).all())
    base_url = os.environ.get("APP_BASE_URL", "https://dog-management.benefit-navi.com").rstrip("/")
    for owner_id in owner_ids:
        owner = session.get(User, owner_id)
        if owner and owner.active:
            if email_notification_allowed(owner, "announcements", session):
                queue_email(session, owner.email, "announcement", f"【{tenant.name}】{title}",
                            f"{owner.name} 様\n\n{body[:1000]}\n\n詳しく見る：{base_url}/family/announcements/view/{announcement.id}",
                            tenant.id, owner.id, f"announcement:{announcement.id}:user:{owner.id}")
            send_web_push(owner.id, "announcements", f"{tenant.name}からのお知らせ", title,
                          f"/family/announcements/view/{announcement.id}", f"push:announcement:{announcement.id}:user:{owner.id}", session)
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
    album_groups: set[str] = set()
    visibility_labels = {"private": "非公開", "relatives": "親戚犬まで", "family": "FAMILY全体"}
    for item in album_items:
        if item.post_group and item.post_group in album_groups:
            continue
        if item.post_group:
            album_groups.add(item.post_group)
        if item.visibility == "private" and item.uploaded_by_id != user.id:
            continue
        taken = item.taken_on.strftime("%Y年%m月%d日") if item.taken_on else "撮影日未設定"
        delete_button = f'<form method="post" action="/family/dogs/{dog.id}/album/{item.id}/delete"><button class="danger">削除</button></form>' if item.uploaded_by_id == user.id else ''
        edit_form = f'''<details><summary>投稿内容を編集</summary><form method="post" action="/family/dogs/{dog.id}/album/{item.id}/edit">
        <label>撮影日</label><input type="date" name="taken_on" value="{item.taken_on.isoformat() if item.taken_on else ''}">
        <label>コメント</label><textarea name="caption" maxlength="300">{html.escape(item.caption or '')}</textarea>
        <label>公開範囲</label><select name="visibility"><option value="private" {'selected' if item.visibility == 'private' else ''}>非公開（自分だけ）</option>
        <option value="relatives" {'selected' if item.visibility == 'relatives' else ''}>親戚犬のオーナーまで</option><option value="family" {'selected' if item.visibility == 'family' else ''}>FAMILY全体</option></select>
        <button>変更を保存</button></form></details>''' if item.uploaded_by_id == user.id else ''
        group_count = session.scalar(select(func.count(FamilyDogAlbumItem.id)).where(FamilyDogAlbumItem.post_group == item.post_group)) if item.post_group else 1
        album_cards += f'''<article class="album-item"><a href="/family/dogs/{dog.id}/album/{item.id}/photo" target="_blank"><img src="/family/dogs/{dog.id}/album/{item.id}/photo" alt="{html.escape(item.caption or dog.call_name)}"></a>
        <div class="album-meta"><p><strong>{taken}</strong> <span class="badge">{visibility_labels.get(item.visibility, "非公開")}</span> {'<span class="badge">写真 ' + str(group_count) + '枚</span>' if group_count > 1 else ''}</p><p>{html.escape(item.caption or "コメントなし")}</p>{edit_form}{delete_button}</div></article>'''
    album_section = f'''<h2>成長アルバム</h2><p>写真を押すと大きく表示できます。</p><div class="album-grid">{album_cards or '<p>成長アルバムの写真はまだありません。</p>'}</div>
    <p><a class="button success" href="/family/growth/add/{dog.id}">＋ {html.escape(dog.call_name)}の成長記録を追加</a></p>'''
    edit_form = f'''<h2>愛犬プロフィール写真・紹介文</h2><form method="post" action="/family/dogs/{dog.id}/profile" enctype="multipart/form-data">
    <label>メイン写真（JPG・PNG・WebP／8MBまで）</label><input type="file" name="photo" accept="image/jpeg,image/png,image/webp">
    <label>愛犬の紹介（300文字まで）</label><textarea name="introduction" maxlength="300" placeholder="性格や好きなことなどをご紹介ください。">{html.escape(profile.introduction if profile and profile.introduction else '')}</textarea>
    <button>愛犬プロフィールを保存</button></form>
    {f'<form method="post" action="/family/dogs/{dog.id}/photo/delete"><button class="danger">写真を削除</button></form>' if profile and profile.photo_data else ''}''' if ownership.relationship == "primary" else '<p><small>写真と紹介文は主オーナーが変更できます。</small></p>'
    body = f'''<a class="button secondary" href="/family">FAMILYホームへ戻る</a>
    <h1>{html.escape(dog.call_name)}</h1><p><span class="badge">{relation}</span> {title_marks(dog.titles)}</p>
    {photo}{introduction}
    <div class="tenant"><strong>{html.escape(tenant.name)}</strong>から共有されています。 <a class="button" href="/family/dogs/{dog.id}/health">うちの子健康管理</a></div>
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


@app.get("/family/dogs/{dog_id}/health/calendar", response_class=HTMLResponse)
def family_dog_health_calendar(dog_id: int, month: str = "", user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned:
        raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, dog = owned
    try:
        selected = date.fromisoformat(f"{month}-01") if month else date.today().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="表示月を確認してください")
    if month and not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(status_code=400, detail="表示月を確認してください")

    first_day = selected.replace(day=1)
    next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    previous_month = (first_day - timedelta(days=1)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    events: dict[date, list[tuple[str, str, str]]] = {}

    def add_event(event_date: date | None, category: str, label: str, title: str):
        if event_date and first_day <= event_date <= month_end and not family_health_schedule_completed(user.id, dog.id, category, title, event_date, session):
            events.setdefault(event_date, []).append((category, label, title))

    owner_records = session.scalars(select(OwnerHealthRecord).where(
        OwnerHealthRecord.dog_id == dog.id, OwnerHealthRecord.tenant_id == ownership.tenant_id,
        OwnerHealthRecord.next_due_on.between(first_day, month_end),
    )).all()
    owner_labels = {"vaccination": "ワクチン", "checkup": "健診", "medication": "投薬", "disease": "再診"}
    for item in owner_records:
        if item.category in owner_labels and not (item.category == "medication" and item.value == "終了") and not (item.category == "disease" and item.value == "完治"):
            add_event(item.next_due_on, item.category, owner_labels[item.category], item.title)

    shares = session.scalars(select(HealthRecordShare).where(
        HealthRecordShare.dog_id == dog.id, HealthRecordShare.owner_visible.is_(True)
    )).all()
    shared_ids: dict[str, list[int]] = {}
    for share in shares:
        shared_ids.setdefault(share.record_type, []).append(share.record_id)
    if shared_ids.get("vaccination"):
        for item in session.scalars(select(Vaccination).where(Vaccination.id.in_(shared_ids["vaccination"]), Vaccination.dog_id == dog.id, Vaccination.next_due_on.between(first_day, month_end))).all():
            add_event(item.next_due_on, "vaccination", "ワクチン", item.vaccine_name)
    if shared_ids.get("health"):
        for item in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(shared_ids["health"]), HealthRecord.dog_id == dog.id, HealthRecord.category == "checkup", HealthRecord.next_due_on.between(first_day, month_end))).all():
            add_event(item.next_due_on, "checkup", "健診", "健康診断")
    if shared_ids.get("medication"):
        for item in session.scalars(select(Medication).where(Medication.id.in_(shared_ids["medication"]), Medication.dog_id == dog.id, Medication.status != "completed", Medication.next_due_on.between(first_day, month_end))).all():
            add_event(item.next_due_on, "medication", "投薬", item.medicine_name)
    if shared_ids.get("disease"):
        for item in session.scalars(select(DiseaseHistory).where(DiseaseHistory.id.in_(shared_ids["disease"]), DiseaseHistory.dog_id == dog.id, DiseaseHistory.status != "recovered", DiseaseHistory.next_followup_on.between(first_day, month_end))).all():
            add_event(item.next_followup_on, "disease", "再診", item.disease_name)

    colors = {"vaccination": "#e9d7f2", "checkup": "#d8ecf2", "medication": "#f6e1b8", "disease": "#f4c9ca"}
    cells = ""
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(first_day.year, first_day.month):
        cells += "<tr>"
        for day in week:
            outside = day.month != first_day.month
            day_events = "".join(
                f'<div style="margin:4px 0;padding:4px 6px;border-radius:8px;background:{colors[category]};color:#3f3437;font-size:.78rem"><a href="/family/dogs/{dog.id}/health/{category}" style="color:#3f3437;text-decoration:none"><strong>{label}</strong> {html.escape(title)}</a><form method="post" action="/family/dogs/{dog.id}/health/schedules/complete" style="margin:0"><input type="hidden" name="category" value="{category}"><input type="hidden" name="title" value="{html.escape(title)}"><input type="hidden" name="due_on" value="{day}"><input type="hidden" name="return_month" value="{first_day:%Y-%m}"><button class="success" style="margin:4px 0 0;padding:3px 6px;font-size:.68rem">実施済みにする</button></form></div>'
                for category, label, title in events.get(day, [])
            )
            today_style = "outline:2px solid #b98b9a;" if day == date.today() else ""
            cells += f'<td style="vertical-align:top;height:112px;min-width:110px;padding:8px;opacity:{".35" if outside else "1"};{today_style}"><strong>{day.day}</strong>{day_events}</td>'
        cells += "</tr>"
    event_count = sum(len(items) for items in events.values())
    body = f'''<a class="button secondary" href="/family/dogs/{dog.id}/health">健康管理へ戻る</a>
    <h1>{html.escape(dog.call_name)}の健康カレンダー</h1>
    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px"><a class="button secondary" href="?month={previous_month:%Y-%m}">← 前月</a><h2>{first_day.year}年{first_day.month}月</h2><a class="button secondary" href="?month={next_month:%Y-%m}">翌月 →</a></div>
    <p><strong>{event_count}件</strong>の健康予定があります。予定を選ぶと各カテゴリーの管理画面を開きます。</p>
    <p><span class="badge" style="background:#e9d7f2">ワクチン</span> <span class="badge" style="background:#d8ecf2">健診</span> <span class="badge" style="background:#f6e1b8">投薬</span> <span class="badge" style="background:#f4c9ca">再診</span></p>
    <div style="overflow-x:auto"><table style="table-layout:fixed;min-width:800px"><tr><th style="color:#b54b56">日</th><th>月</th><th>火</th><th>水</th><th>木</th><th>金</th><th style="color:#416b9b">土</th></tr>{cells}</table></div>
    <p><small>表示されるのは、オーナーが登録した予定と、ブリーダーから共有された予定のみです。</small></p>'''
    return family_layout(f"{dog.call_name}の健康カレンダー｜FAMILY", body, user, session)


@app.post("/family/dogs/{dog_id}/health/schedules/complete")
def family_health_schedule_complete(dog_id: int, category: str = Form(...), title: str = Form(...), due_on: str = Form(...), return_month: str = Form(""), user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned:
        raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, _ = owned
    if category not in {"vaccination", "checkup", "medication", "disease"} or not title.strip() or len(title.strip()) > 150:
        raise HTTPException(status_code=400, detail="健康予定を確認してください")
    try:
        parsed_due = date.fromisoformat(due_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="健康予定を確認してください")
    valid = session.scalar(select(OwnerHealthRecord.id).where(
        OwnerHealthRecord.dog_id == dog_id, OwnerHealthRecord.tenant_id == ownership.tenant_id,
        OwnerHealthRecord.category == category, OwnerHealthRecord.title == title.strip(), OwnerHealthRecord.next_due_on == parsed_due,
    )) is not None
    record_types = {"vaccination": "vaccination", "checkup": "health", "medication": "medication", "disease": "disease"}
    shared_ids = session.scalars(select(HealthRecordShare.record_id).where(
        HealthRecordShare.dog_id == dog_id, HealthRecordShare.record_type == record_types[category], HealthRecordShare.owner_visible.is_(True)
    )).all()
    if not valid and shared_ids:
        if category == "vaccination":
            valid = session.scalar(select(Vaccination.id).where(Vaccination.id.in_(shared_ids), Vaccination.dog_id == dog_id, Vaccination.vaccine_name == title.strip(), Vaccination.next_due_on == parsed_due)) is not None
        elif category == "checkup":
            valid = title.strip() == "健康診断" and session.scalar(select(HealthRecord.id).where(HealthRecord.id.in_(shared_ids), HealthRecord.dog_id == dog_id, HealthRecord.category == "checkup", HealthRecord.next_due_on == parsed_due)) is not None
        elif category == "medication":
            valid = session.scalar(select(Medication.id).where(Medication.id.in_(shared_ids), Medication.dog_id == dog_id, Medication.medicine_name == title.strip(), Medication.next_due_on == parsed_due, Medication.status != "completed")) is not None
        else:
            valid = session.scalar(select(DiseaseHistory.id).where(DiseaseHistory.id.in_(shared_ids), DiseaseHistory.dog_id == dog_id, DiseaseHistory.disease_name == title.strip(), DiseaseHistory.next_followup_on == parsed_due, DiseaseHistory.status != "recovered")) is not None
    if not valid:
        raise HTTPException(status_code=404, detail="完了できる健康予定が見つかりません")
    session.add(FamilyHealthScheduleCompletion(user_id=user.id, dog_id=dog_id, category=category, title=title.strip(), due_on=parsed_due))
    session.commit()
    month_query = f"?month={return_month}" if re.fullmatch(r"\d{4}-\d{2}", return_month) else ""
    return RedirectResponse(f"/family/dogs/{dog_id}/health/calendar{month_query}", status_code=303)


@app.get("/family/dogs/{dog_id}/health/schedules/completed", response_class=HTMLResponse)
def family_health_schedule_completion_history(dog_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned:
        raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    _, dog = owned
    completions = session.scalars(select(FamilyHealthScheduleCompletion).where(
        FamilyHealthScheduleCompletion.user_id == user.id,
        FamilyHealthScheduleCompletion.dog_id == dog.id,
    ).order_by(FamilyHealthScheduleCompletion.completed_at.desc(), FamilyHealthScheduleCompletion.id.desc())).all()
    labels = {"vaccination": "ワクチン", "checkup": "健診", "medication": "投薬", "disease": "再診"}
    rows = ""
    for item in completions:
        completed_at = item.completed_at
        if completed_at.tzinfo:
            completed_at = completed_at.astimezone(ZoneInfo("Asia/Tokyo"))
        rows += f'''<tr><td>{item.due_on}</td><td>{labels.get(item.category, "健康予定")}</td><td>{html.escape(item.title)}</td><td>{completed_at.strftime("%Y-%m-%d %H:%M")}</td><td><form method="post" action="/family/dogs/{dog.id}/health/schedules/completed/{item.id}/undo"><label style="font-weight:400"><input type="checkbox" name="confirm_undo" value="true" style="width:auto" required> 取り消しを確認</label><button class="secondary" style="margin:4px 0 0">未完了に戻す</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/family/dogs/{dog.id}/health">健康管理へ戻る</a>
    <h1>{html.escape(dog.call_name)}の実施済み健康予定</h1>
    <p>実施済みにした健康予定を新しい順に表示します。取り消すと、対象期間の通知・健康トップ・カレンダーへ再表示されます。</p>
    <div style="overflow-x:auto"><table><tr><th>予定日</th><th>種類</th><th>内容</th><th>完了操作日時</th><th>操作</th></tr>{rows or '<tr><td colspan="5">実施済みの健康予定はありません。</td></tr>'}</table></div>'''
    return family_layout(f"{dog.call_name}の実施済み健康予定｜FAMILY", body, user, session)


@app.post("/family/dogs/{dog_id}/health/schedules/completed/{completion_id}/undo")
def family_health_schedule_completion_undo(dog_id: int, completion_id: int, confirm_undo: bool = Form(False), user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    if not confirm_undo:
        raise HTTPException(status_code=400, detail="取り消しの確認が必要です")
    completion = session.scalar(select(FamilyHealthScheduleCompletion).where(
        FamilyHealthScheduleCompletion.id == completion_id,
        FamilyHealthScheduleCompletion.user_id == user.id,
        FamilyHealthScheduleCompletion.dog_id == dog_id,
    ))
    if not completion:
        raise HTTPException(status_code=404, detail="実施済みの健康予定が見つかりません")
    session.delete(completion)
    session.commit()
    return RedirectResponse(f"/family/dogs/{dog_id}/health/schedules/completed", status_code=303)


@app.get("/family/dogs/{dog_id}/health", response_class=HTMLResponse)
def family_dog_health(dog_id: int, health_category: str = "", date_from: str = "", date_to: str = "", keyword: str = "", user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned:
        raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, dog = owned
    tenant = session.get(Tenant, ownership.tenant_id)
    shares = session.scalars(select(HealthRecordShare).where(
        HealthRecordShare.dog_id == dog.id, HealthRecordShare.owner_visible.is_(True)
    )).all()
    shared_ids: dict[str, list[int]] = {}
    for share in shares:
        shared_ids.setdefault(share.record_type, []).append(share.record_id)

    owner_records = session.scalars(select(OwnerHealthRecord).where(
        OwnerHealthRecord.dog_id == dog.id, OwnerHealthRecord.tenant_id == ownership.tenant_id
    ).order_by(OwnerHealthRecord.recorded_on.desc(), OwnerHealthRecord.id.desc())).all()
    owner_category_labels = {"weight": "体重", "vaccination": "ワクチン", "checkup": "健診", "medication": "投薬", "disease": "病歴", "food": "フード", "other": "その他"}
    category_counts = {key: sum(1 for item in owner_records if item.category == key) for key in owner_category_labels}
    category_counts["vaccination"] += len(shared_ids.get("vaccination", [])); category_counts["medication"] += len(shared_ids.get("medication", [])); category_counts["disease"] += len(shared_ids.get("disease", [])); category_counts["food"] += len(shared_ids.get("food", []))

    entries: list[tuple[date, str, str, str]] = []
    shared_checkup_files = ""
    if shared_ids.get("health"):
        for item in session.scalars(select(HealthRecord).where(
            HealthRecord.id.in_(shared_ids["health"]), HealthRecord.dog_id == dog.id
        )).all():
            label = {"weight": "体重", "checkup": "健康診断", "treatment": "診療"}.get(item.category, "健康記録")
            if item.category in {"weight", "checkup"}: category_counts[item.category] += 1
            detail_parts = [f"{item.weight_kg} kg"] if item.weight_kg is not None else []
            if item.category == "checkup":
                test_labels = [name for enabled, name in [(item.physical_exam, "触診"), (item.blood_test, "血液検査"), (item.ultrasound, "エコー"), (item.chest_xray, "胸部X線")] if enabled]
                result_labels = {"normal": "異常なし", "followup": "経過観察", "recheck": "再検査", "treatment": "治療・受診が必要"}
                detail_parts.extend(test_labels)
                if item.result_summary: detail_parts.append(result_labels.get(item.result_summary, item.result_summary))
                if item.attachment_data: shared_checkup_files += f'<a class="button secondary" href="/family/dogs/{dog.id}/checkups/{item.id}/attachment" target="_blank">{item.record_date} 健診結果</a> '
            if item.meal_amount_g is not None:
                detail_parts.append(f"食事 {item.meal_amount_g:g}g")
            if item.food_name:
                detail_parts.append(f"フード：{item.food_name}")
            if item.stool_condition:
                detail_parts.append(f"うんち：{item.stool_condition}")
            if item.health_condition:
                detail_parts.append(f"健康：{item.health_condition}")
            detail = " ／ ".join(detail_parts) or (item.notes or "記録あり")
            entries.append((item.record_date, label, detail, item.notes or ""))
    shared_certificates = ""
    if shared_ids.get("vaccination"):
        for item in session.scalars(select(Vaccination).where(
            Vaccination.id.in_(shared_ids["vaccination"]), Vaccination.dog_id == dog.id
        )).all():
            dose_text = "追加接種" if item.dose_number and item.dose_number >= 4 else (f"{item.dose_number}回目" if item.dose_number else "")
            detail = item.vaccine_name + (f"（{dose_text}）" if dose_text else "")
            note_parts = [f"次回予定：{item.next_due_on}" if item.next_due_on else "", f"動物病院：{item.clinic}" if item.clinic else "", item.notes or ""]
            entries.append((item.administered_on, "ワクチン", detail, " ／ ".join(part for part in note_parts if part)))
            if item.certificate_data:
                shared_certificates += f'<a class="button secondary" href="/family/dogs/{dog.id}/vaccinations/{item.id}/certificate" target="_blank">{item.administered_on} {html.escape(item.vaccine_name)}の証明書</a> '
    if shared_ids.get("medication"):
        for item in session.scalars(select(Medication).where(
            Medication.id.in_(shared_ids["medication"]), Medication.dog_id == dog.id
        )).all():
            details = [item.medicine_name]
            if item.dosage: details.append(f"1回量：{item.dosage}")
            if item.frequency: details.append(f"頻度：{item.frequency}")
            entries.append((item.administered_on, "投薬", " ／ ".join(details), item.owner_notes or ""))
    if shared_ids.get("disease"):
        for item in session.scalars(select(DiseaseHistory).where(
            DiseaseHistory.id.in_(shared_ids["disease"]), DiseaseHistory.dog_id == dog.id
        )).all():
            status_labels = {"treatment": "治療中", "followup": "経過観察", "recovered": "完治", "chronic": "慢性"}
            detail = item.disease_name + (f"（{status_labels.get(item.status, item.status)}）" if item.status else "")
            entries.append((item.diagnosed_on or date.min, "病歴", detail, item.owner_notes or ""))
    if shared_ids.get("food"):
        for item in session.scalars(select(FoodHistory).where(
            FoodHistory.id.in_(shared_ids["food"]), FoodHistory.dog_id == dog.id
        )).all():
            details = [item.name]
            if item.amount_g is not None: details.append(f"1日量：{item.amount_g:g}g")
            if item.times_per_day: details.append(f"1日{item.times_per_day}回")
            if item.ended_on: details.append(f"終了：{item.ended_on}")
            entries.append((item.started_on, "フード", " ／ ".join(details), item.owner_notes or ""))
    for item in owner_records:
        source = "自分が登録" if item.owner_id == user.id else "過去のオーナー記録"
        detail = item.title + (f" ／ {item.value}" if item.value else "")
        entries.append((item.recorded_on, f"{owner_category_labels.get(item.category, 'その他')}（{source}）", detail, item.details or ""))
    entries.sort(key=lambda row: row[0], reverse=True)
    allowed_filters = {"", "weight", "vaccination", "checkup", "medication", "disease", "food"}
    if health_category not in allowed_filters: raise HTTPException(status_code=400, detail="カテゴリーを確認してください")
    try:
        start_filter = date.fromisoformat(date_from) if date_from else None; end_filter = date.fromisoformat(date_to) if date_to else None
    except ValueError: raise HTTPException(status_code=400, detail="検索期間を確認してください")
    if start_filter and end_filter and end_filter < start_filter: raise HTTPException(status_code=400, detail="終了日は開始日以降にしてください")
    filter_labels = {"weight": ("体重",), "vaccination": ("ワクチン",), "checkup": ("健康診断", "健診"), "medication": ("投薬",), "disease": ("病歴",), "food": ("フード",)}
    normalized_keyword = keyword.strip().lower()[:100]
    filtered_entries = []
    for entry in entries:
        item_date, kind, detail, note = entry
        if health_category and not any(label in kind for label in filter_labels[health_category]): continue
        if start_filter and item_date != date.min and item_date < start_filter: continue
        if end_filter and item_date != date.min and item_date > end_filter: continue
        if normalized_keyword and normalized_keyword not in f"{kind} {detail} {note}".lower(): continue
        filtered_entries.append(entry)
    rows = "".join(f"<tr><td>{item_date if item_date != date.min else '-'}</td><td>{html.escape(kind)}</td><td>{html.escape(detail)}</td><td>{html.escape(note)}</td></tr>" for item_date, kind, detail, note in filtered_entries)
    filter_options = '<option value="">すべて</option>' + "".join(f'<option value="{key}" {"selected" if health_category == key else ""}>{label}</option>' for key, label in [("weight", "体重"), ("vaccination", "ワクチン"), ("checkup", "健診"), ("medication", "投薬"), ("disease", "病歴"), ("food", "フード")])
    search_form = f'''<form method="get" action="/family/dogs/{dog.id}/health"><div class="grid"><div><label>カテゴリー</label><select name="health_category">{filter_options}</select></div><div><label>開始日</label><input type="date" name="date_from" value="{html.escape(date_from)}"></div><div><label>終了日</label><input type="date" name="date_to" value="{html.escape(date_to)}"></div><div><label>キーワード</label><input type="search" name="keyword" value="{html.escape(keyword[:100])}" maxlength="100" placeholder="薬剤名・病名・フード名など"></div></div><button>記録を検索</button> <a class="button secondary" href="/family/dogs/{dog.id}/health">条件をクリア</a></form><p><strong>{len(filtered_entries)}件</strong>／全{len(entries)}件を表示</p>'''
    report_query = urlencode({key: value for key, value in {"health_category": health_category, "date_from": date_from, "date_to": date_to, "keyword": keyword[:100]}.items() if value})
    report_url = f"/family/dogs/{dog.id}/health/report.pdf" + (f"?{report_query}" if report_query else "")
    csv_url = f"/family/dogs/{dog.id}/health/report.csv" + (f"?{report_query}" if report_query else "")
    owner_edit_rows = ""
    for item in owner_records:
        owner = session.get(User, item.owner_id)
        if item.owner_id == user.id:
            action = f'''<details><summary>この記録を編集</summary><form method="post" action="/family/dogs/{dog.id}/health/records/{item.id}"><div class="grid"><div><label>カテゴリー</label><select name="category">{''.join(f'<option value="{key}" {"selected" if item.category == key else ""}>{label}</option>' for key, label in owner_category_labels.items())}</select></div><div><label>記録日</label><input type="date" name="recorded_on" value="{item.recorded_on}" required></div><div><label>記録内容</label><input name="title" value="{html.escape(item.title)}" required maxlength="150"></div><div><label>数値・補足</label><input name="value" value="{html.escape(item.value or '')}" maxlength="150"></div></div><label>詳細・メモ</label><textarea name="details">{html.escape(item.details or '')}</textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="share_to_breeder" value="true" {'checked' if item.share_to_breeder else ''}> ブリーダーへ共有する</label><small>共有先：{html.escape(tenant.name if tenant else '契約犬舎')}。ブリーダーは閲覧のみで、変更・削除はできません。</small><button>変更を保存</button></form><form method="post" action="/family/dogs/{dog.id}/health/records/{item.id}/delete"><label style="font-weight:400"><input style="width:auto" type="checkbox" name="confirm_delete" value="true" required> この記録を完全に削除することを確認しました</label><button class="danger">記録を削除</button></form></details>'''
        else:
            action = '<span class="badge">変更不可</span>'
        owner_edit_rows += f'''<tr><td>{item.recorded_on}</td><td>{owner_category_labels.get(item.category, "その他")}</td><td>{html.escape(item.title)}</td><td>{html.escape(owner.name if owner else "過去のオーナー")}</td><td>{'共有中' if item.share_to_breeder else '非共有'}</td><td>{action}</td></tr>'''
    category_cards = "".join(f'''<a class="module" href="/family/dogs/{dog.id}/health/{key}"><h3>{label}管理</h3><p>記録 {category_counts.get(key, 0)}件</p></a>''' for key, label in owner_category_labels.items() if key != "other")
    weight_values: list[tuple[date, float]] = []
    if shared_ids.get("health"):
        for item in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(shared_ids["health"]), HealthRecord.dog_id == dog.id, HealthRecord.category == "weight", HealthRecord.weight_kg.is_not(None))).all():
            weight_values.append((item.record_date, item.weight_kg))
    for item in owner_records:
        if item.category == "weight":
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", item.value or "")
            if match: weight_values.append((item.recorded_on, float(match.group(1))))
    latest_weight = max(weight_values, key=lambda row: row[0]) if weight_values else None
    active_medications = 0
    if shared_ids.get("medication"):
        active_medications += session.scalar(select(func.count(Medication.id)).where(Medication.id.in_(shared_ids["medication"]), Medication.dog_id == dog.id, Medication.status == "ongoing")) or 0
    active_medications += sum(1 for item in owner_records if item.category == "medication" and item.value == "継続中")
    active_diseases = 0
    if shared_ids.get("disease"):
        active_diseases += session.scalar(select(func.count(DiseaseHistory.id)).where(DiseaseHistory.id.in_(shared_ids["disease"]), DiseaseHistory.dog_id == dog.id, DiseaseHistory.status.in_(["treatment", "followup", "chronic"]))) or 0
    active_diseases += sum(1 for item in owner_records if item.category == "disease" and item.value in {"治療中", "経過観察", "慢性"})
    active_food_names: list[str] = []
    if shared_ids.get("food"):
        active_food_names.extend(item.name for item in session.scalars(select(FoodHistory).where(FoodHistory.id.in_(shared_ids["food"]), FoodHistory.dog_id == dog.id, FoodHistory.status == "ongoing", FoodHistory.ended_on.is_(None))).all())
    active_food_names.extend(item.title for item in owner_records if item.category == "food" and item.value == "利用中")
    due_items = [("ワクチン", title, due, days, "vaccination") for due_dog, title, due, days in family_vaccine_due_items(user, session) if due_dog.id == dog.id]
    due_items += [("健診", title, due, days, "checkup") for due_dog, title, due, days in family_checkup_due_items(user, session) if due_dog.id == dog.id]
    due_items += [("投薬", title, due, days, "medication") for due_dog, title, due, days in family_medication_due_items(user, session) if due_dog.id == dog.id]
    due_items += [("再診", title, due, days, "disease") for due_dog, title, due, days in family_disease_due_items(user, session) if due_dog.id == dog.id]
    due_items.sort(key=lambda row: row[2])
    overdue_count = sum(1 for _, _, _, days, _ in due_items if days < 0); upcoming_count = sum(1 for _, _, _, days, _ in due_items if days >= 0)
    due_rows = "".join(f'''<tr><td>{label}</td><td><a href="/family/dogs/{dog.id}/health/{category}">{html.escape(title)}</a></td><td>{due}</td><td><span class="badge" style="{'background:#f4c9ca;color:#8d3037' if days < 0 else 'background:#f6e1b8;color:#755514'}">{abs(days)}日{'超過' if days < 0 else '後'}</span></td><td><form method="post" action="/family/dogs/{dog.id}/health/schedules/complete"><input type="hidden" name="category" value="{category}"><input type="hidden" name="title" value="{html.escape(title)}"><input type="hidden" name="due_on" value="{due}"><button class="success" style="margin:0;padding:7px 10px">実施済みにする</button></form></td></tr>''' for label, title, due, days, category in due_items)
    dashboard = f'''<h2>健康サマリー</h2><div class="grid"><section class="tenant"><h3>最新体重</h3><strong>{f'{latest_weight[1]:g}kg' if latest_weight else '未登録'}</strong><p>{latest_weight[0] if latest_weight else ''}</p></section><section class="tenant"><h3>継続中の投薬</h3><strong>{active_medications}件</strong></section><section class="tenant"><h3>治療・観察・慢性</h3><strong>{active_diseases}件</strong></section><section class="tenant"><h3>現在のフード</h3><strong>{len(active_food_names)}件</strong><p>{html.escape('、'.join(active_food_names) or '未登録')}</p></section></div><div class="grid"><section class="tenant"><h3>30日以内の予定</h3><strong>{upcoming_count}件</strong></section><section class="tenant"><h3>期限超過</h3><strong class="{'error' if overdue_count else ''}">{overdue_count}件</strong></section></div><h2>これからの健康予定</h2><div style="overflow-x:auto"><table><tr><th>種類</th><th>内容</th><th>予定日</th><th>状態</th><th>操作</th></tr>{due_rows or '<tr><td colspan="5">30日以内または期限超過の予定はありません。</td></tr>'}</table></div>'''
    body = f'''<a class="button secondary" href="/family/dogs/{dog.id}">{html.escape(dog.call_name)}のページへ戻る</a> <a class="button" href="/family/dogs/{dog.id}/health/calendar">健康カレンダー</a> <a class="button secondary" href="/family/dogs/{dog.id}/health/schedules/completed">実施済み履歴</a> <a class="button" href="{report_url}">表示条件でPDF出力</a> <a class="button secondary" href="{csv_url}">表示条件でCSV出力</a>
    <h1>{html.escape(dog.call_name)}のうちの子健康管理</h1><div class="tenant"><p>ブリーダーから引き継いだ記録と、オーナー様が継続して登録する記録をまとめて表示します。</p>
    <p>ブリーダーが登録した過去データは閲覧のみです。オーナー様が登録した記録は入力した本人だけが変更できます。</p></div>
    {dashboard}<h2>カテゴリー別管理</h2><div class="grid">{category_cards}</div>
    <h2>健康記録の検索</h2>{search_form}<h2>最近の健康記録</h2>
    <table><tr><th>日付</th><th>種類</th><th>内容</th><th>メモ</th></tr>{rows or '<tr><td colspan="4">条件に一致する健康記録はありません。</td></tr>'}</table>
    <h2>オーナーが入力した記録の管理</h2><div style="overflow-x:auto"><table><tr><th>記録日</th><th>カテゴリー</th><th>内容</th><th>入力者</th><th>ブリーダー共有</th><th>操作</th></tr>{owner_edit_rows or '<tr><td colspan="6">オーナーが入力した記録はまだありません。</td></tr>'}</table></div>
    {f'<h2>共有された検査結果</h2><p>{shared_checkup_files}</p>' if shared_checkup_files else ''}
    {f'<h2>共有された証明書</h2><p>{shared_certificates}</p>' if shared_certificates else ''}
    <p><small>緊急時や治療判断にはこの画面だけを使わず、犬舎または動物病院へご確認ください。</small></p>'''
    return family_layout(f"{dog.call_name}のうちの子健康管理｜FAMILY", body, user, session)


@app.get("/family/dogs/{dog_id}/health/report.pdf")
def family_dog_health_report_pdf(dog_id: int, health_category: str = "", date_from: str = "", date_to: str = "", keyword: str = "", user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned: raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, dog = owned; tenant = session.get(Tenant, ownership.tenant_id)
    shares = session.scalars(select(HealthRecordShare).where(HealthRecordShare.dog_id == dog.id, HealthRecordShare.owner_visible.is_(True))).all()
    ids: dict[str, list[int]] = {}
    for share in shares: ids.setdefault(share.record_type, []).append(share.record_id)
    rows: list[tuple[date, str, str]] = []
    if ids.get("health"):
        for item in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(ids["health"]), HealthRecord.dog_id == dog.id)).all():
            label = {"weight": "体重", "checkup": "健康診断", "treatment": "診療"}.get(item.category, "健康記録")
            detail = f"{item.weight_kg:g}kg" if item.weight_kg is not None else (item.result_summary or item.notes or "記録あり")
            rows.append((item.record_date, label, detail))
    model_specs = [
        ("vaccination", Vaccination, "administered_on", "ワクチン", lambda x: f"{x.vaccine_name}／次回 {x.next_due_on or '未設定'}"),
        ("medication", Medication, "administered_on", "投薬", lambda x: f"{x.medicine_name}／{x.dosage or '用量未登録'}／{x.frequency or '頻度未登録'}／{x.owner_notes or ''}"),
        ("disease", DiseaseHistory, "diagnosed_on", "病歴", lambda x: f"{x.disease_name}／{ {'treatment':'治療中','followup':'経過観察','recovered':'完治','chronic':'慢性'}.get(x.status, '状態未登録')}／{x.owner_notes or ''}"),
        ("food", FoodHistory, "started_on", "フード", lambda x: f"{x.name}／1日量 {f'{x.amount_g:g}g' if x.amount_g is not None else '未登録'}／{f'1日{x.times_per_day}回' if x.times_per_day else '回数未登録'}／{x.owner_notes or ''}"),
    ]
    for key, model, date_field, label, describe in model_specs:
        if ids.get(key):
            for item in session.scalars(select(model).where(model.id.in_(ids[key]), model.dog_id == dog.id)).all(): rows.append((getattr(item, date_field) or date.min, label, describe(item)))
    owner_records = session.scalars(select(OwnerHealthRecord).where(OwnerHealthRecord.tenant_id == ownership.tenant_id, OwnerHealthRecord.dog_id == dog.id)).all()
    labels = {"weight": "体重", "vaccination": "ワクチン", "checkup": "健康診断", "medication": "投薬", "disease": "病歴", "food": "フード", "other": "その他"}
    for item in owner_records: rows.append((item.recorded_on, labels.get(item.category, "その他"), f"{item.title}／{item.value or ''}／{item.details or ''}"))
    rows.sort(key=lambda row: row[0], reverse=True)
    allowed_filters = {"", "weight", "vaccination", "checkup", "medication", "disease", "food"}
    if health_category not in allowed_filters: raise HTTPException(status_code=400, detail="カテゴリーを確認してください")
    try:
        start_filter = date.fromisoformat(date_from) if date_from else None; end_filter = date.fromisoformat(date_to) if date_to else None
    except ValueError: raise HTTPException(status_code=400, detail="検索期間を確認してください")
    if start_filter and end_filter and end_filter < start_filter: raise HTTPException(status_code=400, detail="終了日は開始日以降にしてください")
    report_labels = {"weight": ("体重",), "vaccination": ("ワクチン",), "checkup": ("健康診断", "健診"), "medication": ("投薬",), "disease": ("病歴",), "food": ("フード",)}
    normalized_keyword = keyword.strip().lower()[:100]
    rows = [row for row in rows if (not health_category or row[1] in report_labels[health_category]) and (not start_filter or row[0] != date.min and row[0] >= start_filter) and (not end_filter or row[0] != date.min and row[0] <= end_filter) and (not normalized_keyword or normalized_keyword in f"{row[1]} {row[2]}".lower())]
    condition_parts = [f"カテゴリー：{ {'weight':'体重','vaccination':'ワクチン','checkup':'健診','medication':'投薬','disease':'病歴','food':'フード'}.get(health_category, 'すべて')} ", f"期間：{date_from or '指定なし'}〜{date_to or '指定なし'}"]
    if normalized_keyword: condition_parts.append(f"検索語：{keyword.strip()[:100]}")
    report_condition = "　".join(condition_parts)
    output = io.BytesIO(); pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5")); pdf = canvas.Canvas(output, pagesize=A4); width, height = A4
    def header():
        pdf.setFont("HeiseiKakuGo-W5", 16); pdf.drawString(36, height - 38, f"{dog.call_name} 健康記録レポート")
        pdf.setFont("HeiseiKakuGo-W5", 9); pdf.drawString(36, height - 56, f"犬種：{dog.breed or '未登録'}　生年月日：{dog.birth_date or '未登録'}　共有元：{tenant.name if tenant else 'ブリーダー'}")
        pdf.drawString(36, height - 71, report_condition[:85])
        pdf.drawString(36, height - 86, f"作成日：{date.today()}　※診断書ではありません。診療時の参考資料としてご利用ください。")
        pdf.line(36, height - 94, width - 36, height - 94)
    header(); y = height - 113; pdf.setFont("HeiseiKakuGo-W5", 9)
    for day, label, detail in rows:
        clean = re.sub(r"\s+", " ", detail).strip(); lines = [clean[index:index + 52] for index in range(0, len(clean), 52)] or ["－"]
        needed = 16 * max(len(lines), 1) + 8
        if y - needed < 36: pdf.showPage(); header(); y = height - 113; pdf.setFont("HeiseiKakuGo-W5", 9)
        pdf.drawString(36, y, str(day) if day != date.min else "－"); pdf.drawString(105, y, label)
        for index, line in enumerate(lines): pdf.drawString(165, y - index * 14, line)
        y -= needed
    if not rows: pdf.drawString(36, y, "共有・登録されている健康記録はありません。")
    pdf.save()
    filename = f"health-report-dog-{dog.id}.pdf"
    return Response(content=output.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"})


@app.get("/family/dogs/{dog_id}/health/report.csv")
def family_dog_health_report_csv(dog_id: int, health_category: str = "", date_from: str = "", date_to: str = "", keyword: str = "", user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned: raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, dog = owned
    allowed_filters = {"", "weight", "vaccination", "checkup", "medication", "disease", "food"}
    if health_category not in allowed_filters: raise HTTPException(status_code=400, detail="カテゴリーを確認してください")
    try:
        start_filter = date.fromisoformat(date_from) if date_from else None; end_filter = date.fromisoformat(date_to) if date_to else None
    except ValueError: raise HTTPException(status_code=400, detail="検索期間を確認してください")
    if start_filter and end_filter and end_filter < start_filter: raise HTTPException(status_code=400, detail="終了日は開始日以降にしてください")
    shares = session.scalars(select(HealthRecordShare).where(HealthRecordShare.dog_id == dog.id, HealthRecordShare.owner_visible.is_(True))).all()
    ids: dict[str, list[int]] = {}
    for share in shares: ids.setdefault(share.record_type, []).append(share.record_id)
    rows: list[tuple[date, str, str, str]] = []
    if ids.get("health"):
        for item in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(ids["health"]), HealthRecord.dog_id == dog.id)).all():
            label = {"weight": "体重", "checkup": "健康診断", "treatment": "診療"}.get(item.category, "健康記録")
            detail = f"{item.weight_kg:g}kg" if item.weight_kg is not None else (item.result_summary or "記録あり")
            rows.append((item.record_date, label, detail, item.notes or ""))
    specs = [
        ("vaccination", Vaccination, "administered_on", "ワクチン", lambda x: x.vaccine_name, lambda x: f"次回予定：{x.next_due_on or '未設定'}"),
        ("medication", Medication, "administered_on", "投薬", lambda x: x.medicine_name, lambda x: f"用量：{x.dosage or '未登録'}／頻度：{x.frequency or '未登録'}／{x.owner_notes or ''}"),
        ("disease", DiseaseHistory, "diagnosed_on", "病歴", lambda x: x.disease_name, lambda x: x.owner_notes or ""),
        ("food", FoodHistory, "started_on", "フード", lambda x: x.name, lambda x: f"1日量：{f'{x.amount_g:g}g' if x.amount_g is not None else '未登録'}／{f'1日{x.times_per_day}回' if x.times_per_day else '回数未登録'}／{x.owner_notes or ''}"),
    ]
    for key, model, date_field, label, title_of, note_of in specs:
        if ids.get(key):
            for item in session.scalars(select(model).where(model.id.in_(ids[key]), model.dog_id == dog.id)).all(): rows.append((getattr(item, date_field) or date.min, label, title_of(item), note_of(item)))
    owner_labels = {"weight": "体重", "vaccination": "ワクチン", "checkup": "健康診断", "medication": "投薬", "disease": "病歴", "food": "フード", "other": "その他"}
    for item in session.scalars(select(OwnerHealthRecord).where(OwnerHealthRecord.tenant_id == ownership.tenant_id, OwnerHealthRecord.dog_id == dog.id)).all(): rows.append((item.recorded_on, owner_labels.get(item.category, "その他"), f"{item.title}／{item.value or ''}", item.details or ""))
    filter_labels = {"weight": ("体重",), "vaccination": ("ワクチン",), "checkup": ("健康診断", "健診"), "medication": ("投薬",), "disease": ("病歴",), "food": ("フード",)}
    normalized_keyword = keyword.strip().lower()[:100]
    rows = [row for row in rows if (not health_category or row[1] in filter_labels[health_category]) and (not start_filter or row[0] != date.min and row[0] >= start_filter) and (not end_filter or row[0] != date.min and row[0] <= end_filter) and (not normalized_keyword or normalized_keyword in f"{row[1]} {row[2]} {row[3]}".lower())]
    rows.sort(key=lambda row: row[0], reverse=True)
    output = io.StringIO(newline=""); writer = csv.writer(output); writer.writerow(["愛犬", "日付", "カテゴリー", "内容", "詳細・メモ"])
    for day, label, detail, note in rows: writer.writerow([dog.call_name, day if day != date.min else "", label, detail, note])
    filename = f"health-report-dog-{dog.id}.csv"
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"})


@app.get("/family/dogs/{dog_id}/health/{category}", response_class=HTMLResponse)
def family_owner_health_category_page(dog_id: int, category: str, user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned: raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, dog = owned; tenant = session.get(Tenant, ownership.tenant_id)
    labels = {"weight": "体重", "vaccination": "ワクチン", "checkup": "健診", "medication": "投薬", "disease": "病歴", "food": "フード"}
    if category not in labels: raise HTTPException(status_code=404, detail="健康管理カテゴリーが見つかりません")
    records = session.scalars(select(OwnerHealthRecord).where(OwnerHealthRecord.tenant_id == ownership.tenant_id, OwnerHealthRecord.dog_id == dog.id, OwnerHealthRecord.category == category).order_by(OwnerHealthRecord.recorded_on.desc(), OwnerHealthRecord.id.desc())).all()
    shares = session.scalars(select(HealthRecordShare).where(HealthRecordShare.dog_id == dog.id, HealthRecordShare.owner_visible.is_(True))).all()
    ids: dict[str, list[int]] = {}
    for share in shares: ids.setdefault(share.record_type, []).append(share.record_id)
    inherited: list[tuple[date, str, str]] = []
    if category in {"weight", "checkup"} and ids.get("health"):
        for item in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(ids["health"]), HealthRecord.dog_id == dog.id, HealthRecord.category == category)).all():
            value = f"{item.weight_kg}kg" if category == "weight" and item.weight_kg is not None else (item.result_summary or "健診記録")
            inherited.append((item.record_date, value, item.notes or ""))
    if category == "vaccination" and ids.get("vaccination"):
        for item in session.scalars(select(Vaccination).where(Vaccination.id.in_(ids["vaccination"]), Vaccination.dog_id == dog.id)).all(): inherited.append((item.administered_on, item.vaccine_name, f"次回：{item.next_due_on}" if item.next_due_on else (item.notes or "")))
    if category == "medication" and ids.get("medication"):
        for item in session.scalars(select(Medication).where(Medication.id.in_(ids["medication"]), Medication.dog_id == dog.id)).all():
            status_labels = {"single": "単回", "ongoing": "継続中", "completed": "終了"}
            detail = [status_labels.get(item.status or "single", "単回")]
            if item.dosage: detail.append(f"1回量：{item.dosage}")
            if item.frequency: detail.append(f"頻度：{item.frequency}")
            if item.next_due_on: detail.append(f"次回予定：{item.next_due_on}")
            if item.owner_notes: detail.append(item.owner_notes)
            inherited.append((item.administered_on, item.medicine_name, "\n".join(detail)))
    if category == "disease" and ids.get("disease"):
        for item in session.scalars(select(DiseaseHistory).where(DiseaseHistory.id.in_(ids["disease"]), DiseaseHistory.dog_id == dog.id)).all():
            status_labels = {"treatment": "治療中", "followup": "経過観察", "recovered": "完治", "chronic": "慢性"}
            detail = [status_labels.get(item.status or "followup", "経過観察")]
            if item.symptoms: detail.append(f"症状：{item.symptoms}")
            if item.next_followup_on: detail.append(f"次回診察：{item.next_followup_on}")
            if item.owner_notes: detail.append(item.owner_notes)
            inherited.append((item.diagnosed_on or date.min, item.disease_name, "\n".join(detail)))
    if category == "food" and ids.get("food"):
        for item in session.scalars(select(FoodHistory).where(FoodHistory.id.in_(ids["food"]), FoodHistory.dog_id == dog.id)).all():
            detail = ["利用中" if (item.status or "ongoing") == "ongoing" and not item.ended_on else "終了"]
            if item.manufacturer: detail.append(f"メーカー：{item.manufacturer}")
            if item.amount_g is not None: detail.append(f"1日量：{item.amount_g:g}g")
            if item.times_per_day: detail.append(f"1日{item.times_per_day}回")
            if item.change_reason: detail.append(f"変更・終了理由：{item.change_reason}")
            if item.owner_notes: detail.append(item.owner_notes)
            inherited.append((item.started_on, item.name, "\n".join(detail)))
    inherited.sort(key=lambda row: row[0], reverse=True)
    inherited_rows = "".join(f'<tr><td>{day if day != date.min else "-"}</td><td>{html.escape(title)}</td><td style="white-space:pre-wrap">{html.escape(note or "-")}</td><td><span class="badge">ブリーダー記録・閲覧のみ</span></td></tr>' for day, title, note in inherited)
    category_summary = ""
    if category == "weight":
        weight_points: list[tuple[date, float]] = []
        for day, value, _ in inherited:
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", value or "")
            if match and day != date.min: weight_points.append((day, float(match.group(1))))
        for item in records:
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", item.value or "")
            if match: weight_points.append((item.recorded_on, float(match.group(1))))
        weight_points.sort(key=lambda point: point[0])
        if weight_points:
            latest = weight_points[-1][1]; previous = weight_points[-2][1] if len(weight_points) > 1 else None
            difference = latest - previous if previous is not None else None
            diff_text = f'{difference:+.2f}kg' if difference is not None else "比較データなし"
            values = [point[1] for point in weight_points]; low, high = min(values), max(values); span = max(high - low, 0.2)
            coords = []
            for index, (_, value) in enumerate(weight_points):
                x = 34 + (692 * index / max(len(weight_points) - 1, 1)); y = 178 - ((value - low) / span * 138)
                coords.append((x, y, value))
            polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in coords)
            circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5"><title>{value:g}kg</title></circle>' for x, y, value in coords)
            category_summary = f'''<div class="grid"><section class="tenant"><h3>最新体重</h3><strong>{latest:g}kg</strong></section><section class="tenant"><h3>前回との差</h3><strong>{diff_text}</strong></section><section class="tenant"><h3>測定回数</h3><strong>{len(weight_points)}回</strong></section><section class="tenant"><h3>記録範囲</h3><strong>{low:g}〜{high:g}kg</strong></section></div><h2>体重推移</h2><div class="owner-weight-chart"><svg viewBox="0 0 760 220" role="img" aria-label="体重の時系列推移"><line x1="34" y1="178" x2="726" y2="178"></line><polyline points="{polyline}"></polyline>{circles}<text x="34" y="207">{weight_points[0][0]}</text><text x="726" y="207" text-anchor="end">{weight_points[-1][0]}</text><text x="34" y="25">{high:g}kg</text><text x="34" y="194">{low:g}kg</text></svg></div><style>.owner-weight-chart{{overflow-x:auto;padding:12px;border:1px solid #eadfe1;border-radius:14px;background:#fffafb}}.owner-weight-chart svg{{display:block;width:100%;min-width:560px;height:auto}}.owner-weight-chart line{{stroke:#d9c9ce;stroke-width:1}}.owner-weight-chart polyline{{fill:none;stroke:#b66f7c;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}}.owner-weight-chart circle{{fill:#704454;stroke:#fff;stroke-width:2}}.owner-weight-chart text{{fill:#806b72;font-size:12px}}</style>'''
        else:
            category_summary = '<div class="tenant"><p>体重を登録すると、最新体重・前回差・時系列グラフが表示されます。</p></div>'
    elif category == "vaccination":
        breeder_vaccines = session.scalars(select(Vaccination).where(Vaccination.id.in_(ids.get("vaccination", [0])), Vaccination.dog_id == dog.id).order_by(Vaccination.administered_on.desc())).all()
        all_dates = [item.administered_on for item in breeder_vaccines] + [item.recorded_on for item in records]
        due_dates = [item.next_due_on for item in breeder_vaccines if item.next_due_on] + [item.next_due_on for item in records if item.next_due_on]
        overdue = [day for day in due_dates if day < date.today()]
        upcoming = [day for day in due_dates if date.today() <= day <= date.today() + timedelta(days=30)]
        next_date = min((day for day in due_dates if day >= date.today()), default=None)
        category_summary = f'''<div class="grid"><section class="tenant"><h3>最終接種日</h3><strong>{max(all_dates) if all_dates else "記録なし"}</strong></section><section class="tenant"><h3>次回予定</h3><strong>{next_date or "未設定"}</strong></section><section class="tenant"><h3>30日以内</h3><strong>{len(upcoming)}件</strong></section><section class="tenant"><h3>期限超過</h3><strong class="{'error' if overdue else ''}">{len(overdue)}件</strong></section></div>'''
    elif category == "checkup":
        breeder_checkups = session.scalars(select(HealthRecord).where(HealthRecord.id.in_(ids.get("health", [0])), HealthRecord.dog_id == dog.id, HealthRecord.category == "checkup").order_by(HealthRecord.record_date.desc())).all()
        all_dates = [item.record_date for item in breeder_checkups] + [item.recorded_on for item in records]
        due_dates = [item.next_due_on for item in breeder_checkups if item.next_due_on] + [item.next_due_on for item in records if item.next_due_on]
        overdue = [day for day in due_dates if day < date.today()]; upcoming = [day for day in due_dates if date.today() <= day <= date.today() + timedelta(days=30)]
        next_date = min((day for day in due_dates if day >= date.today()), default=None)
        attention = sum(1 for item in breeder_checkups if item.result_summary in {"followup", "recheck", "treatment"}) + sum(1 for item in records if item.value in {"経過観察", "再検査", "治療・受診が必要"})
        category_summary = f'''<div class="grid"><section class="tenant"><h3>最終受診日</h3><strong>{max(all_dates) if all_dates else "記録なし"}</strong></section><section class="tenant"><h3>次回予定</h3><strong>{next_date or "未設定"}</strong></section><section class="tenant"><h3>要確認の結果</h3><strong>{attention}件</strong></section><section class="tenant"><h3>期限間近・超過</h3><strong class="{'error' if overdue else ''}">{len(upcoming)}件・{len(overdue)}件</strong></section></div>'''
    elif category == "medication":
        breeder_medications = session.scalars(select(Medication).where(Medication.id.in_(ids.get("medication", [0])), Medication.dog_id == dog.id).order_by(Medication.administered_on.desc())).all()
        all_dates = [item.administered_on for item in breeder_medications] + [item.recorded_on for item in records]
        due_dates = [item.next_due_on for item in breeder_medications if item.next_due_on and item.status != "completed"] + [item.next_due_on for item in records if item.next_due_on and item.value != "終了"]
        overdue = [day for day in due_dates if day < date.today()]; upcoming = [day for day in due_dates if date.today() <= day <= date.today() + timedelta(days=30)]
        ongoing = sum(1 for item in breeder_medications if item.status == "ongoing") + sum(1 for item in records if item.value == "継続中")
        next_date = min((day for day in due_dates if day >= date.today()), default=None)
        category_summary = f'''<div class="grid"><section class="tenant"><h3>最終投薬記録</h3><strong>{max(all_dates) if all_dates else "記録なし"}</strong></section><section class="tenant"><h3>継続中</h3><strong>{ongoing}件</strong></section><section class="tenant"><h3>次回予定</h3><strong>{next_date or "未設定"}</strong></section><section class="tenant"><h3>期限間近・超過</h3><strong class="{'error' if overdue else ''}">{len(upcoming)}件・{len(overdue)}件</strong></section></div>'''
    elif category == "disease":
        breeder_diseases = session.scalars(select(DiseaseHistory).where(DiseaseHistory.id.in_(ids.get("disease", [0])), DiseaseHistory.dog_id == dog.id).order_by(DiseaseHistory.diagnosed_on.desc())).all()
        all_dates = [item.diagnosed_on for item in breeder_diseases if item.diagnosed_on] + [item.recorded_on for item in records]
        due_dates = [item.next_followup_on for item in breeder_diseases if item.next_followup_on and item.status != "recovered"] + [item.next_due_on for item in records if item.next_due_on and item.value != "完治"]
        overdue = [day for day in due_dates if day < date.today()]; upcoming = [day for day in due_dates if date.today() <= day <= date.today() + timedelta(days=30)]
        active_count = sum(1 for item in breeder_diseases if item.status in {"treatment", "followup", "chronic"}) + sum(1 for item in records if item.value in {"治療中", "経過観察", "慢性"})
        recurrence_count = sum(1 for item in breeder_diseases if item.recurrence) + sum(1 for item in records if "再発：はい" in (item.details or ""))
        category_summary = f'''<div class="grid"><section class="tenant"><h3>最終診断・記録日</h3><strong>{max(all_dates) if all_dates else "記録なし"}</strong></section><section class="tenant"><h3>治療・観察・慢性</h3><strong>{active_count}件</strong></section><section class="tenant"><h3>再発記録</h3><strong>{recurrence_count}件</strong></section><section class="tenant"><h3>期限間近・超過</h3><strong class="{'error' if overdue else ''}">{len(upcoming)}件・{len(overdue)}件</strong></section></div>'''
    elif category == "food":
        breeder_foods = session.scalars(select(FoodHistory).where(FoodHistory.id.in_(ids.get("food", [0])), FoodHistory.dog_id == dog.id).order_by(FoodHistory.started_on.desc())).all()
        breeder_active = [item for item in breeder_foods if (item.status or "ongoing") == "ongoing" and not item.ended_on]
        owner_active = [item for item in records if item.value == "利用中"]
        active_names = [item.name for item in breeder_active] + [item.title for item in owner_active]
        latest_dates = [item.started_on for item in breeder_foods] + [item.recorded_on for item in records]
        completed_count = sum(1 for item in breeder_foods if item.ended_on or item.status == "completed") + sum(1 for item in records if item.value == "終了")
        category_summary = f'''<div class="grid"><section class="tenant"><h3>現在利用中</h3><strong>{len(active_names)}件</strong><p>{html.escape("、".join(active_names) or "登録なし")}</p></section><section class="tenant"><h3>最新変更日</h3><strong>{max(latest_dates) if latest_dates else "記録なし"}</strong></section><section class="tenant"><h3>終了済み</h3><strong>{completed_count}件</strong></section><section class="tenant"><h3>利用履歴</h3><strong>{len(breeder_foods) + len(records)}件</strong></section></div>'''
    owner_rows = ""
    for item in records:
        owner = session.get(User, item.owner_id)
        schedule = ""
        if category in {"vaccination", "checkup", "medication", "disease"} and item.next_due_on:
            schedule = '<span class="badge" style="background:#f4c9ca;color:#8d3037">期限超過</span>' if item.next_due_on < date.today() else ('<span class="badge" style="background:#f6e1b8;color:#755514">期限間近</span>' if item.next_due_on <= date.today() + timedelta(days=30) else f'<span class="badge">次回 {item.next_due_on}</span>')
        certificate = f'<a class="button secondary" href="/family/dogs/{dog.id}/health/records/{item.id}/attachment" target="_blank">添付ファイルを見る</a>' if item.attachment_data else ""
        if item.owner_id == user.id:
            action = f'''<details><summary>編集・誤入力修正</summary><form method="post" action="/family/dogs/{dog.id}/health/records/{item.id}"><input type="hidden" name="category" value="{category}"><input type="hidden" name="return_to" value="{category}"><label>記録日</label><input type="date" name="recorded_on" value="{item.recorded_on}" required><label>記録内容</label><input name="title" value="{html.escape(item.title)}" required maxlength="150"><label>数値・補足</label><input name="value" value="{html.escape(item.value or '')}" maxlength="150"><label>詳細・メモ</label><textarea name="details">{html.escape(item.details or '')}</textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="share_to_breeder" value="true" {'checked' if item.share_to_breeder else ''}> ブリーダーへ共有する</label><button>変更を保存</button></form><form method="post" action="/family/dogs/{dog.id}/health/records/{item.id}/delete"><input type="hidden" name="return_to" value="{category}"><label style="font-weight:400"><input style="width:auto" type="checkbox" name="confirm_delete" value="true" required> この記録を完全に削除することを確認しました</label><button class="danger">記録を削除</button></form></details>'''
        else: action = '<span class="badge">過去オーナー記録・変更不可</span>'
        owner_rows += f'''<tr><td>{item.recorded_on}<br>{schedule}</td><td>{html.escape(item.title)}{f" ／ {html.escape(item.value)}" if item.value else ""}</td><td style="white-space:pre-wrap">{html.escape(item.details or "-")}<br>{certificate}</td><td>{html.escape(owner.name if owner else "過去のオーナー")}<br>{'ブリーダー共有中' if item.share_to_breeder else 'ブリーダー非共有'}<br>{action}</td></tr>'''
    forms = {
        "weight": '<div class="grid"><div><label>測定日</label><input type="date" name="recorded_on" value="' + str(date.today()) + '" required></div><div><label>体重（kg）</label><input type="number" step="0.01" min="0.01" name="weight_kg" required></div><div><label>健康状態</label><select name="condition"><option>良好</option><option>少し悪い</option><option>悪い</option></select></div></div>',
        "vaccination": '<div class="grid"><div><label>接種日</label><input type="date" name="recorded_on" value="' + str(date.today()) + '" required></div><div><label>ワクチン区分</label><select name="vaccine_type"><option value="rabies">狂犬病</option><option value="mixed">混合ワクチン</option><option value="other">その他</option></select></div><div><label>ワクチン名</label><input name="vaccine_name" required></div><div><label>子犬期の接種順（任意）</label><select name="dose"><option value="">成犬・入力不要</option><option>1回目</option><option>2回目</option><option>3回目</option><option>追加接種</option></select></div><div><label>次回予定日</label><input type="date" name="next_due_on"></div><div><label>動物病院</label><input name="clinic"></div></div><label>接種証明書・写真（PDF・JPG・PNG／8MBまで）</label><input type="file" name="attachment_file" accept="application/pdf,image/jpeg,image/png">',
        "checkup": '<div class="grid"><div><label>受診日</label><input type="date" name="recorded_on" value="' + str(date.today()) + '" required></div><div><label>結果</label><select name="result"><option>異常なし</option><option>経過観察</option><option>再検査</option><option>治療・受診が必要</option></select></div><div><label>次回予定日</label><input type="date" name="next_due_on"></div><div><label>動物病院</label><input name="clinic"></div></div><label>健診項目</label><div class="grid"><label><input style="width:auto" type="checkbox" name="physical_exam"> 触診</label><label><input style="width:auto" type="checkbox" name="blood_test"> 血液検査</label><label><input style="width:auto" type="checkbox" name="ultrasound"> エコー</label><label><input style="width:auto" type="checkbox" name="chest_xray"> 胸部X線</label></div><label>検査結果（PDF・JPG・PNG／8MBまで）</label><input type="file" name="attachment_file" accept="application/pdf,image/jpeg,image/png">',
        "medication": '<div class="grid"><div><label>記録日</label><input type="date" name="recorded_on" value="' + str(date.today()) + '" required></div><div><label>薬剤名</label><input name="medicine_name" required></div><div><label>区分</label><select name="medication_type"><option value="treatment">治療薬</option><option value="prevention">予防薬</option><option value="supplement">サプリメント</option><option value="other">その他</option></select></div><div><label>目的・対象症状</label><input name="purpose"></div><div><label>1回量</label><input name="dosage" placeholder="例：1錠、2.5ml"></div><div><label>投薬頻度</label><input name="frequency" placeholder="例：1日2回、毎月1回"></div><div><label>開始日</label><input type="date" name="started_on"></div><div><label>終了日</label><input type="date" name="ended_on"></div><div><label>状態</label><select name="record_status"><option>単回</option><option>継続中</option><option>終了</option></select></div><div><label>次回予定日</label><input type="date" name="next_due_on"></div><div><label>動物病院</label><input name="clinic"></div></div>',
        "disease": '<div class="grid"><div><label>診断日</label><input type="date" name="recorded_on" value="' + str(date.today()) + '" required></div><div><label>疾患名</label><input name="disease_name" required></div><div><label>分類</label><select name="disease_category"><option value="digestive">消化器</option><option value="respiratory">呼吸器</option><option value="skin">皮膚</option><option value="orthopedic">整形・関節</option><option value="cardiac">循環器</option><option value="urinary">泌尿器</option><option value="reproductive">生殖器</option><option value="infectious">感染症</option><option value="other">その他</option></select></div><div><label>状態</label><select name="record_status"><option>治療中</option><option>経過観察</option><option>完治</option><option>慢性</option></select></div><div><label>治療開始日</label><input type="date" name="treatment_started_on"></div><div><label>治療終了日</label><input type="date" name="treatment_ended_on"></div><div><label>動物病院</label><input name="clinic"></div><div><label>担当獣医師</label><input name="veterinarian"></div><div><label>次回診察日</label><input type="date" name="next_due_on"></div></div><label style="font-weight:400"><input style="width:auto" type="checkbox" name="recurrence" value="true"> 同じ疾患の再発として記録する</label><label>症状</label><textarea name="symptoms"></textarea>',
        "food": '<div class="grid"><div><label>利用開始日</label><input type="date" name="recorded_on" value="' + str(date.today()) + '" required></div><div><label>フード名</label><input name="food_name" required></div><div><label>メーカー</label><input name="manufacturer"></div><div><label>種類</label><select name="food_type"><option value="dry">ドライ</option><option value="wet">ウェット</option><option value="raw">生食</option><option value="prescription">療法食</option><option value="supplement">サプリメント</option><option value="other">その他</option></select></div><div><label>1日量（g）</label><input type="number" step="0.1" min="0.1" name="amount_g"></div><div><label>1日の給与回数</label><input type="number" min="1" max="10" name="times_per_day"></div><div><label>状態</label><select name="record_status"><option>利用中</option><option>終了</option></select></div><div><label>利用終了日</label><input type="date" name="ended_on"></div><div><label>変更・終了理由</label><input name="change_reason"></div></div>'
    }
    body = f'''<a class="button secondary" href="/family/dogs/{dog.id}/health">うちの子健康管理へ戻る</a><h1>{html.escape(dog.call_name)}の{labels[category]}管理</h1><p>対象犬は{html.escape(dog.call_name)}に固定されています。</p>{category_summary}
    <h2>{labels[category]}記録を追加</h2><form method="post" action="/family/dogs/{dog.id}/health/{category}/records" enctype="multipart/form-data">{forms[category]}<label>詳細・メモ</label><textarea name="details"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="share_to_breeder" value="true"> ブリーダーへ共有する</label><small>共有先：{html.escape(tenant.name if tenant else '契約犬舎')}。ブリーダーは閲覧のみで変更・削除できません。</small><button>{labels[category]}記録を追加</button></form>
    <h2>ブリーダーから引き継いだ記録</h2><div style="overflow-x:auto"><table><tr><th>日付</th><th>内容</th><th>メモ</th><th>権限</th></tr>{inherited_rows or '<tr><td colspan="4">共有された記録はまだありません。</td></tr>'}</table></div>
    <h2>オーナーが継続入力した記録</h2><div style="overflow-x:auto"><table><tr><th>日付</th><th>内容</th><th>詳細</th><th>入力者・操作</th></tr>{owner_rows or '<tr><td colspan="4">オーナー記録はまだありません。</td></tr>'}</table></div>'''
    return family_layout(f"{dog.call_name}の{labels[category]}管理｜FAMILY", body, user, session)


@app.post("/family/dogs/{dog_id}/health/{category}/records")
async def family_owner_health_category_create(dog_id: int, category: str, recorded_on: str = Form(...), weight_kg: str = Form(""), condition: str = Form(""), vaccine_type: str = Form("other"), vaccine_name: str = Form(""), dose: str = Form(""), next_due_on: str = Form(""), clinic: str = Form(""), result: str = Form(""), physical_exam: bool = Form(False), blood_test: bool = Form(False), ultrasound: bool = Form(False), chest_xray: bool = Form(False), medicine_name: str = Form(""), medication_type: str = Form("treatment"), purpose: str = Form(""), dosage: str = Form(""), frequency: str = Form(""), started_on: str = Form(""), record_status: str = Form(""), disease_name: str = Form(""), disease_category: str = Form("other"), symptoms: str = Form(""), treatment_started_on: str = Form(""), treatment_ended_on: str = Form(""), veterinarian: str = Form(""), recurrence: bool = Form(False), food_name: str = Form(""), manufacturer: str = Form(""), food_type: str = Form("dry"), change_reason: str = Form(""), amount_g: str = Form(""), times_per_day: str = Form(""), ended_on: str = Form(""), details: str = Form(""), share_to_breeder: bool = Form(False), attachment_file: UploadFile | None = File(None), user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned: raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, dog = owned
    if category not in {"weight", "vaccination", "checkup", "medication", "disease", "food"}: raise HTTPException(status_code=404, detail="健康管理カテゴリーが見つかりません")
    extras = []
    if category == "weight":
        try: weight = float(weight_kg)
        except ValueError: raise HTTPException(status_code=400, detail="体重を確認してください")
        if weight <= 0: raise HTTPException(status_code=400, detail="体重を確認してください")
        title, value = "体重測定", f"{weight:g}kg"; extras = [f"健康状態：{condition}" if condition else ""]
    elif category == "vaccination":
        if vaccine_type not in {"rabies", "mixed", "other"} or not vaccine_name.strip(): raise HTTPException(status_code=400, detail="ワクチン情報を確認してください")
        type_label = {"rabies": "狂犬病", "mixed": "混合ワクチン", "other": "その他"}[vaccine_type]
        title, value = vaccine_name.strip(), type_label + (f"・{dose.strip()}" if dose.strip() else ""); extras = [f"次回予定：{next_due_on}" if next_due_on else "", f"動物病院：{clinic.strip()}" if clinic.strip() else ""]
    elif category == "checkup":
        tests = [name for enabled, name in [(physical_exam, "触診"), (blood_test, "血液検査"), (ultrasound, "エコー"), (chest_xray, "胸部X線")] if enabled]
        if not tests: raise HTTPException(status_code=400, detail="健診項目を1つ以上選択してください")
        title, value = "健康診断", result.strip(); extras = ["検査：" + "・".join(tests), f"次回予定：{next_due_on}" if next_due_on else "", f"動物病院：{clinic.strip()}" if clinic.strip() else ""]
    elif category == "medication":
        if not medicine_name.strip() or medication_type not in {"treatment", "prevention", "supplement", "other"} or record_status not in {"単回", "継続中", "終了"}: raise HTTPException(status_code=400, detail="投薬情報を確認してください")
        try:
            start_day = date.fromisoformat(started_on) if started_on else None; end_day = date.fromisoformat(ended_on) if ended_on else None
        except ValueError: raise HTTPException(status_code=400, detail="投薬期間を確認してください")
        if start_day and end_day and end_day < start_day: raise HTTPException(status_code=400, detail="終了日は開始日以降にしてください")
        type_label = {"treatment": "治療薬", "prevention": "予防薬", "supplement": "サプリメント", "other": "その他"}[medication_type]
        title, value = medicine_name.strip(), record_status.strip(); extras = [f"区分：{type_label}", f"目的・対象症状：{purpose.strip()}" if purpose.strip() else "", f"1回量：{dosage.strip()}" if dosage.strip() else "", f"頻度：{frequency.strip()}" if frequency.strip() else "", f"開始日：{start_day}" if start_day else "", f"終了日：{end_day}" if end_day else "", f"次回予定：{next_due_on}" if next_due_on else "", f"動物病院：{clinic.strip()}" if clinic.strip() else ""]
    elif category == "disease":
        valid_categories = {"digestive": "消化器", "respiratory": "呼吸器", "skin": "皮膚", "orthopedic": "整形・関節", "cardiac": "循環器", "urinary": "泌尿器", "reproductive": "生殖器", "infectious": "感染症", "other": "その他"}
        if not disease_name.strip() or disease_category not in valid_categories or record_status not in {"治療中", "経過観察", "完治", "慢性"}: raise HTTPException(status_code=400, detail="病歴情報を確認してください")
        try:
            treatment_start = date.fromisoformat(treatment_started_on) if treatment_started_on else None; treatment_end = date.fromisoformat(treatment_ended_on) if treatment_ended_on else None
        except ValueError: raise HTTPException(status_code=400, detail="治療期間を確認してください")
        if treatment_start and treatment_end and treatment_end < treatment_start: raise HTTPException(status_code=400, detail="治療終了日は開始日以降にしてください")
        title, value = disease_name.strip(), record_status.strip(); extras = [f"分類：{valid_categories[disease_category]}", f"症状：{symptoms.strip()}" if symptoms.strip() else "", f"治療開始日：{treatment_start}" if treatment_start else "", f"治療終了日：{treatment_end}" if treatment_end else "", f"再発：{'はい' if recurrence else 'いいえ'}", f"動物病院：{clinic.strip()}" if clinic.strip() else "", f"担当獣医師：{veterinarian.strip()}" if veterinarian.strip() else "", f"次回診察：{next_due_on}" if next_due_on else ""]
    else:
        if not food_name.strip() or food_type not in {"dry", "wet", "raw", "prescription", "supplement", "other"} or record_status not in {"利用中", "終了"}: raise HTTPException(status_code=400, detail="フード情報を確認してください")
        try: amount = float(amount_g) if amount_g else None; times = int(times_per_day) if times_per_day else None
        except ValueError: raise HTTPException(status_code=400, detail="給与量・回数を確認してください")
        if (amount is not None and amount <= 0) or (times is not None and not 1 <= times <= 10): raise HTTPException(status_code=400, detail="給与量・回数を確認してください")
        try: end_food = date.fromisoformat(ended_on) if ended_on else None
        except ValueError: raise HTTPException(status_code=400, detail="利用終了日を確認してください")
        if end_food and end_food < date.fromisoformat(recorded_on): raise HTTPException(status_code=400, detail="利用終了日は開始日以降にしてください")
        if record_status == "終了" and not end_food: raise HTTPException(status_code=400, detail="終了済みの場合は利用終了日を入力してください")
        type_label = {"dry": "ドライ", "wet": "ウェット", "raw": "生食", "prescription": "療法食", "supplement": "サプリメント", "other": "その他"}[food_type]
        title, value = food_name.strip(), record_status.strip(); extras = [f"メーカー：{manufacturer.strip()}" if manufacturer.strip() else "", f"種類：{type_label}", f"1日量：{amount:g}g" if amount is not None else "", f"1日{times}回" if times else "", f"終了日：{end_food}" if end_food else "", f"変更・終了理由：{change_reason.strip()}" if change_reason.strip() else ""]
    due = None
    if next_due_on:
        try: due = date.fromisoformat(next_due_on)
        except ValueError: raise HTTPException(status_code=400, detail="次回予定日を確認してください")
    attachment_name = attachment_type = None; attachment_data = None
    if category in {"vaccination", "checkup"} and attachment_file and attachment_file.filename:
        allowed = {"application/pdf", "image/jpeg", "image/png"}
        attachment_data = await attachment_file.read(8 * 1024 * 1024 + 1)
        if attachment_file.content_type not in allowed or not attachment_data or len(attachment_data) > 8 * 1024 * 1024: raise HTTPException(status_code=400, detail="添付ファイルはPDF・JPG・PNGの8MB以下にしてください")
        attachment_name = Path(attachment_file.filename).name[:255]; attachment_type = attachment_file.content_type
    combined = "\n".join(part for part in extras + [details.strip()] if part)
    day = validate_owner_health_record(category, recorded_on, title, value, combined)
    session.add(OwnerHealthRecord(tenant_id=ownership.tenant_id, dog_id=dog.id, owner_id=user.id, category=category, recorded_on=day, title=title, value=value or None, details=combined or None, next_due_on=due, attachment_filename=attachment_name, attachment_content_type=attachment_type, attachment_data=attachment_data, share_to_breeder=share_to_breeder)); session.commit()
    return RedirectResponse(f"/family/dogs/{dog.id}/health/{category}", status_code=303)


def validate_owner_health_record(category: str, recorded_on: str, title: str, value: str, details: str):
    if category not in {"weight", "vaccination", "checkup", "medication", "disease", "food", "other"}:
        raise HTTPException(status_code=400, detail="健康記録のカテゴリーを確認してください")
    if not title.strip() or len(title.strip()) > 150 or len(value.strip()) > 150 or len(details) > 3000:
        raise HTTPException(status_code=400, detail="健康記録の入力内容を確認してください")
    try:
        day = date.fromisoformat(recorded_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="記録日を確認してください")
    return day


@app.post("/family/dogs/{dog_id}/health/records")
def family_owner_health_create(dog_id: int, category: str = Form(...), recorded_on: str = Form(...), title: str = Form(...), value: str = Form(""), details: str = Form(""), share_to_breeder: bool = Form(False), user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned: raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, dog = owned
    day = validate_owner_health_record(category, recorded_on, title, value, details)
    session.add(OwnerHealthRecord(tenant_id=ownership.tenant_id, dog_id=dog.id, owner_id=user.id, category=category, recorded_on=day, title=title.strip(), value=value.strip() or None, details=details.strip() or None, share_to_breeder=share_to_breeder))
    session.commit()
    return RedirectResponse(f"/family/dogs/{dog.id}/health", status_code=303)


@app.post("/family/dogs/{dog_id}/health/records/{record_id}")
def family_owner_health_update(dog_id: int, record_id: int, category: str = Form(...), recorded_on: str = Form(...), title: str = Form(...), value: str = Form(""), details: str = Form(""), share_to_breeder: bool = Form(False), return_to: str = Form("health"), user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session): raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    item = session.scalar(select(OwnerHealthRecord).where(OwnerHealthRecord.id == record_id, OwnerHealthRecord.dog_id == dog_id, OwnerHealthRecord.owner_id == user.id))
    if not item: raise HTTPException(status_code=403, detail="この健康記録を変更する権限がありません")
    day = validate_owner_health_record(category, recorded_on, title, value, details)
    item.category = category; item.recorded_on = day; item.title = title.strip(); item.value = value.strip() or None; item.details = details.strip() or None; item.share_to_breeder = share_to_breeder; item.updated_at = datetime.now(timezone.utc)
    session.commit()
    destination = f"/family/dogs/{dog_id}/health/{return_to}" if return_to in {"weight", "vaccination", "checkup", "medication", "disease", "food"} else f"/family/dogs/{dog_id}/health"
    return RedirectResponse(destination, status_code=303)


@app.post("/family/dogs/{dog_id}/health/records/{record_id}/delete")
def family_owner_health_delete(dog_id: int, record_id: int, confirm_delete: bool = Form(False), return_to: str = Form("health"), user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session): raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    item = session.scalar(select(OwnerHealthRecord).where(OwnerHealthRecord.id == record_id, OwnerHealthRecord.dog_id == dog_id, OwnerHealthRecord.owner_id == user.id))
    if not item: raise HTTPException(status_code=403, detail="この健康記録を削除する権限がありません")
    if not confirm_delete: raise HTTPException(status_code=400, detail="削除の確認が必要です")
    session.delete(item); session.commit()
    destination = f"/family/dogs/{dog_id}/health/{return_to}" if return_to in {"weight", "vaccination", "checkup", "medication", "disease", "food"} else f"/family/dogs/{dog_id}/health"
    return RedirectResponse(destination, status_code=303)


@app.get("/family/dogs/{dog_id}/health/records/{record_id}/attachment")
def family_owner_health_attachment(dog_id: int, record_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned: raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    ownership, _ = owned
    item = session.scalar(select(OwnerHealthRecord).where(OwnerHealthRecord.id == record_id, OwnerHealthRecord.dog_id == dog_id, OwnerHealthRecord.tenant_id == ownership.tenant_id))
    if not item or not item.attachment_data: raise HTTPException(status_code=404, detail="証明書が見つかりません")
    return Response(content=item.attachment_data, media_type=item.attachment_content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store", "Content-Disposition": f"inline; filename*=UTF-8''{quote(item.attachment_filename or 'document')}"})


@app.get("/family/dogs/{dog_id}/vaccinations/{vaccination_id}/certificate")
def family_vaccination_certificate(dog_id: int, vaccination_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    item = session.scalar(select(Vaccination).where(Vaccination.id == vaccination_id, Vaccination.dog_id == dog_id))
    share = health_share_for(session, "vaccination", vaccination_id)
    if not item or not item.certificate_data or not share or not share.owner_visible or share.dog_id != dog_id:
        raise HTTPException(status_code=404, detail="共有された証明書が見つかりません")
    return Response(content=item.certificate_data, media_type=item.certificate_content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store"})


@app.get("/family/dogs/{dog_id}/checkups/{record_id}/attachment")
def family_checkup_attachment(dog_id: int, record_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session): raise HTTPException(status_code=404, detail="閲覧できる愛犬が見つかりません")
    item = session.scalar(select(HealthRecord).where(HealthRecord.id == record_id, HealthRecord.dog_id == dog_id, HealthRecord.category == "checkup"))
    share = health_share_for(session, "health", record_id)
    if not item or not item.attachment_data or not share or not share.owner_visible or share.dog_id != dog_id: raise HTTPException(status_code=404, detail="共有された検査結果が見つかりません")
    return Response(content=item.attachment_data, media_type=item.attachment_content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store"})


@app.get("/family/growth/add", response_class=HTMLResponse)
def family_growth_add_select(user: User = Depends(require_user), session: Session = Depends(db)):
    records = session.execute(
        select(DogOwnership, Dog).join(Dog, Dog.id == DogOwnership.dog_id)
        .where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True), Dog.active.is_(True))
        .order_by(Dog.call_name)
    ).all()
    if len(records) == 1:
        return RedirectResponse(f"/family/growth/add/{records[0][1].id}", status_code=303)
    if not records:
        body = '<h1>成長記録を追加</h1><div class="tenant"><p>投稿できる愛犬がまだ連携されていません。</p><p>犬舎へ登録メールアドレスをお知らせください。</p></div><a class="button secondary" href="/family/timeline">タイムラインへ戻る</a>'
        return family_layout("成長記録を追加｜FAMILY", body, user, session)
    cards = "".join(f'''<a class="module" href="/family/growth/add/{dog.id}"><h3>{html.escape(dog.call_name)}</h3>
        <p>{html.escape(dog.registered_name or "血統書名未登録")}</p><p>この愛犬の成長記録を追加 →</p></a>''' for _, dog in records)
    body = f'''<a class="button secondary" href="/family/timeline">タイムラインへ戻る</a><h1>成長記録を追加</h1>
    <p>投稿する愛犬を選んでください。</p><div class="grid">{cards}</div>'''
    return family_layout("成長記録を追加｜FAMILY", body, user, session)


@app.get("/family/growth/add/{dog_id}", response_class=HTMLResponse)
def family_growth_add_page(dog_id: int, user: User = Depends(require_user), session: Session = Depends(db)):
    record = family_owned_dog(dog_id, user, session)
    if not record:
        raise HTTPException(status_code=404, detail="投稿できる愛犬が見つかりません")
    dog = record[1]
    body = f'''<a class="button secondary" href="/family/timeline">タイムラインへ戻る</a><h1>成長記録を追加</h1>
    <div class="tenant"><p><strong>{html.escape(dog.call_name)}</strong>の成長記録を投稿します。</p></div>
    <form method="post" action="/family/dogs/{dog.id}/album" enctype="multipart/form-data">
    <input type="hidden" name="return_to" value="timeline">
    <label>写真（1投稿につき最大10枚／各8MBまで）</label><input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple required>
    <label>撮影日</label><input type="date" name="taken_on">
    <label>コメント（300文字まで）</label><textarea name="caption" maxlength="300" placeholder="初めてのお散歩、1歳のお誕生日など"></textarea>
    <label>公開範囲</label><select name="visibility"><option value="private">非公開（自分だけ）</option><option value="relatives">親戚犬のオーナーまで</option><option value="family">FAMILY全体</option></select>
    <button class="success">成長記録を投稿</button></form>
    <p><small>このページではプロフィール写真や紹介文は変更されません。</small></p>'''
    return family_layout(f"{dog.call_name}の成長記録を追加｜FAMILY", body, user, session)


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
async def family_dog_album_add(dog_id: int, photos: list[UploadFile] = File(...), taken_on: str = Form(""), caption: str = Form(""), visibility: str = Form("private"), return_to: str = Form(""), user: User = Depends(require_user), session: Session = Depends(db)):
    owned = family_owned_dog(dog_id, user, session)
    if not owned:
        raise HTTPException(status_code=403, detail="この犬のアルバムへ追加できません")
    if family_action_disabled(user.id, owned[1].tenant_id, "posting", session):
        raise HTTPException(status_code=403, detail="犬舎により投稿機能が停止されています")
    caption = caption.strip()
    if len(caption) > 300 or visibility not in {"private", "relatives", "family"}:
        raise HTTPException(status_code=400, detail="コメントまたは公開範囲を確認してください")
    try:
        taken_date = date.fromisoformat(taken_on) if taken_on else None
    except ValueError:
        raise HTTPException(status_code=400, detail="撮影日を確認してください")
    photos = [photo for photo in photos if photo.filename]
    if not photos or len(photos) > 10:
        raise HTTPException(status_code=400, detail="写真は1枚から10枚まで選択してください")
    group = secrets.token_hex(16)
    for position, photo in enumerate(photos):
        content = await photo.read(8 * 1024 * 1024 + 1)
        if not content or len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="写真は1枚8MB以下にしてください")
        try:
            with Image.open(io.BytesIO(content)) as source:
                if source.width * source.height > 25_000_000:
                    raise ValueError("image dimensions are too large")
                image = ImageOps.exif_transpose(source); image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
                if image.mode in {"RGBA", "LA"}:
                    background = Image.new("RGB", image.size, "white"); background.paste(image, mask=image.getchannel("A")); image = background
                else:
                    image = image.convert("RGB")
                output = io.BytesIO(); image.save(output, format="JPEG", quality=88, optimize=True)
        except Exception:
            raise HTTPException(status_code=400, detail="JPG・PNG・WebP形式の写真を選択してください")
        session.add(FamilyDogAlbumItem(dog_id=dog_id, uploaded_by_id=user.id, photo_data=output.getvalue(), photo_content_type="image/jpeg", taken_on=taken_date, caption=caption or None, visibility=visibility, post_group=group, photo_order=position))
    session.commit()
    destination = "/family/timeline" if return_to == "timeline" else f"/family/dogs/{dog_id}"
    return RedirectResponse(destination, status_code=303)


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
    targets = session.scalars(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.post_group == item.post_group)).all() if item.post_group else [item]
    for target in targets:
        session.delete(target)
    session.commit()
    return RedirectResponse(f"/family/dogs/{dog_id}", status_code=303)


@app.post("/family/dogs/{dog_id}/album/{item_id}/edit")
def family_dog_album_edit(dog_id: int, item_id: int, taken_on: str = Form(""), caption: str = Form(""), visibility: str = Form("private"), user: User = Depends(require_user), session: Session = Depends(db)):
    if not family_owned_dog(dog_id, user, session):
        raise HTTPException(status_code=404)
    item = session.scalar(select(FamilyDogAlbumItem).where(
        FamilyDogAlbumItem.id == item_id, FamilyDogAlbumItem.dog_id == dog_id, FamilyDogAlbumItem.uploaded_by_id == user.id,
    ))
    caption = caption.strip()
    if not item or len(caption) > 300 or visibility not in {"private", "relatives", "family"}:
        raise HTTPException(status_code=400, detail="編集内容を確認してください")
    try:
        parsed_taken_on = date.fromisoformat(taken_on) if taken_on else None
    except ValueError:
        raise HTTPException(status_code=400, detail="撮影日を確認してください")
    targets = session.scalars(select(FamilyDogAlbumItem).where(FamilyDogAlbumItem.post_group == item.post_group)).all() if item.post_group else [item]
    for target in targets:
        target.taken_on, target.caption, target.visibility = parsed_taken_on, caption or None, visibility
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
    <label>登録メールアドレス</label><input type="email" value="{html.escape(user.email)}" readonly aria-readonly="true" style="background:#f5f0f1;color:#665159">
    <p><small>このメールアドレスはログインと愛犬の連携に使用されています。FAMILYの他のメンバーには公開されません。変更が必要な場合は犬舎へご連絡ください。</small></p>
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
