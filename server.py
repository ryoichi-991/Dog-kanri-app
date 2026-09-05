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
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from cryptography.fernet import Fernet, InvalidToken

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://app:app@db:5432/Dog_kanri_app")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "7"))
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
passwords = CryptContext(schemes=["argon2"], deprecated="auto")
MODULES = {
    "todo": ("Todoãƒªã‚¹ãƒˆ", "æ—¥ã€…ã®ä½œæ¥­ã€æœŸé™ã€å®Œäº†çŠ¶æ³"),
    "calendar": ("ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼", "ç¹æ®–ãƒ»å¥åº·ãƒ»ç”³è«‹ãƒ»è²©å£²ã®äºˆå®š"),
    "legal": ("æ³•ä»¤ãƒ»è¡Œæ”¿æ›¸é¡", "å®šæœŸå ±å‘Šã€é–‹å§‹ãƒ»æ›´æ–°ãƒ»å¤‰æ›´ç”³è«‹ã€æ³•å®šå¸³ç°¿"),
    "dogs": ("çŠ¬ãƒ»è¡€çµ±æ›¸ç®¡ç†", "å€‹ä½“ã€ãƒã‚¤ã‚¯ãƒ­ãƒãƒƒãƒ—ã€è¡€çµ±æ›¸ã€è¦ªå­é–¢ä¿‚"),
    "breeding": ("äº¤é…ãƒ»è¿‘è¦ªäº¤é…ç‡", "äº¤é…è¨ˆç”»ã€ä¿‚æ•°è¨ˆç®—ã€çµ„ã¿åˆã‚ã›ææ¡ˆ"),
    "births": ("å‡ºç”£ãƒ»ãƒ’ãƒ¼ãƒˆå‘¨æœŸ", "ãƒ’ãƒ¼ãƒˆäºˆæ¸¬ã€äº¤é…æ—¥ã€å‡ºç”£ã€ä»”çŠ¬"),
    "health": ("å¥åº·ãƒ»ãƒ¯ã‚¯ãƒãƒ³", "ä½“é‡ã€è¨ºç™‚ã€äºˆé˜²æ¥ç¨®ã€æ¬¡å›äºˆå®š"),
    "genetics": ("éºä¼å­æ¤œæŸ»", "éºä¼ç—…æ¤œæŸ»çµæœã¨äº¤é…ãƒªã‚¹ã‚¯"),
    "sales": ("ä»”çŠ¬è²©å£²ç®¡ç†", "å•ã„åˆã‚ã›ã€å¥‘ç´„ã€èª¬æ˜ã€å¼•æ¸¡ã—"),
    "finance": ("åæ”¯ãƒ»çµŒè²»å°å¸³", "å…¥é‡‘ã€çµŒè²»ã€æœˆæ¬¡åæ”¯ã€åŸä¾¡ã®è¨˜éŒ²"),
    "finance/reports": ("çµŒå–¶åç›Šãƒ€ãƒƒã‚·ãƒ¥ãƒœãƒ¼ãƒ‰", "æœˆåˆ¥åæ”¯ã€çµŒè²»æ§‹æˆã€æœªå…¥é‡‘ã€è¨¼æ†‘ä¿ç®¡çŠ¶æ³"),
    "finance/budgets": ("äºˆç®—ç®¡ç†ãƒ»äºˆå®Ÿæ¯”è¼ƒ", "æœˆåˆ¥ã®å…¥é‡‘ç›®æ¨™ã€çµŒè²»äºˆç®—ã€å®Ÿç¸¾å·®ç•°ã®ç®¡ç†"),
    "finance/cashflow": ("è³‡é‡‘ç¹°ã‚Šãƒ»90æ—¥äºˆæ¸¬", "å…¥å‡ºé‡‘äºˆå®šã€æœªå…¥é‡‘è«‹æ±‚ã€å°†æ¥æ®‹é«˜ã®ç¢ºèª"),
    "finance/recurring": ("å®šæœŸåæ”¯ãƒ»è‡ªå‹•ç™»éŒ²", "æ¯æœˆã®å…¥é‡‘ãƒ»çµŒè²»ã‚’é‡è¤‡ãªãå°å¸³ã¸è‡ªå‹•ç™»éŒ²"),
    "finance/accounts": ("å£åº§ãƒ»ç¾é‡‘æ®‹é«˜ç®¡ç†", "éŠ€è¡Œå£åº§ã€ç¾é‡‘ã€æ±ºæ¸ˆå£åº§ã”ã¨ã®æ®‹é«˜ã¨æŒ¯æ›¿"),
    "finance/reconciliation": ("å£åº§æ®‹é«˜ç…§åˆãƒ»å·®é¡ãƒã‚§ãƒƒã‚¯", "å¸³ç°¿æ®‹é«˜ã¨éŠ€è¡Œãƒ»ç¾é‡‘ã®å®Ÿæ®‹é«˜ã‚’ç…§åˆ"),
    "finance/statements": ("éŠ€è¡Œæ˜ç´°CSVå–è¾¼ãƒ»è‡ªå‹•ç…§åˆ", "éŠ€è¡Œãƒ»æ±ºæ¸ˆæ˜ç´°ã®å–è¾¼ã€å°å¸³ç…§åˆã€æœªå‡¦ç†ç¢ºèª"),
    "finance/rules": ("æ‘˜è¦ãƒ«ãƒ¼ãƒ«ãƒ»è‡ªå‹•ä»•è¨³å€™è£œ", "æ‘˜è¦ã‚­ãƒ¼ãƒ¯ãƒ¼ãƒ‰ã‹ã‚‰è²»ç›®å€™è£œã‚’åˆ¤å®šã—ç¢ºèªå¾Œã«ç™»éŒ²"),
    "finance/tax": ("æ¶ˆè²»ç¨é›†è¨ˆãƒ»ã‚¤ãƒ³ãƒœã‚¤ã‚¹ç¢ºèª", "ç¨ç‡ãƒ»èª²ç¨åŒºåˆ†åˆ¥é›†è¨ˆã€ç´ä»˜è¦‹è¾¼ã€é©æ ¼è«‹æ±‚æ›¸ã®ç¢ºèª"),
    "finance/payables": ("å–å¼•å…ˆãƒ»è²·æ›é‡‘ãƒ»æ”¯æ‰•ç®¡ç†", "æ”¯æ‰•å…ˆã€è«‹æ±‚é¡ã€æœŸé™ã€æœªæ‰•ãƒ»æ”¯æ‰•æ¸ˆã¿ã®ç®¡ç†"),
    "finance/receivables": ("å£²æ›é‡‘ãƒ»è«‹æ±‚æ›¸å…¥é‡‘æ¶ˆè¾¼", "æœªå…¥é‡‘è«‹æ±‚ã€æœŸé™è¶…éã€å£åº§å…¥é‡‘ã€éŠ€è¡Œæ˜ç´°ã¨ã®æ¶ˆè¾¼"),
    "finance/corrections": ("ä»•è¨³è¨‚æ­£ãƒ»å–æ¶ˆå±¥æ­´", "å…ƒè¨˜éŒ²ã‚’æ®‹ã™åå¯¾ä»•è¨³ã€è¨‚æ­£ä»•è¨³ã€ç†ç”±ã¨æ“ä½œå±¥æ­´"),
    "finance/expense-requests": ("çµŒè²»ç”³è«‹ãƒ»æ‰¿èªç®¡ç†", "å¾“æ¥­å“¡ã®çµŒè²»ç”³è«‹ã€é ˜åæ›¸æ·»ä»˜ã€ç®¡ç†è€…æ‰¿èªã€å´ä¸‹ã€å°å¸³è¨ˆä¸Š"),
    "finance/audit": ("ä¼šè¨ˆæ“ä½œãƒ­ã‚°ãƒ»ç›£æŸ»è¨¼è·¡", "ä¼šè¨ˆæ“ä½œã®å®Ÿè¡Œè€…ã€æ—¥æ™‚ã€å¯¾è±¡ã€å‡¦ç†å†…å®¹ã®è¿½è·¡"),
    "finance/books": ("ä»•è¨³å¸³ãƒ»ç§‘ç›®åˆ¥å…ƒå¸³", "æ—¥ä»˜é †ã€è²»ç›®åˆ¥ã€å£åº§åˆ¥ã®ä¼šè¨ˆå¸³ç°¿ã¨CSVå‡ºåŠ›"),
    "finance/trial-balance": ("æœˆæ¬¡ãƒ»å¹´åº¦è¤‡å¼è©¦ç®—è¡¨", "è¤‡å¼ä»•è¨³ã«ã‚ˆã‚‹æœŸé¦–ãƒ»å½“æœŸãƒ»æœŸæœ«ã®å€Ÿæ–¹è²¸æ–¹æ®‹é«˜ç¢ºèª"),
    "finance/statements-report": ("æç›Šè¨ˆç®—æ›¸ãƒ»è²¸å€Ÿå¯¾ç…§è¡¨", "è¤‡å¼ä»•è¨³ã«ã‚ˆã‚‹åç›Šãƒ»è²»ç”¨ãƒ»è³‡ç”£ãƒ»è² å‚µãƒ»ç´”è³‡ç”£ã®ç¢ºèª"),
    "finance/chart-accounts": ("å‹˜å®šç§‘ç›®ãƒ»è£œåŠ©ç§‘ç›®ç®¡ç†", "è¤‡å¼ç°¿è¨˜ã§ä½¿ç”¨ã™ã‚‹å‹˜å®šç§‘ç›®ã€è£œåŠ©ç§‘ç›®ã€æ—¢å­˜è²»ç›®ã¨ã®å¯¾å¿œç®¡ç†"),
    "finance/journals": ("è¤‡å¼ç°¿è¨˜ä»•è¨³", "å€Ÿæ–¹ãƒ»è²¸æ–¹ãŒä¸€è‡´ã™ã‚‹ä»•è¨³ä¼ç¥¨ã€æ—¢å­˜åæ”¯é€£æºã€å–æ¶ˆä»•è¨³ã®ç®¡ç†"),
    "finance/opening-balances": ("æœŸé¦–æ®‹é«˜ãƒ»å¹´åº¦ç¹°è¶Š", "åˆå¹´åº¦ã®æœŸé¦–æ®‹é«˜ã¨ç· ã‚æ¸ˆã¿å¹´åº¦ã‹ã‚‰ç¿Œå¹´åº¦ã¸ã®æ®‹é«˜ç¹°è¶Š"),
    "finance/general-ledger": ("ç·å‹˜å®šå…ƒå¸³ãƒ»è¤‡å¼è©¦ç®—è¡¨", "è¤‡å¼ä»•è¨³ã‚’åŸºç¤ã«ã—ãŸç§‘ç›®åˆ¥å…ƒå¸³ã¨è²¸å€Ÿä¸€è‡´ã™ã‚‹æ®‹é«˜è©¦ç®—è¡¨"),
    "finance/fixed-assets": ("å›ºå®šè³‡ç”£å°å¸³ãƒ»æ¸›ä¾¡å„Ÿå´", "è¨­å‚™ãƒ»è»Šä¸¡ç­‰ã®å–å¾—æƒ…å ±ã€è€ç”¨å¹´æ•°ã€å¹´åº¦å„Ÿå´ã®ç®¡ç†"),
    "finance/year-end": ("ä¼šè¨ˆå¹´åº¦è¨­å®šãƒ»å¹´åº¦ç· ã‚", "äº‹æ¥­å¹´åº¦ã®é–‹å§‹æœˆã€å¹´åº¦ç‚¹æ¤œã€å¹´åº¦ç¢ºå®šã®ç®¡ç†"),
    "finance/year-end-checklist": ("æ±ºç®—å‰ãƒã‚§ãƒƒã‚¯ãƒªã‚¹ãƒˆ", "å¹´åº¦ç· ã‚å‰ã®æ®‹é«˜ãƒ»è¨¼æ†‘ãƒ»ç¨å‹™ç¢ºèªã¨å®Œäº†è¨˜éŒ²"),
    "finance/closing": ("æœˆæ¬¡ç· ã‚ãƒ»ä¼šè¨ˆæœŸé–“ãƒ­ãƒƒã‚¯", "æœˆæ¬¡ç‚¹æ¤œã€æ®‹é«˜ç¢ºå®šã€ç· ã‚å¾Œã®èª¤ç™»éŒ²é˜²æ­¢"),
    "finance/export": ("ä¼šè¨ˆãƒ»è¨¼æ†‘ä¸€æ‹¬å‡ºåŠ›", "ç¨ç†å£«å…±æœ‰ç”¨CSVã€è¨¼æ†‘åŸæœ¬ã€æ•´åˆæ€§æƒ…å ±ã®ZIPå‡ºåŠ›"),
    "invoices": ("è«‹æ±‚æ›¸ç®¡ç†", "è²©å£²æ¡ˆä»¶ã®è«‹æ±‚æ›¸ä½œæˆã€å…¥é‡‘ç®¡ç†ã€PDFå‡ºåŠ›"),
    "costs": ("åŸä¾¡ãƒ»åˆ©ç›Šç®¡ç†", "çŠ¬ãƒ»å‡ºç”£å›åˆ¥ã®çµŒè²»é…è³¦ã¨æ¡ç®—ç¢ºèª"),
    "finance/documents": ("é ˜åæ›¸ãƒ»è¨¼æ†‘ç®¡ç†", "å°å¸³è¨˜éŒ²ã«ç´ã¥ãé ˜åæ›¸ãƒ»è«‹æ±‚æ›¸ã®ä¿ç®¡"),
}
PREFECTURES = [
    "åŒ—æµ·é“", "é’æ£®çœŒ", "å²©æ‰‹çœŒ", "å®®åŸçœŒ", "ç§‹ç”°çœŒ", "å±±å½¢çœŒ", "ç¦å³¶çœŒ", "èŒ¨åŸçœŒ", "æ ƒæœ¨çœŒ", "ç¾¤é¦¬çœŒ",
    "åŸ¼ç‰çœŒ", "åƒè‘‰çœŒ", "æ±äº¬éƒ½", "ç¥å¥ˆå·çœŒ", "æ–°æ½ŸçœŒ", "å¯Œå±±çœŒ", "çŸ³å·çœŒ", "ç¦äº•çœŒ", "å±±æ¢¨çœŒ", "é•·é‡çœŒ",
    "å²é˜œçœŒ", "é™å²¡çœŒ", "æ„›çŸ¥çœŒ", "ä¸‰é‡çœŒ", "æ»‹è³€çœŒ", "äº¬éƒ½åºœ", "å¤§é˜ªåºœ", "å…µåº«çœŒ", "å¥ˆè‰¯çœŒ", "å’Œæ­Œå±±çœŒ",
    "é³¥å–çœŒ", "å³¶æ ¹çœŒ", "å²¡å±±çœŒ", "åºƒå³¶çœŒ", "å±±å£çœŒ", "å¾³å³¶çœŒ", "é¦™å·çœŒ", "æ„›åª›çœŒ", "é«˜çŸ¥çœŒ", "ç¦å²¡çœŒ",
    "ä½è³€çœŒ", "é•·å´çœŒ", "ç†Šæœ¬çœŒ", "å¤§åˆ†çœŒ", "å®®å´çœŒ", "é¹¿å…å³¶çœŒ", "æ²–ç¸„çœŒ", "æµ·å¤–",
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
    role: Mapped[Role] = mapped_column(SQLEnum(Role), default=Role.customer)  # æ—§DBäº’æ›
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


class FinancialEntry(Base):
    __tablename__ = "financial_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceEntryCorrection(Base):
    __tablename__ = "finance_entry_corrections"
    __table_args__ = (UniqueConstraint("original_entry_id", name="uq_finance_correction_original"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    original_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="RESTRICT"), index=True)
    reversal_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="RESTRICT"), unique=True)
    replacement_entry_id: Mapped[int | None] = mapped_column(ForeignKey("financial_entries.id", ondelete="RESTRICT"), nullable=True, unique=True)
    correction_type: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(String(500))
    corrected_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceBudget(Base):
    __tablename__ = "finance_budgets"
    __table_args__ = (UniqueConstraint("tenant_id", "year", "month", "entry_type", "category", name="uq_finance_budget_period_category"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceCashPlan(Base):
    __tablename__ = "finance_cash_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    due_on: Mapped[date] = mapped_column(Date, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)
    ledger_entry_id: Mapped[int | None] = mapped_column(ForeignKey("financial_entries.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceRecurringRule(Base):
    __tablename__ = "finance_recurring_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    day_of_month: Mapped[int] = mapped_column(Integer)
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)
    start_on: Mapped[date] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class FinanceRecurringPosting(Base):
    __tablename__ = "finance_recurring_postings"
    __table_args__ = (UniqueConstraint("rule_id", "period", name="uq_finance_recurring_rule_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("finance_recurring_rules.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    financial_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceAccount(Base):
    __tablename__ = "finance_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(30), index=True)
    opening_balance: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class FinanceAccountEntry(Base):
    __tablename__ = "finance_account_entries"
    __table_args__ = (UniqueConstraint("financial_entry_id", name="uq_finance_account_entry"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="CASCADE"), index=True)
    financial_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="CASCADE"), index=True)


class FinanceAccountTransfer(Base):
    __tablename__ = "finance_account_transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    transferred_on: Mapped[date] = mapped_column(Date, index=True)
    from_account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="CASCADE"), index=True)
    to_account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FinanceAccountReconciliation(Base):
    __tablename__ = "finance_account_reconciliations"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", "statement_on", name="uq_finance_account_reconciliation"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="CASCADE"), index=True)
    statement_on: Mapped[date] = mapped_column(Date, index=True)
    ledger_balance: Mapped[int] = mapped_column(Integer)
    actual_balance: Mapped[int] = mapped_column(Integer)
    difference: Mapped[int] = mapped_column(Integer)
    checked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FinanceStatementImport(Base):
    __tablename__ = "finance_statement_imports"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", "content_hash", name="uq_finance_statement_import_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceStatementLine(Base):
    __tablename__ = "finance_statement_lines"
    __table_args__ = (UniqueConstraint("import_id", "row_no", name="uq_finance_statement_line_row"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("finance_statement_imports.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="CASCADE"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    transacted_on: Mapped[date] = mapped_column(Date, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="unmatched", index=True)
    financial_entry_id: Mapped[int | None] = mapped_column(ForeignKey("financial_entries.id", ondelete="SET NULL"), nullable=True, index=True)


class FinanceCategorizationRule(Base):
    __tablename__ = "finance_categorization_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "keyword", "entry_type", name="uq_finance_categorization_rule"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    keyword: Mapped[str] = mapped_column(String(100), index=True)
    entry_type: Mapped[str] = mapped_column(String(20), default="any", index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceTaxClassification(Base):
    __tablename__ = "finance_tax_classifications"
    __table_args__ = (UniqueConstraint("financial_entry_id", name="uq_finance_tax_classification_entry"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    financial_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="CASCADE"), index=True)
    tax_category: Mapped[str] = mapped_column(String(30), index=True)
    tax_rate: Mapped[int] = mapped_column(Integer, default=0)
    invoice_status: Mapped[str] = mapped_column(String(30), default="unconfirmed", index=True)
    invoice_registration_no: Mapped[str | None] = mapped_column(String(14), nullable=True)
    checked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceVendor(Base):
    __tablename__ = "finance_vendors"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_finance_vendor_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    invoice_registration_no: Mapped[str | None] = mapped_column(String(14), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinancePayable(Base):
    __tablename__ = "finance_payables"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("finance_vendors.id", ondelete="RESTRICT"), index=True)
    received_on: Mapped[date] = mapped_column(Date, index=True)
    due_on: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(String(200))
    invoice_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="unpaid", index=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("finance_accounts.id", ondelete="SET NULL"), nullable=True)
    financial_entry_id: Mapped[int | None] = mapped_column(ForeignKey("financial_entries.id", ondelete="SET NULL"), nullable=True, unique=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceExpenseRequest(Base):
    __tablename__ = "finance_expense_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    expense_on: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("finance_accounts.id", ondelete="SET NULL"), nullable=True)
    financial_entry_id: Mapped[int | None] = mapped_column(ForeignKey("financial_entries.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceExpenseDocument(Base):
    __tablename__ = "finance_expense_documents"
    __table_args__ = (UniqueConstraint("expense_request_id", name="uq_finance_expense_document_request"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    expense_request_id: Mapped[int] = mapped_column(ForeignKey("finance_expense_requests.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    file_data: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceAuditEvent(Base):
    __tablename__ = "finance_audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(300))
    details: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FinanceFiscalSetting(Base):
    __tablename__ = "finance_fiscal_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_finance_fiscal_setting_tenant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    start_month: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceYearClose(Base):
    __tablename__ = "finance_year_closes"
    __table_args__ = (UniqueConstraint("tenant_id", "start_year", name="uq_finance_year_close"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    start_year: Mapped[int] = mapped_column(Integer, index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    income_total: Mapped[int] = mapped_column(Integer)
    expense_total: Mapped[int] = mapped_column(Integer)
    entry_count: Mapped[int] = mapped_column(Integer)
    closed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FinanceYearCloseChecklist(Base):
    __tablename__ = "finance_year_close_checklists"
    __table_args__ = (UniqueConstraint("tenant_id", "start_year", "item_key", name="uq_finance_year_close_checklist_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    start_year: Mapped[int] = mapped_column(Integer, index=True)
    item_key: Mapped[str] = mapped_column(String(40), index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceFixedAsset(Base):
    __tablename__ = "finance_fixed_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    asset_type: Mapped[str] = mapped_column(String(30), index=True)
    acquired_on: Mapped[date] = mapped_column(Date, index=True)
    acquisition_cost: Mapped[int] = mapped_column(Integer)
    useful_life_years: Mapped[int] = mapped_column(Integer)
    business_use_percent: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    disposed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceDepreciationPosting(Base):
    __tablename__ = "finance_depreciation_postings"
    __table_args__ = (UniqueConstraint("asset_id", "start_year", name="uq_finance_depreciation_asset_year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("finance_fixed_assets.id", ondelete="RESTRICT"), index=True)
    start_year: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    financial_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="RESTRICT"), unique=True)
    posted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceChartAccount(Base):
    __tablename__ = "finance_chart_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_finance_chart_account_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(20), index=True)
    normal_side: Mapped[str] = mapped_column(String(10))
    system_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceSubaccount(Base):
    __tablename__ = "finance_subaccounts"
    __table_args__ = (UniqueConstraint("account_id", "code", name="uq_finance_subaccount_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_chart_accounts.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceCategoryAccountMap(Base):
    __tablename__ = "finance_category_account_maps"
    __table_args__ = (UniqueConstraint("tenant_id", "entry_type", "category", name="uq_finance_category_account_map"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_chart_accounts.id", ondelete="RESTRICT"), index=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceJournalEntry(Base):
    __tablename__ = "finance_journal_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "voucher_no", name="uq_finance_journal_voucher"), UniqueConstraint("source_entry_id", name="uq_finance_journal_source_entry"))
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    voucher_no: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(200))
    source_entry_id: Mapped[int | None] = mapped_column(ForeignKey("financial_entries.id", ondelete="RESTRICT"), nullable=True)
    reversal_of_id: Mapped[int | None] = mapped_column(ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="posted", index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceJournalLine(Base):
    __tablename__ = "finance_journal_lines"
    __table_args__ = (UniqueConstraint("journal_entry_id", "line_no", name="uq_finance_journal_line_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("finance_journal_entries.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String(10), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_chart_accounts.id", ondelete="RESTRICT"), index=True)
    subaccount_id: Mapped[int | None] = mapped_column(ForeignKey("finance_subaccounts.id", ondelete="RESTRICT"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    memo: Mapped[str | None] = mapped_column(String(200), nullable=True)


class FinanceOpeningBalance(Base):
    __tablename__ = "finance_opening_balances"
    __table_args__ = (UniqueConstraint("tenant_id", "start_year", "account_id", "subaccount_id", name="uq_finance_opening_balance_account"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    start_year: Mapped[int] = mapped_column(Integer, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_chart_accounts.id", ondelete="RESTRICT"), index=True)
    subaccount_id: Mapped[int | None] = mapped_column(ForeignKey("finance_subaccounts.id", ondelete="RESTRICT"), nullable=True)
    balance: Mapped[int] = mapped_column(Integer)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceYearCarryforward(Base):
    __tablename__ = "finance_year_carryforwards"
    __table_args__ = (UniqueConstraint("tenant_id", "source_start_year", name="uq_finance_year_carryforward_source"), UniqueConstraint("tenant_id", "target_start_year", name="uq_finance_year_carryforward_target"))
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    source_start_year: Mapped[int] = mapped_column(Integer, index=True)
    target_start_year: Mapped[int] = mapped_column(Integer, index=True)
    source_year_close_id: Mapped[int] = mapped_column(ForeignKey("finance_year_closes.id", ondelete="RESTRICT"), unique=True)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), unique=True)
    debit_total: Mapped[int] = mapped_column(Integer)
    credit_total: Mapped[int] = mapped_column(Integer)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinancePeriodClose(Base):
    __tablename__ = "finance_period_closes"
    __table_args__ = (UniqueConstraint("tenant_id", "year", "month", name="uq_finance_period_close"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    income_total: Mapped[int] = mapped_column(Integer, default=0)
    expense_total: Mapped[int] = mapped_column(Integer, default=0)
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_no", name="uq_invoice_tenant_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    puppy_sale_id: Mapped[int] = mapped_column(ForeignKey("puppy_sales.id", ondelete="CASCADE"), index=True)
    invoice_no: Mapped[str] = mapped_column(String(80), index=True)
    issued_on: Mapped[date] = mapped_column(Date, index=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ledger_entry_id: Mapped[int | None] = mapped_column(ForeignKey("financial_entries.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceReceivableSettlement(Base):
    __tablename__ = "finance_receivable_settlements"
    __table_args__ = (UniqueConstraint("invoice_id", name="uq_finance_receivable_invoice"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    received_on: Mapped[date] = mapped_column(Date, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="RESTRICT"), index=True)
    financial_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="RESTRICT"), unique=True)
    statement_line_id: Mapped[int | None] = mapped_column(ForeignKey("finance_statement_lines.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CostAllocation(Base):
    __tablename__ = "cost_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    financial_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), nullable=True, index=True)
    litter_id: Mapped[int | None] = mapped_column(ForeignKey("litters.id", ondelete="CASCADE"), nullable=True, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinanceDocument(Base):
    __tablename__ = "finance_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    financial_entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="CASCADE"), index=True)
    document_type: Mapped[str] = mapped_column(String(30), index=True)
    issued_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    document_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    file_data: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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
    device_name: Mapped[str] = mapped_column(String(100), default="ã‚¹ãƒãƒ¼ãƒˆãƒ•ã‚©ãƒ³")
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
    """é€ä¿¡æˆåŠŸæ™‚ã¯Noneã€å¤±æ•—æ™‚ã¯å®‰å…¨ã«çŸ­ç¸®ã—ãŸç†ç”±ã‚’è¿”ã™ã€‚"""
    if not smtp_ready():
        return "ãƒ¡ãƒ¼ãƒ«é…ä¿¡ã‚µãƒ¼ãƒ“ã‚¹ãŒæœªè¨­å®šã§ã™"
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
            record_operation(session, "email", "failed", "ãƒ¡ãƒ¼ãƒ«é…ä¿¡ã«å¤±æ•—ã—ã¾ã—ãŸ", delivery.tenant_id,
                f"delivery={delivery.id} purpose={delivery.purpose} error={error}")
        return False
    delivery.status, delivery.error, delivery.sent_at = "sent", None, datetime.now(timezone.utc)
    record_operation(session, "email", "success", "ãƒ¡ãƒ¼ãƒ«ã‚’é…ä¿¡ã—ã¾ã—ãŸ", delivery.tenant_id,
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
        raise HTTPException(status_code=503, detail="LINEèªè¨¼æƒ…å ±ã®æš—å·éµãŒè¨­å®šã•ã‚Œã¦ã„ã¾ã›ã‚“")
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
        text_body = f"{message}\n\nè©³ç´°ã‚’ç¢ºèªã™ã‚‹\n{full_url}"[:5000]
        payload = json.dumps({"to": link.line_user_id, "messages": [{"type": "text", "text": text_body}]}, ensure_ascii=False).encode()
        request = UrlRequest("https://api.line.me/v2/bot/message/push", data=payload, method="POST", headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"LINE API status {response.status}")
        delivery.status, delivery.error, delivery.sent_at = "sent", None, datetime.now(timezone.utc)
        record_operation(session, "line", "success", "LINEé€šçŸ¥ã‚’é…ä¿¡ã—ã¾ã—ãŸ", tenant_id, f"user={user_id} category={category}")
        return True
    except (HTTPError, URLError, RuntimeError, TimeoutError) as exc:
        delivery.status, delivery.error = "failed", f"{type(exc).__name__}: {str(exc)[:420]}"
        record_operation(session, "line", "failed", "LINEé€šçŸ¥ã®é…ä¿¡ã«å¤±æ•—ã—ã¾ã—ãŸ", tenant_id, f"user={user_id} category={category} error={type(exc).__name__}")
        return False


VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "")


def ensure_vapid_keys(session: Session) -> None:
    """ç’°å¢ƒå¤‰æ•°ãŒãªã„å ´åˆã ã‘ã€DBã¸æ°¸ç¶šåŒ–ã—ãŸP-256éµã‚’å†åˆ©ç”¨ã™ã‚‹ã€‚"""
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


def record_finance_audit(session: Session, tenant_id: int, actor_user_id: int, action: str,
                         entity_type: str, entity_id: int | None, summary: str,
                         details: str | None = None) -> None:
    """ä¼šè¨ˆæ“ä½œã‚’è¿½è¨˜å°‚ç”¨ã®ç›£æŸ»è¨¼è·¡ã¨ã—ã¦ä¿å­˜ã™ã‚‹ã€‚"""
    session.add(FinanceAuditEvent(tenant_id=tenant_id, actor_user_id=actor_user_id,
        action=action[:40], entity_type=entity_type[:40], entity_id=entity_id,
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
            record_operation(session, "push", "failed", "ãƒ–ãƒ©ã‚¦ã‚¶é€šçŸ¥ã®é…ä¿¡ã«å¤±æ•—ã—ã¾ã—ãŸ",
                details=f"user={user_id} endpoint_id={subscription.id} error={type(exc).__name__}")
    receipt.status = "sent" if sent else "failed"
    if sent:
        record_operation(session, "push", "success", f"ãƒ–ãƒ©ã‚¦ã‚¶é€šçŸ¥ã‚’{sent}ç«¯æœ«ã¸é…ä¿¡ã—ã¾ã—ãŸ",
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
        raise HTTPException(status_code=403, detail="ã“ã®ãƒ†ãƒŠãƒ³ãƒˆã®ç®¡ç†æ¨©é™ãŒã‚ã‚Šã¾ã›ã‚“")
    return user, tenant


def require_tenant_user(request: Request, user: User = Depends(require_user), session: Session = Depends(db)):
    tenant = selected_tenant(request, user, session)
    if not tenant or tenant_role(user, tenant, session) is None:
        raise HTTPException(status_code=403, detail="åˆ©ç”¨ã§ãã‚‹ãƒ†ãƒŠãƒ³ãƒˆãŒã‚ã‚Šã¾ã›ã‚“")
    return user, tenant


def page_usage_guide(title: str) -> str:
    """ãƒ­ã‚°ã‚¤ãƒ³å¾Œã®å…¨ç”»é¢ã¨ä»Šå¾Œè¿½åŠ ã™ã‚‹ç”»é¢ã¸ã€å…±é€šå½¢å¼ã®æ“ä½œèª¬æ˜ã‚’è‡ªå‹•è¡¨ç¤ºã™ã‚‹ã€‚"""
    page_name = title.split("ï½œ", 1)[0].strip()
    guides = [
        (("ãƒ›ãƒ¼ãƒ ",), ["çŠ¬èˆå…¨ä½“ã®ç™»éŒ²çŠ¶æ³ã¨ã€å„ªå…ˆã—ã¦å¯¾å¿œã™ã‚‹äºˆå®šã‚’ç¢ºèªã§ãã¾ã™ã€‚", "æœŸé™è¶…éãƒ»æœ¬æ—¥ãƒ»7æ—¥ä»¥å†…ã®æ¥­å‹™ã‹ã‚‰å„ç®¡ç†ç”»é¢ã¸ç›´æ¥ç§»å‹•ã§ãã¾ã™ã€‚"], ["è¦å¯¾å¿œã‚µãƒãƒªãƒ¼ã§æœŸé™è¶…éãŒãªã„ã‹ç¢ºèªã—ã¾ã™ã€‚", "æœ¬æ—¥ã¨7æ—¥ä»¥å†…ã®äºˆå®šã‚’å„ªå…ˆåº¦é †ã«ç¢ºèªã—ã¾ã™ã€‚", "äºˆå®šåã¾ãŸã¯ã‚¯ã‚¤ãƒƒã‚¯æ“ä½œã‹ã‚‰å¯¾è±¡ç”»é¢ã‚’é–‹ãã¾ã™ã€‚"], "è¡¨ç¤ºå†…å®¹ã¯é¸æŠä¸­ã®ä¼šç¤¾ãƒ»çŠ¬èˆã ã‘ã«é™å®šã•ã‚Œã¾ã™ã€‚ä½œæ¥­å‰ã«ç”»é¢ä¸Šéƒ¨ã®é¸æŠå…ˆã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼",), ["Todoã€ç¹æ®–ã€å¥åº·ã€è²©å£²ã€æ³•ä»¤ã®äºˆå®šã‚’1ã‹æ‰€ã§ç¢ºèªã§ãã¾ã™ã€‚", "æœˆãƒ»åˆ†é¡ãƒ»çŠ¶æ…‹ã§çµã‚Šè¾¼ã¿ã€æœŸé™è¶…éã‚’æ—©ãè¦‹ã¤ã‘ã‚‰ã‚Œã¾ã™ã€‚"], ["è¡¨ç¤ºã™ã‚‹æœˆã‚’é¸ã³ã¾ã™ã€‚", "å¿…è¦ã«å¿œã˜ã¦åˆ†é¡ã¨çŠ¶æ…‹ã‚’æŒ‡å®šã—ã¾ã™ã€‚", "äºˆå®šåã‚’é¸ã³ã€å…ƒã®ç®¡ç†ç”»é¢ã§å†…å®¹ã‚’ç¢ºèªãƒ»æ›´æ–°ã—ã¾ã™ã€‚"], "è‡ªå‹•è¡¨ç¤ºã•ã‚Œã‚‹äºˆæ¸¬æ—¥ã¯ç›®å®‰ã§ã™ã€‚äº¤é…ãƒ»å‡ºç”£ãƒ»åŒ»ç™‚ãƒ»è¡Œæ”¿ã®ç¢ºå®šæ—¥ã¯åŸè¨˜éŒ²ã§ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("é€šçŸ¥é…ä¿¡å±¥æ­´",), ["LINEãƒ»ãƒ¡ãƒ¼ãƒ«ãƒ»ãƒ–ãƒ©ã‚¦ã‚¶ã®é…ä¿¡çµæœã‚’ã¾ã¨ã‚ã¦ç¢ºèªã§ãã¾ã™ã€‚", "æ¡ä»¶æ¤œç´¢ã€å¤±æ•—é€šçŸ¥ã®å†é€ã€CSVãƒ»PDFå‡ºåŠ›ãŒã§ãã¾ã™ã€‚"], ["æ¤œç´¢æ¡ä»¶ã‚’æŒ‡å®šã—ã¦å±¥æ­´ã‚’çµã‚Šè¾¼ã¿ã¾ã™ã€‚", "å¤±æ•—ç†ç”±ã‚’ç¢ºèªã—ã€è¨­å®šä¿®æ­£å¾Œã«å¿…è¦ãªé€šçŸ¥ã ã‘å†é€ã—ã¾ã™ã€‚", "å¿…è¦ã«å¿œã˜ã¦è¡¨ç¤ºæ¡ä»¶ã®ã¾ã¾å¸³ç¥¨ã‚’å‡ºåŠ›ã—ã¾ã™ã€‚"], "å†é€ã¯ã‚ªãƒ¼ãƒŠãƒ¼ã¸å®Ÿéš›ã«é€šçŸ¥ã•ã‚Œã¾ã™ã€‚å®›å…ˆã¨å†…å®¹ã‚’ç¢ºèªã—ã¦ã‹ã‚‰æ“ä½œã—ã¦ãã ã•ã„ã€‚"),
        (("LINEå…¬å¼", "LINEé€£æº"), ["LINEå…¬å¼ã‚¢ã‚«ã‚¦ãƒ³ãƒˆã®æ¥ç¶šçŠ¶æ…‹ã¨ã‚ªãƒ¼ãƒŠãƒ¼é€£æºã‚’ç¢ºèªã§ãã¾ã™ã€‚", "æ¥ç¶šè¨ºæ–­ã€ãƒ†ã‚¹ãƒˆé€šçŸ¥ã€é…ä¿¡å±¥æ­´ã®ç¢ºèªãŒã§ãã¾ã™ã€‚"], ["æ¥ç¶šçŠ¶æ…‹ã¨æœ€çµ‚Webhookå—ä¿¡æ—¥æ™‚ã‚’ç¢ºèªã—ã¾ã™ã€‚", "ã‚ªãƒ¼ãƒŠãƒ¼ã®é€£æºçŠ¶æ…‹ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å¿…è¦ãªå ´åˆã ã‘ãƒ†ã‚¹ãƒˆé€šçŸ¥ã‚’å®Ÿè¡Œã—ã¾ã™ã€‚"], "Channel secretã‚„ã‚¢ã‚¯ã‚»ã‚¹ãƒˆãƒ¼ã‚¯ãƒ³ã¯ç¬¬ä¸‰è€…ã¸å…±æœ‰ã—ãªã„ã§ãã ã•ã„ã€‚"),
        (("å¥åº·", "ä½“é‡", "ãƒ¯ã‚¯ãƒãƒ³", "å¥è¨º", "æŠ•è–¬", "ç—…æ­´", "ãƒ•ãƒ¼ãƒ‰"), ["æ„›çŠ¬ã®å¥åº·è¨˜éŒ²ã€äºˆå®šã€å…±æœ‰ãƒ‡ãƒ¼ã‚¿ã‚’ç¢ºèªãƒ»ç™»éŒ²ã§ãã¾ã™ã€‚", "æ¤œç´¢ã€å®Ÿæ–½æ¸ˆã¿ç®¡ç†ã€ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼è¡¨ç¤ºã€å¸³ç¥¨å‡ºåŠ›ãŒã§ãã¾ã™ã€‚"], ["å¯¾è±¡çŠ¬ã¨å¥åº·ã‚«ãƒ†ã‚´ãƒªãƒ¼ã‚’ç¢ºèªã—ã¾ã™ã€‚", "æ—¥ä»˜ã¨å†…å®¹ã‚’å…¥åŠ›ã—ã¦è¨˜éŒ²ã—ã¾ã™ã€‚", "å¿…è¦ãªè¨˜éŒ²ã ã‘ãƒ–ãƒªãƒ¼ãƒ€ãƒ¼ã¾ãŸã¯ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰ã—ã¾ã™ã€‚"], "å¥åº·è¨˜éŒ²ã¯è¨ºæ–­æ›¸ã§ã¯ã‚ã‚Šã¾ã›ã‚“ã€‚ç·Šæ€¥æ™‚ã‚„åˆ¤æ–­ã«è¿·ã†å ´åˆã¯ç£åŒ»å¸«ã¸ç›¸è«‡ã—ã¦ãã ã•ã„ã€‚"),
        (("ãƒ’ãƒ¼ãƒˆ", "äº¤é…", "éºä¼å­", "è¡€çµ±"), ["ãƒ’ãƒ¼ãƒˆã€äº¤é…è¨ˆç”»ã€è¡€çµ±æƒ…å ±ã€éºä¼å­æ¤œæŸ»ã‚’ç®¡ç†ã§ãã¾ã™ã€‚", "çµ„ã¿åˆã‚ã›ã®æ¤œè¨ã‚„è¿‘è¦ªäº¤é…åˆ†æã«åˆ©ç”¨ã§ãã¾ã™ã€‚"], ["å¯¾è±¡çŠ¬ã¨ç™»éŒ²æ¸ˆã¿æƒ…å ±ã‚’ç¢ºèªã—ã¾ã™ã€‚", "æ—¥ä»˜ãƒ»ç›¸æ‰‹çŠ¬ãƒ»æ¤œæŸ»çµæœãªã©ã‚’å…¥åŠ›ã—ã¾ã™ã€‚", "åˆ†æçµæœã¨åŸè³‡æ–™ã‚’ç…§åˆã—ã¦è¨ˆç”»ã‚’ç¢ºå®šã—ã¾ã™ã€‚"], "è‡ªå‹•è¨ˆç®—ã‚„ææ¡ˆã¯åˆ¤æ–­ææ–™ã§ã™ã€‚è¡€çµ±æ›¸åŸæœ¬ã¨ç£åŒ»å¸«ãƒ»å°‚é–€å®¶ã®ç¢ºèªã‚’å„ªå…ˆã—ã¦ãã ã•ã„ã€‚"),
        (("å‡ºç”£", "ä»”çŠ¬"), ["å‡ºç”£äºˆå®šã€å‡ºç”£è¨˜éŒ²ã€ä»”çŠ¬æƒ…å ±ã‚’ç™»éŒ²ãƒ»ç¢ºèªã§ãã¾ã™ã€‚", "æ¯çŠ¬åˆ¥ã®å‡ºç”£çŠ¶æ³ã¨ä»”çŠ¬ã®ç®¡ç†ã«åˆ©ç”¨ã§ãã¾ã™ã€‚"], ["æ¯çŠ¬ã¨å¯¾è±¡ã®å‡ºç”£è¨˜éŒ²ã‚’é¸ã³ã¾ã™ã€‚", "æ—¥ä»˜ã€é ­æ•°ã€ä»”çŠ¬æƒ…å ±ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "è²©å£²ãƒ»å¥åº·ãƒ»è¡€çµ±æƒ…å ±ã¸æ­£ã—ãé€£æºã•ã‚ŒãŸã‹ç¢ºèªã—ã¾ã™ã€‚"], "å‡ºç”Ÿæ•°ã‚„å€‹ä½“ã®å–ã‚Šé•ãˆã‚’é˜²ããŸã‚ã€ç™»éŒ²å¾Œã«æ¯çŠ¬ã¨æ—¥ä»˜ã‚’å†ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("è«‹æ±‚æ›¸",), ["è²©å£²æ¡ˆä»¶ã‹ã‚‰è«‹æ±‚æ›¸ã‚’ä½œæˆã—ã€ç™ºè¡Œãƒ»å…¥é‡‘çŠ¶æ³ã‚’ç®¡ç†ã§ãã¾ã™ã€‚", "ä½œæˆã—ãŸè«‹æ±‚æ›¸ã‚’PDFã§ä¿å­˜ãƒ»å°åˆ·ã§ãã¾ã™ã€‚"], ["å¯¾è±¡ã®è²©å£²æ¡ˆä»¶ã€è«‹æ±‚é¡ã€æ”¯æ‰•æœŸé™ã‚’ç¢ºèªã—ã¦è«‹æ±‚æ›¸ã‚’ä½œæˆã—ã¾ã™ã€‚", "PDFã‚’é–‹ãã€å®›åãƒ»é‡‘é¡ãƒ»æŒ¯è¾¼æ¡ˆå†…ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å…¥é‡‘ç¢ºèªå¾Œã«å…¥é‡‘æ¸ˆã¿ã¸å¤‰æ›´ã—ã€åæ”¯å°å¸³ã¸ã®åæ˜ ã‚’ç¢ºèªã—ã¾ã™ã€‚"], "è«‹æ±‚æ›¸ã®ç™ºè¡Œå‰ã«é¡§å®¢åãƒ»é‡‘é¡ãƒ»æ”¯æ‰•æœŸé™ã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚å…¥é‡‘æ¸ˆã¿ã¸ã®å¤‰æ›´ã¯åæ”¯å°å¸³ã¸å®Ÿéš›ã®å…¥é‡‘è¨˜éŒ²ã‚’ä½œæˆã—ã¾ã™ã€‚"),
        (("çµŒå–¶åç›Š", "åç›Šãƒ€ãƒƒã‚·ãƒ¥ãƒœãƒ¼ãƒ‰"), ["å¹´é–“ã®å…¥é‡‘ãƒ»çµŒè²»ãƒ»åæ”¯ã‚’æœˆåˆ¥ã«æ¯”è¼ƒã§ãã¾ã™ã€‚", "çµŒè²»æ§‹æˆã€è²©å£²æœªå…¥é‡‘ã€æœŸé™è¶…éè«‹æ±‚ã€è¨¼æ†‘ã®ä¿ç®¡çŠ¶æ³ã‚’ã¾ã¨ã‚ã¦ç¢ºèªã§ãã¾ã™ã€‚"], ["ç¢ºèªã™ã‚‹å¹´ã‚’é¸ã³ã¾ã™ã€‚", "å¹´é–“ã‚µãƒãƒªãƒ¼ã¨æœˆåˆ¥æ¨ç§»ã‚’ç¢ºèªã—ã¾ã™ã€‚", "è¦ç¢ºèªé …ç›®ã‹ã‚‰å°å¸³ãƒ»è«‹æ±‚æ›¸ãƒ»è¨¼æ†‘ãƒ»åŸä¾¡ç®¡ç†ã¸ç§»å‹•ã—ã¾ã™ã€‚"], "è¡¨ç¤ºé¡ã¯ç™»éŒ²æ¸ˆã¿ãƒ‡ãƒ¼ã‚¿ã«åŸºã¥ãçµŒå–¶ç®¡ç†ä¸Šã®æ¦‚ç®—ã§ã™ã€‚æ±ºç®—ãƒ»ç¨å‹™ç”³å‘Šã§ã¯ç¨ç†å£«ã¨åŸè³‡æ–™ã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("äºˆç®—ç®¡ç†", "äºˆå®Ÿæ¯”è¼ƒ"), ["æœˆãƒ»è²»ç›®ã”ã¨ã«å…¥é‡‘ç›®æ¨™ã¨çµŒè²»äºˆç®—ã‚’ç™»éŒ²ã§ãã¾ã™ã€‚", "å®Ÿç¸¾ã¨ã®å·®ã€ç›®æ¨™é”æˆç‡ã€äºˆç®—è¶…éã‚’å¹´é–“ãƒ»æœˆåˆ¥ã«ç¢ºèªã§ãã¾ã™ã€‚"], ["è¡¨ç¤ºå¹´ã‚’é¸ã³ã¾ã™ã€‚", "å¯¾è±¡æœˆãƒ»åŒºåˆ†ãƒ»è²»ç›®ãƒ»äºˆç®—é¡ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "äºˆå®Ÿä¸€è¦§ã§æœªé”ã‚„è¶…éã‚’ç¢ºèªã—ã€å°å¸³ã®å†…å®¹ã‚’è¦‹ç›´ã—ã¾ã™ã€‚"], "äºˆç®—ã¯çµŒå–¶åˆ¤æ–­ç”¨ã®ç›®å®‰ã§ã™ã€‚å®Ÿç¸¾ã¯åæ”¯ãƒ»çµŒè²»å°å¸³ã¸ã®ç™»éŒ²å†…å®¹ã‹ã‚‰é›†è¨ˆã•ã‚Œã¾ã™ã€‚"),
        (("è³‡é‡‘ç¹°ã‚Š", "90æ—¥äºˆæ¸¬"), ["ç¾åœ¨ã®å°å¸³æ®‹é«˜ã¸å…¥é‡‘äºˆå®šãƒ»æ”¯æ‰•äºˆå®šãƒ»æœªå…¥é‡‘è«‹æ±‚æ›¸ã‚’åæ˜ ã—ã€30æ—¥ãƒ»60æ—¥ãƒ»90æ—¥å¾Œã®è¦‹è¾¼ã¿æ®‹é«˜ã‚’ç¢ºèªã§ãã¾ã™ã€‚", "äºˆå®šã‚’å®Ÿè¡Œæ¸ˆã¿ã«ã™ã‚‹ã¨åæ”¯å°å¸³ã¸ä¸€åº¦ã ã‘åæ˜ ã§ãã¾ã™ã€‚"], ["ä»Šå¾Œã®å…¥é‡‘äºˆå®šã¾ãŸã¯æ”¯æ‰•äºˆå®šã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "æœŸé–“åˆ¥ã®è¦‹è¾¼ã¿æ®‹é«˜ã¨äºˆå®šä¸€è¦§ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å®Ÿéš›ã«å…¥å‡ºé‡‘ã—ãŸäºˆå®šã ã‘å®Ÿè¡Œæ¸ˆã¿ã«ã—ã¾ã™ã€‚"], "è¦‹è¾¼ã¿æ®‹é«˜ã¯ç™»éŒ²æ¸ˆã¿äºˆå®šã«åŸºã¥ãæ¦‚ç®—ã§ã™ã€‚äºŒé‡è¨ˆä¸Šã‚’é˜²ããŸã‚ã€è«‹æ±‚æ›¸ç”±æ¥ã®å…¥é‡‘ã‚’æ‰‹å‹•äºˆå®šã¸é‡è¤‡ç™»éŒ²ã—ãªã„ã§ãã ã•ã„ã€‚"),
        (("å®šæœŸåæ”¯", "è‡ªå‹•ç™»éŒ²"), ["æ¯æœˆç™ºç”Ÿã™ã‚‹å…¥é‡‘ãƒ»çµŒè²»ã‚’æŒ‡å®šæ—¥ã«åæ”¯å°å¸³ã¸è‡ªå‹•ç™»éŒ²ã§ãã¾ã™ã€‚", "31æ—¥ãªã©å­˜åœ¨ã—ãªã„æ—¥ã¯ã€ãã®æœˆã®æœ«æ—¥ã«è‡ªå‹•èª¿æ•´ã•ã‚Œã¾ã™ã€‚"], ["åŒºåˆ†ãƒ»è²»ç›®ãƒ»é‡‘é¡ãƒ»æ¯æœˆã®ç™»éŒ²æ—¥ãƒ»é–‹å§‹æ—¥ã‚’è¨­å®šã—ã¾ã™ã€‚", "æœ‰åŠ¹ãªãƒ«ãƒ¼ãƒ«ã¨ç›´è¿‘ã®è‡ªå‹•ç™»éŒ²å±¥æ­´ã‚’ç¢ºèªã—ã¾ã™ã€‚", "ä¸è¦ã«ãªã£ãŸãƒ«ãƒ¼ãƒ«ã¯åœæ­¢ã—ã¾ã™ã€‚"], "é‡‘é¡å¤‰æ›´ã‚„åœæ­¢å‰ã«å½“æœˆåˆ†ãŒç™»éŒ²æ¸ˆã¿ã‹ç¢ºèªã—ã¦ãã ã•ã„ã€‚åŒã˜ãƒ«ãƒ¼ãƒ«ã®åŒã˜æœˆã¯ä¸€åº¦ã ã‘ç™»éŒ²ã•ã‚Œã¾ã™ã€‚"),
        (("å£åº§ãƒ»ç¾é‡‘", "å£åº§åˆ¥æ®‹é«˜"), ["éŠ€è¡Œå£åº§ãƒ»ç¾é‡‘ãƒ»æ±ºæ¸ˆå£åº§ã‚’ç™»éŒ²ã—ã€å£åº§ã”ã¨ã®æ®‹é«˜ã‚’ç¢ºèªã§ãã¾ã™ã€‚", "æœªå‰²å½“ã®å°å¸³è¨˜éŒ²ã‚’å£åº§ã¸å‰²ã‚Šå½“ã¦ã€å£åº§é–“ã®è³‡é‡‘ç§»å‹•ã‚’è¨˜éŒ²ã§ãã¾ã™ã€‚"], ["å£åº§åãƒ»ç¨®é¡ãƒ»é–‹å§‹æ®‹é«˜ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "æœªå‰²å½“ã®å…¥é‡‘ãƒ»çµŒè²»ã‚’å®Ÿéš›ã®å…¥å‡ºé‡‘å£åº§ã¸å‰²ã‚Šå½“ã¦ã¾ã™ã€‚", "å£åº§é–“ã§è³‡é‡‘ã‚’ç§»ã—ãŸå ´åˆã¯æŒ¯æ›¿ã¨ã—ã¦ç™»éŒ²ã—ã¾ã™ã€‚"], "å£åº§é–“æŒ¯æ›¿ã¯åç›Šãƒ»çµŒè²»ã¸è¨ˆä¸Šã•ã‚Œã¾ã›ã‚“ã€‚å°å¸³è¨˜éŒ²ã‚’èª¤ã£ãŸå£åº§ã¸å‰²ã‚Šå½“ã¦ãªã„ã‚ˆã†ã€æ—¥ä»˜ãƒ»å†…å®¹ãƒ»é‡‘é¡ã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("å£åº§æ®‹é«˜ç…§åˆ", "å·®é¡ãƒã‚§ãƒƒã‚¯"), ["æŒ‡å®šæ—¥æ™‚ç‚¹ã®å¸³ç°¿æ®‹é«˜ã¨ã€é€šå¸³ãƒ»ç¾é‡‘ãƒ»æ±ºæ¸ˆã‚µãƒ¼ãƒ“ã‚¹ã®å®Ÿæ®‹é«˜ã‚’æ¯”è¼ƒã§ãã¾ã™ã€‚", "å·®é¡ã‚¼ãƒ­ã®ç¢ºèªå±¥æ­´ã‚’æ®‹ã—ã€æœˆæ¬¡ç· ã‚å‰ã®å…¥åŠ›æ¼ã‚Œã‚„äºŒé‡è¨ˆä¸Šã‚’è¦‹ã¤ã‘ã‚‰ã‚Œã¾ã™ã€‚"], ["ç…§åˆæ—¥ã¨å£åº§ã‚’é¸ã³ã¾ã™ã€‚", "é€šå¸³ãªã©ã§ç¢ºèªã—ãŸå®Ÿæ®‹é«˜ã‚’å…¥åŠ›ã—ã¾ã™ã€‚", "å·®é¡ãŒã‚ã‚‹å ´åˆã¯æœªå‰²å½“è¨˜éŒ²ãƒ»æŒ¯æ›¿ãƒ»é–‹å§‹æ®‹é«˜ã‚’ç¢ºèªã—ã¾ã™ã€‚"], "å·®é¡ã‚’æ¶ˆã™ãŸã‚ã ã‘ã®æ¶ç©ºå–å¼•ã¯ç™»éŒ²ã›ãšã€åŸå› ã¨ãªã£ãŸåŸè¨˜éŒ²ã‚’ä¿®æ­£ã—ã¦ãã ã•ã„ã€‚"),
        (("éŠ€è¡Œæ˜ç´°CSV", "æ˜ç´°å–è¾¼", "è‡ªå‹•ç…§åˆ"), ["éŠ€è¡Œã‚„æ±ºæ¸ˆã‚µãƒ¼ãƒ“ã‚¹ã‹ã‚‰å‡ºåŠ›ã—ãŸCSVã‚’å£åº§ã¸å–ã‚Šè¾¼ã‚ã¾ã™ã€‚", "æ—¥ä»˜ãƒ»åŒºåˆ†ãƒ»é‡‘é¡ãŒä¸€è‡´ã™ã‚‹å°å¸³è¨˜éŒ²ã‚’è‡ªå‹•ç…§åˆã—ã€æœªå‡¦ç†æ˜ç´°ã‚’æŠ½å‡ºã§ãã¾ã™ã€‚"], ["å–è¾¼å…ˆå£åº§ã¨CSVãƒ•ã‚¡ã‚¤ãƒ«ã‚’é¸ã³ã¾ã™ã€‚", "è‡ªå‹•ç…§åˆçµæœã¨æœªå‡¦ç†ä»¶æ•°ã‚’ç¢ºèªã—ã¾ã™ã€‚", "æœªå‡¦ç†æ˜ç´°ã ã‘è²»ç›®ã‚’é¸ã‚“ã§å°å¸³ã¸ç™»éŒ²ã—ã¾ã™ã€‚"], "åŒã˜CSVã¯é‡è¤‡å–è¾¼ã§ãã¾ã›ã‚“ã€‚å–è¾¼å‰ã«å£åº§ã¨æ˜ç´°æœŸé–“ã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("æ‘˜è¦ãƒ«ãƒ¼ãƒ«", "è‡ªå‹•ä»•è¨³å€™è£œ"), ["æ‘˜è¦ã«å«ã¾ã‚Œã‚‹ã‚­ãƒ¼ãƒ¯ãƒ¼ãƒ‰ã‹ã‚‰è²»ç›®å€™è£œã‚’è‡ªå‹•è¡¨ç¤ºã§ãã¾ã™ã€‚", "å€™è£œã‚’ç¢ºèªã—ãŸæ˜ç´°ã ã‘å€‹åˆ¥ã¾ãŸã¯ä¸€æ‹¬ã§å°å¸³ã¸ç™»éŒ²ã§ãã¾ã™ã€‚"], ["ã‚­ãƒ¼ãƒ¯ãƒ¼ãƒ‰ãƒ»å…¥å‡ºé‡‘åŒºåˆ†ãƒ»è²»ç›®ãƒ»å„ªå…ˆåº¦ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "éŠ€è¡Œæ˜ç´°ç”»é¢ã§å€™è£œã¨é©ç”¨ãƒ«ãƒ¼ãƒ«ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å†…å®¹ãŒæ­£ã—ã„å€™è£œã ã‘ç¢ºèªæ“ä½œã§å°å¸³ã¸åæ˜ ã—ã¾ã™ã€‚"], "ãƒ«ãƒ¼ãƒ«ã¯å€™è£œåˆ¤å®šã ã‘ã«ä½¿ã‚ã‚Œã€ç¢ºèªãªã—ã«è‡ªå‹•è¨ˆä¸Šã•ã‚Œã¾ã›ã‚“ã€‚å„ªå…ˆåº¦ãŒé«˜ã„ãƒ«ãƒ¼ãƒ«ã‹ã‚‰é©ç”¨ã•ã‚Œã¾ã™ã€‚"),
        (("æ¶ˆè²»ç¨åŒºåˆ†", "ã‚¤ãƒ³ãƒœã‚¤ã‚¹ç¢ºèª"), ["å°å¸³è¨˜éŒ²ã”ã¨ã«èª²ç¨ãƒ»éèª²ç¨ç­‰ã®åŒºåˆ†ã¨ç¨ç‡ã‚’è¨˜éŒ²ã§ãã¾ã™ã€‚", "çµŒè²»ã®é©æ ¼è«‹æ±‚æ›¸ç¢ºèªçŠ¶æ³ã¨ç™»éŒ²ç•ªå·ã‚’æœˆåˆ¥ã«ç‚¹æ¤œã§ãã¾ã™ã€‚"], ["å¯¾è±¡æœˆã‚’é¸ã³ã€æœªåˆ†é¡ã®å–å¼•ã‚’ç¢ºèªã—ã¾ã™ã€‚", "ç¨åŒºåˆ†ãƒ»ç¨ç‡ãƒ»é©æ ¼è«‹æ±‚æ›¸ã®çŠ¶æ…‹ã‚’åŸè³‡æ–™ã¨ç…§åˆã—ã¦ç™»éŒ²ã—ã¾ã™ã€‚", "æœˆæ¬¡ç· ã‚å‰ã«æœªåˆ†é¡ä»¶æ•°ã¨æœªç¢ºèªä»¶æ•°ã‚’ã‚¼ãƒ­ã«è¿‘ã¥ã‘ã¾ã™ã€‚"], "ç¨é¡ã¯ç¨è¾¼é‡‘é¡ã‹ã‚‰æ±‚ã‚ãŸç®¡ç†ä¸Šã®æ¦‚ç®—ã§ã™ã€‚ç™»éŒ²ç•ªå·ã¯å½¢å¼ã ã‘ã‚’ç¢ºèªã—ã€å®Ÿåœ¨ãƒ»æœ‰åŠ¹æ€§ã¯è‡ªå‹•ç…§ä¼šã—ã¾ã›ã‚“ã€‚ç”³å‘ŠåŒºåˆ†ãƒ»ä»•å…¥ç¨é¡æ§é™¤ãƒ»çµŒéæªç½®ã¯ç¨ç†å£«ã¨åŸè³‡æ–™ã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("è²·æ›é‡‘", "æ”¯æ‰•ç®¡ç†", "å–å¼•å…ˆ"), ["ä»•å…¥å…ˆãƒ»ç—…é™¢ãƒ»ä¼šå ´ãƒ»é…é€ä¼šç¤¾ãªã©ã®å–å¼•å…ˆã¨æœªæ‰•è«‹æ±‚ã‚’ç®¡ç†ã§ãã¾ã™ã€‚", "æ”¯æ‰•æœŸé™ã€æœŸé™è¶…éã€æ”¯æ‰•æ¸ˆã¿ã‚’ç¢ºèªã—ã€æ”¯æ‰•æ™‚ã«å£åº§ã¨åæ”¯å°å¸³ã¸ä¸€åº¦ã ã‘åæ˜ ã§ãã¾ã™ã€‚"], ["å–å¼•å…ˆã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "è«‹æ±‚æ—¥ãƒ»æ”¯æ‰•æœŸé™ãƒ»è²»ç›®ãƒ»è«‹æ±‚é¡ã‚’æœªæ‰•ã¨ã—ã¦ç™»éŒ²ã—ã¾ã™ã€‚", "å®Ÿéš›ã®æ”¯æ‰•æ—¥ã¨å£åº§ã‚’ç¢ºèªã—ã¦æ”¯æ‰•æ¸ˆã¿ã«ã—ã¾ã™ã€‚"], "æ”¯æ‰•æ¸ˆã¿æ“ä½œã¯åæ”¯å°å¸³ã¸å®Ÿéš›ã®çµŒè²»ã‚’ä½œæˆã—ã¾ã™ã€‚äºŒé‡è¨ˆä¸Šã‚’é˜²ããŸã‚ã€åŒã˜æ”¯æ‰•ã‚’éŠ€è¡Œæ˜ç´°ã‚„æ‰‹å…¥åŠ›ã‹ã‚‰é‡è¤‡ç™»éŒ²ã—ãªã„ã§ãã ã•ã„ã€‚"),
        (("å£²æ›é‡‘", "å…¥é‡‘æ¶ˆè¾¼"), ["ç™ºè¡Œæ¸ˆã¿è«‹æ±‚æ›¸ã®æœªå…¥é‡‘é¡ã€æœŸé™è¶…éã€å…¥é‡‘å±¥æ­´ã‚’ç¢ºèªã§ãã¾ã™ã€‚", "å£åº§ã¸ã®ç›´æ¥å…¥é‡‘ã¾ãŸã¯éŠ€è¡Œæ˜ç´°ã®å…¥é‡‘ã‚’ã€è«‹æ±‚æ›¸ã¨åæ”¯å°å¸³ã¸ä¸€åº¦ã ã‘çµã³ä»˜ã‘ã‚‰ã‚Œã¾ã™ã€‚"], ["è«‹æ±‚æ›¸ã‚’ç™ºè¡Œæ¸ˆã¿ã«ã—ã¾ã™ã€‚", "å…¥é‡‘æ—¥ãƒ»å…¥é‡‘å£åº§ã‚’ç¢ºèªã™ã‚‹ã‹ã€éŠ€è¡Œæ˜ç´°ã®ä¸€è‡´å€™è£œã‚’é¸ã³ã¾ã™ã€‚", "ç¢ºèªæ¬„ã‚’å…¥ã‚Œã¦è«‹æ±‚æ›¸ã‚’å…¥é‡‘æ¸ˆã¿ã«ã—ã¾ã™ã€‚"], "åŒã˜å…¥é‡‘ã‚’æ‰‹å…¥åŠ›ã¨éŠ€è¡Œæ˜ç´°ã®ä¸¡æ–¹ã‹ã‚‰ç™»éŒ²ã—ãªã„ã§ãã ã•ã„ã€‚é‡‘é¡ãŒåŒã˜è«‹æ±‚æ›¸ãŒè¤‡æ•°ã‚ã‚‹å ´åˆã¯ã€è«‹æ±‚ç•ªå·ã¨ãŠå®¢æ§˜åã‚’å¿…ãšç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("ä»•è¨³è¨‚æ­£", "å–æ¶ˆå±¥æ­´", "åå¯¾ä»•è¨³"), ["èª¤ã£ãŸåæ”¯è¨˜éŒ²ã‚’å‰Šé™¤ã›ãšã€å…ƒè¨˜éŒ²ãƒ»åå¯¾ä»•è¨³ãƒ»è¨‚æ­£å¾Œã®è¨˜éŒ²ã‚’ä¸€çµ„ã§æ®‹ã›ã¾ã™ã€‚", "è¨‚æ­£ç†ç”±ã€å®Ÿè¡Œè€…ã€å®Ÿè¡Œæ—¥æ™‚ã‚’è¨˜éŒ²ã—ã€ä¼šè¨ˆãƒ‡ãƒ¼ã‚¿ã®å¤‰æ›´çµŒç·¯ã‚’ç¢ºèªã§ãã¾ã™ã€‚"], ["è¨‚æ­£å¯¾è±¡ã¨è¨‚æ­£æ—¥ã‚’é¸ã³ã¾ã™ã€‚", "å–æ¶ˆã®ã¿ã€ã¾ãŸã¯æ­£ã—ã„å†…å®¹ã¸è¨‚æ­£ã‚’é¸ã³ã€ç†ç”±ã‚’å…¥åŠ›ã—ã¾ã™ã€‚", "ç¢ºèªæ¬„ã‚’å…¥ã‚Œã¦ç®¡ç†è€…ãŒå®Ÿè¡Œã—ã¾ã™ã€‚"], "å…ƒè¨˜éŒ²ã¯å‰Šé™¤ã•ã‚Œã¾ã›ã‚“ã€‚è«‹æ±‚æ›¸å…¥é‡‘ã€è²·æ›é‡‘æ”¯æ‰•ã€å®šæœŸåæ”¯ãªã©ä»–æ©Ÿèƒ½ã‹ã‚‰ä½œã‚‰ã‚ŒãŸè¨˜éŒ²ã¯ã€å…ƒæ©Ÿèƒ½ã¨ã®ä¸æ•´åˆã‚’é˜²ããŸã‚ã“ã®ç”»é¢ã§ã¯è¨‚æ­£ã§ãã¾ã›ã‚“ã€‚"),
        (("çµŒè²»ç”³è«‹", "æ‰¿èªç®¡ç†"), ["å¾“æ¥­å“¡ãŒç«‹æ›¿ãƒ»æ”¯æ‰•çµŒè²»ã‚’ç”³è«‹ã—ã€é ˜åæ›¸ã‚„ãƒ¬ã‚·ãƒ¼ãƒˆã®åŸæœ¬ã‚’æ·»ä»˜ã§ãã¾ã™ã€‚", "ç®¡ç†è€…ã¯è¨¼æ†‘ã‚’ç¢ºèªã—ã¦æ‰¿èªã¾ãŸã¯å´ä¸‹ã—ã€æ‰¿èªè€…ã€æ‰¿èªæ—¥æ™‚ã€åˆ¤æ–­ã‚³ãƒ¡ãƒ³ãƒˆã‚’æ®‹ã›ã¾ã™ã€‚"], ["çµŒè²»æ—¥ãƒ»è²»ç›®ãƒ»å†…å®¹ãƒ»é‡‘é¡ã‚’å…¥åŠ›ã—ã¦ç”³è«‹ã—ã¾ã™ã€‚", "ç”³è«‹ä¸€è¦§ã‹ã‚‰PDFã¾ãŸã¯å†™çœŸã®è¨¼æ†‘ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "ç®¡ç†è€…ãŒè¨¼æ†‘ã¨æ”¯æ‰•å£åº§ã‚’ç¢ºèªã—ã€æ‰¿èªã¾ãŸã¯å´ä¸‹ã—ã¾ã™ã€‚"], "ç”³è«‹ã ã‘ã§ã¯å°å¸³ã¸è¨ˆä¸Šã•ã‚Œã¾ã›ã‚“ã€‚è¨¼æ†‘ãŒãªã„ç”³è«‹ã¯æ‰¿èªã§ããšã€æ‰¿èªå¾Œã‚‚æ‰‹å…¥åŠ›ã‚„éŠ€è¡Œæ˜ç´°ã‹ã‚‰é‡è¤‡ç™»éŒ²ã—ãªã„ã§ãã ã•ã„ã€‚"),
        (("ä¼šè¨ˆæ“ä½œãƒ­ã‚°", "ç›£æŸ»è¨¼è·¡", "ä¼šè¨ˆç›£æŸ»"), ["æœˆæ¬¡ç· ã‚ã€ä»•è¨³è¨‚æ­£ã€çµŒè²»æ‰¿èªã€å…¥å‡ºé‡‘ãªã©é‡è¦ãªä¼šè¨ˆæ“ä½œã‚’è¿½è·¡ã§ãã¾ã™ã€‚", "å®Ÿè¡Œè€…ã€æ—¥æ™‚ã€å¯¾è±¡ç•ªå·ã€å‡¦ç†å†…å®¹ã‚’ç®¡ç†è€…ã ã‘ãŒç¢ºèªãƒ»CSVå‡ºåŠ›ã§ãã¾ã™ã€‚"], ["æœŸé–“ã‚„æ“ä½œåŒºåˆ†ã§æ¤œç´¢ã—ã¾ã™ã€‚", "å¯¾è±¡ç•ªå·ã¨æ¦‚è¦ã‚’ç¢ºèªã—ã¾ã™ã€‚", "ç›£æŸ»ã‚„ç¨ç†å£«å…±æœ‰ãŒå¿…è¦ãªå ´åˆã¯CSVã‚’å®‰å…¨ã«ä¿ç®¡ã—ã¾ã™ã€‚"], "ç›£æŸ»ãƒ­ã‚°ã¯è¿½è¨˜å°‚ç”¨ã§ã™ã€‚å€‹äººæƒ…å ±ã¨å–å¼•æƒ…å ±ã‚’å«ã‚€ãŸã‚ã€CSVã¯æ¨©é™ç®¡ç†ã•ã‚ŒãŸå ´æ‰€ã§ä¿ç®¡ã—ã¦ãã ã•ã„ã€‚"),
        (("ä»•è¨³å¸³", "ç§‘ç›®åˆ¥å…ƒå¸³", "ä¼šè¨ˆå¸³ç°¿"), ["åæ”¯å°å¸³ã‚’æ—¥ä»˜é †ã®ä»•è¨³å¸³ã¨è²»ç›®åˆ¥é›†è¨ˆã§ç¢ºèªã§ãã¾ã™ã€‚", "å£åº§ã‚’æŒ‡å®šã™ã‚‹ã¨ã€ãã®å£åº§ã®å–å¼•ã¨å£åº§é–“æŒ¯æ›¿ã ã‘ã‚’æŠ½å‡ºã§ãã¾ã™ã€‚"], ["å¯¾è±¡å¹´ãƒ»æœˆã€åŒºåˆ†ã€è²»ç›®ã€å£åº§ã‚’é¸ã³ã¾ã™ã€‚", "åˆè¨ˆã¨æ˜ç´°ã‚’ç…§åˆã—ã¾ã™ã€‚", "ç¨ç†å£«å…±æœ‰ã‚„ä¿ç®¡ãŒå¿…è¦ãªå ´åˆã¯CSVã‚’å‡ºåŠ›ã—ã¾ã™ã€‚"], "ã“ã®å¸³ç°¿ã¯åæ”¯å°å¸³ã‚’åŸºç¤ã«ã—ãŸç®¡ç†å¸³ç°¿ã§ã™ã€‚æ³•å®šå¸³ç°¿ã‚„è¤‡å¼ç°¿è¨˜ã¨ã—ã¦åˆ©ç”¨ã™ã‚‹å ´åˆã¯ã€ç¨ç†å£«ã¨å‹˜å®šç§‘ç›®ãƒ»æœŸé¦–æ®‹é«˜ã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("æœˆæ¬¡ãƒ»å¹´åº¦è¤‡å¼è©¦ç®—è¡¨", "æ®‹é«˜è©¦ç®—è¡¨"), ["äº‹æ¥­å¹´åº¦ã®é–‹å§‹ã‹ã‚‰æŒ‡å®šæœˆæœ«ã¾ã§ã®è¤‡å¼ä»•è¨³ã‚’å‹˜å®šç§‘ç›®åˆ¥ã«ç¢ºèªã§ãã¾ã™ã€‚", "æœŸé¦–æ®‹é«˜ã€å½“æœŸå¢—æ¸›ã€æœŸæœ«æ®‹é«˜ã‚’å€Ÿæ–¹ãƒ»è²¸æ–¹ã®6æ¬„ã§ç…§åˆã§ãã¾ã™ã€‚"], ["äº‹æ¥­å¹´åº¦ã¨é›†è¨ˆæœˆã‚’é¸ã³ã¾ã™ã€‚", "å½“æœŸã¨æœŸæœ«ã®è²¸å€Ÿå·®é¡ãŒã‚¼ãƒ­ã§ã‚ã‚‹ã“ã¨ã‚’ç¢ºèªã—ã¾ã™ã€‚", "ç¨ç†å£«å…±æœ‰ã‚„æœˆæ¬¡ä¿ç®¡ã«ã¯CSVã‚’å‡ºåŠ›ã—ã¾ã™ã€‚"], "æœŸé¦–æ®‹é«˜ãƒ»å¹´åº¦ç¹°è¶Šãƒ»å–æ¶ˆä»•è¨³ã‚’å«ã‚€ç®¡ç†ç”¨ã®è¤‡å¼è©¦ç®—è¡¨ã§ã™ã€‚æ­£å¼ãªæ±ºç®—ãƒ»ç¨å‹™ç”³å‘Šã¯ç¨ç†å£«ã¸ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("æç›Šè¨ˆç®—æ›¸", "è²¸å€Ÿå¯¾ç…§è¡¨", "è²¡å‹™è«¸è¡¨"), ["è¤‡å¼ä»•è¨³ã®å‹˜å®šç§‘ç›®æ®‹é«˜ã‹ã‚‰ã€åç›Šãƒ»è²»ç”¨ãƒ»å½“æœŸåˆ©ç›Šã‚’æç›Šè¨ˆç®—æ›¸å½¢å¼ã§ç¢ºèªã§ãã¾ã™ã€‚", "è³‡ç”£ãƒ»è² å‚µãƒ»ç´”è³‡ç”£ã¨å½“æœŸåˆ©ç›Šã‚’è²¸å€Ÿå¯¾ç…§è¡¨å½¢å¼ã§ç¢ºèªã—ã€è²¸å€Ÿå·®é¡ã‚’æ¤œæŸ»ã§ãã¾ã™ã€‚"], ["äº‹æ¥­å¹´åº¦ã¨é›†è¨ˆæœˆã‚’é¸ã³ã¾ã™ã€‚", "æç›Šè¨ˆç®—æ›¸ã€è²¸å€Ÿå¯¾ç…§è¡¨ã€ç·å‹˜å®šå…ƒå¸³ã®æ®‹é«˜ã‚’ç…§åˆã—ã¾ã™ã€‚", "ç¨ç†å£«å…±æœ‰ã‚„æœˆæ¬¡ä¿ç®¡ã«ã¯CSVã‚’å‡ºåŠ›ã—ã¾ã™ã€‚"], "æœŸé¦–æ®‹é«˜ã€å¹´åº¦ç¹°è¶Šã€å–æ¶ˆä»•è¨³ã‚’å«ã‚€ç™»éŒ²æ¸ˆã¿è¤‡å¼ä»•è¨³ã‚’é›†è¨ˆã—ã¾ã™ã€‚æ­£å¼ãªæ±ºç®—æ›¸ãƒ»ç¨å‹™ç”³å‘Šã¯ç¨ç†å£«ã¨ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("å‹˜å®šç§‘ç›®", "è£œåŠ©ç§‘ç›®", "ç§‘ç›®ãƒã‚¹ã‚¿ãƒ¼"), ["è³‡ç”£ã€è² å‚µã€ç´”è³‡ç”£ã€åç›Šã€è²»ç”¨ã®å‹˜å®šç§‘ç›®ã¨å€Ÿæ–¹ãƒ»è²¸æ–¹ã®é€šå¸¸æ®‹é«˜ã‚’ç®¡ç†ã§ãã¾ã™ã€‚", "æ—¢å­˜ã®å…¥é‡‘ãƒ»çµŒè²»è²»ç›®ã‚’å‹˜å®šç§‘ç›®ã¸å¯¾å¿œä»˜ã‘ã€æ¬¡æ®µéšã®è¤‡å¼ç°¿è¨˜ã¸å¼•ãç¶™ã’ã¾ã™ã€‚"], ["åˆå›ã¯æ¨™æº–ç§‘ç›®ã‚’ä¸€æ‹¬ä½œæˆã—ã¾ã™ã€‚", "å¿…è¦ãªå‹˜å®šç§‘ç›®ãƒ»è£œåŠ©ç§‘ç›®ã‚’è¿½åŠ ã—ã¾ã™ã€‚", "æ—¢å­˜è²»ç›®ã®å¯¾å¿œç§‘ç›®ã‚’ç¢ºèªãƒ»å¤‰æ›´ã—ã¾ã™ã€‚"], "ä½¿ç”¨æ¸ˆã¿ç§‘ç›®ã®å‰Šé™¤ã¯è¡Œã‚ãšã€åœæ­¢ã—ã¦å±¥æ­´ã‚’ä¿æŒã—ã¦ãã ã•ã„ã€‚ç§‘ç›®åŒºåˆ†ã‚„ç¨å‹™ä¸Šã®æ‰±ã„ã¯ç¨ç†å£«ã«ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("è¤‡å¼ç°¿è¨˜", "ä»•è¨³ä¼ç¥¨", "å€Ÿæ–¹", "è²¸æ–¹"), ["å€Ÿæ–¹ã¨è²¸æ–¹ãŒä¸€è‡´ã™ã‚‹ä»•è¨³ä¼ç¥¨ã‚’ç™»éŒ²ã—ã€å‹˜å®šç§‘ç›®ãƒ»è£œåŠ©ç§‘ç›®åˆ¥ã«è¨˜éŒ²ã§ãã¾ã™ã€‚", "æ—¢å­˜ã®åæ”¯å°å¸³ã‚’ç§‘ç›®å¯¾å¿œã«å¾“ã£ã¦è¤‡å¼ä»•è¨³ã¸é‡è¤‡ãªãå¤‰æ›ã§ãã¾ã™ã€‚"], ["æ¨™æº–ç§‘ç›®ã¨è²»ç›®å¯¾å¿œã‚’å…ˆã«è¨­å®šã—ã¾ã™ã€‚", "æœªé€£æºã®åæ”¯ã‚’è¤‡å¼ä»•è¨³ã¸å¤‰æ›ã™ã‚‹ã‹ã€æ‰‹å‹•ä»•è¨³ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "èª¤ã‚Šã¯å…ƒä¼ç¥¨ã‚’å‰Šé™¤ã›ãšå–æ¶ˆä»•è¨³ã§è¨‚æ­£ã—ã¾ã™ã€‚"], "è²¸å€Ÿä¸ä¸€è‡´ã®ä»•è¨³ã¯ç™»éŒ²ã§ãã¾ã›ã‚“ã€‚ç· ã‚æ¸ˆã¿æœŸé–“ã¯å¤‰æ›´ã§ããšã€å–æ¶ˆã‚‚æ–°ã—ã„ä¼ç¥¨ã¨ã—ã¦å±¥æ­´ã‚’ä¿æŒã—ã¾ã™ã€‚"),
        (("æœŸé¦–æ®‹é«˜", "å¹´åº¦ç¹°è¶Š", "æ®‹é«˜ç¹°è¶Š"), ["åˆå¹´åº¦ã®è³‡ç”£ãƒ»è² å‚µæ®‹é«˜ã‚’è²¸å€Ÿä¸€è‡´ã®æœŸé¦–ä»•è¨³ã¨ã—ã¦ç™»éŒ²ã§ãã¾ã™ã€‚", "ç· ã‚æ¸ˆã¿å¹´åº¦ã®è³‡ç”£ãƒ»è² å‚µãƒ»ç´”è³‡ç”£æ®‹é«˜ã¨å½“æœŸæç›Šã‚’ç¿Œå¹´åº¦ã¸ä¸€åº¦ã ã‘ç¹°ã‚Šè¶Šã›ã¾ã™ã€‚"], ["åˆå¹´åº¦ã¯ç§‘ç›®ã”ã¨ã®æœŸé¦–æ®‹é«˜ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "12ã‹æœˆã‚’ç· ã‚ã¦å¹´åº¦ç· ã‚ã‚’å®Œäº†ã—ã¾ã™ã€‚", "ç¹°è¶Šå†…å®¹ã‚’ç¢ºèªã—ã€ç¿Œå¹´åº¦ã®åˆæ—¥ã«æœŸé¦–ä»•è¨³ã‚’ä½œæˆã—ã¾ã™ã€‚"], "å¹´åº¦ç¹°è¶Šå¾Œã¯å…ƒå¹´åº¦ã®ç· ã‚ã‚’è§£é™¤ã§ãã¾ã›ã‚“ã€‚è¨‚æ­£ãŒå¿…è¦ãªå ´åˆã¯ç¹°è¶Šå‰ã«è¡Œã„ã€æœŸé¦–æ®‹é«˜ã¨ç¨å‹™ä¸Šã®æ‰±ã„ã¯ç¨ç†å£«ã¸ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("ç·å‹˜å®šå…ƒå¸³", "è¤‡å¼è©¦ç®—è¡¨"), ["ç™»éŒ²æ¸ˆã¿ã®å€Ÿæ–¹ãƒ»è²¸æ–¹ä»•è¨³ã‹ã‚‰å‹˜å®šç§‘ç›®åˆ¥ã®ç·å‹˜å®šå…ƒå¸³ã‚’ä½œæˆã—ã¾ã™ã€‚", "ç§‘ç›®ã”ã¨ã®å€Ÿæ–¹åˆè¨ˆã€è²¸æ–¹åˆè¨ˆã€æœŸæœ«æ®‹é«˜ã¨å…¨ä½“ã®è²¸å€Ÿä¸€è‡´ã‚’ç¢ºèªã§ãã¾ã™ã€‚"], ["äº‹æ¥­å¹´åº¦ã‚’é¸ã³ã¾ã™ã€‚", "è¤‡å¼è©¦ç®—è¡¨ã§è²¸å€Ÿå·®é¡ãŒã‚¼ãƒ­ã§ã‚ã‚‹ã“ã¨ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å‹˜å®šç§‘ç›®ã‚’é¸ã³ã€ç›¸æ‰‹ç§‘ç›®ã¨æ®‹é«˜æ¨ç§»ã‚’ç·å‹˜å®šå…ƒå¸³ã§ç…§åˆã—ã¾ã™ã€‚"], "æœŸé¦–æ®‹é«˜ã€å¹´åº¦ç¹°è¶Šã€å–æ¶ˆä»•è¨³ã‚’å«ã‚€è¤‡å¼ä»•è¨³ãŒé›†è¨ˆå¯¾è±¡ã§ã™ã€‚ç¨ç†å£«å…±æœ‰ã«ã¯CSVã‚’å‡ºåŠ›ã—ã¦ãã ã•ã„ã€‚"),
        (("å›ºå®šè³‡ç”£", "æ¸›ä¾¡å„Ÿå´"), ["è¨­å‚™ã€æ©Ÿå™¨ã€è»Šä¸¡ãªã©ã®å–å¾—ä¾¡é¡ã€è€ç”¨å¹´æ•°ã€äº‹æ¥­ä½¿ç”¨å‰²åˆã‚’å°å¸³ç®¡ç†ã§ãã¾ã™ã€‚", "çµ‚äº†ã—ãŸäº‹æ¥­å¹´åº¦ã®å„Ÿå´é¡ã‚’é‡è¤‡ãªãè¨ˆä¸Šã—ã€æ¸›ä¾¡å„Ÿå´è²»ï¼æ¸›ä¾¡å„Ÿå´ç´¯è¨ˆé¡ã®è¤‡å¼ä»•è¨³ã‚’è‡ªå‹•ä½œæˆã§ãã¾ã™ã€‚"], ["å›ºå®šè³‡ç”£ã®å–å¾—æƒ…å ±ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "å¯¾è±¡äº‹æ¥­å¹´åº¦ã®å„Ÿå´è¦‹è¾¼é¡ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å¹´åº¦çµ‚äº†å¾Œã«ç¢ºèªãƒã‚§ãƒƒã‚¯ã‚’å…¥ã‚Œã¦è¤‡å¼ä»•è¨³ã¸è¨ˆä¸Šã—ã¾ã™ã€‚"], "è€ç”¨å¹´æ•°ã€å„Ÿå´æ–¹æ³•ã€å°‘é¡è³‡ç”£ã®æ‰±ã„ã¯ç¨å‹™åˆ¤æ–­ãŒå¿…è¦ã§ã™ã€‚è¨ˆä¸Šå‰ã«ç¨ç†å£«ã¸ç¢ºèªã—ã€ã“ã“ã§ã¯å®šé¡æ³•ã®ç®¡ç†ç”¨æ¦‚ç®—ã¨ã—ã¦æ‰±ã£ã¦ãã ã•ã„ã€‚"),
        (("ä¼šè¨ˆå¹´åº¦", "å¹´åº¦ç· ã‚", "äº‹æ¥­å¹´åº¦"), ["äº‹æ¥­å¹´åº¦ã®é–‹å§‹æœˆã‚’è¨­å®šã—ã€12ã‹æœˆåˆ†ã®æœˆæ¬¡ç· ã‚ã¨å¹´åº¦å†…ã®æœªå‡¦ç†ã‚’ç¢ºèªã§ãã¾ã™ã€‚", "å¹´åº¦ç¢ºå®šæ™‚ã®åæ”¯ãƒ»ä»¶æ•°ãƒ»å®Ÿè¡Œè€…ãƒ»æ—¥æ™‚ã‚’ä¿å­˜ã§ãã¾ã™ã€‚"], ["äº‹æ¥­å¹´åº¦ã®é–‹å§‹æœˆã‚’è¨­å®šã—ã¾ã™ã€‚", "12ã‹æœˆã™ã¹ã¦ã®æœˆæ¬¡ç· ã‚ã¨æœªå‡¦ç†0ä»¶ã‚’ç¢ºèªã—ã¾ã™ã€‚", "ç®¡ç†è€…ãŒå¹´åº¦ç· ã‚ã‚’å®Ÿè¡Œã—ã¾ã™ã€‚"], "å¹´åº¦ç· ã‚ã‚’è§£é™¤ã—ã¦ã‚‚å„æœˆã®æœˆæ¬¡ç· ã‚ã¯è§£é™¤ã•ã‚Œã¾ã›ã‚“ã€‚ä¿®æ­£ã™ã‚‹æœˆã ã‘æœˆæ¬¡ç· ã‚ã‚’è§£é™¤ã—ã€ä¿®æ­£å¾Œã«ç· ã‚ç›´ã—ã¦ãã ã•ã„ã€‚"),
        (("æ±ºç®—å‰ãƒã‚§ãƒƒã‚¯ãƒªã‚¹ãƒˆ", "æ±ºç®—æº–å‚™"), ["å¹´åº¦ç· ã‚å‰ã«æ£šå¸ã€å£²æ›ãƒ»è²·æ›ã€å›ºå®šè³‡ç”£ã€æ¶ˆè²»ç¨ã€è¨¼æ†‘ã€ç¨ç†å£«ç¢ºèªã®å®Œäº†çŠ¶æ³ã‚’è¨˜éŒ²ã§ãã¾ã™ã€‚", "è‡ªå‹•ç‚¹æ¤œé …ç›®ã¨æ‹…å½“è€…ãŒç¢ºèªã™ã‚‹é …ç›®ã‚’ä¸€ç”»é¢ã§ç…§åˆã§ãã¾ã™ã€‚"], ["å¯¾è±¡äº‹æ¥­å¹´åº¦ã‚’é¸ã³ã€è‡ªå‹•ç‚¹æ¤œã®æœªå‡¦ç†ã‚’è§£æ¶ˆã—ã¾ã™ã€‚", "åŸè³‡æ–™ã¨æ®‹é«˜ã‚’ç…§åˆã—ã€å„é …ç›®ã‚’å®Œäº†ã«ã—ã¾ã™ã€‚", "å…¨é …ç›®å®Œäº†å¾Œã«å¹´åº¦ç· ã‚ã‚’å®Ÿè¡Œã—ã¾ã™ã€‚"], "ãƒã‚§ãƒƒã‚¯ã ã‘ã§æ­£å¼ãªæ±ºç®—ãƒ»ç¨å‹™åˆ¤æ–­ãŒå®Œäº†ã™ã‚‹ã‚‚ã®ã§ã¯ã‚ã‚Šã¾ã›ã‚“ã€‚æ ¹æ‹ è³‡æ–™ã‚’ä¿å­˜ã—ã€å¿…è¦ãªé …ç›®ã¯ç¨ç†å£«ã¸ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("æœˆæ¬¡ç· ã‚", "ä¼šè¨ˆæœŸé–“ãƒ­ãƒƒã‚¯"), ["æœˆã”ã¨ã®å…¥é‡‘ãƒ»çµŒè²»ã€è¨¼æ†‘ã€å£åº§å‰²å½“ã®çŠ¶æ…‹ã‚’ç‚¹æ¤œã§ãã¾ã™ã€‚", "ç· ã‚ãŸæœˆã¯å°å¸³ç™»éŒ²ãƒ»å£åº§å‰²å½“ãƒ»å£åº§æŒ¯æ›¿ã‚’ãƒ­ãƒƒã‚¯ã—ã€ç¢ºå®šå¾Œã®èª¤å¤‰æ›´ã‚’é˜²ãã¾ã™ã€‚"], ["å¯¾è±¡æœˆã‚’é¸ã³ã€æœªå‰²å½“ã¨è¨¼æ†‘æœªä¿ç®¡ã‚’ç¢ºèªã—ã¾ã™ã€‚", "é›†è¨ˆé¡ã‚’ç¢ºèªã—ã¦ç®¡ç†è€…ãŒæœˆæ¬¡ç· ã‚ã‚’å®Ÿè¡Œã—ã¾ã™ã€‚", "ä¿®æ­£ãŒå¿…è¦ãªå ´åˆã ã‘ç†ç”±ã‚’ç¢ºèªã—ã¦ç· ã‚ã‚’è§£é™¤ã—ã¾ã™ã€‚"], "ç· ã‚è§£é™¤å¾Œã«ä¿®æ­£ã—ãŸå ´åˆã¯ã€å†åº¦é›†è¨ˆã‚’ç¢ºèªã—ã¦ç· ã‚ç›´ã—ã¦ãã ã•ã„ã€‚"),
        (("ä¼šè¨ˆãƒ»è¨¼æ†‘ä¸€æ‹¬å‡ºåŠ›",), ["æŒ‡å®šå¹´ã®åæ”¯å°å¸³ãƒ»è«‹æ±‚æ›¸ãƒ»åŸä¾¡é…è³¦ã‚’CSVã§å‡ºåŠ›ã§ãã¾ã™ã€‚", "é ˜åæ›¸ãƒ»è¨¼æ†‘åŸæœ¬ã¨æ”¹ã–ã‚“ç¢ºèªç”¨ã®æ•´åˆæ€§æƒ…å ±ã‚’ZIPã«ã¾ã¨ã‚ã‚‰ã‚Œã¾ã™ã€‚"], ["å‡ºåŠ›ã™ã‚‹å¹´ã‚’æŒ‡å®šã—ã¾ã™ã€‚", "ç®¡ç†è€…ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã¨å®‰å…¨ä¿ç®¡ã®ç¢ºèªã‚’å…¥åŠ›ã—ã¾ã™ã€‚", "ãƒ€ã‚¦ãƒ³ãƒ­ãƒ¼ãƒ‰ã—ãŸZIPã‚’æ¨©é™ç®¡ç†ã•ã‚ŒãŸå ´æ‰€ã¸ä¿å­˜ã—ã¾ã™ã€‚"], "ZIPã«ã¯å€‹äººæƒ…å ±ãƒ»å–å¼•æƒ…å ±ãƒ»è¨¼æ†‘åŸæœ¬ãŒå«ã¾ã‚Œã¾ã™ã€‚ãƒ¡ãƒ¼ãƒ«ã¸ç›´æ¥æ·»ä»˜ã›ãšã€å®‰å…¨ãªå…±æœ‰æ–¹æ³•ã‚’åˆ©ç”¨ã—ã¦ãã ã•ã„ã€‚"),
        (("é ˜åæ›¸", "è¨¼æ†‘"), ["åæ”¯å°å¸³ã®è¨˜éŒ²ã¸é ˜åæ›¸ãƒ»è«‹æ±‚æ›¸ã®PDFã‚„å†™çœŸã‚’ç´ã¥ã‘ã¦ä¿ç®¡ã§ãã¾ã™ã€‚", "ç™ºè¡Œå…ƒãƒ»æ›¸é¡ç•ªå·ãƒ»å°å¸³é‡‘é¡ã¨åŸæœ¬ã‚’ã¾ã¨ã‚ã¦ç¢ºèªã§ãã¾ã™ã€‚"], ["ç´ã¥ã‘ã‚‹å°å¸³è¨˜éŒ²ã¨æ›¸é¡ç¨®åˆ¥ã‚’é¸ã³ã¾ã™ã€‚", "ç™ºè¡Œå…ƒãƒ»æ›¸é¡ç•ªå·ã‚’å…¥åŠ›ã—ã€PDFã¾ãŸã¯å†™çœŸã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "ä¸€è¦§ã‹ã‚‰æ›¸é¡ã‚’é–‹ãã€å°å¸³ã®æ—¥ä»˜ãƒ»é‡‘é¡ã¨ç…§åˆã—ã¾ã™ã€‚"], "æ›¸é¡ã«ã¯å€‹äººæƒ…å ±ã‚„å£åº§æƒ…å ±ãŒå«ã¾ã‚Œã‚‹å ´åˆãŒã‚ã‚Šã¾ã™ã€‚å¿…è¦ãªæ‹…å½“è€…ã ã‘ãŒé–²è¦§ã—ã€åŸæœ¬ã‚‚æ³•å®šæœŸé–“ã«å¾“ã£ã¦ä¿ç®¡ã—ã¦ãã ã•ã„ã€‚"),
        (("åŸä¾¡", "åˆ©ç›Š", "æ¡ç®—"), ["çµŒè²»ã‚’ç‰¹å®šã®çŠ¬ã¾ãŸã¯å‡ºç”£å›ã¸é…è³¦ã—ã€å£²ä¸Šãƒ»åŸä¾¡ãƒ»åˆ©ç›Šã‚’ç¢ºèªã§ãã¾ã™ã€‚", "å‡ºç”£å›ã”ã¨ã®è²©å£²äºˆå®šé¡ã€å…¥é‡‘é¡ã€æœªå…¥é‡‘é¡ã€åŸä¾¡ã‚’æ¯”è¼ƒã§ãã¾ã™ã€‚"], ["æœªé…è³¦ã®çµŒè²»ã‹ã‚‰å¯¾è±¡è¨˜éŒ²ã‚’é¸ã³ã¾ã™ã€‚", "å¯¾è±¡ã®çŠ¬ã¾ãŸã¯å‡ºç”£å›ã®ã©ã¡ã‚‰ã‹ä¸€æ–¹ã¨é…è³¦é¡ã‚’æŒ‡å®šã—ã¾ã™ã€‚", "å‡ºç”£å›åˆ¥ã®åˆ©ç›Šã¨æœªé…è³¦çµŒè²»ã‚’ç¢ºèªã—ã¾ã™ã€‚"], "åˆ©ç›Šã¯ç™»éŒ²æ¸ˆã¿ã®è²©å£²ä¾¡æ ¼ãƒ»å…¥é‡‘é¡ãƒ»é…è³¦æ¸ˆã¿çµŒè²»ã‹ã‚‰ç®—å‡ºã—ãŸç®¡ç†ä¸Šã®æ¦‚ç®—ã§ã™ã€‚ç¨å‹™ä¸Šã®åˆ©ç›Šã¯ç¨ç†å£«ã¸ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("åæ”¯", "çµŒè²»", "åŸä¾¡", "è«‹æ±‚"), ["çŠ¬èˆã”ã¨ã®å…¥é‡‘ã¨çµŒè²»ã‚’è¨˜éŒ²ã—ã€æœˆæ¬¡ã®åæ”¯ã‚’ç¢ºèªã§ãã¾ã™ã€‚", "è²»ç›®åˆ¥ã®æ”¯å‡ºã¨è²©å£²ç®¡ç†ä¸Šã®æœªå…¥é‡‘é¡ã‚’ã¾ã¨ã‚ã¦æŠŠæ¡ã§ãã¾ã™ã€‚"], ["è¡¨ç¤ºæœˆã¨åŒºåˆ†ã‚’é¸ã‚“ã§è¨˜éŒ²ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å…¥é‡‘ã¾ãŸã¯çµŒè²»ã®æ—¥ä»˜ãƒ»è²»ç›®ãƒ»é‡‘é¡ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "æœˆæ¬¡æ®‹é«˜ã¨è²©å£²æœªå…¥é‡‘é¡ã‚’ç¢ºèªã—ã¾ã™ã€‚"], "ç¨å‹™ç”³å‘Šç”¨ã®ä¼šè¨ˆå¸³ç°¿ã‚’ä»£æ›¿ã™ã‚‹ã‚‚ã®ã§ã¯ã‚ã‚Šã¾ã›ã‚“ã€‚é ˜åæ›¸ãƒ»è«‹æ±‚æ›¸ã®åŸæœ¬ã¨ç…§åˆã—ã€ç¨ç†å£«ã¸ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("çŠ¬ãƒ»è¡€çµ±æ›¸", "çŠ¬ä¸€è¦§", "åœ¨ç±çŠ¬", "è¦ªçŠ¬", "è²©å£²çŠ¬", "è­²æ¸¡æ¸ˆ", "å¤–éƒ¨çŠ¬"), ["çŠ¬ã®åŸºæœ¬æƒ…å ±ã€åœ¨ç±åŒºåˆ†ã€å†™çœŸã€è¡€çµ±æ›¸ã‚’ç®¡ç†ã§ãã¾ã™ã€‚", "è¦ªçŠ¬ãƒ»ä»”çŠ¬ãƒ»è²©å£²çŠ¬ãƒ»è­²æ¸¡æ¸ˆçŠ¬ãªã©ã®çŠ¶æ…‹ã‚’ç¢ºèªã§ãã¾ã™ã€‚"], ["å¯¾è±¡çŠ¬ã‚’æ¤œç´¢ã¾ãŸã¯ä¸€è¦§ã‹ã‚‰é¸ã³ã¾ã™ã€‚", "ç™»éŒ²ãƒ»ç·¨é›†ç”»é¢ã§å¿…è¦é …ç›®ã‚’å…¥åŠ›ã—ã¾ã™ã€‚", "ä¿å­˜å¾Œã«åå‰ã€æ€§åˆ¥ã€ç”Ÿå¹´æœˆæ—¥ã€åœ¨ç±çŠ¶æ…‹ã‚’ç¢ºèªã—ã¾ã™ã€‚"], "è²©å£²ãƒ»è­²æ¸¡ãƒ»æ­»äº¡ãªã©ã®çŠ¶æ…‹å¤‰æ›´ã¯ã€ä¸€è¦§è¡¨ç¤ºã‚„å¸³ç¥¨ã«å½±éŸ¿ã—ã¾ã™ã€‚å¯¾è±¡çŠ¬ã‚’ç¢ºèªã—ã¦æ“ä½œã—ã¦ãã ã•ã„ã€‚"),
        (("è²©å£²", "é¡§å®¢", "å•†è«‡", "å¥‘ç´„", "å¼•æ¸¡"), ["é¡§å®¢ã€å•†è«‡ã€å¥‘ç´„ã€è²©å£²ãƒ»å¼•æ¸¡ã—çŠ¶æ³ã‚’ç®¡ç†ã§ãã¾ã™ã€‚", "é€²æ—ç¢ºèªã¨å¿…è¦æ›¸é¡ã®ä½œæˆãƒ»å‡ºåŠ›ã«åˆ©ç”¨ã§ãã¾ã™ã€‚"], ["é¡§å®¢ã¨å¯¾è±¡çŠ¬ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å•†è«‡ã‚„å¥‘ç´„ã®é€²æ—ã‚’å…¥åŠ›ã—ã¾ã™ã€‚", "å¼•æ¸¡ã—å‰ã«å¥‘ç´„å†…å®¹ã¨å¿…è¦æ›¸é¡ã‚’ç¢ºèªã—ã¾ã™ã€‚"], "å€‹äººæƒ…å ±ã‚’å«ã‚€ãŸã‚ã€é–²è¦§ãƒ»å‡ºåŠ›ã—ãŸãƒ‡ãƒ¼ã‚¿ã®å–æ‰±ã„ã«æ³¨æ„ã—ã¦ãã ã•ã„ã€‚"),
        (("æ³•ä»¤", "è¡Œæ”¿", "å¸³ç°¿", "å±Šå‡º"), ["å‹•ç‰©å–æ‰±æ¥­ã«å¿…è¦ãªè¨˜éŒ²ã‚„è¡Œæ”¿æ›¸é¡ã‚’ç¢ºèªãƒ»ä½œæˆã§ãã¾ã™ã€‚", "ç™»éŒ²æƒ…å ±ã‚’ã‚‚ã¨ã«å¸³ç¥¨ã‚’å‡ºåŠ›ã§ãã¾ã™ã€‚"], ["å¯¾è±¡æœŸé–“ã¨æå‡ºå…ˆã‚’ç¢ºèªã—ã¾ã™ã€‚", "ä¸è¶³ã—ã¦ã„ã‚‹æƒ…å ±ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "å‡ºåŠ›å¾Œã«åŸç°¿ãƒ»æå‡ºè¦é ˜ã¨ç…§åˆã—ã¾ã™ã€‚"], "è‡ªæ²»ä½“ã”ã¨ã«æ§˜å¼ã‚„æå‡ºè¦ä»¶ãŒç•°ãªã‚‹å ´åˆãŒã‚ã‚Šã¾ã™ã€‚æå‡ºå‰ã«ç®¡è½„è¡Œæ”¿æ©Ÿé–¢ã¸ç¢ºèªã—ã¦ãã ã•ã„ã€‚"),
        (("FAMILY", "ã‚ªãƒ¼ãƒŠãƒ¼", "ãƒ¡ãƒƒã‚»ãƒ¼ã‚¸", "ã‚¿ã‚¤ãƒ ãƒ©ã‚¤ãƒ³", "ãŠçŸ¥ã‚‰ã›"), ["ã‚ªãƒ¼ãƒŠãƒ¼ã¨ã®é€£æºã€æƒ…å ±å…±æœ‰ã€äº¤æµæ©Ÿèƒ½ã‚’ç®¡ç†ã§ãã¾ã™ã€‚", "ãŠçŸ¥ã‚‰ã›ã€ãƒ¡ãƒƒã‚»ãƒ¼ã‚¸ã€æŠ•ç¨¿ã€åˆ©ç”¨çŠ¶æ³ã‚’ç¢ºèªã§ãã¾ã™ã€‚"], ["å¯¾è±¡ã®ã‚ªãƒ¼ãƒŠãƒ¼ã¾ãŸã¯æ„›çŠ¬ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å…¬é–‹ç¯„å›²ã¨é€šçŸ¥å…ˆã‚’ç¢ºèªã—ã¦å†…å®¹ã‚’ç™»éŒ²ã—ã¾ã™ã€‚", "é€ä¿¡ãƒ»å…¬é–‹å¾Œã®è¡¨ç¤ºã‚’ç¢ºèªã—ã¾ã™ã€‚"], "ãƒ¡ãƒƒã‚»ãƒ¼ã‚¸ã‚„æŠ•ç¨¿ã«ã¯å€‹äººæƒ…å ±ãƒ»éå…¬é–‹æƒ…å ±ã‚’è¨˜è¼‰ã—ã™ããªã„ã‚ˆã†æ³¨æ„ã—ã¦ãã ã•ã„ã€‚"),
        (("ãƒãƒƒã‚¯ã‚¢ãƒƒãƒ—", "ãƒ‡ãƒ¼ã‚¿å‡ºåŠ›"), ["çŠ¬èˆãƒ‡ãƒ¼ã‚¿ã®å‡ºåŠ›ã€ãƒãƒƒã‚¯ã‚¢ãƒƒãƒ—ã€æ•´åˆæ€§ç¢ºèªãŒã§ãã¾ã™ã€‚", "ä¿ç®¡ã‚„éšœå®³æ™‚ã®å¾©æ—§æº–å‚™ã«åˆ©ç”¨ã§ãã¾ã™ã€‚"], ["å‡ºåŠ›å¯¾è±¡ã¨å½¢å¼ã‚’ç¢ºèªã—ã¾ã™ã€‚", "ãƒ•ã‚¡ã‚¤ãƒ«ã‚’ä½œæˆã—ã€å®‰å…¨ãªå ´æ‰€ã¸ä¿ç®¡ã—ã¾ã™ã€‚", "å®šæœŸçš„ã«æ¤œè¨¼æ©Ÿèƒ½ã§ãƒ•ã‚¡ã‚¤ãƒ«ã®æ•´åˆæ€§ã‚’ç¢ºèªã—ã¾ã™ã€‚"], "å‡ºåŠ›ãƒ•ã‚¡ã‚¤ãƒ«ã«ã¯å€‹äººæƒ…å ±ãŒå«ã¾ã‚Œã¾ã™ã€‚å…±æœ‰å…ˆã¨ä¿ç®¡å ´æ‰€ã‚’é™å®šã—ã¦ãã ã•ã„ã€‚"),
    ]
    abilities = [f"ã€Œ{page_name}ã€ã«é–¢ã™ã‚‹æƒ…å ±ã‚’ç¢ºèªã§ãã¾ã™ã€‚", "è¡¨ç¤ºã•ã‚Œã¦ã„ã‚‹å…¥åŠ›æ¬„ã‚„ãƒœã‚¿ãƒ³ã‹ã‚‰ã€æ¨©é™ã«å¿œã˜ãŸç™»éŒ²ãƒ»æ¤œç´¢ãƒ»å¤‰æ›´ãŒã§ãã¾ã™ã€‚"]
    steps = ["ç”»é¢ã®å¯¾è±¡ã¨ç¾åœ¨ã®çŠ¶æ…‹ã‚’ç¢ºèªã—ã¾ã™ã€‚", "å¿…è¦ãªé …ç›®ã‚’å…¥åŠ›ã¾ãŸã¯é¸æŠã—ã¦æ“ä½œã—ã¾ã™ã€‚", "å®Œäº†ãƒ¡ãƒƒã‚»ãƒ¼ã‚¸ã¨æ›´æ–°å¾Œã®å†…å®¹ã‚’ç¢ºèªã—ã¾ã™ã€‚"]
    caution = "æ“ä½œã§ãã‚‹å†…å®¹ã¯ã‚¢ã‚«ã‚¦ãƒ³ãƒˆæ¨©é™ã«ã‚ˆã‚Šç•°ãªã‚Šã¾ã™ã€‚é‡è¦ãªå¤‰æ›´ã¯å¯¾è±¡ã¨å†…å®¹ã‚’ç¢ºèªã—ã¦ã‹ã‚‰å®Ÿè¡Œã—ã¦ãã ã•ã„ã€‚"
    for keywords, specific_abilities, specific_steps, specific_caution in guides:
        if any(keyword in page_name for keyword in keywords):
            abilities, steps, caution = specific_abilities, specific_steps, specific_caution
            break
    ability_items = "".join(f"<li>{html.escape(item)}</li>" for item in abilities)
    step_items = "".join(f"<li>{html.escape(item)}</li>" for item in steps)
    return f'''<details class="page-guide"><summary>ã“ã®ç”»é¢ã®ä½¿ã„æ–¹ã‚’è¦‹ã‚‹</summary><div class="page-guide-grid"><section><h3>ã“ã®ç”»é¢ã§ã§ãã‚‹ã“ã¨</h3><ul>{ability_items}</ul></section><section><h3>åŸºæœ¬çš„ãªä½¿ã„æ–¹</h3><ol>{step_items}</ol></section><section><h3>æ“ä½œä¸Šã®æ³¨æ„</h3><p>{html.escape(caution)}</p></section></div></details>'''


def layout(title: str, body: str, user: User | None = None, owner_mode: bool = False, notification_count: int = 0) -> str:
    nav = ""
    body_class = "owner-view" if user and owner_mode else ("authenticated" if user else "guest")
    if user and owner_mode:
        notification_badge = f'<span class="nav-count">{notification_count}</span>' if notification_count else ""
        nav = f'''<aside class="owner-header"><a class="owner-brand" href="/family"><strong>ESTRELLA</strong><small>FAMILY</small></a>
        <nav><p class="owner-nav-label">ãƒ›ãƒ¼ãƒ </p><a href="/family"><span>âŒ‚</span>ã†ã¡ã®å­</a><a href="/family/notifications"><span>â—</span>é€šçŸ¥{notification_badge}</a>
        <p class="owner-nav-label">äº¤æµ</p><a href="/family/messages"><span>âœ‰</span>ãƒ¡ãƒƒã‚»ãƒ¼ã‚¸</a><a href="/family/announcements"><span>â—‡</span>ãŠçŸ¥ã‚‰ã›</a><a href="/family/timeline"><span>â–¦</span>ã‚¿ã‚¤ãƒ ãƒ©ã‚¤ãƒ³</a><a href="/family/anniversaries"><span>â™¡</span>è¨˜å¿µæ—¥</a><a href="/family/relatives"><span>â™¢</span>å…„å¼Ÿãƒ»è¦ªæˆšçŠ¬</a><a href="/family/kennel"><span>â™§</span>çŠ¬èˆFAMILYä¼š</a>
        <p class="owner-nav-label">è¨­å®š</p><a href="/family/profile"><span>â™™</span>ãƒ—ãƒ­ãƒ•ã‚£ãƒ¼ãƒ«è¨­å®š</a><a href="/family/notification-settings"><span>â—</span>é€šçŸ¥è¨­å®š</a><a href="/family/line"><span>LINE</span>LINEé€£æº</a><a href="/family/consents"><span>âœ“</span>è¦ç´„ãƒ»åŒæ„</a><a href="/family/devices"><span>â–£</span>ã‚¢ãƒ—ãƒªãƒ»ç«¯æœ«</a><a href="/family/account"><span>â†ª</span>é€€ä¼šãƒ»å¼•ç¶™ã</a></nav>
        <div class="owner-account"><span>{html.escape(user.name)}</span><form method="post" action="/logout"><button>ãƒ­ã‚°ã‚¢ã‚¦ãƒˆ</button></form></div></aside>'''
    elif user:
        platform_link = '<a href="/platform/tenants"><span>â—†</span>ãƒ†ãƒŠãƒ³ãƒˆç®¡ç†</a>' if user.platform_admin else ""
        nav = f'''<aside class="sidebar">
        <a class="brand" href="/dashboard"><span class="brand-logo-wrap"><img class="brand-logo" src="https://estrella.dog/wp-content/uploads/2025/10/logo-1.svg" alt="ESTRELLA ãƒ­ã‚´"></span><span><strong>ESTRELLA</strong><small>Breeder Management</small></span></a>
        <nav aria-label="ç®¡ç†ãƒ¡ãƒ‹ãƒ¥ãƒ¼">
          <a class="nav-home" href="/dashboard"><span>âŒ‚</span>ç®¡ç†ç”»é¢TOP</a>
          <details class="nav-group" data-nav-group="daily"><summary><span>â–¦</span>æ—¥å¸¸æ¥­å‹™</summary><div class="nav-group-links">
            <a href="/family"><span>â™¢</span>FAMILY</a><a href="/modules/todo"><span>âœ“</span>Todoãƒªã‚¹ãƒˆ</a><a href="/modules/calendar"><span>â–¦</span>ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼</a>
          </div></details>
          <details class="nav-group" data-nav-group="dogs"><summary><span>ğŸ•</span>çŠ¬ã®ç®¡ç†</summary><div class="nav-group-links">
            <a href="/modules/resident-dogs"><span>ğŸ•</span>åœ¨ç±çŠ¬ä¸€è¦§</a><a href="/modules/dog-list/puppy"><span>â—Œ</span>ä»”çŠ¬ä¸€è¦§</a><a href="/modules/sale-dogs"><span>Â¥</span>è²©å£²çŠ¬ä¸€è¦§</a><a href="/modules/transferred-dogs"><span>â†—</span>è­²æ¸¡æ¸ˆä¸€è¦§</a><a href="/modules/dog-list/parent"><span>â™™</span>è¦ªçŠ¬ä¸€è¦§</a><a href="/modules/dog-list/external"><span>â—‡</span>å¤–éƒ¨çŠ¬ä¸€è¦§</a>
          </div></details>
          <details class="nav-group" data-nav-group="breeding"><summary><span>â™¡</span>ç¹æ®–ã¨è¡€çµ±</summary><div class="nav-group-links">
            <a href="/modules/breeding"><span>â™¡</span>ãƒ’ãƒ¼ãƒˆãƒ»äº¤é…ç®¡ç†</a><a href="/modules/births"><span>âœ¦</span>å‡ºç”£ç®¡ç†</a><a href="/modules/genetics"><span>âŒ˜</span>éºä¼å­ãƒ»äº¤é…åˆ†æ</a><a href="/modules/dogs"><span>â—</span>çŠ¬ãƒ»è¡€çµ±æ›¸ç®¡ç†</a>
          </div></details>
          <details class="nav-group" data-nav-group="business"><summary><span>ï¼‹</span>å¥åº·ã¨è²©å£²</summary><div class="nav-group-links">
            <a href="/modules/health"><span>ï¼‹</span>å¥åº·ç®¡ç†</a><a href="/modules/sales"><span>Â¥</span>è²©å£²ç®¡ç†</a><a href="/modules/finance/reports"><span>â–¥</span>çµŒå–¶åç›Š</a><a href="/modules/finance/budgets"><span>â—</span>äºˆç®—ãƒ»äºˆå®Ÿæ¯”è¼ƒ</a><a href="/modules/finance/cashflow"><span>â†—</span>è³‡é‡‘ç¹°ã‚Š</a><a href="/modules/finance/receivables"><span>ï¿¥</span>å£²æ›ãƒ»å…¥é‡‘</a><a href="/modules/finance/payables"><span>ï¿¥</span>è²·æ›ãƒ»æ”¯æ‰•</a><a href="/modules/finance/expense-requests"><span>âœ“</span>çµŒè²»ç”³è«‹</a><a href="/modules/finance/accounts"><span>â—‡</span>å£åº§ãƒ»ç¾é‡‘</a><a href="/modules/finance/statements"><span>â‡„</span>æ˜ç´°å–è¾¼</a><a href="/modules/finance/rules"><span>âš™</span>ä»•è¨³å€™è£œ</a><a href="/modules/finance/tax"><span>ï¼…</span>æ¶ˆè²»ç¨ç¢ºèª</a><a href="/modules/finance/corrections"><span>â†¶</span>ä»•è¨³è¨‚æ­£</a><a href="/modules/finance/audit"><span>â—‰</span>ä¼šè¨ˆç›£æŸ»</a><a href="/modules/finance/chart-accounts"><span>âŒ˜</span>å‹˜å®šç§‘ç›®</a><a href="/modules/finance/journals"><span>â‡†</span>è¤‡å¼ä»•è¨³</a><a href="/modules/finance/opening-balances"><span>â†¦</span>æœŸé¦–ãƒ»ç¹°è¶Š</a><a href="/modules/finance/books"><span>â–¥</span>ä»•è¨³å¸³ãƒ»å…ƒå¸³</a><a href="/modules/finance/trial-balance"><span>â–¦</span>è©¦ç®—è¡¨</a><a href="/modules/finance/statements-report"><span>â–¤</span>è²¡å‹™è«¸è¡¨</a><a href="/modules/finance/fixed-assets"><span>â–£</span>å›ºå®šè³‡ç”£</a><a href="/modules/finance/year-end"><span>âœ“</span>å¹´åº¦ç· ã‚</a><a href="/modules/finance/year-end-checklist"><span>â˜‘</span>æ±ºç®—å‰ç¢ºèª</a><a href="/modules/finance/reconciliation"><span>â‰’</span>æ®‹é«˜ç…§åˆ</a><a href="/modules/finance/closing"><span>âœ“</span>æœˆæ¬¡ç· ã‚</a><a href="/modules/finance/recurring"><span>â†»</span>å®šæœŸåæ”¯</a><a href="/modules/finance"><span>â–¤</span>åæ”¯ãƒ»çµŒè²»å°å¸³</a><a href="/modules/finance/documents"><span>â–£</span>é ˜åæ›¸ãƒ»è¨¼æ†‘</a><a href="/modules/finance/export"><span>â‡©</span>ä¼šè¨ˆä¸€æ‹¬å‡ºåŠ›</a><a href="/modules/costs"><span>â–³</span>åŸä¾¡ãƒ»åˆ©ç›Šç®¡ç†</a><a href="/modules/invoices"><span>â–¡</span>è«‹æ±‚æ›¸ç®¡ç†</a><a href="/modules/legal"><span>â–¤</span>æ³•ä»¤ãƒ»è¡Œæ”¿æ›¸é¡</a>
          </div></details>
          <details class="nav-group" data-nav-group="family-admin"><summary><span>â™¢</span>FAMILYç®¡ç†</summary><div class="nav-group-links">
            <a href="/family/announcements/manage"><span>â—‡</span>FAMILYãŠçŸ¥ã‚‰ã›</a><a href="/family/messages/manage"><span>âœ‰</span>ãƒ¡ãƒƒã‚»ãƒ¼ã‚¸ç®¡ç†</a><a href="/family/timeline/comments/manage"><span>ğŸ’¬</span>ã‚³ãƒ¡ãƒ³ãƒˆç®¡ç†</a><a href="/family/timeline/reports/manage"><span>!</span>ã‚¿ã‚¤ãƒ ãƒ©ã‚¤ãƒ³é€šå ±</a><a href="/family/safety/reports/manage"><span>âš‘</span>ãƒ—ãƒ­ãƒ•ã‚£ãƒ¼ãƒ«ãƒ»ãƒ¡ãƒƒã‚»ãƒ¼ã‚¸é€šå ±</a><a href="/family/restrictions/manage"><span>âŠ˜</span>FAMILYåˆ©ç”¨åœæ­¢</a><a href="/family/dashboard/manage"><span>â–¥</span>FAMILYé›†è¨ˆ</a><a href="/family/withdrawals/manage"><span>â†ª</span>é€€ä¼šç”³è«‹</a><a href="/family/terms/manage"><span>âœ“</span>è¦ç´„ãƒ»åŒæ„ç®¡ç†</a><a href="/family/line/manage"><span>LINE</span>LINEå…¬å¼è¨­å®š</a><a href="/family/backups/manage"><span>â‡©</span>ãƒ‡ãƒ¼ã‚¿å‡ºåŠ›</a>
          </div></details>
          <details class="nav-group" data-nav-group="system"><summary><span>âš™</span>ã‚·ã‚¹ãƒ†ãƒ è¨­å®š</summary><div class="nav-group-links">
            <a href="/admin/users"><span>â™™</span>ãƒ¦ãƒ¼ã‚¶ãƒ¼ç®¡ç†</a><a href="/admin/password-resets"><span>âŒ</span>ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰å†è¨­å®š</a><a href="/admin/notification-deliveries"><span>â—</span>é€šçŸ¥é…ä¿¡å±¥æ­´</a><a href="/admin/email-deliveries"><span>âœ‰</span>ãƒ¡ãƒ¼ãƒ«é€ä¿¡å±¥æ­´</a><a href="/admin/operations"><span>â—‰</span>é‹ç”¨ç›£è¦–</a>{platform_link}
          </div></details>
        </nav>
        <div class="sidebar-user"><div class="avatar">{html.escape(user.name[:1])}</div><div><strong>{html.escape(user.name)}</strong><small>{"é‹å–¶ç®¡ç†è€…" if user.platform_admin else "ãƒ¦ãƒ¼ã‚¶ãƒ¼"}</small></div><form method="post" action="/logout"><button title="ãƒ­ã‚°ã‚¢ã‚¦ãƒˆ">â†ª</button></form></div>
        </aside>'''
    content = body
    if user and 'class="page-guide"' not in content:
        guide = page_usage_guide(title)
        heading_end = content.find("</h1>")
        content = content[:heading_end + 5] + guide + content[heading_end + 5:] if heading_end >= 0 else guide + content
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--wine:#704454;--rose:#b66f7c;--rose-light:#ead0d5;--cream:#faf6f3;--paper:#fffdfb;--ink:#3f3036;--muted:#816f76;--line:#eadfe1;--green:#718b75;--danger:#a94f55}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--cream);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;line-height:1.55}}.sidebar{{position:fixed;inset:0 auto 0 0;width:260px;background:linear-gradient(180deg,#68404f 0%,#55333f 100%);color:#fff;display:flex;flex-direction:column;z-index:10;box-shadow:6px 0 24px #4b26331a}}.brand{{height:84px;display:flex;align-items:center;gap:13px;padding:18px 22px;color:#fff;text-decoration:none;border-bottom:1px solid #ffffff1f}}.brand-mark{{display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:#f0d8dc;color:var(--wine);font-family:Georgia,serif;font-size:25px}}.brand strong{{display:block;letter-spacing:1.8px;font-family:Georgia,serif}}.brand small,.sidebar-user small{{display:block;color:#ead5da;font-size:11px}}.sidebar nav{{padding:12px 13px;overflow-y:auto;flex:1}}.sidebar nav a{{display:flex;align-items:center;gap:12px;color:#f8eef1;text-decoration:none;padding:10px 13px;border-radius:10px;font-size:14px;margin:2px 0}}.sidebar nav a:hover,.sidebar nav a.active{{background:#ffffff1c;color:#fff}}.sidebar nav a span{{width:20px;text-align:center;color:#eac3cb}}.nav-home{{font-weight:750;border-bottom:1px solid #ffffff1c;margin-bottom:10px!important}}.nav-group{{margin:5px 0;border:1px solid #ffffff16;border-radius:11px;overflow:hidden;background:#ffffff06}}.nav-group summary{{display:flex;align-items:center;gap:11px;padding:11px 13px;cursor:pointer;list-style:none;font-size:14px;font-weight:700;color:#fff;user-select:none}}.nav-group summary::-webkit-details-marker{{display:none}}.nav-group summary:after{{content:"ï¼‹";margin-left:auto;color:#dfc5cb;font-size:15px}}.nav-group[open] summary{{background:#ffffff12}}.nav-group[open] summary:after{{content:"âˆ’"}}.nav-group summary>span{{width:20px;text-align:center;color:#eac3cb}}.nav-group-links{{padding:4px 6px 7px;background:#321e2638}}.sidebar .nav-group-links a{{padding:8px 10px;font-size:13px}}.nav-label{{margin:14px 12px 5px;color:#cbaeb5;font-size:10px;letter-spacing:1.5px;font-weight:700}}.sidebar-user{{display:flex;align-items:center;gap:10px;padding:15px;border-top:1px solid #ffffff1f;background:#452934}}.sidebar-user .avatar{{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:#e7c6cc;color:var(--wine);font-weight:700}}.sidebar-user strong{{display:block;max-width:125px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}}.sidebar-user form{{margin-left:auto}}.sidebar-user button{{margin:0;padding:8px;background:transparent;color:#fff;font-size:18px}}main{{max-width:1280px;margin-left:260px;padding:38px 42px}}.card{{background:var(--paper);padding:34px;border:1px solid #f1e7e8;border-radius:20px;box-shadow:0 10px 35px #63404c0d}}h1{{margin:0 0 22px;font-size:28px;letter-spacing:.02em}}h2{{margin-top:34px;padding-bottom:8px;border-bottom:1px solid var(--line);font-size:20px}}label{{display:block;margin:15px 0 6px;font-size:13px;font-weight:650;color:#665159}}input,select,textarea{{width:100%;padding:11px 13px;border:1px solid #dacdd0;border-radius:10px;background:#fff;font-size:15px;color:var(--ink);outline:none}}input:focus,select:focus,textarea:focus{{border-color:var(--rose);box-shadow:0 0 0 3px #b66f7c18}}textarea{{min-height:84px;resize:vertical}}button,.button{{display:inline-block;margin-top:17px;padding:11px 18px;border:0;border-radius:10px;background:var(--rose);color:#fff;text-decoration:none;font-weight:650;cursor:pointer;box-shadow:0 4px 12px #b66f7c28}}button:hover,.button:hover{{filter:brightness(.95)}}.secondary{{background:#89747b}}.danger{{background:var(--danger)}}.success{{background:var(--green)}}.inline{{display:inline}}.inline button{{margin:3px;padding:7px 10px;font-size:12px}}.error{{background:#fff0f0;color:#963c43;padding:13px;border-left:4px solid var(--danger);border-radius:8px}}table{{width:100%;border-collapse:separate;border-spacing:0;margin-top:18px;font-size:14px;overflow:hidden}}th{{background:#f6edef;color:#694d57;font-size:12px;letter-spacing:.03em}}th,td{{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line)}}tr:hover td{{background:#fdf8f8}}.badge{{display:inline-block;padding:5px 10px;border-radius:99px;background:var(--rose-light);color:var(--wine);font-size:12px;font-weight:700}}.tenant{{padding:18px;background:#f7edef;border:1px solid #ecdadd;border-radius:14px;margin-bottom:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:18px}}.module{{position:relative;display:block;min-height:118px;padding:21px;border:1px solid var(--line);border-radius:15px;text-decoration:none;color:var(--ink);background:linear-gradient(145deg,#fff 0%,#fdf8f7 100%);transition:.2s}}.module:after{{content:"â€º";position:absolute;right:18px;top:15px;color:#c18a94;font-size:24px}}.module:hover{{transform:translateY(-2px);border-color:#d6a7af;box-shadow:0 9px 22px #70445414}}.module h3{{margin:0 25px 9px 0;font-size:17px;color:#66404e}}.module p{{margin:0;color:var(--muted);font-size:13px}}
.brand-logo-wrap{{width:48px;height:48px;flex:0 0 48px;overflow:hidden;display:grid;place-items:center}}.brand-logo{{display:block;width:48px;height:48px;object-fit:contain}}.title-crown{{display:inline-flex;align-items:center;gap:2px;margin:2px 5px 2px 0;font-size:20px;font-weight:800}}.title-crown small{{font-size:9px;color:var(--ink)}}.crown-silver{{color:#9da3aa;text-shadow:0 1px #fff}}.crown-gold{{color:#d4a72c;text-shadow:0 1px #fff}}.crown-rose{{color:#cf788b}}.crown-purple{{color:#9167a8}}.crown-blue{{color:#668caf}}.guest main{{max-width:760px;margin:45px auto;padding:24px}}
.owner-header{{position:fixed;inset:0 auto 0 0;z-index:20;width:260px;padding:0;background:linear-gradient(180deg,#68404f 0%,#55333f 100%);color:#fff;display:flex;flex-direction:column;box-shadow:6px 0 24px #4b263326}}.owner-brand{{min-height:92px;padding:23px 24px;color:#fff;text-decoration:none;font-family:Georgia,serif;letter-spacing:1.5px;white-space:nowrap;border-bottom:1px solid #ffffff1f;display:flex;flex-direction:column;justify-content:center}}.owner-brand strong{{font-size:19px}}.owner-brand small{{color:#e8d2d7;font-size:12px;letter-spacing:3px}}.owner-header nav{{display:block;flex:1;padding:12px 13px;overflow-y:auto}}.owner-header nav a{{display:flex;align-items:center;gap:11px;color:#f8eef1;text-decoration:none;padding:10px 13px;border-radius:10px;margin:2px 0;font-size:14px;white-space:nowrap}}.owner-header nav a span{{width:20px;text-align:center;color:#eac3cb}}.owner-header nav a:hover{{background:#ffffff17;color:#fff}}.owner-nav-label{{margin:15px 12px 5px;color:#cbaeb5;font-size:10px;letter-spacing:1.5px;font-weight:700}}.owner-account{{display:flex;align-items:center;gap:10px;padding:16px;background:#452934;border-top:1px solid #ffffff1f;font-size:13px}}.owner-account>span{{min-width:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.owner-account form{{margin:0}}.owner-account button{{margin:0;padding:8px 11px;background:#ffffff1c;box-shadow:none;font-size:12px}}.owner-view main{{margin:0 0 0 260px;max-width:none;padding:38px 42px}}.owner-view main>.card{{max-width:1180px;margin:0 auto}}
.nav-count{{display:inline-grid;place-items:center;min-width:19px;height:19px;margin-left:4px;padding:0 5px;border-radius:10px;background:#fff;color:var(--wine);font-size:11px;font-weight:800}}.notification-item{{display:block;margin:12px 0;padding:18px;border:1px solid var(--line);border-radius:14px;background:#fff;color:var(--ink);text-decoration:none}}.notification-item.unread{{border-left:5px solid var(--rose);background:#fffafb}}.notification-item p{{margin:5px 0}}.notification-kind{{display:inline-block;margin-right:7px;color:var(--wine);font-size:12px;font-weight:750}}
.timeline-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:22px 0}}.timeline-tile{{position:relative;display:block;aspect-ratio:1;overflow:hidden;background:#f1e7e9;color:#fff;text-decoration:none}}.timeline-tile img{{display:block;width:100%;height:100%;object-fit:cover;transition:transform .2s ease}}.timeline-tile:hover img{{transform:scale(1.025)}}.timeline-overlay{{position:absolute;inset:auto 0 0;padding:28px 10px 8px;background:linear-gradient(transparent,#2d1924cc);font-size:12px}}.timeline-overlay strong{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.timeline-stats{{display:flex;justify-content:space-between;gap:6px;margin-top:2px;font-size:11px}}
.family-photo-stage{{width:100%;min-height:260px;max-height:70vh;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:18px;background:linear-gradient(145deg,#f7edef,#fff);border:1px solid var(--line);margin-bottom:18px}}.family-dog-photo{{display:block;max-width:100%;max-height:70vh;width:auto;height:auto;object-fit:contain}}.family-dog-thumb{{display:block;width:100%;height:190px;object-fit:contain;border-radius:12px;margin-bottom:12px;background:#f7edef}}
.family-home-grid{{display:grid;gap:18px;margin-top:18px}}.family-home-card{{display:grid;grid-template-columns:minmax(260px,340px) 1fr;min-height:260px;padding:0;overflow:hidden;border:1px solid var(--line);border-radius:18px;text-decoration:none;color:var(--ink);background:#fff;box-shadow:0 8px 24px #7044540d;transition:.2s}}.family-home-card:hover{{transform:translateY(-2px);border-color:#d6a7af;box-shadow:0 12px 28px #70445418}}.family-home-photo{{display:flex;align-items:center;justify-content:center;min-height:260px;padding:14px;background:linear-gradient(145deg,#f3e7e9,#fbf5f4)}}.family-home-photo img{{display:block;width:100%;height:232px;object-fit:contain;border-radius:12px}}.family-home-photo-empty{{font-family:Georgia,serif;font-size:72px;color:#c59aa3}}.family-home-info{{display:flex;flex-direction:column;justify-content:center;padding:30px 34px}}.family-home-info h3{{margin:0 0 12px;font-size:25px;color:var(--wine)}}.family-home-info p{{margin:5px 0;color:var(--muted)}}.family-home-info .registered-name{{color:var(--ink);font-weight:650}}.family-home-info .badge{{align-self:flex-start;margin-top:12px}}.family-home-more{{margin-top:18px;color:var(--rose);font-weight:700}}
.album-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;margin:18px 0}}.album-item{{overflow:hidden;border:1px solid var(--line);border-radius:15px;background:#fff}}.album-item a{{display:flex;height:210px;align-items:center;justify-content:center;background:#f7edef}}.album-item img{{display:block;max-width:100%;max-height:210px;width:auto;height:auto;object-fit:contain}}.album-meta{{padding:13px}}.album-meta p{{margin:5px 0}}.album-meta form button{{margin-top:8px}}
.page-guide{{margin:14px 0 24px;border:1px solid #decbd0;border-radius:14px;background:#fffafa;overflow:hidden}}.page-guide summary{{padding:14px 17px;cursor:pointer;color:var(--wine);font-weight:750;list-style:none}}.page-guide summary::-webkit-details-marker{{display:none}}.page-guide summary:after{{content:"ï¼‹";float:right;font-size:18px}}.page-guide[open] summary{{border-bottom:1px solid var(--line);background:#f8edef}}.page-guide[open] summary:after{{content:"âˆ’"}}.page-guide-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:16px}}.page-guide-grid section{{padding:12px 14px;border-radius:11px;background:#fff}}.page-guide-grid h3{{margin:0 0 8px;color:var(--wine);font-size:14px}}.page-guide-grid ul,.page-guide-grid ol{{margin:0;padding-left:20px}}.page-guide-grid li,.page-guide-grid p{{margin:5px 0;font-size:13px;color:#665159}}
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
    """é‹å–¶ç®¡ç†è€…ãƒ»çŠ¬èˆã‚¹ã‚¿ãƒƒãƒ•ä»¥å¤–ã«ã¯æ¥­å‹™ç”¨ã‚µã‚¤ãƒ‰ãƒãƒ¼ã‚’è¡¨ç¤ºã—ãªã„ã€‚"""
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
            return JSONResponse({"detail": "å®‰å…¨ã®ãŸã‚ã€ã“ã®æ“ä½œã‚’å—ã‘ä»˜ã‘ã¾ã›ã‚“ã§ã—ãŸ"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    return response


@app.on_event("startup")
def startup():
    # æ—¢å­˜DBã¸å®‰å…¨ã«åˆ—ã‚’è¿½åŠ ã—ã¦ã‹ã‚‰ã€æ–°ãƒ†ãƒ¼ãƒ–ãƒ«ã‚’ä½œã‚‹ã€‚
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
        # æ—§ç®¡ç†è€…ãŒã„ã‚‹å ´åˆã¯æœ€åˆã®1äººã‚’é‹å–¶ç®¡ç†è€…ã¸è‡ªå‹•æ˜‡æ ¼ã™ã‚‹ã€‚
        if not platform_admin_exists(session):
            legacy = session.scalar(select(User).where(User.role == Role.admin).order_by(User.id).limit(1))
            if legacy:
                legacy.platform_admin = True
                session.commit()
        # æ—§ãƒ¦ãƒ¼ã‚¶ãƒ¼ã‚’æ¶ˆã•ãšã€åˆæœŸãƒ†ãƒŠãƒ³ãƒˆã¸æ‰€å±ã•ã›ã‚‹ã€‚
        users = list(session.scalars(select(User)).all())
        if users and not session.scalar(select(Tenant.id).limit(1)):
            tenant = Tenant(name="åˆæœŸãƒ†ãƒŠãƒ³ãƒˆ")
            session.add(tenant)
            session.flush()
            for user in users:
                session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=user.role))
            session.commit()


def dispatch_scheduled_emails():
    with SessionLocal() as session:
        generate_due_finance_recurring(session, date.today())
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
                label = "èª•ç”Ÿæ—¥" if event_type == "birthday" else "ãŠè¿ãˆè¨˜å¿µæ—¥"
                timing = "æœ¬æ—¥" if days == 0 else ("æ˜æ—¥" if days == 1 else "7æ—¥å¾Œ")
                if setting.email_enabled:
                    queue_email(session, owner.email, "anniversary", f"ã€ESTRELLA FAMILYã€‘{dog.call_name}ã®{label}ãŒ{timing}ã§ã™",
                                f"{owner.name} æ§˜\n\n{dog.call_name}ã®{label}ã¯{event_date.strftime('%Yå¹´%mæœˆ%dæ—¥')}ã§ã™ã€‚å¤§åˆ‡ãªè¨˜å¿µæ—¥ã‚’ã”ç¢ºèªãã ã•ã„ã€‚\n{base_url}/family/anniversaries",
                                dog.tenant_id, owner.id, f"anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}")
                send_web_push(owner.id, "anniversaries", f"{dog.call_name}ã®{label}ãŒ{timing}ã§ã™", event_date.strftime("%Yå¹´%mæœˆ%dæ—¥"),
                              "/family/anniversaries", f"push:anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}", session)
                send_line_push(owner.id, dog.tenant_id, "anniversaries", f"{dog.call_name}ã®{label}ãŒ{timing}ã§ã™ã€‚\næ—¥ä»˜ï¼š{event_date.strftime('%Yå¹´%mæœˆ%dæ—¥')}",
                               "/family/anniversaries", f"line:anniversary:{owner.id}:{dog.id}:{event_type}:{event_date.isoformat()}:{days}", session)
            health_groups = [
                ("health_vaccinations", "ãƒ¯ã‚¯ãƒãƒ³", "vaccination", family_vaccine_due_items(owner, session)),
                ("health_checkups", "å¥è¨º", "checkup", family_checkup_due_items(owner, session)),
                ("health_medications", "æŠ•è–¬", "medication", family_medication_due_items(owner, session)),
                ("health_followups", "å†è¨ºãƒ»çµŒéç¢ºèª", "disease", family_disease_due_items(owner, session)),
            ]
            for setting_name, label, category, raw_items in health_groups:
                if not getattr(setting, setting_name, False):
                    continue
                for dog, title, due_on, days in family_health_notification_timing(raw_items):
                    timing = f"{days}æ—¥å¾Œ" if days > 1 else ("æ˜æ—¥" if days == 1 else ("æœ¬æ—¥" if days == 0 else f"{abs(days)}æ—¥è¶…é"))
                    subject = f"ã€ESTRELLA FAMILYã€‘{dog.call_name}ã®{label}äºˆå®šãŒ{timing}ã§ã™"
                    message = f"{owner.name} æ§˜\n\n{dog.call_name}ã®{label}äºˆå®šã‚’ã”ç¢ºèªãã ã•ã„ã€‚\nå†…å®¹ï¼š{title}\näºˆå®šæ—¥ï¼š{due_on.strftime('%Yå¹´%mæœˆ%dæ—¥')}ï¼ˆ{timing}ï¼‰\n\nå®Ÿæ–½å¾Œã¯å¥åº·ç®¡ç†ç”»é¢ã§ã€Œå®Ÿæ–½æ¸ˆã¿ã«ã™ã‚‹ã€ã‚’æŠ¼ã—ã¦ãã ã•ã„ã€‚\n{base_url}/family/dogs/{dog.id}/health/{category}"
                    title_key = hashlib.sha256(title.encode()).hexdigest()[:12]
                    dedupe = f"health:{owner.id}:{dog.id}:{category}:{due_on.isoformat()}:{days}:{title_key}"
                    if setting.email_enabled:
                        queue_email(session, owner.email, "health_reminder", subject, message, dog.tenant_id, owner.id, f"email:{dedupe}")
                    send_web_push(owner.id, setting_name, subject.removeprefix("ã€ESTRELLA FAMILYã€‘"),
                                  f"{title}ï¼äºˆå®šæ—¥ {due_on.strftime('%Yå¹´%mæœˆ%dæ—¥')}", f"/family/dogs/{dog.id}/health/{category}", f"push:{dedupe}", session)
                    send_line_push(owner.id, dog.tenant_id, setting_name,
                                   f"{dog.call_name}ã®{label}äºˆå®šãŒ{timing}ã§ã™ã€‚\nå†…å®¹ï¼š{title}\näºˆå®šæ—¥ï¼š{due_on.strftime('%Yå¹´%mæœˆ%dæ—¥')}",
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
    return layout("Dogç®¡ç†ã‚¢ãƒ—ãƒª", '<h1>Dogç®¡ç†ã‚¢ãƒ—ãƒª</h1><p>è¤‡æ•°ã®ä¼šç¤¾ãƒ»çŠ¬èˆã‚’å®‰å…¨ã«ç®¡ç†ã—ã¾ã™ã€‚</p><a class="button" href="/login">ãƒ­ã‚°ã‚¤ãƒ³</a>ã€€<a href="/register">ãŠå®¢æ§˜ç™»éŒ²</a>')


@app.get("/setup", response_class=HTMLResponse)
def setup_page(session: Session = Depends(db)):
    if platform_admin_exists(session):
        return RedirectResponse("/login", status_code=303)
    return layout("åˆæœŸè¨­å®š", '<h1>åˆæœŸé‹å–¶ç®¡ç†è€…ç™»éŒ²</h1><form method="post"><label>ãŠåå‰</label><input name="name" required maxlength="100"><label>ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹</label><input name="email" type="email" required><label>æœ€åˆã®ä¼šç¤¾ãƒ»çŠ¬èˆå</label><input name="tenant_name" required maxlength="150"><label>ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ï¼ˆ8æ–‡å­—ä»¥ä¸Šï¼‰</label><input name="password" type="password" minlength="8" required><button>ç™»éŒ²ã™ã‚‹</button></form>')


@app.post("/setup", response_class=HTMLResponse)
def setup(name: str = Form(...), email: str = Form(...), tenant_name: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    if len(password) < 8:
        return layout("ã‚¨ãƒ©ãƒ¼", '<p class="error">ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã¯8æ–‡å­—ä»¥ä¸Šã«ã—ã¦ãã ã•ã„ã€‚</p><a href="/setup">æˆ»ã‚‹</a>')
    session.execute(text("SELECT pg_advisory_xact_lock(20260824)"))
    if platform_admin_exists(session):
        session.rollback()
        return RedirectResponse("/login", status_code=303)
    email = normalize_email(email)
    if session.scalar(select(User).where(User.email == email)):
        session.rollback()
        return layout("ã‚¨ãƒ©ãƒ¼", '<p class="error">ã“ã®ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹ã¯æ—¢ã«ç™»éŒ²ã•ã‚Œã¦ã„ã¾ã™ã€‚</p>')
    user = User(name=name.strip(), email=email, password_hash=passwords.hash(password), role=Role.admin, platform_admin=True)
    tenant = Tenant(name=tenant_name.strip())
    session.add_all([user, tenant])
    session.flush()
    session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=Role.admin))
    session.commit()
    return RedirectResponse("/login?setup=1", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page():
    return layout("ãŠå®¢æ§˜ç™»éŒ²", '<h1>ãŠå®¢æ§˜ç™»éŒ²</h1><p>ç™»éŒ²å¾Œã€ãƒ†ãƒŠãƒ³ãƒˆç®¡ç†è€…ã‹ã‚‰æ‰€å±è¿½åŠ ã‚’å—ã‘ã¦ãã ã•ã„ã€‚</p><form method="post"><label>ãŠåå‰</label><input name="name" required maxlength="100"><label>ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹</label><input name="email" type="email" required><label>ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ï¼ˆ8æ–‡å­—ä»¥ä¸Šï¼‰</label><input name="password" type="password" minlength="8" required><button>ç™»éŒ²ã™ã‚‹</button></form>')


@app.post("/register", response_class=HTMLResponse)
def register(name: str = Form(...), email: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    email = normalize_email(email)
    if len(password) < 8 or session.scalar(select(User).where(User.email == email)):
        return layout("ç™»éŒ²ã‚¨ãƒ©ãƒ¼", '<p class="error">ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹ã®é‡è¤‡ã€ã¾ãŸã¯ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã®é•·ã•ã‚’ç¢ºèªã—ã¦ãã ã•ã„ã€‚</p><a href="/register">æˆ»ã‚‹</a>')
    session.add(User(name=name.strip(), email=email, password_hash=passwords.hash(password), role=Role.customer))
    session.commit()
    return RedirectResponse("/login?registered=1", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(registered: int = 0, setup: int = 0):
    notice = "<p>åˆæœŸè¨­å®šãŒå®Œäº†ã—ã¾ã—ãŸã€‚</p>" if setup else ("<p>ç™»éŒ²ãŒå®Œäº†ã—ã¾ã—ãŸã€‚</p>" if registered else "")
    return layout("ãƒ­ã‚°ã‚¤ãƒ³", f'<h1>ãƒ­ã‚°ã‚¤ãƒ³</h1>{notice}<form method="post"><label>ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹</label><input name="email" type="email" required><label>ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰</label><input name="password" type="password" required><button>ãƒ­ã‚°ã‚¤ãƒ³</button></form><p><a href="/forgot-password">ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã‚’ãŠå¿˜ã‚Œã®æ–¹</a></p>')


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    throttle_key = auth_throttle_key(request, "web-login", email)
    if auth_throttle_blocked(throttle_key, session):
        return HTMLResponse(layout("ãƒ­ã‚°ã‚¤ãƒ³", '<p class="error">ãƒ­ã‚°ã‚¤ãƒ³è©¦è¡ŒãŒå¤šã„ãŸã‚ã€15åˆ†å¾Œã«ã‚‚ã†ä¸€åº¦ãŠè©¦ã—ãã ã•ã„ã€‚</p><a href="/login">æˆ»ã‚‹</a>'), status_code=429)
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not user.active or not passwords.verify(password, user.password_hash):
        auth_throttle_failure(throttle_key, session)
        return HTMLResponse(layout("ãƒ­ã‚°ã‚¤ãƒ³", '<p class="error">ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹ã¾ãŸã¯ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ãŒé•ã„ã¾ã™ã€‚</p><a href="/login">æˆ»ã‚‹</a>'), status_code=401)
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
    return layout("ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰å†è¨­å®š", '''<h1>ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã‚’ãŠå¿˜ã‚Œã®æ–¹</h1><p>ç™»éŒ²ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹ã‚’å…¥åŠ›ã—ã¦ãã ã•ã„ã€‚å®‰å…¨ç¢ºèªå¾Œã€çŠ¬èˆã‹ã‚‰å†è¨­å®šæ–¹æ³•ã‚’ã”æ¡ˆå†…ã—ã¾ã™ã€‚</p>
    <form method="post"><label>ç™»éŒ²ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹</label><input type="email" name="email" required><button>å†è¨­å®šã‚’ç”³ã—è¾¼ã‚€</button></form><p><a href="/login">ãƒ­ã‚°ã‚¤ãƒ³ã¸æˆ»ã‚‹</a></p>''')


@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_request(request: Request, email: str = Form(...), session: Session = Depends(db)):
    throttle_key = auth_throttle_key(request, "forgot-password", email)
    if auth_throttle_blocked(throttle_key, session):
        return layout("å—ä»˜å®Œäº†", '<h1>å—ä»˜ã—ã¾ã—ãŸ</h1><p>ç™»éŒ²çŠ¶æ³ã«ã‹ã‹ã‚ã‚‰ãšã€å®‰å…¨ã®ãŸã‚åŒã˜æ¡ˆå†…ã‚’è¡¨ç¤ºã—ã¦ã„ã¾ã™ã€‚</p><p><a href="/login">ãƒ­ã‚°ã‚¤ãƒ³ã¸æˆ»ã‚‹</a></p>')
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
                subject = "ã€ESTRELLA FAMILYã€‘ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰å†è¨­å®š"
                body = f"{account.name} æ§˜\n\nä»¥ä¸‹ã®ãƒªãƒ³ã‚¯ã‹ã‚‰30åˆ†ä»¥å†…ã«æ–°ã—ã„ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã‚’è¨­å®šã—ã¦ãã ã•ã„ã€‚\n{base_url}/reset-password/{raw_token}\n\nãŠå¿ƒå½“ãŸã‚ŠãŒãªã„å ´åˆã¯ã€ã“ã®ãƒ¡ãƒ¼ãƒ«ã‚’ç ´æ£„ã—ã¦ãã ã•ã„ã€‚"
                error = send_email_content(account.email, subject, body)
                delivery = EmailDelivery(user_id=account.id, recipient=account.email, purpose="password_reset", subject=subject,
                                         body="ã‚»ã‚­ãƒ¥ãƒªãƒ†ã‚£ä¿è­·ã®ãŸã‚å†è¨­å®šãƒªãƒ³ã‚¯æœ¬æ–‡ã¯ä¿å­˜ã—ã¦ã„ã¾ã›ã‚“ã€‚", attempts=1,
                                         status="failed" if error else "sent", error=error, sent_at=None if error else datetime.now(timezone.utc))
                session.add(delivery)
                if not error:
                    reset_request.resolved_at = datetime.now(timezone.utc)
            session.commit()
    return layout("å—ä»˜å®Œäº†", '<h1>å—ä»˜ã—ã¾ã—ãŸ</h1><p>ç™»éŒ²çŠ¶æ³ã«ã‹ã‹ã‚ã‚‰ãšã€å®‰å…¨ã®ãŸã‚åŒã˜æ¡ˆå†…ã‚’è¡¨ç¤ºã—ã¦ã„ã¾ã™ã€‚çŠ¬èˆã‹ã‚‰ã®é€£çµ¡ã‚’ãŠå¾…ã¡ãã ã•ã„ã€‚</p><p><a href="/login">ãƒ­ã‚°ã‚¤ãƒ³ã¸æˆ»ã‚‹</a></p>')


def active_password_reset(raw_token: str, session: Session) -> PasswordResetToken | None:
    reset = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(raw_token), PasswordResetToken.used_at.is_(None)))
    if not reset:
        return None
    expires = reset.expires_at if reset.expires_at.tzinfo else reset.expires_at.replace(tzinfo=timezone.utc)
    return reset if expires > datetime.now(timezone.utc) else None


@app.get("/reset-password/{raw_token}", response_class=HTMLResponse)
def reset_password_page(raw_token: str, session: Session = Depends(db)):
    if not active_password_reset(raw_token, session):
        return HTMLResponse(layout("ãƒªãƒ³ã‚¯ã‚¨ãƒ©ãƒ¼", '<h1>å†è¨­å®šãƒªãƒ³ã‚¯ã‚’åˆ©ç”¨ã§ãã¾ã›ã‚“</h1><p>æœŸé™åˆ‡ã‚Œã¾ãŸã¯ä½¿ç”¨æ¸ˆã¿ã§ã™ã€‚çŠ¬èˆã¸å†åº¦ãŠç”³ã—è¾¼ã¿ãã ã•ã„ã€‚</p>'), status_code=400)
    return layout("æ–°ã—ã„ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰", f'''<h1>æ–°ã—ã„ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã‚’è¨­å®š</h1><form method="post">
    <label>æ–°ã—ã„ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ï¼ˆ8æ–‡å­—ä»¥ä¸Šï¼‰</label><input type="password" name="password" minlength="8" required>
    <label>ç¢ºèªå…¥åŠ›</label><input type="password" name="password_confirm" minlength="8" required><button>ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã‚’å¤‰æ›´ã™ã‚‹</button></form>''')


@app.post("/reset-password/{raw_token}", response_class=HTMLResponse)
def reset_password_save(raw_token: str, password: str = Form(...), password_confirm: str = Form(...), session: Session = Depends(db)):
    reset = active_password_reset(raw_token, session)
    if not reset or len(password) < 8 or password != password_confirm:
        return HTMLResponse(layout("å…¥åŠ›ã‚¨ãƒ©ãƒ¼", '<p class="error">ãƒªãƒ³ã‚¯ã€ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã®é•·ã•ã€ç¢ºèªå…¥åŠ›ã‚’ã”ç¢ºèªãã ã•ã„ã€‚</p>'), status_code=400)
    account = session.get(User, reset.user_id)
    account.password_hash = passwords.hash(password)
    reset.used_at = datetime.now(timezone.utc)
    requests = session.scalars(select(PasswordResetRequest).where(PasswordResetRequest.user_id == account.id, PasswordResetRequest.resolved_at.is_(None))).all()
    for request_item in requests:
        request_item.resolved_at = datetime.now(timezone.utc)
    session.execute(text("DELETE FROM login_sessions WHERE user_id = :user_id"), {"user_id": account.id})
    session.commit()
    return layout("å¤‰æ›´å®Œäº†", '<h1>ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã‚’å¤‰æ›´ã—ã¾ã—ãŸ</h1><p>æ–°ã—ã„ãƒ‘ã‚¹ãƒ¯ãƒ¼ãƒ‰ã§ãƒ­ã‚°ã‚¤ãƒ³ã—ã¦ãã ã•ã„ã€‚</p><p><a class="button" href="/login">ãƒ­ã‚°ã‚¤ãƒ³ã™ã‚‹</a></p>')


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
        raise HTTPException(status_code=403, detail="ã“ã®ãƒ†ãƒŠãƒ³ãƒˆã¸åˆ‡ã‚Šæ›¿ãˆã‚‹æ¨©é™ãŒã‚ã‚Šã¾ã›ã‚“")
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("tenant_id", str(tenant_id), httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return response


def dashboard_priority_items(tenant_id: int, session: Session) -> list[tuple[date, str, str, str]]:
    """é¸æŠä¸­ã®çŠ¬èˆã§ã€æœªå®Œäº†ã‹ã¤7æ—¥ä»¥å†…ã«å¯¾å¿œãŒå¿…è¦ãªäºˆå®šã‚’è¿”ã™ã€‚"""
    today = date.today(); limit_day = today + timedelta(days=7); items: list[tuple[date, str, str, str]] = []; keys: set[tuple[date, str]] = set()
    category_urls = {"breeding": "/modules/breeding", "health": "/modules/health", "sales": "/modules/sales", "customer": "/modules/sales", "legal": "/modules/legal"}
    category_labels = {"breeding": "ç¹æ®–", "health": "å¥åº·", "sales": "è²©å£²", "customer": "é¡§å®¢", "legal": "æ³•ä»¤", "care": "ãŠä¸–è©±", "general": "ä¸€èˆ¬"}
    for task in session.scalars(select(TaskEvent).where(TaskEvent.tenant_id == tenant_id, TaskEvent.completed.is_(False), TaskEvent.due_date <= limit_day)).all():
        key = (task.due_date, task.title); keys.add(key)
        items.append((task.due_date, task.title, category_labels.get(task.category, "Todo"), category_urls.get(task.category, "/modules/todo")))
    for document in session.scalars(select(LegalDocument).where(LegalDocument.tenant_id == tenant_id, LegalDocument.due_date.is_not(None), LegalDocument.due_date <= limit_day, LegalDocument.status != "completed")).all():
        key = (document.due_date, document.document_type)
        if key not in keys: items.append((document.due_date, document.document_type, "æ³•ä»¤", "/modules/legal"))
    items.sort(key=lambda item: (item[0], item[1]))
    return items[:50]


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(require_user), session: Session = Depends(db)):
    tenants = accessible_tenants(user, session)
    if not tenants and session.scalar(select(DogOwnership.id).where(DogOwnership.user_id == user.id, DogOwnership.active.is_(True)).limit(1)) is not None:
        return RedirectResponse("/family", status_code=303)
    tenant = selected_tenant(request, user, session)
    options = "".join(f'<option value="{t.id}" {"selected" if tenant and t.id == tenant.id else ""}>{html.escape(t.name)}</option>' for t in tenants)
    switcher = f'<div class="tenant"><form method="post" action="/tenant/switch"><label>è¡¨ç¤ºã™ã‚‹ä¼šç¤¾ãƒ»çŠ¬èˆ</label><select name="tenant_id">{options}</select><button>åˆ‡ã‚Šæ›¿ãˆã‚‹</button></form></div>' if tenants else '<p class="error">æ‰€å±ãƒ†ãƒŠãƒ³ãƒˆãŒã‚ã‚Šã¾ã›ã‚“ã€‚ç®¡ç†è€…ã¸é€£çµ¡ã—ã¦ãã ã•ã„ã€‚</p>'
    role = tenant_role(user, tenant, session)
    label = "é‹å–¶ç®¡ç†è€…" if user.platform_admin else ({Role.admin: "ç®¡ç†è€…", Role.employee: "å¾“æ¥­å“¡", Role.customer: "ãŠå®¢æ§˜"}.get(role, "æœªæ‰€å±"))
    dog_count = session.scalar(select(func.count(Dog.id)).where(Dog.tenant_id == tenant.id, Dog.active.is_(True))) if tenant else 0
    module_cards = ""
    if tenant:
        for key, (title, description) in MODULES.items():
            extra = f"ï¼ˆç™»éŒ² {dog_count}é ­ï¼‰" if key == "dogs" else ""
            module_cards += f'<a class="module" href="/modules/{key}"><h3>{title}</h3><p>{description}{extra}</p></a>'
    body = f'<h1>{html.escape(user.name)}ã•ã‚“ã€ã“ã‚“ã«ã¡ã¯</h1>{switcher}<p><span class="badge">{label}</span></p>'
    if tenant:
        priority_items = dashboard_priority_items(tenant.id, session); today = date.today()
        overdue_count = sum(1 for item in priority_items if item[0] < today); today_count = sum(1 for item in priority_items if item[0] == today); week_count = sum(1 for item in priority_items if today < item[0] <= today + timedelta(days=7))
        priority_rows = "".join(f'''<a class="priority-item" href="{url}"><span><strong>{html.escape(title)}</strong><small>{html.escape(category)}ï¼{due}</small></span><span class="badge" style="{'background:#f4c9ca;color:#8d3037' if due < today else ('background:#ead0d5;color:#704454' if due == today else 'background:#f6e1b8;color:#755514')}">{f'{(today-due).days}æ—¥è¶…é' if due < today else ('æœ¬æ—¥' if due == today else f'{(due-today).days}æ—¥å¾Œ')}</span></a>''' for due, title, category, url in priority_items[:10])
        body += f'''<h2>{html.escape(tenant.name)} æ¥­å‹™ãƒ›ãƒ¼ãƒ </h2><section aria-label="è¦å¯¾å¿œæ¥­å‹™"><h2>ä»Šæ—¥ã®è¦å¯¾å¿œ</h2><div class="grid"><a class="module" href="/modules/calendar?calendar_state=overdue&show_all=true"><h3>æœŸé™è¶…é</h3><p><strong class="{'error' if overdue_count else ''}">{overdue_count}ä»¶</strong></p></a><a class="module" href="/modules/calendar?month={today:%Y-%m}"><h3>æœ¬æ—¥ã®äºˆå®š</h3><p><strong>{today_count}ä»¶</strong></p></a><a class="module" href="/modules/calendar"><h3>7æ—¥ä»¥å†…</h3><p><strong>{week_count}ä»¶</strong></p></a></div><div class="priority-list">{priority_rows or '<div class="tenant">7æ—¥ä»¥å†…ã¾ãŸã¯æœŸé™è¶…éã®è¦å¯¾å¿œæ¥­å‹™ã¯ã‚ã‚Šã¾ã›ã‚“ã€‚</div>'}</div><div class="health-toolbar"><a class="button" href="/modules/calendar">æ¥­å‹™ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼</a><a class="button secondary" href="/modules/todo">Todoã‚’ç™»éŒ²</a><a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†</a></div></section><h2>æ©Ÿèƒ½ä¸€è¦§</h2><div class="grid">{module_cards}</div>'''
    return layout("ãƒ›ãƒ¼ãƒ ", body, user)


@app.get("/modules/todo", response_class=HTMLResponse)
def todo_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    tasks = session.scalars(select(TaskEvent).where(TaskEvent.tenant_id == tenant.id).order_by(TaskEvent.completed, TaskEvent.due_date)).all()
    category_labels = {"general": "ä¸€èˆ¬", "care": "ãŠä¸–è©±", "customer": "ãŠå®¢æ§˜å¯¾å¿œ", "breeding": "ç¹æ®–", "health": "å¥åº·", "legal": "ç”³è«‹"}
    rows = ""
    for task in tasks:
        state = "å®Œäº†" if task.completed else "æœªå®Ÿæ–½"
        rows += f'<tr><td>{task.due_date}</td><td>{html.escape(task.title)}</td><td>{category_labels.get(task.category, task.category)}</td><td>{state}</td><td><form class="inline" method="post" action="/modules/todo/{task.id}/toggle"><button class="{"secondary" if task.completed else "success"}">{"æœªå®Œäº†ã«æˆ»ã™" if task.completed else "å®Œäº†"}</button></form></td></tr>'
    body = f'''<h1>Todoãƒªã‚¹ãƒˆ</h1><form method="post"><div class="grid"><div><label>äºˆå®šæ—¥</label><input type="date" name="due_date" required></div><div><label>ã‚¿ã‚¤ãƒˆãƒ«</label><input name="title" required></div><div><label>ã‚«ãƒ†ã‚´ãƒªãƒ¼</label><select name="category"><option value="general">ä¸€èˆ¬</option><option value="care">ãŠä¸–è©±</option><option value="customer">ãŠå®¢æ§˜å¯¾å¿œ</option><option value="breeding">ç¹æ®–</option><option value="health">å¥åº·</option><option value="legal">ç”³è«‹</option></select></div></div><label>ãƒ¡ãƒ¢</label><textarea name="notes"></textarea><button>äºˆå®šã‚’è¿½åŠ </button></form><table><tr><th>æ—¥ä»˜</th><th>å†…å®¹</th><th>åˆ†é¡</th><th>çŠ¶æ…‹</th><th>æ“ä½œ</th></tr>{rows}</table>'''
    return layout("Todoãƒªã‚¹ãƒˆ", body, user)


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
        raise HTTPException(status_code=400, detail="è¡¨ç¤ºæœˆã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if first_day < date(2000, 1, 1) or first_day > date(2100, 12, 1): raise HTTPException(status_code=400, detail="è¡¨ç¤ºæœˆã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    allowed_categories = {"", "todo", "breeding", "health", "sales", "legal"}; allowed_states = {"", "upcoming", "overdue", "completed"}
    if calendar_category not in allowed_categories or calendar_state not in allowed_states: raise HTTPException(status_code=400, detail="æ¤œç´¢æ¡ä»¶ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
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
        dog = dogs.get(item.dog_id); add_event(item.start_date + timedelta(days=180), f"{dog.call_name if dog else 'å¯¾è±¡çŠ¬'} æ¬¡å›ãƒ’ãƒ¼ãƒˆäºˆæ¸¬", "breeding", "ãƒ’ãƒ¼ãƒˆè¨˜éŒ²", "/modules/breeding")
    completed_breedings = set(session.scalars(select(Litter.breeding_id).where(Litter.tenant_id == tenant.id, Litter.breeding_id.is_not(None))).all())
    for item in session.scalars(select(BreedingRecord).where(BreedingRecord.tenant_id == tenant.id)).all():
        dog = dogs.get(item.dam_id); add_event(item.mating_date + timedelta(days=63), f"{dog.call_name if dog else 'æ¯çŠ¬'} å‡ºç”£äºˆå®š", "breeding", "äº¤é…è¨˜éŒ²", "/modules/births", item.id in completed_breedings)
    for item in session.scalars(select(Vaccination).where(Vaccination.tenant_id == tenant.id, Vaccination.next_due_on.is_not(None))).all():
        dog = dogs.get(item.dog_id); add_event(item.next_due_on, f"{dog.call_name if dog else 'å¯¾è±¡çŠ¬'} {item.vaccine_name}æ¥ç¨®äºˆå®š", "health", "ãƒ¯ã‚¯ãƒãƒ³", "/modules/health/vaccinations")
    for item in session.scalars(select(HealthRecord).where(HealthRecord.tenant_id == tenant.id, HealthRecord.category == "checkup", HealthRecord.next_due_on.is_not(None))).all():
        dog = dogs.get(item.dog_id); add_event(item.next_due_on, f"{dog.call_name if dog else 'å¯¾è±¡çŠ¬'} æ¬¡å›å¥è¨ºäºˆå®š", "health", "å¥è¨º", "/modules/health/checkups")
    for item in session.scalars(select(Medication).where(Medication.tenant_id == tenant.id, Medication.next_due_on.is_not(None), Medication.status != "completed")).all():
        dog = dogs.get(item.dog_id); add_event(item.next_due_on, f"{dog.call_name if dog else 'å¯¾è±¡çŠ¬'} {item.medicine_name}æŠ•è–¬äºˆå®š", "health", "æŠ•è–¬", "/modules/health/medications")
    for item in session.scalars(select(DiseaseHistory).where(DiseaseHistory.tenant_id == tenant.id, DiseaseHistory.next_followup_on.is_not(None), DiseaseHistory.status != "recovered")).all():
        dog = dogs.get(item.dog_id); add_event(item.next_followup_on, f"{dog.call_name if dog else 'å¯¾è±¡çŠ¬'} {item.disease_name}å†è¨ºãƒ»ç¢ºèª", "health", "å†è¨ºãƒ»çµŒéç¢ºèª", "/modules/health/diseases")
    for item in session.scalars(select(LegalDocument).where(LegalDocument.tenant_id == tenant.id, LegalDocument.due_date.is_not(None))).all(): add_event(item.due_date, item.document_type, "legal", "æ³•ä»¤ãƒ»è¡Œæ”¿", "/modules/legal", item.status == "completed")
    events = [item for item in events if (show_all or first_day <= item[0] <= month_end) and (not calendar_category or item[2] == calendar_category) and (not calendar_state or item[3] == calendar_state)]
    events.sort(key=lambda item: (item[0], item[1]))
    category_labels = {"todo": "Todo", "breeding": "ç¹æ®–", "health": "å¥åº·", "sales": "è²©å£²ãƒ»é¡§å®¢", "legal": "æ³•ä»¤"}; state_labels = {"upcoming": "äºˆå®š", "overdue": "æœŸé™è¶…é", "completed": "å®Œäº†"}
    state_styles = {"upcoming": "background:#f6e1b8;color:#755514", "overdue": "background:#f4c9ca;color:#8d3037", "completed": "background:#d9eadb;color:#47634b"}
    rows = "".join(f'''<tr><td>{day}</td><td><a href="{url}">{html.escape(title)}</a></td><td>{category_labels[category]}</td><td>{html.escape(source)}</td><td><span class="badge" style="{state_styles[state]}">{state_labels[state]}</span></td></tr>''' for day, title, category, state, source, url in events)
    mobile_cards = "".join(f'''<article class="calendar-mobile-card"><h3><a href="{url}">{html.escape(title)}</a></h3><p>{day}ã€€<span class="badge" style="{state_styles[state]}">{state_labels[state]}</span></p><p>{category_labels[category]}ï¼{html.escape(source)}</p></article>''' for day, title, category, state, source, url in events)
    category_options = "".join(f'<option value="{value}" {"selected" if calendar_category == value else ""}>{label}</option>' for value, label in (("", "ã™ã¹ã¦"), ("todo", "Todo"), ("breeding", "ç¹æ®–"), ("health", "å¥åº·"), ("sales", "è²©å£²ãƒ»é¡§å®¢"), ("legal", "æ³•ä»¤")))
    state_options = "".join(f'<option value="{value}" {"selected" if calendar_state == value else ""}>{label}</option>' for value, label in (("", "ã™ã¹ã¦"), ("upcoming", "äºˆå®š"), ("overdue", "æœŸé™è¶…é"), ("completed", "å®Œäº†")))
    body = f'''<h1>æ¥­å‹™ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼</h1><p>Todoã«åŠ ãˆã€ãƒ’ãƒ¼ãƒˆäºˆæ¸¬ãƒ»å‡ºç”£äºˆå®šãƒ»å¥åº·äºˆå®šãƒ»æ³•ä»¤æœŸé™ã‚’ç™»éŒ²ãƒ‡ãƒ¼ã‚¿ã‹ã‚‰è‡ªå‹•è¡¨ç¤ºã—ã¾ã™ã€‚</p><form method="get" action="/modules/calendar"><div class="grid"><div><label>è¡¨ç¤ºæœˆ</label><input type="month" name="month" value="{first_day:%Y-%m}" required></div><div><label>åˆ†é¡</label><select name="calendar_category">{category_options}</select></div><div><label>çŠ¶æ…‹</label><select name="calendar_state">{state_options}</select></div></div><label style="font-weight:400"><input type="checkbox" name="show_all" value="true" style="width:auto" {"checked" if show_all else ""}> æœˆã‚’é™å®šã›ãšå…¨æœŸé–“ã‚’è¡¨ç¤º</label><button>ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼ã‚’è¡¨ç¤º</button> <a class="button secondary" href="/modules/calendar">ä»Šæœˆã¸æˆ»ã‚‹</a> <a class="button" href="/modules/todo">äºˆå®šã‚’æ‰‹å‹•ç™»éŒ²</a></form><p><strong>{len(events)}ä»¶</strong>ã®äºˆå®šã‚’è¡¨ç¤ºã—ã¦ã„ã¾ã™ã€‚</p><div class="calendar-desktop-only" style="overflow-x:auto"><table><tr><th>æ—¥ä»˜</th><th>äºˆå®š</th><th>åˆ†é¡</th><th>ç™»éŒ²å…ƒ</th><th>çŠ¶æ…‹</th></tr>{rows or '<tr><td colspan="5">æ¡ä»¶ã«ä¸€è‡´ã™ã‚‹äºˆå®šã¯ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></div><section class="calendar-mobile-only">{mobile_cards or '<div class="tenant">æ¡ä»¶ã«ä¸€è‡´ã™ã‚‹äºˆå®šã¯ã‚ã‚Šã¾ã›ã‚“ã€‚</div>'}</section>'''
    return layout("ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼", body, user)


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
    body = f'''<h1>äº¤é…ãƒ»ãƒ’ãƒ¼ãƒˆç®¡ç†</h1>
    <h2>ãƒ’ãƒ¼ãƒˆè¨˜éŒ²</h2><form method="post" action="/modules/breeding/heat"><div class="grid"><div><label>æ¯çŠ¬</label><select name="dog_id" required>{female_options}</select></div><div><label>ãƒ’ãƒ¼ãƒˆé–‹å§‹æ—¥</label><input name="start_date" type="date" required></div></div><label>ãƒ¡ãƒ¢</label><textarea name="notes"></textarea><button>ãƒ’ãƒ¼ãƒˆã‚’ç™»éŒ²</button></form>
    <table><tr><th>æ¯çŠ¬</th><th>é–‹å§‹æ—¥</th><th>æ¬¡å›äºˆæ¸¬</th></tr>{heat_rows}</table>
    <h2>äº¤é…è¨˜éŒ²</h2><form method="post" action="/modules/breeding/mating"><div class="grid"><div><label>æ¯çŠ¬</label><select name="dam_id" required>{female_options}</select></div><div><label>çˆ¶çŠ¬</label><select name="sire_id" required>{male_options}</select></div><div><label>1å›ç›®äº¤é…æ—¥</label><input name="mating_date" type="date" required></div><div><label>äº¤é…æ–¹æ³•</label><select name="method"><option value="natural">è‡ªç„¶äº¤é…</option><option value="artificial">äººå·¥æˆç²¾</option></select></div></div><label>ãƒ¡ãƒ¢</label><textarea name="notes"></textarea><button>äº¤é…ã‚’ç™»éŒ²</button></form>
    <table><tr><th>æ¯çŠ¬</th><th>çˆ¶çŠ¬</th><th>äº¤é…æ—¥</th><th>å‡ºç”£äºˆå®šæ—¥</th><th>è¿‘è¦ªäº¤é…ç‡</th><th>çŠ¶æ…‹</th></tr>{breeding_rows}</table>
    <h2>äº¤é…ã‚·ãƒŸãƒ¥ãƒ¬ãƒ¼ã‚·ãƒ§ãƒ³</h2><form method="post" action="/modules/breeding/simulation"><div class="grid"><div><label>æ¯çŠ¬</label><select name="dam_id">{female_options}</select></div><div><label>çˆ¶çŠ¬</label><select name="sire_id">{male_options}</select></div></div><button>è¿‘è¦ªäº¤é…ç‡ã¨éºä¼ç—…ãƒªã‚¹ã‚¯ã‚’è¨ˆç®—</button></form>'''
    return layout("äº¤é…ãƒ»ãƒ’ãƒ¼ãƒˆç®¡ç†", body, user)


@app.post("/modules/breeding/heat")
def heat_create(dog_id: int = Form(...), start_date: str = Form(...), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = session.scalar(select(Dog).where(Dog.id == dog_id, Dog.tenant_id == tenant.id, Dog.sex == "female"))
    if not dog:
        raise HTTPException(status_code=400, detail="æ¯çŠ¬ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
    started = date.fromisoformat(start_date)
    session.add(HeatCycle(tenant_id=tenant.id, dog_id=dog.id, start_date=started, notes=notes.strip() or None))
    session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} æ¬¡å›ãƒ’ãƒ¼ãƒˆäºˆæ¸¬", category="breeding", due_date=started + timedelta(days=180)))
    session.commit()
    return RedirectResponse("/modules/breeding", status_code=303)


@app.post("/modules/breeding/mating")
def mating_create(dam_id: int = Form(...), sire_id: int = Form(...), mating_date: str = Form(...), method: str = Form("natural"), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dam = session.scalar(select(Dog).where(Dog.id == dam_id, Dog.tenant_id == tenant.id, Dog.sex == "female"))
    sire = session.scalar(select(Dog).where(Dog.id == sire_id, Dog.tenant_id == tenant.id, Dog.sex == "male"))
    if not dam or not sire or dam.id == sire.id or method not in {"natural", "artificial"}:
        raise HTTPException(status_code=400, detail="äº¤é…æƒ…å ±ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    mated = date.fromisoformat(mating_date)
    note = f"äº¤é…æ–¹æ³•: {'è‡ªç„¶äº¤é…' if method == 'natural' else 'äººå·¥æˆç²¾'}"
    if notes.strip():
        note += "\n" + notes.strip()
    coefficient = offspring_coefficient(session, tenant.id, sire.id, dam.id) * 100
    session.add(BreedingRecord(tenant_id=tenant.id, sire_id=sire.id, dam_id=dam.id, mating_date=mated, coefficient=coefficient, status="mated", notes=note))
    session.add(TaskEvent(tenant_id=tenant.id, dog_id=dam.id, title=f"{dam.call_name} å‡ºç”£äºˆå®š", category="breeding", due_date=mated + timedelta(days=63)))
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
    risk_html = "".join(f"<li>{html.escape(message)}</li>" for message in risks) or "<li>ä¸¡è¦ªã§å…±é€šã™ã‚‹éºä¼å­æ¤œæŸ»æƒ…å ±ãŒã‚ã‚Šã¾ã›ã‚“ã€‚</li>"
    level = "æ¯”è¼ƒçš„ä½ã„" if coefficient < 6.25 else ("æ³¨æ„ãŒå¿…è¦" if coefficient < 12.5 else "é«˜ã„")
    body = f'<h1>äº¤é…ã‚·ãƒŸãƒ¥ãƒ¬ãƒ¼ã‚·ãƒ§ãƒ³çµæœ</h1><p>{html.escape(sire.call_name)} Ã— {html.escape(dam.call_name)}</p><div class="tenant"><h2>äºˆå®šä»”çŠ¬ã®è¿‘è¦ªäº¤é…ç‡ï¼š{coefficient:.2f}%</h2><p>åˆ¤å®šï¼š{level}</p></div><h2>éºä¼ç—…ãƒªã‚¹ã‚¯</h2><ul>{risk_html}</ul><p>è¡€çµ±ã‚„æ¤œæŸ»æƒ…å ±ãŒæœªç™»éŒ²ã®å ´åˆã€çµæœã¯éå°è©•ä¾¡ã•ã‚Œã‚‹å¯èƒ½æ€§ãŒã‚ã‚Šã¾ã™ã€‚æœ€çµ‚åˆ¤æ–­ã«ã¯ç£åŒ»å¸«ãƒ»éºä¼å­¦ã®å°‚é–€å®¶ã¸ã®ç¢ºèªãŒå¿…è¦ã§ã™ã€‚</p><a class="button secondary" href="/modules/breeding">æˆ»ã‚‹</a>'
    return layout("äº¤é…ã‚·ãƒŸãƒ¥ãƒ¬ãƒ¼ã‚·ãƒ§ãƒ³", body, user)


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
    body = f'''<h1>å‡ºç”£ç®¡ç†</h1><form method="post"><div class="grid"><div><label>æ¯çŠ¬</label><select name="dam_id" required>{options}</select></div><div><label>å‡ºç”£æ—¥</label><input name="birth_date" type="date" required></div><div><label>å‡ºç”Ÿé ­æ•°</label><input name="born_count" type="number" min="0" required></div><div><label>ç”Ÿå­˜é ­æ•°</label><input name="alive_count" type="number" min="0" required></div></div><label>ãƒ¡ãƒ¢</label><textarea name="notes"></textarea><button>å‡ºç”£ã‚’ç™»éŒ²</button></form><table><tr><th>å‡ºç”£æ—¥</th><th>æ¯çŠ¬</th><th>å‡ºç”Ÿ</th><th>ç”Ÿå­˜</th><th>ãƒ¡ãƒ¢</th></tr>{rows}</table>'''
    return layout("å‡ºç”£ç®¡ç†", body, user)


@app.post("/modules/births")
def litter_create(dam_id: int = Form(...), birth_date: str = Form(...), born_count: int = Form(...), alive_count: int = Form(...), notes: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dam = session.scalar(select(Dog).where(Dog.id == dam_id, Dog.tenant_id == tenant.id, Dog.sex == "female"))
    if not dam or born_count < 0 or alive_count < 0 or alive_count > born_count:
        raise HTTPException(status_code=400, detail="å‡ºç”£æƒ…å ±ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    born = date.fromisoformat(birth_date)
    session.add(Litter(tenant_id=tenant.id, dam_id=dam.id, birth_date=born, born_count=born_count, alive_count=alive_count, notes=notes.strip() or None))
    related = session.scalar(select(BreedingRecord).where(BreedingRecord.tenant_id == tenant.id, BreedingRecord.dam_id == dam.id, BreedingRecord.mating_date <= born).order_by(BreedingRecord.mating_date.desc()))
    if related:
        related.status = "delivered"
    session.commit()
    return RedirectResponse("/modules/births", status_code=303)


PEDIGREE_LABELS = [
    "ç™»éŒ²ã™ã‚‹çŠ¬", "çˆ¶çŠ¬", "æ¯çŠ¬", "çˆ¶æ–¹ç¥–çˆ¶", "çˆ¶æ–¹ç¥–æ¯", "æ¯æ–¹ç¥–çˆ¶", "æ¯æ–¹ç¥–æ¯",
    "çˆ¶æ–¹ç¥–çˆ¶ã®çˆ¶", "çˆ¶æ–¹ç¥–çˆ¶ã®æ¯", "çˆ¶æ–¹ç¥–æ¯ã®çˆ¶", "çˆ¶æ–¹ç¥–æ¯ã®æ¯",
    "æ¯æ–¹ç¥–çˆ¶ã®çˆ¶", "æ¯æ–¹ç¥–çˆ¶ã®æ¯", "æ¯æ–¹ç¥–æ¯ã®çˆ¶", "æ¯æ–¹ç¥–æ¯ã®æ¯",
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
    "champion": ("CH", "silver", "ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
    "international_champion": ("INT.CH", "gold", "ã‚¤ãƒ³ã‚¿ãƒ¼ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
    "junior_champion": ("J.CH", "rose", "ã‚¸ãƒ¥ãƒ‹ã‚¢ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
    "junior_international_champion": ("J.INT.CH", "purple", "ã‚¸ãƒ¥ãƒ‹ã‚¢ã‚¤ãƒ³ã‚¿ãƒ¼ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
    "international_veteran_champion": ("CIB-V", "purple", "ã‚¤ãƒ³ã‚¿ãƒ¼ãƒŠã‚·ãƒ§ãƒŠãƒ«ãƒ™ãƒ†ãƒ©ãƒ³ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
    "international_show_champion": ("C.I.E.", "gold", "ã‚¤ãƒ³ã‚¿ãƒ¼ãƒŠã‚·ãƒ§ãƒŠãƒ«ã‚·ãƒ§ãƒ¼ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
    "veteran_champion": ("V.CH", "rose", "ãƒ™ãƒ†ãƒ©ãƒ³ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
    "grand_champion": ("G.CH", "blue", "ã‚°ãƒ©ãƒ³ãƒ‰ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³"),
}

# JKCå…¬å¼ã®3ä»£ç¥–è¡€çµ±è¨¼æ˜æ›¸ã«è¨˜è¼‰ã•ã‚Œã‚‹ç•ªå·ã¨é ˜åŸŸã€‚ç•ªå·æ¤œå‡ºãŒä¸€ã¤å¤±æ•—ã—ã¦ã‚‚ã€
# å¾Œç¶šã®çŠ¬ãŒåˆ¥ã®è¦ªæ—æ¬„ã¸ãšã‚Œãªã„ã‚ˆã†å„æ¬„ã‚’ç‹¬ç«‹ã—ã¦èª­ã¿å–ã‚‹ã€‚
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
    """é•·ã„ç§°å·ã‹ã‚‰å…ˆã«æ¶ˆè²»ã—ã€J.CH/INT.CHå†…ã®CHã‚’äºŒé‡è¨ˆä¸Šã—ãªã„ã€‚"""
    remaining = value.upper().replace("ï¼", "/")
    found: list[str] = []
    for key, pattern in TITLE_PATTERNS:
        if re.search(pattern, remaining, re.IGNORECASE):
            found.append(key)
            remaining = re.sub(pattern, " ", remaining, flags=re.IGNORECASE)
    return found


def title_marks(value: str | None) -> str:
    keys = [key for key in (value or "").split(",") if key in TITLE_LABELS]
    return "".join(f'<span class="title-crown crown-{TITLE_LABELS[key][1]}" title="{TITLE_LABELS[key][2]}">â™›<small>{TITLE_LABELS[key][0]}</small></span>' for key in keys)


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
    """å…¨é¢OCRã®åº§æ¨™ã‚’ä¿ã£ãŸã¾ã¾ã€æŒ‡å®šç¯„å›²å†…ã®è¡Œã‚’è¿”ã™ã€‚"""
    # JKCã®çŠ¬åãƒ»ç•ªå·ãƒ»ç§°å·æ¬„ã¯è‹±å­—ã§æ§‹æˆã•ã‚Œã‚‹ã€‚jpnã¨ã®æ··åœ¨èªè­˜ã¯è‹±å­—è¡Œã‚’
    # è½ã¨ã™ã“ã¨ãŒã‚ã‚‹ãŸã‚ã€é…ç½®è§£æã ã‘ã¯engå›ºå®šã§å®Ÿè¡Œã™ã‚‹ã€‚
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
    value = value.upper().replace("â€”", "-").replace("â€“", "-").replace("âˆ’", "-").replace("ï¼", "-").replace("ï¼", "/")
    value = re.sub(r"\b(?:IKC|JKO)\b", "JKC", value)
    # JKC-MS -05878/21 ã®ã‚ˆã†ãªåŸæœ¬ä¸Šã®ç©ºç™½ã‚„ã€å…¨è§’è¨˜å·ã‚’è¨±å®¹ã—ã¦
    # ä¿å­˜æ™‚ã ã‘ JKC-MS-05878/21 ã®çµ±ä¸€å½¢å¼ã«ã™ã‚‹ã€‚
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
    """ç¥–å…ˆç•ªå·ã‚’æ··ãœãªã„ã‚ˆã†ã€æœ¬çŠ¬ã®ç™»éŒ²ç•ªå·æ¬„ã ã‘ã‚’æ‹¡å¤§ã—ã¦èªè­˜ã™ã‚‹ã€‚"""
    width, height = image.size
    crop = image.crop((int(width * .02), int(height * .17), int(width * .34), int(height * .215)))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS)
    value = pytesseract.image_to_string(crop, lang="eng", config="--psm 6", timeout=70)
    return normalize_jkc_number(value)


def jkc_root_sex_birth(image: Image.Image) -> dict[str, str]:
    """æœ¬çŠ¬ã®æ€§åˆ¥ãƒ»ç”Ÿå¹´æœˆæ—¥æ¬„ã ã‘ã‚’æ‹¡å¤§ã—ã€ç¥–å…ˆã®ç”Ÿå¹´æœˆæ—¥æ··å…¥ã‚’é˜²ãã€‚"""
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
    """JKCæœ¬çŠ¬æ¬„ã®çŠ¬ç¨®ã ã‘ã‚’æ‹¡å¤§ã—ã€é€”ä¸­ã§åˆ‡ã‚ŒãŸå…¨é¢OCRã‚ˆã‚Šå„ªå…ˆã™ã‚‹ã€‚"""
    width, height = image.size
    crop = image.crop((int(width * .02), int(height * .13), int(width * .45), int(height * .20)))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS)
    value = pytesseract.image_to_string(crop, lang="eng", config="--psm 6", timeout=70).upper()
    # å°ã•ãªè‹±å­—ãƒ©ãƒ™ãƒ« Breed ã¯ BRE / PEE / EU ã«å´©ã‚Œã‚„ã™ã„ã€‚ä¸€æ–¹ã€å³å´ã®
    # çŠ¬ç¨®åã¯å¤§ããæ˜ç­ãªãŸã‚ã€JKCã®çŠ¬ç¨®å°‚ç”¨é ˜åŸŸå†…ã«é™ã£ã¦å„å´©ã‚Œã‚’è¨±å®¹ã™ã‚‹ã€‚
    match = re.search(r"(?:BRE(?:ED|EDS)?|PEE|EU)[^A-Z\n]{0,8}([A-Z][A-Z .'-]{2,60})", value)
    if not match:
        # MINIATUREã¯ç´°ã„æ´»å­—ã®ãŸã‚MINIATU!/MINTATç­‰ã¸åˆ†å‰²ã•ã‚Œã‚„ã™ã„ã€‚
        # SCHNAUZERã¨ã®çµ„ã¿åˆã‚ã›ã‚’ç¢ºèªã§ãã‚‹å ´åˆã®ã¿å…¬å¼è¡¨è¨˜ã¸è£œæ­£ã™ã‚‹ã€‚
        spatial_value = " ".join(ocr_spatial_lines(image, (.02, .12, .42, .20))).upper()
        combined = value + " " + spatial_value
        if "SCHNAUZER" in combined and re.search(r"MINI|MINT", combined):
            return "MINIATURE SCHNAUZER"
        return ""
    breed = re.sub(r"\s{2,}", " ", match.group(1)).strip(" .-")
    parts = breed.split()
    # å·¦éš£ã®æ—¥æœ¬èªãƒ©ãƒ™ãƒ«ã®æ–­ç‰‡ãŒå˜ç‹¬1æ–‡å­—ï¼ˆä¾‹: "S MINIATURE ..."ï¼‰ã§
    # æ··ã–ã‚‹ã“ã¨ãŒã‚ã‚‹ãŸã‚ã€çŠ¬ç¨®æœ¬ä½“ãŒè¤‡æ•°èªã‚ã‚‹å ´åˆã ã‘é™¤å»ã™ã‚‹ã€‚
    if len(parts) >= 3 and len(parts[0]) == 1:
        breed = " ".join(parts[1:])
    return breed if breed not in {"BREED", "NAME OF DOG"} else ""


def normalize_pedigree_color(value: str) -> str:
    """è¡€çµ±æ›¸ã®æ­£å¼è¡¨è¨˜ãƒ»ç•¥è¨˜ãƒ»OCRã®ç©ºç™½æºã‚Œã‚’ç®¡ç†ç”¨è¡¨è¨˜ã¸çµ±ä¸€ã™ã‚‹ã€‚"""
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
    """æœ¬çŠ¬æ¬„ã ã‘ã‚’èª­ã¿ã€ç¥–å…ˆæ¬„ã®ç•ªå·ã‚„å›£ä½“åã‚’æ··å…¥ã•ã›ãªã„ã€‚"""
    def lines_in(box: tuple[float, float, float, float]) -> list[str]:
        if records is None:
            return ocr_spatial_lines(image, box)
        left, top, right, bottom = box
        return [value for x, y, value in records if left <= x <= right and top <= y <= bottom]

    lines = lines_in((.02, .08, .68, .28))
    value = "\n".join(lines)
    result = {"organization": "JKC", "country": "æ—¥æœ¬"}
    trusted_identity = jkc_root_sex_birth(image)

    trusted_breed = jkc_root_breed(image)
    breed_match = re.search(r"(?:^|\n)\s*(?:BREED|çŠ¬ç¨®)\s*[:ï¼š]?\s*([A-Z][A-Z .'-]{2,60})", value, re.IGNORECASE)
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
    # FEMALEã®å…ˆé ­Fã¯ã€ç½«ç·šã‚„æ—¥æœ¬èªãƒ©ãƒ™ãƒ«ã®å½±éŸ¿ã§R/Eã¨ã—ã¦èª¤èªã•ã‚Œã‚„ã™ã„ã€‚
    # MALEã‚ˆã‚Šå…ˆã«åˆ¤å®šã—ã€FEMALEã®ä¸€éƒ¨ã‚’ç‰¡ã¨èª¤åˆ¤å®šã—ãªã„ã€‚
    if re.search(r"\b(?:FEMALE|REMALE|EMALE)\b", upper_value):
        result["sex"] = "female"
    elif re.search(r"\bMALE\b", upper_value):
        result["sex"] = "male"

    # æ—¥æœ¬èªãƒ©ãƒ™ãƒ«ã€Œå¹´ãƒ»æœˆãƒ»æ—¥ã€ã¯OCRã§ 47/48ãƒ»A/Hãƒ»0/H ã«å´©ã‚Œã‚„ã™ã„ã€‚
    # å¹´ãƒãƒ¼ã‚«ãƒ¼ã®2æ–‡å­—ã‚’æœˆã«æ··ãœãªã„JKCå°‚ç”¨ãƒ‘ã‚¿ãƒ¼ãƒ³ã‚’æœ€å„ªå…ˆã™ã‚‹ã€‚
    birth = re.search(r"(20\d{2})\s*(?:å¹´|4\d?)\s*(1[0-2]|[1-9])\s*(?:æœˆ|[AH])?\s*(3[01]|[12]\d|[1-9])\s*(?:æ—¥|[HO0])?", value)
    if not birth:
        birth = re.search(r"(20\d{2})\s*å¹´\s*(1[0-2]|[1-9])\s*æœˆ\s*(3[01]|[12]\d|[1-9])\s*æ—¥", value)
    if birth:
        year, month, day = map(int, birth.groups())
        try:
            result["birth_date"] = date(year, month, day).isoformat()
        except ValueError:
            pass
    result.update(trusted_identity)
    # æœ¬çŠ¬ã®ç§°å·ã¯çŠ¬åã®ç›´ä¸Šã ã‘ã‹ã‚‰å–å¾—ã™ã‚‹ã€‚åºƒã„æœ¬äººæƒ…å ±é ˜åŸŸã«ã¯
    # å³å´7ç•ªç¥–å…ˆã®INT.CHç­‰ãŒå…¥ã‚Šå¾—ã‚‹ãŸã‚ã€æœ¬äººã¸èª¤ä»˜ä¸ã—ãªã„ã€‚
    root_title_lines = lines_in((.25, .035, .76, .115))
    title_keys = extract_title_keys("\n".join(root_title_lines))
    if title_keys:
        result["titles"] = ",".join(title_keys)
    return result


def jkc_slot_text(image: Image.Image) -> str:
    """JKCã®ç•ªå·ä»˜ã15æ¬„ã‚’ç‹¬ç«‹è§£æã—ã€æ¬ è½ã«ã‚ˆã‚‹è¡€ç¸ä½ç½®ã®é€£é–ãšã‚Œã‚’é˜²ãã€‚"""
    records = ocr_spatial_records(image)
    metadata = jkc_root_metadata(image, records)
    results: list[str] = [f"[[PEDIGREE_META]] {json.dumps(metadata, ensure_ascii=False)}"]

    def crop_text(box: tuple[float, float, float, float], psm: int = 6) -> str:
        width, height = image.size
        left, top, right, bottom = box
        # 3å€åŒ–ã¨å˜ä¸€ãƒ–ãƒ­ãƒƒã‚¯è§£æã§ã€å…¨é¢OCRãŒè½ã¨ã—ãŸçˆ¶æ¯æ¬„ã‚‚å†è©¦è¡Œã™ã‚‹ã€‚
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
            # è¡¨ã®ç½«ç·šãŒ | ã‚„ ] ã¨ã—ã¦çŠ¬åå…ˆé ­ã«ä»˜ç€ã—ãŸã‚±ãƒ¼ã‚¹ã€‚
            compact = "\n".join(lines)
            direct = re.search(r"(?:^|\n)[^A-Z\n]*([A-Z][A-Z0-9'â€™* .-]{4,})\n[^\n]*(?:JKC|KC)\s*-?\s*MS", compact)
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
            # ç™»éŒ²ç•ªå·ã ã‘ãŒèª­ã‚ãªã„å ´åˆã‚‚ã€æ¬„ä¸Šéƒ¨ã®çŠ¬åã¯å›åã™ã‚‹ã€‚
            before_registration = [record for record in local if record[1] < top + (bottom - top) * .58]
            color_records = [record[2] for record in local]
        possible = []
        for _, candidate_y, candidate in before_registration:
            candidate = candidate.rsplit("|", 1)[-1]
            clean_name, _ = split_name_titles(candidate)
            upper = clean_name.upper()
            if len(clean_name) >= 5 and re.search(r"[A-Z]{4}", upper) and not any(word in upper for word in PEDIGREE_EXCLUDE) and not re.search(r"\b(?:SIRE|DAM|CDI?|DNA|SLT|PPR|BLK|MALE|FEMALE|G\.?G\.?)\b", upper) and not re.fullmatch(r"[A-Z. ]*CH[A-Z0-9/., ()-]*", upper):
                possible.append((candidate_y, clean_name))
        # ç™»éŒ²ç•ªå·ã«æœ€ã‚‚è¿‘ã„ç›´å‰è¡ŒãŒçŠ¬åã€‚é•·ã•å„ªå…ˆã ã¨éš£æ¥æ¬„ã®æ–‡å­—ã‚’é¸ã³ã‚„ã™ã„ã€‚
        name = max(possible, key=lambda item: item[0])[1] if possible else ""
        name_y = max((item[0] for item in possible), default=bottom)
        title_context = "\n".join(record[2] for record in local if record[1] < name_y)
        titles = extract_title_keys(title_context)
        # å‰ã®ä¸–ä»£æ¬„ã®æ¯›è‰²ãŒçŸ©å½¢ä¸Šç«¯ã¸å…¥ã‚‹å ´åˆãŒã‚ã‚‹ãŸã‚ã€æœ¬çŠ¬ã®ç™»éŒ²ç•ªå·ã‚ˆã‚Š
        # ä¸‹ã«ã‚ã‚‹æ¯›è‰²ã‚’å„ªå…ˆã—ã€éš£æ¥çŠ¬ã®è‰²ã‚’å–ã‚Šè¾¼ã¾ãªã„ã€‚
        local_color = normalize_pedigree_color("\n".join(color_records))
        # å…¨é¢åº§æ¨™OCRã§åå‰ã¨æ¯›è‰²ãŒå–ã‚ŒãŸæ¬„ã¯å†OCRã—ãªã„ã€‚å¾“æ¥ã¯å…¨14æ¬„ã‚’
        # å¸¸ã«æ‹¡å¤§OCRã—ã¦ã„ãŸãŸã‚ã€ä½æ€§èƒ½ãªæœ¬ç•ªç’°å¢ƒã§å‡¦ç†ä¸Šé™ã«é”ã—ã¦ã„ãŸã€‚
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
        # ç¸¦ç½«ç·šã‚’ I ã¨èª¤èªã—ãŸçŠ¬åã ã‘ã‚’å®‰å…¨ã«è£œæ­£ã™ã‚‹ã€‚
        name = re.sub(r"(?<=[A-Z])\](?=[A-Z])", "I", name.upper())
        # JKCçŠ¬èˆåã®æ‰€æœ‰æ ¼ JPâ€™S ã¯ã€ç´°ã„ã‚¢ãƒã‚¹ãƒˆãƒ­ãƒ•ã‚£ãŒ Â°ãƒ»*ãƒ»' ã¨
        # èªè­˜ã•ã‚Œã‚„ã™ã„ã€‚æ„å‘³ãŒä¸€æ„ã«å®šã¾ã‚‹ JP + è¨˜å· + S ã ã‘ã‚’æ­£è¦åŒ–ã™ã‚‹ã€‚
        name = re.sub(r"\bJP\s*[â€œâ€Â°*'`Â´â€™â€˜]{1,3}\s*S\b", "JPâ€™S", name, flags=re.IGNORECASE)
        # åŒã˜è¡€çµ±æ›¸å†…ã®æœ¬çŠ¬åã«å®Œå…¨ä¸€è‡´ã™ã‚‹èªåˆ—ãŒã‚ã‚Œã°ã€OCRã§åˆ†æ–­ã•ã‚ŒãŸ
        # "NI INA" ã®ã‚ˆã†ãªç©ºç™½ã ã‘ã‚’åŸè¡¨è¨˜ã¸æˆ»ã™ã€‚
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
    """JKCè¼¸å…¥çŠ¬ç™»éŒ²è¨¼æ˜æ›¸ã¯çˆ¶æ¯ã ã‘ã®æ›¸å¼ãªã®ã§ã€15æ¬„OCRã‚’å®Ÿè¡Œã—ãªã„ã€‚"""
    upper = full_text.upper().replace("Â°", "â€™").replace("*", "â€™")
    metadata: dict[str, str] = {"organization": "JKC", "country": "æ—¥æœ¬"}
    jkc = re.search(r"JKC\s*[-â€” ]?\s*([A-Z]{1,4})\s*[-â€” ]?\s*(\d{4,6})\s*/\s*(\d{2})(?:\s*[-â€” ]?\s*([A-Z1I]))?", upper)
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
    birth = re.search(r"(20\d{2})\s*(?:å¹´|4[A-Z0-9]?)?\s*(1[0-2]|[1-9])\s*(?:æœˆ|A)?\s*(3[01]|[12]\d|[1-9])\s*(?:æ—¥|H)?", full_text, re.IGNORECASE)
    if birth:
        try:
            metadata["birth_date"] = date(*map(int, birth.groups())).isoformat()
        except ValueError:
            pass
    dog_name = ""
    name_match = re.search(r"(?:CH\s*\([^\n)]{2,6}\)\s*)?\n?\s*([A-Z][A-Z0-9'â€™ .-]{5,80})\s*\n\s*(?:BREED|Breed)", upper, re.IGNORECASE)
    if name_match:
        dog_name = name_match.group(1).strip(" .-")
    if not dog_name:
        name_match = re.search(r"(?:PLASMA|[A-Z]{3,})[- ][A-Z0-9'â€™ -]{3,}\b", upper)
        dog_name = name_match.group(0).strip(" .-") if name_match else ""
    dog_name = re.sub(r"\bJP\s*[Â°*'`Â´â€™â€˜]\s*S\b", "JPâ€™S", dog_name)
    dog_name = re.sub(r"\bMS\s*[Â°*'`Â´â€™â€˜]\s*S\b", "MSâ€™S", dog_name)
    root_titles = extract_title_keys(upper.split(dog_name, 1)[0][-100:] if dog_name and dog_name in upper else "")

    def parent_after(label: str) -> tuple[str, list[str], str]:
        end_label = "DAM" if label == "SIRE" else "JAPAN KENNEL CLUB"
        section_match = re.search(rf"\b{label}\b([\s\S]*?)(?=\b{end_label}\b)", upper)
        section = section_match.group(1) if section_match else ""
        match = re.search(r"([A-Z][A-Z0-9'â€™ .-]{5,80})\s*\n\s*KATH\d+", section)
        if not match:
            return "", [], ""
        name = re.sub(r"\bMS\s*[Â°*'`Â´â€™â€˜]\s*S\b", "MSâ€™S", match.group(1).strip(" .-"))
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
    """PDFã¾ãŸã¯å†™çœŸã‹ã‚‰æ–‡å­—ã‚’æŠ½å‡ºã™ã‚‹ã€‚ã‚¹ã‚­ãƒ£ãƒ³PDFã¯1ãƒšãƒ¼ã‚¸ç›®ã‚’ç”»åƒåŒ–ã—ã¦OCRã™ã‚‹ã€‚"""
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
        if re.search(r"REGISTRATION\s+CERTIFICATE\s+FOR\s+IMPORTED\s+DOG|è¼¸å…¥çŠ¬ç™»éŒ²è¨¼æ˜æ›¸", full_text, re.IGNORECASE):
            full_text += "\n" + imported_dog_certificate_text(image, full_text)
        elif re.search(r"JAPAN\s+KENNEL\s+CLUB|JKC[-â€” ]?MS", full_text, re.IGNORECASE):
            full_text += "\n" + jkc_slot_text(image)
        return full_text


PEDIGREE_DOCUMENT_TYPES = {
    "domestic_pedigree": "å›½å†…è¡€çµ±è¨¼æ˜æ›¸",
    "import_registration": "è¼¸å…¥çŠ¬ç™»éŒ²è¨¼æ˜æ›¸ï¼ˆæ—¥æœ¬ï¼‰",
    "export_pedigree": "å‡ºç”Ÿå›½ãƒ»è¼¸å‡ºè¡€çµ±è¨¼æ˜æ›¸",
    "updated_pedigree": "æ›´æ–°å¾Œã®è¡€çµ±è¨¼æ˜æ›¸",
    "other": "ãã®ä»–",
}


def pedigree_document_metadata(raw_text: str, metadata: dict[str, str]) -> dict[str, str]:
    """åŸæœ¬å˜ä½ã®ç•ªå·ã‚’åˆ¤å®šã™ã‚‹ã€‚çŠ¬æœ¬ä½“ã®å›½å†…ç•ªå·ã¨æµ·å¤–ç•ªå·ã¯æ··ãœãªã„ã€‚"""
    upper = raw_text.upper().replace("â€™", "'")
    is_import = "REGISTRATION CERTIFICATE FOR IMPORTED DOG" in upper or "è¼¸å…¥çŠ¬ç™»éŒ²è¨¼æ˜æ›¸" in raw_text
    is_export = "CERTIFIED EXPORT PEDIGREE" in upper or "EXPORT PEDIGREE" in upper
    kath = re.search(r"\bKATH\s*[- ]?\s*(\d{7,12})\b", upper)
    jkc = re.search(r"\bJKC\s*[-â€” ]?\s*([A-Z]{1,4})\s*[-â€” ]?\s*(\d{4,6})\s*/\s*(\d{2})(?:\s*[-â€” ]?\s*([A-Z1]))?", upper)
    # å›½å†…ã®é€šå¸¸è¡€çµ±æ›¸ã¸OCRãŒæ¨æ¸¬ã—ãŸ -K/-P ç­‰ã‚’ä»˜ã‘ãªã„ã€‚
    # è¼¸å…¥çŠ¬ç™»éŒ²è¨¼æ˜æ›¸ã§æ˜è¨˜ã•ã‚Œã‚‹ -Iï¼ˆOCRã§ã¯ -1ï¼‰ã ã‘ã‚’è¨±å¯ã™ã‚‹ã€‚
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
        return {"type": "import_registration", "registration_no": jkc_no or metadata.get("pedigree_no", ""), "organization": "JKC", "country": "æ—¥æœ¬", "domestic_no": jkc_no, "origin_no": kath_no, "origin_country": "ã‚¿ã‚¤", "origin_organization": "KCTH", "primary": "true"}
    if is_export or kath_no:
        return {"type": "export_pedigree", "registration_no": kath_no or metadata.get("pedigree_no", ""), "organization": "KCTH", "country": "ã‚¿ã‚¤", "domestic_no": "", "origin_no": kath_no, "origin_country": "ã‚¿ã‚¤", "origin_organization": "KCTH", "primary": "false"}
    organization = metadata.get("organization", "")
    country = metadata.get("country", "")
    return {"type": "domestic_pedigree", "registration_no": jkc_no or metadata.get("pedigree_no", ""), "organization": organization, "country": country, "domestic_no": jkc_no or metadata.get("pedigree_no", ""), "origin_no": "", "origin_country": "", "origin_organization": "", "primary": "true" if organization.upper() == "JKC" else "false"}


def pedigree_candidates(raw_text: str) -> tuple[dict[str, str], list[str], list[list[str]], list[str]]:
    """OCRçµæœã‹ã‚‰æœ¬äººæƒ…å ±ã¨è¡€çµ±åå€™è£œã‚’ä½œã‚‹ã€‚æœ€çµ‚ç¢ºå®šå‰ã«å¿…ãšç·¨é›†ç”»é¢ã‚’è¡¨ç¤ºã™ã‚‹ã€‚"""
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
        "breed": r"(?:BREED|çŠ¬ç¨®)\s*[:ï¼š]?\s*([A-Z][A-Z .'-]{2,60})",
        "pedigree_no": r"(?:REG(?:ISTRATION)?\.?\s*(?:NO\.?|NUMBER)?|ç™»éŒ²ç•ªå·)\s*[:ï¼š]?\s*([A-Z0-9\-/]+)",
        "microchip_no": r"(?:MICROCHIP|ãƒã‚¤ã‚¯ãƒ­ãƒãƒƒãƒ—)\s*(?:NO\.?)?\s*[:ï¼š]?\s*([0-9]{10,20})",
        "birth_date": r"(?:DATE OF BIRTH|BORN|ç”Ÿå¹´æœˆæ—¥)\s*[:ï¼š]?\s*(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        "color": r"(?:COLOR|COLOUR|æ¯›è‰²)\s*[:ï¼š]?\s*([A-Z& ]{3,30})",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            metadata[key] = match.group(1).strip().replace(".", "-").replace("/", "-") if key == "birth_date" else match.group(1).strip()
    # "Registered"ã®æœ«å°¾ãªã©ã€ç•ªå·ã§ã¯ãªã„è‹±å­—ã ã‘ã®èª¤æŠ½å‡ºã‚’ç ´æ£„ã™ã‚‹ã€‚
    if "pedigree_no" in metadata and not re.search(r"\d", metadata["pedigree_no"]):
        metadata.pop("pedigree_no")
    if "pedigree_no" in metadata and re.search(r"(?:J|I)?KC", metadata["pedigree_no"], re.IGNORECASE):
        normalized_jkc = normalize_jkc_number(metadata["pedigree_no"])
        if normalized_jkc:
            metadata["pedigree_no"] = normalized_jkc
        else:
            metadata.pop("pedigree_no")
    if "pedigree_no" not in metadata:
        match = re.search(r"\b(JKC[-â€” ]?MS\s*[-â€”]?\s*\d{5}/\d{2})\b", clean, re.IGNORECASE)
        if match:
            metadata["pedigree_no"] = re.sub(r"\s+", "", match.group(1)).replace("â€”", "-")
    if "microchip_no" not in metadata:
        match = re.search(r"\bID\s*([0-9]{15})\b", clean, re.IGNORECASE)
        if match:
            metadata["microchip_no"] = match.group(1)
    if "birth_date" not in metadata:
        match = re.search(r"(20\d{2})\s*å¹´\s*(\d{1,2})\s*æœˆ\s*(\d{1,2})\s*æ—¥", clean)
        if match:
            metadata["birth_date"] = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    organizations = ["JKC", "FCI", "AKC", "KC", "VDH", "ENCI", "LOF", "RSCE", "CBKC", "CKC", "ANKC", "NZKC"]
    found_orgs = [org for org in organizations if re.search(rf"\b{re.escape(org)}\b", clean, re.IGNORECASE)]
    if found_orgs:
        metadata["organization"] = " / ".join(found_orgs)
    countries = {
        "JAPAN": "æ—¥æœ¬", "UNITED STATES": "ã‚¢ãƒ¡ãƒªã‚«", "USA": "ã‚¢ãƒ¡ãƒªã‚«", "GERMANY": "ãƒ‰ã‚¤ãƒ„",
        "ITALY": "ã‚¤ã‚¿ãƒªã‚¢", "FRANCE": "ãƒ•ãƒ©ãƒ³ã‚¹", "SPAIN": "ã‚¹ãƒšã‚¤ãƒ³", "PORTUGAL": "ãƒãƒ«ãƒˆã‚¬ãƒ«",
        "NETHERLANDS": "ã‚ªãƒ©ãƒ³ãƒ€", "POLAND": "ãƒãƒ¼ãƒ©ãƒ³ãƒ‰", "CZECH": "ãƒã‚§ã‚³", "HUNGARY": "ãƒãƒ³ã‚¬ãƒªãƒ¼",
        "RUSSIA": "ãƒ­ã‚·ã‚¢", "THAILAND": "ã‚¿ã‚¤", "INDONESIA": "ã‚¤ãƒ³ãƒ‰ãƒã‚·ã‚¢", "AUSTRALIA": "ã‚ªãƒ¼ã‚¹ãƒˆãƒ©ãƒªã‚¢",
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
        value = re.sub(r"^[\dâ‘¡-â‘®()\[\].:ï¼š\-\s]+", "", line).strip(" |;,")
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
        raise HTTPException(status_code=400, detail="å¯¾è±¡çŠ¬ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
    return dog


def reuse_registered_pedigree(
    session: Session,
    tenant_id: int,
    names: list[str],
    titles: list[list[str]],
    colors: list[str],
) -> tuple[list[str], list[list[str]], list[str], str]:
    """çˆ¶æ¯ãŒç™»éŒ²æ¸ˆã¿ãªã‚‰ã€äººãŒç¢ºèªæ¸ˆã¿ã®è¡€çµ±ã‚’åŒè…¹çŠ¬ã¸å†åˆ©ç”¨ã™ã‚‹ã€‚"""
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
    return names, titles, colors, "çˆ¶æ¯ãŒä¸€è‡´ã—ãŸç™»éŒ²æ¸ˆã¿è¡€çµ±ã‚’å†åˆ©ç”¨ã—ã¾ã—ãŸã€‚å…ˆç¥–æƒ…å ±ã‚‚åŸæœ¬ã¨ç…§åˆã—ã¦ãã ã•ã„ã€‚"


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
            messages.append(f"{name}: ç‰‡è¦ªã®æ¤œæŸ»æƒ…å ±ãŒä¸è¶³")
        elif sire == "carrier" and dam == "carrier":
            messages.append(f"{name}: ã‚¢ãƒ•ã‚§ã‚¯ãƒ†ãƒƒãƒ‰25%ãƒ»ã‚­ãƒ£ãƒªã‚¢50%ã®å¯èƒ½æ€§")
        elif "affected" in {sire, dam} and "carrier" in {sire, dam}:
            messages.append(f"{name}: ã‚¢ãƒ•ã‚§ã‚¯ãƒ†ãƒƒãƒ‰50%ã®å¯èƒ½æ€§")
        elif sire == "affected" and dam == "affected":
            messages.append(f"{name}: ã‚¢ãƒ•ã‚§ã‚¯ãƒ†ãƒƒãƒ‰100%ã®å¯èƒ½æ€§")
        elif "affected" in {sire, dam}:
            messages.append(f"{name}: å…¨é ­ã‚­ãƒ£ãƒªã‚¢ã¨ãªã‚‹å¯èƒ½æ€§")
        else:
            messages.append(f"{name}: ã‚¢ãƒ•ã‚§ã‚¯ãƒ†ãƒƒãƒ‰ç™ºç—‡ãƒªã‚¹ã‚¯ã¯ä½ã„çµ„ã¿åˆã‚ã›")
    return messages


@app.get("/modules/health", response_class=HTMLResponse)
def health_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    category_labels = {"puppy": "å­çŠ¬", "parent": "è¦ªçŠ¬", "external": "å¤–éƒ¨çŠ¬"}
    status_labels = {"resident": "åœ¨ç±ä¸­", "reserved": "äºˆç´„æ¸ˆã¿ï¼ˆåœ¨ç±ä¸­ï¼‰", "retired": "å¼•é€€ï¼ˆåœ¨ç±ä¸­ï¼‰", "delivered": "è²©å£²æ¸ˆã¿", "transferred": "è­²æ¸¡æ¸ˆã¿"}
    options = "".join(
        f'<option value="{d.id}" data-nonresident="{str(d.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [d.call_name, d.registered_name, d.breed, category_labels.get(d.category, d.category), status_labels.get(d.status, d.status)])))}">'
        f'{html.escape(d.call_name)}ï½œ{html.escape(category_labels.get(d.category, d.category))}'
        f'ï½œ{html.escape(status_labels.get(d.status, d.status))}{"ï½œ" + html.escape(d.registered_name) if d.registered_name else ""}</option>' for d in dogs
    )

    def dog_picker(key: str) -> str:
        return f'''<div class="dog-picker"><label for="{key}-dog-search">å¯¾è±¡çŠ¬ã‚’æ¤œç´¢</label>
        <input id="{key}-dog-search" class="dog-search" type="search" data-dog-select="{key}-dog-select" placeholder="å‘¼ã³åãƒ»è¡€çµ±æ›¸åãƒ»çŠ¬ç¨®ãƒ»åŒºåˆ†ã§æ¤œç´¢" autocomplete="off">
        <label class="dog-search-all"><input type="checkbox" data-dog-all="{key}-dog-select"> è²©å£²æ¸ˆã¿ãƒ»è­²æ¸¡æ¸ˆã¿ã®çŠ¬ã‚‚æ¤œç´¢ã™ã‚‹</label>
        <small class="dog-search-count">å…¨{len(dogs)}é ­ã‹ã‚‰é¸æŠ</small>
        <label for="{key}-dog-select">å¯¾è±¡çŠ¬</label><select id="{key}-dog-select" name="dog_id" required>{options}</select></div>'''

    dog_search_script = '''<style>.dog-picker{grid-column:span 2;min-width:0}.dog-picker .dog-search,.dog-picker select{max-width:100%}.dog-search-all{display:flex;align-items:center;gap:7px;margin:8px 0 3px;font-weight:500}.dog-search-all input{width:auto;margin:0}.dog-search-count{display:block;margin-top:5px;color:#806b72}.dog-picker select{margin-top:2px}@media(max-width:700px){.dog-picker{grid-column:1/-1}}</style>
    <script>document.querySelectorAll('.dog-search').forEach(function(input){
      var select=document.getElementById(input.dataset.dogSelect); var original=Array.from(select.options).map(function(option){return option.cloneNode(true)}); var count=input.parentElement.querySelector('.dog-search-count'); var includeAll=input.parentElement.querySelector('[data-dog-all]');
      function filterDogs(){var query=input.value.trim().toLowerCase(); var current=select.value; var matches=original.filter(function(option){var statusMatch=includeAll.checked || option.dataset.nonresident!=='true'; var textMatch=!query || (option.dataset.search || option.textContent).toLowerCase().includes(query); return statusMatch && textMatch}); select.replaceChildren.apply(select,matches.map(function(option){return option.cloneNode(true)})); if(matches.some(function(option){return option.value===current}))select.value=current; count.textContent=(includeAll.checked?'åœ¨ç±çŠ¬ä»¥å¤–ã‚’å«ã‚€ ':'åœ¨ç±çŠ¬ ') + matches.length+'é ­ã‹ã‚‰é¸æŠ';}
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
    body = f'''<h1>å¥åº·ç®¡ç†</h1><p>çŠ¬ã”ã¨ã®å¥åº·çŠ¶æ…‹ã¨ã€æœªæ¥ç¨®ãƒ»æœªå—è¨ºã‚’ã¾ã¨ã‚ã¦ç¢ºèªã§ãã¾ã™ã€‚</p>
    <div class="grid"><a class="module" href="/modules/health/weights"><h3>ä½“é‡ç®¡ç†</h3><p>å­çŠ¬ãƒ»è¦ªçŠ¬ã®ä½“é‡æ¨ç§»ã‚’è¨˜éŒ²</p></a>
    <a class="module" href="/modules/health/vaccinations"><h3>ãƒ¯ã‚¯ãƒãƒ³ç®¡ç†</h3><p>ç‹‚çŠ¬ç—… æœªæ¥ç¨® {len(set(parent_ids) - rabies_vaccinated_ids)}é ­ ï¼ æ··åˆ æœªæ¥ç¨® {len(set(parent_ids) - mixed_vaccinated_ids)}é ­</p></a>
    <a class="module" href="/modules/health/checkups"><h3>å¥è¨ºç®¡ç†</h3><p>ä»Šå¹´åº¦æœªå—è¨º {len(set(parent_ids) - checked_ids)}é ­</p></a>
    <a class="module" href="/modules/health/medications"><h3>æŠ•è–¬ç®¡ç†</h3><p>æŠ•è–¬è¨˜éŒ² {len(medications)}ä»¶</p></a>
    <a class="module" href="/modules/health/diseases"><h3>ç—…æ­´ç®¡ç†</h3><p>ç—…æ­´è¨˜éŒ² {len(diseases)}ä»¶</p></a>
    <a class="module" href="/modules/health/foods"><h3>ãƒ•ãƒ¼ãƒ‰ç®¡ç†</h3><p>åˆ©ç”¨å±¥æ­´ {len(foods)}ä»¶</p></a>
    <a class="module" href="/modules/health/owner-records"><h3>ã‚ªãƒ¼ãƒŠãƒ¼å…±æœ‰è¨˜éŒ²</h3><p>å…±æœ‰ä¸­ {owner_shared_count}ä»¶ï¼ˆé–²è¦§å°‚ç”¨ï¼‰</p></a></div>
    <h2 id="checks">ç°¡æ˜“å¥åº·è¨˜éŒ²</h2><form method="post" action="/modules/health/record"><div class="grid">{dog_picker("health")}<div><label>è¨˜éŒ²æ—¥</label><input type="date" name="record_date" required></div><div><label>ç¨®é¡</label><select name="category"><option value="weight">ä½“é‡</option><option value="treatment">è¨ºç™‚</option></select></div><div><label>ä½“é‡ï¼ˆkgï¼‰</label><input type="number" step="0.01" min="0" name="weight_kg"></div><div><label>å‹•ç‰©ç—…é™¢</label><input name="clinic"></div></div><label>çµæœãƒ»ãƒ¡ãƒ¢</label><textarea name="notes"></textarea><button>è¨˜éŒ²ã™ã‚‹</button></form><table><tr><th>æ—¥ä»˜</th><th>çŠ¬</th><th>ç¨®é¡</th><th>ä½“é‡kg</th><th>ãƒ¡ãƒ¢</th></tr>{health_rows}</table>
    {dog_search_script}'''
    return layout("å¥åº·ç®¡ç†", body, user)


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
    category_labels = {"weight": "ä½“é‡", "vaccination": "ãƒ¯ã‚¯ãƒãƒ³", "checkup": "å¥è¨º", "medication": "æŠ•è–¬", "disease": "ç—…æ­´", "food": "ãƒ•ãƒ¼ãƒ‰", "other": "ãã®ä»–"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id); owner = session.get(User, item.owner_id)
        if not dog: continue
        attachment = f'<a class="button secondary" href="/modules/health/owner-records/{item.id}/attachment" target="_blank">è¨¼æ˜æ›¸ãƒ»æ·»ä»˜ã‚’è¦‹ã‚‹</a>' if item.attachment_data else ""
        rows += f'''<tr><td>{item.recorded_on}</td><td>{html.escape(dog.call_name)}</td><td>{category_labels.get(item.category, "ãã®ä»–")}</td><td>{html.escape(item.title)}</td><td>{html.escape(item.value or "-")}</td><td style="white-space:pre-wrap">{html.escape(item.details or "-")}<br>{attachment}</td><td>{html.escape(owner.name if owner else "ã‚ªãƒ¼ãƒŠãƒ¼")}</td><td><span class="badge">é–²è¦§ã®ã¿</span></td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†ã¸æˆ»ã‚‹</a><h1>ã‚ªãƒ¼ãƒŠãƒ¼å…±æœ‰è¨˜éŒ²</h1>
    <div class="tenant"><p>ã‚ªãƒ¼ãƒŠãƒ¼æ§˜ãŒã€Œãƒ–ãƒªãƒ¼ãƒ€ãƒ¼ã¸å…±æœ‰ã™ã‚‹ã€ã«è¨­å®šã—ãŸå¥åº·è¨˜éŒ²ã§ã™ã€‚</p><p>å…±æœ‰å…ˆï¼š<strong>{html.escape(tenant.name)}</strong> ï¼ ãƒ–ãƒªãƒ¼ãƒ€ãƒ¼å´ã‹ã‚‰å¤‰æ›´ãƒ»å‰Šé™¤ã¯ã§ãã¾ã›ã‚“ã€‚</p></div>
    <div style="overflow-x:auto"><table><tr><th>è¨˜éŒ²æ—¥</th><th>çŠ¬</th><th>ã‚«ãƒ†ã‚´ãƒªãƒ¼</th><th>è¨˜éŒ²å†…å®¹</th><th>æ•°å€¤ãƒ»è£œè¶³</th><th>è©³ç´°</th><th>å…¥åŠ›è€…</th><th>æ¨©é™</th></tr>{rows or '<tr><td colspan="8">ã‚ªãƒ¼ãƒŠãƒ¼æ§˜ã‹ã‚‰å…±æœ‰ã•ã‚ŒãŸè¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></div>'''
    return layout("ã‚ªãƒ¼ãƒŠãƒ¼å…±æœ‰è¨˜éŒ²", body, user)


@app.get("/modules/health/owner-records/{record_id}/attachment")
def health_owner_record_attachment(record_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    _, tenant = access
    item = session.scalar(select(OwnerHealthRecord).where(OwnerHealthRecord.id == record_id, OwnerHealthRecord.tenant_id == tenant.id, OwnerHealthRecord.share_to_breeder.is_(True)))
    if not item or not item.attachment_data: raise HTTPException(status_code=404, detail="å…±æœ‰ã•ã‚ŒãŸè¨¼æ˜æ›¸ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
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
    food_options = '<option value="">é¸æŠã—ã¦ãã ã•ã„</option>' + "".join(
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
            parts.append(f"é£Ÿäº‹ {item.meal_amount_g:g}g")
        if item.food_name:
            parts.append(f"ãƒ•ãƒ¼ãƒ‰ï¼š{html.escape(item.food_name)}")
        if item.stool_condition:
            parts.append(f"ã†ã‚“ã¡ï¼š{html.escape(item.stool_condition)}")
        if item.health_condition:
            parts.append(f"å¥åº·ï¼š{html.escape(item.health_condition)}")
        return "<br>".join(parts) or "-"

    def dog_card(dog: Dog) -> str:
            items = by_dog.get(dog.id, [])
            rows = ""
            for item in items[:10]:
                share = health_share_for(session, "health", item.id)
                is_shared = bool(share and share.owner_visible)
                rows += f'''<tr><td>{recorded_time(item)}</td><td>{item.weight_kg if item.weight_kg is not None else "-"} kg</td><td>{condition_detail(item)}</td><td>{html.escape(item.notes or "-")}</td><td>
                <form method="post" action="/modules/health/shares/health/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if is_shared else 'true'}"><button class="secondary">{'å…±æœ‰ä¸­ï¼ˆéå…¬é–‹ã«ã™ã‚‹ï¼‰' if is_shared else 'ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰'}</button></form></td></tr>'''
            latest = f"æœ€æ–° {items[0].weight_kg} kgï¼ˆ{items[0].record_date}ï¼‰" if items else "è¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“"
            return f'''<section class="tenant"><h3>{html.escape(dog.call_name)}</h3><p>{latest}</p>
            <details><summary>è¨˜éŒ²ã‚’è¿½åŠ ãƒ»å±¥æ­´ã‚’è¦‹ã‚‹</summary><form method="post" action="/modules/health/record">
            <input type="hidden" name="dog_id" value="{dog.id}"><input type="hidden" name="category" value="weight"><input type="hidden" name="return_to" value="weights">
            <label>æ¸¬å®šæ—¥æ™‚</label><input type="datetime-local" name="recorded_at" value="{now_local}" required><label>ä½“é‡ï¼ˆkgï¼‰</label><input type="number" step="0.01" min="0.01" name="weight_kg" required>
            <div class="grid"><div><label>é£Ÿäº‹é‡ï¼ˆgï¼‰</label><input type="number" step="0.1" min="0" name="meal_amount_g" placeholder="ä¾‹ï¼š80"></div><div><label>ãƒ•ãƒ¼ãƒ‰å</label><select name="food_name">{food_options}</select></div>
            <div><label>ã†ã‚“ã¡ã®çŠ¶æ…‹</label><select name="stool_condition"><option value="">é¸æŠã—ã¦ãã ã•ã„</option><option>è‰¯å¥½</option><option>ã‚„ã‚ã‚‰ã‹ã„</option><option>ä¸‹ç—¢</option><option>ç¡¬ã„</option><option>å‡ºã¦ã„ãªã„</option></select></div>
            <div><label>å¥åº·çŠ¶æ…‹</label><select name="health_condition"><option value="">é¸æŠã—ã¦ãã ã•ã„</option><option>è‰¯å¥½</option><option>å°‘ã—æ‚ªã„</option><option>æ‚ªã„</option></select></div></div>
            <label>ãƒ¡ãƒ¢</label><textarea name="notes" placeholder="é£Ÿæ¬²ã‚„ä½“èª¿ãªã©"></textarea><label><input type="checkbox" name="owner_visible" checked> ã‚ªãƒ¼ãƒŠãƒ¼ãƒšãƒ¼ã‚¸ã«ã‚‚å…±æœ‰ã™ã‚‹</label><button>ä½“é‡ã‚’è¨˜éŒ²</button></form>
            <table><tr><th>æ¸¬å®šæ—¥æ™‚</th><th>ä½“é‡</th><th>é£Ÿäº‹ãƒ»çŠ¶æ…‹</th><th>ãƒ¡ãƒ¢</th><th>å…±æœ‰</th></tr>{rows or '<tr><td colspan="5">è¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></details></section>'''

    def dog_cards(category: str):
        targets = [dog for dog in dogs if dog.category == category]
        if not targets:
            return '<p>å¯¾è±¡ã®çŠ¬ã¯ç™»éŒ²ã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚</p>'
        if category != "puppy":
            return "".join(dog_card(dog) for dog in targets)
        groups: dict[tuple[int | None, int | None, date | None], list[Dog]] = {}
        for dog in targets:
            groups.setdefault((dog.dam_id, dog.sire_id, dog.birth_date), []).append(dog)
        output = ""
        for (dam_id, sire_id, birth_date), siblings in groups.items():
            dam = session.get(Dog, dam_id) if dam_id else None
            sire = session.get(Dog, sire_id) if sire_id else None
            title = f"{birth_date or 'å‡ºç”Ÿæ—¥æœªç™»éŒ²'}ç”Ÿã¾ã‚Œã€€æ¯çŠ¬ï¼š{html.escape(dam.call_name) if dam else 'æœªç™»éŒ²'} ï¼ çˆ¶çŠ¬ï¼š{html.escape(sire.call_name) if sire else 'æœªç™»éŒ²'}"
            output += f'<section class="weight-litter"><h3>{title}</h3><p>å…„å¼Ÿ {len(siblings)}é ­</p><div class="weight-siblings">' + "".join(dog_card(dog) for dog in siblings) + "</div></section>"
        return output

    body = f'''<a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†ã¸æˆ»ã‚‹</a><h1>ä½“é‡ç®¡ç†</h1>
    <p>ä½“é‡ã¯æ„›çŠ¬ã«ç´ã¥ã„ã¦ä¿å­˜ã•ã‚Œã¾ã™ã€‚å…±æœ‰ä¸­ã®è¨˜éŒ²ã¯ã€è²©å£²ãƒ»è­²æ¸¡å¾Œã‚‚é€£æºã•ã‚ŒãŸã‚ªãƒ¼ãƒŠãƒ¼ãŒç¢ºèªã§ãã¾ã™ã€‚</p>
    <style>.weight-litter{{margin:20px 0;padding:20px;border:1px solid #eadadd;border-radius:16px;background:#fffafb}}.weight-litter>h3{{margin:0;color:#68404f}}.weight-litter>p{{margin:5px 0 14px;color:#806b72}}.weight-siblings{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}}.weight-siblings .tenant{{margin:0;min-width:0}}@media(max-width:700px){{.weight-siblings{{grid-template-columns:1fr}}.weight-siblings table{{display:block;overflow-x:auto}}}}</style>
    <h2>å­çŠ¬</h2>{dog_cards("puppy")}<h2>è¦ªçŠ¬</h2>{dog_cards("parent")}'''
    return layout("ä½“é‡ç®¡ç†", body, user)


@app.get("/modules/health/checkups", response_class=HTMLResponse)
def health_checkups_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(HealthRecord).where(HealthRecord.tenant_id == tenant.id, HealthRecord.category == "checkup").order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())).all()
    category_labels = {"puppy": "å­çŠ¬", "parent": "è¦ªçŠ¬", "external": "å¤–éƒ¨çŠ¬"}
    status_labels = {"resident": "åœ¨ç±ä¸­", "reserved": "äºˆç´„æ¸ˆã¿ï¼ˆåœ¨ç±ä¸­ï¼‰", "retired": "å¼•é€€ï¼ˆåœ¨ç±ä¸­ï¼‰", "delivered": "è²©å£²æ¸ˆã¿", "transferred": "è­²æ¸¡æ¸ˆã¿"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}ï½œ{category_labels.get(dog.category, dog.category)}ï½œ{status_labels.get(dog.status, dog.status)}{"ï½œ" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    resident_parents = [dog for dog in dogs if dog.category == "parent" and dog.status not in {"delivered", "transferred"}]
    year_start = date(date.today().year, 1, 1)
    checked_ids = {item.dog_id for item in records if item.record_date >= year_start}
    unchecked = [dog for dog in resident_parents if dog.id not in checked_ids]
    checked = [dog for dog in resident_parents if dog.id in checked_ids]
    upcoming = [item for item in records if item.next_due_on and date.today() <= item.next_due_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_due_on and item.next_due_on < date.today()]
    result_labels = {"normal": "ç•°å¸¸ãªã—", "followup": "çµŒéè¦³å¯Ÿ", "recheck": "å†æ¤œæŸ»", "treatment": "æ²»ç™‚ãƒ»å—è¨ºãŒå¿…è¦"}

    def names(items: list[Dog]) -> str:
        return "ã€".join(html.escape(dog.call_name) for dog in items) or "è©²å½“ãªã—"

    def tests(item: HealthRecord) -> str:
        labels = []
        if item.physical_exam: labels.append("è§¦è¨º")
        if item.blood_test: labels.append("è¡€æ¶²æ¤œæŸ»")
        if item.ultrasound: labels.append("ã‚¨ã‚³ãƒ¼")
        if item.chest_xray: labels.append("èƒ¸éƒ¨Xç·š")
        return "ãƒ»".join(labels) or "é …ç›®æœªç™»éŒ²"

    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog: continue
        share = health_share_for(session, "health", item.id); shared = bool(share and share.owner_visible)
        attachment = f'<a href="/modules/health/checkups/{item.id}/attachment" target="_blank">çµæœã‚’è¦‹ã‚‹</a>' if item.attachment_data else "-"
        rows += f'''<tr><td>{item.record_date}</td><td>{html.escape(dog.call_name)}</td><td>{tests(item)}</td><td>{result_labels.get(item.result_summary or "", "æœªè¨­å®š")}</td><td>{item.next_due_on or "-"}</td><td>{attachment}</td><td><form method="post" action="/modules/health/shares/health/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'å…±æœ‰ä¸­ï¼ˆéå…¬é–‹ã«ã™ã‚‹ï¼‰' if shared else 'ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰'}</button></form></td></tr>'''

    body = f'''<a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†ã¸æˆ»ã‚‹</a><h1>å¥è¨ºç®¡ç†</h1><p>å¹´åº¦å†…ã®æœªå—è¨ºãƒ»å—è¨ºæ¸ˆã¿ã‚’åˆ†é¡ã—ã€æ¤œæŸ»é …ç›®ã¨çµæœã‚’çŠ¬ã”ã¨ã«ç®¡ç†ã—ã¾ã™ã€‚</p>
    <div class="grid"><section class="tenant"><h3>ä»Šå¹´åº¦æœªå—è¨º</h3><strong>{len(unchecked)}é ­</strong><p>{names(unchecked)}</p></section><section class="tenant"><h3>ä»Šå¹´åº¦å—è¨ºæ¸ˆã¿</h3><strong>{len(checked)}é ­</strong><p>{names(checked)}</p></section><section class="tenant"><h3>30æ—¥ä»¥å†…ã®äºˆå®š</h3><strong>{len(upcoming)}ä»¶</strong></section><section class="tenant"><h3>æœŸé™è¶…é</h3><strong>{len(overdue)}ä»¶</strong></section></div>
    <h2>å¥è¨ºè¨˜éŒ²ã‚’è¿½åŠ </h2><form method="post" action="/modules/health/checkup" enctype="multipart/form-data"><div class="grid"><div class="dog-picker"><label>å¯¾è±¡çŠ¬ã‚’æ¤œç´¢</label><input class="dog-search" type="search" data-dog-select="checkup-dog" placeholder="å‘¼ã³åãƒ»è¡€çµ±æ›¸åãƒ»çŠ¬ç¨®ãƒ»åŒºåˆ†ã§æ¤œç´¢"><label class="dog-search-all"><input type="checkbox"> è²©å£²æ¸ˆã¿ãƒ»è­²æ¸¡æ¸ˆã¿ã®çŠ¬ã‚‚æ¤œç´¢ã™ã‚‹</label><small class="dog-search-count"></small><label>å¯¾è±¡çŠ¬</label><select id="checkup-dog" name="dog_id" required>{options}</select></div>
    <div><label>å—è¨ºæ—¥</label><input type="date" name="record_date" value="{date.today()}" required></div><div><label>å‹•ç‰©ç—…é™¢</label><input name="clinic"></div><div><label>çµæœåŒºåˆ†</label><select name="result_summary" required><option value="normal">ç•°å¸¸ãªã—</option><option value="followup">çµŒéè¦³å¯Ÿ</option><option value="recheck">å†æ¤œæŸ»</option><option value="treatment">æ²»ç™‚ãƒ»å—è¨ºãŒå¿…è¦</option></select></div><div><label>æ¬¡å›å¥è¨ºäºˆå®šæ—¥</label><input type="date" name="next_due_on"></div></div>
    <fieldset><legend>å¥è¨ºé …ç›®ï¼ˆ1ã¤ä»¥ä¸Šé¸æŠï¼‰</legend><div class="grid"><label><input style="width:auto" type="checkbox" name="physical_exam" value="true"> è§¦è¨º</label><label><input style="width:auto" type="checkbox" name="blood_test" value="true"> è¡€æ¶²æ¤œæŸ»</label><label><input style="width:auto" type="checkbox" name="ultrasound" value="true"> ã‚¨ã‚³ãƒ¼</label><label><input style="width:auto" type="checkbox" name="chest_xray" value="true"> èƒ¸éƒ¨Xç·š</label></div></fieldset>
    <label>æ‰€è¦‹ãƒ»çµæœ</label><textarea name="notes"></textarea><label>æ¤œæŸ»çµæœï¼ˆç”»åƒãƒ»PDFã€8MBã¾ã§ï¼‰</label><input type="file" name="attachment_file" accept="image/jpeg,image/png,image/webp,application/pdf"><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> ã‚ªãƒ¼ãƒŠãƒ¼ãƒšãƒ¼ã‚¸ã«ã‚‚å…±æœ‰ã™ã‚‹</label><button>å¥è¨ºã‚’è¨˜éŒ²</button></form>
    <h2>å¥è¨ºå±¥æ­´</h2><div style="overflow-x:auto"><table><tr><th>å—è¨ºæ—¥</th><th>çŠ¬</th><th>å¥è¨ºé …ç›®</th><th>çµæœ</th><th>æ¬¡å›äºˆå®š</th><th>æ·»ä»˜</th><th>å…±æœ‰</th></tr>{rows or '<tr><td colspan="7">å¥è¨ºè¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}fieldset{{margin-top:18px;border:1px solid #eadfe1;border-radius:12px}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style>
    <script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'åœ¨ç±çŠ¬ä»¥å¤–ã‚’å«ã‚€ ':'åœ¨ç±çŠ¬ ')+matches.length+'é ­ã‹ã‚‰é¸æŠ'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("å¥è¨ºç®¡ç†", body, user)


@app.post("/modules/health/checkup")
async def health_checkup_create(dog_id: int = Form(...), record_date: str = Form(...), clinic: str = Form(""), result_summary: str = Form(...), next_due_on: str = Form(""), physical_exam: bool = Form(False), blood_test: bool = Form(False), ultrasound: bool = Form(False), chest_xray: bool = Form(False), notes: str = Form(""), owner_visible: bool = Form(False), attachment_file: UploadFile | None = File(None), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access; dog = tenant_dog(session, tenant.id, dog_id)
    if result_summary not in {"normal", "followup", "recheck", "treatment"} or not any([physical_exam, blood_test, ultrasound, chest_xray]):
        raise HTTPException(status_code=400, detail="å¥è¨ºé …ç›®ã¨çµæœã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    attachment_data = None
    if attachment_file and attachment_file.filename:
        if attachment_file.content_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
            raise HTTPException(status_code=400, detail="æ¤œæŸ»çµæœã¯JPEGãƒ»PNGãƒ»WebPãƒ»PDFã«å¯¾å¿œã—ã¦ã„ã¾ã™")
        attachment_data = await attachment_file.read(8 * 1024 * 1024 + 1)
        if len(attachment_data) > 8 * 1024 * 1024: raise HTTPException(status_code=413, detail="æ¤œæŸ»çµæœã¯8MBä»¥ä¸‹ã«ã—ã¦ãã ã•ã„")
    due = date.fromisoformat(next_due_on) if next_due_on else None
    item = HealthRecord(tenant_id=tenant.id, dog_id=dog.id, record_date=date.fromisoformat(record_date), category="checkup", clinic=clinic.strip() or None, notes=notes.strip() or None, physical_exam=physical_exam, blood_test=blood_test, ultrasound=ultrasound, chest_xray=chest_xray, result_summary=result_summary, next_due_on=due, attachment_filename=((attachment_file.filename or "")[:255] or None) if attachment_file and attachment_data else None, attachment_content_type=attachment_file.content_type if attachment_file and attachment_data else None, attachment_data=attachment_data)
    session.add(item); session.flush()
    if owner_visible: session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="health", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    if due: session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} æ¬¡å›å¥è¨ºäºˆå®š", category="health", due_date=due))
    session.commit(); return RedirectResponse("/modules/health/checkups", status_code=303)


@app.get("/modules/health/checkups/{record_id}/attachment")
def health_checkup_attachment(record_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    _, tenant = access; item = session.scalar(select(HealthRecord).where(HealthRecord.id == record_id, HealthRecord.tenant_id == tenant.id, HealthRecord.category == "checkup"))
    if not item or not item.attachment_data: raise HTTPException(status_code=404, detail="æ¤œæŸ»çµæœãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
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
    if stool_condition not in {"", "è‰¯å¥½", "ã‚„ã‚ã‚‰ã‹ã„", "ä¸‹ç—¢", "ç¡¬ã„", "å‡ºã¦ã„ãªã„"}:
        raise HTTPException(status_code=400, detail="ã†ã‚“ã¡ã®çŠ¶æ…‹ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if health_condition not in {"", "è‰¯å¥½", "å°‘ã—æ‚ªã„", "æ‚ªã„"}:
        raise HTTPException(status_code=400, detail="å¥åº·çŠ¶æ…‹ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
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
        raise HTTPException(status_code=400, detail="å…±æœ‰å¯¾è±¡ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    item = session.scalar(select(model).where(model.id == record_id, model.tenant_id == tenant.id))
    if not item:
        raise HTTPException(status_code=404, detail="å¥åº·è¨˜éŒ²ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
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
    category_labels = {"puppy": "å­çŠ¬", "parent": "è¦ªçŠ¬", "external": "å¤–éƒ¨çŠ¬"}
    status_labels = {"resident": "åœ¨ç±ä¸­", "reserved": "äºˆç´„æ¸ˆã¿ï¼ˆåœ¨ç±ä¸­ï¼‰", "retired": "å¼•é€€ï¼ˆåœ¨ç±ä¸­ï¼‰", "delivered": "è²©å£²æ¸ˆã¿", "transferred": "è­²æ¸¡æ¸ˆã¿"}
    options = "".join(
        f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">'
        f'{html.escape(dog.call_name)}ï½œ{category_labels.get(dog.category, dog.category)}ï½œ{status_labels.get(dog.status, dog.status)}'
        f'{"ï½œ" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs
    )
    resident_parents = [dog for dog in dogs if dog.category == "parent" and dog.status not in {"delivered", "transferred"}]
    year_start = date(date.today().year, 1, 1)
    rabies_ids = {item.dog_id for item in records if item.administered_on >= year_start and item.vaccine_type == "rabies"}
    mixed_ids = {item.dog_id for item in records if item.administered_on >= year_start and item.vaccine_type == "mixed"}
    missing_rabies = [dog for dog in resident_parents if dog.id not in rabies_ids]
    missing_mixed = [dog for dog in resident_parents if dog.id not in mixed_ids]
    upcoming = [item for item in records if item.next_due_on and date.today() <= item.next_due_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_due_on and item.next_due_on < date.today()]
    type_labels = {"rabies": "ç‹‚çŠ¬ç—…", "mixed": "æ··åˆãƒ¯ã‚¯ãƒãƒ³", "other": "ãã®ä»–"}

    def dose_label(value: int | None) -> str:
        return "è¿½åŠ æ¥ç¨®" if value and value >= 4 else (f"{value}å›ç›®" if value else "-")

    def dog_names(items: list[Dog]) -> str:
        return "ã€".join(html.escape(dog.call_name) for dog in items) or "è©²å½“ãªã—"

    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog:
            continue
        share = health_share_for(session, "vaccination", item.id)
        shared = bool(share and share.owner_visible)
        certificate = f'<a href="/modules/health/vaccinations/{item.id}/certificate" target="_blank">è¨¼æ˜æ›¸ã‚’è¦‹ã‚‹</a>' if item.certificate_data else "-"
        rows += f'''<tr><td>{item.administered_on}</td><td>{html.escape(dog.call_name)}</td><td>{type_labels.get(item.vaccine_type or "other", "ãã®ä»–")}</td><td>{html.escape(item.vaccine_name)}</td><td>{dose_label(item.dose_number)}</td><td>{item.next_due_on or "-"}</td><td>{certificate}</td><td>
        <form method="post" action="/modules/health/shares/vaccination/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'å…±æœ‰ä¸­ï¼ˆéå…¬é–‹ã«ã™ã‚‹ï¼‰' if shared else 'ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰'}</button></form></td></tr>'''

    body = f'''<a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†ã¸æˆ»ã‚‹</a><h1>ãƒ¯ã‚¯ãƒãƒ³ç®¡ç†</h1>
    <p>ç‹‚çŠ¬ç—…ã¨æ··åˆãƒ¯ã‚¯ãƒãƒ³ã‚’åˆ¥ã€…ã«åˆ¤å®šã—ã€å­çŠ¬æœŸã®æ¥ç¨®é †ã¨æ¬¡å›äºˆå®šã‚‚ç®¡ç†ã—ã¾ã™ã€‚</p>
    <div class="grid"><section class="tenant"><h3>ç‹‚çŠ¬ç—…ãƒ»ä»Šå¹´åº¦æœªæ¥ç¨®</h3><strong>{len(missing_rabies)}é ­</strong><p>{dog_names(missing_rabies)}</p></section>
    <section class="tenant"><h3>æ··åˆãƒ»ä»Šå¹´åº¦æœªæ¥ç¨®</h3><strong>{len(missing_mixed)}é ­</strong><p>{dog_names(missing_mixed)}</p></section>
    <section class="tenant"><h3>30æ—¥ä»¥å†…ã®äºˆå®š</h3><strong>{len(upcoming)}ä»¶</strong></section><section class="tenant"><h3>æœŸé™è¶…é</h3><strong>{len(overdue)}ä»¶</strong></section></div>
    <h2>æ¥ç¨®è¨˜éŒ²ã‚’è¿½åŠ </h2><form method="post" action="/modules/health/vaccine" enctype="multipart/form-data"><div class="grid">
    <div class="dog-picker"><label>å¯¾è±¡çŠ¬ã‚’æ¤œç´¢</label><input class="dog-search" type="search" data-dog-select="vaccination-dog" placeholder="å‘¼ã³åãƒ»è¡€çµ±æ›¸åãƒ»çŠ¬ç¨®ãƒ»åŒºåˆ†ã§æ¤œç´¢"><label class="dog-search-all"><input type="checkbox"> è²©å£²æ¸ˆã¿ãƒ»è­²æ¸¡æ¸ˆã¿ã®çŠ¬ã‚‚æ¤œç´¢ã™ã‚‹</label><small class="dog-search-count"></small><label>å¯¾è±¡çŠ¬</label><select id="vaccination-dog" name="dog_id" required>{options}</select></div>
    <div><label>ãƒ¯ã‚¯ãƒãƒ³åŒºåˆ†</label><select name="vaccine_type" required><option value="rabies">ç‹‚çŠ¬ç—…</option><option value="mixed">æ··åˆãƒ¯ã‚¯ãƒãƒ³</option><option value="other">ãã®ä»–</option></select></div>
    <div><label>ãƒ¯ã‚¯ãƒãƒ³å</label><input name="vaccine_name" required></div><div><label>å­çŠ¬æœŸã®æ¥ç¨®é †ï¼ˆä»»æ„ï¼‰</label><select name="dose_number"><option value="">å…¥åŠ›ãªã—</option><option value="1">1å›ç›®</option><option value="2">2å›ç›®</option><option value="3">3å›ç›®</option><option value="4">è¿½åŠ æ¥ç¨®</option></select><small>æˆçŠ¬ã®å®šæœŸæ¥ç¨®ã§ã¯å…¥åŠ›ä¸è¦ã§ã™ã€‚</small></div>
    <div><label>æ¥ç¨®æ—¥</label><input type="date" name="administered_on" value="{date.today()}" required></div><div><label>æ¬¡å›æ¥ç¨®äºˆå®šæ—¥</label><input type="date" name="next_due_on"></div>
    <div><label>å‹•ç‰©ç—…é™¢</label><input name="clinic"></div><div><label>ãƒ¡ãƒ¼ã‚«ãƒ¼</label><input name="manufacturer"></div><div><label>è£½é€ ç•ªå·ãƒ»ãƒ­ãƒƒãƒˆç•ªå·</label><input name="lot_no"></div><div><label>è¨¼æ˜æ›¸ç•ªå·</label><input name="certificate_no"></div>
    <div><label>å‰¯åå¿œ</label><select name="reaction"><option value="none">ãªã—</option><option value="mild">è»½ã„ç—‡çŠ¶ã‚ã‚Š</option><option value="severe">å¼·ã„ç—‡çŠ¶ã‚ã‚Š</option><option value="unknown">ä¸æ˜</option></select></div><div><label>è¨¼æ˜æ›¸ï¼ˆç”»åƒãƒ»PDFã€8MBã¾ã§ï¼‰</label><input type="file" name="certificate_file" accept="image/jpeg,image/png,image/webp,application/pdf"></div></div>
    <label>ãƒ¡ãƒ¢</label><textarea name="notes"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> ã‚ªãƒ¼ãƒŠãƒ¼ãƒšãƒ¼ã‚¸ã«ã‚‚å…±æœ‰ã™ã‚‹</label><input type="hidden" name="return_to" value="vaccinations"><button>æ¥ç¨®ã‚’è¨˜éŒ²</button></form>
    <h2>æ¥ç¨®å±¥æ­´</h2><div style="overflow-x:auto"><table><tr><th>æ¥ç¨®æ—¥</th><th>çŠ¬</th><th>åŒºåˆ†</th><th>ãƒ¯ã‚¯ãƒãƒ³</th><th>å›æ•°</th><th>æ¬¡å›äºˆå®š</th><th>è¨¼æ˜æ›¸</th><th>å…±æœ‰</th></tr>{rows or '<tr><td colspan="8">æ¥ç¨®è¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style>
    <script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'åœ¨ç±çŠ¬ä»¥å¤–ã‚’å«ã‚€ ':'åœ¨ç±çŠ¬ ')+matches.length+'é ­ã‹ã‚‰é¸æŠ'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("ãƒ¯ã‚¯ãƒãƒ³ç®¡ç†", body, user)


@app.get("/modules/health/vaccinations/{vaccination_id}/certificate")
def vaccination_certificate(vaccination_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    _, tenant = access
    item = session.scalar(select(Vaccination).where(Vaccination.id == vaccination_id, Vaccination.tenant_id == tenant.id))
    if not item or not item.certificate_data:
        raise HTTPException(status_code=404, detail="è¨¼æ˜æ›¸ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
    return Response(content=item.certificate_data, media_type=item.certificate_content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store"})


@app.post("/modules/health/vaccine")
async def vaccine_create(dog_id: int = Form(...), vaccine_name: str = Form(...), administered_on: str = Form(...), next_due_on: str = Form(""), certificate_no: str = Form(""), vaccine_type: str = Form("other"), dose_number: str = Form(""), clinic: str = Form(""), manufacturer: str = Form(""), lot_no: str = Form(""), reaction: str = Form("unknown"), notes: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), certificate_file: UploadFile | None = File(None), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if vaccine_type not in {"rabies", "mixed", "other"} or reaction not in {"none", "mild", "severe", "unknown"}:
        raise HTTPException(status_code=400, detail="ãƒ¯ã‚¯ãƒãƒ³æƒ…å ±ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if dose_number not in {"", "1", "2", "3", "4"}:
        raise HTTPException(status_code=400, detail="å­çŠ¬æœŸã®æ¥ç¨®é †ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    next_due = date.fromisoformat(next_due_on) if next_due_on else None
    file_data = None
    if certificate_file and certificate_file.filename:
        allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        if certificate_file.content_type not in allowed:
            raise HTTPException(status_code=400, detail="è¨¼æ˜æ›¸ã¯JPEGãƒ»PNGãƒ»WebPãƒ»PDFã«å¯¾å¿œã—ã¦ã„ã¾ã™")
        file_data = await certificate_file.read(8 * 1024 * 1024 + 1)
        if len(file_data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="è¨¼æ˜æ›¸ã¯8MBä»¥ä¸‹ã«ã—ã¦ãã ã•ã„")
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
        session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} {vaccine_name.strip()}æ¥ç¨®äºˆå®š", category="health", due_date=next_due))
    session.commit()
    return RedirectResponse("/modules/health/vaccinations" if return_to == "vaccinations" else "/modules/health", status_code=303)


@app.get("/modules/health/medications", response_class=HTMLResponse)
def health_medications_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(Medication).where(Medication.tenant_id == tenant.id).order_by(Medication.administered_on.desc(), Medication.id.desc())).all()
    category_labels = {"puppy": "å­çŠ¬", "parent": "è¦ªçŠ¬", "external": "å¤–éƒ¨çŠ¬"}; status_labels = {"resident": "åœ¨ç±ä¸­", "reserved": "äºˆç´„æ¸ˆã¿ï¼ˆåœ¨ç±ä¸­ï¼‰", "retired": "å¼•é€€ï¼ˆåœ¨ç±ä¸­ï¼‰", "delivered": "è²©å£²æ¸ˆã¿", "transferred": "è­²æ¸¡æ¸ˆã¿"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}ï½œ{category_labels.get(dog.category, dog.category)}ï½œ{status_labels.get(dog.status, dog.status)}{"ï½œ" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    counts: dict[int, int] = {}
    for item in records: counts[item.dog_id] = counts.get(item.dog_id, 0) + 1

    def age(dog: Dog) -> str:
        if not dog.birth_date: return "æœªç™»éŒ²"
        today = date.today(); months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
        return f"{months // 12}æ­³{months % 12}ã‹æœˆ" if months >= 12 else f"{max(months, 0)}ã‹æœˆ"

    resident_dogs = [dog for dog in dogs if dog.status not in {"delivered", "transferred"}]
    dog_rows = "".join(f'<tr><td>{html.escape(dog.call_name)}</td><td>{age(dog)}</td><td>{dog.birth_date or "æœªç™»éŒ²"}</td><td>{counts.get(dog.id, 0)}å›</td></tr>' for dog in resident_dogs)
    ongoing = [item for item in records if item.status == "ongoing"]
    upcoming = [item for item in records if item.next_due_on and date.today() <= item.next_due_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_due_on and item.next_due_on < date.today() and item.status != "completed"]
    type_labels = {"treatment": "æ²»ç™‚è–¬", "prevention": "äºˆé˜²è–¬", "supplement": "ã‚µãƒ—ãƒªãƒ¡ãƒ³ãƒˆ", "other": "ãã®ä»–"}; status_text = {"single": "å˜å›", "ongoing": "ç¶™ç¶šä¸­", "completed": "çµ‚äº†"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog: continue
        share = health_share_for(session, "medication", item.id); shared = bool(share and share.owner_visible)
        rows += f'''<tr><td>{item.administered_on}</td><td>{html.escape(dog.call_name)}</td><td>{html.escape(item.medicine_name)}</td><td>{type_labels.get(item.medication_type or "other", "ãã®ä»–")}</td><td>{html.escape(item.dosage or "-")}</td><td>{html.escape(item.frequency or "-")}</td><td>{status_text.get(item.status or "single", "å˜å›")}</td><td>{item.next_due_on or "-"}</td><td><form method="post" action="/modules/health/shares/medication/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'å…±æœ‰ä¸­ï¼ˆéå…¬é–‹ã«ã™ã‚‹ï¼‰' if shared else 'ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰'}</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†ã¸æˆ»ã‚‹</a><h1>æŠ•è–¬ç®¡ç†</h1><p>çŠ¬ã”ã¨ã®æŠ•è–¬å›æ•°ã¨ã€ç¶™ç¶šä¸­ãƒ»å˜å›ãƒ»çµ‚äº†ã—ãŸè–¬ã‚’ç®¡ç†ã—ã¾ã™ã€‚</p>
    <div class="grid"><section class="tenant"><h3>ç¶™ç¶šä¸­</h3><strong>{len(ongoing)}ä»¶</strong></section><section class="tenant"><h3>30æ—¥ä»¥å†…ã®äºˆå®š</h3><strong>{len(upcoming)}ä»¶</strong></section><section class="tenant"><h3>æœŸé™è¶…é</h3><strong>{len(overdue)}ä»¶</strong></section><section class="tenant"><h3>æŠ•è–¬è¨˜éŒ²</h3><strong>{len(records)}ä»¶</strong></section></div>
    <h2>çŠ¬ã”ã¨ã®æŠ•è–¬å›æ•°</h2><div style="overflow-x:auto"><table><tr><th>å¯¾è±¡çŠ¬</th><th>å¹´é½¢</th><th>èª•ç”Ÿæ—¥</th><th>æŠ•è–¬å›æ•°</th></tr>{dog_rows or '<tr><td colspan="4">å¯¾è±¡çŠ¬ã¯ã„ã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <h2>æŠ•è–¬è¨˜éŒ²ã‚’è¿½åŠ </h2><form method="post" action="/modules/health/medication"><div class="grid"><div class="dog-picker"><label>å¯¾è±¡çŠ¬ã‚’æ¤œç´¢</label><input class="dog-search" type="search" data-dog-select="medication-dog" placeholder="å‘¼ã³åãƒ»è¡€çµ±æ›¸åãƒ»çŠ¬ç¨®ãƒ»åŒºåˆ†ã§æ¤œç´¢"><label class="dog-search-all"><input type="checkbox"> è²©å£²æ¸ˆã¿ãƒ»è­²æ¸¡æ¸ˆã¿ã®çŠ¬ã‚‚æ¤œç´¢ã™ã‚‹</label><small class="dog-search-count"></small><label>å¯¾è±¡çŠ¬</label><select id="medication-dog" name="dog_id" required>{options}</select></div>
    <div><label>è–¬å‰¤å</label><input name="medicine_name" required></div><div><label>åŒºåˆ†</label><select name="medication_type"><option value="treatment">æ²»ç™‚è–¬</option><option value="prevention">äºˆé˜²è–¬</option><option value="supplement">ã‚µãƒ—ãƒªãƒ¡ãƒ³ãƒˆ</option><option value="other">ãã®ä»–</option></select></div><div><label>è¨˜éŒ²æ—¥</label><input type="date" name="administered_on" value="{date.today()}" required></div><div><label>ç›®çš„ãƒ»å¯¾è±¡ç—‡çŠ¶</label><input name="purpose"></div><div><label>1å›é‡</label><input name="dosage" placeholder="ä¾‹ï¼š1éŒ ã€2.5ml"></div><div><label>æŠ•è–¬é »åº¦</label><input name="frequency" placeholder="ä¾‹ï¼š1æ—¥2å›ã€æ¯æœˆ1å›"></div><div><label>é–‹å§‹æ—¥</label><input type="date" name="started_on"></div><div><label>çµ‚äº†æ—¥</label><input type="date" name="ended_on"></div><div><label>æ¬¡å›äºˆå®šæ—¥</label><input type="date" name="next_due_on"></div><div><label>çŠ¶æ…‹</label><select name="medication_status"><option value="single">å˜å›</option><option value="ongoing">ç¶™ç¶šä¸­</option><option value="completed">çµ‚äº†</option></select></div><div><label>å‹•ç‰©ç—…é™¢</label><input name="clinic"></div></div>
    <label>ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰ã™ã‚‹èª¬æ˜</label><textarea name="owner_notes"></textarea><label>çŠ¬èˆå†…éƒ¨ãƒ¡ãƒ¢ï¼ˆã‚ªãƒ¼ãƒŠãƒ¼ã«ã¯è¡¨ç¤ºã•ã‚Œã¾ã›ã‚“ï¼‰</label><textarea name="notes"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> ã‚ªãƒ¼ãƒŠãƒ¼ãƒšãƒ¼ã‚¸ã«ã‚‚å…±æœ‰ã™ã‚‹</label><input type="hidden" name="return_to" value="medications"><button>æŠ•è–¬ã‚’è¨˜éŒ²</button></form>
    <h2>æŠ•è–¬å±¥æ­´</h2><div style="overflow-x:auto"><table><tr><th>è¨˜éŒ²æ—¥</th><th>çŠ¬</th><th>è–¬å‰¤</th><th>åŒºåˆ†</th><th>1å›é‡</th><th>é »åº¦</th><th>çŠ¶æ…‹</th><th>æ¬¡å›äºˆå®š</th><th>å…±æœ‰</th></tr>{rows or '<tr><td colspan="9">æŠ•è–¬è¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style><script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'åœ¨ç±çŠ¬ä»¥å¤–ã‚’å«ã‚€ ':'åœ¨ç±çŠ¬ ')+matches.length+'é ­ã‹ã‚‰é¸æŠ'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("æŠ•è–¬ç®¡ç†", body, user)


@app.post("/modules/health/medication")
def medication_create(dog_id: int = Form(...), medicine_name: str = Form(...), administered_on: str = Form(...), medication_type: str = Form("treatment"), purpose: str = Form(""), dosage: str = Form(""), frequency: str = Form(""), started_on: str = Form(""), ended_on: str = Form(""), next_due_on: str = Form(""), medication_status: str = Form("single"), clinic: str = Form(""), owner_notes: str = Form(""), notes: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if not medicine_name.strip() or medication_type not in {"treatment", "prevention", "supplement", "other"} or medication_status not in {"single", "ongoing", "completed"}:
        raise HTTPException(status_code=400, detail="æŠ•è–¬æƒ…å ±ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    try:
        recorded = date.fromisoformat(administered_on)
        parse = lambda value: date.fromisoformat(value) if value else None
        started, ended, due = parse(started_on), parse(ended_on), parse(next_due_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="æŠ•è–¬æ—¥ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if started and ended and ended < started: raise HTTPException(status_code=400, detail="çµ‚äº†æ—¥ã¯é–‹å§‹æ—¥ä»¥é™ã«ã—ã¦ãã ã•ã„")
    item = Medication(tenant_id=tenant.id, dog_id=dog.id, medicine_name=medicine_name.strip(), administered_on=recorded, medication_type=medication_type, purpose=purpose.strip() or None, dosage=dosage.strip() or None, frequency=frequency.strip() or None, started_on=started, ended_on=ended, next_due_on=due, status=medication_status, clinic=clinic.strip() or None, owner_notes=owner_notes.strip() or None, notes=notes.strip() or None)
    session.add(item); session.flush()
    if owner_visible: session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="medication", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    if due: session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} {medicine_name.strip()}æŠ•è–¬äºˆå®š", category="health", due_date=due))
    session.commit()
    return RedirectResponse("/modules/health/medications" if return_to == "medications" else "/modules/health", status_code=303)


@app.get("/modules/health/diseases", response_class=HTMLResponse)
def health_diseases_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(DiseaseHistory).where(DiseaseHistory.tenant_id == tenant.id).order_by(DiseaseHistory.diagnosed_on.desc(), DiseaseHistory.id.desc())).all()
    category_labels = {"puppy": "å­çŠ¬", "parent": "è¦ªçŠ¬", "external": "å¤–éƒ¨çŠ¬"}; status_labels = {"resident": "åœ¨ç±ä¸­", "reserved": "äºˆç´„æ¸ˆã¿ï¼ˆåœ¨ç±ä¸­ï¼‰", "retired": "å¼•é€€ï¼ˆåœ¨ç±ä¸­ï¼‰", "delivered": "è²©å£²æ¸ˆã¿", "transferred": "è­²æ¸¡æ¸ˆã¿"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}ï½œ{category_labels.get(dog.category, dog.category)}ï½œ{status_labels.get(dog.status, dog.status)}{"ï½œ" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    counts: dict[int, int] = {}
    for item in records: counts[item.dog_id] = counts.get(item.dog_id, 0) + 1

    def age(dog: Dog) -> str:
        if not dog.birth_date: return "æœªç™»éŒ²"
        today = date.today(); months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
        return f"{months // 12}æ­³{months % 12}ã‹æœˆ" if months >= 12 else f"{max(months, 0)}ã‹æœˆ"

    resident_dogs = [dog for dog in dogs if dog.status not in {"delivered", "transferred"}]
    dog_rows = "".join(f'<tr><td>{html.escape(dog.call_name)}</td><td>{age(dog)}</td><td>{dog.birth_date or "æœªç™»éŒ²"}</td><td>{counts.get(dog.id, 0)}å›</td></tr>' for dog in resident_dogs)
    active = [item for item in records if item.status in {"treatment", "followup", "chronic"}]
    recurring = [item for item in records if item.recurrence]
    upcoming = [item for item in records if item.next_followup_on and date.today() <= item.next_followup_on <= date.today() + timedelta(days=30)]
    overdue = [item for item in records if item.next_followup_on and item.next_followup_on < date.today() and item.status != "recovered"]
    status_text = {"treatment": "æ²»ç™‚ä¸­", "followup": "çµŒéè¦³å¯Ÿ", "recovered": "å®Œæ²»", "chronic": "æ…¢æ€§"}; disease_types = {"digestive": "æ¶ˆåŒ–å™¨", "respiratory": "å‘¼å¸å™¨", "skin": "çš®è†š", "orthopedic": "æ•´å½¢ãƒ»é–¢ç¯€", "cardiac": "å¾ªç’°å™¨", "urinary": "æ³Œå°¿å™¨", "reproductive": "ç”Ÿæ®–å™¨", "infectious": "æ„ŸæŸ“ç—‡", "other": "ãã®ä»–"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id)
        if not dog: continue
        share = health_share_for(session, "disease", item.id); shared = bool(share and share.owner_visible)
        rows += f'''<tr><td>{item.diagnosed_on or "-"}</td><td>{html.escape(dog.call_name)}</td><td>{html.escape(item.disease_name)}</td><td>{disease_types.get(item.disease_category or "other", "ãã®ä»–")}</td><td>{status_text.get(item.status or "followup", "çµŒéè¦³å¯Ÿ")}</td><td>{'å†ç™º' if item.recurrence else '-'}</td><td>{item.next_followup_on or '-'}</td><td><form method="post" action="/modules/health/shares/disease/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'å…±æœ‰ä¸­ï¼ˆéå…¬é–‹ã«ã™ã‚‹ï¼‰' if shared else 'ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰'}</button></form></td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†ã¸æˆ»ã‚‹</a><h1>ç—…æ­´ç®¡ç†</h1><p>çŠ¬ã”ã¨ã®ç½¹æ‚£è¨˜éŒ²å›æ•°ã¨ã€æ²»ç™‚ä¸­ãƒ»çµŒéè¦³å¯Ÿãƒ»å®Œæ²»ãƒ»æ…¢æ€§ã®çŠ¶æ…‹ã‚’ç®¡ç†ã—ã¾ã™ã€‚</p>
    <div class="grid"><section class="tenant"><h3>æ²»ç™‚ãƒ»è¦³å¯Ÿãƒ»æ…¢æ€§</h3><strong>{len(active)}ä»¶</strong></section><section class="tenant"><h3>å†ç™ºè¨˜éŒ²</h3><strong>{len(recurring)}ä»¶</strong></section><section class="tenant"><h3>30æ—¥ä»¥å†…ã®å†è¨º</h3><strong>{len(upcoming)}ä»¶</strong></section><section class="tenant"><h3>æœŸé™è¶…é</h3><strong>{len(overdue)}ä»¶</strong></section></div>
    <h2>çŠ¬ã”ã¨ã®ç½¹æ‚£è¨˜éŒ²å›æ•°</h2><div style="overflow-x:auto"><table><tr><th>å¯¾è±¡çŠ¬</th><th>å¹´é½¢</th><th>èª•ç”Ÿæ—¥</th><th>ç½¹æ‚£å›æ•°</th></tr>{dog_rows or '<tr><td colspan="4">å¯¾è±¡çŠ¬ã¯ã„ã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <h2>ç—…æ­´ã‚’è¿½åŠ </h2><form method="post" action="/modules/health/disease"><div class="grid"><div class="dog-picker"><label>å¯¾è±¡çŠ¬ã‚’æ¤œç´¢</label><input class="dog-search" type="search" data-dog-select="disease-dog" placeholder="å‘¼ã³åãƒ»è¡€çµ±æ›¸åãƒ»çŠ¬ç¨®ãƒ»åŒºåˆ†ã§æ¤œç´¢"><label class="dog-search-all"><input type="checkbox"> è²©å£²æ¸ˆã¿ãƒ»è­²æ¸¡æ¸ˆã¿ã®çŠ¬ã‚‚æ¤œç´¢ã™ã‚‹</label><small class="dog-search-count"></small><label>å¯¾è±¡çŠ¬</label><select id="disease-dog" name="dog_id" required>{options}</select></div>
    <div><label>ç–¾æ‚£å</label><input name="disease_name" required></div><div><label>åˆ†é¡</label><select name="disease_category">{''.join(f'<option value="{key}">{label}</option>' for key, label in disease_types.items())}</select></div><div><label>è¨ºæ–­æ—¥</label><input type="date" name="diagnosed_on" value="{date.today()}" required></div><div><label>çŠ¶æ…‹</label><select name="disease_status"><option value="treatment">æ²»ç™‚ä¸­</option><option value="followup">çµŒéè¦³å¯Ÿ</option><option value="recovered">å®Œæ²»</option><option value="chronic">æ…¢æ€§</option></select></div><div><label>æ²»ç™‚é–‹å§‹æ—¥</label><input type="date" name="treatment_started_on"></div><div><label>æ²»ç™‚çµ‚äº†æ—¥</label><input type="date" name="treatment_ended_on"></div><div><label>æ¬¡å›è¨ºå¯Ÿãƒ»ç¢ºèªæ—¥</label><input type="date" name="next_followup_on"></div><div><label>å‹•ç‰©ç—…é™¢</label><input name="clinic"></div><div><label>æ‹…å½“ç£åŒ»å¸«</label><input name="veterinarian"></div></div>
    <label style="font-weight:400"><input style="width:auto" type="checkbox" name="recurrence" value="true"> åŒã˜ç–¾æ‚£ã®å†ç™ºã¨ã—ã¦è¨˜éŒ²ã™ã‚‹</label><label>ç—‡çŠ¶</label><textarea name="symptoms"></textarea><label>ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰ã™ã‚‹èª¬æ˜</label><textarea name="owner_notes"></textarea><label>çŠ¬èˆå†…éƒ¨ãƒ¡ãƒ¢ï¼ˆã‚ªãƒ¼ãƒŠãƒ¼ã«ã¯è¡¨ç¤ºã•ã‚Œã¾ã›ã‚“ï¼‰</label><textarea name="details"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> ã‚ªãƒ¼ãƒŠãƒ¼ãƒšãƒ¼ã‚¸ã«ã‚‚å…±æœ‰ã™ã‚‹</label><input type="hidden" name="return_to" value="diseases"><button>ç—…æ­´ã‚’ç™»éŒ²</button></form>
    <h2>ç—…æ­´ä¸€è¦§</h2><div style="overflow-x:auto"><table><tr><th>è¨ºæ–­æ—¥</th><th>çŠ¬</th><th>ç–¾æ‚£</th><th>åˆ†é¡</th><th>çŠ¶æ…‹</th><th>å†ç™º</th><th>æ¬¡å›</th><th>å…±æœ‰</th></tr>{rows or '<tr><td colspan="8">ç—…æ­´è¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style><script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'åœ¨ç±çŠ¬ä»¥å¤–ã‚’å«ã‚€ ':'åœ¨ç±çŠ¬ ')+matches.length+'é ­ã‹ã‚‰é¸æŠ'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("ç—…æ­´ç®¡ç†", body, user)


@app.post("/modules/health/disease")
def disease_create(dog_id: int = Form(...), disease_name: str = Form(...), diagnosed_on: str = Form(""), treatment_started_on: str = Form(""), treatment_ended_on: str = Form(""), disease_category: str = Form("other"), symptoms: str = Form(""), disease_status: str = Form("followup"), recurrence: bool = Form(False), clinic: str = Form(""), veterinarian: str = Form(""), next_followup_on: str = Form(""), owner_notes: str = Form(""), details: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    try:
        parse = lambda value: date.fromisoformat(value) if value else None
        diagnosed, started, ended, followup = parse(diagnosed_on), parse(treatment_started_on), parse(treatment_ended_on), parse(next_followup_on)
    except ValueError: raise HTTPException(status_code=400, detail="ç—…æ­´ã®æ—¥ä»˜ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if started and ended and ended < started:
        raise HTTPException(status_code=400, detail="æ²»ç™‚çµ‚äº†æ—¥ã¯é–‹å§‹æ—¥ä»¥é™ã«ã—ã¦ãã ã•ã„")
    valid_categories = {"digestive", "respiratory", "skin", "orthopedic", "cardiac", "urinary", "reproductive", "infectious", "other"}
    if not disease_name.strip() or disease_category not in valid_categories or disease_status not in {"treatment", "followup", "recovered", "chronic"}: raise HTTPException(status_code=400, detail="ç—…æ­´æƒ…å ±ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    item = DiseaseHistory(tenant_id=tenant.id, dog_id=dog.id, disease_name=disease_name.strip(), diagnosed_on=diagnosed, treatment_started_on=started, treatment_ended_on=ended, disease_category=disease_category, symptoms=symptoms.strip() or None, status=disease_status, recurrence=recurrence, clinic=clinic.strip() or None, veterinarian=veterinarian.strip() or None, next_followup_on=followup, owner_notes=owner_notes.strip() or None, details=details.strip() or None)
    session.add(item); session.flush()
    if owner_visible: session.add(HealthRecordShare(tenant_id=tenant.id, dog_id=dog.id, record_type="disease", record_id=item.id, owner_visible=True, updated_by_id=user.id))
    if followup: session.add(TaskEvent(tenant_id=tenant.id, dog_id=dog.id, title=f"{dog.call_name} {disease_name.strip()}å†è¨ºãƒ»ç¢ºèª", category="health", due_date=followup))
    session.commit()
    return RedirectResponse("/modules/health/diseases" if return_to == "diseases" else "/modules/health", status_code=303)


@app.get("/modules/health/foods", response_class=HTMLResponse)
def health_foods_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True)).order_by(Dog.call_name)).all()
    records = session.scalars(select(FoodHistory).where(FoodHistory.tenant_id == tenant.id).order_by(FoodHistory.started_on.desc(), FoodHistory.id.desc())).all()
    category_labels = {"puppy": "å­çŠ¬", "parent": "è¦ªçŠ¬", "external": "å¤–éƒ¨çŠ¬"}; status_labels = {"resident": "åœ¨ç±ä¸­", "reserved": "äºˆç´„æ¸ˆã¿ï¼ˆåœ¨ç±ä¸­ï¼‰", "retired": "å¼•é€€ï¼ˆåœ¨ç±ä¸­ï¼‰", "delivered": "è²©å£²æ¸ˆã¿", "transferred": "è­²æ¸¡æ¸ˆã¿"}
    options = "".join(f'<option value="{dog.id}" data-nonresident="{str(dog.status in {"delivered", "transferred"}).lower()}" data-search="{html.escape(" ".join(filter(None, [dog.call_name, dog.registered_name, dog.breed, category_labels.get(dog.category), status_labels.get(dog.status)])))}">{html.escape(dog.call_name)}ï½œ{category_labels.get(dog.category, dog.category)}ï½œ{status_labels.get(dog.status, dog.status)}{"ï½œ" + html.escape(dog.registered_name) if dog.registered_name else ""}</option>' for dog in dogs)
    counts: dict[int, int] = {}
    for item in records:
        if item.dog_id: counts[item.dog_id] = counts.get(item.dog_id, 0) + 1

    def age(dog: Dog) -> str:
        if not dog.birth_date: return "æœªç™»éŒ²"
        today = date.today(); months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
        return f"{months // 12}æ­³{months % 12}ã‹æœˆ" if months >= 12 else f"{max(months, 0)}ã‹æœˆ"

    resident_dogs = [dog for dog in dogs if dog.status not in {"delivered", "transferred"}]
    dog_rows = "".join(f'<tr><td>{html.escape(dog.call_name)}</td><td>{age(dog)}</td><td>{dog.birth_date or "æœªç™»éŒ²"}</td><td>{counts.get(dog.id, 0)}å›</td></tr>' for dog in resident_dogs)
    ongoing = [item for item in records if item.dog_id and (item.status or "ongoing") == "ongoing" and not item.ended_on]
    completed = [item for item in records if item.dog_id and ((item.status or "") == "completed" or item.ended_on)]
    type_labels = {"dry": "ãƒ‰ãƒ©ã‚¤", "wet": "ã‚¦ã‚§ãƒƒãƒˆ", "raw": "ç”Ÿé£Ÿ", "prescription": "ç™‚æ³•é£Ÿ", "supplement": "ã‚µãƒ—ãƒªãƒ¡ãƒ³ãƒˆ", "other": "ãã®ä»–"}
    rows = ""
    for item in records:
        dog = session.get(Dog, item.dog_id) if item.dog_id else None
        shared = False
        if dog:
            share = health_share_for(session, "food", item.id); shared = bool(share and share.owner_visible)
        amount = f"{item.amount_g:g}g" if item.amount_g is not None else "-"
        frequency = f"1æ—¥{item.times_per_day}å›" if item.times_per_day else "-"
        share_cell = f'''<form method="post" action="/modules/health/shares/food/{item.id}"><input type="hidden" name="owner_visible" value="{'false' if shared else 'true'}"><button class="secondary">{'å…±æœ‰ä¸­ï¼ˆéå…¬é–‹ã«ã™ã‚‹ï¼‰' if shared else 'ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰'}</button></form>''' if dog else "æ—§è¨˜éŒ²"
        rows += f'''<tr><td>{html.escape(dog.call_name) if dog else "çŠ¬æœªè¨­å®š"}</td><td>{html.escape(item.name)}</td><td>{type_labels.get(item.food_type or "other", "ãã®ä»–")}</td><td>{amount}</td><td>{frequency}</td><td>{item.started_on}</td><td>{item.ended_on or "ç¶™ç¶šä¸­"}</td><td>{html.escape(item.change_reason or "-")}</td><td>{share_cell}</td></tr>'''
    body = f'''<a class="button secondary" href="/modules/health">å¥åº·ç®¡ç†ã¸æˆ»ã‚‹</a><h1>ãƒ•ãƒ¼ãƒ‰ç®¡ç†</h1><p>çŠ¬ã”ã¨ã®ãƒ•ãƒ¼ãƒ‰åˆ©ç”¨æœŸé–“ã€çµ¦ä¸é‡ã€å¤‰æ›´å±¥æ­´ã‚’ç®¡ç†ã—ã¾ã™ã€‚</p>
    <div class="grid"><section class="tenant"><h3>åˆ©ç”¨ä¸­</h3><strong>{len(ongoing)}ä»¶</strong></section><section class="tenant"><h3>çµ‚äº†æ¸ˆã¿</h3><strong>{len(completed)}ä»¶</strong></section><section class="tenant"><h3>åˆ©ç”¨å±¥æ­´</h3><strong>{len(records)}ä»¶</strong></section></div>
    <h2>çŠ¬ã”ã¨ã®ãƒ•ãƒ¼ãƒ‰å¤‰æ›´å›æ•°</h2><div style="overflow-x:auto"><table><tr><th>å¯¾è±¡çŠ¬</th><th>å¹´é½¢</th><th>èª•ç”Ÿæ—¥</th><th>åˆ©ç”¨å±¥æ­´</th></tr>{dog_rows or '<tr><td colspan="4">å¯¾è±¡çŠ¬ã¯ã„ã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <h2>ãƒ•ãƒ¼ãƒ‰åˆ©ç”¨è¨˜éŒ²ã‚’è¿½åŠ </h2><form method="post" action="/modules/health/food"><div class="grid"><div class="dog-picker"><label>å¯¾è±¡çŠ¬ã‚’æ¤œç´¢</label><input class="dog-search" type="search" data-dog-select="food-dog" placeholder="å‘¼ã³åãƒ»è¡€çµ±æ›¸åãƒ»çŠ¬ç¨®ãƒ»åŒºåˆ†ã§æ¤œç´¢"><label class="dog-search-all"><input type="checkbox"> è²©å£²æ¸ˆã¿ãƒ»è­²æ¸¡æ¸ˆã¿ã®çŠ¬ã‚‚æ¤œç´¢ã™ã‚‹</label><small class="dog-search-count"></small><label>å¯¾è±¡çŠ¬</label><select id="food-dog" name="dog_id" required>{options}</select></div>
    <div><label>ãƒ•ãƒ¼ãƒ‰å</label><input name="name" required></div><div><label>ãƒ¡ãƒ¼ã‚«ãƒ¼</label><input name="manufacturer"></div><div><label>ç¨®é¡</label><select name="food_type">{''.join(f'<option value="{key}">{label}</option>' for key, label in type_labels.items())}</select></div><div><label>1æ—¥é‡ï¼ˆgï¼‰</label><input type="number" step="0.1" min="0.1" name="amount_g"></div><div><label>1æ—¥ã®çµ¦ä¸å›æ•°</label><input type="number" min="1" max="10" name="times_per_day"></div><div><label>åˆ©ç”¨é–‹å§‹æ—¥</label><input type="date" name="started_on" value="{date.today()}" required></div><div><label>åˆ©ç”¨çµ‚äº†æ—¥</label><input type="date" name="ended_on"></div><div><label>çŠ¶æ…‹</label><select name="food_status"><option value="ongoing">åˆ©ç”¨ä¸­</option><option value="completed">çµ‚äº†</option></select></div><div><label>å¤‰æ›´ãƒ»çµ‚äº†ç†ç”±</label><input name="change_reason" placeholder="ä¾‹ï¼šæˆçŠ¬ç”¨ã¸åˆ‡æ›¿ã€é£Ÿã„ã¤ãä½ä¸‹"></div></div>
    <label>ã‚ªãƒ¼ãƒŠãƒ¼ã¸å…±æœ‰ã™ã‚‹èª¬æ˜</label><textarea name="owner_notes"></textarea><label>çŠ¬èˆå†…éƒ¨ãƒ¡ãƒ¢ï¼ˆã‚ªãƒ¼ãƒŠãƒ¼ã«ã¯è¡¨ç¤ºã•ã‚Œã¾ã›ã‚“ï¼‰</label><textarea name="notes"></textarea><label style="font-weight:400"><input style="width:auto" type="checkbox" name="owner_visible" value="true"> ã‚ªãƒ¼ãƒŠãƒ¼ãƒšãƒ¼ã‚¸ã«ã‚‚å…±æœ‰ã™ã‚‹</label><input type="hidden" name="return_to" value="foods"><button>ãƒ•ãƒ¼ãƒ‰åˆ©ç”¨è¨˜éŒ²ã‚’ç™»éŒ²</button></form>
    <h2>ãƒ•ãƒ¼ãƒ‰åˆ©ç”¨å±¥æ­´</h2><div style="overflow-x:auto"><table><tr><th>çŠ¬</th><th>ãƒ•ãƒ¼ãƒ‰</th><th>ç¨®é¡</th><th>1æ—¥é‡</th><th>å›æ•°</th><th>é–‹å§‹</th><th>çµ‚äº†ãƒ»çŠ¶æ…‹</th><th>å¤‰æ›´ç†ç”±</th><th>å…±æœ‰</th></tr>{rows or '<tr><td colspan="9">ãƒ•ãƒ¼ãƒ‰åˆ©ç”¨è¨˜éŒ²ã¯ã¾ã ã‚ã‚Šã¾ã›ã‚“ã€‚</td></tr>'}</table></div>
    <style>.dog-picker{{grid-column:span 2;min-width:0}}.dog-search-all{{display:flex;gap:7px;align-items:center;margin:8px 0;font-weight:500}}.dog-search-all input{{width:auto;margin:0}}.dog-search-count{{display:block;color:#806b72}}@media(max-width:700px){{.dog-picker{{grid-column:1/-1}}}}</style><script>document.querySelectorAll('.dog-search').forEach(function(input){{var select=document.getElementById(input.dataset.dogSelect),all=input.parentElement.querySelector('.dog-search-all input'),count=input.parentElement.querySelector('.dog-search-count'),original=Array.from(select.options).map(function(o){{return o.cloneNode(true)}});function filterDogs(){{var q=input.value.trim().toLowerCase(),current=select.value,matches=original.filter(function(o){{return (all.checked||o.dataset.nonresident!=='true')&&(!q||(o.dataset.search||o.textContent).toLowerCase().includes(q))}});select.replaceChildren.apply(select,matches.map(function(o){{return o.cloneNode(true)}}));if(matches.some(function(o){{return o.value===current}}))select.value=current;count.textContent=(all.checked?'åœ¨ç±çŠ¬ä»¥å¤–ã‚’å«ã‚€ ':'åœ¨ç±çŠ¬ ')+matches.length+'é ­ã‹ã‚‰é¸æŠ'}}input.addEventListener('input',filterDogs);all.addEventListener('change',filterDogs);filterDogs()}});</script>'''
    return layout("ãƒ•ãƒ¼ãƒ‰ç®¡ç†", body, user)


@app.post("/modules/health/food")
def food_create(dog_id: int = Form(...), name: str = Form(...), started_on: str = Form(...), ended_on: str = Form(""), manufacturer: str = Form(""), food_type: str = Form("dry"), amount_g: str = Form(""), times_per_day: str = Form(""), food_status: str = Form("ongoing"), change_reason: str = Form(""), owner_notes: str = Form(""), notes: str = Form(""), owner_visible: bool = Form(False), return_to: str = Form("health"), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    try:
        started = date.fromisoformat(started_on)
        ended = date.fromisoformat(ended_on) if ended_on else None
    except ValueError: raise HTTPException(status_code=400, detail="ãƒ•ãƒ¼ãƒ‰åˆ©ç”¨æ—¥ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if ended and ended < started:
        raise HTTPException(status_code=400, detail="åˆ©ç”¨çµ‚äº†æ—¥ã¯é–‹å§‹æ—¥ä»¥é™ã«ã—ã¦ãã ã•ã„")
    if not name.strip() or food_type not in {"dry", "wet", "raw", "prescription", "supplement", "other"} or food_status not in {"ongoing", "completed"}:
        raise HTTPException(status_code=400, detail="ãƒ•ãƒ¼ãƒ‰æƒ…å ±ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if food_status == "completed" and not ended:
        raise HTTPException(status_code=400, detail="çµ‚äº†æ¸ˆã¿ã®å ´åˆã¯åˆ©ç”¨çµ‚äº†æ—¥ã‚’å…¥åŠ›ã—ã¦ãã ã•ã„")
    try:
        amount = float(amount_g) if amount_g else None
        times = int(times_per_day) if times_per_day else None
    except ValueError:
        raise HTTPException(status_code=400, detail="çµ¦ä¸é‡ãƒ»å›æ•°ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if (amount is not None and amount <= 0) or (times is not None and not 1 <= times <= 10):
        raise HTTPException(status_code=400, detail="çµ¦ä¸é‡ãƒ»å›æ•°ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
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
        return HTMLResponse(layout("èª­ã¿å–ã‚Šã‚¨ãƒ©ãƒ¼", '<h1>èª­ã¿å–ã‚Šã§ãã¾ã›ã‚“ã§ã—ãŸ</h1><p class="error">PDFãƒ»JPGãƒ»PNGãƒ»WebPã®ã„ãšã‚Œã‹ã‚’é¸æŠã—ã¦ãã ã•ã„ã€‚</p><a class="button secondary" href="/modules/dogs">æˆ»ã‚‹</a>', user), status_code=400)
    content = await pedigree_file.read(15 * 1024 * 1024 + 1)
    if not content or len(content) > 15 * 1024 * 1024:
        return HTMLResponse(layout("èª­ã¿å–ã‚Šã‚¨ãƒ©ãƒ¼", '<h1>èª­ã¿å–ã‚Šã§ãã¾ã›ã‚“ã§ã—ãŸ</h1><p class="error">ãƒ•ã‚¡ã‚¤ãƒ«ã¯15MBä»¥ä¸‹ã«ã—ã¦ãã ã•ã„ã€‚</p><a class="button secondary" href="/modules/dogs">æˆ»ã‚‹</a>', user), status_code=400)
    try:
        with tempfile.TemporaryDirectory(prefix="pedigree-") as tmp:
            source = Path(tmp) / f"source{suffix}"
            source.write_bytes(content)
            # OCRã¯CPUè² è·ãŒé«˜ã„ãŸã‚ã‚¤ãƒ™ãƒ³ãƒˆãƒ«ãƒ¼ãƒ—å¤–ã§å®Ÿè¡Œã—ã€å‡¦ç†ä¸­ã‚‚
            # ãƒ˜ãƒ«ã‚¹ãƒã‚§ãƒƒã‚¯ã‚„ä»–ç”»é¢ã¸ã®ã‚¢ã‚¯ã‚»ã‚¹ã‚’æ­¢ã‚ãªã„ã€‚
            raw_text = await asyncio.to_thread(extract_pedigree_text, source, pedigree_file.content_type or "")
        metadata, candidates, detected_titles, detected_colors = pedigree_candidates(raw_text)
        document_metadata = pedigree_document_metadata(raw_text, metadata)
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError) as exc:
        return HTMLResponse(layout("èª­ã¿å–ã‚Šã‚¨ãƒ©ãƒ¼", f'<h1>èª­ã¿å–ã‚Šã§ãã¾ã›ã‚“ã§ã—ãŸ</h1><p class="error">ç”»åƒãŒä¸é®®æ˜ã€ã¾ãŸã¯å¯¾å¿œã§ããªã„PDFã§ã™ã€‚æ’®ã‚Šç›´ã™ã‹åˆ¥å½¢å¼ã§ãŠè©¦ã—ãã ã•ã„ã€‚</p><p><small>{html.escape(type(exc).__name__)}</small></p><a class="button secondary" href="/modules/dogs">æˆ»ã‚‹</a>', user), status_code=422)

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
        return f'<label>ã‚¿ã‚¤ãƒˆãƒ«ï¼ˆè¤‡æ•°é¸æŠå¯ï¼‰</label><select name="title_{index}" multiple size="5">{options}</select>'
    pedigree_fields = "".join(
        f'<div class="review-field"><label>{PEDIGREE_LABELS[index]}ï¼ˆ{"ç‰¡" if index % 2 else "ç‰" if index else "æœ¬äºº"}ï¼‰</label><input name="ancestor_{index}" value="{html.escape(name)}" maxlength="200" {"required" if index == 0 else ""}>{f"<label>æ¯›è‰²</label><input name=\"ancestor_color_{index}\" value=\"{html.escape(colors_by_dog[index])}\" maxlength=\"100\" placeholder=\"ä¾‹ï¼šSALT &amp; PEPPER\">" if index else ""}{title_select(index)}<label class="review-check"><input type="checkbox" name="verified_fields" value="ancestor_{index}" {"required" if name else ""}> <span>{"åŸæœ¬ã¨ç…§åˆæ¸ˆã¿" if name else "æœªèª­ï¼ˆå…¥åŠ›ã™ã‚‹å ´åˆã¯ç…§åˆã—ã¦ãã ã•ã„ï¼‰"}</span></label></div>'
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
    existing_options = '<option value="">æ–°ã—ã„çŠ¬ã¨ã—ã¦ç™»éŒ²</option>' + "".join(
        f'<option value="{dog.id}" {"selected" if dog.id == matched_dog_id else ""}>{html.escape(dog.call_name)}ï¼{html.escape(dog.registered_name or "è¡€çµ±åæœªç™»éŒ²")}ï¼å›½å†…ç•ªå·ï¼š{html.escape(dog.pedigree_no or "æœªç™»éŒ²")}ï¼æµ·å¤–ç•ªå·ï¼š{html.escape(dog.origin_registration_no or "æœªç™»éŒ²")}ï¼MCï¼š{html.escape(dog.microchip_no or "æœªç™»éŒ²")}</option>'
        for dog in existing_dogs
    )
    sex_value = metadata.get("sex", "")
    sex_options = f'<option value="" {"selected" if not sex_value else ""}>é¸æŠã—ã¦ãã ã•ã„</option><option value="male" {"selected" if sex_value == "male" else ""}>ç‰¡</option><option value="female" {"selected" if sex_value == "female" else ""}>ç‰</option>'
    document_type_options = "".join(f'<option value="{key}" {"selected" if document_metadata["type"] == key else ""}>{label}</option>' for key, label in PEDIGREE_DOCUMENT_TYPES.items())
    matched_notice = '<p class="tenant"><strong>åŒã˜ãƒã‚¤ã‚¯ãƒ­ãƒãƒƒãƒ—ç•ªå·ã¾ãŸã¯ç™»éŒ²ç•ªå·ã®çŠ¬ã‚’è¦‹ã¤ã‘ãŸãŸã‚ã€ä¸Šæ›¸ãå¯¾è±¡ã«é¸æŠã—ã¾ã—ãŸã€‚</strong> åˆ¥ã®çŠ¬ã®å ´åˆã¯é¸æŠã‚’å¤‰æ›´ã—ã¦ãã ã•ã„ã€‚</p>' if matched_dog_id else ''
    lineage_notice = f'<p class="tenant"><strong>ç™»éŒ²æ¸ˆã¿è¡€çµ±ã‚’å†åˆ©ç”¨</strong><br>{html.escape(reused_notice)}</p>' if reused_notice else ''
    body = f'''<style>.review-field{{padding:12px;border:1px solid #eadadd;border-radius:12px;background:#fffafb}}.review-check{{display:flex;align-items:center;gap:8px;margin-top:10px;color:#8b3f53}}.review-check input{{width:auto;accent-color:#b66f7c}}#pedigree-submit:disabled{{background:#b9adb1;cursor:not-allowed;box-shadow:none}}</style><h1>è¡€çµ±æ›¸ã®èª­ã¿å–ã‚Šçµæœ</h1><p><span class="badge">ç¢ºèªä»˜ãåŠè‡ªå‹•ç™»éŒ²</span></p><p class="error"><strong>OCRçµæœã¯æœªç¢ºå®šã§ã™ã€‚</strong> èª­ã‚ãªã„æ–‡å­—ã‚’æ¨æ¸¬ã—ã¦æ­£å¼ç™»éŒ²ã—ã¾ã›ã‚“ã€‚åŸæœ¬ã¨ç…§åˆã—ã¦ä¿®æ­£ã—ã€å„ã€ŒåŸæœ¬ã¨ç…§åˆæ¸ˆã¿ã€ã‚’é¸æŠã—ã¦ãã ã•ã„ã€‚</p>{matched_notice}{lineage_notice}
    <form id="pedigree-review-form" method="post" action="/modules/dogs/pedigree/import"><input type="hidden" name="upload_id" value="{upload.id}"><h2>æ–°è¦ç™»éŒ²ã¾ãŸã¯ä¸Šæ›¸ãæ›´æ–°</h2><label for="existing-dog-search">ç™»éŒ²çŠ¬ã‚’æ¤œç´¢</label><input id="existing-dog-search" type="search" placeholder="å‘¼ã³åãƒ»è¡€çµ±æ›¸åãƒ»å›½å†…ç•ªå·ãƒ»æµ·å¤–ç•ªå·ãƒ»ãƒã‚¤ã‚¯ãƒ­ãƒãƒƒãƒ—ç•ªå·ã‚’å…¥åŠ›" autocomplete="off"><p id="existing-dog-result" style="margin:6px 0;color:#765f68;font-size:12px"></p><label for="existing-dog-select">ç™»éŒ²æ–¹æ³•</label><select id="existing-dog-select" name="existing_dog_id">{existing_options}</select><p><small>åŒä¸€çŠ¬ã®æµ·å¤–è¡€çµ±æ›¸ã¨æ—¥æœ¬ã®è¼¸å…¥çŠ¬ç™»éŒ²è¨¼æ˜æ›¸ã¯ã€åŒã˜ç™»éŒ²çŠ¬ã‚’é¸ã‚“ã§ãã ã•ã„ã€‚ãƒã‚¤ã‚¯ãƒ­ãƒãƒƒãƒ—ç•ªå·ãŒä¸€è‡´ã™ã‚‹å ´åˆã¯è‡ªå‹•é¸æŠã—ã¾ã™ã€‚</small></p><h2>ä»Šå›ã‚¢ãƒƒãƒ—ãƒ­ãƒ¼ãƒ‰ã—ãŸæ›¸é¡</h2><div class="grid"><div><label>æ›¸é¡ã®ç¨®é¡</label><select name="document_type">{document_type_options}</select></div><div class="review-field"><label>ã“ã®æ›¸é¡ã«è¨˜è¼‰ã•ã‚ŒãŸç™»éŒ²ç•ªå·</label><input name="document_registration_no" value="{html.escape(document_metadata['registration_no'])}"><label class="review-check"><input type="checkbox" name="verified_fields" value="document_registration_no" required> åŸæœ¬ã¨ç…§åˆæ¸ˆã¿</label></div><div><label>ç™ºè¡Œå›£ä½“</label><input name="document_organization" value="{html.escape(document_metadata['organization'])}"></div><div><label>ç™ºè¡Œå›½</label><input name="document_country" value="{html.escape(document_metadata['country'])}"></div><div><label>ç™ºè¡Œæ—¥</label><input type="date" name="document_issued_on"></div></div><h2>ç™»éŒ²ã™ã‚‹çŠ¬ã®æƒ…å ±</h2><div class="grid"><div><label>å‘¼ã³å</label><input name="call_name" value="{html.escape(names[0])}" required maxlength="100"></div><div class="review-field"><label>çŠ¬ç¨®ï¼ˆè‡ªç”±å…¥åŠ›å¯ï¼‰</label><input name="breed" value="{html.escape(metadata.get('breed',''))}" maxlength="150" placeholder="ä¾‹ï¼šMINIATURE SCHNAUZER"><label class="review-check"><input type="checkbox" name="verified_fields" value="breed" required> åŸæœ¬ã¨ç…§åˆæ¸ˆã¿</label></div><div class="review-field"><label>æ€§åˆ¥</label><select name="sex" required>{sex_options}</select><label class="review-check"><input type="checkbox" name="verified_fields" value="sex" required> åŸæœ¬ã¨ç…§åˆæ¸ˆã¿</label></div><div><label>åŒºåˆ†</label><select name="category"><option value="parent">è¦ªçŠ¬</option><option value="puppy">å­çŠ¬</option><option value="external">å¤–éƒ¨çŠ¬</option></select></div><div class="review-field"><label>ç”Ÿå¹´æœˆæ—¥</label><input type="date" name="birth_date" value="{html.escape(metadata.get('birth_date',''))}"><label class="review-check"><input type="checkbox" name="verified_fields" value="birth_date" required> åŸæœ¬ã¨ç…§åˆæ¸ˆã¿</label></div><div class="review-field"><label>æ¯›è‰²</label><input name="color" value="{html.escape(metadata.get('color',''))}"><label class="review-check"><input type="checkbox" name="verified_fields" value="color" required> åŸæœ¬ã¨ç…§åˆæ¸ˆã¿</label></div><div class="review-field"><label>å›½å†…ãƒ¡ã‚¤ãƒ³ç•ªå·ï¼ˆJKCï¼‰</label><input name="pedigree_no" value="{html.escape(document_metadata['domestic_no'])}" placeholder="ä¾‹ï¼šJKC-MS-07782/25-I"><label class="review-check"><input type="checkbox" name="verified_fields" value="pedigree_no" required> åŸæœ¬ã¨ç…§åˆæ¸ˆã¿</label></div><div><label>å‡ºç”Ÿå›½ãƒ»æµ·å¤–ç™»éŒ²ç•ªå·</label><input name="origin_registration_no" value="{html.escape(document_metadata['origin_no'])}" placeholder="ä¾‹ï¼šKATH116090377"></div><div><label>ãƒã‚¤ã‚¯ãƒ­ãƒãƒƒãƒ—ç•ªå·</label><input name="microchip_no" value="{html.escape(metadata.get('microchip_no',''))}"></div><div><label>å‡ºç”Ÿå›½</label><input name="origin_registration_country" value="{html.escape(document_metadata['origin_country'])}"></div><div><label>æµ·å¤–ç™ºè¡Œå›£ä½“</label><input name="origin_registration_organization" value="{html.escape(document_metadata['origin_organization'])}"></div><input type="hidden" name="pedigree_country" value="æ—¥æœ¬"><input type="hidden" name="pedigree_organization" value="JKC"></div><h2>è¡€çµ±åãƒ»ã‚¿ã‚¤ãƒˆãƒ«ãƒ»è¦ªå­é–¢ä¿‚</h2><p><small>èª­ã¿å–ã‚Œãªã‹ã£ãŸå…ˆç¥–ã¯ç©ºæ¬„ã®ã¾ã¾ã§æ§‹ã„ã¾ã›ã‚“ã€‚å…¥åŠ›ã•ã‚Œã¦ã„ã‚‹å„å€‹ä½“ã¯ã€çŠ¬åãƒ»æ¯›è‰²ãƒ»ã‚¿ã‚¤ãƒˆãƒ«ã‚’åŸæœ¬ã¨ç…§åˆã—ã¦ãã ã•ã„ã€‚</small></p><div class="grid">{pedigree_fields}</div><button id="pedigree-submit" disabled>æœªç¢ºèªã®é …ç›®ãŒã‚ã‚Šã¾ã™</button> <a class="button secondary" href="/modules/dogs">ã‚­ãƒ£ãƒ³ã‚»ãƒ«</a></form>
    <script>(function(){{const search=document.getElementById('existing-dog-search');const select=document.getElementById('existing-dog-select');const result=document.getElementById('existing-dog-result');const dogs=Array.from(select.options).slice(1).map(option=>({{value:option.value,text:option.textContent}}));function render(){{const keyword=search.value.trim().toLocaleLowerCase('ja');const matches=keyword?dogs.filter(dog=>dog.text.toLocaleLowerCase('ja').includes(keyword)):dogs;const selected=select.value;select.replaceChildren(new Option('æ–°ã—ã„çŠ¬ã¨ã—ã¦ç™»éŒ²',''),...matches.map(dog=>new Option(dog.text,dog.value)));if(matches.some(dog=>dog.value===selected))select.value=selected;result.textContent=keyword?matches.length+'é ­ãŒè¦‹ã¤ã‹ã‚Šã¾ã—ãŸ':dogs.length+'é ­ã‹ã‚‰æ¤œç´¢ã§ãã¾ã™';}}search.addEventListener('input',render);render();const form=document.getElementById('pedigree-review-form');const submit=document.getElementById('pedigree-submit');function reviewState(){{for(let index=0;index<15;index++){{const field=form.querySelector('[name="ancestor_'+index+'"]');const check=form.querySelector('input[value="ancestor_'+index+'"]');if(field&&check){{check.required=Boolean(field.value.trim());check.parentElement.querySelector('span').textContent=check.required?'åŸæœ¬ã¨ç…§åˆæ¸ˆã¿':'æœªèª­ï¼ˆå…¥åŠ›ã™ã‚‹å ´åˆã¯ç…§åˆã—ã¦ãã ã•ã„ï¼‰';}}}}const checks=Array.from(form.querySelectorAll('input[name="verified_fields"]:required'));const ready=checks.every(check=>check.checked);submit.disabled=!ready;submit.textContent=ready?'ç¢ºèªã—ãŸå†…å®¹ã§ç™»éŒ²ãƒ»æ›´æ–°ã™ã‚‹':'æœªç¢ºèªã®é …ç›®ãŒã‚ã‚Šã¾ã™';}}form.addEventListener('change',reviewState);form.addEventListener('input',reviewState);reviewState();}})();</script>
    <details><summary>èª­ã¿å–ã£ãŸå…ƒã®æ–‡å­—ã‚’ç¢ºèª</summary><pre style="white-space:pre-wrap;background:#f7edef;padding:15px;border-radius:10px;max-height:300px;overflow:auto">{html.escape(raw_text[:12000])}</pre></details>'''
    return layout("è¡€çµ±æ›¸èª­ã¿å–ã‚Šç¢ºèª", body, user)


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
        raise HTTPException(status_code=400, detail="çŠ¬ã®æƒ…å ±ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    names = [value.strip() for value in [ancestor_0, ancestor_1, ancestor_2, ancestor_3, ancestor_4, ancestor_5, ancestor_6, ancestor_7, ancestor_8, ancestor_9, ancestor_10, ancestor_11, ancestor_12, ancestor_13, ancestor_14]]
    raw_colors = [color, ancestor_color_1, ancestor_color_2, ancestor_color_3, ancestor_color_4, ancestor_color_5, ancestor_color_6, ancestor_color_7, ancestor_color_8, ancestor_color_9, ancestor_color_10, ancestor_color_11, ancestor_color_12, ancestor_color_13, ancestor_color_14]
    colors = [normalize_pedigree_color(value) or value.strip() for value in raw_colors]
    titles = [title_0, title_1, title_2, title_3, title_4, title_5, title_6, title_7, title_8, title_9, title_10, title_11, title_12, title_13, title_14]
    titles = [[key for key in values if key in TITLE_LABELS] for values in titles]
    if not names[0]:
        raise HTTPException(status_code=400, detail="ç™»éŒ²ã™ã‚‹çŠ¬ã®è¡€çµ±æ›¸åãŒå¿…è¦ã§ã™")
    verified = set(verified_fields)
    required_reviews = {"document_registration_no", "breed", "sex", "birth_date", "color", "pedigree_no", "ancestor_0"}
    required_reviews.update(f"ancestor_{index}" for index, name in enumerate(names[1:], start=1) if name)
    missing_reviews = sorted(required_reviews - verified)
    if missing_reviews:
        raise HTTPException(status_code=400, detail="åŸæœ¬ã¨ã®ç…§åˆãŒå®Œäº†ã—ã¦ã„ãªã„é …ç›®ãŒã‚ã‚Šã¾ã™")
    submitted_pedigree_no = pedigree_no.strip()
    normalized_pedigree_no = normalize_jkc_number(submitted_pedigree_no) if submitted_pedigree_no else ""
    if submitted_pedigree_no and not normalized_pedigree_no:
        raise HTTPException(status_code=400, detail="å›½å†…ãƒ¡ã‚¤ãƒ³ç•ªå·ã‚’ç¢ºèªã—ã¦ãã ã•ã„ï¼ˆä¾‹ï¼šJKC-MS-05878/21ï¼‰")
    pedigree_no = normalized_pedigree_no
    # æ›¸é¡ç•ªå·ã‚‚JKCç•ªå·ãªã‚‰åŒã˜è¡¨è¨˜ã¸çµ±ä¸€ã™ã‚‹ã€‚æµ·å¤–ç•ªå·ã¯å…¥åŠ›å€¤ã‚’ä¿æŒã™ã‚‹ã€‚
    normalized_document_no = normalize_jkc_number(document_registration_no)
    if normalized_document_no:
        document_registration_no = normalized_document_no
    if birth_date:
        try:
            parsed_birth_date = date.fromisoformat(birth_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="ç”Ÿå¹´æœˆæ—¥ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
        if parsed_birth_date > date.today() or parsed_birth_date.year < 1980:
            raise HTTPException(status_code=400, detail="ç”Ÿå¹´æœˆæ—¥ã®å¹´ãƒ»æœˆãƒ»æ—¥ã‚’åŸæœ¬ã§ç¢ºèªã—ã¦ãã ã•ã„")
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
                raise HTTPException(status_code=400, detail="æ›´æ–°å¯¾è±¡ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
            existing = session.scalar(select(Dog).where(Dog.id == update_id, Dog.tenant_id == tenant.id))
            if not existing:
                raise HTTPException(status_code=400, detail="æ›´æ–°å¯¾è±¡ã®çŠ¬ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
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
    # è¡€çµ±æ›¸ã®ä¸Šæ›¸ãæ›´æ–°ã§ã€Œè²©å£²æ¸ˆã€ã€Œè­²æ¸¡æ¸ˆã€ãªã©ã®é‹ç”¨çŠ¶æ…‹ã‚’åœ¨èˆä¸­ã¸æˆ»ã•ãªã„ã€‚
    if not existing_dog_id:
        root.status = "resident"
    root.birth_date = parsed_birth_date or root.birth_date
    root.color = colors[0] or root.color
    # å›½å†…ç•ªå·ã¨å‡ºç”Ÿå›½ç•ªå·ã¯åˆ¥ç®¡ç†ã€‚æµ·å¤–è¡€çµ±æ›¸ã®è¿½åŠ ã§æ—¢å­˜JKCç•ªå·ã‚’ä¸Šæ›¸ãã—ãªã„ã€‚
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
        raise HTTPException(status_code=400, detail="ã‚¢ãƒƒãƒ—ãƒ­ãƒ¼ãƒ‰ã—ãŸè¡€çµ±æ›¸ãƒ‡ãƒ¼ã‚¿ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
    upload.dog_id = root.id
    upload.document_type = document_type
    upload.registration_no = document_registration_no.strip() or None
    upload.organization = document_organization.strip() or None
    upload.country = document_country.strip() or None
    try:
        upload.issued_on = date.fromisoformat(document_issued_on) if document_issued_on else None
    except ValueError:
        raise HTTPException(status_code=400, detail="æ›¸é¡ã®ç™ºè¡Œæ—¥ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
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
    sire_options = '<option value="">æœªç™»éŒ²</option>' + "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in dogs if d.sex == "male")
    dam_options = '<option value="">æœªç™»éŒ²</option>' + "".join(f'<option value="{d.id}">{html.escape(d.call_name)}</option>' for d in dogs if d.sex == "female")
    category_labels = {"parent": "è¦ªçŠ¬", "puppy": "å­çŠ¬", "external": "å¤–éƒ¨çŠ¬"}
    status_labels = {"resident": "åœ¨èˆä¸­", "reserved": "äºˆç´„æ¸ˆ", "delivered": "è²©å£²æ¸ˆ", "retired": "å¼•é€€", "transferred": "è­²æ¸¡æ¸ˆ"}
    sales_by_dog = {sale.dog_id: sale for sale in session.scalars(select(PuppySale).where(PuppySale.tenant_id == tenant.id).order_by(PuppySale.id)).all()}
    rows = ""
    for d in dogs:
        sale = sales_by_dog.get(d.id)
        buyer = session.get(Customer, sale.customer_id) if sale and sale.customer_id else None
        buyer_name = buyer.name if buyer else sale.customer_name if sale else "-"
        dog_name = html.escape(d.registered_name or d.call_name)
        archive_link = f" <a class='button danger' href='/modules/dogs/{d.id}/archive-confirm'>ç™»éŒ²è§£é™¤</a>" if can_archive else ""
        rows += f"<tr><td><a href='/modules/dogs/{d.id}'><strong>{dog_name}</strong></a><br><small>{html.escape(d.call_name)}</small></td><td>{title_marks(d.titles) or '-'}</td><td>{category_labels.get(d.category, d.category)}</td><td>{html.escape(d.breed or '-')}</td><td>{html.escape(d.registered_name or '-')}</td><td>{'ç‰¡' if d.sex == 'male' else 'ç‰'}</td><td>{html.escape(d.pedigree_organization or '-')}<br><small>{html.escape(d.pedigree_country or '')}</small></td><td>{d.pedigree_updated_at.date() if d.pedigree_updated_at else '-'}</td><td>{status_labels.get(d.status, d.status)}</td><td>{html.escape(buyer_name)}</td><td><a class='button secondary' href='/modules/dogs/{d.id}/edit'>ç·¨é›†</a>{archive_link}</td></tr>"
    archived_link = f'''<p><a class="button secondary" href="/modules/archived-dogs">ç™»éŒ²è§£é™¤æ¸ˆã¿ä¸€è¦§ï¼ˆ{archived_count}é ­ï¼‰</a></p>''' if can_archive else ""
    body = f'''<h1>çŠ¬ãƒ»è¡€çµ±æ›¸ç®¡ç†</h1><p>{html.escape(tenant.name)}ã®ç™»éŒ²ä¸­ã®çŠ¬ã ã‘ãŒè¡¨ç¤ºã•ã‚Œã¾ã™ã€‚</p>{archived_link}
    <div class="tenant"><h2 style="margin-top:0">å›½å†…ãƒ»æµ·å¤–è¡€çµ±æ›¸ã‹ã‚‰è‡ªå‹•ç™»éŒ²ï¼æ›´æ–°</h2><p>JKCãƒ»FCIãƒ»AKCãƒ»KCãƒ»VDHãªã©ã®PDFã¾ãŸã¯å†™çœŸã‚’å¤šè¨€èªã§èª­ã¿å–ã‚Šã€æœ¬äººã‹ã‚‰æ›¾ç¥–çˆ¶æ¯ã¾ã§æœ€å¤§15é ­ã‚’ç™»éŒ²ã—ã¾ã™ã€‚æ–°ã—ã„è¡€çµ±æ›¸ã‚’èª­ã¿è¾¼ã‚ã°ã€æ—¢å­˜çŠ¬ã‚’é¸ã‚“ã§ä¸Šæ›¸ãæ›´æ–°ã§ãã¾ã™ã€‚</p><form method="post" action="/modules/dogs/pedigree/scan" enctype="multipart/form-data"><label>è¡€çµ±æ›¸ãƒ•ã‚¡ã‚¤ãƒ«ï¼ˆPDFãƒ»JPGãƒ»PNGãƒ»WebPï¼15MBã¾ã§ï¼‰</label><input type="file" name="pedigree_file" accept="application/pdf,image/jpeg,image/png,image/webp" required><button>èª­ã¿å–ã£ã¦ç™»éŒ²ãƒ»æ›´æ–°ã™ã‚‹</button></form><p><small>å†™çœŸã¯çœŸä¸Šã‹ã‚‰ã€å½±ã‚„åå°„ãŒå…¥ã‚‰ãªã„ã‚ˆã†ã«æ’®å½±ã™ã‚‹ã¨ç²¾åº¦ãŒä¸ŠãŒã‚Šã¾ã™ã€‚ç™»éŒ²å‰ã«å¿…ãšèª­ã¿å–ã‚Šçµæœã‚’ã”ç¢ºèªãã ã•ã„ã€‚</small></p></div>
    <p>{title_marks('champion')}ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³ã€€{title_marks('international_champion')}ã‚¤ãƒ³ã‚¿ãƒ¼ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³ã€€{title_marks('junior_champion')}Jr.ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³ã€€{title_marks('junior_international_champion')}Jr.ã‚¤ãƒ³ã‚¿ãƒ¼ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³ã€€{title_marks('grand_champion')}ã‚°ãƒ©ãƒ³ãƒ‰ãƒãƒ£ãƒ³ãƒ”ã‚ªãƒ³</p>
    <h2>æ‰‹å…¥åŠ›ã§çŠ¬ã‚’ç™»éŒ²</h2>
    <form method="post"><div class="grid"><div><label>åŒºåˆ†</label><select name="category"><option value="parent">è¦ªçŠ¬</option><option value="puppy">å­çŠ¬</option><option value="external">å¤–éƒ¨çŠ¬</option></select></div><div><label>å‘¼ã³å</label><input name="call_name" required></div><div><label>çŠ¬ç¨®ï¼ˆè‡ªç”±å…¥åŠ›å¯ï¼‰</label><input name="breed" maxlength="150" placeholder="ä¾‹ï¼šãƒŸãƒƒã‚¯ã‚¹ï¼ˆã‚·ãƒ¥ãƒŠã‚¦ã‚¶ãƒ¼Ã—ãƒ—ãƒ¼ãƒ‰ãƒ«ï¼‰"></div><div><label>è¡€çµ±æ›¸å</label><input name="registered_name"></div><div><label>æ€§åˆ¥</label><select name="sex"><option value="male">ç‰¡</option><option value="female">ç‰</option></select></div><div><label>çŠ¶æ…‹</label><select name="status"><option value="resident">åœ¨èˆä¸­</option><option value="reserved">äºˆç´„æ¸ˆ</option><option value="delivered">è²©å£²æ¸ˆ</option><option value="retired">å¼•é€€</option><option value="transferred">è­²æ¸¡æ¸ˆ</option></select></div><div><label>ç”Ÿå¹´æœˆæ—¥</label><input name="birth_date" type="date"></div><div><label>æ¯›è‰²</label><input name="color"></div><div><label>çˆ¶çŠ¬</label><select name="sire_id">{sire_options}</select></div><div><label>æ¯çŠ¬</label><select name="dam_id">{dam_options}</select></div><div><label>ãƒã‚¤ã‚¯ãƒ­ãƒãƒƒãƒ—ç•ªå·</label><input name="microchip_no"></div><div><label>è¡€çµ±æ›¸ç•ªå·</label><input name="pedigree_no"></div></div><p><small>è¡€çµ±æ›¸ãŒãªã„ãƒŸãƒƒã‚¯ã‚¹çŠ¬ã‚‚ã€çŠ¬ç¨®ã‚’ä»»æ„ã®åç§°ã§å…¥åŠ›ã—ã¦ç™»éŒ²ã§ãã¾ã™ã€‚</small></p><button>çŠ¬ã‚’ç™»éŒ²</button></form>
    <table><tr><th>å‘¼ã³å</th><th>ã‚¿ã‚¤ãƒˆãƒ«</th><th>åŒºåˆ†</th><th>çŠ¬ç¨®</th><th>è¡€çµ±æ›¸å</th><th>æ€§åˆ¥</th><th>ç™ºè¡Œå›£ä½“ãƒ»å›½</th><th>è¡€çµ±æ›¸æ›´æ–°æ—¥</th><th>çŠ¶æ…‹</th><th>è²©å£²å…ˆ</th><th>æ“ä½œ</th></tr>{rows}</table>'''
    return layout("çŠ¬ãƒ»è¡€çµ±æ›¸ç®¡ç†", body, user)


@app.get("/modules/dogs/{dog_id}/archive-confirm", response_class=HTMLResponse)
def dog_archive_confirm(dog_id: int, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if not dog.active:
        return RedirectResponse("/modules/archived-dogs", status_code=303)
    body = f'''<h1>ç™»éŒ²è§£é™¤ã®ç¢ºèª</h1><div class="tenant"><h2 style="margin-top:0">{html.escape(dog.call_name)}</h2><p>{html.escape(dog.registered_name or "è¡€çµ±æ›¸åæœªç™»éŒ²")}</p></div><p class="error">ã“ã®çŠ¬ã‚’ç™»éŒ²è§£é™¤ã™ã‚‹ã¨ã€é€šå¸¸ã®çŠ¬ä¸€è¦§ãƒ»åœ¨ç±çŠ¬ä¸€è¦§ãƒ»ä»”çŠ¬ï¼è¦ªçŠ¬ä¸€è¦§ã‹ã‚‰éè¡¨ç¤ºã«ãªã‚Šã¾ã™ã€‚</p><p>å¥åº·ãƒ»ç¹æ®–ãƒ»è¡€çµ±ãƒ»è²©å£²ãªã©ã®å±¥æ­´ã¯å‰Šé™¤ã•ã‚Œãšã€å¾Œã‹ã‚‰å¾©å…ƒã§ãã¾ã™ã€‚</p><form method="post" action="/modules/dogs/{dog.id}/archive"><button class="danger">ç™»éŒ²è§£é™¤ã™ã‚‹</button> <a class="button secondary" href="/modules/dogs">ã‚­ãƒ£ãƒ³ã‚»ãƒ«</a></form>'''
    return layout("ç™»éŒ²è§£é™¤ã®ç¢ºèª", body, user)


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
        f'''<tr><td><strong>{html.escape(dog.call_name)}</strong><br><small>{html.escape(dog.registered_name or "è¡€çµ±æ›¸åæœªç™»éŒ²")}</small></td><td>{html.escape(dog.breed or "-")}</td><td>{"ç‰¡" if dog.sex == "male" else "ç‰"}</td><td>{html.escape(dog.pedigree_no or "-")}</td><td><form class="inline" method="post" action="/modules/dogs/{dog.id}/restore"><button class="success">å¾©å…ƒã™ã‚‹</button></form></td></tr>'''
        for dog in dogs
    )
    body = f'''<h1>ç™»éŒ²è§£é™¤æ¸ˆã¿ã®çŠ¬</h1><p>ç™»éŒ²è§£é™¤ã—ãŸçŠ¬ã‚’å¾©å…ƒã§ãã¾ã™ã€‚é–¢é€£ã™ã‚‹å¥åº·ãƒ»ç¹æ®–ãƒ»è¡€çµ±ãƒ»è²©å£²å±¥æ­´ã¯ä¿æŒã•ã‚Œã¦ã„ã¾ã™ã€‚</p><table><tr><th>çŠ¬å</th><th>çŠ¬ç¨®</th><th>æ€§åˆ¥</th><th>è¡€çµ±æ›¸ç•ªå·</th><th>æ“ä½œ</th></tr>{rows or '<tr><td colspan="5">ç™»éŒ²è§£é™¤æ¸ˆã¿ã®çŠ¬ã¯ã„ã¾ã›ã‚“ã€‚</td></tr>'}</table><p><a class="button secondary" href="/modules/dogs">çŠ¬ãƒ»è¡€çµ±æ›¸ç®¡ç†ã¸æˆ»ã‚‹</a></p>'''
    return layout("ç™»éŒ²è§£é™¤æ¸ˆã¿ã®çŠ¬", body, user)


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
    # å‡ºç”£ç®¡ç†ã®è¨˜éŒ²ã¨ã€æ¯çŠ¬ã«ç´ã¥ãä»”çŠ¬ã®èª•ç”Ÿæ—¥ã‚’çµ±åˆã™ã‚‹ã€‚åŒã˜æ—¥ä»˜ã¯
    # åŒä¸€ã®å‡ºç”£ã¨ã—ã¦æ•°ãˆã‚‹ãŸã‚ã€ä¸¡æ–¹ã«ç™»éŒ²ã•ã‚Œã¦ã„ã¦ã‚‚äºŒé‡è¨ˆä¸Šã—ãªã„ã€‚
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
    metrics = f'''<div class="grid"><div class="module"><h3>åœ¨ç±åˆè¨ˆ</h3><p><strong style="font-size:28px">{len(dogs)}</strong>é ­</p></div><div class="module"><h3>ç‰¡ï¼ç‰</h3><p><strong>{males}</strong>é ­ ï¼ <strong>{females}</strong>é ­</p></div><div class="module"><h3>è¦ªçŠ¬</h3><p><strong style="font-size:28px">{parents}</strong>é ­</p></div><div class="module"><h3>å­çŠ¬</h3><p><strong style="font-size:28px">{puppies}</strong>é ­</p></div></div>'''
    rows = ""
    today = date.today()
    for dog in dogs:
        if dog.birth_date:
            months = (today.year - dog.birth_date.year) * 12 + today.month - dog.birth_date.month - (today.day < dog.birth_date.day)
            age = f"{months // 12}æ­³{months % 12}ã‹æœˆ" if months >= 12 else f"{max(months, 0)}ã‹æœˆ"
        else:
            age = "-"
        sire = session.get(Dog, dog.sire_id) if dog.sire_id else None
        dam = session.get(Dog, dog.dam_id) if dog.dam_id else None
        category = {"parent":"è¦ªçŠ¬", "puppy":"å­çŠ¬"}.get(dog.category, dog.category)
        state = "äºˆç´„æ¸ˆ" if dog.status == "reserved" else "åœ¨èˆä¸­"
        lifetime_births = len(birth_dates_by_dam.get(dog.id, set())) if dog.sex == "female" else None
        birth_count = f'''<strong>{lifetime_births}</strong>å›''' if lifetime_births is not None else "å¯¾è±¡å¤–"
        rows += f'''<tr><td><a href="/modules/dogs/{dog.id}"><strong>{html.escape(dog.call_name)}</strong></a><br><small>{html.escape(dog.registered_name or "è¡€çµ±åæœªç™»éŒ²")}</small></td><td>{title_marks(dog.titles) or "-"}</td><td>{"ç‰¡" if dog.sex == "male" else "ç‰"}</td><td>{category}</td><td>{html.escape(dog.breed or "-")}</td><td>{dog.birth_date or "-"}<br><small>{age}</small></td><td>{html.escape(dog.color or "-")}</td><td>{html.escape(sire.registered_name or sire.call_name) if sire else "-"}</td><td>{html.escape(dam.registered_name or dam.call_name) if dam else "-"}</td><td>{birth_count}</td><td><span class="badge">{state}</span></td><td><a class="button secondary" href="/modules/dogs/{dog.id}/edit">ç·¨é›†</a></td></tr>'''
    body = f'''<h1>åœ¨ç±çŠ¬ä¸€è¦§</h1><p>{html.escape(tenant.name)}ã§ç¾åœ¨ç®¡ç†ã—ã¦ã„ã‚‹åœ¨èˆä¸­ãƒ»äºˆç´„æ¸ˆã¿ã®çŠ¬ã‚’è¡¨ç¤ºã—ã¦ã„ã¾ã™ã€‚</p>{metrics}<table><tr><th>çŠ¬å</th><th>ã‚¿ã‚¤ãƒˆãƒ«</th><th>æ€§åˆ¥</th><th>åŒºåˆ†</th><th>çŠ¬ç¨®</th><th>ç”Ÿå¹´æœˆæ—¥ãƒ»å¹´é½¢</th><th>æ¯›è‰²</th><th>çˆ¶çŠ¬</th><th>æ¯çŠ¬</th><th>ç”Ÿæ¶¯å‡ºç”£å›æ•°</th><th>çŠ¶æ…‹</th><th>æ“ä½œ</th></tr>{rows or '<tr><td colspan="12">åœ¨ç±çŠ¬ã¯ã¾ã ç™»éŒ²ã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚</td></tr>'}</table>'''
    return layout("åœ¨ç±çŠ¬ä¸€è¦§", body, user)


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
    metrics = f'''<div class="grid"><div class="module"><h3>è­²æ¸¡æ¸ˆåˆè¨ˆ</h3><p><strong style="font-size:28px">{len(dogs)}</strong>é ­</p></div><div class="module"><h3>ç‰¡ï¼ç‰</h3><p><strong>{male_count}</strong>é ­ ï¼ <strong>{female_count}</strong>é ­</p></div><div class="module"><h3>ä»”çŠ¬</h3><p><strong style="font-size:28px">{puppy_count}</strong>é ­</p></div><div class="module"><h3>è¦ªçŠ¬</h3><p><strong style="font-size:28px">{parent_count}</strong>é ­</p></div></div>'''
    rows = ""
    for dog in dogs:
        transfer = transfers_by_dog.get(dog.id)
        customer = session.get(Customer, transfer.customer_id) if transfer and transfer.customer_id else None
        recipient = customer.name if customer else "æœªç™»éŒ²"
        sire = session.get(Dog, dog.sire_id) if dog.sire_id else None
        dam = session.get(Dog, dog.dam_id) if dog.dam_id else None
        category = {"parent": "è¦ªçŠ¬", "puppy": "ä»”çŠ¬"}.get(dog.category, dog.category)
        handover_date = transfer.transferred_on if transfer else "-"
        transfer_amount = f"Â¥{transfer.amount:,}" if transfer and transfer.amount is not None else "-"
        transfer_label = "è­²æ¸¡å…ˆã‚’å¤‰æ›´" if transfer else "è­²æ¸¡å…ˆã‚’ç™»éŒ²"
        rows += f'''<tr><td><a href="/modules/dogs/{dog.id}"><strong>{html.escape(dog.call_name)}</strong></a><br><small>{html.escape(dog.registered_name or "è¡€çµ±åæœªç™»éŒ²")}</small></td><td>{category}</td><td>{"ç‰¡" if dog.sex == "male" else "ç‰"}</td><td>{html.escape(dog.breed or "-")}</td><td>{dog.birth_date or "-"}</td><td>{html.escape(dog.color or "-")}</td><td>{html.escape(sire.registered_name or sire.call_name) if sire else "-"}</td><td>{html.escape(dam.registered_name or dam.call_name) if dam else "-"}</td><td>{html.escape(recipient)}</td><td>{handover_date}</td><td>{transfer_amount}</td><td><a class="button" href="/modules/transferred-dogs/{dog.id}">{transfer_label}</a> <a class="button secondary" href="/modules/dogs/{dog.id}">è©³ç´°</a></td></tr>'''
    body = f'''<h1>è­²æ¸¡æ¸ˆä¸€è¦§</h1><p>{html.escape(tenant.name)}ã§ã€Œè­²æ¸¡æ¸ˆã€ã«è¨­å®šã—ãŸçŠ¬ã‚’è¡¨ç¤ºã—ã¦ã„ã¾ã™ã€‚è¡€çµ±å‚ç…§ç”¨ã®å¤–éƒ¨çŠ¬ã¯å«ã¿ã¾ã›ã‚“ã€‚</p><p><small>æœ‰å„Ÿã§è²©å£²ã—ãŸä»”çŠ¬ã¯ã€Œè²©å£²çŠ¬ä¸€è¦§ã€ã§ç®¡ç†ã—ã€ç„¡å„Ÿãƒ»æœ‰å„Ÿã‚’å•ã‚ãªã„è­²æ¸¡ã¯ã“ã®ç”»é¢ã§ç¢ºèªã§ãã¾ã™ã€‚</small></p>{metrics}<table><tr><th>çŠ¬å</th><th>åŒºåˆ†</th><th>æ€§åˆ¥</th><th>çŠ¬ç¨®</th><th>ç”Ÿå¹´æœˆæ—¥</th><th>æ¯›è‰²</th><th>çˆ¶çŠ¬</th><th>æ¯çŠ¬</th><th>è­²æ¸¡å…ˆ</th><th>è­²æ¸¡æ—¥</th><th>è­²æ¸¡é‡‘é¡</th><th>æ“ä½œ</th></tr>{rows or '<tr><td colspan="12">è­²æ¸¡æ¸ˆã¿ã®çŠ¬ã¯ã„ã¾ã›ã‚“ã€‚</td></tr>'}</table>'''
    return layout("è­²æ¸¡æ¸ˆä¸€è¦§", body, user)


@app.get("/modules/transferred-dogs/{dog_id}", response_class=HTMLResponse)
def dog_transfer_page(dog_id: int, access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dog = tenant_dog(session, tenant.id, dog_id)
    if not dog.active or dog.category == "external":
        raise HTTPException(status_code=404, detail="è­²æ¸¡å…ˆã‚’ç™»éŒ²ã§ãã‚‹çŠ¬ã§ã¯ã‚ã‚Šã¾ã›ã‚“")
    transfer = session.scalar(select(DogTransfer).where(DogTransfer.tenant_id == tenant.id, DogTransfer.dog_id == dog.id))
    customers = session.scalars(select(Customer).where(Customer.tenant_id == tenant.id).order_by(Customer.name)).all()
    selected_customer_id = transfer.customer_id if transfer else None
    customer_options = '<option value="">æ–°ã—ã„è­²æ¸¡å…ˆã‚’å…¥åŠ›ã™ã‚‹</option>' + "".join(
        f'<option value="{customer.id}" {"selected" if customer.id == selected_customer_id else ""}>{html.escape(customer.name)}ï¼{html.escape(customer.phone or customer.email or "é€£çµ¡å…ˆæœªç™»éŒ²")}</option>'
        for customer in customers
    )
    selected_customer = session.get(Customer, selected_customer_id) if selected_customer_id else None
    registered_customer = ""
    if selected_customer:
        registered_customer = f'''<div class="tenant"><strong>ç¾åœ¨ã®è­²æ¸¡å…ˆ</strong><p>{html.escape(selected_customer.name)}ã€€{html.escape(selected_customer.phone or "")}<br>{html.escape(selected_customer.email or "")}<br>{html.escape(selected_customer.postal_code or "")} {html.escape(selected_customer.address or "")}</p></div>'''
    body = f'''<h1>è­²æ¸¡å…ˆã®ç™»éŒ²</h1><div class="tenant"><h2 style="margin-top:0">{html.escape(dog.call_name)}</h2><p>{html.escape(dog.registered_name or "è¡€çµ±åæœªç™»éŒ²")}ï¼{"ç‰¡" if dog.sex == "male" else "ç‰"}ï¼{html.escape(dog.breed or "çŠ¬ç¨®æœªç™»éŒ²")}</p></div>{registered_customer}
    <form method="post" action="/modules/transferred-dogs/{dog.id}"><h2>ç™»éŒ²æ¸ˆã¿ã®ãŠå®¢æ§˜ã‚’é¸ã¶</h2><label>è­²æ¸¡å…ˆ</label><select name="customer_id">{customer_options}</select><p><small>ç™»éŒ²æ¸ˆã¿ã®ãŠå®¢æ§˜ã‚’é¸ã‚“ã å ´åˆã€ä¸‹ã®æ–°è¦å…¥åŠ›æ¬„ã¯ä½¿ç”¨ã—ã¾ã›ã‚“ã€‚</small></p>
    <h2>æ–°ã—ã„è­²æ¸¡å…ˆã‚’ç™»éŒ²ã™ã‚‹</h2><div class="grid"><div><label>ãŠåå‰</label><input name="customer_name" maxlength="150"></div><div><label>ãƒ•ãƒªã‚¬ãƒŠ</label><input name="customer_name_kana" maxlength="150"></div><div><label>é›»è©±ç•ªå·</label><input name="customer_phone" type="tel" maxlength="50"></div><div><label>ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹</label><input name="customer_email" type="email" maxlength="255"></div><div><label>éƒµä¾¿ç•ªå·</label><input name="customer_postal_code" maxlength="20"></div><div><label>ä½æ‰€</label><input name="customer_address" maxlength="300"></div></div>
    <h2>è­²æ¸¡æƒ…å ±</h2><div class="grid"><div><label>è­²æ¸¡æ—¥</label><input name="transferred_on" type="date" value="{transfer.transferred_on if transfer else date.today()}" required></div><div><label>è­²æ¸¡é‡‘é¡ï¼ˆå††ï¼‰</label><input name="amount" type="number" min="0" step="1" value="{transfer.amount if transfer and transfer.amount is not None else ""}" placeholder="ç„¡æ–™ã®å ´åˆã¯0ã¾ãŸã¯ç©ºæ¬„"><small>å††å˜ä½ãƒ»åŠè§’æ•°å­—ã§å…¥åŠ›ã—ã¦ãã ã•ã„ã€‚</small></div><div><label>è­²æ¸¡ç†ç”±</label><select name="reason"><option value="">é¸æŠã—ã¦ãã ã•ã„</option>{''.join(f'<option value="{value}" {"selected" if transfer and transfer.reason == value else ""}>{value}</option>' for value in ["å¼•é€€çŠ¬ã®è­²æ¸¡", "ç¹æ®–çŠ¬ã®è­²æ¸¡", "ç„¡å„Ÿè­²æ¸¡", "æœ‰å„Ÿè­²æ¸¡", "å…±åŒæ‰€æœ‰", "ãã®ä»–"])}</select></div></div><label>ãƒ¡ãƒ¢</label><textarea name="notes" placeholder="è­²æ¸¡æ™‚ã®å–ã‚Šæ±ºã‚ã€åç¾©å¤‰æ›´ã€å¥åº·çŠ¶æ…‹ãªã©">{html.escape(transfer.notes or "") if transfer else ""}</textarea><button>è­²æ¸¡å…ˆæƒ…å ±ã‚’ä¿å­˜ã™ã‚‹</button> <a class="button secondary" href="/modules/transferred-dogs">ã‚­ãƒ£ãƒ³ã‚»ãƒ«</a></form>'''
    return layout("è­²æ¸¡å…ˆã®ç™»éŒ²", body, user)


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
        raise HTTPException(status_code=400, detail="è­²æ¸¡å…ˆã‚’ç™»éŒ²ã§ãã‚‹çŠ¬ã§ã¯ã‚ã‚Šã¾ã›ã‚“")
    try:
        transfer_date = date.fromisoformat(transferred_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="è­²æ¸¡æ—¥ã‚’ç¢ºèªã—ã¦ãã ã•ã„")
    if transfer_date > date.today():
        raise HTTPException(status_code=400, detail="æœªæ¥ã®æ—¥ä»˜ã¯è­²æ¸¡æ—¥ã«ç™»éŒ²ã§ãã¾ã›ã‚“")
    try:
        transfer_amount = int(amount) if amount.strip() else None
    except ValueError:
        raise HTTPException(status_code=400, detail="è­²æ¸¡é‡‘é¡ã¯å††å˜ä½ã®æ•°å­—ã§å…¥åŠ›ã—ã¦ãã ã•ã„")
    if transfer_amount is not None and transfer_amount < 0:
        raise HTTPException(status_code=400, detail="è­²æ¸¡é‡‘é¡ã¯0å††ä»¥ä¸Šã§å…¥åŠ›ã—ã¦ãã ã•ã„")
    if customer_id:
        try:
            selected_customer_id = int(customer_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="è­²æ¸¡å…ˆã‚’ç¢ºèªã—ã¦ãã ã•ã„")
        customer = session.scalar(select(Customer).where(Customer.id == selected_customer_id, Customer.tenant_id == tenant.id))
        if not customer:
            raise HTTPException(status_code=400, detail="è­²æ¸¡å…ˆãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“")
    else:
        if not customer_name.strip():
            raise HTTPException(status_code=400, detail="ç™»éŒ²æ¸ˆã¿ã®ãŠå®¢æ§˜ã‚’é¸ã¶ã‹ã€æ–°ã—ã„è­²æ¸¡å…ˆã®ãŠåå‰ã‚’å…¥åŠ›ã—ã¦ãã ã•ã„")
        customer = Customer(
            tenant_id=tenant.id, name=customer_name.strip(), name_kana=customer_name_kana.strip() or None,
            phone=customer_phone.strip() or None, email=normalize_email(customer_email) if customer_email.strip() else None,
            postal_code=customer_postal_code.strip() or None, address=customer_address.strip() or None,
            notes="è­²æ¸¡å…ˆç™»éŒ²ç”»é¢ã‹ã‚‰ä½œæˆ",
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
    labels = {"puppy": "ä»”çŠ¬ä¸€è¦§", "parent": "è¦ªçŠ¬ä¸€è¦§", "external": "å¤–éƒ¨çŠ¬ä¸€è¦§"}
    if category not in labels:
        raise HTTPException(status_code=404)
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True), Dog.category == category).order_by(Dog.birth_date.desc(), Dog.registered_name, Dog.call_name)).all()
    status_labels = {"resident":"åœ¨èˆä¸­", "reserved":"äºˆç´„æ¸ˆ", "delivered":"è²©å£²æ¸ˆ", "retired":"å¼•é€€", "transferred":"è­²æ¸¡æ¸ˆ"}
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
        rows += f'''<tr><td><a href="/modules/dogs/{dog.id}"><strong>{html.escape(dog.call_name)}</strong></a><br><small>{html.escape(dog.registered_name or "è¡€çµ±åæœªç™»éŒ²")}</small></td><td>{title_marks(dog.titles) or "-"}</td><td>{"ç‰¡" if dog.sex == "male" else "ç‰"}</td><td>{html.escape(dog.breed or "-")}</td><td>{dog.birth_date or "-"}</td><td>{html.escape(dog.color or "-")}</td><td>{html.escape(dog.pedigree_no or "-")}</td><td>{html.escape(sire.registered_name or sire.call_name) if sire else "-"}</td><td>{html.escape(dam.registered_name or dam.call_name) if dam else "-"}</td><td><span class="badge">{status_labels.get(dog.status, dog.status)}</span></td>{f'<td>{html.escape(buyer_name)}</td>' if category == 'puppy' else ''}<td><a class="button secondary" href="/modules/dogs/{dog.id}/edit">ç·¨é›†</a></td></tr>'''
    buyer_header = "<th>è²©å£²å…ˆ</th>" if category == "puppy" else ""
    columns = 12 if category == "puppy" else 11
    metrics = f'''<div class="grid"><div class="module"><h3>ç™»éŒ²é ­æ•°</h3><p><strong style="font-size:28px">{len(dogs)}</strong>é ­</p></div><div class="module"><h3>ç‰¡</h3><p><strong style="font-size:28px">{male_count}</strong>é ­</p></div><div class="module"><h3>ç‰</h3><p><strong style="font-size:28px">{female_count}</strong>é ­</p></div><div class="module"><h3>åœ¨èˆãƒ»äºˆç´„ä¸­</h3><p><strong style="font-size:28px">{resident_count}</strong>é ­</p></div></div>'''
    description = "è¡€çµ±å‚ç…§ãƒ»äº¤é…æ¤œè¨ã®ãŸã‚ã«ç™»éŒ²ã—ãŸçŠ¬ã§ã™ã€‚" if category == "external" else "ç™»éŒ²æ¸ˆã¿ã®çŠ¬ã‚’çŠ¶æ…‹ã«ã‹ã‹ã‚ã‚‰ãšè¡¨ç¤ºã—ã¦ã„ã¾ã™ã€‚"
    body = f'''<h1>{labels[category]}</h1><p>{html.escape(tenant.name)} â€” {description}</p>{metrics}<table><tr><th>çŠ¬å</th><th>ã‚¿ã‚¤ãƒˆãƒ«</th><th>æ€§åˆ¥</th><th>çŠ¬ç¨®</th><th>ç”Ÿå¹´æœˆæ—¥</th><th>æ¯›è‰²</th><th>è¡€çµ±æ›¸ç•ªå·</th><th>çˆ¶çŠ¬</th><th>æ¯çŠ¬</th><th>çŠ¶æ…‹</th>{buyer_header}<th>æ“ä½œ</th></tr>{rows or f'<tr><td colspan="{columns}">ç™»éŒ²çŠ¬ã¯ã„ã¾ã›ã‚“ã€‚</td></tr>'}</table>'''
    return layout(labels[category], body, user)


@app.get("/modules/sale-dogs", response_class=HTMLResponse)
def sale_dogs_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    puppies = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id, Dog.active.is_(True), Dog.category == "puppy").order_by(Dog.dam_id, Dog.birth_date.desc(), Dog.call_name)).all()
    sales = session.scalars(select(PuppySale).where(PuppySale.tenant_id == tenant.id).order_by(PuppySale.id)).all()
    sales_by_dog = {sale.dog_id: sale for sale in sales}
    dog_states = {"resident":"è²©å£²ä¸­", "reserved":"äºˆç´„æ¸ˆ", "delivered":"è²©å£²æ¸ˆ", "retired":"å¼•é€€", "transferred":"è­²æ¸¡æ¸ˆ"}
    sale_states = {
        "inquiry":"å•ã„åˆã‚ã›", "visit":"è¦‹å­¦äºˆå®š", "consideration":"æ¤œè¨ä¸­", "reserved":"äºˆç´„æ¸ˆã¿",
        "contracted":"å¥‘ç´„æ¸ˆã¿", "paid":"å…¥é‡‘æ¸ˆã¿", "handed_over":"è²©å£²å®Œäº†", "cancelled":"ã‚­ãƒ£ãƒ³ã‚»ãƒ«",
    }
    groups: dict[int | None, list[Dog]] = {}
    foçuÓÆòµë(š+myÖÆVâ†6öçFVçB’â‚¢#B¢#B÷"æ÷Bf–ÆVæÖR÷"ÆVâ†—77VVEö'’’âS÷"ÆVâ†Fö7VÖVçEöæò’â ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.i»šî8õDn8;´¥~8;µä~8;µvV%8ã„Ô.Kº^Kˆ¾8~y›¾˜Ë.8~8n8ş88^8B"¢6W76–öâæFB„f–ææ6TFö7VÖVçB‡FVæçEö–C×FVæçBæ–BÂf–ææ6–ÅöVçG'•ö–CÖVçG'’æ–BÂFö7VÖVçE÷G—SÖFö7VÖVçE÷G—RÂ—77VVEö'“Ö—77VVEö'’ç7G&—‚’÷"æöæRÂFö7VÖVçEöæóÖFö7VÖVçEöæòç7G&—‚’÷"æöæRÂf–ÆVæÖSÖf–ÆVæÖRÂ6öçFVçE÷G—SÖFö7VÖVçEöf–ÆRæ6öçFVçE÷G—RÂf–ÆUöFFÖ6öçFVçB’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öÖöGVÆW2öf–ææ6RöFö7VÖVçG2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öÖöGVÆW2öf–ææ6RöFö7VÖVçG2÷¶Fö7VÖVçEö–GÒöf–ÆR"¦FVbf–ææ6UöFö7VÖVçEöf–ÆR†Fö7VÖVçEö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçE÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„f–ææ6TFö7VÖVçB’çv†W&R„f–ææ6TFö7VÖVçBæ–BÓÒFö7VÖVçEö–BÂf–ææ6TFö7VÖVçBçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B—FVÓ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.i»šî8ÎŠh¾8N8¾8(®8î8¾8)2"¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒæf–ÆUöFFÂÖVF–÷G—SÖ—FVÒæ6öçFVçE÷G—RÂ†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R"Â%‚Ô6öçFVçBÕG—RÔ÷F–öç2#¢&æ÷6æ–fb"Â$6öçFVçBÔF—7÷6—F–öâ#¢b&–æÆ–æS²f–ÆVæÖR£ÕUDbÓ‚rw·V÷FR†—FVÒæf–ÆVæÖR—Ò'Ò  ¤ævWB‚"öÖöGVÆW2÷¶ÖöGVÆUö¶W—Ò"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbÖöGVÆU÷vR†ÖöGVÆUö¶W“¢7G"Â66W73ÔFWVæG2‡&WV—&U÷FVæçE÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bÖöGVÆUö¶W’æ÷B–âÔôETÄU2÷"ÖöGVÆUö¶W’–â²&Föw2"Â'FöFò"Â&6ÆVæF""Â&'&VVF–ær"Â&&—'F‡2"Â&†VÇF‚"Â&vVæWF–72"Â'6ÆW2"Â&f–ææ6R"Â&–çfö–6W2"Â&6÷7G2'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢W6W"ÂFVæçBÒ66W70¢F—FÆRÂFW67&—F–öâÒÔôETÄU5¶ÖöGVÆUö¶W•Ğ¢FWF–Ç2Ò°¢&ÆVvÂ#¢.Zé®iÉşZY®8zÊÎKˆzŠîX¹^xšXùnh›jZŞ8î™h¾Zx¾8;¾i»Nik8;¾ZHi»Ni»šî8k9^Zé®[‹>{ş8).KÙÎh‰8;¾KùŞZÙ8~8î88""À¢&'&VVF–ær#¢.x‹nxªÎ8;¾jøŞxªÎ8KªN˜XŞiz^8Zh®ZŠx«nk88‹ùŠj®KªN˜XŞxè~8).Š‰˜Ë.8~8[niÚ^8şŠ{[8¾8({XN8şY8(ş8¾8).hùj8~8î88""À¢&&—'F‡2#¢.89.8;Î88™h¾Zx¾iz^8KªN˜XŞK¨Zé®8X{®yJ>K¨Zé®8X{®yIşš
Şi[8K¹NxªÎ8îx«nhX¾8).zêyn8~8î88""À¢&†VÇF‚#¢.KÙ>˜xŞ8Š‹®y˜.8h©^‰jÎ8X^[«~Š‹®ijŞ88:ş8*ş888;>8jÊY¹îhê^zŠîiz^8).zêyn8~8î88""À¢&vVæWF–72#¢.˜®KÉŞyx^8N88î8*ş8:®8*.8;¾8*Ş8:>8:®8*.8;¾8*.89^8*~8*ş88n88>88zØ8î{YiéÎ8jIÎiû¾j™ş™j.8).zêyn8~8î88""À¢'6ÆW2#¢.YXş8NY8(ş8¾8¾8(ZY{HN8k9^Zé®ŠªÎiˆî8Kº>˜y8[É^kŠ8~88*.89^8+ş8;Î89^8*8:Ş8;Î8î8~zêyn8~8î88""À¢Ğ¢&öG’ÒbsÆƒç·F—FÆWÓÂöƒãÇãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷7ããÂ÷ãÇç¶FW67&—F–öçÓÂ÷ãÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsî8>8îj™şˆ;Ş8~ŠÎ8n8>8ƒÂ÷7G&öæsãÇç¶FWF–Ç5¶ÖöGVÆUö¶W•×ÓÂ÷ãÂöF—cãÇî[.yJ88~8;Î8+ş898;Î8+8şKÙÎh‰kˆ8ş8~88.XZ^X©¾8;¾[‹>zZyK¾™Ú.8).šnjÊ‹ûŞXª8~8î88#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öF6†&ö&B#îjZŞX¹89¾8;Î8:8h‹¾8(³Âöâp¢&WGW&âÆ–÷WB‡F—FÆRÂ&öG’ÂW6W"  ¤ævWB‚"÷ÆFf÷&Ò÷FVæçG2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbFVæçEöÆ—7B‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BW6W"çÆFf÷&ÕöFÖ–ã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2¢FVæçG2Ò6W76–öâç66Æ'2‡6VÆV7B…FVæçB’æ÷&FW%ö'’…FVæçBææÖR’’æÆÂ‚¢&÷w2Ò" ¢f÷"FVæçB–âFVæçG3 ¢–bFVæçBæFVÆWFVC ¢7FFRÒsÇ7â6Æ73Ò&&FvR#îX˜®™šNkˆ8óÂ÷7ãâp¢7F–öç2ÒbsÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"÷ÆFf÷&Ò÷FVæçG2÷·FVæçBæ–GÒö7F–öâ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&7F–öâ"fÇVSÒ'&W7F÷&R#ãÆ'WGFöâ6Æ73Ò'7V66W72#î[êXX3Âö'WGFöããÂöf÷&Óâp¢VÇ6S ¢7FFRÒsÇ7â6Æ73Ò&&FvR#îZéşŠÎKŠÓÂ÷7ãâr–bFVæçBæ7F—fRVÇ6RsÇ7â6Æ73Ò&&FvR#îXÎjÚ.KŠÓÂ÷7ãâp¢7v—F6…ö7F–öâÒbsÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"÷ÆFf÷&Ò÷FVæçG2÷·FVæçBæ–GÒö7F–öâ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&7F–öâ"fÇVSÒ'6VÆV7B#ãÆ'WGFöãîŠzK®8;¾ZéşŠÃÂö'WGFöããÂöf÷&Óâr–bFVæçBæ7F—fRVÇ6R" ¢FövvÆRÒ‚w7F÷rÂ~XÎjÚ"rÂw6V6öæF'’r’–bFVæçBæ7F—fRVÇ6R‚w7F'BrÂ~XhŞ™h²rÂw7V66W72r¢7F–öç2Ò7v—F6…ö7F–öâ²bsÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"÷ÆFf÷&Ò÷FVæçG2÷·FVæçBæ–GÒö7F–öâ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&7F–öâ"fÇVSÒ'·FövvÆU³×Ò#ãÆ'WGFöâ6Æ73Ò'·FövvÆU³%×Ò#ç·FövvÆU³×ÓÂö'WGFöããÂöf÷&ÓãÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"÷ÆFf÷&Ò÷FVæçG2÷·FVæçBæ–GÒö7F–öâ"öç7V&Ö—CÒ'&WGW&â6öæf—&Ò…Â~8>8î88n88®8;>888).X˜®™šNh›8N8¾8~8î88¾ûÉş88~8;Î8+ş8ş[êXX>8~8Ş8î88%Âr’#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&7F–öâ"fÇVSÒ&FVÆWFR#ãÆ'WGFöâ6Æ73Ò&FævW"#îX˜®™šCÂö'WGFöããÂöf÷&Óâp¢&÷w2³Òb#ÇG#ãÇFCç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷FCãÇFCç·7FFWÓÂ÷FCãÇFCç¶7F–öç7ÓÂ÷FCãÂ÷G#â ¢&WGW&âÆ–÷WB‚.88n88®8;>88zêyb"ÂbsÆƒî88n88®8;>88zêycÂöƒãÆf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃîik8~8NKÉ®zKî8;¾xªÎˆˆîYÓÂöÆ&VÃãÆ–çWBæÖSÒ&æÖR"&WV—&VBÖ†ÆVæwFƒÒ#S#ãÆ'WGFöãîKÙÎh‰88(³Âö'WGFöããÂöf÷&ÓãÇF&ÆSãÇG#ãÇFƒîKÉ®zKî8;¾xªÎˆˆãÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w7ÓÂ÷F&ÆSârÂW6W"  ¤ç÷7B‚"÷ÆFf÷&Ò÷FVæçG2"¦FVbFVæçEö7&VFR†æÖS¢7G"Òf÷&Ò‚âââ’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BW6W"çÆFf÷&ÕöFÖ–ã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2¢–b6W76–öâç66Æ"‡6VÆV7B…FVæçB’çv†W&R…FVæçBææÖRÓÒæÖRç7G&—‚’’“ ¢&WGW&â…DÔÅ&W7öç6R†Æ–÷WB‚.8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#îYÎ8YŞX˜Ş8î88n88®8;>888Î8.8(®8î88#Â÷ãÆ‡&VcÒ"÷ÆFf÷&Ò÷FVæçG2#îh‹¾8(³ÂöârÂW6W"’¢6W76–öâæFB…FVæçB†æÖSÖæÖRç7G&—‚’’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"÷ÆFf÷&Ò÷FVæçG2"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"÷ÆFf÷&Ò÷FVæçG2÷·FVæçEö–GÒö7F–öâ"¦FVbFVæçEö7F–öâ‡FVæçEö–C¢–çBÂ7F–öã¢7G"Òf÷&Ò‚âââ’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BW6W"çÆFf÷&ÕöFÖ–ã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2¢FVæçBÒ6W76–öâævWB…FVæçBÂFVæçEö–B¢–bæ÷BFVæçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.88n88®8;>888ÎŠh¾8N8¾8(®8î8¾8)2"¢–b7F–öâÓÒ'6VÆV7B"æBFVæçBæ7F—fRæBæ÷BFVæçBæFVÆWFVC ¢&W7öç6RÒ&VF—&V7E&W7öç6R‚"öF6†&ö&B"Â7FGW5ö6öFSÓ32¢&W7öç6Rç6WEö6öö¶–R‚'FVæçEö–B"Â7G"‡FVæçBæ–B’Â‡GGöæÇ“ÕG'VRÂ6V7W&SÔ4ôô´”Uõ4T5U$RÂ6ÖW6—FSÒ&Æ‚"¢&WGW&â&W7öç6P¢–b7F–öâÓÒ'7F÷"æBæ÷BFVæçBæFVÆWFVC ¢FVæçBæ7F—fRÒfÇ6P¢VÆ–b7F–öâÓÒ'7F'B"æBæ÷BFVæçBæFVÆWFVC ¢FVæçBæ7F—fRÒG'VP¢VÆ–b7F–öâÓÒ&FVÆWFR# ¢FVæçBæ7F—fRÒfÇ6P¢FVæçBæFVÆWFVBÒG'VP¢VÆ–b7F–öâÓÒ'&W7F÷&R# ¢FVæçBæFVÆWFVBÒfÇ6P¢FVæçBæ7F—fRÒG'VP¢VÇ6S ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.xJX«8®i8ŞKÙÎ8~8’"¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"÷ÆFf÷&Ò÷FVæçG2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö†öÖR‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFörÂFVæçB¢æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B¢æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’¢æ÷&FW%ö'’…FVæçBææÖRÂFöræ6ÆÅöæÖR¢’æÆÂ‚¢6&G2Ò" ¢f÷"÷væW'6†—ÂFörÂFVæçB–â&V6÷&G3 ¢6W‚Ò²&ÖÆR#¢.xš"Â&fVÖÆR#¢.x™Ò'ÒævWB†Förç6W‚ÂFörç6W‚¢&VÆF–öâÒ.K‹¾8*®8;Î88®8;Â"–b÷væW'6†—ç&VÆF–öç6†—ÓÒ'&–Ö'’"VÇ6R.8NZënixò ¢fÖ–Ç•÷&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöræ–B’¢†÷FòÒbsÆ–Ör7&3Ò"öfÖ–Ç’öFöw2÷¶Föræ–GÒ÷†÷Fò"ÇCÒ'¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ò#âr–bfÖ–Ç•÷&öf–ÆRæBfÖ–Ç•÷&öf–ÆRç†÷FõöFFVÇ6RbsÇ7â6Æ73Ò&fÖ–Ç’Ö†öÖR×†÷FòÖV×G’#ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖU³£Ò—ÓÂ÷7ãâp¢6&G2³ÒbrrsÆ6Æ73Ò&fÖ–Ç’Ö†öÖRÖ6&B"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒ#à¢Ç7â6Æ73Ò&fÖ–Ç’Ö†öÖR×†÷Fò#ç·†÷F÷ÓÂ÷7ãà¢Ç7â6Æ73Ò&fÖ–Ç’Ö†öÖRÖ–æfò#ãÆƒ3ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöƒ3à¢Ç6Æ73Ò'&Vv—7FW&VBÖæÖR#ç¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ÓÂ÷à¢Çç¶‡FÖÂæW66R†Föræ'&VVB÷".xªÎzŠîiÊ®y›¾˜Ë""—ÒûÈò¶‡FÖÂæW66R‡6W‚—ÒûÈò¶‡FÖÂæW66R†Föræ6öÆ÷"÷".jù¾ˆ›.iÊ®y›¾˜Ë""—ÓÂ÷à¢Çç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷ãÇ7â6Æ73Ò&&FvR#ç·&VÆF–öçÓÂ÷7ããÇ7â6Æ73Ò&fÖ–Ç’Ö†öÖRÖÖ÷&R#î89~8:Ş89^8*>8;Î8:¾8).Šh¾8(²(i#Â÷7ããÂ÷7ãà¢Âöârrp¢–bæ÷B6&G3 ¢6&G2ÒsÆF—b6Æ73Ò'FVæçB#ãÇî8î8xªÎ8Î˜
>i®8^8(Î8n8N8î8¾8)>8#Â÷ãÇîxªÎˆˆî88y›¾˜Ë.8~8ş8:8;Î8:¾8*.888:Î8+8).8®yú^8(8¾8ş88^8N8#Â÷ãÂöF—câp¢&öG’ÒbrrsÆƒädÔ”Å’89¾8;Î8:Âöƒà¢ÇîxªÎˆˆî8¾8(8.8®8ş8¾˜
>i®8^8(Î8ş8Î8n88îZÙ8Ş888).ŠzK®8~8n8N8î88#Â÷à¢Æƒ#î8n88îZÙÂöƒ#à¢ÆF—b6Æ73Ò&fÖ–Ç’Ö†öÖRÖw&–B#ç¶6&G7ÓÂöF—cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚$dÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¦FVbfÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†—FV×3¢Æ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÒ’ÓâÆ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÓ ¢"".K¨Zé®iz^8ó~iz^X˜Ş8;¾X˜Şiz^8;¾[Ù>iz^8iÊ®ZèÎK¨n8îiÉş™™‹h^˜î8ş{i{i®ŠzK®88(¾8""" ¢&WGW&â¶—FVÒf÷"—FVÒ–â—FV×2–b—FVÕ³5ÒÂ÷"—FVÕ³5Ò–â³ÂÂwÕĞ  ¤ævWB‚"öfÖ–Ç’öæ÷F–f–6F–öç2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öæ÷F–f–6F–öç2‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢—FV×3¢Æ—7E·GWÆU¶FFWF–ÖRÂ7G%ÕÒÒµĞ¢6WGF–æw2ÒfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–ær‡W6W"Â6W76–öâ¢f÷"6öçfW'6F–öâÂÖW76vR–â†fÖ–Ç•÷Vç&VEöÖW76vUö—FV×2‡W6W"Â6W76–öâ’–b6WGF–æw2æÖW76vW2VÇ6RµÒ“ ¢÷F†W%ö–BÒ6öçfW'6F–öâçW6W#%ö–B–b6öçfW'6F–öâçW6W#ö–BÓÒW6W"æ–BVÇ6R6öçfW'6F–öâçW6W#ö–@¢&Wf–WrÒÖW76vRæ&öG•³£ƒÒ²‚.(
b"–bÆVâ†ÖW76vRæ&öG’’âƒVÇ6R""¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ#à¢Ç7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#îikyØ8:88>8+¾8;Î8+ƒÂ÷7ããÇ7â6Æ73Ò&&FvR#îiÊ®ŠªÓÂ÷7ãà¢ÇãÇ7G&öæsç¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†÷F†W%ö–BÂ6W76–öâ’—Ş8^8)>8¾8([®8Ş8î8~8óÂ÷7G&öæsãÂ÷à¢Çç¶‡FÖÂæW66R‡&Wf–Wr—ÓÂ÷ãÇ6ÖÆÃç¶ÖW76vRç6VçEöBç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRTƒ¢TÒr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚†ÖW76vRç6VçEöBÂ6&B’¢f÷"ææ÷Væ6VÖVçBÂFVæçB–â†fÖ–Ç•÷Vç&VEöææ÷Væ6VÖVçG2‡W6W"Â6W76–öâ’–b6WGF–æw2æææ÷Væ6VÖVçG2VÇ6RµÒ“ ¢WfVçBÒb"ûÈò™h¾X*ÎizR¶ææ÷Væ6VÖVçBæWfVçEöFFRç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—Ò"–bææ÷Væ6VÖVçBæWfVçEöFFRVÇ6R" ¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçBæ–GÒ#à¢Ç7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#îxªÎˆˆî8¾8(8î8®yú^8(8³Â÷7ããÇ7â6Æ73Ò&&FvR#îiÊ®ŠªÓÂ÷7ãà¢ÇãÇ7G&öæsç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBçF—FÆR—ÓÂ÷7G&öæsãÂ÷ãÇç¶‡FÖÂæW66R‡FVæçBææÖR—×¶WfVçGÓÂ÷à¢Ç6ÖÆÃç¶ææ÷Væ6VÖVçBæ7&VFVEöBç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRTƒ¢TÒr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚†ææ÷Væ6VÖVçBæ7&VFVEöBÂ6&B’¢f÷"Æ–¶RÂ—FVÒÂFör–â†fÖ–Ç•÷Vç&VEöÆ–¶Uö—FV×2‡W6W"Â6W76–öâ’–b6WGF–æw2æÆ–¶W2VÇ6RµÒ“ ¢Æ–¶W%öæÖRÒfÖ–Ç•öÖW76vUöæÖR†Æ–¶RçW6W%ö–BÂ6W76–öâ¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ#à¢Ç7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#î8+ş8*N8:8:8*N8;3Â÷7ããÇ7â6Æ73Ò&&FvR#îiÊ®ŠªÓÂ÷7ãà¢ÇãÇ7G&öæsç¶‡FÖÂæW66R†Æ–¶W%öæÖR—Ş8^8)>8Ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îXiyÉş8¾8Î8N8N8Ş8Ş8~8î8~8óÂ÷7G&öæsãÂ÷à¢Ç6ÖÆÃç¶Æ–¶Ræ7&VFVEöBç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRTƒ¢TÒr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚†Æ–¶Ræ7&VFVEöBÂ6&B’¢f÷"6öÖÖVçBÂ—FVÒÂFör–â†fÖ–Ç•÷Vç&VEö6öÖÖVçEö—FV×2‡W6W"Â6W76–öâ’–b6WGF–æw2æÆ–¶W2VÇ6RµÒ“ ¢6öÖÖVçFW%öæÖRÒfÖ–Ç•öÖW76vUöæÖR†6öÖÖVçBçW6W%ö–BÂ6W76–öâ¢&Wf–WrÒ6öÖÖVçBæ&öG•³£ƒÒ²‚.(
b"–bÆVâ†6öÖÖVçBæ&öG’’âƒVÇ6R""¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ#à¢Ç7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#î8+ş8*N8:8:8*N8;3Â÷7ããÇ7â6Æ73Ò&&FvR#îiÊ®ŠªÓÂ÷7ãà¢ÇãÇ7G&öæsç¶‡FÖÂæW66R†6öÖÖVçFW%öæÖR—Ş8^8)>8Ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îXiyÉş8¾8+>8:8;>888~8î8~8óÂ÷7G&öæsãÂ÷à¢Çç¶‡FÖÂæW66R‡&Wf–Wr—ÓÂ÷ãÇ6ÖÆÃç¶6öÖÖVçBæ7&VFVEöBç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRTƒ¢TÒr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚†6öÖÖVçBæ7&VFVEöBÂ6&B’¢f÷"FörÂWfVçE÷G—RÂWfVçEöFFRÂF—2–â†fÖ–Ç•öææ—fW'6'•öæ÷F–f–6F–öåö—FV×2‡W6W"Â6W76–öâ’–b6WGF–æw2æææ—fW'6&–W2VÇ6RµÒ“ ¢Æ&VÂÒ.Š©^yIşizR"–bWfVçE÷G—RÓÒ&&—'F†F’"VÇ6R.8®‹øî8Š‰[û^izR ¢F–Ö–ærÒ.K¸®iz^8~8’"–bF—2ÓÒVÇ6R‚.iˆîiz^8~8’"–bF—2ÓÒVÇ6R#~iz^[èÎ8~8’"¢6WVFõ÷F–ÖRÒFFWF–ÖRæ6öÖ&–æR†WfVçEöFFRÂFFWF–ÖRæÖ–âçF–ÖR‚’ÂG¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’öææ—fW'6&–W2öæ÷F–6R÷¶Föræ–GÒ÷¶WfVçE÷G—WÒ÷¶WfVçEöFFRæ—6öf÷&ÖB‚—Ò#à¢Ç7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#îZJ~Xˆ~8®Š‰[û^izSÂ÷7ããÇ7â6Æ73Ò&&FvR#ç¶F—7Şiz^X˜ÓÂ÷7ãà¢ÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8ç¶Æ&VÇŞ8Ç·F–Ö–æwÓÂ÷7G&öæsãÂ÷ãÇ6ÖÆÃç¶WfVçEöFFRç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚‡6WVFõ÷F–ÖRÂ6&B’¢f÷"FörÂF—FÆRÂGVUööâÂF—2–â†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•÷f66–æUöGVUö—FV×2‡W6W"Â6W76–öâ’’–b6WGF–æw2æ†VÇF…÷f66–æF–öç2VÇ6RµÒ“ ¢F–Ö–ærÒb.8.8‡¶F—7ŞizR"–bF—2ãÒVÇ6Rb'¶'2†F—2—Şiz^‹h^˜â ¢6WVFõ÷F–ÖRÒFFWF–ÖRæ6öÖ&–æR†GVUööâÂFFWF–ÖRæÖ–âçF–ÖR‚’ÂG¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷f66–æF–öâ#ãÇ7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#î8:ş8*ş888;>K¨Zé£Â÷7ããÇ7â6Æ73Ò&&FvR#ç·F–Ö–æwÓÂ÷7ããÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8ç¶‡FÖÂæW66R‡F—FÆR—ŞK¨Zé®8).z+®Š¨Ş8~8n8ş88^8CÂ÷7G&öæsãÂ÷ãÇ6ÖÆÃç¶GVUööâç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚‡6WVFõ÷F–ÖRÂ6&B’¢f÷"FörÂF—FÆRÂGVUööâÂF—2–â†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•ö6†V6·WöGVUö—FV×2‡W6W"Â6W76–öâ’’–b6WGF–æw2æ†VÇF…ö6†V6·W2VÇ6RµÒ“ ¢F–Ö–ærÒb.8.8‡¶F—7ŞizR"–bF—2ãÒVÇ6Rb'¶'2†F—2—Şiz^‹h^˜â ¢6WVFõ÷F–ÖRÒFFWF–ÖRæ6öÖ&–æR†GVUööâÂFFWF–ÖRæÖ–âçF–ÖR‚’ÂG¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚ö6†V6·W#ãÇ7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#îX^Š‹®K¨Zé£Â÷7ããÇ7â6Æ73Ò&&FvR#ç·F–Ö–æwÓÂ÷7ããÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8ç¶‡FÖÂæW66R‡F—FÆR—ŞK¨Zé®8).z+®Š¨Ş8~8n8ş88^8CÂ÷7G&öæsãÂ÷ãÇ6ÖÆÃç¶GVUööâç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚‡6WVFõ÷F–ÖRÂ6&B’¢f÷"FörÂF—FÆRÂGVUööâÂF—2–â†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•öÖVF–6F–öåöGVUö—FV×2‡W6W"Â6W76–öâ’’–b6WGF–æw2æ†VÇF…öÖVF–6F–öç2VÇ6RµÒ“ ¢F–Ö–ærÒb.8.8‡¶F—7ŞizR"–bF—2ãÒVÇ6Rb'¶'2†F—2—Şiz^‹h^˜â ¢6WVFõ÷F–ÖRÒFFWF–ÖRæ6öÖ&–æR†GVUööâÂFFWF–ÖRæÖ–âçF–ÖR‚’ÂG¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚öÖVF–6F–öâ#ãÇ7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#îh©^‰jÎK¨Zé£Â÷7ããÇ7â6Æ73Ò&&FvR#ç·F–Ö–æwÓÂ÷7ããÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8ç¶‡FÖÂæW66R‡F—FÆR—Şh©^‰jÎK¨Zé®8).z+®Š¨Ş8~8n8ş88^8CÂ÷7G&öæsãÂ÷ãÇ6ÖÆÃç¶GVUööâç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚‡6WVFõ÷F–ÖRÂ6&B’¢f÷"FörÂF—FÆRÂGVUööâÂF—2–â†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•öF—6V6UöGVUö—FV×2‡W6W"Â6W76–öâ’’–b6WGF–æw2æ†VÇF…öföÆÆ÷wW2VÇ6RµÒ“ ¢F–Ö–ærÒb.8.8‡¶F—7ŞizR"–bF—2ãÒVÇ6Rb'¶'2†F—2—Şiz^‹h^˜â ¢6WVFõ÷F–ÖRÒFFWF–ÖRæ6öÖ&–æR†GVUööâÂFFWF–ÖRæÖ–âçF–ÖR‚’ÂG¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’¢6&BÒbrrsÆ6Æ73Ò&æ÷F–f–6F–öâÖ—FVÒVç&VB"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚öF—6V6R#ãÇ7â6Æ73Ò&æ÷F–f–6F–öâÖ¶–æB#îXhŞŠ‹®K¨Zé£Â÷7ããÇ7â6Æ73Ò&&FvR#ç·F–Ö–æwÓÂ÷7ããÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8ç¶‡FÖÂæW66R‡F—FÆR—ŞXhŞŠ‹®8;¾z+®Š¨ŞK¨Zé®8~8“Â÷7G&öæsãÂ÷ãÇ6ÖÆÃç¶GVUööâç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ÓÂ÷6ÖÆÃãÂöârrp¢—FV×2æVæB‚‡6WVFõ÷F–ÖRÂ6&B’¢6&G2Ò""æ¦ö–â†6&Bf÷"òÂ6&B–â6÷'FVB†—FV×2Â¶W“ÖÆÖ&F—FVÓ¢—FVÕ³ÒÂ&WfW'6SÕG'VR’¢–bæ÷B6&G3 ¢6&G2ÒsÆF—b6Æ73Ò'FVæçB#ãÇîik8~8N˜	®yú^8ş8.8(®8î8¾8)>8#Â÷ãÇãÇ6ÖÆÃîikyØ8:88>8+¾8;Î8+8xªÎˆˆî8¾8(8î8®yú^8(8¾8XiyÉş88î8Î8N8N8Ş8Ş8).8>8>8~8î88(8nz+®Š¨Ş8~8Ş8î88#Â÷6ÖÆÃãÂ÷ãÂöF—câp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒî˜	®yúSÂöƒà¢ÇîiÊ®ŠªŞ8î8:88>8+¾8;Î8+8xªÎˆˆî8¾8(8î8®yú^8(8¾8h‰™[~XiyÉş88î8Î8N8N8Ş8Ş8).8î88(8nŠzK®8~8n8N8î88#Â÷ç¶6&G7Ğ¢ÇãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ—fW'6&–W2#îŠ©^yIşiz^8;¾8®‹øî8Š‰[û^iz^8).z+®Š¨ÓÂöâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2#î˜	®yú^ŠŠŞZé£ÂöãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.˜	®yú^ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¦FVbfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–ær‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâfÖ–Ç”æ÷F–f–6F–öå6WGF–æs ¢6WGF–ærÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”æ÷F–f–6F–öå6WGF–ær’çv†W&R„fÖ–Ç”æ÷F–f–6F–öå6WGF–ærçW6W%ö–BÓÒW6W"æ–B’¢–bæ÷B6WGF–æs ¢6WGF–ærÒfÖ–Ç”æ÷F–f–6F–öå6WGF–ær‡W6W%ö–C×W6W"æ–B¢6W76–öâæFB‡6WGF–ær¢6W76–öâæfÇW6‚‚¢&WGW&â6WGF–æp  ¤ævWB‚"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–æw5÷vR‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢6WGF–ærÒfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–ær‡W6W"Â6W76–öâ¢6†V6¶VBÒÆÖ&FfÇVS¢&6†V6¶VB"–bfÇVRVÇ6R" ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öæ÷F–f–6F–öç2#î˜	®yú^8h‹¾8(³ÂöãÆƒî˜	®yú^ŠŠŞZé£ÂöƒãÆf÷&ÒÖWF†öCÒ'÷7B#à¢ÆF—b6Æ73Ò'FVæçB#ãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&VÖ–ÅöVæ&ÆVB"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræVÖ–ÅöVæ&ÆVB—Óây›¾˜Ë.8:8;Î8:¾8*.888:Î8+8~8(.˜	®yú^8).Xù~8Xùn8(³ÂöÆ&VÃà¢ÇãÇ6ÖÆÃî8:8;Î8:¾˜XŞKú8+^8;Î89>8+8îŠŠŞZé®[èÎ8¾˜Kú8^8(Î8î88.yK¾™Ú.Xh^˜	®yú^8ş8>8îŠŠŞZé®8¾8¾8¾8(ş8(8®XŠyJ8~8Ş8î88#Â÷6ÖÆÃãÂ÷ãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'W6…öVæ&ÆVB"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–ærçW6…öVæ&ÆVB—Óâ8>8îzºşiÊ¾889~88>8+~8:^˜	®yú^8).˜8(³ÂöÆ&VÃà¢ÇãÆ'WGFöâG—SÒ&'WGFöâ"–CÒ'W6‚×&Vv—7FW""6Æ73Ò'6V6öæF'’#î89n8:8*n8+n˜	®yú^8).Š‹Xúş88(³Âö'WGFöãâÇ7â–CÒ'W6‚×7FFR#ãÂ÷7ããÂ÷ãÇãÇ6ÖÆÃæ•†öæ^8~8ş89¾8;Î8:yK¾™Ú.8‹ûŞXª8~8ôdÔ”Å8¾8(ŠŠŞZé®8~8n8ş88^8N8#Â÷6ÖÆÃãÂ÷ãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&Æ–æUöVæ&ÆVB"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræÆ–æUöVæ&ÆVB—Óâ˜
>i®8~8şxªÎˆˆî8äÄ”ä^XZÎ[Èş8*.8*¾8*n8;>888~˜	®yú^8).Xù~8Xùn8(³ÂöÆ&VÃà¢ÇãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öÆ–æR#äÄ”ä^XZÎ[Èş8*.8*¾8*n8;>888).˜
>i£ÂöãÂ÷ãÇãÇ6ÖÆÃîxªÎˆˆî8N88¾iÊÎK«®˜
>i®8ÎZèÎK¨n8~8n8N8(¾ZNY88˜XŞKú8^8(Î8î88#Â÷6ÖÆÃãÂ÷ãÂöF—cà¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&ÖW76vW2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræÖW76vW2—ÓâikyØ8:88>8+¾8;Î8+ƒÂöÆ&VÃà¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&ææ÷Væ6VÖVçG2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræææ÷Væ6VÖVçG2—ÓâxªÎˆˆî8¾8(8î8®yú^8(8³ÂöÆ&VÃà¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&Æ–¶W2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræÆ–¶W2—Óâh‰™[~XiyÉş88î8N8N8ÓÂöÆ&VÃà¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&ææ—fW'6&–W2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræææ—fW'6&–W2—ÓâŠ©^yIşiz^8;¾8®‹øî8Š‰[û^iz^ûÈƒ~iz^X˜Ş8;¾X˜Şiz^8;¾[Ù>iz^ûÈ“ÂöÆ&VÃà¢Æƒ#îX^[«~K¨Zé®8î˜	®yúSÂöƒ#ãÇîYNK¨Zé®8ã~iz^X˜Ş8;¾X˜Şiz^8;¾[Ù>iz^88ZéşikŞkˆ8ş8¾8~8n8N8®8NiÉş™™‹h^˜î8).˜	®yú^8~8î88#Â÷à¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&†VÇF…÷f66–æF–öç2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræ†VÇF…÷f66–æF–öç2—Óâ8:ş8*ş888;>K¨Zé£ÂöÆ&VÃà¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&†VÇF…ö6†V6·W2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræ†VÇF…ö6†V6·W2—ÓâX^Š‹®K¨Zé£ÂöÆ&VÃà¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&†VÇF…öÖVF–6F–öç2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræ†VÇF…öÖVF–6F–öç2—Óâh©^‰jÎK¨Zé£ÂöÆ&VÃà¢ÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&†VÇF…öföÆÆ÷wW2"fÇVSÒ'G'VR"¶6†V6¶VB‡6WGF–æræ†VÇF…öföÆÆ÷wW2—ÓâXhŞŠ‹®8;¾{XÎ˜îz+®Š¨ŞK¨Zé£ÂöÆ&VÃà¢Æ'WGFöãî˜	®yú^ŠŠŞZé®8).KùŞZÙƒÂö'WGFöããÂöf÷&ÓãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷W6‚×FW7B#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#î8>8îzºşiÊ¾888n8+88˜	®yú^8).˜8(³Âö'WGFöããÂöf÷&ÓãÇãÇ6ÖÆÃî8*®89^8¾8~8n8(.88~8;Î8+ş8şX˜®™šN8^8(Î8®8YNyK¾™Ú.8¾8(z+®Š¨Ş8~8Ş8î88#Â÷6ÖÆÃãÂ÷à¢Ç67&—Cæ6öç7Bf–C×¶§6öâæGV×2…d”EõT$Ä”5ô´U’—Ó¶gVæ7F–öâ#cB‡2—·¶6öç7BÒsÒrç&WVB‚ƒB×2æÆVæwF‚SB’SB’ÇcÒ‡2·’ç&WÆ6R‚òÒörÂr²r’ç&WÆ6R‚õòörÂròr’Ç#ÖFö"‡b“·&WGW&âV–çC„'&’æg&öÒ…²ââç%ÒæÖ†3Óæ2æ6†$6öFTBƒ’’—×Ğ¢Fö7VÖVçBævWDVÆVÖVçD'”–B‚wW6‚×&Vv—7FW"r’æöæ6Æ–6³Ö7–æ2‚“Óç·¶6öç7B7FFSÖFö7VÖVçBævWDVÆVÖVçD'”–B‚wW6‚×7FFRr“·G'—·¶–b‚f–B—F‡&÷ræWrW'&÷"‚~˜	®yú^8+^8;Î898;Î8îŠŠŞZé®k©nX)KŠŞ8~8’r“¶6öç7B&VsÖv—Bæf–vF÷"ç6W'f–6Uv÷&¶W"ç&Vv—7FW"‚röfÖ–Ç’×W6‚×v÷&¶W"æ§2r“¶6öç7BW&Ö—76–öãÖv—Bæ÷F–f–6F–öâç&WVW7EW&Ö—76–öâ‚“¶–b‡W&Ö—76–öâÓÒvw&çFVBr—F‡&÷ræWrW'&÷"‚~89n8:8*n8+n8~˜	®yú^8ÎŠ‹Xúş8^8(Î8î8¾8)>8~8~8òr“¶6öç7B7V#Öv—B&VrçW6„ÖævW"ç7V'67&–&R‡··W6W%f—6–&ÆTöæÇ“§G'VRÆÆ–6F–öå6W'fW$¶W“¦#cB‡f–B—×Ò“¶6öç7B&W3Öv—BfWF6‚‚röfÖ–Ç’÷W6‚×7V'67&—F–öç2rÇ·¶ÖWF†öC¢uõ5BrÆ†VFW'3§·²t6öçFVçBÕG—Rs¢vÆ–6F–öâö§6öâw×ÒÆ&öG“¤¥4ôâç7G&–æv–g’‡7V"—×Ò“¶–b‚&W2æö²—F‡&÷ræWrW'&÷"‚~zºşiÊ¾y›¾˜Ë.8¾ZKiY~8~8î8~8òr“·7FFRçFW‡D6öçFVçCÒ~˜	®yú^zºşiÊ¾8).y›¾˜Ë.8~8î8~8òs·×Ö6F6‚†R—··7FFRçFW‡D6öçFVçCÖRæÖW76vW×××Ó³Â÷67&—Cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.˜	®yú^ŠŠŞZé®ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2"¦FVbfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–æw5÷6fR†ÖW76vW3¢&ööÂÒf÷&Ò„fÇ6R’Âææ÷Væ6VÖVçG3¢&ööÂÒf÷&Ò„fÇ6R’ÂÆ–¶W3¢&ööÂÒf÷&Ò„fÇ6R’Âææ—fW'6&–W3¢&ööÂÒf÷&Ò„fÇ6R’Â†VÇF…÷f66–æF–öç3¢&ööÂÒf÷&Ò„fÇ6R’Â†VÇF…ö6†V6·W3¢&ööÂÒf÷&Ò„fÇ6R’Â†VÇF…öÖVF–6F–öç3¢&ööÂÒf÷&Ò„fÇ6R’Â†VÇF…öföÆÆ÷wW3¢&ööÂÒf÷&Ò„fÇ6R’ÂÆ–æUöVæ&ÆVC¢&ööÂÒf÷&Ò„fÇ6R’ÂVÖ–ÅöVæ&ÆVC¢&ööÂÒf÷&Ò„fÇ6R’ÂW6…öVæ&ÆVC¢&ööÂÒf÷&Ò„fÇ6R’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢6WGF–ærÒfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–ær‡W6W"Â6W76–öâ¢6WGF–æræÖW76vW2Â6WGF–æræææ÷Væ6VÖVçG2Â6WGF–æræÆ–¶W2Â6WGF–æræææ—fW'6&–W2ÒÖW76vW2Âææ÷Væ6VÖVçG2ÂÆ–¶W2Âææ—fW'6&–W0¢6WGF–æræ†VÇF…÷f66–æF–öç2Â6WGF–æræ†VÇF…ö6†V6·W2Ò†VÇF…÷f66–æF–öç2Â†VÇF…ö6†V6·W0¢6WGF–æræ†VÇF…öÖVF–6F–öç2Â6WGF–æræ†VÇF…öföÆÆ÷wW2Ò†VÇF…öÖVF–6F–öç2Â†VÇF…öföÆÆ÷wW0¢6WGF–æræÆ–æUöVæ&ÆVBÒÆ–æUöVæ&ÆV@¢6WGF–æræVÖ–ÅöVæ&ÆVBÒVÖ–ÅöVæ&ÆV@¢6WGF–ærçW6…öVæ&ÆVBÒW6…öVæ&ÆV@¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öÆ–æR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÆ–æU÷6WGF–æw2‡FW7C¢7G"Ò""ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&G2Ò6W76–öâæW†V7WFR‡6VÆV7B…FVæçBÂÆ–æTöff–6–Ä66÷VçB’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–B¢æ÷WFW&¦ö–â„Æ–æTöff–6–Ä66÷VçBÂÆ–æTöff–6–Ä66÷VçBçFVæçEö–BÓÒFVæçBæ–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢æF—7F–æ7B‚’æ÷&FW%ö'’…FVæçBææÖR’’æÆÂ‚¢6&G2Ò" ¢6WGF–ærÒfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–ær‡W6W"Â6W76–öâ¢f÷"FVæçBÂ66÷VçB–â&V6÷&G3 ¢Æ–æ²Ò6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Æ–æTÆ–æ²’çv†W&R„fÖ–Ç”Æ–æTÆ–æ²çFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç”Æ–æTÆ–æ²çW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç”Æ–æTÆ–æ²æ7F—fRæ—5ò…G'VR’’¢–bæ÷B66÷VçB÷"æ÷B66÷VçBæ7F—fS ¢7FFRÒsÇ7â6Æ73Ò&&FvR#îxªÎˆˆîXN8îk©nX)KŠÓÂ÷7ããÇãÇ6ÖÆÃäÄ”ä^XZÎ[Èş8*.8*¾8*n8;>888îhê^{i®[èÎ8¾XŠyJ8~8Ş8î88#Â÷6ÖÆÃãÂ÷âp¢VÆ–bÆ–æ³ ¢FVÆ—fW'•÷7FFRÒsÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6F6V&F3¶6öÆ÷#¢33cVC6"#î˜	®yúTôãÂ÷7ãâr–b6WGF–æræÆ–æUöVæ&ÆVBVÇ6RsÇ7â6Æ73Ò&&FvR#î˜	®yúTôdcÂ÷7ãâp¢FW7Eö'WGFöâÒbsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÆ–æR÷·FVæçBæ–GÒ÷FW7B#ãÆ'WGFöãäÄ”ä^88n8+88˜	®yú^8).Xù~8Xùn8(³Âö'WGFöããÂöf÷&Óâr–b6WGF–æræÆ–æUöVæ&ÆVBVÇ6RsÇãÆ6Æ73Ò&'WGFöâ"‡&VcÒ"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2#î˜	®yú^ŠŠŞZé®8tÄ”ä^8)$ôî8¾88(³ÂöãÂ÷âp¢7FFRÒbrrsÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6F6V&F3¶6öÆ÷#¢33cVC6"#î˜
>i®kˆ8óÂ÷7ãâ¶FVÆ—fW'•÷7FFWÓÇç¶‡FÖÂæW66R†66÷VçBæ66÷VçEöæÖR—Ş8¾8(˜	®yú^8).Xù~8Xùn8(Î8î88#Â÷ç·FW7Eö'WGFöçÓÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÆ–æR÷·FVæçBæ–GÒ÷VæÆ–æ²#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWBG—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&Õ÷VæÆ–æ²"fÇVSÒ'G'VR"7G–ÆSÒ'v–GFƒ¦WFò"&WV—&VCâ˜
>i®Šz>™šN8).z+®Š¨ÓÂöÆ&VÃãÆ'WGFöâ6Æ73Ò'6V6öæF'’#äÄ”ä^˜
>i®8).Šz>™šCÂö'WGFöããÂöf÷&Óârrp¢VÇ6S ¢7FFRÒbrrsÇ7â6Æ73Ò&&FvR#îiÊ®˜
>i£Â÷7ããÇç¶‡FÖÂæW66R†66÷VçBæ66÷VçEöæÖR—Ş8).Xø¾88‹ûŞXª8~8ş[èÎ8˜
>i®8+>8;Î888).XZÎ[ÈôÄ”ä^8˜Kú8~8î88#Â÷ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÆ–æR÷·FVæçBæ–GÒ÷Fö¶Vâ#ãÆ'WGFöãã^XˆniÈX«8î˜
>i®8+>8;Î888).y›®ŠÃÂö'WGFöããÂöf÷&Óârrp¢6&G2³ÒbsÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ"7G–ÆSÒ&Ö&v–â×F÷£#ç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂöƒ#ç·7FFWÓÂ÷6V7F–öãâp¢æ÷F–6RÒsÆF—b6Æ73Ò'7V66W72#äÄ”ä^88n8+88˜	®yú^8).˜Kú8~8î8~8ş8#ÂöF—câr–bFW7BÓÒ'6VçB"VÇ6R‚sÆF—b6Æ73Ò&W'&÷"#äÄ”ä^88n8+88˜	®yú^8).˜Kú8~8Ş8î8¾8)>8~8~8ş8.zêynˆ^8˜
>{Z8~8n8ş88^8N8#ÂöF—câr–bFW7BÓÒ&f–ÆVB"VÇ6Rrr¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2#î˜	®yú^ŠŠŞZé®8h‹¾8(³ÂöãÆƒäÄ”ä^XZÎ[Èş8*.8*¾8*n8;>88˜
>i£Âöƒç¶æ÷F–6WĞ¢ÇîxªÎˆˆî8N88äÄ”ä^XZÎ[Èş8*.8*¾8*n8;>888„dÔ”ÅKÉ®Y:8).ZèXZ8¾{IK¹88î88.X¾K«¤Ä”ä^8ä”N8(N™»¾Š›yZ®Xû~8).XZ^X©¾88(¾[ø^Šh8ş8.8(®8î8¾8)>8#Â÷ç¶6&G2÷"sÆF—b6Æ73Ò'FVæçB#î˜
>i®Zûî‹8îxªÎˆˆî8Î8.8(®8î8¾8)>8#ÂöF—câwÒrrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚$Ä”ä^XZÎ[Èş8*.8*¾8*n8;>88˜
>i®ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öÆ–æR÷·FVæçEö–GÒ÷FW7B"¦FVbfÖ–Ç•öÆ–æU÷FW7B‡FVæçEö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢ÆÆ÷vVBÒ6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçEö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’¢–bæ÷BÆÆ÷vVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢7F×ÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’ç7G&gF–ÖR‚"U’VÒVBT‚TÒU2Vb"¢6VçBÒ6VæEöÆ–æU÷W6‚‡W6W"æ–BÂFVæçEö–BÂ'FW7B"Â$Ä”ä^˜	®yú^8îhê^{i®88n8+888¾h‰X©ş8~8î8~8ş8.K¸®[èÎ8ŠŠŞZé®8~8şX^[«~K¨Zé®8(NŠ‰[û^iz^8).8®yú^8(8¾8~8î88""À¢"öfÖ–Ç’öæ÷F–f–6F–öç2"Âb&Æ–æS§FW7C§·W6W"æ–GÓ§·FVæçEö–GÓ§·7F×Ò"Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öÆ–æS÷FW7C×²w6VçBr–b6VçBVÇ6Rvf–ÆVBwÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öÆ–æR÷·FVæçEö–GÒ÷Fö¶Vâ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÆ–æU÷Fö¶Våö7&VFR‡FVæçEö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢ÆÆ÷vVBÒ6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçEö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’¢66÷VçBÒ6W76–öâç66Æ"‡6VÆV7B„Æ–æTöff–6–Ä66÷VçB’çv†W&R„Æ–æTöff–6–Ä66÷VçBçFVæçEö–BÓÒFVæçEö–BÂÆ–æTöff–6–Ä66÷VçBæ7F—fRæ—5ò…G'VR’’¢–bæ÷BÆÆ÷vVB÷"æ÷B66÷VçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.˜
>i®8~8Ş8(´Ä”ä^XZÎ[Èş8*.8*¾8*n8;>888ÎŠh¾8N8¾8(®8î8¾8)2"¢æ÷rÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢öÆE÷Fö¶Vç2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”Æ–æTÆ–æµFö¶Vâ’çv†W&R„fÖ–Ç”Æ–æTÆ–æµFö¶VâçW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç”Æ–æTÆ–æµFö¶VâçFVæçEö–BÓÒFVæçEö–BÂfÖ–Ç”Æ–æTÆ–æµFö¶VâçW6VEöBæ—5ò„æöæR’’’æÆÂ‚¢f÷"öÆB–âöÆE÷Fö¶Vç3 ¢öÆBçW6VEöBÒæ÷p¢&u÷Fö¶VâÒ6V7&WG2çFö¶Vå÷W&Ç6fRƒ"¢6W76–öâæFB„fÖ–Ç”Æ–æTÆ–æµFö¶Vâ‡FVæçEö–C×FVæçEö–BÂW6W%ö–C×W6W"æ–BÂFö¶Våö†6ƒ×Fö¶Våö†6‚‡&u÷Fö¶Vâ’ÂW‡—&W5öCÖæ÷r²F–ÖVFVÇF†Ö–çWFW3ÓR’’¢6W76–öâæ6öÖÖ—B‚¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öÆ–æR#äÄ”ä^˜
>i®8h‹¾8(³ÂöãÆƒäÄ”ä^˜
>i®8+>8;Î88“ÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇîjÊ8îih~ZÙ~8)#Ç7G&öæsç¶‡FÖÂæW66R†66÷VçBæ66÷VçEöæÖR—ÓÂ÷7G&öæsî8˜Kú8~8n8ş88^8N8#Â÷ãÇ7G–ÆSÒ&föçB×6—¦S£ãW&VÓ¶ÆWGFW"×76–æs¢ã†VÒ#ãÇ7G&öæsî˜
>i¢¶‡FÖÂæW66R‡&u÷Fö¶Vâ—ÓÂ÷7G&öæsãÂ÷ãÇãÇ6ÖÆÃîiÈX«i˜.™i>8ó^Xˆn8~88.8>8î8+>8;Î888).K¹nK«®8yú^8(8¾8®8N8~8ş88^8N8.KÛşyJ[èÎ8şˆz®X¹^y¨N8¾xJX«8¾8®8(®8î88#Â÷6ÖÆÃãÂ÷ãÂöF—cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚$Ä”ä^˜
>i®8+>8;Î88ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öÆ–æR÷·FVæçEö–GÒ÷VæÆ–æ²"¦FVbfÖ–Ç•öÆ–æU÷VæÆ–æ²‡FVæçEö–C¢–çBÂ6öæf—&Õ÷VæÆ–æ³¢&ööÂÒf÷&Ò„fÇ6R’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷B6öæf—&Õ÷VæÆ–æ²÷"æ÷B6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçEö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ$Ä”ä^˜
>i®Šz>™šN8).z+®Š¨Ş8~8n8ş88^8B"¢Æ–æ²Ò6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Æ–æTÆ–æ²’çv†W&R„fÖ–Ç”Æ–æTÆ–æ²çFVæçEö–BÓÒFVæçEö–BÂfÖ–Ç”Æ–æTÆ–æ²çW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç”Æ–æTÆ–æ²æ7F—fRæ—5ò…G'VR’’¢–bÆ–æ³ ¢Æ–æ²æ7F—fRÂÆ–æ²çVæÆ–æ¶VEöBÒfÇ6RÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öÆ–æR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öÆ–æRöÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbÆ–æUööff–6–Åö66÷VçEöÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢66÷VçBÒ6W76–öâç66Æ"‡6VÆV7B„Æ–æTöff–6–Ä66÷VçB’çv†W&R„Æ–æTöff–6–Ä66÷VçBçFVæçEö–BÓÒFVæçBæ–B’¢&6U÷W&ÂÒ÷2æVçf—&öâævWB‚$ô$4UõU$Â"Â&‡GG3¢òöFörÖÖævVÖVçBæ&VæVf—BÖæf’æ6öÒ"’ç'7G&—‚"ò"¢vV&†ööµ÷W&ÂÒb'¶&6U÷W&ÇÒöÆ–æR÷vV&†öö²÷¶66÷VçBçvV&†ööµö¶W—Ò"–b66÷VçBVÇ6R.KùŞZÙ[èÎ8¾y›®ŠÎ8^8(Î8î8’ ¢Æ–æ¶VEö6÷VçBÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç”Æ–æTÆ–æ²æ–B’’çv†W&R„fÖ–Ç”Æ–æTÆ–æ²çFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç”Æ–æTÆ–æ²æ7F—fRæ—5ò…G'VR’’’÷" ¢FVÆ—fW&–W2Ò6W76–öâç66Æ'2‡6VÆV7B„Æ–æTFVÆ—fW'’’çv†W&R„Æ–æTFVÆ—fW'’çFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„Æ–æTFVÆ—fW'’æ7&VFVEöBæFW62‚’’æÆ–Ö—BƒS’’æÆÂ‚¢÷væW'2Ò¶—FVÒæ–C¢—FVÒææÖRf÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B…W6W"’çv†W&R…W6W"æ–Bæ–åò‡¶—FVÒçW6W%ö–Bf÷"—FVÒ–âFVÆ—fW&–W7Ò’’’æÆÂ‚—Ò–bFVÆ—fW&–W2VÇ6R·Ğ¢FVÆ—fW'•÷&÷w2Ò""æ¦ö–â†brrsÇG#ãÇFCç¶—FVÒæ7&VFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†÷væW'2ævWB†—FVÒçW6W%ö–BÂ"Ò"’÷""Ò"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒæ6FVv÷'’—ÓÂ÷FCãÇFCç².h‰X©ò"–b—FVÒç7FGW2ÓÒ'6VçB"VÇ6R.ZKiYr'ÓÂ÷FCãÇFCç¶—FVÒæGFV×G2÷"ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒæW'&÷"÷""Ò"—ÓÂ÷FCãÇFCç¶bsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÆ–æRöÖævRöFVÆ—fW&–W2÷¶—FVÒæ–GÒ÷&WG'’#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#îXhŞ˜Âö'WGFöããÂöf÷&Óâr–b—FVÒç7FGW2Ò'6VçB"æB—FVÒæÖW76vRæB—FVÒçF&vWE÷W&ÂVÇ6R~ûÈÒwÓÂ÷FCãÂ÷G#ârrrf÷"—FVÒ–âFVÆ—fW&–W2¢7FGW5÷FW‡BÒ.hê^{i®z+®Š¨Şkˆ8ò"–b66÷VçBæB66÷VçBæ7F—fRæB66÷VçBçfW&–f–VEöBVÇ6R‚.ŠŠŞZé®kˆ8ş8;¾iÊ®z+®Š¨Ò"–b66÷VçBæB66÷VçBæ7F—fRVÇ6R.iÊ®hê^{i¢"¢g&–VæE÷W&ÂÒb&‡GG3¢òöÆ–æRæÖRõ"÷F’÷÷·V÷FR†66÷VçBæ&÷Eö&6–5ö–B—Ò"–b66÷VçBæB66÷VçBæ&÷Eö&6–5ö–BVÇ6R" ¢fW&–f–VE÷FW‡BÒ66÷VçBçfW&–f–VEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–b66÷VçBæB66÷VçBçfW&–f–VEöBVÇ6R.iÊ®z+®Š¨Ò ¢vV&†ööµ÷FW‡BÒ66÷VçBæÆ7E÷vV&†ööµöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–b66÷VçBæB66÷VçBæÆ7E÷vV&†ööµöBVÇ6R.iÊ®Xù~Kú ¢¶W•÷7FFRÒ.ŠŠŞZé®kˆ8ò"–bÆ–æUö6—†W"‚’VÇ6R.iÊ®ŠŠŞZé®ûÈiÊÎyZ®y+Z(>8„Ä”äUô5$TDTåD”Å5ô´U8Î[ø^Šh8~8ûÈ’ ¢&öG’ÒbrrsÆƒäÄ”ä^XZÎ[Èş8*.8*¾8*n8;>88ŠŠŞZé£ÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇîx«nhX¾ûÉ£Ç7â6Æ73Ò&&FvR#ç·7FGW5÷FW‡GÓÂ÷7ãî8˜
>i®KŠŞ8î8®Zê.jyûÉ£Ç7G&öæsç¶Æ–æ¶VEö6÷VçGŞYÓÂ÷7G&öæsãÂ÷à¢ÇîXZÎ[Èş8*.8*¾8*n8;>88ûÉ£Ç7G&öæsç¶‡FÖÂæW66R‚†66÷VçBæ&÷EöF—7Æ•öæÖR÷"66÷VçBæ66÷VçEöæÖR’–b66÷VçBVÇ6RFVæçBææÖR—ÓÂ÷7G&öæsç¶b~ûÈ‡¶‡FÖÂæW66R†66÷VçBæ&÷Eö&6–5ö–B—ŞûÈ’r–b66÷VçBæB66÷VçBæ&÷Eö&6–5ö–BVÇ6RrwÓÂ÷à¢Çähê^{i®z+®Š¨ŞûÉ§·fW&–f–VE÷FW‡GÓÆ'#åvV&†öö¾iÈ{X.Xù~KúûÉ§·vV&†ööµ÷FW‡GÓÆ'#îi©~Xû~˜Û^ûÉ§¶‡FÖÂæW66R†¶W•÷7FFR—ÓÂ÷à¢¶bsÇ6Æ73Ò&W'&÷"#îy»N‹ù8*8:8;ÎûÉ§¶‡FÖÂæW66R†66÷VçBæÆ7EöW'&÷"—ÓÂ÷âr–b66÷VçBæB66÷VçBæÆ7EöW'&÷"VÇ6RrwĞ¢ÇåvV&†öö²U$ÃÆ'#ãÆ6öFSç¶‡FÖÂæW66R‡vV&†ööµ÷W&Â—ÓÂö6öFSãÂ÷ãÇãÇ6ÖÆÃäÄ”äRöff–6–Â66÷VçBÖævW.ûÈôFWfVÆ÷W'26öç6öÆ^8åvV&†öö²U$Î8ŠŠŞZé®8~8n8ş88^8N8#Â÷6ÖÆÃãÂ÷à¢¶bsÇãÆ6Æ73Ò&'WGFöâ"‡&VcÒ'¶g&–VæE÷W&ÇÒ"F&vWCÒ%ö&Ææ²"&VÃÒ&æö÷VæW"#äÄ”ä^8~Xø¾88‹ûŞXªÂöãÂ÷âr–bg&–VæE÷W&ÂVÇ6RrwÓÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃîXZÎ[Èş8*.8*¾8*n8;>88YÓÂöÆ&VÃãÆ–çWBæÖSÒ&66÷VçEöæÖR"Ö†ÆVæwFƒÒ#S"fÇVSÒ'¶‡FÖÂæW66R†66÷VçBæ66÷VçEöæÖR–b66÷VçBVÇ6RFVæçBææÖR—Ò"&WV—&VCà¢ÆÆ&VÃä6†ææVÂ”CÂöÆ&VÃãÆ–çWBæÖSÒ&6†ææVÅö–B"Ö†ÆVæwFƒÒ#"fÇVSÒ'¶‡FÖÂæW66R†66÷VçBæ6†ææVÅö–B÷"rr’–b66÷VçBVÇ6RrwÒ#à¢ÆÆ&VÃä6†ææVÂ6V7&WCÂöÆ&VÃãÆ–çWBG—SÒ'77v÷&B"æÖSÒ&6†ææVÅ÷6V7&WB"WFö6ö×ÆWFSÒ&æWr×77v÷&B"Æ6V†öÆFW#Ò'²‚~ZHi»N8~8®8NZNY8şz›®jÈBr–b66÷VçBVÇ6R~[ø^š‚r—Ò#à¢ÆÆ&VÃä6†ææVÂ66W72Fö¶VãÂöÆ&VÃãÇFW‡F&VæÖSÒ&66W75÷Fö¶Vâ"WFö6ö×ÆWFSÒ&öfb"Æ6V†öÆFW#Ò'²‚~ZHi»N8~8®8NZNY8şz›®jÈBr–b66÷VçBVÇ6R~[ø^š‚r—Ò#ãÂ÷FW‡F&Và¢ÆÆ&VÃãÆ–çWBG—SÒ&6†V6¶&÷‚"æÖSÒ&7F—fR"fÇVSÒ'G'VR"7G–ÆSÒ'v–GFƒ¦WFò"²v6†V6¶VBr–b66÷VçBæB66÷VçBæ7F—fRVÇ6RrwÓâÄ”ä^˜
>i®8).iÈX«8¾88(³ÂöÆ&VÃà¢ÇãÇ6ÖÆÃîŠ¨ŞŠ‹Îh8^Z8şi©~Xû~XÉn8~8nKùŞZÙ8^8(Î8yK¾™Ú.8XhŞŠzK®8~8î8¾8)>8#Â÷6ÖÆÃãÂ÷ãÆ'WGFöãäÄ”ä^ŠŠŞZé®8).KùŞZÙƒÂö'WGFöããÂöf÷&Óà¢¶bsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÆ–æRöÖævR÷FW7B#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#äÄ”äR8îhê^{i®8).z+®Š¨ÓÂö'WGFöããÂöf÷&Óâr–b66÷VçBVÇ6RrwĞ¢Æƒ#îX‰ŞiÉşŠŠŞZé®8îh˜¾šcÂöƒ#ãÆöÃãÆÆ“îiÊÎyZ®y+Z(>8i©~Xû~˜Û^8).ŠŠŞZé£ÂöÆ“ãÆÆ“ä6†ææVÂ6V7&WN8™[~iÉô6†ææVÂ66W72Fö¶Vî8).KùŞZÙƒÂöÆ“ãÆÆ“îKˆ®Š‰…vV&†öö²U$Î8)$Ä”äRFWfVÆ÷W'>8y›¾˜Ë.8~8vV&†öö¾8).iÈX«XÉcÂöÆ“ãÆÆ“î8ÄÄ”äR8îhê^{i®8).z+®Š¨Ş8Ş8).ZéşŠÃÂöÆ“ãÆÆ“î8®Zê.jy8ÄdÔ”ÅyK¾™Ú.8¾8(“^Xˆn8+>8;Î888).y›®ŠÎ8~8n˜
>i£ÂöÆ“ãÂööÃà¢Æƒ#äÄ”ä^˜XŞKú[^jÛCÂöƒ#ãÆF—b7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆSãÇG#ãÇFƒîiz^i˜#Â÷FƒãÇFƒî8®Zê.jyƒÂ÷FƒãÇFƒîzŠîšãÂ÷FƒãÇFƒî{YiéÃÂ÷FƒãÇFƒîŠšnŠÃÂ÷FƒãÇFƒî8*8:8;ÃÂ÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç¶FVÆ—fW'•÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#r#î˜XŞKú[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSãÂöF—cârrp¢&WGW&âÆ–÷WB‚$Ä”ä^XZÎ[Èş8*.8*¾8*n8;>88ŠŠŞZé¢"Â&öG’Â66W75³Ò  ¤ç÷7B‚"öfÖ–Ç’öÆ–æRöÖævRöFVÆ—fW&–W2÷¶FVÆ—fW'•ö–GÒ÷&WG'’"¦FVbÆ–æUöFVÆ—fW'•÷&WG'’†FVÆ—fW'•ö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢FVÆ—fW'’Ò6W76–öâævWB„Æ–æTFVÆ—fW'’ÂFVÆ—fW'•ö–B¢–bæ÷BFVÆ—fW'’÷"FVÆ—fW'’çFVæçEö–BÒFVæçBæ–B÷"FVÆ—fW'’ç7FGW2ÓÒ'6VçB"÷"æ÷BFVÆ—fW'’æÖW76vR÷"æ÷BFVÆ—fW'’çF&vWE÷W&Ã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6VæEöÆ–æU÷W6‚†FVÆ—fW'’çW6W%ö–BÂFVÆ—fW'’çFVæçEö–BÂFVÆ—fW'’æ6FVv÷'’ÂFVÆ—fW'’æÖW76vRÂFVÆ—fW'’çF&vWE÷W&ÂÂFVÆ—fW'’æFVGWUö¶W’Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öÆ–æRöÖævR"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öÆ–æRöÖævR"¦FVbÆ–æUööff–6–Åö66÷VçE÷6fR†66÷VçEöæÖS¢7G"Òf÷&Ò‚âââ’Â6†ææVÅö–C¢7G"Òf÷&Ò‚""’Â6†ææVÅ÷6V7&WC¢7G"Òf÷&Ò‚""’Â66W75÷Fö¶Vã¢7G"Òf÷&Ò‚""’Â7F—fS¢&ööÂÒf÷&Ò„fÇ6R’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢66÷VçBÒ6W76–öâç66Æ"‡6VÆV7B„Æ–æTöff–6–Ä66÷VçB’çv†W&R„Æ–æTöff–6–Ä66÷VçBçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B66÷VçC ¢–bæ÷B6†ææVÅ÷6V7&WBç7G&—‚’÷"æ÷B66W75÷Fö¶Vâç7G&—‚“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ$6†ææVÂ6V7&WN8†66W72Fö¶Vî8).XZ^X©¾8~8n8ş88^8B"¢66÷VçBÒÆ–æTöff–6–Ä66÷VçB‡FVæçEö–C×FVæçBæ–BÂ66÷VçEöæÖSÖ66÷VçEöæÖRç7G&—‚•³£SÒÂ6†ææVÅö–CÖ6†ææVÅö–Bç7G&—‚•³£Ò÷"æöæRÀ¢6†ææVÅ÷6V7&WEöVæ7'—FVCÖÆ–æUöVæ7'—B†6†ææVÅ÷6V7&WBç7G&—‚’’Â66W75÷Fö¶VåöVæ7'—FVCÖÆ–æUöVæ7'—B†66W75÷Fö¶Vâç7G&—‚’’ÂvV&†ööµö¶W“×6V7&WG2çFö¶Vå÷W&Ç6fRƒ3"’¢6W76–öâæFB†66÷VçB¢VÇ6S ¢66÷VçBæ66÷VçEöæÖRÂ66÷VçBæ6†ææVÅö–BÒ66÷VçEöæÖRç7G&—‚•³£SÒÂ6†ææVÅö–Bç7G&—‚•³£Ò÷"æöæP¢–b6†ææVÅ÷6V7&WBç7G&—‚“¢66÷VçBæ6†ææVÅ÷6V7&WEöVæ7'—FVBÒÆ–æUöVæ7'—B†6†ææVÅ÷6V7&WBç7G&—‚’¢–b66W75÷Fö¶Vâç7G&—‚“¢66÷VçBæ66W75÷Fö¶VåöVæ7'—FVBÒÆ–æUöVæ7'—B†66W75÷Fö¶Vâç7G&—‚’¢66÷VçBæ7F—fRÂ66÷VçBçWFFVEöBÒ7F—fRÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öÆ–æRöÖævR"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öÆ–æRöÖævR÷FW7B"¦FVbÆ–æUööff–6–Åö66÷VçE÷FW7B†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢66÷VçBÒ6W76–öâç66Æ"‡6VÆV7B„Æ–æTöff–6–Ä66÷VçB’çv†W&R„Æ–æTöff–6–Ä66÷VçBçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B66÷VçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ$Ä”ä^XZÎ[Èş8*.8*¾8*n8;>88ŠŠŞZé®8Î8.8(®8î8¾8)2"¢–æfòÂW'&÷"ÒÆ–æUö&÷Eö–æfò†66÷VçB¢–bW'&÷"÷"æ÷B–æfó ¢66÷VçBæÆ7EöW'&÷"Â66÷VçBçfW&–f–VEöBÒb$hê^{i®z+®Š¨ŞûÉ§¶W'&÷"÷"~[ùÎzÙN8).z+®Š¨Ş8~8Ş8î8¾8)2wÒ"ÂæöæP¢VÇ6S ¢66÷VçBæ&÷EöF—7Æ•öæÖRÒ–æfòævWB‚&F—7Æ”æÖR"’÷"66÷VçBæ66÷VçEöæÖP¢66÷VçBæ&÷Eö&6–5ö–BÒ–æfòævWB‚&&6–4–B"’÷"æöæP¢66÷VçBçfW&–f–VEöBÂ66÷VçBæÆ7EöW'&÷"ÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’ÂæöæP¢66÷VçBçWFFVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öÆ–æRöÖævR"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öÆ–æR÷vV&†öö²÷·vV&†ööµö¶W—Ò"¦7–æ2FVbÆ–æU÷vV&†öö²‡vV&†ööµö¶W“¢7G"Â&WVW7C¢&WVW7BÂ…öÆ–æU÷6–væGW&S¢7G"ÂæöæRÒ†VFW"„æöæR’“ ¢v—F‚6W76–öäÆö6Â‚’26W76–öã ¢66÷VçBÒ6W76–öâç66Æ"‡6VÆV7B„Æ–æTöff–6–Ä66÷VçB’çv†W&R„Æ–æTöff–6–Ä66÷VçBçvV&†ööµö¶W’ÓÒvV&†ööµö¶W’ÂÆ–æTöff–6–Ä66÷VçBæ7F—fRæ—5ò…G'VR’’¢–bæ÷B66÷VçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢–bæ÷B…öÆ–æU÷6–væGW&S ¢66÷VçBæÆ7EöW'&÷"Ò%vV&†öö¾{Û.YŞ8Î8.8(®8î8¾8)2#²6W76–öâæ6öÖÖ—B‚¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ$Ä”ä^{Û.YŞ8).z+®Š¨Ş8~8Ş8î8¾8)2"¢&uö&öG’Òv—B&WVW7Bæ&öG’‚¢G'“ ¢6†ææVÅ÷6V7&WBÒÆ–æUöFV7'—B†66÷VçBæ6†ææVÅ÷6V7&WEöVæ7'—FVB’æVæ6öFR‚¢W†6WB'VçF–ÖTW'&÷# ¢66÷VçBæÆ7EöW'&÷"Ò%vV&†öö¾Š¨ŞŠ‹Îh8^Z8).[êXû~8~8Ş8î8¾8)2#²6W76–öâæ6öÖÖ—B‚¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓS2ÂFWF–ÃÒ$Ä”ä^ŠŠŞZé®8).[êXû~8~8Ş8î8¾8)2"¢W‡V7FVBÒ&6ScBæ#cFVæ6öFR††Ö2ææWr†6†ææVÅ÷6V7&WBÂ&uö&öG’Â†6†Æ–"ç6†#Sb’æF–vW7B‚’’æFV6öFR‚¢–bæ÷B†Ö2æ6ö×&UöF–vW7B†W‡V7FVBÂ…öÆ–æU÷6–væGW&R“ ¢66÷VçBæÆ7EöW'&÷"Ò%vV&†öö¾{Û.YŞ8ÎKˆˆ{N8~8î8¾8)2#²6W76–öâæ6öÖÖ—B‚¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ$Ä”ä^{Û.YŞ8).z+®Š¨Ş8~8Ş8î8¾8)2"¢G'“ ¢–ÆöBÒ§6öâæÆöG2‡&uö&öG’¢W†6WB§6öâä¥4ôäFV6öFTW'&÷# ¢66÷VçBæÆ7EöW'&÷"Ò%vV&†öö¾8*N898;>888ä¥4ôî8ÎKˆŞjÚ>8~8’#²6W76–öâæ6öÖÖ—B‚¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ$Ä”ä^8*N898;>888).ŠªŞ8şXùn8(Î8î8¾8)2"¢æ÷rÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢66÷VçBæÆ7E÷vV&†ööµöBÂ66÷VçBæÆ7EöW'&÷"Òæ÷rÂæöæP¢2Ä”äRFWfVÆ÷W'>8î8ÎjIÎŠ‹Î8Ş8öWfVçG>8Îz›®8î8ş8(8Xù~KúŠ‰˜Ë.8).XX8¾z+®Zé®88(¾8 ¢6W76–öâæ6öÖÖ—B‚¢f÷"WfVçB–â–ÆöBævWB‚&WfVçG2"ÂµÒ“ ¢6÷W&6RÒWfVçBævWB‚'6÷W&6R"’÷"·Ó²Æ–æU÷W6W%ö–BÒ6÷W&6RævWB‚'W6W$–B"¢–bæ÷BÆ–æU÷W6W%ö–B÷"6÷W&6RævWB‚'G—R"’Ò'W6W"# ¢6öçF–çVP¢–bWfVçBævWB‚'G—R"’ÓÒ'VæföÆÆ÷r# ¢Æ–æ²Ò6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Æ–æTÆ–æ²’çv†W&R„fÖ–Ç”Æ–æTÆ–æ²çFVæçEö–BÓÒ66÷VçBçFVæçEö–BÂfÖ–Ç”Æ–æTÆ–æ²æÆ–æU÷W6W%ö–BÓÒÆ–æU÷W6W%ö–BÂfÖ–Ç”Æ–æTÆ–æ²æ7F—fRæ—5ò…G'VR’’¢–bÆ–æ³¢Æ–æ²æ7F—fRÂÆ–æ²çVæÆ–æ¶VEöBÒfÇ6RÂæ÷p¢6öçF–çVP¢ÖW76vRÒWfVçBævWB‚&ÖW76vR"’÷"·Ó²FW‡EöÖW76vRÒ7G"†ÖW76vRævWB‚'FW‡B"Â""’’ç7G&—‚’–bÖW76vRævWB‚'G—R"’ÓÒ'FW‡B"VÇ6R" ¢ÖF6‚Ò&RægVÆÆÖF6‚‡".˜
>i¥Ç2²…´Õ¦×£Ó•òÕ×³ÃCÒ’"ÂFW‡EöÖW76vR¢&WÇ’Ò$dÔ”ÅyK¾™Ú.8~˜
>i®8+>8;Î888).y›®ŠÎ8~88Î˜
>i¢8+>8;Î888Ş8˜Kú8~8n8ş88^8N8" ¢–bÖF6ƒ ¢Fö¶VâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Æ–æTÆ–æµFö¶Vâ’çv†W&R„fÖ–Ç”Æ–æTÆ–æµFö¶VâçFVæçEö–BÓÒ66÷VçBçFVæçEö–BÀ¢fÖ–Ç”Æ–æTÆ–æµFö¶VâçFö¶Våö†6‚ÓÒFö¶Våö†6‚†ÖF6‚æw&÷Wƒ’’ÂfÖ–Ç”Æ–æTÆ–æµFö¶VâçW6VEöBæ—5ò„æöæR’ÂfÖ–Ç”Æ–æTÆ–æµFö¶VâæW‡—&W5öBâæ÷r’¢6öæfÆ–7BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Æ–æTÆ–æ²æ–B’çv†W&R„fÖ–Ç”Æ–æTÆ–æ²çFVæçEö–BÓÒ66÷VçBçFVæçEö–BÂfÖ–Ç”Æ–æTÆ–æ²æÆ–æU÷W6W%ö–BÓÒÆ–æU÷W6W%ö–BÀ¢fÖ–Ç”Æ–æTÆ–æ²çW6W%ö–BÒFö¶VâçW6W%ö–B’’–bFö¶VâVÇ6RæöæP¢–bFö¶VâæBæ÷B6öæfÆ–7C ¢Æ–æ²Ò6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Æ–æTÆ–æ²’çv†W&R„fÖ–Ç”Æ–æTÆ–æ²çFVæçEö–BÓÒ66÷VçBçFVæçEö–BÂfÖ–Ç”Æ–æTÆ–æ²çW6W%ö–BÓÒFö¶VâçW6W%ö–B’¢–bÆ–æ³ ¢Æ–æ²æÆ–æU÷W6W%ö–BÂÆ–æ²æ7F—fRÂÆ–æ²çVæÆ–æ¶VEöBÂÆ–æ²æÆ–æ¶VEöBÒÆ–æU÷W6W%ö–BÂG'VRÂæöæRÂæ÷p¢VÇ6S ¢6W76–öâæFB„fÖ–Ç”Æ–æTÆ–æ²‡FVæçEö–CÖ66÷VçBçFVæçEö–BÂW6W%ö–C×Fö¶VâçW6W%ö–BÂÆ–æU÷W6W%ö–CÖÆ–æU÷W6W%ö–B’¢Fö¶VâçW6VEöBÒæ÷p¢&WÇ’Ò$dÔ”Å88äÄ”ä^˜
>i®8ÎZèÎK¨n8~8î8~8ş8.K¸®[èÎ8xªÎˆˆî8¾8(8îZJ~Xˆ~8®˜	®yú^8).8>88(88®˜8(®8~8î88" ¢VÇ6S ¢&WÇ’Ò.˜
>i®8+>8;Î888ÎxJX«8î8ş8şiÉş™™Xˆ~8(Î8~88$dÔ”ÅyK¾™Ú.8¾8(ik8~8N8+>8;Î888).y›®ŠÎ8~8n8ş88^8N8" ¢6W76–öâæ6öÖÖ—B‚¢–bWfVçBævWB‚'&WÇ•Fö¶Vâ"’æBWfVçBævWB‚'G—R"’–â²&ÖW76vR"Â&föÆÆ÷r'Ó ¢Æ–æU÷&WÇ’†66÷VçBÂWfVçE²'&WÇ•Fö¶Vâ%ÒÂ&WÇ’¢&WGW&â¥4ôå&W7öç6R‡²&ö²#¢G'VWÒ  ¤ævWB‚"öfÖ–Ç’×W6‚×v÷&¶W"æ§2"¦FVbfÖ–Ç•÷W6…÷v÷&¶W"‚“ ¢67&—BÒrrw6VÆbæFDWfVçDÆ—7FVæW"‚'W6‚"ÆWfVçCÓç¶ÆWBFF×·F—FÆS¢$U5E$TÄÄdÔ”Å’"Æ&öG“¢.ik8~8N8®yú^8(8¾8Î8.8(®8î8’"ÇW&Ã¢"öfÖ–Ç’öæ÷F–f–6F–öç2'Ó·G'—¶FF×²ââæFFÂââæWfVçBæFFæ§6öâ‚—×Ö6F6‚†R—·ÖWfVçBçv—EVçF–Â‡6VÆbç&Vv—7G&F–öâç6†÷tæ÷F–f–6F–öâ†FFçF—FÆRÇ¶&öG“¦FFæ&öG’Æ–6öã¢"öff–6öâæ–6ò"ÆFF§·W&Ã¦FFçW&Ç×Ò’—Ò“·6VÆbæFDWfVçDÆ—7FVæW"‚&æ÷F–f–6F–öæ6Æ–6²"ÆWfVçCÓç¶WfVçBææ÷F–f–6F–öâæ6Æ÷6R‚“¶WfVçBçv—EVçF–Â†6Æ–VçG2æÖF6„ÆÂ‡·G—S¢'v–æF÷r"Æ–æ6ÇVFUVæ6öçG&öÆÆVC§G'VWÒ’çF†Vâ†—FV×3Óç¶f÷"†6öç7B—FVÒöb—FV×2—¶–b‚&fö7W2"–â—FVÒ—¶—FVÒææf–vFR†WfVçBææ÷F–f–6F–öâæFFçW&Â“·&WGW&â—FVÒæfö7W2‚—××&WGW&â6Æ–VçG2æ÷Våv–æF÷r†WfVçBææ÷F–f–6F–öâæFFçW&Â—Ò’—Ò“²rrp¢&WGW&â&W7öç6R†6öçFVçC×67&—BÂÖVF–÷G—SÒ&Æ–6F–öâö¦f67&—B"Â†VFW'3×²%6W'f–6RÕv÷&¶W"ÔÆÆ÷vVB#¢"ò"Â$66†RÔ6öçG&öÂ#¢&æòÖ66†R'Ò  ¤ç÷7B‚"öfÖ–Ç’÷W6‚×7V'67&—F–öç2"¦7–æ2FVbfÖ–Ç•÷W6…÷7V'67&—F–öåö7&VFR‡&WVW7C¢&WVW7BÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–ÆöBÒv—B&WVW7Bæ§6öâ‚¢VæGö–çBÂ¶W—2Ò7G"‡–ÆöBævWB‚&VæGö–çB"Â""’’Â–ÆöBævWB‚&¶W—2"’÷"·Ğ¢#SfF‚ÂWF‚Ò7G"†¶W—2ævWB‚'#SfF‚"Â""’’Â7G"†¶W—2ævWB‚&WF‚"Â""’¢–bæ÷BVæGö–çBç7F'G7v—F‚‚&‡GG3¢òò"’÷"æ÷B#SfF‚÷"æ÷BWFƒ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.˜	®yú^zºşiÊ¾h8^Z8).z+®Š¨Ş8~8Ş8î8¾8)2"¢7V'67&—F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•W6…7V'67&—F–öâ’çv†W&R„fÖ–Ç•W6…7V'67&—F–öâæVæGö–çBÓÒVæGö–çB’¢–b7V'67&—F–öã ¢7V'67&—F–öâçW6W%ö–BÂ7V'67&—F–öâç#SfF‚Â7V'67&—F–öâæWF‚Â7V'67&—F–öâæ7F—fRÒW6W"æ–BÂ#SfF‚ÂWF‚ÂG'VP¢VÇ6S ¢6W76–öâæFB„fÖ–Ç•W6…7V'67&—F–öâ‡W6W%ö–C×W6W"æ–BÂVæGö–çCÖVæGö–çBÂ#SfFƒ×#SfF‚ÂWFƒÖWF‚À¢W6W%övVçCÒ‡&WVW7Bæ†VFW'2ævWB‚'W6W"ÖvVçB"’÷"""•³£3Ò÷"æöæR’¢6WGF–ærÒfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–ær‡W6W"Â6W76–öâ“²6WGF–ærçW6…öVæ&ÆVBÒG'VP¢6W76–öâæ6öÖÖ—B‚¢&WGW&â¥4ôå&W7öç6R‡²&ö²#¢G'VWÒ  ¤ç÷7B‚"öfÖ–Ç’÷W6‚×FW7B"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷W6…÷FW7B‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢¶W’Òb'W6ƒ§FW7C§·W6W"æ–GÓ§¶FFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’æ—6öf÷&ÖB‚—Ò ¢6VçBÒ6VæE÷vV%÷W6‚‡W6W"æ–BÂ&ÖW76vW2"Â$U5E$TÄÄdÔ”Å’88n8+88˜	®yúR"Â.89n8:8*n8+n˜	®yú^8şjÚ>[‹8¾ŠŠŞZé®8^8(Î8n8N8î88""Â"öfÖ–Ç’öæ÷F–f–6F–öç2"Â¶W’Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢–bæ÷B6VçC ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚.˜	®yú^88n8+88ûÙÄdÔ”Å’"ÂsÆƒî˜	®yú^8).˜Kú8~8Ş8î8¾8)>8~8~8óÂöƒãÇ6Æ73Ò&W'&÷"#îXX8¾8Î89n8:8*n8+n˜	®yú^8).Š‹Xúş88(¾8Ş8).h«Î8~8ikyØ8:88>8+¾8;Î8+889~88>8+~8:^˜	®yú^8).8*®8;>8¾8~8nKùŞZÙ8~8n8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2#î˜	®yú^ŠŠŞZé®8h‹¾8(³ÂöârÂW6W"Â6W76–öâ’Â7FGW5ö6öFSÓC¢&WGW&âfÖ–Ç•öÆ–÷WB‚.˜	®yú^88n8+88ûÙÄdÔ”Å’"ÂsÆƒî88n8+88˜	®yú^8).˜Kú8~8î8~8óÂöƒãÇî8>8îzºşiÊ¾8¾˜	®yú^8ÎŠzK®8^8(Î8(¾8>88).8Nz+®Š¨Ş8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2#î˜	®yú^ŠŠŞZé®8h‹¾8(³ÂöârÂW6W"Â6W76–öâ  ¦FVbæW‡EöfÖ–Ç•öææ—fW'6'’†ÖöçFƒ¢–çBÂF“¢–çBÂFöF“¢FFR’ÓâFFS ¢"".K¸®[›N8î8ş8şiÚ^[›N8îŠ‰[û^iz^8).‹ùN88#.iÈƒ#iz^8ş[›>[›N8¾8ó.iÈƒ#iz^88~8nzYŞ8n8""" ¢FVbö67W'&Væ6R‡–V#¢–çB’ÓâFFS ¢G'“ ¢&WGW&âFFR‡–V"ÂÖöçF‚ÂF’¢W†6WBfÇVTW'&÷# ¢&WGW&âFFR‡–V"Â"Â#‚ ¢6æF–FFRÒö67W'&Væ6R‡FöF’ç–V"¢&WGW&â6æF–FFR–b6æF–FFRãÒFöF’VÇ6Rö67W'&Væ6R‡FöF’ç–V"²  ¤ævWB‚"öfÖ–Ç’öææ—fW'6&–W2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öææ—fW'6&–W2‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFörÂFVæçB’æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B¢æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’À¢FVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢FöF’ÒFFRçFöF’‚¢WfVçG3¢Æ—7E·GWÆU¶–çBÂ7G%ÕÒÒµĞ¢Ö—76–æuö†æF÷fW#¢Æ—7E·7G%ÒÒµĞ¢f÷"÷væW'6†—ÂFörÂFVæçB–â&V6÷&G3 ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöræ–B’¢†÷FòÒbsÆ–Ör6Æ73Ò&fÖ–Ç’ÖFör×F‡VÖ""7&3Ò"öfÖ–Ç’öFöw2÷¶Föræ–GÒ÷†÷Fò"ÇCÒ'¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ò#âr–b&öf–ÆRæB&öf–ÆRç†÷FõöFFVÇ6R" ¢–bFöræ&—'F…öFFS ¢W6öÖ–ærÒæW‡EöfÖ–Ç•öææ—fW'6'’†Föræ&—'F…öFFRæÖöçF‚ÂFöræ&—'F…öFFRæF’ÂFöF’¢F—2Ò‡W6öÖ–ærÒFöF’’æF—0¢GW&æ–ærÒW6öÖ–ærç–V"ÒFöræ&—'F…öFFRç–V ¢F–Ö–ærÒ.K¸®iz^8~8ûÈ"–bF—2ÓÒVÇ6Rb.8.8‡¶F—7ŞizR ¢WfVçG2æVæB‚†F—2ÂbrrsÆ6Æ73Ò&ÖöGVÆR"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒ#ç·†÷F÷ÓÆƒ3ï	øè"¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îŠ©^yIşizSÂöƒ3à¢Çç·W6öÖ–ærç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ŞûÈ‡·F–Ö–æwŞûÈ“Â÷ãÇãÇ7G&öæsç·GW&æ–æwŞjÛ3Â÷7G&öæsî8¾8®8(®8î8“Â÷ãÇç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷ãÂöârrr’ ¢†æF÷fW"Ò6W76–öâç66Æ"€¢6VÆV7B…W•6ÆRæ†æF÷fW%öFFR’çv†W&R…W•6ÆRçFVæçEö–BÓÒFörçFVæçEö–BÂW•6ÆRæFöuö–BÓÒFöræ–BÀ¢W•6ÆRæ†æF÷fW%öFFRæ—5öæ÷B„æöæR’¢æ÷&FW%ö'’…W•6ÆRæ†æF÷fW%öFFRæFW62‚’’æÆ–Ö—Bƒ¢¢–bæ÷B†æF÷fW# ¢†æF÷fW"Ò6W76–öâç66Æ"€¢6VÆV7B„FöuG&ç6fW"çG&ç6fW'&VEööâ’çv†W&R„FöuG&ç6fW"çFVæçEö–BÓÒFörçFVæçEö–BÂFöuG&ç6fW"æFöuö–BÓÒFöræ–B¢æ÷&FW%ö'’„FöuG&ç6fW"çG&ç6fW'&VEööâæFW62‚’’æÆ–Ö—Bƒ¢¢–b†æF÷fW# ¢W6öÖ–ærÒæW‡EöfÖ–Ç•öææ—fW'6'’††æF÷fW"æÖöçF‚Â†æF÷fW"æF’ÂFöF’¢F—2Ò‡W6öÖ–ærÒFöF’’æF—0¢–V'2ÒW6öÖ–ærç–V"Ò†æF÷fW"ç–V ¢F–Ö–ærÒ.K¸®iz^8~8ûÈ"–bF—2ÓÒVÇ6Rb.8.8‡¶F—7ŞizR ¢WfVçG2æVæB‚†F—2ÂbrrsÆ6Æ73Ò&ÖöGVÆR"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒ#ç·†÷F÷ÓÆƒ3ï	øú¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8î8®‹øî8Š‰[û^izSÂöƒ3à¢Çç·W6öÖ–ærç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ŞûÈ‡·F–Ö–æwŞûÈ“Â÷ãÇãÇ7G&öæsç·–V'7ŞY[›CÂ÷7G&öæsî8~8“Â÷ãÇî8®‹øî8iz^ûÉ§¶†æF÷fW"ç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ÓÂ÷ãÂöârrr’¢VÇ6S ¢Ö—76–æuö†æF÷fW"æVæB†‡FÖÂæW66R†Föræ6ÆÅöæÖR’ ¢6&G2Ò""æ¦ö–â†6&Bf÷"òÂ6&B–â6÷'FVB†WfVçG2Â¶W“ÖÆÖ&FWfVçC¢WfVçE³Ò’¢–bæ÷B6&G3 ¢6&G2ÒsÆF—b6Æ73Ò'FVæçB#ãÇîŠzK®8~8Ş8(¾Š‰[û^iz^8Î8î88.8(®8î8¾8)>8#Â÷ãÇîxªÎ8îyIş[›NiÈiz^8(N8‹*Z;.8;¾ŠÛ.kŠzêyn8î[É^kŠ8~iz^8).y›¾˜Ë.88(¾8ˆz®X¹^ŠzK®8^8(Î8î88#Â÷ãÂöF—câp¢æ÷F–6RÒbrrsÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsî8®‹øî8iz^8îy›¾˜Ë.[è^8Â÷7G&öæsãÇç².8"æ¦ö–â†Ö—76–æuö†æF÷fW"—ÓÂ÷à¢ÇãÇ6ÖÆÃîxªÎˆˆîXN8î‹*Z;.zêyn8î8ş8şŠÛ.kŠXXzêyn8~[É^kŠ8~iz^8).y›¾˜Ë.88(¾888®‹øî8Š‰[û^iz^8ÎŠzK®8^8(Î8î88#Â÷6ÖÆÃãÂ÷ãÂöF—cârrr–bÖ—76–æuö†æF÷fW"VÇ6R" ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒîŠ©^yIşiz^8;¾8®‹øî8Š‰[û^izSÂöƒà¢Çî8n88îZÙ8îZJ~Xˆ~8®Š‰[û^iz^8).8‹ù8Nšn8¾ŠzK®8~8n8N8î88#Â÷ãÆF—b6Æ73Ò&w&–B#ç¶6&G7ÓÂöF—cç¶æ÷F–6WÒrrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.Š©^yIşiz^8;¾8®‹øî8Š‰[û^iz^ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’öææ—fW'6&–W2öæ÷F–6R÷¶Föuö–GÒ÷¶WfVçE÷G—WÒ÷¶WfVçEöFFWÒ"¦FVbfÖ–Ç•öææ—fW'6'•öæ÷F–6Uö÷Vâ†Föuö–C¢–çBÂWfVçE÷G—S¢7G"ÂWfVçEöFFS¢7G"ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bWfVçE÷G—Ræ÷B–â²&&—'F†F’"Â&†öÖV6öÖ–ær'Ò÷"æ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢G'“ ¢'6VBÒFFRæg&öÖ—6öf÷&ÖB†WfVçEöFFR¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢W†—7F–ærÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ—fW'6'”F—6Ö—76Â’çv†W&R€¢fÖ–Ç”ææ—fW'6'”F—6Ö—76ÂçW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç”ææ—fW'6'”F—6Ö—76ÂæFöuö–BÓÒFöuö–BÀ¢fÖ–Ç”ææ—fW'6'”F—6Ö—76ÂæWfVçE÷G—RÓÒWfVçE÷G—RÂfÖ–Ç”ææ—fW'6'”F—6Ö—76ÂæWfVçEöFFRÓÒ'6VBÀ¢’¢–bæ÷BW†—7F–æs ¢6W76–öâæFB„fÖ–Ç”ææ—fW'6'”F—6Ö—76Â‡W6W%ö–C×W6W"æ–BÂFöuö–CÖFöuö–BÂWfVçE÷G—SÖWfVçE÷G—RÂWfVçEöFFS×'6VB’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öææ—fW'6&–W2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öææ÷Væ6VÖVçG2‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢FVæçEö–G2ÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçBÂFVæçB’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–B¢çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–Bæ–åò‡FVæçEö–G2’ÂfÖ–Ç”ææ÷Væ6VÖVçBæ7F—fRæ—5ò…G'VR’À¢FVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢æ÷&FW%ö'’„fÖ–Ç”ææ÷Væ6VÖVçBæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ¢’æÆÂ‚’–bFVæçEö–G2VÇ6RµĞ¢6&G2Ò" ¢f÷"ææ÷Væ6VÖVçBÂFVæçB–â&V6÷&G3 ¢WfVçBÒbsÇãÇ7â6Æ73Ò&&FvR#î™h¾X*Îiz^ûÉ§¶ææ÷Væ6VÖVçBæWfVçEöFFRç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"—ÓÂ÷7ããÂ÷âr–bææ÷Væ6VÖVçBæWfVçEöFFRVÇ6R" ¢6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÇãÇ7G&öæsç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷7G&öæsî8Ç6ÖÆÃç¶ææ÷Væ6VÖVçBæ7&VFVEöBæFFR‚’ç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"—Şhë.‹È“Â÷6ÖÆÃãÂ÷à¢Æƒ"7G–ÆSÒ&Ö&v–â×F÷£‡‚#ç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBçF—FÆR—ÓÂöƒ#ç¶WfVçGĞ¢ÆF—b7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBæ&öG’—ÓÂöF—cãÇãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçBæ–GÒ#îŠ›>8~8şŠh¾8(³ÂöãÂ÷ãÂö'F–6ÆSârrp¢–bæ÷B6&G3 ¢6&G2ÒsÆF—b6Æ73Ò'FVæçB#ãÇîxûîYÊ8xªÎˆˆî8¾8(8î8®yú^8(8¾8ş8.8(®8î8¾8)>8#Â÷ãÂöF—câp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒîxªÎˆˆî8¾8(8î8®yú^8(8³Âöƒà¢ÇîhI¾xªÎ8).‹øî88şxªÎˆˆî8¾8(8î8dÔ”ÅKÉ®8;¾8*N898;>888;¾ZJ~Xˆ~8®8NjXh^8).ŠzK®8~8n8N8î88#Â÷ç¶6&G7Òrrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.xªÎˆˆî8¾8(8î8®yú^8(8¾ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçEö–GÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öææ÷Væ6VÖVçEöFWF–Â†ææ÷Væ6VÖVçEö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢FVæçEö–G2ÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ¢&V6÷&BÒ6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçBÂFVæçB’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–B¢çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒææ÷Væ6VÖVçEö–BÂfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–Bæ–åò‡FVæçEö–G2’À¢fÖ–Ç”ææ÷Væ6VÖVçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢’æf—'7B‚’–bFVæçEö–G2VÇ6RæöæP¢–bæ÷B&V6÷&C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.8®yú^8(8¾8ÎŠh¾8N8¾8(®8î8¾8)2"¢ææ÷Væ6VÖVçBÂFVæçBÒ&V6÷&@¢&VBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçE&VB’çv†W&R€¢fÖ–Ç”ææ÷Væ6VÖVçE&VBæææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÀ¢fÖ–Ç”ææ÷Væ6VÖVçE&VBçW6W%ö–BÓÒW6W"æ–BÀ¢’¢–b&VC ¢&VBç&VEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢VÇ6S ¢6W76–öâæFB„fÖ–Ç”ææ÷Væ6VÖVçE&VB†ææ÷Væ6VÖVçEö–CÖææ÷Væ6VÖVçBæ–BÂW6W%ö–C×W6W"æ–B’¢6W76–öâæ6öÖÖ—B‚¢WfVçEöFWF–Ç2ÒµĞ¢–bææ÷Væ6VÖVçBæWfVçEöFFS ¢WfVçEöFWF–Ç2æVæB†b.™h¾X*Îiz^ûÉ§¶ææ÷Væ6VÖVçBæWfVçEöFFRç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—Ò"¢–bææ÷Væ6VÖVçBæWfVçE÷F–ÖS ¢WfVçEöFWF–Ç2æVæB†b.™h¾Zx¾i˜.X‹¾ûÉ§¶ææ÷Væ6VÖVçBæWfVçE÷F–ÖWÒ"¢–bææ÷Væ6VÖVçBæWfVçEöÆö6F–öã ¢WfVçEöFWF–Ç2æVæB†b.™h¾X*ÎZNh˜ûÉ§¶‡FÖÂæW66R†ææ÷Væ6VÖVçBæWfVçEöÆö6F–öâ—Ò"¢–bææ÷Væ6VÖVçBæWfVçEö66—G“ ¢WfVçEöFWF–Ç2æVæB†b.Zé®Y:ûÉ§¶ææ÷Væ6VÖVçBæWfVçEö66—G—ŞYÒ"¢WfVçBÒbsÆF—b6Æ73Ò'FVæçB#ãÇãÇ7G&öæsî8*N898;>88h8^ZÂ÷7G&öæsãÂ÷ãÇç²#Æ'#â"æ¦ö–â†WfVçEöFWF–Ç2—ÓÂ÷ãÂöF—câr–bWfVçEöFWF–Ç2VÇ6R" ¢&W7öç6Uöf÷&ÒÒ" ¢–bææ÷Væ6VÖVçBæWfVçEöFFS ¢FVFÆ–æRÒææ÷Væ6VÖVçBç&W7öç6UöFVFÆ–æR÷"†FFWF–ÖR€¢ææ÷Væ6VÖVçBæWfVçEöFFRç–V"Âææ÷Væ6VÖVçBæWfVçEöFFRæÖöçF‚Âææ÷Væ6VÖVçBæWfVçEöFFRæF’À¢’ÂÂG¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’À¢’ÒF–ÖVFVÇF†F—3Ó’¢–bæ÷BFVFÆ–æRçG¦–æfó ¢FVFÆ–æRÒFVFÆ–æRç&WÆ6R‡G¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’¢VÇ6S ¢FVFÆ–æRÒFVFÆ–æRæ7F–ÖW¦öæR…¦öæT–æfò‚$6–õFö·–ò"’¢&W7öç6Uö÷VâÒFFWF–ÖRææ÷r…¦öæT–æfò‚$6–õFö·–ò"’’ÂFVFÆ–æP¢FVFÆ–æUöÆ&VÂÒFVFÆ–æRç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizRXØX˜Ói˜""¢&W7öç6RÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”WfVçE&W7öç6R’çv†W&R€¢fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÂfÖ–Ç”WfVçE&W7öç6RçW6W%ö–BÓÒW6W"æ–@¢’¢÷væVEöFöw2Ò6W76–öâç66Æ'2€¢6VÆV7B„För’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—çFVæçEö–BÓÒææ÷Væ6VÖVçBçFVæçEö–BÀ¢Föt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’’æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢6VÆV7FVEöæÖW2Ò6WB‚‡&W7öç6RæFöuöæÖW2÷"""’ç7Æ—B‚.8"’’–b&W7öç6RVÇ6R6WB‚¢Föuö6†V6·2Ò""æ¦ö–â€¢bsÆÆ&VÂ7G–ÆSÒ&F—7Æ“¦–æÆ–æRÖfÆWƒ¶Æ–vâÖ—FV×3¦6VçFW#¶v£gƒ¶Ö&v–â×&–v‡C£g‚#ãÆ–çWBG—SÒ&6†V6¶&÷‚"æÖSÒ&Föuö–G2"fÇVSÒ'¶Föræ–GÒ"7G–ÆSÒ'v–GFƒ¦WFò"²v6†V6¶VBr–bFöræ6ÆÅöæÖR–â6VÆV7FVEöæÖW2VÇ6RrwÓç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöÆ&VÃâp¢f÷"För–â÷væVEöFöw0¢’÷"sÇãÇ6ÖÆÃî8>8îxªÎˆˆî8˜
>i®8^8(Î8şhI¾xªÎ8ş8.8(®8î8¾8)>8#Â÷6ÖÆÃãÂ÷âp¢7W'&VçBÒ²&GFVæF–ær#¢.Xø.Xª"Â'v—FÆ—7FVB#¢.8*Ş8:>8;>8+¾8:¾[è^8"Â&Ö–&R#¢.jIÎŠˆîKŠÒ"Â&FV6Æ–æVB#¢.KˆŞXø.Xª'ÒævWB‡&W7öç6Rç7FGW2Â.iÊ®Y¹îzÙB"’–b&W7öç6RVÇ6R.iÊ®Y¹îzÙB ¢f÷&ÒÒbrrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçBæ–GÒ÷&W7öç6R#à¢ÆÆ&VÃîXø.Xª8¾8N8N8cÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&W7öç6U÷7FGW2"&WV—&VCà¢Æ÷F–öâfÇVSÒ&GFVæF–ær"²w6VÆV7FVBr–b&W7öç6RæB&W7öç6Rç7FGW2ÓÒvGFVæF–ærrVÇ6RrwÓîXø.Xª8~8î8“Âö÷F–öãà¢Æ÷F–öâfÇVSÒ&Ö–&R"²w6VÆV7FVBr–b&W7öç6RæB&W7öç6Rç7FGW2ÓÒvÖ–&RrVÇ6RrwÓîjIÎŠˆîKŠÓÂö÷F–öãà¢Æ÷F–öâfÇVSÒ&FV6Æ–æVB"²w6VÆV7FVBr–b&W7öç6RæB&W7öç6Rç7FGW2ÓÒvFV6Æ–æVBrVÇ6RrwÓîXø.Xª8~8î8¾8)3Âö÷F–öããÂ÷6VÆV7Cà¢ÆÆ&VÃîXø.XªK«®i[ÂöÆ&VÃãÆ–çWBG—SÒ&çVÖ&W""æÖSÒ''G•÷6—¦R"Ö–ãÒ#"ÖƒÒ##"fÇVSÒ'·&W7öç6Rç'G•÷6—¦R–b&W7öç6RVÇ6RÒ"&WV—&VCà¢ÆÆ&VÃîKˆ{y.8¾Xø.Xª88(¾hI¾xªÃÂöÆ&VÃãÆF—cç¶Föuö6†V6·7ÓÂöF—cà¢ÆÆ&VÃîxªÎˆˆî88î˜
>{ZK¨¾š^ûÈƒSih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&æ÷FR"Ö†ÆVæwFƒÒ#S#ç¶‡FÖÂæW66R‡&W7öç6Rææ÷FR÷"rr’–b&W7öç6RVÇ6RrwÓÂ÷FW‡F&Và¢Æ'WGFöãîY¹îzÙN8).KùŞZÙ88(³Âö'WGFöããÂöf÷&Óârrr–b&W7öç6Uö÷VâVÇ6RrrsÆF—b6Æ73Ò'FVæçB#ãÇãÇ7G&öæsîY¹îzÙNXù~K¹8ş{X.K¨n8~8î8~8ş8#Â÷7G&öæsãÂ÷ãÇîZHi»N8Î[ø^Šh8®ZNY8şxªÎˆˆî8y»Nhê^8N˜
>{Z8ş88^8N8#Â÷ãÂöF—cârrp¢&W7öç6Uöf÷&ÒÒbrrsÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ"7G–ÆSÒ&Ö&v–â×F÷£#î8*N898;>88Xø.XªY¹îzÙCÂöƒ#ãÇîxûîYÊ8îY¹îzÙNûÉ£Ç7â6Æ73Ò&&FvR#ç¶7W'&VçGÓÂ÷7ããÂ÷à¢ÇãÇ7G&öæsîY¹îzÙNiÉş™™ûÉ§¶FVFÆ–æUöÆ&VÇÓÂ÷7G&öæsãÂ÷ç¶f÷&×Ğ¢ÇãÇ6ÖÆÃîY¹îzÙNiÉş™™8î8~8şKÙ^[ªn8~8(.ZHi»N8~8Ş8î88.Zé®Y:X‹˜N[èÎ8ş8ŠŠŞZé®8^8(Î8n8N8(¾ZNY8¾8*Ş8:>8;>8+¾8:¾[è^888®8(®8î88#Â÷6ÖÆÃãÂ÷ãÂ÷6V7F–öãârrp¢7F—f—G’Ò" ¢&W÷'BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”WfVçE&W÷'B’çv†W&R„fÖ–Ç”WfVçE&W÷'Bæææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–B’¢–b&W÷'C ¢GFVæF–ærÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”WfVçE&W7öç6Ræ–B’çv†W&R„fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÀ¢fÖ–Ç”WfVçE&W7öç6RçW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç”WfVçE&W7öç6Rç7FGW2ÓÒ&GFVæF–ær"’¢†÷F÷2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”WfVçE&W÷'E†÷Fò’çv†W&R„fÖ–Ç”WfVçE&W÷'E†÷Fòç&W÷'Eö–BÓÒ&W÷'Bæ–B’æ÷&FW%ö'’„fÖ–Ç”WfVçE&W÷'E†÷Fòç†÷Fõö÷&FW"’’æÆÂ‚’–bGFVæF–ærVÇ6RµĞ¢vÆÆW'’Òrræ¦ö–â†bsÆ–Ör7&3Ò"öfÖ–Ç’öææ÷Væ6VÖVçG2÷&W÷'G2÷†÷F÷2÷·†÷Fòæ–GÒ"ÇCÒ.8*N898;>88XiyÉò"7G–ÆSÒ'v–GFƒ£S¶†V–v‡C£##ƒ¶ö&¦V7BÖf—C¦6öçF–ã¶&6¶w&÷VæC¢6cvVFVc¶&÷&FW"×&F—W3£'‚#ârf÷"†÷Fò–â†÷F÷2¢Æ–Ö—FVBÒsÇãÇ6ÖÆÃî™¸nYXiyÉş8ş8*N898;>88Xø.Xªˆ^™™Zé®8~XZÎ™h¾8~8n8N8î88#Â÷6ÖÆÃãÂ÷âr–bæ÷BGFVæF–ærVÇ6R" ¢7F—f—G’ÒbrrsÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ"7G–ÆSÒ&Ö&v–â×F÷£#î8*N898;>88kK¾X¹^ZY£Âöƒ#ãÆF—b7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R‡&W÷'Bæ&öG’—ÓÂöF—cç¶Æ–Ö—FVGÓÆF—b6Æ73Ò&w&–B#ç¶vÆÆW'—ÓÂöF—cãÂ÷6V7F–öãârrp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2#î8®yú^8(8¾KˆŠj~8h‹¾8(³Âöà¢Æƒç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBçF—FÆR—ÓÂöƒãÇãÇ7G&öæsç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷7G&öæsî8Ç6ÖÆÃç¶ææ÷Væ6VÖVçBæ7&VFVEöBæFFR‚’ç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—Şhë.‹È“Â÷6ÖÆÃãÂ÷à¢¶WfVçGÓÆF—b6Æ73Ò'FVæçB"7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBæ&öG’—ÓÂöF—cç¶7F—f—G—×·&W7öç6Uöf÷&×Òrrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶ææ÷Væ6VÖVçBçF—FÆWŞûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2÷&W÷'G2÷†÷F÷2÷·†÷Fõö–GÒ"¦FVbfÖ–Ç•öWfVçE÷&W÷'E÷†÷Fò‡†÷Fõö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒ6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç”WfVçE&W÷'E†÷FòÂfÖ–Ç”WfVçE&W÷'BÂfÖ–Ç”ææ÷Væ6VÖVçB¢æ¦ö–â„fÖ–Ç”WfVçE&W÷'BÂfÖ–Ç”WfVçE&W÷'Bæ–BÓÒfÖ–Ç”WfVçE&W÷'E†÷Fòç&W÷'Eö–B¢æ¦ö–â„fÖ–Ç”ææ÷Væ6VÖVçBÂfÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒfÖ–Ç”WfVçE&W÷'Bæææ÷Væ6VÖVçEö–B¢çv†W&R„fÖ–Ç”WfVçE&W÷'E†÷Fòæ–BÓÒ†÷Fõö–B’’æf—'7B‚¢–bæ÷B&V6÷&C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢†÷FòÂ&W÷'BÂææ÷Væ6VÖVçBÒ&V6÷&@¢ÆÆ÷vVBÒææ÷Væ6VÖVçBçFVæçEö–B–âfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ’æB6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”WfVçE&W7öç6Ræ–B’çv†W&R€¢fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÂfÖ–Ç”WfVçE&W7öç6RçW6W%ö–BÓÒW6W"æ–BÀ¢fÖ–Ç”WfVçE&W7öç6Rç7FGW2ÓÒ&GFVæF–ær"’¢–bæ÷BÆÆ÷vVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçC×†÷Fòç†÷FõöFFÂÖVF–÷G—S×†÷Fòç†÷Fõö6öçFVçE÷G—RÂ†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ç÷7B‚"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçEö–GÒ÷&W7öç6R"¦FVbfÖ–Ç•öWfVçE÷&W7öç6U÷6fR€¢ææ÷Væ6VÖVçEö–C¢–çBÂ&W7öç6U÷7FGW3¢7G"Òf÷&Ò‚âââ’Â'G•÷6—¦S¢–çBÒf÷&Òƒ’À¢Föuö–G3¢Æ—7E¶–çEÒÒf÷&Ò…µÒ’Âæ÷FS¢7G"Òf÷&Ò‚""’À¢W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’À¢“ ¢FVæçEö–G2ÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ¢ææ÷Væ6VÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R€¢fÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒææ÷Væ6VÖVçEö–BÂfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–Bæ–åò‡FVæçEö–G2’À¢fÖ–Ç”ææ÷Væ6VÖVçBæ7F—fRæ—5ò…G'VR’ÂfÖ–Ç”ææ÷Væ6VÖVçBæWfVçEöFFRæ—5öæ÷B„æöæR’À¢’’–bFVæçEö–G2VÇ6RæöæP¢–bæ÷Bææ÷Væ6VÖVçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.Y¹îzÙN8~8Ş8(¾8*N898;>888ÎŠh¾8N8¾8(®8î8¾8)2"¢FVFÆ–æRÒææ÷Væ6VÖVçBç&W7öç6UöFVFÆ–æR÷"†FFWF–ÖR€¢ææ÷Væ6VÖVçBæWfVçEöFFRç–V"Âææ÷Væ6VÖVçBæWfVçEöFFRæÖöçF‚Âææ÷Væ6VÖVçBæWfVçEöFFRæF’À¢’ÂÂG¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’À¢’ÒF–ÖVFVÇF†F—3Ó’¢–bæ÷BFVFÆ–æRçG¦–æfó ¢FVFÆ–æRÒFVFÆ–æRç&WÆ6R‡G¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’¢VÇ6S ¢FVFÆ–æRÒFVFÆ–æRæ7F–ÖW¦öæR…¦öæT–æfò‚$6–õFö·–ò"’¢–bFFWF–ÖRææ÷r…¦öæT–æfò‚$6–õFö·–ò"’’ãÒFVFÆ–æS ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.Y¹îzÙNiÉş™™8).˜î8î8n8N8î88.ZHi»N8Î[ø^Šh8®ZNY8şxªÎˆˆî8y»Nhê^8N˜
>{Z8ş88^8B"¢–b&W7öç6U÷7FGW2æ÷B–â²&GFVæF–ær"Â&Ö–&R"Â&FV6Æ–æVB'Ò÷"æ÷BÃÒ'G•÷6—¦RÃÒ#÷"ÆVâ†æ÷FRç7G&—‚’’âS ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Y¹îzÙNXh^Zë8).z+®Š¨Ş8~8n8ş88^8B"¢Föw2Ò6W76–öâç66Æ'2€¢6VÆV7B„För’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B¢çv†W&R„Föræ–Bæ–åò†Föuö–G2’ÂFöt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÀ¢Föt÷væW'6†—çFVæçEö–BÓÒææ÷Væ6VÖVçBçFVæçEö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’¢æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚’–bFöuö–G2VÇ6RµĞ¢&W7öç6RÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”WfVçE&W7öç6R’çv†W&R€¢fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÂfÖ–Ç”WfVçE&W7öç6RçW6W%ö–BÓÒW6W"æ–@¢’¢–bæ÷B&W7öç6S ¢&W7öç6RÒfÖ–Ç”WfVçE&W7öç6R†ææ÷Væ6VÖVçEö–CÖææ÷Væ6VÖVçBæ–BÂW6W%ö–C×W6W"æ–B¢6W76–öâæFB‡&W7öç6R¢f–æÅ÷7FGW2Ò&W7öç6U÷7FGW0¢–b&W7öç6U÷7FGW2ÓÒ&GFVæF–ær"æBææ÷Væ6VÖVçBæWfVçEö66—G“ ¢&W6W'fVBÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6öÆW66R†gVæ2ç7VÒ„fÖ–Ç”WfVçE&W7öç6Rç'G•÷6—¦R’Â’’çv†W&R€¢fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÂfÖ–Ç”WfVçE&W7öç6Rç7FGW2ÓÒ&GFVæF–ær"À¢fÖ–Ç”WfVçE&W7öç6RçW6W%ö–BÒW6W"æ–BÀ¢’’÷" ¢–b&W6W'fVB²'G•÷6—¦Râææ÷Væ6VÖVçBæWfVçEö66—G“ ¢–bææ÷Væ6VÖVçBçv—FÆ—7EöVæ&ÆVC ¢f–æÅ÷7FGW2Ò'v—FÆ—7FVB ¢VÇ6S ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Zé®Y:8¾˜N8~8n8N8(¾8ş8(Xø.XªXù~K¹8~8Ş8î8¾8)2"¢&W7öç6Rç7FGW2Òf–æÅ÷7FGW0¢&W7öç6Rç'G•÷6—¦RÒ'G•÷6—¦P¢&W7öç6RæFöuöæÖW2Ò.8"æ¦ö–â†Föræ6ÆÅöæÖRf÷"För–âFöw2’÷"æöæP¢&W7öç6Rææ÷FRÒæ÷FRç7G&—‚’÷"æöæP¢&W7öç6RçWFFVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæfÇW6‚‚¢&öÖ÷FVC¢Æ—7E´fÖ–Ç”WfVçE&W7öç6UÒÒµĞ¢–bææ÷Væ6VÖVçBæWfVçEö66—G’æBææ÷Væ6VÖVçBçv—FÆ—7EöVæ&ÆVC ¢GFVæF–æu÷F÷FÂÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6öÆW66R†gVæ2ç7VÒ„fÖ–Ç”WfVçE&W7öç6Rç'G•÷6—¦R’Â’’çv†W&R€¢fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÂfÖ–Ç”WfVçE&W7öç6Rç7FGW2ÓÒ&GFVæF–ær"À¢’’÷" ¢v—F–ærÒ6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”WfVçE&W7öç6R’çv†W&R€¢fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÂfÖ–Ç”WfVçE&W7öç6Rç7FGW2ÓÒ'v—FÆ—7FVB"À¢’æ÷&FW%ö'’„fÖ–Ç”WfVçE&W7öç6RçWFFVEöB’’æÆÂ‚¢f÷"v—F–æu÷&W7öç6R–âv—F–æs ¢–bGFVæF–æu÷F÷FÂ²v—F–æu÷&W7öç6Rç'G•÷6—¦RÃÒææ÷Væ6VÖVçBæWfVçEö66—G“ ¢v—F–æu÷&W7öç6Rç7FGW2Ò&GFVæF–ær ¢GFVæF–æu÷F÷FÂ³Òv—F–æu÷&W7öç6Rç'G•÷6—¦P¢&öÖ÷FVBæVæB‡v—F–æu÷&W7öç6R¢&W7öç6Uö÷væW"Ò6W76–öâævWB…W6W"ÂW6W"æ–B¢–b&W7öç6Uö÷væW"æBVÖ–Åöæ÷F–f–6F–öåöÆÆ÷vVB‡&W7öç6Uö÷væW"Â&ææ÷Væ6VÖVçG2"Â6W76–öâ“ ¢7FGW5öÆ&VÂÒ²&GFVæF–ær#¢.Xø.Xª"Â'v—FÆ—7FVB#¢.8*Ş8:>8;>8+¾8:¾[è^8"Â&Ö–&R#¢.jIÎŠˆîKŠÒ"Â&FV6Æ–æVB#¢.KˆŞXø.Xª'ÒævWB‡&W7öç6Rç7FGW2Â&W7öç6Rç7FGW2¢VWVUöVÖ–Â‡6W76–öâÂ&W7öç6Uö÷væW"æVÖ–ÂÂ&WfVçE÷&W7öç6R"Âb.8	U5E$TÄÄdÔ”Å8	¶ææ÷Væ6VÖVçBçF—FÆWŞ8îY¹îzÙN8).Xù~8K¹88î8~8ò"À¢b'·&W7öç6Uö÷væW"ææÖWÒjy…ÆåÆîY¹îzÙNûÉ§·7FGW5öÆ&VÇÕÆîXø.XªK«®i[ûÉ§·&W7öç6Rç'G•÷6—¦WŞYÕÆîhI¾xªÎûÉ§·&W7öç6RæFöuöæÖW2÷"~8®8rwÕÆåÆîY¹îzÙNiÉş™™8î8~8ôdÔ”Å8î8®yú^8(8¾yK¾™Ú.8¾8(ZHi»N8~8Ş8î88""À¢ææ÷Væ6VÖVçBçFVæçEö–BÂ&W7öç6Uö÷væW"æ–B¢f÷"&öÖ÷FVE÷&W7öç6R–â&öÖ÷FVC ¢&öÖ÷FVEö÷væW"Ò6W76–öâævWB…W6W"Â&öÖ÷FVE÷&W7öç6RçW6W%ö–B¢–b&öÖ÷FVEö÷væW"æBVÖ–Åöæ÷F–f–6F–öåöÆÆ÷vVB‡&öÖ÷FVEö÷væW"Â&ææ÷Væ6VÖVçG2"Â6W76–öâ“ ¢VWVUöVÖ–Â‡6W76–öâÂ&öÖ÷FVEö÷væW"æVÖ–ÂÂ&WfVçE÷&öÖ÷FVB"Âb.8	U5E$TÄÄdÔ”Å8	¶ææ÷Væ6VÖVçBçF—FÆWŞ8îXø.Xªiê8).8NyJhHş8~8Ş8î8~8ò"À¢b'·&öÖ÷FVEö÷væW"ææÖWÒjy…ÆåÆî8*Ş8:>8;>8+¾8:¾[è^88¾8(8ÎXø.Xª8Ş8{›8(®Kˆ®8Î8(®8î8~8ş8.Xø.XªK«®i[ûÉ§·&öÖ÷FVE÷&W7öç6Rç'G•÷6—¦WŞYÒ"À¢ææ÷Væ6VÖVçBçFVæçEö–BÂ&öÖ÷FVEö÷væW"æ–B¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçBæ–GÒ"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öææ÷Væ6VÖVçG5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢ææ÷Væ6VÖVçG2Ò6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–BÓÒFVæçBæ–B¢æ÷&FW%ö'’„fÖ–Ç”ææ÷Væ6VÖVçBæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ¢’æÆÂ‚¢&÷w2Ò" ¢f÷"ææ÷Væ6VÖVçB–âææ÷Væ6VÖVçG3 ¢7FFRÒ.XZÎ™h¾KŠÒ"–bææ÷Væ6VÖVçBæ7F—fRVÇ6R.hë.‹ÈXÎjÚ" ¢7F–öâÒ'7F÷"–bææ÷Væ6VÖVçBæ7F—fRVÇ6R'7F'B ¢7F–öåöÆ&VÂÒ.hë.‹È8).XÎjÚ""–bææ÷Væ6VÖVçBæ7F—fRVÇ6R.XhŞXZÎ™h² ¢WfVçBÒææ÷Væ6VÖVçBæWfVçEöFFRç7G&gF–ÖR‚"U’ÒVÒÒVB"’–bææ÷Væ6VÖVçBæWfVçEöFFRVÇ6R.ûÈÒ ¢&W7öç6W2Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç”WfVçE&W7öç6Ræ–B’’çv†W&R„fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–B’’–bææ÷Væ6VÖVçBæWfVçEöFFRVÇ6R ¢&W7öç6UöÆ–æ²ÒbsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçBæ–GÒ÷&W7öç6W2#îY¹îzÙB·&W7öç6W7ŞK»cÂöâr–bææ÷Væ6VÖVçBæWfVçEöFFRVÇ6R.ûÈÒ ¢&÷w2³ÒbrrsÇG#ãÇFCç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBçF—FÆR—ÓÂ÷FCãÇFCç¶WfVçGÓÂ÷FCãÇFCç·7FFWÓÂ÷FCãÇFCç¶ææ÷Væ6VÖVçBæ7&VFVEöBæFFR‚—ÓÂ÷FCãÇFCç·&W7öç6UöÆ–æ·ÓÂ÷FCà¢ÇFCãÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçBæ–GÒö7F–öâ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&7F–öâ"fÇVSÒ'¶7F–öçÒ#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#ç¶7F–öåöÆ&VÇÓÂö'WGFöããÂöf÷&ÓãÂ÷FCãÂ÷G#ârrp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öF6†&ö&B#î8888>8+~8:^89Î8;Î888h‹¾8(³ÂöãÆƒç¶‡FÖÂæW66R‡FVæçBææÖR—ÒdÔ”Å8®yú^8(8¾zêycÂöƒà¢Çî8>8îxªÎˆˆî8¾8(hI¾xªÎ8).‹øî88ş8*®8;Î88®8;Îjy888¾ŠzK®8^8(Î8î88#Â÷à¢Æf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃî8+ş8*N888:¾ûÈƒSih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÆ–çWBæÖSÒ'F—FÆR"Ö†ÆVæwFƒÒ#S"&WV—&VBÆ6V†öÆFW#Ò.Kè¾ûÉ¤U5E$TÄÄdÔ”ÅKÉ®™h¾X*Î8î8®yú^8(8²#à¢ÆÆ&VÃî™h¾X*Îiz^ûÈ8*N898;>888îZNYûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&WfVçEöFFR#à¢ÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃî™h¾Zx¾i˜.X‹³ÂöÆ&VÃãÆ–çWBG—SÒ'F–ÖR"æÖSÒ&WfVçE÷F–ÖR#ãÂöF—cãÆF—cãÆÆ&VÃîZé®Y:ûÈYŞûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&çVÖ&W""æÖSÒ&WfVçEö66—G’"Ö–ãÒ#"ÖƒÒ##ãÂöF—cãÂöF—cà¢ÆÆ&VÃî™h¾X*ÎZNh˜ÂöÆ&VÃãÆ–çWBæÖSÒ&WfVçEöÆö6F–öâ"Ö†ÆVæwFƒÒ#3"Æ6V†öÆFW#Ò.KÉ®ZNYŞ8;¾KØşh˜8®8’#à¢ÆÆ&VÃîY¹îzÙNiÉş™™ûÈiÊ®hÈ~Zé®8îZNY8ş™h¾X*Îiz^X˜Şiz^8îXØX˜Ói˜.ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&FFWF–ÖRÖÆö6Â"æÖSÒ'&W7öç6UöFVFÆ–æR#à¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'v—FÆ—7EöVæ&ÆVB"fÇVSÒ'G'VR#âZé®Y:X‹˜N[èÎ8ş8*Ş8:>8;>8+¾8:¾[è^88~Xù~8K¹88(³ÂöÆ&VÃà¢ÆÆ&VÃî8®yú^8(8¾Xh^ZëûÈƒ"Ãih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&&öG’"Ö†ÆVæwFƒÒ##"&WV—&VBÆ6V†öÆFW#Ò.iz^i˜.8KÉ®ZN8hÈ8xš8Xø.Xªikk9^8®88).8NjXh^8ş88^8N8"#ãÂ÷FW‡F&Và¢Æ'WGFöãî8®yú^8(8¾8).XZÎ™h¾88(³Âö'WGFöããÂöf÷&ÓãÆƒ#îhë.‹È[^jÛCÂöƒ#à¢ÇF&ÆSãÇG#ãÇFƒî8+ş8*N888:³Â÷FƒãÇFƒî™h¾X*ÎizSÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîhë.‹ÈizSÂ÷FƒãÇFƒîXø.XªY¹îzÙCÂ÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#b#î8®yú^8(8¾8ş8î88.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚$dÔ”Å8®yú^8(8¾zêyb"Â&öG’ÂW6W"  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçEö–GÒ÷&W7öç6W2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öWfVçE÷&W7öç6W5öÖævR†ææ÷Væ6VÖVçEö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢ææ÷Væ6VÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R€¢fÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒææ÷Væ6VÖVçEö–BÂfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–BÓÒFVæçBæ–BÀ¢fÖ–Ç”ææ÷Væ6VÖVçBæWfVçEöFFRæ—5öæ÷B„æöæR’À¢’¢–bæ÷Bææ÷Væ6VÖVçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.8*N898;>888ÎŠh¾8N8¾8(®8î8¾8)2"¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç”WfVçE&W7öç6RÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒfÖ–Ç”WfVçE&W7öç6RçW6W%ö–B¢çv†W&R„fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–B¢æ÷&FW%ö'’„fÖ–Ç”WfVçE&W7öç6Rç7FGW2ÂW6W"ææÖR¢’æÆÂ‚¢Æ&VÇ2Ò²&GFVæF–ær#¢.Xø.Xª"Â'v—FÆ—7FVB#¢.8*Ş8:>8;>8+¾8:¾[è^8"Â&Ö–&R#¢.jIÎŠˆîKŠÒ"Â&FV6Æ–æVB#¢.KˆŞXø.Xª'Ğ¢&÷w2Ò" ¢GFVæF–æu÷V÷ÆRÒ ¢f÷"&W7öç6RÂ÷væW"–â&V6÷&G3 ¢–b&W7öç6Rç7FGW2ÓÒ&GFVæF–ær# ¢GFVæF–æu÷V÷ÆR³Ò&W7öç6Rç'G•÷6—¦P¢&÷w2³ÒbrrsÇG#ãÇFCç¶‡FÖÂæW66R†÷væW"ææÖR—ÓÂ÷FCãÇFCç¶Æ&VÇ2ævWB‡&W7öç6Rç7FGW2Â&W7öç6Rç7FGW2—ÓÂ÷FCà¢ÇFCç·&W7öç6Rç'G•÷6—¦WŞYÓÂ÷FCãÇFCç¶‡FÖÂæW66R‡&W7öç6RæFöuöæÖW2÷".ûÈÒ"—ÓÂ÷FCãÇFB7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R‡&W7öç6Rææ÷FR÷".ûÈÒ"—ÓÂ÷FCà¢ÇFCç·&W7öç6RçWFFVEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—ÓÂ÷FCãÂ÷G#ârrp¢7VÖÖ'’Ò·7FGW3¢7VÒƒf÷"&W7öç6RÂò–â&V6÷&G2–b&W7öç6Rç7FGW2ÓÒ7FGW2’f÷"7FGW2–âÆ&VÇ7Ğ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR#î8®yú^8(8¾zêyn8h‹¾8(³ÂöãÆƒç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBçF—FÆR—ÒXø.XªY¹îzÙCÂöƒà¢Çî™h¾X*Îiz^ûÉ§¶ææ÷Væ6VÖVçBæWfVçEöFFRç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—ÓÂ÷ãÆF—b6Æ73Ò&w&–B#à¢ÆF—b6Æ73Ò&ÖöGVÆR#ãÆƒ3îXø.XªÂöƒ3ãÇãÇ7G&öæsç·7VÖÖ'•²vGFVæF–æru×Ş{XNûÈ÷¶GFVæF–æu÷V÷ÆWŞYÓÂ÷7G&öæsãÂ÷ãÂöF—cà¢ÆF—b6Æ73Ò&ÖöGVÆR#ãÆƒ3î8*Ş8:>8;>8+¾8:¾[è^8Âöƒ3ãÇãÇ7G&öæsç·7VÖÖ'•²wv—FÆ—7FVBu×Ş{XCÂ÷7G&öæsãÂ÷ãÂöF—cà¢ÆF—b6Æ73Ò&ÖöGVÆR#ãÆƒ3îjIÎŠˆîKŠÓÂöƒ3ãÇãÇ7G&öæsç·7VÖÖ'•²vÖ–&Ru×Ş{XCÂ÷7G&öæsãÂ÷ãÂöF—cà¢ÆF—b6Æ73Ò&ÖöGVÆR#ãÆƒ3îKˆŞXø.XªÂöƒ3ãÇãÇ7G&öæsç·7VÖÖ'•²vFV6Æ–æVBu×Ş{XCÂ÷7G&öæsãÂ÷ãÂöF—cãÂöF—cà¢ÇãÆ6Æ73Ò&'WGFöâ"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçBæ–GÒ÷&W÷'B#îkK¾X¹^ZY®8).KÙÎh‰ÂöâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçBæ–GÒ÷&W7öç6W2æ77b#ä55nX{®X©³ÂöâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçBæ–GÒ÷&W7öç6W2çFb#åDnX{®X©³ÂöãÂ÷à¢ÇF&ÆSãÇG#ãÇFƒî8*®8;Î88®8;ÃÂ÷FƒãÇFƒîY¹îzÙCÂ÷FƒãÇFƒîK«®i[Â÷FƒãÇFƒîhI¾xªÃÂ÷FƒãÇFƒî˜
>{ZK¨¾šSÂ÷FƒãÇFƒîi»Nikiz^i˜#Â÷FƒãÂ÷G#à¢·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#b#îY¹îzÙN8ş8î88.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚.8*N898;>88Xø.XªY¹îzÙB"Â&öG’ÂW6W"  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçEö–GÒ÷&W÷'B"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öWfVçE÷&W÷'EöÖævR†ææ÷Væ6VÖVçEö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢ææ÷Væ6VÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒææ÷Væ6VÖVçEö–BÀ¢fÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç”ææ÷Væ6VÖVçBæWfVçEöFFRæ—5öæ÷B„æöæR’’¢–bæ÷Bææ÷Væ6VÖVçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&W÷'BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”WfVçE&W÷'B’çv†W&R„fÖ–Ç”WfVçE&W÷'Bæææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–B’¢6÷VçBÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç”WfVçE&W÷'E†÷Fòæ–B’’çv†W&R„fÖ–Ç”WfVçE&W÷'E†÷Fòç&W÷'Eö–BÓÒ&W÷'Bæ–B’’–b&W÷'BVÇ6R ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçBæ–GÒ÷&W7öç6W2#îXø.XªY¹îzÙN8h‹¾8(³ÂöãÆƒî8*N898;>88kK¾X¹^ZY£ÂöƒãÇç¶‡FÖÂæW66R†ææ÷Væ6VÖVçBçF—FÆR—ÓÂ÷ãÆf÷&ÒÖWF†öCÒ'÷7B"Væ7G—SÒ&×VÇF—'Böf÷&ÒÖFF#ãÆÆ&VÃî™h¾X*ÎZY®ûÈƒ"Ãih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&&öG’"Ö†ÆVæwFƒÒ##"&WV—&VCç¶‡FÖÂæW66R‡&W÷'Bæ&öG’–b&W÷'BVÇ6Rrr—ÓÂ÷FW‡F&VãÆÆ&VÃîXø.Xªˆ^™™Zé®XiyÉşûÈiÈZJsié®8;¾YC„Ô.8î8~ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&f–ÆR"æÖSÒ'†÷F÷2"66WCÒ&–ÖvRö§VrÆ–ÖvR÷ærÆ–ÖvR÷vV'"×VÇF—ÆSãÇãÇ6ÖÆÃîxûîYÊ‚¶6÷VçB÷"Şié®8.ik8~8NXiyÉş8).˜h©î88(¾8iz.ZÙXiyÉş8).{Úî8Şhù¾88î88#Â÷6ÖÆÃãÂ÷ãÆ'WGFöãîkK¾X¹^ZY®8).XZÎ™h¾88(³Âö'WGFöããÂöf÷&Óârrp¢&WGW&âÆ–÷WB‚.8*N898;>88kK¾X¹^ZY¢"Â&öG’ÂW6W"  ¤ç÷7B‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçEö–GÒ÷&W÷'B"¦7–æ2FVbfÖ–Ç•öWfVçE÷&W÷'E÷6fR†ææ÷Væ6VÖVçEö–C¢–çBÂ&öG“¢7G"Òf÷&Ò‚âââ’Â†÷F÷3¢Æ—7EµWÆöDf–ÆUÒÒf–ÆR…µÒ’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢ææ÷Væ6VÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒææ÷Væ6VÖVçEö–BÀ¢fÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç”ææ÷Væ6VÖVçBæWfVçEöFFRæ—5öæ÷B„æöæR’’¢&öG’Ò&öG’ç7G&—‚¢–bæ÷Bææ÷Væ6VÖVçB÷"æ÷B&öG’÷"ÆVâ†&öG’’â#÷"ÆVâ…·f÷"–â†÷F÷2–bæf–ÆVæÖUÒ’â ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.kK¾X¹^ZY®8îXh^Zë8).z+®Š¨Ş8~8n8ş88^8B"¢&W÷'BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”WfVçE&W÷'B’çv†W&R„fÖ–Ç”WfVçE&W÷'Bæææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–B’¢–bæ÷B&W÷'C ¢&W÷'BÒfÖ–Ç”WfVçE&W÷'B†ææ÷Væ6VÖVçEö–CÖææ÷Væ6VÖVçBæ–BÂ&öG“Ö&öG’Â7&VFVEö'•ö–C×W6W"æ–B“²6W76–öâæFB‡&W÷'B“²6W76–öâæfÇW6‚‚¢&W÷'Bæ&öG’Â&W÷'BçWFFVEöBÒ&öG’ÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6VÆV7FVBÒ·f÷"–â†÷F÷2–bæf–ÆVæÖUĞ¢–b6VÆV7FVC ¢f÷"öÆB–â6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”WfVçE&W÷'E†÷Fò’çv†W&R„fÖ–Ç”WfVçE&W÷'E†÷Fòç&W÷'Eö–BÓÒ&W÷'Bæ–B’’æÆÂ‚“¢6W76–öâæFVÆWFR†öÆB¢f÷"÷6—F–öâÂ†÷Fò–âVçVÖW&FR‡6VÆV7FVB“ ¢6öçFVçBÒv—B†÷Fòç&VBƒ‚¢#B¢#B²¢–bæ÷B6öçFVçB÷"ÆVâ†6öçFVçB’â‚¢#B¢#C¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XiyÉş8óié£„Ô.Kº^Kˆ¾8¾8~8n8ş88^8B"¢G'“ ¢v—F‚–ÖvRæ÷Vâ†–òä'—FW4”ò†6öçFVçB’’26÷W&6S ¢–ÖvRÒ–ÖvT÷2æW†–e÷G&ç7÷6R‡6÷W&6R“²–ÖvRçF‡VÖ&æ–Â‚ƒƒÂƒ’Â–ÖvRå&W6×Æ–æräÄä5¤õ2“²–ÖvRÒ–ÖvRæ6öçfW'B‚%$t""“²÷WGWBÒ–òä'—FW4”ò‚“²–ÖvRç6fR†÷WGWBÂ$¥Tr"ÂVÆ—G“Óƒ‚Â÷F–Ö—¦SÕG'VR¢W†6WBW†6WF–öã¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XiyÉş[Ú.[Èş8).z+®Š¨Ş8~8n8ş88^8B"¢6W76–öâæFB„fÖ–Ç”WfVçE&W÷'E†÷Fò‡&W÷'Eö–C×&W÷'Bæ–BÂ†÷FõöFFÖ÷WGWBævWGfÇVR‚’Â†÷Fõö÷&FW#×÷6—F–öâ’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçBæ–GÒ÷&W÷'B"Â7FGW5ö6öFSÓ32  ¦FVbfÖ–Ç•öWfVçEöW‡÷'E÷&V6÷&G2†ææ÷Væ6VÖVçEö–C¢–çBÂFVæçEö–C¢–çBÂ6W76–öã¢6W76–öâ“ ¢ææ÷Væ6VÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R€¢fÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒææ÷Væ6VÖVçEö–BÂfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–BÓÒFVæçEö–BÀ¢fÖ–Ç”ææ÷Væ6VÖVçBæWfVçEöFFRæ—5öæ÷B„æöæR’’¢–bæ÷Bææ÷Væ6VÖVçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.8*N898;>888ÎŠh¾8N8¾8(®8î8¾8)2"¢&V6÷&G2Ò6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç”WfVçE&W7öç6RÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒfÖ–Ç”WfVçE&W7öç6RçW6W%ö–B¢çv†W&R„fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–B’æ÷&FW%ö'’„fÖ–Ç”WfVçE&W7öç6Rç7FGW2ÂW6W"ææÖR’’æÆÂ‚¢&WGW&âææ÷Væ6VÖVçBÂ&V6÷&G0  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçEö–GÒ÷&W7öç6W2æ77b"¦FVbfÖ–Ç•öWfVçE÷&W7öç6W5ö77b†ææ÷Væ6VÖVçEö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢ææ÷Væ6VÖVçBÂ&V6÷&G2ÒfÖ–Ç•öWfVçEöW‡÷'E÷&V6÷&G2†ææ÷Væ6VÖVçEö–BÂFVæçBæ–BÂ6W76–öâ¢Æ&VÇ2Ò²&GFVæF–ær#¢.Xø.Xª"Â'v—FÆ—7FVB#¢.8*Ş8:>8;>8+¾8:¾[è^8"Â&Ö–&R#¢.jIÎŠˆîKŠÒ"Â&FV6Æ–æVB#¢.KˆŞXø.Xª'Ğ¢÷WGWBÒ–òå7G&–æt”ò†æWvÆ–æSÒ""¢w&—FW"Ò77bçw&—FW"†÷WGWB¢w&—FW"çw&—FW&÷r…².8*®8;Î88®8;Â"Â.Y¹îzÙB"Â.K«®i["Â.hI¾xªÂ"Â.˜
>{ZK¨¾šR"Â.i»Nikiz^i˜"%Ò¢f÷"&W7öç6RÂ÷væW"–â&V6÷&G3 ¢w&—FW"çw&—FW&÷r…¶÷væW"ææÖRÂÆ&VÇ2ævWB‡&W7öç6Rç7FGW2Â&W7öç6Rç7FGW2’Â&W7öç6Rç'G•÷6—¦RÀ¢&W7öç6RæFöuöæÖW2÷"""Â&W7öç6Rææ÷FR÷"""Â&W7öç6RçWFFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"•Ò¢f–ÆVæÖRÒb&WfVçB×¶ææ÷Væ6VÖVçBæ–GÒ×'F–6—çG2æ77b ¢&WGW&â&W7öç6R†6öçFVçCÒ%ÇVfVfb"²÷WGWBævWGfÇVR‚’ÂÖVF–÷G—SÒ'FW‡Bö77c²6†'6WC×WFbÓ‚"À¢†VFW'3×²$6öçFVçBÔF—7÷6—F–öâ#¢bvGF6†ÖVçC²f–ÆVæÖSÒ'¶f–ÆVæÖWÒ"wÒ  ¤ævWB‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçEö–GÒ÷&W7öç6W2çFb"¦FVbfÖ–Ç•öWfVçE÷&W7öç6W5÷Fb†ææ÷Væ6VÖVçEö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢ææ÷Væ6VÖVçBÂ&V6÷&G2ÒfÖ–Ç•öWfVçEöW‡÷'E÷&V6÷&G2†ææ÷Væ6VÖVçEö–BÂFVæçBæ–BÂ6W76–öâ¢Æ&VÇ2Ò²&GFVæF–ær#¢.Xø.Xª"Â'v—FÆ—7FVB#¢.8*Ş8:>8;>8+¾8:¾[è^8"Â&Ö–&R#¢.jIÎŠˆîKŠÒ"Â&FV6Æ–æVB#¢.KˆŞXø.Xª'Ğ¢÷WGWBÒ–òä'—FW4”ò‚¢FfÖWG&–72ç&Vv—7FW$föçB…Væ–6öFT4”DföçB‚$†V—6V”¶·TvòÕsR"’¢FbÒ6çf2ä6çf2†÷WGWBÂvW6—¦SÖÆæG66R„B’¢v–GF‚Â†V–v‡BÒÆæG66R„B¢FVb†VFW"‚“ ¢Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"ÂR“²FbæG&u7G&–ærƒ3RÂ†V–v‡BÒ3RÂb'¶ææ÷Væ6VÖVçBçF—FÆWÒXø.Xªˆ^YŞ{ò"¢Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Â’“²FbæG&u7G&–ærƒ3RÂ†V–v‡BÒS"Âb.™h¾X*Îiz^ûÉ§¶ææ÷Væ6VÖVçBæWfVçEöFFRç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—Ş8X{®X©¾iz^ûÉ§¶FFRçFöF’‚’ç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRr—Ò"¢FbæG&u7G&–ærƒ3RÂ†V–v‡BÒs"Â.8*®8;Î88®8;Â"“²FbæG&u7G&–ærƒsRÂ†V–v‡BÒs"Â.Y¹îzÙB"“²FbæG&u7G&–ærƒ#sRÂ†V–v‡BÒs"Â.K«®i["“²FbæG&u7G&–ærƒ3#Â†V–v‡BÒs"Â.hI¾xªÂ"“²FbæG&u7G&–ærƒSÂ†V–v‡BÒs"Â.˜
>{ZK¨¾šR"¢†VFW"‚“²’Ò†V–v‡BÒ“ ¢f÷"&W7öç6RÂ÷væW"–â&V6÷&G3 ¢–b’Â3S ¢Fbç6†÷uvR‚“²†VFW"‚“²’Ò†V–v‡BÒ“ ¢fÇVW2Ò¶÷væW"ææÖU³£#%ÒÂÆ&VÇ2ævWB‡&W7öç6Rç7FGW2Â&W7öç6Rç7FGW2’Âb'·&W7öç6Rç'G•÷6—¦WŞYÒ"Â‡&W7öç6RæFöuöæÖW2÷".ûÈÒ"•³£#…ÒÂ‡&W7öç6Rææ÷FR÷".ûÈÒ"•³£CUÕĞ¢f÷"‚ÂfÇVR–â¦—…³3RÂsRÂ#sRÂ3#ÂSÒÂfÇVW2“ ¢FbæG&u7G&–ær‡‚Â’ÂfÇVR¢’ÓÒ€¢Fbç6fR‚¢&WGW&â&W7öç6R†6öçFVçCÖ÷WGWBævWGfÇVR‚’ÂÖVF–÷G—SÒ&Æ–6F–öâ÷Fb"À¢†VFW'3×²$6öçFVçBÔF—7÷6—F–öâ#¢bvGF6†ÖVçC²f–ÆVæÖSÒ&WfVçB×¶ææ÷Væ6VÖVçBæ–GÒ×'F–6—çG2çFb"wÒ  ¤ç÷7B‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR"¦FVbfÖ–Ç•öææ÷Væ6VÖVçEö7&VFR‡F—FÆS¢7G"Òf÷&Ò‚âââ’Â&öG“¢7G"Òf÷&Ò‚âââ’ÂWfVçEöFFS¢7G"Òf÷&Ò‚""’ÂWfVçE÷F–ÖS¢7G"Òf÷&Ò‚""’ÂWfVçEöÆö6F–öã¢7G"Òf÷&Ò‚""’ÂWfVçEö66—G“¢7G"Òf÷&Ò‚""’Â&W7öç6UöFVFÆ–æS¢7G"Òf÷&Ò‚""’Âv—FÆ—7EöVæ&ÆVC¢&ööÂÒf÷&Ò„fÇ6R’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢F—FÆRÂ&öG’ÒF—FÆRç7G&—‚’Â&öG’ç7G&—‚¢–bæ÷BF—FÆR÷"ÆVâ‡F—FÆR’âS÷"æ÷B&öG’÷"ÆVâ†&öG’’â# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8+ş8*N888:¾88®yú^8(8¾Xh^Zë8îih~ZÙ~i[8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢'6VEöWfVçEöFFRÒFFRæg&öÖ—6öf÷&ÖB†WfVçEöFFR’–bWfVçEöFFRVÇ6RæöæP¢–bWfVçE÷F–ÖRæBæ÷B&RægVÆÆÖF6‚‡""ƒó¥³ÕÆGÃ%³Ó5Ò“¥³ÓUÕÆB"ÂWfVçE÷F–ÖR“ ¢&—6RfÇVTW'&÷ ¢'6VEö66—G’Ò–çB†WfVçEö66—G’’–bWfVçEö66—G’VÇ6RæöæP¢–b'6VEö66—G’—2æ÷BæöæRæBæ÷BÃÒ'6VEö66—G’ÃÒ ¢&—6RfÇVTW'&÷ ¢'6VEöFVFÆ–æRÒFFWF–ÖRæg&öÖ—6öf÷&ÖB‡&W7öç6UöFVFÆ–æR’ç&WÆ6R‡G¦–æfóÕ¦öæT–æfò‚$6–õFö·–ò"’’–b&W7öç6UöFVFÆ–æRVÇ6RæöæP¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.™h¾X*Îiz^8;¾i˜.X‹¾8;¾Zé®Y:8;¾Y¹îzÙNiÉş™™8).z+®Š¨Ş8~8n8ş88^8B"¢–bæ÷B'6VEöWfVçEöFFRæBç’…¶WfVçE÷F–ÖRÂWfVçEöÆö6F–öâç7G&—‚’Â'6VEö66—G’Â'6VEöFVFÆ–æRÂv—FÆ—7EöVæ&ÆVEÒ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8*N898;>88h8^Z8).ŠŠŞZé®88(¾ZNY8ş™h¾X*Îiz^8Î[ø^Šh8~8’"¢ææ÷Væ6VÖVçBÒfÖ–Ç”ææ÷Væ6VÖVçB‡FVæçEö–C×FVæçBæ–BÂF—FÆS×F—FÆRÂ&öG“Ö&öG’ÂWfVçEöFFS×'6VEöWfVçEöFFRÀ¢WfVçE÷F–ÖSÖWfVçE÷F–ÖR÷"æöæRÂWfVçEöÆö6F–öãÖWfVçEöÆö6F–öâç7G&—‚•³£3Ò÷"æöæRÀ¢WfVçEö66—G“×'6VEö66—G’Â&W7öç6UöFVFÆ–æS×'6VEöFVFÆ–æRÀ¢v—FÆ—7EöVæ&ÆVC×v—FÆ—7EöVæ&ÆVBÂ7&VFVEö'•ö–C×W6W"æ–B¢6W76–öâæFB†ææ÷Væ6VÖVçB¢6W76–öâæfÇW6‚‚¢÷væW%ö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—çW6W%ö–B’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚’¢&6U÷W&ÂÒ÷2æVçf—&öâævWB‚$ô$4UõU$Â"Â&‡GG3¢òöFörÖÖævVÖVçBæ&VæVf—BÖæf’æ6öÒ"’ç'7G&—‚"ò"¢f÷"÷væW%ö–B–â÷væW%ö–G3 ¢÷væW"Ò6W76–öâævWB…W6W"Â÷væW%ö–B¢–b÷væW"æB÷væW"æ7F—fS ¢–bVÖ–Åöæ÷F–f–6F–öåöÆÆ÷vVB†÷væW"Â&ææ÷Væ6VÖVçG2"Â6W76–öâ“ ¢VWVUöVÖ–Â‡6W76–öâÂ÷væW"æVÖ–ÂÂ&ææ÷Væ6VÖVçB"Âb.8	·FVæçBææÖWŞ8	·F—FÆWÒ"À¢b'¶÷væW"ææÖWÒjy…ÆåÆç¶&öG•³£×ÕÆåÆîŠ›>8~8şŠh¾8(¾ûÉ§¶&6U÷W&ÇÒöfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçBæ–GÒ"À¢FVæçBæ–BÂ÷væW"æ–BÂb&ææ÷Væ6VÖVçC§¶ææ÷Væ6VÖVçBæ–GÓ§W6W#§¶÷væW"æ–GÒ"¢6VæE÷vV%÷W6‚†÷væW"æ–BÂ&ææ÷Væ6VÖVçG2"Âb'·FVæçBææÖWŞ8¾8(8î8®yú^8(8²"ÂF—FÆRÀ¢b"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçBæ–GÒ"Âb'W6ƒ¦ææ÷Væ6VÖVçC§¶ææ÷Væ6VÖVçBæ–GÓ§W6W#§¶÷væW"æ–GÒ"Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR÷¶ææ÷Væ6VÖVçEö–GÒö7F–öâ"¦FVbfÖ–Ç•öææ÷Væ6VÖVçEö7F–öâ†ææ÷Væ6VÖVçEö–C¢–çBÂ7F–öã¢7G"Òf÷&Ò‚âââ’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢ææ÷Væ6VÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçBæ–BÓÒææ÷Væ6VÖVçEö–BÂfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷Bææ÷Væ6VÖVçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.8®yú^8(8¾8ÎŠh¾8N8¾8(®8î8¾8)2"¢–b7F–öâÓÒ'7F÷# ¢ææ÷Væ6VÖVçBæ7F—fRÒfÇ6P¢VÆ–b7F–öâÓÒ'7F'B# ¢ææ÷Væ6VÖVçBæ7F—fRÒG'VP¢VÇ6S ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.i8ŞKÙÎ8).z+®Š¨Ş8~8n8ş88^8B"¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öææ÷Væ6VÖVçG2öÖævR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öFöuöFWF–Â†Föuö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒ6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFörÂFVæçB¢æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B¢æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æFöuö–BÓÒFöuö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’¢’æf—'7B‚¢–bæ÷B&V6÷&C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÂFVæçBÒ&V6÷&@¢6W‚Ò²&ÖÆR#¢.xš"Â&fVÖÆR#¢.x™Ò'ÒævWB†Förç6W‚ÂFörç6W‚¢&—'F‚ÒFöræ&—'F…öFFRç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"’–bFöræ&—'F…öFFRVÇ6R.iÊ®y›¾˜Ë" ¢7FGW5öÆ&VÂÒ²'&W6–FVçB#¢.YÊˆˆîKŠÒ"Â'&W6W'fVB#¢.K¨{HNkˆ‚"Â'6öÆB#¢.‹*Z;.kˆ‚"Â'G&ç6fW'&VB#¢.ŠÛ.kŠkˆ‚'ÒævWB†Förç7FGW2ÂFörç7FGW2¢&VÆF–öâÒ.K‹¾8*®8;Î88®8;Â"–b÷væW'6†—ç&VÆF–öç6†—ÓÒ'&–Ö'’"VÇ6R.8NZënixò ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöræ–B’¢6—&RÒ6W76–öâævWB„FörÂFörç6—&Uö–B’–bFörç6—&Uö–BVÇ6RæöæP¢FÒÒ6W76–öâævWB„FörÂFöræFÕö–B’–bFöræFÕö–BVÇ6RæöæP¢vRÒ.iÊ®y›¾˜Ë" ¢–bFöræ&—'F…öFFS ¢FöF’ÒFFRçFöF’‚¢ÖöçF‡2Ò‡FöF’ç–V"ÒFöræ&—'F…öFFRç–V"’¢"²FöF’æÖöçF‚ÒFöræ&—'F…öFFRæÖöçF‚Ò‡FöF’æF’ÂFöræ&—'F…öFFRæF’¢vRÒb'¶ÖöçF‡2òò'ŞjÛ7¶ÖöçF‡2R'Ş8¾iÈ‚"–bÖöçF‡2ãÒ"VÇ6Rb'¶Ö‚†ÖöçF‡2Â—Ş8¾iÈ‚ ¢†÷FòÒbsÆF—b6Æ73Ò&fÖ–Ç’×†÷Fò×7FvR#ãÆ–Ör6Æ73Ò&fÖ–Ç’ÖFör×†÷Fò"7&3Ò"öfÖ–Ç’öFöw2÷¶Föræ–GÒ÷†÷Fò"ÇCÒ'¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ò#ãÂöF—câr–b&öf–ÆRæB&öf–ÆRç†÷FõöFFVÇ6RsÆF—b6Æ73Ò'FVæçB"7G–ÆSÒ'FW‡BÖÆ–vã¦6VçFW#·FF–æs£SW‚#îhI¾xªÎ8îXiyÉş8ş8î8y›¾˜Ë.8^8(Î8n8N8î8¾8)>8#ÂöF—câp¢–çG&öGV7F–öâÒbsÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsî8*®8;Î88®8;Îjy8¾8(8î{KK¸³Â÷7G&öæsãÇ7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R‡&öf–ÆRæ–çG&öGV7F–öâ—ÓÂ÷ãÂöF—câr–b&öf–ÆRæB&öf–ÆRæ–çG&öGV7F–öâVÇ6Rrp¢Æ'VÕö—FV×2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒæFöuö–BÓÒFöræ–B’æ÷&FW%ö'’„fÖ–Ç”FötÆ'VÔ—FVÒçF¶VåööâæFW62‚’ÂfÖ–Ç”FötÆ'VÔ—FVÒæ7&VFVEöBæFW62‚’’’æÆÂ‚¢Æ'VÕö6&G2Ò" ¢Æ'VÕöw&÷W3¢6WE·7G%ÒÒ6WB‚¢f—6–&–Æ—G•öÆ&VÇ2Ò²'&—fFR#¢.™ÙîXZÎ™h²"Â'&VÆF—fW2#¢.Šj®h‰®xªÎ8î8r"Â&fÖ–Ç’#¢$dÔ”ÅXZKÙ2'Ğ¢f÷"—FVÒ–âÆ'VÕö—FV×3 ¢–b—FVÒç÷7Eöw&÷WæB—FVÒç÷7Eöw&÷W–âÆ'VÕöw&÷W3 ¢6öçF–çVP¢–b—FVÒç÷7Eöw&÷W ¢Æ'VÕöw&÷W2æFB†—FVÒç÷7Eöw&÷W¢–b—FVÒçf—6–&–Æ—G’ÓÒ'&—fFR"æB—FVÒçWÆöFVEö'•ö–BÒW6W"æ–C ¢6öçF–çVP¢F¶VâÒ—FVÒçF¶Våööâç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"’–b—FVÒçF¶VåööâVÇ6R.i*î[Ûiz^iÊ®ŠŠŞZé¢ ¢FVÆWFUö'WGFöâÒbsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒöÆ'VÒ÷¶—FVÒæ–GÒöFVÆWFR#ãÆ'WGFöâ6Æ73Ò&FævW"#îX˜®™šCÂö'WGFöããÂöf÷&Óâr–b—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–BVÇ6Rrp¢VF—Eöf÷&ÒÒbrrsÆFWF–Ç3ãÇ7VÖÖ'“îh©^z‹şXh^Zë8).{z™¸cÂ÷7VÖÖ'“ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒöÆ'VÒ÷¶—FVÒæ–GÒöVF—B#à¢ÆÆ&VÃîi*î[ÛizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'F¶Våööâ"fÇVSÒ'¶—FVÒçF¶Våööâæ—6öf÷&ÖB‚’–b—FVÒçF¶VåööâVÇ6RrwÒ#à¢ÆÆ&VÃî8+>8:8;>88ƒÂöÆ&VÃãÇFW‡F&VæÖSÒ&6F–öâ"Ö†ÆVæwFƒÒ#3#ç¶‡FÖÂæW66R†—FVÒæ6F–öâ÷"rr—ÓÂ÷FW‡F&Và¢ÆÆ&VÃîXZÎ™h¾zøNY»#ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'f—6–&–Æ—G’#ãÆ÷F–öâfÇVSÒ'&—fFR"²w6VÆV7FVBr–b—FVÒçf—6–&–Æ—G’ÓÒw&—fFRrVÇ6RrwÓî™ÙîXZÎ™h¾ûÈˆz®Xˆn88ûÈ“Âö÷F–öãà¢Æ÷F–öâfÇVSÒ'&VÆF—fW2"²w6VÆV7FVBr–b—FVÒçf—6–&–Æ—G’ÓÒw&VÆF—fW2rVÇ6RrwÓîŠj®h‰®xªÎ8î8*®8;Î88®8;Î8î8sÂö÷F–öããÆ÷F–öâfÇVSÒ&fÖ–Ç’"²w6VÆV7FVBr–b—FVÒçf—6–&–Æ—G’ÓÒvfÖ–Ç’rVÇ6RrwÓädÔ”ÅXZKÙ3Âö÷F–öããÂ÷6VÆV7Cà¢Æ'WGFöãîZHi»N8).KùŞZÙƒÂö'WGFöããÂöf÷&ÓãÂöFWF–Ç3ârrr–b—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–BVÇ6Rrp¢w&÷Wö6÷VçBÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç”FötÆ'VÔ—FVÒæ–B’’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒç÷7Eöw&÷WÓÒ—FVÒç÷7Eöw&÷W’’–b—FVÒç÷7Eöw&÷WVÇ6R¢Æ'VÕö6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò&Æ'VÒÖ—FVÒ#ãÆ‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒöÆ'VÒ÷¶—FVÒæ–GÒ÷†÷Fò"F&vWCÒ%ö&Ææ²#ãÆ–Ör7&3Ò"öfÖ–Ç’öFöw2÷¶Föræ–GÒöÆ'VÒ÷¶—FVÒæ–GÒ÷†÷Fò"ÇCÒ'¶‡FÖÂæW66R†—FVÒæ6F–öâ÷"Föræ6ÆÅöæÖR—Ò#ãÂöà¢ÆF—b6Æ73Ò&Æ'VÒÖÖWF#ãÇãÇ7G&öæsç·F¶VçÓÂ÷7G&öæsâÇ7â6Æ73Ò&&FvR#ç·f—6–&–Æ—G•öÆ&VÇ2ævWB†—FVÒçf—6–&–Æ—G’Â.™ÙîXZÎ™h²"—ÓÂ÷7ãâ²sÇ7â6Æ73Ò&&FvR#îXiyÉòr²7G"†w&÷Wö6÷VçB’²~ié£Â÷7ãâr–bw&÷Wö6÷VçBâVÇ6RrwÓÂ÷ãÇç¶‡FÖÂæW66R†—FVÒæ6F–öâ÷".8+>8:8;>888®8r"—ÓÂ÷ç¶VF—Eöf÷&××¶FVÆWFUö'WGFöçÓÂöF—cãÂö'F–6ÆSârrp¢Æ'VÕ÷6V7F–öâÒbrrsÆƒ#îh‰™[~8*.8:¾898:Âöƒ#ãÇîXiyÉş8).h«Î88ZJ~8Ş8şŠzK®8~8Ş8î88#Â÷ãÆF—b6Æ73Ò&Æ'VÒÖw&–B#ç¶Æ'VÕö6&G2÷"sÇîh‰™[~8*.8:¾898:8îXiyÉş8ş8î88.8(®8î8¾8)>8#Â÷âwÓÂöF—cà¢ÇãÆ6Æ73Ò&'WGFöâ7V66W72"‡&VcÒ"öfÖ–Ç’öw&÷wF‚öFB÷¶Föræ–GÒ#îûÈ²¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îh‰™[~Š‰˜Ë.8).‹ûŞXªÂöãÂ÷ârrp¢VF—Eöf÷&ÒÒbrrsÆƒ#îhI¾xªÎ89~8:Ş89^8*>8;Î8:¾XiyÉş8;¾{KK¸¾ihsÂöƒ#ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒ÷&öf–ÆR"Væ7G—SÒ&×VÇF—'Böf÷&ÒÖFF#à¢ÆÆ&VÃî8:8*N8;>XiyÉşûÈ„¥~8;µä~8;µvV%ûÈó„Ô.8î8~ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&f–ÆR"æÖSÒ'†÷Fò"66WCÒ&–ÖvRö§VrÆ–ÖvR÷ærÆ–ÖvR÷vV'#à¢ÆÆ&VÃîhI¾xªÎ8î{KK¸¾ûÈƒ3ih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&–çG&öGV7F–öâ"Ö†ÆVæwFƒÒ#3"Æ6V†öÆFW#Ò.h
~jÎ8(NZ[Ş8Ş8®8>88®88).8N{KK¸¾8ş88^8N8"#ç¶‡FÖÂæW66R‡&öf–ÆRæ–çG&öGV7F–öâ–b&öf–ÆRæB&öf–ÆRæ–çG&öGV7F–öâVÇ6Rrr—ÓÂ÷FW‡F&Và¢Æ'WGFöãîhI¾xªÎ89~8:Ş89^8*>8;Î8:¾8).KùŞZÙƒÂö'WGFöããÂöf÷&Óà¢¶bsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒ÷†÷FòöFVÆWFR#ãÆ'WGFöâ6Æ73Ò&FævW"#îXiyÉş8).X˜®™šCÂö'WGFöããÂöf÷&Óâr–b&öf–ÆRæB&öf–ÆRç†÷FõöFFVÇ6RrwÒrrr–b÷væW'6†—ç&VÆF–öç6†—ÓÒ'&–Ö'’"VÇ6RsÇãÇ6ÖÆÃîXiyÉş8{KK¸¾ih~8şK‹¾8*®8;Î88®8;Î8ÎZHi»N8~8Ş8î88#Â÷6ÖÆÃãÂ÷âp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³Âöà¢Æƒç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöƒãÇãÇ7â6Æ73Ò&&FvR#ç·&VÆF–öçÓÂ÷7ãâ·F—FÆUöÖ&·2†FörçF—FÆW2—ÓÂ÷à¢·†÷F÷×¶–çG&öGV7F–öçĞ¢ÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷7G&öæsî8¾8(X[iÈ8^8(Î8n8N8î88"Æ6Æ73Ò&'WGFöâ"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚#î8n88îZÙX^[«~zêycÂöãÂöF—cà¢ÇF&ÆSãÇG#ãÇFƒîŠ{[i»YÓÂ÷FƒãÇFCç¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".iÊ®y›¾˜Ë""—ÓÂ÷FCãÂ÷G#à¢ÇG#ãÇFƒîxªÎzŠãÂ÷FƒãÇFCç¶‡FÖÂæW66R†Föræ'&VVB÷".iÊ®y›¾˜Ë""—ÓÂ÷FCãÂ÷G#à¢ÇG#ãÇFƒîh
~XŠSÂ÷FƒãÇFCç¶‡FÖÂæW66R‡6W‚—ÓÂ÷FCãÂ÷G#ãÇG#ãÇFƒîyIş[›NiÈiz^8;¾[›N›Ú#Â÷FƒãÇFCç¶&—'F‡ŞûÈ‡¶vWŞûÈ“Â÷FCãÂ÷G#à¢ÇG#ãÇFƒîjù¾ˆ›#Â÷FƒãÇFCç¶‡FÖÂæW66R†Föræ6öÆ÷"÷".iÊ®y›¾˜Ë""—ÓÂ÷FCãÂ÷G#ãÇG#ãÇFƒîxûîYÊ8îx«nhX³Â÷FƒãÇFCç¶‡FÖÂæW66R‡7FGW5öÆ&VÂ—ÓÂ÷FCãÂ÷G#à¢ÇG#ãÇFƒîx‹nxªÃÂ÷FƒãÇFCç¶‡FÖÂæW66R‚‡6—&Rç&Vv—7FW&VEöæÖR÷"6—&Ræ6ÆÅöæÖR’–b6—&RVÇ6R.iÊ®y›¾˜Ë""—Ò·F—FÆUöÖ&·2‡6—&RçF—FÆW2’–b6—&RVÇ6RrwÓÂ÷FCãÂ÷G#à¢ÇG#ãÇFƒîjøŞxªÃÂ÷FƒãÇFCç¶‡FÖÂæW66R‚†FÒç&Vv—7FW&VEöæÖR÷"FÒæ6ÆÅöæÖR’–bFÒVÇ6R.iÊ®y›¾˜Ë""—Ò·F—FÆUöÖ&·2†FÒçF—FÆW2’–bFÒVÇ6RrwÓÂ÷FCãÂ÷G#ãÂ÷F&ÆSà¢¶Æ'VÕ÷6V7F–öç×¶VF—Eöf÷&×ÓÇî8>8îyK¾™Ú.8~8şxªÎˆˆî8îš~Zê.h8^Z8˜yšŞ889î8*N8*ş8:Ş8888>89~yZ®Xû~8®88î™ÙîXZÎ™h¾h8^Z8şŠzK®8~8î8¾8)>8#Â÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶Föræ6ÆÅöæÖWŞûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¦FVbfÖ–Ç•ö÷væVEöFör†Föuö–C¢–çBÂW6W#¢W6W"Â6W76–öã¢6W76–öâ“ ¢&WGW&â6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFör’æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æFöuö–BÓÒFöuö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’¢’æf—'7B‚  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚ö6ÆVæF""Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öFöuö†VÇF…ö6ÆVæF"†Föuö–C¢–çBÂÖöçFƒ¢7G"Ò""ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÒ÷væV@¢G'“ ¢6VÆV7FVBÒFFRæg&öÖ—6öf÷&ÖB†b'¶ÖöçF‡ÒÓ"’–bÖöçF‚VÇ6RFFRçFöF’‚’ç&WÆ6R†F“Ó¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.ŠzK®iÈ8).z+®Š¨Ş8~8n8ş88^8B"¢–bÖöçF‚æBæ÷B&RægVÆÆÖF6‚‡"%ÆG³GÒÕÆG³'Ò"ÂÖöçF‚“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.ŠzK®iÈ8).z+®Š¨Ş8~8n8ş88^8B" ¢f—'7EöF’Ò6VÆV7FVBç&WÆ6R†F“Ó¢æW‡EöÖöçF‚Ò†f—'7EöF’ç&WÆ6R†F“Ó#‚’²F–ÖVFVÇF†F—3ÓB’’ç&WÆ6R†F“Ó¢&Wf–÷W5öÖöçF‚Ò†f—'7EöF’ÒF–ÖVFVÇF†F—3Ó’’ç&WÆ6R†F“Ó¢ÖöçF…öVæBÒæW‡EöÖöçF‚ÒF–ÖVFVÇF†F—3Ó¢WfVçG3¢F–7E¶FFRÂÆ—7E·GWÆU·7G"Â7G"Â7G%ÕÕÒÒ·Ğ ¢FVbFEöWfVçB†WfVçEöFFS¢FFRÂæöæRÂ6FVv÷'“¢7G"ÂÆ&VÃ¢7G"ÂF—FÆS¢7G"“ ¢–bWfVçEöFFRæBf—'7EöF’ÃÒWfVçEöFFRÃÒÖöçF…öVæBæBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂFöræ–BÂ6FVv÷'’ÂF—FÆRÂWfVçEöFFRÂ6W76–öâ“ ¢WfVçG2ç6WFFVfVÇB†WfVçEöFFRÂµÒ’æVæB‚†6FVv÷'’ÂÆ&VÂÂF—FÆR’ ¢÷væW%÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R€¢÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöræ–BÂ÷væW$†VÇF…&V6÷&BçFVæçEö–BÓÒ÷væW'6†—çFVæçEö–BÀ¢÷væW$†VÇF…&V6÷&BææW‡EöGVUööâæ&WGvVVâ†f—'7EöF’ÂÖöçF…öVæB’À¢’’æÆÂ‚¢÷væW%öÆ&VÇ2Ò²'f66–æF–öâ#¢.8:ş8*ş888;2"Â&6†V6·W#¢.X^Š‹¢"Â&ÖVF–6F–öâ#¢.h©^‰jÂ"Â&F—6V6R#¢.XhŞŠ‹¢'Ğ¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢–b—FVÒæ6FVv÷'’–â÷væW%öÆ&VÇ2æBæ÷B†—FVÒæ6FVv÷'’ÓÒ&ÖVF–6F–öâ"æB—FVÒçfÇVRÓÒ.{X.K¨b"’æBæ÷B†—FVÒæ6FVv÷'’ÓÒ&F—6V6R"æB—FVÒçfÇVRÓÒ.ZèÎk+²"“ ¢FEöWfVçB†—FVÒææW‡EöGVUööâÂ—FVÒæ6FVv÷'’Â÷væW%öÆ&VÇ5¶—FVÒæ6FVv÷'•ÒÂ—FVÒçF—FÆR ¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R€¢†VÇF…&V6÷&E6†&RæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR¢’’æÆÂ‚¢6†&VEö–G3¢F–7E·7G"ÂÆ—7E¶–çEÕÒÒ·Ğ¢f÷"6†&R–â6†&W3 ¢6†&VEö–G2ç6WFFVfVÇB‡6†&Rç&V6÷&E÷G—RÂµÒ’æVæB‡6†&Rç&V6÷&Eö–B¢–b6†&VEö–G2ævWB‚'f66–æF–öâ"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B…f66–æF–öâ’çv†W&R…f66–æF–öâæ–Bæ–åò‡6†&VEö–G5²'f66–æF–öâ%Ò’Âf66–æF–öâæFöuö–BÓÒFöræ–BÂf66–æF–öâææW‡EöGVUööâæ&WGvVVâ†f—'7EöF’ÂÖöçF…öVæB’’’æÆÂ‚“ ¢FEöWfVçB†—FVÒææW‡EöGVUööâÂ'f66–æF–öâ"Â.8:ş8*ş888;2"Â—FVÒçf66–æUöæÖR¢–b6†&VEö–G2ævWB‚&†VÇF‚"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò‡6†&VEö–G5²&†VÇF‚%Ò’Â†VÇF…&V6÷&BæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&6†V6·W"Â†VÇF…&V6÷&BææW‡EöGVUööâæ&WGvVVâ†f—'7EöF’ÂÖöçF…öVæB’’’æÆÂ‚“ ¢FEöWfVçB†—FVÒææW‡EöGVUööâÂ&6†V6·W"Â.X^Š‹¢"Â.X^[«~Š‹®ijÒ"¢–b6†&VEö–G2ævWB‚&ÖVF–6F–öâ"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„ÖVF–6F–öâ’çv†W&R„ÖVF–6F–öâæ–Bæ–åò‡6†&VEö–G5²&ÖVF–6F–öâ%Ò’ÂÖVF–6F–öâæFöuö–BÓÒFöræ–BÂÖVF–6F–öâç7FGW2Ò&6ö×ÆWFVB"ÂÖVF–6F–öâææW‡EöGVUööâæ&WGvVVâ†f—'7EöF’ÂÖöçF…öVæB’’’æÆÂ‚“ ¢FEöWfVçB†—FVÒææW‡EöGVUööâÂ&ÖVF–6F–öâ"Â.h©^‰jÂ"Â—FVÒæÖVF–6–æUöæÖR¢–b6†&VEö–G2ævWB‚&F—6V6R"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„F—6V6T†—7F÷'’’çv†W&R„F—6V6T†—7F÷'’æ–Bæ–åò‡6†&VEö–G5²&F—6V6R%Ò’ÂF—6V6T†—7F÷'’æFöuö–BÓÒFöræ–BÂF—6V6T†—7F÷'’ç7FGW2Ò'&V6÷fW&VB"ÂF—6V6T†—7F÷'’ææW‡EöföÆÆ÷wWööâæ&WGvVVâ†f—'7EöF’ÂÖöçF…öVæB’’’æÆÂ‚“ ¢FEöWfVçB†—FVÒææW‡EöföÆÆ÷wWööâÂ&F—6V6R"Â.XhŞŠ‹¢"Â—FVÒæF—6V6UöæÖR ¢6öÆ÷'2Ò²'f66–æF–öâ#¢"6S–Cvc""Â&6†V6·W#¢"6C†V6c""Â&ÖVF–6F–öâ#¢"6cfS#‚"Â&F—6V6R#¢"6cF3–6'Ğ¢6VÆÇ2Ò" ¢f÷"vVV²–â6ÆVæF"ä6ÆVæF"†f—'7GvVV¶F“Ób’æÖöçF†FFW66ÆVæF"†f—'7EöF’ç–V"Âf—'7EöF’æÖöçF‚“ ¢6VÆÇ2³Ò#ÇG#â ¢f÷"F’–âvVV³ ¢÷WG6–FRÒF’æÖöçF‚Òf—'7EöF’æÖöçF€¢F•öWfVçG2Ò""æ¦ö–â€¢bsÆF—b7G–ÆSÒ&Ö&v–ã£G‚·FF–æs£G‚gƒ¶&÷&FW"×&F—W3£‡ƒ¶&6¶w&÷VæC§¶6öÆ÷'5¶6FVv÷'•×Ó¶6öÆ÷#¢36c3C3s¶föçB×6—¦S¢ãs‡&VÒ#ãÆ‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷¶6FVv÷'—Ò"7G–ÆSÒ&6öÆ÷#¢36c3C3s·FW‡BÖFV6÷&F–öã¦æöæR#ãÇ7G&öæsç¶Æ&VÇÓÂ÷7G&öæsâ¶‡FÖÂæW66R‡F—FÆR—ÓÂöãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFR"7G–ÆSÒ&Ö&v–ã£#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&6FVv÷'’"fÇVSÒ'¶6FVv÷'—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F—FÆR"fÇVSÒ'¶‡FÖÂæW66R‡F—FÆR—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&GVUööâ"fÇVSÒ'¶F—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'&WGW&åöÖöçF‚"fÇVSÒ'¶f—'7EöF“¢U’ÒV×Ò#ãÆ'WGFöâ6Æ73Ò'7V66W72"7G–ÆSÒ&Ö&v–ã£G‚·FF–æs£7‚gƒ¶föçB×6—¦S¢ãc‡&VÒ#îZéşikŞkˆ8ş8¾88(³Âö'WGFöããÂöf÷&ÓãÂöF—câp¢f÷"6FVv÷'’ÂÆ&VÂÂF—FÆR–âWfVçG2ævWB†F’ÂµÒ¢¢FöF•÷7G–ÆRÒ&÷WFÆ–æS£'‚6öÆ–B6#“†#–²"–bF’ÓÒFFRçFöF’‚’VÇ6R" ¢6VÆÇ2³ÒbsÇFB7G–ÆSÒ'fW'F–6ÂÖÆ–vã§F÷¶†V–v‡C£'ƒ¶Ö–â×v–GFƒ£ƒ·FF–æs£‡ƒ¶÷6—G“§²"ã3R"–b÷WG6–FRVÇ6R#'Ó··FöF•÷7G–ÆWÒ#ãÇ7G&öæsç¶F’æF—ÓÂ÷7G&öæsç¶F•öWfVçG7ÓÂ÷FCâp¢6VÆÇ2³Ò#Â÷G#â ¢WfVçEö6÷VçBÒ7VÒ†ÆVâ†—FV×2’f÷"—FV×2–âWfVçG2çfÇVW2‚’¢vVV¶F•öÆ&VÇ2Ò.iÈx¾kNiÊ˜yYÉşizR ¢Öö&–ÆUö6ÆVæF%ö—FV×2Ò""æ¦ö–â€¢brrsÆ'F–6ÆR6Æ73Ò&†VÇF‚ÖÖö&–ÆRÖ6&B#ãÆƒ3ç¶F’æÖöçF‡ŞiÈ‡¶F’æF—Şiz^ûÈ‡·vVV¶F•öÆ&VÇ5¶F’çvVV¶F’‚•×ŞûÈ“Âöƒ3ãÇãÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC§¶6öÆ÷'5¶6FVv÷'•×Ò#ç¶Æ&VÇÓÂ÷7ãâÆ‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷¶6FVv÷'—Ò#ç¶‡FÖÂæW66R‡F—FÆR—ÓÂöãÂ÷à¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFR#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&6FVv÷'’"fÇVSÒ'¶6FVv÷'—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F—FÆR"fÇVSÒ'¶‡FÖÂæW66R‡F—FÆR—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&GVUööâ"fÇVSÒ'¶F—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'&WGW&åöÖöçF‚"fÇVSÒ'¶f—'7EöF“¢U’ÒV×Ò#ãÆ'WGFöâ6Æ73Ò'7V66W72#îZéşikŞkˆ8ş8¾88(³Âö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrp¢f÷"F’–â6÷'FVB†WfVçG2’f÷"6FVv÷'’ÂÆ&VÂÂF—FÆR–âWfVçG5¶F•Ğ¢¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚#îX^[«~zêyn8h‹¾8(³Âöà¢Æƒç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îX^[«~8*¾8:Î8;>888;ÃÂöƒà¢ÆF—b6Æ73Ò&†VÇF‚ÖÖöçF‚Öæb"7G–ÆSÒ&F—7Æ“¦fÆWƒ¶Æ–vâÖ—FV×3¦6VçFW#¶§W7F–g’Ö6öçFVçC§76RÖ&WGvVVã¶v£'‚#ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ#öÖöçFƒ×·&Wf–÷W5öÖöçFƒ¢U’ÒV×Ò#î(iX˜ŞiÈƒÂöãÆƒ#ç¶f—'7EöF’ç–V'Ş[›G¶f—'7EöF’æÖöçF‡ŞiÈƒÂöƒ#ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ#öÖöçFƒ×¶æW‡EöÖöçFƒ¢U’ÒV×Ò#î{øÎiÈ‚(i#ÂöãÂöF—cà¢ÇãÇ7G&öæsç¶WfVçEö6÷VçGŞK»cÂ÷7G&öæsî8îX^[«~K¨Zé®8Î8.8(®8î88.K¨Zé®8).˜8n8YN8*¾88n8+N8:®8;Î8îzêynyK¾™Ú.8).™h¾8Ş8î88#Â÷à¢ÇãÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6S–Cvc"#î8:ş8*ş888;3Â÷7ãâÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6C†V6c"#îX^Š‹£Â÷7ãâÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6cfS#‚#îh©^‰jÃÂ÷7ãâÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6cF3–6#îXhŞŠ‹£Â÷7ããÂ÷à¢ÆF—b6Æ73Ò&†VÇF‚ÖFW6·F÷ÖöæÇ’"7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆR7G–ÆSÒ'F&ÆRÖÆ–÷WC¦f—†VC¶Ö–â×v–GFƒ£ƒ‚#ãÇG#ãÇF‚7G–ÆSÒ&6öÆ÷#¢6#SF#Sb#îizSÂ÷FƒãÇFƒîiÈƒÂ÷FƒãÇFƒîx³Â÷FƒãÇFƒîkCÂ÷FƒãÇFƒîiÊƒÂ÷FƒãÇFƒî˜yÂ÷FƒãÇF‚7G–ÆSÒ&6öÆ÷#¢3Cf#–"#îYÉóÂ÷FƒãÂ÷G#ç¶6VÆÇ7ÓÂ÷F&ÆSãÂöF—cà¢Ç6V7F–öâ6Æ73Ò&†VÇF‚ÖÖö&–ÆRÖöæÇ’"&–ÖÆ&VÃÒ.K¸®iÈ8îX^[«~K¨Zé¢#ç¶Öö&–ÆUö6ÆVæF%ö—FV×2÷"sÆF—b6Æ73Ò'FVæçB#îK¸®iÈ8îX^[«~K¨Zé®8ş8.8(®8î8¾8)>8#ÂöF—câwÓÂ÷6V7F–öãà¢ÇãÇ6ÖÆÃîŠzK®8^8(Î8(¾8î8ş88*®8;Î88®8;Î8Îy›¾˜Ë.8~8şK¨Zé®8889n8:®8;Î888;Î8¾8(X[iÈ8^8(Î8şK¨Zé®8î8ş8~88#Â÷6ÖÆÃãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶Föræ6ÆÅöæÖWŞ8îX^[«~8*¾8:Î8;>888;ÎûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFR"¦FVbfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFR†Föuö–C¢–çBÂ6FVv÷'“¢7G"Òf÷&Ò‚âââ’ÂF—FÆS¢7G"Òf÷&Ò‚âââ’ÂGVUööã¢7G"Òf÷&Ò‚âââ’Â&WGW&åöÖöçFƒ¢7G"Òf÷&Ò‚""’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂòÒ÷væV@¢–b6FVv÷'’æ÷B–â²'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R'Ò÷"æ÷BF—FÆRç7G&—‚’÷"ÆVâ‡F—FÆRç7G&—‚’’âS ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.X^[«~K¨Zé®8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢'6VEöGVRÒFFRæg&öÖ—6öf÷&ÖB†GVUööâ¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.X^[«~K¨Zé®8).z+®Š¨Ş8~8n8ş88^8B"¢fÆ–BÒ6W76–öâç66Æ"‡6VÆV7B„÷væW$†VÇF…&V6÷&Bæ–B’çv†W&R€¢÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöuö–BÂ÷væW$†VÇF…&V6÷&BçFVæçEö–BÓÒ÷væW'6†—çFVæçEö–BÀ¢÷væW$†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ6FVv÷'’Â÷væW$†VÇF…&V6÷&BçF—FÆRÓÒF—FÆRç7G&—‚’Â÷væW$†VÇF…&V6÷&BææW‡EöGVUööâÓÒ'6VEöGVRÀ¢’’—2æ÷BæöæP¢&V6÷&E÷G—W2Ò²'f66–æF–öâ#¢'f66–æF–öâ"Â&6†V6·W#¢&†VÇF‚"Â&ÖVF–6F–öâ#¢&ÖVF–6F–öâ"Â&F—6V6R#¢&F—6V6R'Ğ¢6†&VEö–G2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&Rç&V6÷&Eö–B’çv†W&R€¢†VÇF…&V6÷&E6†&RæFöuö–BÓÒFöuö–BÂ†VÇF…&V6÷&E6†&Rç&V6÷&E÷G—RÓÒ&V6÷&E÷G—W5¶6FVv÷'•ÒÂ†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR¢’’æÆÂ‚¢–bæ÷BfÆ–BæB6†&VEö–G3 ¢–b6FVv÷'’ÓÒ'f66–æF–öâ# ¢fÆ–BÒ6W76–öâç66Æ"‡6VÆV7B…f66–æF–öâæ–B’çv†W&R…f66–æF–öâæ–Bæ–åò‡6†&VEö–G2’Âf66–æF–öâæFöuö–BÓÒFöuö–BÂf66–æF–öâçf66–æUöæÖRÓÒF—FÆRç7G&—‚’Âf66–æF–öâææW‡EöGVUööâÓÒ'6VEöGVR’’—2æ÷BæöæP¢VÆ–b6FVv÷'’ÓÒ&6†V6·W# ¢fÆ–BÒF—FÆRç7G&—‚’ÓÒ.X^[«~Š‹®ijÒ"æB6W76–öâç66Æ"‡6VÆV7B„†VÇF…&V6÷&Bæ–B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò‡6†&VEö–G2’Â†VÇF…&V6÷&BæFöuö–BÓÒFöuö–BÂ†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&6†V6·W"Â†VÇF…&V6÷&BææW‡EöGVUööâÓÒ'6VEöGVR’’—2æ÷BæöæP¢VÆ–b6FVv÷'’ÓÒ&ÖVF–6F–öâ# ¢fÆ–BÒ6W76–öâç66Æ"‡6VÆV7B„ÖVF–6F–öâæ–B’çv†W&R„ÖVF–6F–öâæ–Bæ–åò‡6†&VEö–G2’ÂÖVF–6F–öâæFöuö–BÓÒFöuö–BÂÖVF–6F–öâæÖVF–6–æUöæÖRÓÒF—FÆRç7G&—‚’ÂÖVF–6F–öâææW‡EöGVUööâÓÒ'6VEöGVRÂÖVF–6F–öâç7FGW2Ò&6ö×ÆWFVB"’’—2æ÷BæöæP¢VÇ6S ¢fÆ–BÒ6W76–öâç66Æ"‡6VÆV7B„F—6V6T†—7F÷'’æ–B’çv†W&R„F—6V6T†—7F÷'’æ–Bæ–åò‡6†&VEö–G2’ÂF—6V6T†—7F÷'’æFöuö–BÓÒFöuö–BÂF—6V6T†—7F÷'’æF—6V6UöæÖRÓÒF—FÆRç7G&—‚’ÂF—6V6T†—7F÷'’ææW‡EöföÆÆ÷wWööâÓÒ'6VEöGVRÂF—6V6T†—7F÷'’ç7FGW2Ò'&V6÷fW&VB"’’—2æ÷BæöæP¢–bæ÷BfÆ–C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.ZèÎK¨n8~8Ş8(¾X^[«~K¨Zé®8ÎŠh¾8N8¾8(®8î8¾8)2"¢6W76–öâæFB„fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâ‡W6W%ö–C×W6W"æ–BÂFöuö–CÖFöuö–BÂ6FVv÷'“Ö6FVv÷'’ÂF—FÆS×F—FÆRç7G&—‚’ÂGVUööã×'6VEöGVR’¢6W76–öâæ6öÖÖ—B‚¢ÖöçF…÷VW'’Òb#öÖöçFƒ×·&WGW&åöÖöçF‡Ò"–b&RægVÆÆÖF6‚‡"%ÆG³GÒÕÆG³'Ò"Â&WGW&åöÖöçF‚’VÇ6R" ¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚ö6ÆVæF'¶ÖöçF…÷VW'—Ò"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFVB"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWF–öåö†—7F÷'’†Föuö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢òÂFörÒ÷væV@¢6ö×ÆWF–öç2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâ’çv†W&R€¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâçW6W%ö–BÓÒW6W"æ–BÀ¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæFöuö–BÓÒFöræ–BÀ¢’æ÷&FW%ö'’„fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæ6ö×ÆWFVEöBæFW62‚’ÂfÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæ–BæFW62‚’’’æÆÂ‚¢Æ&VÇ2Ò²'f66–æF–öâ#¢.8:ş8*ş888;2"Â&6†V6·W#¢.X^Š‹¢"Â&ÖVF–6F–öâ#¢.h©^‰jÂ"Â&F—6V6R#¢.XhŞŠ‹¢'Ğ¢&÷w2Ò" ¢Öö&–ÆUö6&G2Ò" ¢f÷"—FVÒ–â6ö×ÆWF–öç3 ¢6ö×ÆWFVEöBÒ—FVÒæ6ö×ÆWFVEö@¢–b6ö×ÆWFVEöBçG¦–æfó ¢6ö×ÆWFVEöBÒ6ö×ÆWFVEöBæ7F–ÖW¦öæR…¦öæT–æfò‚$6–õFö·–ò"’¢&÷w2³ÒbrrsÇG#ãÇFCç¶—FVÒæGVUööçÓÂ÷FCãÇFCç¶Æ&VÇ2ævWB†—FVÒæ6FVv÷'’Â.X^[«~K¨Zé¢"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒçF—FÆR—ÓÂ÷FCãÇFCç¶6ö×ÆWFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷FCãÇFCãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFVB÷¶—FVÒæ–GÒ÷VæFò#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWBG—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&Õ÷VæFò"fÇVSÒ'G'VR"7G–ÆSÒ'v–GFƒ¦WFò"&WV—&VCâXùn8(®kh8~8).z+®Š¨ÓÂöÆ&VÃãÆ'WGFöâ6Æ73Ò'6V6öæF'’"7G–ÆSÒ&Ö&v–ã£G‚#îiÊ®ZèÎK¨n8¾h‹¾8“Âö'WGFöããÂöf÷&ÓãÂ÷FCãÂ÷G#ârrp¢Öö&–ÆUö6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò&†VÇF‚ÖÖö&–ÆRÖ6&B#ãÆƒ3ç¶Æ&VÇ2ævWB†—FVÒæ6FVv÷'’Â.X^[«~K¨Zé¢"—ŞûÉ§¶‡FÖÂæW66R†—FVÒçF—FÆR—ÓÂöƒ3ãÇîK¨Zé®iz^ûÉ§¶—FVÒæGVUööçÓÂ÷ãÇîZèÎK¨ni8ŞKÙÎûÉ§¶6ö×ÆWFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFVB÷¶—FVÒæ–GÒ÷VæFò#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWBG—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&Õ÷VæFò"fÇVSÒ'G'VR"7G–ÆSÒ'v–GFƒ¦WFò"&WV—&VCâXùn8(®kh8~8).z+®Š¨ÓÂöÆ&VÃãÆ'WGFöâ6Æ73Ò'6V6öæF'’#îiÊ®ZèÎK¨n8¾h‹¾8“Âö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚#îX^[«~zêyn8h‹¾8(³Âöà¢Æƒç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îZéşikŞkˆ8şX^[«~K¨Zé£Âöƒà¢ÇîZéşikŞkˆ8ş8¾8~8şX^[«~K¨Zé®8).ik8~8Nšn8¾ŠzK®8~8î88.Xùn8(®kh888Zûî‹iÉş™i>8î˜	®yú^8;¾X^[«~8888>89~8;¾8*¾8:Î8;>888;Î8XhŞŠzK®8^8(Î8î88#Â÷à¢ÆF—b6Æ73Ò&†VÇF‚ÖFW6·F÷ÖöæÇ’"7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆSãÇG#ãÇFƒîK¨Zé®izSÂ÷FƒãÇFƒîzŠîšãÂ÷FƒãÇFƒîXh^Zë“Â÷FƒãÇFƒîZèÎK¨ni8ŞKÙÎiz^i˜#Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#R#îZéşikŞkˆ8ş8îX^[«~K¨Zé®8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSãÂöF—cãÇ6V7F–öâ6Æ73Ò&†VÇF‚ÖÖö&–ÆRÖöæÇ’#ç¶Öö&–ÆUö6&G2÷"sÆF—b6Æ73Ò'FVæçB#îZéşikŞkˆ8ş8îX^[«~K¨Zé®8ş8.8(®8î8¾8)>8#ÂöF—câwÓÂ÷6V7F–öãârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶Föræ6ÆÅöæÖWŞ8îZéşikŞkˆ8şX^[«~K¨Zé®ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFVB÷¶6ö×ÆWF–öåö–GÒ÷VæFò"¦FVbfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWF–öå÷VæFò†Föuö–C¢–çBÂ6ö×ÆWF–öåö–C¢–çBÂ6öæf—&Õ÷VæFó¢&ööÂÒf÷&Ò„fÇ6R’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢–bæ÷B6öæf—&Õ÷VæFó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Xùn8(®kh8~8îz+®Š¨Ş8Î[ø^Šh8~8’"¢6ö×ÆWF–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâ’çv†W&R€¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæ–BÓÒ6ö×ÆWF–öåö–BÀ¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâçW6W%ö–BÓÒW6W"æ–BÀ¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæFöuö–BÓÒFöuö–BÀ¢’¢–bæ÷B6ö×ÆWF–öã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.ZéşikŞkˆ8ş8îX^[«~K¨Zé®8ÎŠh¾8N8¾8(®8î8¾8)2"¢6W76–öâæFVÆWFR†6ö×ÆWF–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFVB"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öFöuö†VÇF‚†Föuö–C¢–çBÂ†VÇF…ö6FVv÷'“¢7G"Ò""ÂFFUög&öÓ¢7G"Ò""ÂFFU÷Fó¢7G"Ò""Â¶W—v÷&C¢7G"Ò""ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÒ÷væV@¢FVæçBÒ6W76–öâævWB…FVæçBÂ÷væW'6†—çFVæçEö–B¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R€¢†VÇF…&V6÷&E6†&RæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR¢’’æÆÂ‚¢6†&VEö–G3¢F–7E·7G"ÂÆ—7E¶–çEÕÒÒ·Ğ¢f÷"6†&R–â6†&W3 ¢6†&VEö–G2ç6WFFVfVÇB‡6†&Rç&V6÷&E÷G—RÂµÒ’æVæB‡6†&Rç&V6÷&Eö–B ¢÷væW%÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R€¢÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöræ–BÂ÷væW$†VÇF…&V6÷&BçFVæçEö–BÓÒ÷væW'6†—çFVæçEö–@¢’æ÷&FW%ö'’„÷væW$†VÇF…&V6÷&Bç&V6÷&FVEööâæFW62‚’Â÷væW$†VÇF…&V6÷&Bæ–BæFW62‚’’’æÆÂ‚¢÷væW%ö6FVv÷'•öÆ&VÇ2Ò²'vV–v‡B#¢.KÙ>˜xÒ"Â'f66–æF–öâ#¢.8:ş8*ş888;2"Â&6†V6·W#¢.X^Š‹¢"Â&ÖVF–6F–öâ#¢.h©^‰jÂ"Â&F—6V6R#¢.yx^jÛB"Â&fööB#¢.89^8;Î88’"Â&÷F†W"#¢.8Ş8îK¹b'Ğ¢6FVv÷'•ö6÷VçG2Ò¶¶W“¢7VÒƒf÷"—FVÒ–â÷væW%÷&V6÷&G2–b—FVÒæ6FVv÷'’ÓÒ¶W’’f÷"¶W’–â÷væW%ö6FVv÷'•öÆ&VÇ7Ğ¢6FVv÷'•ö6÷VçG5²'f66–æF–öâ%Ò³ÒÆVâ‡6†&VEö–G2ævWB‚'f66–æF–öâ"ÂµÒ’“²6FVv÷'•ö6÷VçG5²&ÖVF–6F–öâ%Ò³ÒÆVâ‡6†&VEö–G2ævWB‚&ÖVF–6F–öâ"ÂµÒ’“²6FVv÷'•ö6÷VçG5²&F—6V6R%Ò³ÒÆVâ‡6†&VEö–G2ævWB‚&F—6V6R"ÂµÒ’“²6FVv÷'•ö6÷VçG5²&fööB%Ò³ÒÆVâ‡6†&VEö–G2ævWB‚&fööB"ÂµÒ’ ¢VçG&–W3¢Æ—7E·GWÆU¶FFRÂ7G"Â7G"Â7G%ÕÒÒµĞ¢6†&VEö6†V6·Wöf–ÆW2Ò" ¢–b6†&VEö–G2ævWB‚&†VÇF‚"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R€¢†VÇF…&V6÷&Bæ–Bæ–åò‡6†&VEö–G5²&†VÇF‚%Ò’Â†VÇF…&V6÷&BæFöuö–BÓÒFöræ–@¢’’æÆÂ‚“ ¢Æ&VÂÒ²'vV–v‡B#¢.KÙ>˜xÒ"Â&6†V6·W#¢.X^[«~Š‹®ijÒ"Â'G&VFÖVçB#¢.Š‹®y˜"'ÒævWB†—FVÒæ6FVv÷'’Â.X^[«~Š‰˜Ë""¢–b—FVÒæ6FVv÷'’–â²'vV–v‡B"Â&6†V6·W'Ó¢6FVv÷'•ö6÷VçG5¶—FVÒæ6FVv÷'•Ò³Ò¢FWF–Å÷'G2Ò¶b'¶—FVÒçvV–v‡Eö¶wÒ¶r%Ò–b—FVÒçvV–v‡Eö¶r—2æ÷BæöæRVÇ6RµĞ¢–b—FVÒæ6FVv÷'’ÓÒ&6†V6·W# ¢FW7EöÆ&VÇ2Ò¶æÖRf÷"Væ&ÆVBÂæÖR–â²†—FVÒç‡—6–6ÅöW†ÒÂ.ŠznŠ‹¢"’Â†—FVÒæ&ÆööE÷FW7BÂ.Škk.jIÎiû²"’Â†—FVÒçVÇG&6÷VæBÂ.8*8+>8;Â"’Â†—FVÒæ6†W7E÷‡&’Â.ˆ;˜:…{y¢"•Ò–bVæ&ÆVEĞ¢&W7VÇEöÆ&VÇ2Ò²&æ÷&ÖÂ#¢.y[[‹8®8r"Â&föÆÆ÷wW#¢.{XÎ˜îŠk>Zùò"Â'&V6†V6²#¢.XhŞjIÎiû²"Â'G&VFÖVçB#¢.k+¾y˜.8;¾Xù~Š‹®8Î[ø^Šh'Ğ¢FWF–Å÷'G2æW‡FVæB‡FW7EöÆ&VÇ2¢–b—FVÒç&W7VÇE÷7VÖÖ'“¢FWF–Å÷'G2æVæB‡&W7VÇEöÆ&VÇ2ævWB†—FVÒç&W7VÇE÷7VÖÖ'’Â—FVÒç&W7VÇE÷7VÖÖ'’’¢–b—FVÒæGF6†ÖVçEöFF¢6†&VEö6†V6·Wöf–ÆW2³ÒbsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö6†V6·W2÷¶—FVÒæ–GÒöGF6†ÖVçB"F&vWCÒ%ö&Ææ²#ç¶—FVÒç&V6÷&EöFFWÒX^Š‹®{YiéÃÂöâp¢–b—FVÒæÖVÅöÖ÷VçEör—2æ÷BæöæS ¢FWF–Å÷'G2æVæB†b.š9şK¨²¶—FVÒæÖVÅöÖ÷VçEös¦wÖr"¢–b—FVÒæfööEöæÖS ¢FWF–Å÷'G2æVæB†b.89^8;Î88ûÉ§¶—FVÒæfööEöæÖWÒ"¢–b—FVÒç7FööÅö6öæF—F–öã ¢FWF–Å÷'G2æVæB†b.8n8)>8ûÉ§¶—FVÒç7FööÅö6öæF—F–öçÒ"¢–b—FVÒæ†VÇF…ö6öæF—F–öã ¢FWF–Å÷'G2æVæB†b.X^[«~ûÉ§¶—FVÒæ†VÇF…ö6öæF—F–öçÒ"¢FWF–ÂÒ"ûÈò"æ¦ö–â†FWF–Å÷'G2’÷"†—FVÒææ÷FW2÷".Š‰˜Ë.8.8(¢"¢VçG&–W2æVæB‚†—FVÒç&V6÷&EöFFRÂÆ&VÂÂFWF–ÂÂ—FVÒææ÷FW2÷"""’¢6†&VEö6W'F–f–6FW2Ò" ¢–b6†&VEö–G2ævWB‚'f66–æF–öâ"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B…f66–æF–öâ’çv†W&R€¢f66–æF–öâæ–Bæ–åò‡6†&VEö–G5²'f66–æF–öâ%Ò’Âf66–æF–öâæFöuö–BÓÒFöræ–@¢’’æÆÂ‚“ ¢F÷6U÷FW‡BÒ.‹ûŞXªhê^zŠâ"–b—FVÒæF÷6UöçVÖ&W"æB—FVÒæF÷6UöçVÖ&W"ãÒBVÇ6R†b'¶—FVÒæF÷6UöçVÖ&W'ŞY¹îyºâ"–b—FVÒæF÷6UöçVÖ&W"VÇ6R""¢FWF–ÂÒ—FVÒçf66–æUöæÖR²†b.ûÈ‡¶F÷6U÷FW‡GŞûÈ’"–bF÷6U÷FW‡BVÇ6R""¢æ÷FU÷'G2Ò¶b.jÊY¹îK¨Zé®ûÉ§¶—FVÒææW‡EöGVUööçÒ"–b—FVÒææW‡EöGVUööâVÇ6R""Âb.X¹^xšyx^™š.ûÉ§¶—FVÒæ6Æ–æ–7Ò"–b—FVÒæ6Æ–æ–2VÇ6R""Â—FVÒææ÷FW2÷""%Ğ¢VçG&–W2æVæB‚†—FVÒæFÖ–æ—7FW&VEööâÂ.8:ş8*ş888;2"ÂFWF–ÂÂ"ûÈò"æ¦ö–â‡'Bf÷"'B–âæ÷FU÷'G2–b'B’’¢–b—FVÒæ6W'F–f–6FUöFF ¢6†&VEö6W'F–f–6FW2³ÒbsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒ÷f66–æF–öç2÷¶—FVÒæ–GÒö6W'F–f–6FR"F&vWCÒ%ö&Ææ²#ç¶—FVÒæFÖ–æ—7FW&VEööçÒ¶‡FÖÂæW66R†—FVÒçf66–æUöæÖR—Ş8îŠ‹Îiˆîi»ƒÂöâp¢–b6†&VEö–G2ævWB‚&ÖVF–6F–öâ"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„ÖVF–6F–öâ’çv†W&R€¢ÖVF–6F–öâæ–Bæ–åò‡6†&VEö–G5²&ÖVF–6F–öâ%Ò’ÂÖVF–6F–öâæFöuö–BÓÒFöræ–@¢’’æÆÂ‚“ ¢FWF–Ç2Ò¶—FVÒæÖVF–6–æUöæÖUĞ¢–b—FVÒæF÷6vS¢FWF–Ç2æVæB†b#Y¹î˜xşûÉ§¶—FVÒæF÷6vWÒ"¢–b—FVÒæg&WVVæ7“¢FWF–Ç2æVæB†b.š¾[ªnûÉ§¶—FVÒæg&WVVæ7—Ò"¢VçG&–W2æVæB‚†—FVÒæFÖ–æ—7FW&VEööâÂ.h©^‰jÂ"Â"ûÈò"æ¦ö–â†FWF–Ç2’Â—FVÒæ÷væW%öæ÷FW2÷"""’¢–b6†&VEö–G2ævWB‚&F—6V6R"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„F—6V6T†—7F÷'’’çv†W&R€¢F—6V6T†—7F÷'’æ–Bæ–åò‡6†&VEö–G5²&F—6V6R%Ò’ÂF—6V6T†—7F÷'’æFöuö–BÓÒFöræ–@¢’’æÆÂ‚“ ¢7FGW5öÆ&VÇ2Ò²'G&VFÖVçB#¢.k+¾y˜.KŠÒ"Â&föÆÆ÷wW#¢.{XÎ˜îŠk>Zùò"Â'&V6÷fW&VB#¢.ZèÎk+²"Â&6‡&öæ–2#¢.hZ.h
r'Ğ¢FWF–ÂÒ—FVÒæF—6V6UöæÖR²†b.ûÈ‡·7FGW5öÆ&VÇ2ævWB†—FVÒç7FGW2Â—FVÒç7FGW2—ŞûÈ’"–b—FVÒç7FGW2VÇ6R""¢VçG&–W2æVæB‚†—FVÒæF–væ÷6VEööâ÷"FFRæÖ–âÂ.yx^jÛB"ÂFWF–ÂÂ—FVÒæ÷væW%öæ÷FW2÷"""’¢–b6†&VEö–G2ævWB‚&fööB"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„fööD†—7F÷'’’çv†W&R€¢fööD†—7F÷'’æ–Bæ–åò‡6†&VEö–G5²&fööB%Ò’ÂfööD†—7F÷'’æFöuö–BÓÒFöræ–@¢’’æÆÂ‚“ ¢FWF–Ç2Ò¶—FVÒææÖUĞ¢–b—FVÒæÖ÷VçEör—2æ÷BæöæS¢FWF–Ç2æVæB†b#iz^˜xşûÉ§¶—FVÒæÖ÷VçEös¦wÖr"¢–b—FVÒçF–ÖW5÷W%öF“¢FWF–Ç2æVæB†b#izW¶—FVÒçF–ÖW5÷W%öF—ŞY¹â"¢–b—FVÒæVæFVEööã¢FWF–Ç2æVæB†b.{X.K¨nûÉ§¶—FVÒæVæFVEööçÒ"¢VçG&–W2æVæB‚†—FVÒç7F'FVEööâÂ.89^8;Î88’"Â"ûÈò"æ¦ö–â†FWF–Ç2’Â—FVÒæ÷væW%öæ÷FW2÷"""’¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢6÷W&6RÒ.ˆz®Xˆn8Îy›¾˜Ë""–b—FVÒæ÷væW%ö–BÓÒW6W"æ–BVÇ6R.˜îXë¾8î8*®8;Î88®8;ÎŠ‰˜Ë" ¢FWF–ÂÒ—FVÒçF—FÆR²†b"ûÈò¶—FVÒçfÇVWÒ"–b—FVÒçfÇVRVÇ6R""¢VçG&–W2æVæB‚†—FVÒç&V6÷&FVEööâÂb'¶÷væW%ö6FVv÷'•öÆ&VÇ2ævWB†—FVÒæ6FVv÷'’Â~8Ş8îK¹br—ŞûÈ‡·6÷W&6WŞûÈ’"ÂFWF–ÂÂ—FVÒæFWF–Ç2÷"""’¢VçG&–W2ç6÷'B†¶W“ÖÆÖ&F&÷s¢&÷u³ÒÂ&WfW'6SÕG'VR¢ÆÆ÷vVEöf–ÇFW'2Ò²""Â'vV–v‡B"Â'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R"Â&fööB'Ğ¢–b†VÇF…ö6FVv÷'’æ÷B–âÆÆ÷vVEöf–ÇFW'3¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8*¾88n8+N8:®8;Î8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢7F'Eöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFUög&öÒ’–bFFUög&öÒVÇ6RæöæS²VæEöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFU÷Fò’–bFFU÷FòVÇ6RæöæP¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jIÎ{J.iÉş™i>8).z+®Š¨Ş8~8n8ş88^8B"¢–b7F'Eöf–ÇFW"æBVæEöf–ÇFW"æBVæEöf–ÇFW"Â7F'Eöf–ÇFW#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢f–ÇFW%öÆ&VÇ2Ò²'vV–v‡B#¢‚.KÙ>˜xÒ"Â’Â'f66–æF–öâ#¢‚.8:ş8*ş888;2"Â’Â&6†V6·W#¢‚.X^[«~Š‹®ijÒ"Â.X^Š‹¢"’Â&ÖVF–6F–öâ#¢‚.h©^‰jÂ"Â’Â&F—6V6R#¢‚.yx^jÛB"Â’Â&fööB#¢‚.89^8;Î88’"Â—Ğ¢æ÷&ÖÆ—¦VEö¶W—v÷&BÒ¶W—v÷&Bç7G&—‚’æÆ÷vW"‚•³£Ğ¢f–ÇFW&VEöVçG&–W2ÒµĞ¢f÷"VçG'’–âVçG&–W3 ¢—FVÕöFFRÂ¶–æBÂFWF–ÂÂæ÷FRÒVçG'¢–b†VÇF…ö6FVv÷'’æBæ÷Bç’†Æ&VÂ–â¶–æBf÷"Æ&VÂ–âf–ÇFW%öÆ&VÇ5¶†VÇF…ö6FVv÷'•Ò“¢6öçF–çVP¢–b7F'Eöf–ÇFW"æB—FVÕöFFRÒFFRæÖ–âæB—FVÕöFFRÂ7F'Eöf–ÇFW#¢6öçF–çVP¢–bVæEöf–ÇFW"æB—FVÕöFFRÒFFRæÖ–âæB—FVÕöFFRâVæEöf–ÇFW#¢6öçF–çVP¢–bæ÷&ÖÆ—¦VEö¶W—v÷&BæBæ÷&ÖÆ—¦VEö¶W—v÷&Bæ÷B–âb'¶¶–æGÒ¶FWF–ÇÒ¶æ÷FWÒ"æÆ÷vW"‚“¢6öçF–çVP¢f–ÇFW&VEöVçG&–W2æVæB†VçG'’¢&÷w2Ò""æ¦ö–â†b#ÇG#ãÇFCç¶—FVÕöFFR–b—FVÕöFFRÒFFRæÖ–âVÇ6RrÒwÓÂ÷FCãÇFCç¶‡FÖÂæW66R†¶–æB—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†FWF–Â—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†æ÷FR—ÓÂ÷FCãÂ÷G#â"f÷"—FVÕöFFRÂ¶–æBÂFWF–ÂÂæ÷FR–âf–ÇFW&VEöVçG&–W2¢f–ÇFW%ö÷F–öç2ÒsÆ÷F–öâfÇVSÒ"#î888cÂö÷F–öãâr²""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶¶W—Ò"²'6VÆV7FVB"–b†VÇF…ö6FVv÷'’ÓÒ¶W’VÇ6R"'Óç¶Æ&VÇÓÂö÷F–öãârf÷"¶W’ÂÆ&VÂ–â²‚'vV–v‡B"Â.KÙ>˜xÒ"’Â‚'f66–æF–öâ"Â.8:ş8*ş888;2"’Â‚&6†V6·W"Â.X^Š‹¢"’Â‚&ÖVF–6F–öâ"Â.h©^‰jÂ"’Â‚&F—6V6R"Â.yx^jÛB"’Â‚&fööB"Â.89^8;Î88’"•Ò¢6V&6…öf÷&ÒÒbrrsÆf÷&ÒÖWF†öCÒ&vWB"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚#ãÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃî8*¾88n8+N8:®8;ÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ&†VÇF…ö6FVv÷'’#ç¶f–ÇFW%ö÷F–öç7ÓÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃî™h¾Zx¾izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&FFUög&öÒ"fÇVSÒ'¶‡FÖÂæW66R†FFUög&öÒ—Ò#ãÂöF—cãÆF—cãÆÆ&VÃî{X.K¨nizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&FFU÷Fò"fÇVSÒ'¶‡FÖÂæW66R†FFU÷Fò—Ò#ãÂöF—cãÆF—cãÆÆ&VÃî8*Ş8;Î8:ş8;Î88“ÂöÆ&VÃãÆ–çWBG—SÒ'6V&6‚"æÖSÒ&¶W—v÷&B"fÇVSÒ'¶‡FÖÂæW66R†¶W—v÷&E³£Ò—Ò"Ö†ÆVæwFƒÒ#"Æ6V†öÆFW#Ò.‰jÎXšNYŞ8;¾yx^YŞ8;¾89^8;Î88YŞ8®8’#ãÂöF—cãÂöF—cãÆ'WGFöãîŠ‰˜Ë.8).jIÎ{J#Âö'WGFöãâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚#îiÚK»n8).8*ş8:®8*#ÂöãÂöf÷&ÓãÇãÇ7G&öæsç¶ÆVâ†f–ÇFW&VEöVçG&–W2—ŞK»cÂ÷7G&öæsîûÈşXZ‡¶ÆVâ†VçG&–W2—ŞK»n8).ŠzK£Â÷ârrp¢&W÷'E÷VW'’ÒW&ÆVæ6öFR‡¶¶W“¢fÇVRf÷"¶W’ÂfÇVR–â²&†VÇF…ö6FVv÷'’#¢†VÇF…ö6FVv÷'’Â&FFUög&öÒ#¢FFUög&öÒÂ&FFU÷Fò#¢FFU÷FòÂ&¶W—v÷&B#¢¶W—v÷&E³£×Òæ—FV×2‚’–bfÇVWÒ¢&W÷'E÷W&ÂÒb"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷&W÷'BçFb"²†b#÷·&W÷'E÷VW'—Ò"–b&W÷'E÷VW'’VÇ6R""¢77e÷W&ÂÒb"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷&W÷'Bæ77b"²†b#÷·&W÷'E÷VW'—Ò"–b&W÷'E÷VW'’VÇ6R""¢÷væW%öVF—E÷&÷w2Ò" ¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢÷væW"Ò6W76–öâævWB…W6W"Â—FVÒæ÷væW%ö–B¢–b—FVÒæ÷væW%ö–BÓÒW6W"æ–C ¢7F–öâÒbrrsÆFWF–Ç3ãÇ7VÖÖ'“î8>8îŠ‰˜Ë.8).{z™¸cÂ÷7VÖÖ'“ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷&V6÷&G2÷¶—FVÒæ–GÒ#ãÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃî8*¾88n8+N8:®8;ÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ&6FVv÷'’#ç²rræ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶¶W—Ò"²'6VÆV7FVB"–b—FVÒæ6FVv÷'’ÓÒ¶W’VÇ6R"'Óç¶Æ&VÇÓÂö÷F–öãârf÷"¶W’ÂÆ&VÂ–â÷væW%ö6FVv÷'•öÆ&VÇ2æ—FV×2‚’—ÓÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîŠ‰˜Ë.izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ'¶—FVÒç&V6÷&FVEööçÒ"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃîŠ‰˜Ë.Xh^Zë“ÂöÆ&VÃãÆ–çWBæÖSÒ'F—FÆR"fÇVSÒ'¶‡FÖÂæW66R†—FVÒçF—FÆR—Ò"&WV—&VBÖ†ÆVæwFƒÒ#S#ãÂöF—cãÆF—cãÆÆ&VÃîi[X
N8;¾Š9Î‹k3ÂöÆ&VÃãÆ–çWBæÖSÒ'fÇVR"fÇVSÒ'¶‡FÖÂæW66R†—FVÒçfÇVR÷"rr—Ò"Ö†ÆVæwFƒÒ#S#ãÂöF—cãÂöF—cãÆÆ&VÃîŠ›>{K8;¾8:8:#ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FWF–Ç2#ç¶‡FÖÂæW66R†—FVÒæFWF–Ç2÷"rr—ÓÂ÷FW‡F&VãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†&U÷Fõö'&VVFW""fÇVSÒ'G'VR"²v6†V6¶VBr–b—FVÒç6†&U÷Fõö'&VVFW"VÇ6RrwÓâ89n8:®8;Î888;Î8X[iÈ88(³ÂöÆ&VÃãÇ6ÖÆÃîX[iÈXXûÉ§¶‡FÖÂæW66R‡FVæçBææÖR–bFVæçBVÇ6R~ZY{HNxªÎˆˆâr—Ş8.89n8:®8;Î888;Î8ş™k.Šj~8î8ş8~8ZHi»N8;¾X˜®™šN8ş8~8Ş8î8¾8)>8#Â÷6ÖÆÃãÆ'WGFöãîZHi»N8).KùŞZÙƒÂö'WGFöããÂöf÷&ÓãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷&V6÷&G2÷¶—FVÒæ–GÒöFVÆWFR#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&ÕöFVÆWFR"fÇVSÒ'G'VR"&WV—&VCâ8>8îŠ‰˜Ë.8).ZèÎXZ8¾X˜®™šN88(¾8>88).z+®Š¨Ş8~8î8~8óÂöÆ&VÃãÆ'WGFöâ6Æ73Ò&FævW"#îŠ‰˜Ë.8).X˜®™šCÂö'WGFöããÂöf÷&ÓãÂöFWF–Ç3ârrp¢VÇ6S ¢7F–öâÒsÇ7â6Æ73Ò&&FvR#îZHi»NKˆŞXúóÂ÷7ãâp¢÷væW%öVF—E÷&÷w2³ÒbrrsÇG#ãÇFCç¶—FVÒç&V6÷&FVEööçÓÂ÷FCãÇFCç¶÷væW%ö6FVv÷'•öÆ&VÇ2ævWB†—FVÒæ6FVv÷'’Â.8Ş8îK¹b"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒçF—FÆR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†÷væW"ææÖR–b÷væW"VÇ6R.˜îXë¾8î8*®8;Î88®8;Â"—ÓÂ÷FCãÇFCç²~X[iÈKŠÒr–b—FVÒç6†&U÷Fõö'&VVFW"VÇ6R~™ÙîX[iÈ’wÓÂ÷FCãÇFCç¶7F–öçÓÂ÷FCãÂ÷G#ârrp¢6FVv÷'•ö6&G2Ò""æ¦ö–â†brrsÆ6Æ73Ò&ÖöGVÆR"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷¶¶W—Ò#ãÆƒ3ç¶Æ&VÇŞzêycÂöƒ3ãÇîŠ‰˜Ë"¶6FVv÷'•ö6÷VçG2ævWB†¶W’Â—ŞK»cÂ÷ãÂöârrrf÷"¶W’ÂÆ&VÂ–â÷væW%ö6FVv÷'•öÆ&VÇ2æ—FV×2‚’–b¶W’Ò&÷F†W""¢vV–v‡E÷fÇVW3¢Æ—7E·GWÆU¶FFRÂfÆöEÕÒÒµĞ¢–b6†&VEö–G2ævWB‚&†VÇF‚"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò‡6†&VEö–G5²&†VÇF‚%Ò’Â†VÇF…&V6÷&BæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ'vV–v‡B"Â†VÇF…&V6÷&BçvV–v‡Eö¶ræ—5öæ÷B„æöæR’’’æÆÂ‚“ ¢vV–v‡E÷fÇVW2æVæB‚†—FVÒç&V6÷&EöFFRÂ—FVÒçvV–v‡Eö¶r’¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢–b—FVÒæ6FVv÷'’ÓÒ'vV–v‡B# ¢ÖF6‚Ò&Rç6V&6‚‡""…³Ó•Ò²ƒó¥Âå³Ó•Ò²“ò’"Â—FVÒçfÇVR÷"""¢–bÖF6ƒ¢vV–v‡E÷fÇVW2æVæB‚†—FVÒç&V6÷&FVEööâÂfÆöB†ÖF6‚æw&÷Wƒ’’’¢ÆFW7E÷vV–v‡BÒÖ‚‡vV–v‡E÷fÇVW2Â¶W“ÖÆÖ&F&÷s¢&÷u³Ò’–bvV–v‡E÷fÇVW2VÇ6RæöæP¢7F—fUöÖVF–6F–öç2Ò ¢–b6†&VEö–G2ævWB‚&ÖVF–6F–öâ"“ ¢7F—fUöÖVF–6F–öç2³Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„ÖVF–6F–öâæ–B’’çv†W&R„ÖVF–6F–öâæ–Bæ–åò‡6†&VEö–G5²&ÖVF–6F–öâ%Ò’ÂÖVF–6F–öâæFöuö–BÓÒFöræ–BÂÖVF–6F–öâç7FGW2ÓÒ&öævö–ær"’’÷" ¢7F—fUöÖVF–6F–öç2³Ò7VÒƒf÷"—FVÒ–â÷væW%÷&V6÷&G2–b—FVÒæ6FVv÷'’ÓÒ&ÖVF–6F–öâ"æB—FVÒçfÇVRÓÒ.{i{i®KŠÒ"¢7F—fUöF—6V6W2Ò ¢–b6†&VEö–G2ævWB‚&F—6V6R"“ ¢7F—fUöF—6V6W2³Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„F—6V6T†—7F÷'’æ–B’’çv†W&R„F—6V6T†—7F÷'’æ–Bæ–åò‡6†&VEö–G5²&F—6V6R%Ò’ÂF—6V6T†—7F÷'’æFöuö–BÓÒFöræ–BÂF—6V6T†—7F÷'’ç7FGW2æ–åò…²'G&VFÖVçB"Â&föÆÆ÷wW"Â&6‡&öæ–2%Ò’’’÷" ¢7F—fUöF—6V6W2³Ò7VÒƒf÷"—FVÒ–â÷væW%÷&V6÷&G2–b—FVÒæ6FVv÷'’ÓÒ&F—6V6R"æB—FVÒçfÇVR–â².k+¾y˜.KŠÒ"Â.{XÎ˜îŠk>Zùò"Â.hZ.h
r'Ò¢7F—fUöfööEöæÖW3¢Æ—7E·7G%ÒÒµĞ¢–b6†&VEö–G2ævWB‚&fööB"“ ¢7F—fUöfööEöæÖW2æW‡FVæB†—FVÒææÖRf÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„fööD†—7F÷'’’çv†W&R„fööD†—7F÷'’æ–Bæ–åò‡6†&VEö–G5²&fööB%Ò’ÂfööD†—7F÷'’æFöuö–BÓÒFöræ–BÂfööD†—7F÷'’ç7FGW2ÓÒ&öævö–ær"ÂfööD†—7F÷'’æVæFVEööâæ—5ò„æöæR’’’æÆÂ‚’¢7F—fUöfööEöæÖW2æW‡FVæB†—FVÒçF—FÆRf÷"—FVÒ–â÷væW%÷&V6÷&G2–b—FVÒæ6FVv÷'’ÓÒ&fööB"æB—FVÒçfÇVRÓÒ.XŠyJKŠÒ"¢GVUö—FV×2Ò²‚.8:ş8*ş888;2"ÂF—FÆRÂGVRÂF—2Â'f66–æF–öâ"’f÷"GVUöFörÂF—FÆRÂGVRÂF—2–âfÖ–Ç•÷f66–æUöGVUö—FV×2‡W6W"Â6W76–öâ’–bGVUöFöræ–BÓÒFöræ–EĞ¢GVUö—FV×2³Ò²‚.X^Š‹¢"ÂF—FÆRÂGVRÂF—2Â&6†V6·W"’f÷"GVUöFörÂF—FÆRÂGVRÂF—2–âfÖ–Ç•ö6†V6·WöGVUö—FV×2‡W6W"Â6W76–öâ’–bGVUöFöræ–BÓÒFöræ–EĞ¢GVUö—FV×2³Ò²‚.h©^‰jÂ"ÂF—FÆRÂGVRÂF—2Â&ÖVF–6F–öâ"’f÷"GVUöFörÂF—FÆRÂGVRÂF—2–âfÖ–Ç•öÖVF–6F–öåöGVUö—FV×2‡W6W"Â6W76–öâ’–bGVUöFöræ–BÓÒFöræ–EĞ¢GVUö—FV×2³Ò²‚.XhŞŠ‹¢"ÂF—FÆRÂGVRÂF—2Â&F—6V6R"’f÷"GVUöFörÂF—FÆRÂGVRÂF—2–âfÖ–Ç•öF—6V6UöGVUö—FV×2‡W6W"Â6W76–öâ’–bGVUöFöræ–BÓÒFöræ–EĞ¢GVUö—FV×2ç6÷'B†¶W“ÖÆÖ&F&÷s¢&÷u³%Ò¢÷fW&GVUö6÷VçBÒ7VÒƒf÷"òÂòÂòÂF—2Âò–âGVUö—FV×2–bF—2Â“²W6öÖ–æuö6÷VçBÒ7VÒƒf÷"òÂòÂòÂF—2Âò–âGVUö—FV×2–bF—2ãÒ¢GVU÷&÷w2Ò""æ¦ö–â†brrsÇG#ãÇFCç¶Æ&VÇÓÂ÷FCãÇFCãÆ‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷¶6FVv÷'—Ò#ç¶‡FÖÂæW66R‡F—FÆR—ÓÂöãÂ÷FCãÇFCç¶GVWÓÂ÷FCãÇFCãÇ7â6Æ73Ò&&FvR"7G–ÆSÒ'²v&6¶w&÷VæC¢6cF3–6¶6öÆ÷#¢3†C33rr–bF—2ÂVÇ6Rv&6¶w&÷VæC¢6cfS#ƒ¶6öÆ÷#¢3sSSSBwÒ#ç¶'2†F—2—ŞizW²~‹h^˜âr–bF—2ÂVÇ6R~[èÂwÓÂ÷7ããÂ÷FCãÇFCãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFR#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&6FVv÷'’"fÇVSÒ'¶6FVv÷'—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F—FÆR"fÇVSÒ'¶‡FÖÂæW66R‡F—FÆR—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&GVUööâ"fÇVSÒ'¶GVWÒ#ãÆ'WGFöâ6Æ73Ò'7V66W72"7G–ÆSÒ&Ö&v–ã£·FF–æs£w‚‚#îZéşikŞkˆ8ş8¾88(³Âö'WGFöããÂöf÷&ÓãÂ÷FCãÂ÷G#ârrrf÷"Æ&VÂÂF—FÆRÂGVRÂF—2Â6FVv÷'’–âGVUö—FV×2¢GVUöÖö&–ÆUö6&G2Ò""æ¦ö–â†brrsÆ'F–6ÆR6Æ73Ò&†VÇF‚ÖÖö&–ÆRÖ6&B#ãÆƒ3ç¶Æ&VÇŞûÉ£Æ‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷¶6FVv÷'—Ò#ç¶‡FÖÂæW66R‡F—FÆR—ÓÂöãÂöƒ3ãÇîK¨Zé®iz^ûÉ§¶GVWŞ8Ç7â6Æ73Ò&&FvR"7G–ÆSÒ'²v&6¶w&÷VæC¢6cF3–6¶6öÆ÷#¢3†C33rr–bF—2ÂVÇ6Rv&6¶w&÷VæC¢6cfS#ƒ¶6öÆ÷#¢3sSSSBwÒ#ç¶'2†F—2—ŞizW²~‹h^˜âr–bF—2ÂVÇ6R~[èÂwÓÂ÷7ããÂ÷ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFR#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&6FVv÷'’"fÇVSÒ'¶6FVv÷'—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F—FÆR"fÇVSÒ'¶‡FÖÂæW66R‡F—FÆR—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&GVUööâ"fÇVSÒ'¶GVWÒ#ãÆ'WGFöâ6Æ73Ò'7V66W72#îZéşikŞkˆ8ş8¾88(³Âö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrrf÷"Æ&VÂÂF—FÆRÂGVRÂF—2Â6FVv÷'’–âGVUö—FV×2¢F6†&ö&BÒbrrsÆƒ#îX^[«~8+^89î8:®8;ÃÂöƒ#ãÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÈikKÙ>˜xÓÂöƒ3ãÇ7G&öæsç¶bw¶ÆFW7E÷vV–v‡E³Ó¦wÖ¶rr–bÆFW7E÷vV–v‡BVÇ6R~iÊ®y›¾˜Ë"wÓÂ÷7G&öæsãÇç¶ÆFW7E÷vV–v‡E³Ò–bÆFW7E÷vV–v‡BVÇ6RrwÓÂ÷ãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3î{i{i®KŠŞ8îh©^‰jÃÂöƒ3ãÇ7G&öæsç¶7F—fUöÖVF–6F–öç7ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îk+¾y˜.8;¾Šk>Zùş8;¾hZ.h
sÂöƒ3ãÇ7G&öæsç¶7F—fUöF—6V6W7ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îxûîYÊ8î89^8;Î88“Âöƒ3ãÇ7G&öæsç¶ÆVâ†7F—fUöfööEöæÖW2—ŞK»cÂ÷7G&öæsãÇç¶‡FÖÂæW66R‚~8ræ¦ö–â†7F—fUöfööEöæÖW2’÷"~iÊ®y›¾˜Ë"r—ÓÂ÷ãÂ÷6V7F–öããÂöF—cãÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3ã3iz^Kº^Xh^8îK¨Zé£Âöƒ3ãÇ7G&öæsç·W6öÖ–æuö6÷VçGŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÉş™™‹h^˜ãÂöƒ3ãÇ7G&öær6Æ73Ò'²vW'&÷"r–b÷fW&GVUö6÷VçBVÇ6RrwÒ#ç¶÷fW&GVUö6÷VçGŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÂöF—cãÆƒ#î8>8(Î8¾8(8îX^[«~K¨Zé£Âöƒ#ãÆF—b6Æ73Ò&†VÇF‚ÖFW6·F÷ÖöæÇ’"7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆSãÇG#ãÇFƒîzŠîšãÂ÷FƒãÇFƒîXh^Zë“Â÷FƒãÇFƒîK¨Zé®izSÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç¶GVU÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#R#ã3iz^Kº^Xh^8î8ş8şiÉş™™‹h^˜î8îK¨Zé®8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSãÂöF—cãÇ6V7F–öâ6Æ73Ò&†VÇF‚ÖÖö&–ÆRÖöæÇ’#ç¶GVUöÖö&–ÆUö6&G2÷"sÆF—b6Æ73Ò'FVæçB#ã3iz^Kº^Xh^8î8ş8şiÉş™™‹h^˜î8îK¨Zé®8ş8.8(®8î8¾8)>8#ÂöF—câwÓÂ÷6V7F–öãârrp¢&öG’ÒbrrsÆF—b6Æ73Ò&†VÇF‚×FööÆ&"#ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒ#ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8î89®8;Î8+8h‹¾8(³ÂöãÆ6Æ73Ò&'WGFöâ"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚ö6ÆVæF"#îX^[«~8*¾8:Î8;>888;ÃÂöãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷66†VGVÆW2ö6ö×ÆWFVB#îZéşikŞkˆ8ş[^jÛCÂöãÆ6Æ73Ò&'WGFöâ"‡&VcÒ'·&W÷'E÷W&ÇÒ#îŠzK®iÚK»n8uDnX{®X©³ÂöãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ'¶77e÷W&ÇÒ#îŠzK®iÚK»n8t55nX{®X©³ÂöãÂöF—cà¢Æƒç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8î8n88îZÙX^[«~zêycÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇî89n8:®8;Î888;Î8¾8([É^8Ş{i8N8Š‰˜Ë.888*®8;Î88®8;Îjy8Î{i{i®8~8ny›¾˜Ë.88(¾Š‰˜Ë.8).8î88(8nŠzK®8~8î88#Â÷à¢Çî89n8:®8;Î888;Î8Îy›¾˜Ë.8~8ş˜îXë¾88~8;Î8+ş8ş™k.Šj~8î8ş8~88.8*®8;Î88®8;Îjy8Îy›¾˜Ë.8~8şŠ‰˜Ë.8şXZ^X©¾8~8şiÊÎK«®888ÎZHi»N8~8Ş8î88#Â÷ãÂöF—cà¢¶F6†&ö&GÓÆƒ#î8*¾88n8+N8:®8;ÎXŠ^zêycÂöƒ#ãÆF—b6Æ73Ò&w&–B#ç¶6FVv÷'•ö6&G7ÓÂöF—cà¢Æƒ#îX^[«~Š‰˜Ë.8îjIÎ{J#Âöƒ#ç·6V&6…öf÷&×ÓÆƒ#îiÈ‹ù8îX^[«~Š‰˜Ë#Âöƒ#à¢ÇF&ÆSãÇG#ãÇFƒîiz^K¹ƒÂ÷FƒãÇFƒîzŠîšãÂ÷FƒãÇFƒîXh^Zë“Â÷FƒãÇFƒî8:8:#Â÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îiÚK»n8¾Kˆˆ{N88(¾X^[«~Š‰˜Ë.8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSà¢Æƒ#î8*®8;Î88®8;Î8ÎXZ^X©¾8~8şŠ‰˜Ë.8îzêycÂöƒ#ãÆF—b7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆSãÇG#ãÇFƒîŠ‰˜Ë.izSÂ÷FƒãÇFƒî8*¾88n8+N8:®8;ÃÂ÷FƒãÇFƒîXh^Zë“Â÷FƒãÇFƒîXZ^X©¾ˆSÂ÷FƒãÇFƒî89n8:®8;Î888;ÎX[iÈ“Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç¶÷væW%öVF—E÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#b#î8*®8;Î88®8;Î8ÎXZ^X©¾8~8şŠ‰˜Ë.8ş8î88.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSãÂöF—cà¢¶bsÆƒ#îX[iÈ8^8(Î8şjIÎiû¾{YiéÃÂöƒ#ãÇç·6†&VEö6†V6·Wöf–ÆW7ÓÂ÷âr–b6†&VEö6†V6·Wöf–ÆW2VÇ6RrwĞ¢¶bsÆƒ#îX[iÈ8^8(Î8şŠ‹Îiˆîi»ƒÂöƒ#ãÇç·6†&VEö6W'F–f–6FW7ÓÂ÷âr–b6†&VEö6W'F–f–6FW2VÇ6RrwĞ¢ÇãÇ6ÖÆÃî{x®h
^i˜.8(Nk+¾y˜.XŠNijŞ8¾8ş8>8îyK¾™Ú.888).KÛş8(ş8®8xªÎˆˆî8î8ş8şX¹^xšyx^™š.88Nz+®Š¨Ş8ş88^8N8#Â÷6ÖÆÃãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶Föræ6ÆÅöæÖWŞ8î8n88îZÙX^[«~zêynûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷&W÷'BçFb"¦FVbfÖ–Ç•öFöuö†VÇF…÷&W÷'E÷Fb†Föuö–C¢–çBÂ†VÇF…ö6FVv÷'“¢7G"Ò""ÂFFUög&öÓ¢7G"Ò""ÂFFU÷Fó¢7G"Ò""Â¶W—v÷&C¢7G"Ò""ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÒ÷væVC²FVæçBÒ6W76–öâævWB…FVæçBÂ÷væW'6†—çFVæçEö–B¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R„†VÇF…&V6÷&E6†&RæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR’’’æÆÂ‚¢–G3¢F–7E·7G"ÂÆ—7E¶–çEÕÒÒ·Ğ¢f÷"6†&R–â6†&W3¢–G2ç6WFFVfVÇB‡6†&Rç&V6÷&E÷G—RÂµÒ’æVæB‡6†&Rç&V6÷&Eö–B¢&÷w3¢Æ—7E·GWÆU¶FFRÂ7G"Â7G%ÕÒÒµĞ¢–b–G2ævWB‚&†VÇF‚"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò†–G5²&†VÇF‚%Ò’Â†VÇF…&V6÷&BæFöuö–BÓÒFöræ–B’’æÆÂ‚“ ¢Æ&VÂÒ²'vV–v‡B#¢.KÙ>˜xÒ"Â&6†V6·W#¢.X^[«~Š‹®ijÒ"Â'G&VFÖVçB#¢.Š‹®y˜"'ÒævWB†—FVÒæ6FVv÷'’Â.X^[«~Š‰˜Ë""¢FWF–ÂÒb'¶—FVÒçvV–v‡Eö¶s¦wÖ¶r"–b—FVÒçvV–v‡Eö¶r—2æ÷BæöæRVÇ6R†—FVÒç&W7VÇE÷7VÖÖ'’÷"—FVÒææ÷FW2÷".Š‰˜Ë.8.8(¢"¢&÷w2æVæB‚†—FVÒç&V6÷&EöFFRÂÆ&VÂÂFWF–Â’¢ÖöFVÅ÷7V72Ò°¢‚'f66–æF–öâ"Âf66–æF–öâÂ&FÖ–æ—7FW&VEööâ"Â.8:ş8*ş888;2"ÂÆÖ&Fƒ¢b'·‚çf66–æUöæÖWŞûÈşjÊY¹â·‚ææW‡EöGVUööâ÷"~iÊ®ŠŠŞZé¢wÒ"’À¢‚&ÖVF–6F–öâ"ÂÖVF–6F–öâÂ&FÖ–æ—7FW&VEööâ"Â.h©^‰jÂ"ÂÆÖ&Fƒ¢b'·‚æÖVF–6–æUöæÖWŞûÈ÷·‚æF÷6vR÷"~yJ˜xşiÊ®y›¾˜Ë"wŞûÈ÷·‚æg&WVVæ7’÷"~š¾[ªniÊ®y›¾˜Ë"wŞûÈ÷·‚æ÷væW%öæ÷FW2÷"rwÒ"’À¢‚&F—6V6R"ÂF—6V6T†—7F÷'’Â&F–væ÷6VEööâ"Â.yx^jÛB"ÂÆÖ&Fƒ¢b'·‚æF—6V6UöæÖWŞûÈ÷²²wG&VFÖVçBs¢~k+¾y˜.KŠÒrÂvföÆÆ÷wWs¢~{XÎ˜îŠk>ZùòrÂw&V6÷fW&VBs¢~ZèÎk+²rÂv6‡&öæ–2s¢~hZ.h
rwÒævWB‡‚ç7FGW2Â~x«nhX¾iÊ®y›¾˜Ë"r—ŞûÈ÷·‚æ÷væW%öæ÷FW2÷"rwÒ"’À¢‚&fööB"ÂfööD†—7F÷'’Â'7F'FVEööâ"Â.89^8;Î88’"ÂÆÖ&Fƒ¢b'·‚ææÖWŞûÈóiz^˜xò¶bw·‚æÖ÷VçEös¦wÖrr–b‚æÖ÷VçEör—2æ÷BæöæRVÇ6R~iÊ®y›¾˜Ë"wŞûÈ÷¶bsizW·‚çF–ÖW5÷W%öF—ŞY¹âr–b‚çF–ÖW5÷W%öF’VÇ6R~Y¹îi[iÊ®y›¾˜Ë"wŞûÈ÷·‚æ÷væW%öæ÷FW2÷"rwÒ"’À¢Ğ¢f÷"¶W’ÂÖöFVÂÂFFUöf–VÆBÂÆ&VÂÂFW67&–&R–âÖöFVÅ÷7V73 ¢–b–G2ævWB†¶W’“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B†ÖöFVÂ’çv†W&R†ÖöFVÂæ–Bæ–åò†–G5¶¶W•Ò’ÂÖöFVÂæFöuö–BÓÒFöræ–B’’æÆÂ‚“¢&÷w2æVæB‚†vWFGG"†—FVÒÂFFUöf–VÆB’÷"FFRæÖ–âÂÆ&VÂÂFW67&–&R†—FVÒ’’¢÷væW%÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&BçFVæçEö–BÓÒ÷væW'6†—çFVæçEö–BÂ÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöræ–B’’æÆÂ‚¢Æ&VÇ2Ò²'vV–v‡B#¢.KÙ>˜xÒ"Â'f66–æF–öâ#¢.8:ş8*ş888;2"Â&6†V6·W#¢.X^[«~Š‹®ijÒ"Â&ÖVF–6F–öâ#¢.h©^‰jÂ"Â&F—6V6R#¢.yx^jÛB"Â&fööB#¢.89^8;Î88’"Â&÷F†W"#¢.8Ş8îK¹b'Ğ¢f÷"—FVÒ–â÷væW%÷&V6÷&G3¢&÷w2æVæB‚†—FVÒç&V6÷&FVEööâÂÆ&VÇ2ævWB†—FVÒæ6FVv÷'’Â.8Ş8îK¹b"’Âb'¶—FVÒçF—FÆWŞûÈ÷¶—FVÒçfÇVR÷"rwŞûÈ÷¶—FVÒæFWF–Ç2÷"rwÒ"’¢&÷w2ç6÷'B†¶W“ÖÆÖ&F&÷s¢&÷u³ÒÂ&WfW'6SÕG'VR¢ÆÆ÷vVEöf–ÇFW'2Ò²""Â'vV–v‡B"Â'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R"Â&fööB'Ğ¢–b†VÇF…ö6FVv÷'’æ÷B–âÆÆ÷vVEöf–ÇFW'3¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8*¾88n8+N8:®8;Î8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢7F'Eöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFUög&öÒ’–bFFUög&öÒVÇ6RæöæS²VæEöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFU÷Fò’–bFFU÷FòVÇ6RæöæP¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jIÎ{J.iÉş™i>8).z+®Š¨Ş8~8n8ş88^8B"¢–b7F'Eöf–ÇFW"æBVæEöf–ÇFW"æBVæEöf–ÇFW"Â7F'Eöf–ÇFW#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢&W÷'EöÆ&VÇ2Ò²'vV–v‡B#¢‚.KÙ>˜xÒ"Â’Â'f66–æF–öâ#¢‚.8:ş8*ş888;2"Â’Â&6†V6·W#¢‚.X^[«~Š‹®ijÒ"Â.X^Š‹¢"’Â&ÖVF–6F–öâ#¢‚.h©^‰jÂ"Â’Â&F—6V6R#¢‚.yx^jÛB"Â’Â&fööB#¢‚.89^8;Î88’"Â—Ğ¢æ÷&ÖÆ—¦VEö¶W—v÷&BÒ¶W—v÷&Bç7G&—‚’æÆ÷vW"‚•³£Ğ¢&÷w2Ò·&÷rf÷"&÷r–â&÷w2–b†æ÷B†VÇF…ö6FVv÷'’÷"&÷u³Ò–â&W÷'EöÆ&VÇ5¶†VÇF…ö6FVv÷'•Ò’æB†æ÷B7F'Eöf–ÇFW"÷"&÷u³ÒÒFFRæÖ–âæB&÷u³ÒãÒ7F'Eöf–ÇFW"’æB†æ÷BVæEöf–ÇFW"÷"&÷u³ÒÒFFRæÖ–âæB&÷u³ÒÃÒVæEöf–ÇFW"’æB†æ÷Bæ÷&ÖÆ—¦VEö¶W—v÷&B÷"æ÷&ÖÆ—¦VEö¶W—v÷&B–âb'·&÷u³×Ò·&÷u³%×Ò"æÆ÷vW"‚’•Ğ¢6öæF—F–öå÷'G2Ò¶b.8*¾88n8+N8:®8;ÎûÉ§²²wvV–v‡Bs¢~KÙ>˜xÒrÂwf66–æF–öâs¢~8:ş8*ş888;2rÂv6†V6·Ws¢~X^Š‹¢rÂvÖVF–6F–öâs¢~h©^‰jÂrÂvF—6V6Rs¢~yx^jÛBrÂvfööBs¢~89^8;Î88’wÒævWB††VÇF…ö6FVv÷'’Â~888br—Ò"Âb.iÉş™i>ûÉ§¶FFUög&öÒ÷"~hÈ~Zé®8®8rwŞ8	Ç¶FFU÷Fò÷"~hÈ~Zé®8®8rwÒ%Ğ¢–bæ÷&ÖÆ—¦VEö¶W—v÷&C¢6öæF—F–öå÷'G2æVæB†b.jIÎ{J.Š©îûÉ§¶¶W—v÷&Bç7G&—‚•³£×Ò"¢&W÷'Eö6öæF—F–öâÒ.8"æ¦ö–â†6öæF—F–öå÷'G2¢÷WGWBÒ–òä'—FW4”ò‚“²FfÖWG&–72ç&Vv—7FW$föçB…Væ–6öFT4”DföçB‚$†V—6V”¶·TvòÕsR"’“²FbÒ6çf2ä6çf2†÷WGWBÂvW6—¦SÔB“²v–GF‚Â†V–v‡BÒ@¢FVb†VFW"‚“ ¢Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Âb“²FbæG&u7G&–ærƒ3bÂ†V–v‡BÒ3‚Âb'¶Föræ6ÆÅöæÖWÒX^[«~Š‰˜Ë.8:Î89Ş8;Î88‚"¢Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Â’“²FbæG&u7G&–ærƒ3bÂ†V–v‡BÒSbÂb.xªÎzŠîûÉ§¶Föræ'&VVB÷"~iÊ®y›¾˜Ë"wŞ8yIş[›NiÈiz^ûÉ§¶Föræ&—'F…öFFR÷"~iÊ®y›¾˜Ë"wŞ8X[iÈXX>ûÉ§·FVæçBææÖR–bFVæçBVÇ6R~89n8:®8;Î888;ÂwÒ"¢FbæG&u7G&–ærƒ3bÂ†V–v‡BÒsÂ&W÷'Eö6öæF—F–öå³£ƒUÒ¢FbæG&u7G&–ærƒ3bÂ†V–v‡BÒƒbÂb.KÙÎh‰iz^ûÉ§¶FFRçFöF’‚—Ş8(¾Š‹®ijŞi»8~8ş8.8(®8î8¾8)>8.Š‹®y˜.i˜.8îXø.ˆ>‹8~ii88~8n8NXŠyJ8ş88^8N8""¢FbæÆ–æRƒ3bÂ†V–v‡BÒ“BÂv–GF‚Ò3bÂ†V–v‡BÒ“B¢†VFW"‚“²’Ò†V–v‡BÒ3²Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Â’¢f÷"F’ÂÆ&VÂÂFWF–Â–â&÷w3 ¢6ÆVâÒ&Rç7V"‡"%Ç2²"Â""ÂFWF–Â’ç7G&—‚“²Æ–æW2Ò¶6ÆVå¶–æFWƒ¦–æFW‚²S%Òf÷"–æFW‚–â&ævRƒÂÆVâ†6ÆVâ’ÂS"•Ò÷"².ûÈÒ%Ğ¢æVVFVBÒb¢Ö‚†ÆVâ†Æ–æW2’Â’²€¢–b’ÒæVVFVBÂ3c¢Fbç6†÷uvR‚“²†VFW"‚“²’Ò†V–v‡BÒ3²Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Â’¢FbæG&u7G&–ærƒ3bÂ’Â7G"†F’’–bF’ÒFFRæÖ–âVÇ6R.ûÈÒ"“²FbæG&u7G&–ærƒRÂ’ÂÆ&VÂ¢f÷"–æFW‚ÂÆ–æR–âVçVÖW&FR†Æ–æW2“¢FbæG&u7G&–ærƒcRÂ’Ò–æFW‚¢BÂÆ–æR¢’ÓÒæVVFV@¢–bæ÷B&÷w3¢FbæG&u7G&–ærƒ3bÂ’Â.X[iÈ8;¾y›¾˜Ë.8^8(Î8n8N8(¾X^[«~Š‰˜Ë.8ş8.8(®8î8¾8)>8""¢Fbç6fR‚¢f–ÆVæÖRÒb&†VÇF‚×&W÷'BÖFör×¶Föræ–GÒçFb ¢&WGW&â&W7öç6R†6öçFVçCÖ÷WGWBævWGfÇVR‚’ÂÖVF–÷G—SÒ&Æ–6F–öâ÷Fb"Â†VFW'3×²$6öçFVçBÔF—7÷6—F–öâ#¢bvGF6†ÖVçC²f–ÆVæÖSÒ'¶f–ÆVæÖWÒ"rÂ$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R'Ò  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷&W÷'Bæ77b"¦FVbfÖ–Ç•öFöuö†VÇF…÷&W÷'Eö77b†Föuö–C¢–çBÂ†VÇF…ö6FVv÷'“¢7G"Ò""ÂFFUög&öÓ¢7G"Ò""ÂFFU÷Fó¢7G"Ò""Â¶W—v÷&C¢7G"Ò""ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÒ÷væV@¢ÆÆ÷vVEöf–ÇFW'2Ò²""Â'vV–v‡B"Â'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R"Â&fööB'Ğ¢–b†VÇF…ö6FVv÷'’æ÷B–âÆÆ÷vVEöf–ÇFW'3¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8*¾88n8+N8:®8;Î8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢7F'Eöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFUög&öÒ’–bFFUög&öÒVÇ6RæöæS²VæEöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFU÷Fò’–bFFU÷FòVÇ6RæöæP¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jIÎ{J.iÉş™i>8).z+®Š¨Ş8~8n8ş88^8B"¢–b7F'Eöf–ÇFW"æBVæEöf–ÇFW"æBVæEöf–ÇFW"Â7F'Eöf–ÇFW#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R„†VÇF…&V6÷&E6†&RæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR’’’æÆÂ‚¢–G3¢F–7E·7G"ÂÆ—7E¶–çEÕÒÒ·Ğ¢f÷"6†&R–â6†&W3¢–G2ç6WFFVfVÇB‡6†&Rç&V6÷&E÷G—RÂµÒ’æVæB‡6†&Rç&V6÷&Eö–B¢&÷w3¢Æ—7E·GWÆU¶FFRÂ7G"Â7G"Â7G%ÕÒÒµĞ¢–b–G2ævWB‚&†VÇF‚"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò†–G5²&†VÇF‚%Ò’Â†VÇF…&V6÷&BæFöuö–BÓÒFöræ–B’’æÆÂ‚“ ¢Æ&VÂÒ²'vV–v‡B#¢.KÙ>˜xÒ"Â&6†V6·W#¢.X^[«~Š‹®ijÒ"Â'G&VFÖVçB#¢.Š‹®y˜"'ÒævWB†—FVÒæ6FVv÷'’Â.X^[«~Š‰˜Ë""¢FWF–ÂÒb'¶—FVÒçvV–v‡Eö¶s¦wÖ¶r"–b—FVÒçvV–v‡Eö¶r—2æ÷BæöæRVÇ6R†—FVÒç&W7VÇE÷7VÖÖ'’÷".Š‰˜Ë.8.8(¢"¢&÷w2æVæB‚†—FVÒç&V6÷&EöFFRÂÆ&VÂÂFWF–ÂÂ—FVÒææ÷FW2÷"""’¢7V72Ò°¢‚'f66–æF–öâ"Âf66–æF–öâÂ&FÖ–æ—7FW&VEööâ"Â.8:ş8*ş888;2"ÂÆÖ&Fƒ¢‚çf66–æUöæÖRÂÆÖ&Fƒ¢b.jÊY¹îK¨Zé®ûÉ§·‚ææW‡EöGVUööâ÷"~iÊ®ŠŠŞZé¢wÒ"’À¢‚&ÖVF–6F–öâ"ÂÖVF–6F–öâÂ&FÖ–æ—7FW&VEööâ"Â.h©^‰jÂ"ÂÆÖ&Fƒ¢‚æÖVF–6–æUöæÖRÂÆÖ&Fƒ¢b.yJ˜xşûÉ§·‚æF÷6vR÷"~iÊ®y›¾˜Ë"wŞûÈşš¾[ªnûÉ§·‚æg&WVVæ7’÷"~iÊ®y›¾˜Ë"wŞûÈ÷·‚æ÷væW%öæ÷FW2÷"rwÒ"’À¢‚&F—6V6R"ÂF—6V6T†—7F÷'’Â&F–væ÷6VEööâ"Â.yx^jÛB"ÂÆÖ&Fƒ¢‚æF—6V6UöæÖRÂÆÖ&Fƒ¢‚æ÷væW%öæ÷FW2÷"""’À¢‚&fööB"ÂfööD†—7F÷'’Â'7F'FVEööâ"Â.89^8;Î88’"ÂÆÖ&Fƒ¢‚ææÖRÂÆÖ&Fƒ¢b#iz^˜xşûÉ§¶bw·‚æÖ÷VçEös¦wÖrr–b‚æÖ÷VçEör—2æ÷BæöæRVÇ6R~iÊ®y›¾˜Ë"wŞûÈ÷¶bsizW·‚çF–ÖW5÷W%öF—ŞY¹âr–b‚çF–ÖW5÷W%öF’VÇ6R~Y¹îi[iÊ®y›¾˜Ë"wŞûÈ÷·‚æ÷væW%öæ÷FW2÷"rwÒ"’À¢Ğ¢f÷"¶W’ÂÖöFVÂÂFFUöf–VÆBÂÆ&VÂÂF—FÆUööbÂæ÷FUööb–â7V73 ¢–b–G2ævWB†¶W’“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B†ÖöFVÂ’çv†W&R†ÖöFVÂæ–Bæ–åò†–G5¶¶W•Ò’ÂÖöFVÂæFöuö–BÓÒFöræ–B’’æÆÂ‚“¢&÷w2æVæB‚†vWFGG"†—FVÒÂFFUöf–VÆB’÷"FFRæÖ–âÂÆ&VÂÂF—FÆUööb†—FVÒ’Âæ÷FUööb†—FVÒ’’¢÷væW%öÆ&VÇ2Ò²'vV–v‡B#¢.KÙ>˜xÒ"Â'f66–æF–öâ#¢.8:ş8*ş888;2"Â&6†V6·W#¢.X^[«~Š‹®ijÒ"Â&ÖVF–6F–öâ#¢.h©^‰jÂ"Â&F—6V6R#¢.yx^jÛB"Â&fööB#¢.89^8;Î88’"Â&÷F†W"#¢.8Ş8îK¹b'Ğ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&BçFVæçEö–BÓÒ÷væW'6†—çFVæçEö–BÂ÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöræ–B’’æÆÂ‚“¢&÷w2æVæB‚†—FVÒç&V6÷&FVEööâÂ÷væW%öÆ&VÇ2ævWB†—FVÒæ6FVv÷'’Â.8Ş8îK¹b"’Âb'¶—FVÒçF—FÆWŞûÈ÷¶—FVÒçfÇVR÷"rwÒ"Â—FVÒæFWF–Ç2÷"""’¢f–ÇFW%öÆ&VÇ2Ò²'vV–v‡B#¢‚.KÙ>˜xÒ"Â’Â'f66–æF–öâ#¢‚.8:ş8*ş888;2"Â’Â&6†V6·W#¢‚.X^[«~Š‹®ijÒ"Â.X^Š‹¢"’Â&ÖVF–6F–öâ#¢‚.h©^‰jÂ"Â’Â&F—6V6R#¢‚.yx^jÛB"Â’Â&fööB#¢‚.89^8;Î88’"Â—Ğ¢æ÷&ÖÆ—¦VEö¶W—v÷&BÒ¶W—v÷&Bç7G&—‚’æÆ÷vW"‚•³£Ğ¢&÷w2Ò·&÷rf÷"&÷r–â&÷w2–b†æ÷B†VÇF…ö6FVv÷'’÷"&÷u³Ò–âf–ÇFW%öÆ&VÇ5¶†VÇF…ö6FVv÷'•Ò’æB†æ÷B7F'Eöf–ÇFW"÷"&÷u³ÒÒFFRæÖ–âæB&÷u³ÒãÒ7F'Eöf–ÇFW"’æB†æ÷BVæEöf–ÇFW"÷"&÷u³ÒÒFFRæÖ–âæB&÷u³ÒÃÒVæEöf–ÇFW"’æB†æ÷Bæ÷&ÖÆ—¦VEö¶W—v÷&B÷"æ÷&ÖÆ—¦VEö¶W—v÷&B–âb'·&÷u³×Ò·&÷u³%×Ò·&÷u³5×Ò"æÆ÷vW"‚’•Ğ¢&÷w2ç6÷'B†¶W“ÖÆÖ&F&÷s¢&÷u³ÒÂ&WfW'6SÕG'VR¢÷WGWBÒ–òå7G&–æt”ò†æWvÆ–æSÒ""“²w&—FW"Ò77bçw&—FW"†÷WGWB“²w&—FW"çw&—FW&÷r…².hI¾xªÂ"Â.iz^K¹‚"Â.8*¾88n8+N8:®8;Â"Â.Xh^Zë’"Â.Š›>{K8;¾8:8:"%Ò¢f÷"F’ÂÆ&VÂÂFWF–ÂÂæ÷FR–â&÷w3¢w&—FW"çw&—FW&÷r…¶Föræ6ÆÅöæÖRÂF’–bF’ÒFFRæÖ–âVÇ6R""ÂÆ&VÂÂFWF–ÂÂæ÷FUÒ¢f–ÆVæÖRÒb&†VÇF‚×&W÷'BÖFör×¶Föræ–GÒæ77b ¢&WGW&â&W7öç6R†6öçFVçCÒ%ÇVfVfb"²÷WGWBævWGfÇVR‚’ÂÖVF–÷G—SÒ'FW‡Bö77c²6†'6WC×WFbÓ‚"Â†VFW'3×²$6öçFVçBÔF—7÷6—F–öâ#¢bvGF6†ÖVçC²f–ÆVæÖSÒ'¶f–ÆVæÖWÒ"rÂ$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R'Ò  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷¶6FVv÷'—Ò"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö÷væW%ö†VÇF…ö6FVv÷'•÷vR†Föuö–C¢–çBÂ6FVv÷'“¢7G"ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÒ÷væVC²FVæçBÒ6W76–öâævWB…FVæçBÂ÷væW'6†—çFVæçEö–B¢Æ&VÇ2Ò²'vV–v‡B#¢.KÙ>˜xÒ"Â'f66–æF–öâ#¢.8:ş8*ş888;2"Â&6†V6·W#¢.X^Š‹¢"Â&ÖVF–6F–öâ#¢.h©^‰jÂ"Â&F—6V6R#¢.yx^jÛB"Â&fööB#¢.89^8;Î88’'Ğ¢–b6FVv÷'’æ÷B–âÆ&VÇ3¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.X^[«~zêyn8*¾88n8+N8:®8;Î8ÎŠh¾8N8¾8(®8î8¾8)2"¢&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&BçFVæçEö–BÓÒ÷væW'6†—çFVæçEö–BÂ÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöræ–BÂ÷væW$†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ6FVv÷'’’æ÷&FW%ö'’„÷væW$†VÇF…&V6÷&Bç&V6÷&FVEööâæFW62‚’Â÷væW$†VÇF…&V6÷&Bæ–BæFW62‚’’’æÆÂ‚¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R„†VÇF…&V6÷&E6†&RæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR’’’æÆÂ‚¢–G3¢F–7E·7G"ÂÆ—7E¶–çEÕÒÒ·Ğ¢f÷"6†&R–â6†&W3¢–G2ç6WFFVfVÇB‡6†&Rç&V6÷&E÷G—RÂµÒ’æVæB‡6†&Rç&V6÷&Eö–B¢–æ†W&—FVC¢Æ—7E·GWÆU¶FFRÂ7G"Â7G%ÕÒÒµĞ¢–b6FVv÷'’–â²'vV–v‡B"Â&6†V6·W'ÒæB–G2ævWB‚&†VÇF‚"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò†–G5²&†VÇF‚%Ò’Â†VÇF…&V6÷&BæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ6FVv÷'’’’æÆÂ‚“ ¢fÇVRÒb'¶—FVÒçvV–v‡Eö¶wÖ¶r"–b6FVv÷'’ÓÒ'vV–v‡B"æB—FVÒçvV–v‡Eö¶r—2æ÷BæöæRVÇ6R†—FVÒç&W7VÇE÷7VÖÖ'’÷".X^Š‹®Š‰˜Ë""¢–æ†W&—FVBæVæB‚†—FVÒç&V6÷&EöFFRÂfÇVRÂ—FVÒææ÷FW2÷"""’¢–b6FVv÷'’ÓÒ'f66–æF–öâ"æB–G2ævWB‚'f66–æF–öâ"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B…f66–æF–öâ’çv†W&R…f66–æF–öâæ–Bæ–åò†–G5²'f66–æF–öâ%Ò’Âf66–æF–öâæFöuö–BÓÒFöræ–B’’æÆÂ‚“¢–æ†W&—FVBæVæB‚†—FVÒæFÖ–æ—7FW&VEööâÂ—FVÒçf66–æUöæÖRÂb.jÊY¹îûÉ§¶—FVÒææW‡EöGVUööçÒ"–b—FVÒææW‡EöGVUööâVÇ6R†—FVÒææ÷FW2÷"""’’¢–b6FVv÷'’ÓÒ&ÖVF–6F–öâ"æB–G2ævWB‚&ÖVF–6F–öâ"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„ÖVF–6F–öâ’çv†W&R„ÖVF–6F–öâæ–Bæ–åò†–G5²&ÖVF–6F–öâ%Ò’ÂÖVF–6F–öâæFöuö–BÓÒFöræ–B’’æÆÂ‚“ ¢7FGW5öÆ&VÇ2Ò²'6–ævÆR#¢.XÙY¹â"Â&öævö–ær#¢.{i{i®KŠÒ"Â&6ö×ÆWFVB#¢.{X.K¨b'Ğ¢FWF–ÂÒ·7FGW5öÆ&VÇ2ævWB†—FVÒç7FGW2÷"'6–ævÆR"Â.XÙY¹â"•Ğ¢–b—FVÒæF÷6vS¢FWF–ÂæVæB†b#Y¹î˜xşûÉ§¶—FVÒæF÷6vWÒ"¢–b—FVÒæg&WVVæ7“¢FWF–ÂæVæB†b.š¾[ªnûÉ§¶—FVÒæg&WVVæ7—Ò"¢–b—FVÒææW‡EöGVUööã¢FWF–ÂæVæB†b.jÊY¹îK¨Zé®ûÉ§¶—FVÒææW‡EöGVUööçÒ"¢–b—FVÒæ÷væW%öæ÷FW3¢FWF–ÂæVæB†—FVÒæ÷væW%öæ÷FW2¢–æ†W&—FVBæVæB‚†—FVÒæFÖ–æ—7FW&VEööâÂ—FVÒæÖVF–6–æUöæÖRÂ%Æâ"æ¦ö–â†FWF–Â’’¢–b6FVv÷'’ÓÒ&F—6V6R"æB–G2ævWB‚&F—6V6R"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„F—6V6T†—7F÷'’’çv†W&R„F—6V6T†—7F÷'’æ–Bæ–åò†–G5²&F—6V6R%Ò’ÂF—6V6T†—7F÷'’æFöuö–BÓÒFöræ–B’’æÆÂ‚“ ¢7FGW5öÆ&VÇ2Ò²'G&VFÖVçB#¢.k+¾y˜.KŠÒ"Â&föÆÆ÷wW#¢.{XÎ˜îŠk>Zùò"Â'&V6÷fW&VB#¢.ZèÎk+²"Â&6‡&öæ–2#¢.hZ.h
r'Ğ¢FWF–ÂÒ·7FGW5öÆ&VÇ2ævWB†—FVÒç7FGW2÷"&föÆÆ÷wW"Â.{XÎ˜îŠk>Zùò"•Ğ¢–b—FVÒç7–×Fö×3¢FWF–ÂæVæB†b.yx~x«nûÉ§¶—FVÒç7–×Fö×7Ò"¢–b—FVÒææW‡EöföÆÆ÷wWööã¢FWF–ÂæVæB†b.jÊY¹îŠ‹®ZùşûÉ§¶—FVÒææW‡EöföÆÆ÷wWööçÒ"¢–b—FVÒæ÷væW%öæ÷FW3¢FWF–ÂæVæB†—FVÒæ÷væW%öæ÷FW2¢–æ†W&—FVBæVæB‚†—FVÒæF–væ÷6VEööâ÷"FFRæÖ–âÂ—FVÒæF—6V6UöæÖRÂ%Æâ"æ¦ö–â†FWF–Â’’¢–b6FVv÷'’ÓÒ&fööB"æB–G2ævWB‚&fööB"“ ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„fööD†—7F÷'’’çv†W&R„fööD†—7F÷'’æ–Bæ–åò†–G5²&fööB%Ò’ÂfööD†—7F÷'’æFöuö–BÓÒFöræ–B’’æÆÂ‚“ ¢FWF–ÂÒ².XŠyJKŠÒ"–b†—FVÒç7FGW2÷"&öævö–ær"’ÓÒ&öævö–ær"æBæ÷B—FVÒæVæFVEööâVÇ6R.{X.K¨b%Ğ¢–b—FVÒæÖçVf7GW&W#¢FWF–ÂæVæB†b.8:8;Î8*¾8;ÎûÉ§¶—FVÒæÖçVf7GW&W'Ò"¢–b—FVÒæÖ÷VçEör—2æ÷BæöæS¢FWF–ÂæVæB†b#iz^˜xşûÉ§¶—FVÒæÖ÷VçEös¦wÖr"¢–b—FVÒçF–ÖW5÷W%öF“¢FWF–ÂæVæB†b#izW¶—FVÒçF–ÖW5÷W%öF—ŞY¹â"¢–b—FVÒæ6†ævU÷&V6öã¢FWF–ÂæVæB†b.ZHi»N8;¾{X.K¨nynyKûÉ§¶—FVÒæ6†ævU÷&V6öçÒ"¢–b—FVÒæ÷væW%öæ÷FW3¢FWF–ÂæVæB†—FVÒæ÷væW%öæ÷FW2¢–æ†W&—FVBæVæB‚†—FVÒç7F'FVEööâÂ—FVÒææÖRÂ%Æâ"æ¦ö–â†FWF–Â’’¢–æ†W&—FVBç6÷'B†¶W“ÖÆÖ&F&÷s¢&÷u³ÒÂ&WfW'6SÕG'VR¢–æ†W&—FVE÷&÷w2Ò""æ¦ö–â†bsÇG#ãÇFCç¶F’–bF’ÒFFRæÖ–âVÇ6R"Ò'ÓÂ÷FCãÇFCç¶‡FÖÂæW66R‡F—FÆR—ÓÂ÷FCãÇFB7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†æ÷FR÷""Ò"—ÓÂ÷FCãÇFCãÇ7â6Æ73Ò&&FvR#î89n8:®8;Î888;ÎŠ‰˜Ë.8;¾™k.Šj~8î8óÂ÷7ããÂ÷FCãÂ÷G#ârf÷"F’ÂF—FÆRÂæ÷FR–â–æ†W&—FVB¢6FVv÷'•÷7VÖÖ'’Ò" ¢–b6FVv÷'’ÓÒ'vV–v‡B# ¢vV–v‡E÷ö–çG3¢Æ—7E·GWÆU¶FFRÂfÆöEÕÒÒµĞ¢f÷"F’ÂfÇVRÂò–â–æ†W&—FVC ¢ÖF6‚Ò&Rç6V&6‚‡""…³Ó•Ò²ƒó¥Âå³Ó•Ò²“ò’"ÂfÇVR÷"""¢–bÖF6‚æBF’ÒFFRæÖ–ã¢vV–v‡E÷ö–çG2æVæB‚†F’ÂfÆöB†ÖF6‚æw&÷Wƒ’’’¢f÷"—FVÒ–â&V6÷&G3 ¢ÖF6‚Ò&Rç6V&6‚‡""…³Ó•Ò²ƒó¥Âå³Ó•Ò²“ò’"Â—FVÒçfÇVR÷"""¢–bÖF6ƒ¢vV–v‡E÷ö–çG2æVæB‚†—FVÒç&V6÷&FVEööâÂfÆöB†ÖF6‚æw&÷Wƒ’’’¢vV–v‡E÷ö–çG2ç6÷'B†¶W“ÖÆÖ&Fö–çC¢ö–çE³Ò¢–bvV–v‡E÷ö–çG3 ¢ÆFW7BÒvV–v‡E÷ö–çG5²ÓÕ³Ó²&Wf–÷W2ÒvV–v‡E÷ö–çG5²Ó%Õ³Ò–bÆVâ‡vV–v‡E÷ö–çG2’âVÇ6RæöæP¢F–ffW&Væ6RÒÆFW7BÒ&Wf–÷W2–b&Wf–÷W2—2æ÷BæöæRVÇ6RæöæP¢F–fe÷FW‡BÒbw¶F–ffW&Væ6S¢²ã&gÖ¶rr–bF–ffW&Væ6R—2æ÷BæöæRVÇ6R.jùN‹È>88~8;Î8+ş8®8r ¢fÇVW2Ò·ö–çE³Òf÷"ö–çB–âvV–v‡E÷ö–çG5Ó²Æ÷rÂ†–v‚ÒÖ–â‡fÇVW2’ÂÖ‚‡fÇVW2“²7âÒÖ‚††–v‚ÒÆ÷rÂã"¢6ö÷&G2ÒµĞ¢f÷"–æFW‚Â…òÂfÇVR’–âVçVÖW&FR‡vV–v‡E÷ö–çG2“ ¢‚Ò3B²ƒc“"¢–æFW‚òÖ‚†ÆVâ‡vV–v‡E÷ö–çG2’ÒÂ’“²’Òs‚Ò‚‡fÇVRÒÆ÷r’ò7â¢3‚¢6ö÷&G2æVæB‚‡‚Â’ÂfÇVR’¢öÇ–Æ–æRÒ""æ¦ö–â†b'·ƒ¢ãgÒÇ·“¢ãgÒ"f÷"‚Â’Âò–â6ö÷&G2¢6—&6ÆW2Ò""æ¦ö–â†bsÆ6—&6ÆR7ƒÒ'·ƒ¢ãgÒ"7“Ò'·“¢ãgÒ"#Ò#R#ãÇF—FÆSç·fÇVS¦wÖ¶sÂ÷F—FÆSãÂö6—&6ÆSârf÷"‚Â’ÂfÇVR–â6ö÷&G2¢6FVv÷'•÷7VÖÖ'’ÒbrrsÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÈikKÙ>˜xÓÂöƒ3ãÇ7G&öæsç¶ÆFW7C¦wÖ¶sÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îX˜ŞY¹î88î[zãÂöƒ3ãÇ7G&öæsç¶F–fe÷FW‡GÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îkŠÎZé®Y¹îi[Âöƒ3ãÇ7G&öæsç¶ÆVâ‡vV–v‡E÷ö–çG2—ŞY¹ãÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îŠ‰˜Ë.zøNY»#Âöƒ3ãÇ7G&öæsç¶Æ÷s¦wŞ8	Ç¶†–vƒ¦wÖ¶sÂ÷7G&öæsãÂ÷6V7F–öããÂöF—cãÆƒ#îKÙ>˜xŞhêz{³Âöƒ#ãÆF—b6Æ73Ò&÷væW"×vV–v‡BÖ6†'B#ãÇ7frf–Wt&÷ƒÒ#sc##"&öÆSÒ&–Ör"&–ÖÆ&VÃÒ.KÙ>˜xŞ8îi˜.{;¾X‰~hêz{²#ãÆÆ–æRƒÒ#3B"“Ò#s‚"ƒ#Ò#s#b"“#Ò#s‚#ãÂöÆ–æSãÇöÇ–Æ–æRö–çG3Ò'·öÇ–Æ–æWÒ#ãÂ÷öÇ–Æ–æSç¶6—&6ÆW7ÓÇFW‡BƒÒ#3B"“Ò##r#ç·vV–v‡E÷ö–çG5³Õ³×ÓÂ÷FW‡CãÇFW‡BƒÒ#s#b"“Ò##r"FW‡BÖæ6†÷#Ò&VæB#ç·vV–v‡E÷ö–çG5²ÓÕ³×ÓÂ÷FW‡CãÇFW‡BƒÒ#3B"“Ò##R#ç¶†–vƒ¦wÖ¶sÂ÷FW‡CãÇFW‡BƒÒ#3B"“Ò#“B#ç¶Æ÷s¦wÖ¶sÂ÷FW‡CãÂ÷7fsãÂöF—cãÇ7G–ÆSâæ÷væW"×vV–v‡BÖ6†'G·¶÷fW&fÆ÷r×ƒ¦WFó·FF–æs£'ƒ¶&÷&FW#£‚6öÆ–B6VFfS¶&÷&FW"×&F—W3£Gƒ¶&6¶w&÷VæC¢6ffff'×Òæ÷væW"×vV–v‡BÖ6†'B7fw·¶F—7Æ“¦&Æö6³·v–GFƒ£S¶Ö–â×v–GFƒ£Scƒ¶†V–v‡C¦WF÷×Òæ÷væW"×vV–v‡BÖ6†'BÆ–æW··7G&ö¶S¢6C–3–6S·7G&ö¶R×v–GFƒ£×Òæ÷væW"×vV–v‡BÖ6†'BöÇ–Æ–æW·¶f–ÆÃ¦æöæS·7G&ö¶S¢6#cfcv3·7G&ö¶R×v–GFƒ£C·7G&ö¶RÖÆ–æV6§&÷VæC·7G&ö¶RÖÆ–æV¦ö–ã§&÷VæG×Òæ÷væW"×vV–v‡BÖ6†'B6—&6ÆW·¶f–ÆÃ¢3sCCSC·7G&ö¶S¢6ffc·7G&ö¶R×v–GFƒ£'×Òæ÷væW"×vV–v‡BÖ6†'BFW‡G·¶f–ÆÃ¢3ƒf#s#¶föçB×6—¦S£'‡×ÓÂ÷7G–ÆSârrp¢VÇ6S ¢6FVv÷'•÷7VÖÖ'’ÒsÆF—b6Æ73Ò'FVæçB#ãÇîKÙ>˜xŞ8).y›¾˜Ë.88(¾88iÈikKÙ>˜xŞ8;¾X˜ŞY¹î[zî8;¾i˜.{;¾X‰~8+8:89^8ÎŠzK®8^8(Î8î88#Â÷ãÂöF—câp¢VÆ–b6FVv÷'’ÓÒ'f66–æF–öâ# ¢'&VVFW%÷f66–æW2Ò6W76–öâç66Æ'2‡6VÆV7B…f66–æF–öâ’çv†W&R…f66–æF–öâæ–Bæ–åò†–G2ævWB‚'f66–æF–öâ"Â³Ò’’Âf66–æF–öâæFöuö–BÓÒFöræ–B’æ÷&FW%ö'’…f66–æF–öâæFÖ–æ—7FW&VEööâæFW62‚’’’æÆÂ‚¢ÆÅöFFW2Ò¶—FVÒæFÖ–æ—7FW&VEööâf÷"—FVÒ–â'&VVFW%÷f66–æW5Ò²¶—FVÒç&V6÷&FVEööâf÷"—FVÒ–â&V6÷&G5Ğ¢GVUöFFW2Ò¶—FVÒææW‡EöGVUööâf÷"—FVÒ–â'&VVFW%÷f66–æW2–b—FVÒææW‡EöGVUööåÒ²¶—FVÒææW‡EöGVUööâf÷"—FVÒ–â&V6÷&G2–b—FVÒææW‡EöGVUööåĞ¢÷fW&GVRÒ¶F’f÷"F’–âGVUöFFW2–bF’ÂFFRçFöF’‚•Ğ¢W6öÖ–ærÒ¶F’f÷"F’–âGVUöFFW2–bFFRçFöF’‚’ÃÒF’ÃÒFFRçFöF’‚’²F–ÖVFVÇF†F—3Ó3•Ğ¢æW‡EöFFRÒÖ–â‚†F’f÷"F’–âGVUöFFW2–bF’ãÒFFRçFöF’‚’’ÂFVfVÇCÔæöæR¢6FVv÷'•÷7VÖÖ'’ÒbrrsÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÈ{X.hê^zŠîizSÂöƒ3ãÇ7G&öæsç¶Ö‚†ÆÅöFFW2’–bÆÅöFFW2VÇ6R.Š‰˜Ë.8®8r'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îjÊY¹îK¨Zé£Âöƒ3ãÇ7G&öæsç¶æW‡EöFFR÷".iÊ®ŠŠŞZé¢'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3ã3iz^Kº^XhSÂöƒ3ãÇ7G&öæsç¶ÆVâ‡W6öÖ–ær—ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÉş™™‹h^˜ãÂöƒ3ãÇ7G&öær6Æ73Ò'²vW'&÷"r–b÷fW&GVRVÇ6RrwÒ#ç¶ÆVâ†÷fW&GVR—ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÂöF—cârrp¢VÆ–b6FVv÷'’ÓÒ&6†V6·W# ¢'&VVFW%ö6†V6·W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò†–G2ævWB‚&†VÇF‚"Â³Ò’’Â†VÇF…&V6÷&BæFöuö–BÓÒFöræ–BÂ†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&6†V6·W"’æ÷&FW%ö'’„†VÇF…&V6÷&Bç&V6÷&EöFFRæFW62‚’’’æÆÂ‚¢ÆÅöFFW2Ò¶—FVÒç&V6÷&EöFFRf÷"—FVÒ–â'&VVFW%ö6†V6·W5Ò²¶—FVÒç&V6÷&FVEööâf÷"—FVÒ–â&V6÷&G5Ğ¢GVUöFFW2Ò¶—FVÒææW‡EöGVUööâf÷"—FVÒ–â'&VVFW%ö6†V6·W2–b—FVÒææW‡EöGVUööåÒ²¶—FVÒææW‡EöGVUööâf÷"—FVÒ–â&V6÷&G2–b—FVÒææW‡EöGVUööåĞ¢÷fW&GVRÒ¶F’f÷"F’–âGVUöFFW2–bF’ÂFFRçFöF’‚•Ó²W6öÖ–ærÒ¶F’f÷"F’–âGVUöFFW2–bFFRçFöF’‚’ÃÒF’ÃÒFFRçFöF’‚’²F–ÖVFVÇF†F—3Ó3•Ğ¢æW‡EöFFRÒÖ–â‚†F’f÷"F’–âGVUöFFW2–bF’ãÒFFRçFöF’‚’’ÂFVfVÇCÔæöæR¢GFVçF–öâÒ7VÒƒf÷"—FVÒ–â'&VVFW%ö6†V6·W2–b—FVÒç&W7VÇE÷7VÖÖ'’–â²&föÆÆ÷wW"Â'&V6†V6²"Â'G&VFÖVçB'Ò’²7VÒƒf÷"—FVÒ–â&V6÷&G2–b—FVÒçfÇVR–â².{XÎ˜îŠk>Zùò"Â.XhŞjIÎiû²"Â.k+¾y˜.8;¾Xù~Š‹®8Î[ø^Šh'Ò¢6FVv÷'•÷7VÖÖ'’ÒbrrsÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÈ{X.Xù~Š‹®izSÂöƒ3ãÇ7G&öæsç¶Ö‚†ÆÅöFFW2’–bÆÅöFFW2VÇ6R.Š‰˜Ë.8®8r'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îjÊY¹îK¨Zé£Âöƒ3ãÇ7G&öæsç¶æW‡EöFFR÷".iÊ®ŠŠŞZé¢'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îŠhz+®Š¨Ş8î{YiéÃÂöƒ3ãÇ7G&öæsç¶GFVçF–öçŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÉş™™™i>‹ù8;¾‹h^˜ãÂöƒ3ãÇ7G&öær6Æ73Ò'²vW'&÷"r–b÷fW&GVRVÇ6RrwÒ#ç¶ÆVâ‡W6öÖ–ær—ŞK»n8;·¶ÆVâ†÷fW&GVR—ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÂöF—cârrp¢VÆ–b6FVv÷'’ÓÒ&ÖVF–6F–öâ# ¢'&VVFW%öÖVF–6F–öç2Ò6W76–öâç66Æ'2‡6VÆV7B„ÖVF–6F–öâ’çv†W&R„ÖVF–6F–öâæ–Bæ–åò†–G2ævWB‚&ÖVF–6F–öâ"Â³Ò’’ÂÖVF–6F–öâæFöuö–BÓÒFöræ–B’æ÷&FW%ö'’„ÖVF–6F–öâæFÖ–æ—7FW&VEööâæFW62‚’’’æÆÂ‚¢ÆÅöFFW2Ò¶—FVÒæFÖ–æ—7FW&VEööâf÷"—FVÒ–â'&VVFW%öÖVF–6F–öç5Ò²¶—FVÒç&V6÷&FVEööâf÷"—FVÒ–â&V6÷&G5Ğ¢GVUöFFW2Ò¶—FVÒææW‡EöGVUööâf÷"—FVÒ–â'&VVFW%öÖVF–6F–öç2–b—FVÒææW‡EöGVUööâæB—FVÒç7FGW2Ò&6ö×ÆWFVB%Ò²¶—FVÒææW‡EöGVUööâf÷"—FVÒ–â&V6÷&G2–b—FVÒææW‡EöGVUööâæB—FVÒçfÇVRÒ.{X.K¨b%Ğ¢÷fW&GVRÒ¶F’f÷"F’–âGVUöFFW2–bF’ÂFFRçFöF’‚•Ó²W6öÖ–ærÒ¶F’f÷"F’–âGVUöFFW2–bFFRçFöF’‚’ÃÒF’ÃÒFFRçFöF’‚’²F–ÖVFVÇF†F—3Ó3•Ğ¢öævö–ærÒ7VÒƒf÷"—FVÒ–â'&VVFW%öÖVF–6F–öç2–b—FVÒç7FGW2ÓÒ&öævö–ær"’²7VÒƒf÷"—FVÒ–â&V6÷&G2–b—FVÒçfÇVRÓÒ.{i{i®KŠÒ"¢æW‡EöFFRÒÖ–â‚†F’f÷"F’–âGVUöFFW2–bF’ãÒFFRçFöF’‚’’ÂFVfVÇCÔæöæR¢6FVv÷'•÷7VÖÖ'’ÒbrrsÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÈ{X.h©^‰jÎŠ‰˜Ë#Âöƒ3ãÇ7G&öæsç¶Ö‚†ÆÅöFFW2’–bÆÅöFFW2VÇ6R.Š‰˜Ë.8®8r'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3î{i{i®KŠÓÂöƒ3ãÇ7G&öæsç¶öævö–æwŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îjÊY¹îK¨Zé£Âöƒ3ãÇ7G&öæsç¶æW‡EöFFR÷".iÊ®ŠŠŞZé¢'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÉş™™™i>‹ù8;¾‹h^˜ãÂöƒ3ãÇ7G&öær6Æ73Ò'²vW'&÷"r–b÷fW&GVRVÇ6RrwÒ#ç¶ÆVâ‡W6öÖ–ær—ŞK»n8;·¶ÆVâ†÷fW&GVR—ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÂöF—cârrp¢VÆ–b6FVv÷'’ÓÒ&F—6V6R# ¢'&VVFW%öF—6V6W2Ò6W76–öâç66Æ'2‡6VÆV7B„F—6V6T†—7F÷'’’çv†W&R„F—6V6T†—7F÷'’æ–Bæ–åò†–G2ævWB‚&F—6V6R"Â³Ò’’ÂF—6V6T†—7F÷'’æFöuö–BÓÒFöræ–B’æ÷&FW%ö'’„F—6V6T†—7F÷'’æF–væ÷6VEööâæFW62‚’’’æÆÂ‚¢ÆÅöFFW2Ò¶—FVÒæF–væ÷6VEööâf÷"—FVÒ–â'&VVFW%öF—6V6W2–b—FVÒæF–væ÷6VEööåÒ²¶—FVÒç&V6÷&FVEööâf÷"—FVÒ–â&V6÷&G5Ğ¢GVUöFFW2Ò¶—FVÒææW‡EöföÆÆ÷wWööâf÷"—FVÒ–â'&VVFW%öF—6V6W2–b—FVÒææW‡EöföÆÆ÷wWööâæB—FVÒç7FGW2Ò'&V6÷fW&VB%Ò²¶—FVÒææW‡EöGVUööâf÷"—FVÒ–â&V6÷&G2–b—FVÒææW‡EöGVUööâæB—FVÒçfÇVRÒ.ZèÎk+²%Ğ¢÷fW&GVRÒ¶F’f÷"F’–âGVUöFFW2–bF’ÂFFRçFöF’‚•Ó²W6öÖ–ærÒ¶F’f÷"F’–âGVUöFFW2–bFFRçFöF’‚’ÃÒF’ÃÒFFRçFöF’‚’²F–ÖVFVÇF†F—3Ó3•Ğ¢7F—fUö6÷VçBÒ7VÒƒf÷"—FVÒ–â'&VVFW%öF—6V6W2–b—FVÒç7FGW2–â²'G&VFÖVçB"Â&föÆÆ÷wW"Â&6‡&öæ–2'Ò’²7VÒƒf÷"—FVÒ–â&V6÷&G2–b—FVÒçfÇVR–â².k+¾y˜.KŠÒ"Â.{XÎ˜îŠk>Zùò"Â.hZ.h
r'Ò¢&V7W'&Væ6Uö6÷VçBÒ7VÒƒf÷"—FVÒ–â'&VVFW%öF—6V6W2–b—FVÒç&V7W'&Væ6R’²7VÒƒf÷"—FVÒ–â&V6÷&G2–b.XhŞy›®ûÉ®8ş8B"–â†—FVÒæFWF–Ç2÷"""’¢6FVv÷'•÷7VÖÖ'’ÒbrrsÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÈ{X.Š‹®ijŞ8;¾Š‰˜Ë.izSÂöƒ3ãÇ7G&öæsç¶Ö‚†ÆÅöFFW2’–bÆÅöFFW2VÇ6R.Š‰˜Ë.8®8r'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îk+¾y˜.8;¾Šk>Zùş8;¾hZ.h
sÂöƒ3ãÇ7G&öæsç¶7F—fUö6÷VçGŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îXhŞy›®Š‰˜Ë#Âöƒ3ãÇ7G&öæsç·&V7W'&Væ6Uö6÷VçGŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÉş™™™i>‹ù8;¾‹h^˜ãÂöƒ3ãÇ7G&öær6Æ73Ò'²vW'&÷"r–b÷fW&GVRVÇ6RrwÒ#ç¶ÆVâ‡W6öÖ–ær—ŞK»n8;·¶ÆVâ†÷fW&GVR—ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÂöF—cârrp¢VÆ–b6FVv÷'’ÓÒ&fööB# ¢'&VVFW%öfööG2Ò6W76–öâç66Æ'2‡6VÆV7B„fööD†—7F÷'’’çv†W&R„fööD†—7F÷'’æ–Bæ–åò†–G2ævWB‚&fööB"Â³Ò’’ÂfööD†—7F÷'’æFöuö–BÓÒFöræ–B’æ÷&FW%ö'’„fööD†—7F÷'’ç7F'FVEööâæFW62‚’’’æÆÂ‚¢'&VVFW%ö7F—fRÒ¶—FVÒf÷"—FVÒ–â'&VVFW%öfööG2–b†—FVÒç7FGW2÷"&öævö–ær"’ÓÒ&öævö–ær"æBæ÷B—FVÒæVæFVEööåĞ¢÷væW%ö7F—fRÒ¶—FVÒf÷"—FVÒ–â&V6÷&G2–b—FVÒçfÇVRÓÒ.XŠyJKŠÒ%Ğ¢7F—fUöæÖW2Ò¶—FVÒææÖRf÷"—FVÒ–â'&VVFW%ö7F—fUÒ²¶—FVÒçF—FÆRf÷"—FVÒ–â÷væW%ö7F—fUĞ¢ÆFW7EöFFW2Ò¶—FVÒç7F'FVEööâf÷"—FVÒ–â'&VVFW%öfööG5Ò²¶—FVÒç&V6÷&FVEööâf÷"—FVÒ–â&V6÷&G5Ğ¢6ö×ÆWFVEö6÷VçBÒ7VÒƒf÷"—FVÒ–â'&VVFW%öfööG2–b—FVÒæVæFVEööâ÷"—FVÒç7FGW2ÓÒ&6ö×ÆWFVB"’²7VÒƒf÷"—FVÒ–â&V6÷&G2–b—FVÒçfÇVRÓÒ.{X.K¨b"¢6FVv÷'•÷7VÖÖ'’ÒbrrsÆF—b6Æ73Ò&w&–B#ãÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îxûîYÊXŠyJKŠÓÂöƒ3ãÇ7G&öæsç¶ÆVâ†7F—fUöæÖW2—ŞK»cÂ÷7G&öæsãÇç¶‡FÖÂæW66R‚.8"æ¦ö–â†7F—fUöæÖW2’÷".y›¾˜Ë.8®8r"—ÓÂ÷ãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îiÈikZHi»NizSÂöƒ3ãÇ7G&öæsç¶Ö‚†ÆFW7EöFFW2’–bÆFW7EöFFW2VÇ6R.Š‰˜Ë.8®8r'ÓÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3î{X.K¨nkˆ8óÂöƒ3ãÇ7G&öæsç¶6ö×ÆWFVEö6÷VçGŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ3îXŠyJ[^jÛCÂöƒ3ãÇ7G&öæsç¶ÆVâ†'&VVFW%öfööG2’²ÆVâ‡&V6÷&G2—ŞK»cÂ÷7G&öæsãÂ÷6V7F–öããÂöF—cârrp¢÷væW%÷&÷w2Ò" ¢f÷"—FVÒ–â&V6÷&G3 ¢÷væW"Ò6W76–öâævWB…W6W"Â—FVÒæ÷væW%ö–B¢66†VGVÆRÒ" ¢–b6FVv÷'’–â²'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R'ÒæB—FVÒææW‡EöGVUööã ¢66†VGVÆRÒsÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6cF3–6¶6öÆ÷#¢3†C33r#îiÉş™™‹h^˜ãÂ÷7ãâr–b—FVÒææW‡EöGVUööâÂFFRçFöF’‚’VÇ6R‚sÇ7â6Æ73Ò&&FvR"7G–ÆSÒ&&6¶w&÷VæC¢6cfS#ƒ¶6öÆ÷#¢3sSSSB#îiÉş™™™i>‹ùÂ÷7ãâr–b—FVÒææW‡EöGVUööâÃÒFFRçFöF’‚’²F–ÖVFVÇF†F—3Ó3’VÇ6RbsÇ7â6Æ73Ò&&FvR#îjÊY¹â¶—FVÒææW‡EöGVUööçÓÂ÷7ãâr¢6W'F–f–6FRÒbsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷&V6÷&G2÷¶—FVÒæ–GÒöGF6†ÖVçB"F&vWCÒ%ö&Ææ²#îk{¾K¹89^8*8*N8:¾8).Šh¾8(³Âöâr–b—FVÒæGF6†ÖVçEöFFVÇ6R" ¢–b—FVÒæ÷væW%ö–BÓÒW6W"æ–C ¢7F–öâÒbrrsÆFWF–Ç3ãÇ7VÖÖ'“î{z™¸n8;¾ŠªNXZ^X©¾KúîjÚ3Â÷7VÖÖ'“ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷&V6÷&G2÷¶—FVÒæ–GÒ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&6FVv÷'’"fÇVSÒ'¶6FVv÷'—Ò#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'&WGW&å÷Fò"fÇVSÒ'¶6FVv÷'—Ò#ãÆÆ&VÃîŠ‰˜Ë.izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ'¶—FVÒç&V6÷&FVEööçÒ"&WV—&VCãÆÆ&VÃîŠ‰˜Ë.Xh^Zë“ÂöÆ&VÃãÆ–çWBæÖSÒ'F—FÆR"fÇVSÒ'¶‡FÖÂæW66R†—FVÒçF—FÆR—Ò"&WV—&VBÖ†ÆVæwFƒÒ#S#ãÆÆ&VÃîi[X
N8;¾Š9Î‹k3ÂöÆ&VÃãÆ–çWBæÖSÒ'fÇVR"fÇVSÒ'¶‡FÖÂæW66R†—FVÒçfÇVR÷"rr—Ò"Ö†ÆVæwFƒÒ#S#ãÆÆ&VÃîŠ›>{K8;¾8:8:#ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FWF–Ç2#ç¶‡FÖÂæW66R†—FVÒæFWF–Ç2÷"rr—ÓÂ÷FW‡F&VãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†&U÷Fõö'&VVFW""fÇVSÒ'G'VR"²v6†V6¶VBr–b—FVÒç6†&U÷Fõö'&VVFW"VÇ6RrwÓâ89n8:®8;Î888;Î8X[iÈ88(³ÂöÆ&VÃãÆ'WGFöãîZHi»N8).KùŞZÙƒÂö'WGFöããÂöf÷&ÓãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷&V6÷&G2÷¶—FVÒæ–GÒöFVÆWFR#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'&WGW&å÷Fò"fÇVSÒ'¶6FVv÷'—Ò#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&ÕöFVÆWFR"fÇVSÒ'G'VR"&WV—&VCâ8>8îŠ‰˜Ë.8).ZèÎXZ8¾X˜®™šN88(¾8>88).z+®Š¨Ş8~8î8~8óÂöÆ&VÃãÆ'WGFöâ6Æ73Ò&FævW"#îŠ‰˜Ë.8).X˜®™šCÂö'WGFöããÂöf÷&ÓãÂöFWF–Ç3ârrp¢VÇ6S¢7F–öâÒsÇ7â6Æ73Ò&&FvR#î˜îXë¾8*®8;Î88®8;ÎŠ‰˜Ë.8;¾ZHi»NKˆŞXúóÂ÷7ãâp¢÷væW%÷&÷w2³ÒbrrsÇG#ãÇFCç¶—FVÒç&V6÷&FVEööçÓÆ'#ç·66†VGVÆWÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒçF—FÆR—×¶b"ûÈò¶‡FÖÂæW66R†—FVÒçfÇVR—Ò"–b—FVÒçfÇVRVÇ6R"'ÓÂ÷FCãÇFB7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†—FVÒæFWF–Ç2÷""Ò"—ÓÆ'#ç¶6W'F–f–6FWÓÂ÷FCãÇFCç¶‡FÖÂæW66R†÷væW"ææÖR–b÷væW"VÇ6R.˜îXë¾8î8*®8;Î88®8;Â"—ÓÆ'#ç²~89n8:®8;Î888;ÎX[iÈKŠÒr–b—FVÒç6†&U÷Fõö'&VVFW"VÇ6R~89n8:®8;Î888;Î™ÙîX[iÈ’wÓÆ'#ç¶7F–öçÓÂ÷FCãÂ÷G#ârrp¢f÷&×2Ò°¢'vV–v‡B#¢sÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃîkŠÎZé®izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ"r²7G"†FFRçFöF’‚’’²r"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃîKÙ>˜xŞûÈ†¶~ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&çVÖ&W""7FWÒ#ã"Ö–ãÒ#ã"æÖSÒ'vV–v‡Eö¶r"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃîX^[«~x«nhX³ÂöÆ&VÃãÇ6VÆV7BæÖSÒ&6öæF—F–öâ#ãÆ÷F–öãîˆšşZ[ÓÂö÷F–öããÆ÷F–öãî[	8~h*®8CÂö÷F–öããÆ÷F–öãîh*®8CÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÂöF—cârÀ¢'f66–æF–öâ#¢sÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃîhê^zŠîizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ"r²7G"†FFRçFöF’‚’’²r"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃî8:ş8*ş888;>XË®XˆcÂöÆ&VÃãÇ6VÆV7BæÖSÒ'f66–æU÷G—R#ãÆ÷F–öâfÇVSÒ'&&–W2#îx¸.xªÎyxSÂö÷F–öããÆ÷F–öâfÇVSÒ&Ö—†VB#îk{~Y8:ş8*ş888;3Âö÷F–öããÆ÷F–öâfÇVSÒ&÷F†W"#î8Ş8îK¹cÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃî8:ş8*ş888;>YÓÂöÆ&VÃãÆ–çWBæÖSÒ'f66–æUöæÖR"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃîZÙxªÎiÉş8îhê^zŠîšnûÈK»¾hHşûÈ“ÂöÆ&VÃãÇ6VÆV7BæÖSÒ&F÷6R#ãÆ÷F–öâfÇVSÒ"#îh‰xªÎ8;¾XZ^X©¾KˆŞŠhÂö÷F–öããÆ÷F–öããY¹îyºãÂö÷F–öããÆ÷F–öãã.Y¹îyºãÂö÷F–öããÆ÷F–öãã>Y¹îyºãÂö÷F–öããÆ÷F–öãî‹ûŞXªhê^zŠãÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîjÊY¹îK¨Zé®izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&æW‡EöGVUööâ#ãÂöF—cãÆF—cãÆÆ&VÃîX¹^xšyx^™š#ÂöÆ&VÃãÆ–çWBæÖSÒ&6Æ–æ–2#ãÂöF—cãÂöF—cãÆÆ&VÃîhê^zŠîŠ‹Îiˆîi»8;¾XiyÉşûÈ…Dn8;´¥~8;µä~ûÈó„Ô.8î8~ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&f–ÆR"æÖSÒ&GF6†ÖVçEöf–ÆR"66WCÒ&Æ–6F–öâ÷FbÆ–ÖvRö§VrÆ–ÖvR÷ær#ârÀ¢&6†V6·W#¢sÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃîXù~Š‹®izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ"r²7G"†FFRçFöF’‚’’²r"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃî{YiéÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&W7VÇB#ãÆ÷F–öãîy[[‹8®8sÂö÷F–öããÆ÷F–öãî{XÎ˜îŠk>ZùóÂö÷F–öããÆ÷F–öãîXhŞjIÎiû³Âö÷F–öããÆ÷F–öãîk+¾y˜.8;¾Xù~Š‹®8Î[ø^ŠhÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîjÊY¹îK¨Zé®izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&æW‡EöGVUööâ#ãÂöF—cãÆF—cãÆÆ&VÃîX¹^xšyx^™š#ÂöÆ&VÃãÆ–çWBæÖSÒ&6Æ–æ–2#ãÂöF—cãÂöF—cãÆÆ&VÃîX^Š‹®š^yºãÂöÆ&VÃãÆF—b6Æ73Ò&w&–B#ãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'‡—6–6ÅöW†Ò#âŠznŠ‹£ÂöÆ&VÃãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&&ÆööE÷FW7B#âŠkk.jIÎiû³ÂöÆ&VÃãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'VÇG&6÷VæB#â8*8+>8;ÃÂöÆ&VÃãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&6†W7E÷‡&’#âˆ;˜:…{y£ÂöÆ&VÃãÂöF—cãÆÆ&VÃîjIÎiû¾{YiéÎûÈ…Dn8;´¥~8;µä~ûÈó„Ô.8î8~ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&f–ÆR"æÖSÒ&GF6†ÖVçEöf–ÆR"66WCÒ&Æ–6F–öâ÷FbÆ–ÖvRö§VrÆ–ÖvR÷ær#ârÀ¢&ÖVF–6F–öâ#¢sÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃîŠ‰˜Ë.izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ"r²7G"†FFRçFöF’‚’’²r"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃî‰jÎXšNYÓÂöÆ&VÃãÆ–çWBæÖSÒ&ÖVF–6–æUöæÖR"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃîXË®XˆcÂöÆ&VÃãÇ6VÆV7BæÖSÒ&ÖVF–6F–öå÷G—R#ãÆ÷F–öâfÇVSÒ'G&VFÖVçB#îk+¾y˜.‰jÃÂö÷F–öããÆ÷F–öâfÇVSÒ'&WfVçF–öâ#îK¨™‹.‰jÃÂö÷F–öããÆ÷F–öâfÇVSÒ'7WÆVÖVçB#î8+^89~8:®8:8;>88ƒÂö÷F–öããÆ÷F–öâfÇVSÒ&÷F†W"#î8Ş8îK¹cÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîyºîy¨N8;¾Zûî‹yx~x«cÂöÆ&VÃãÆ–çWBæÖSÒ'W'÷6R#ãÂöF—cãÆF—cãÆÆ&VÃãY¹î˜xóÂöÆ&VÃãÆ–çWBæÖSÒ&F÷6vR"Æ6V†öÆFW#Ò.Kè¾ûÉ£˜Ê8"ãVÖÂ#ãÂöF—cãÆF—cãÆÆ&VÃîh©^‰jÎš¾[ªcÂöÆ&VÃãÆ–çWBæÖSÒ&g&WVVæ7’"Æ6V†öÆFW#Ò.Kè¾ûÉ£izS.Y¹î8jøîiÈƒY¹â#ãÂöF—cãÆF—cãÆÆ&VÃî™h¾Zx¾izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'7F'FVEööâ#ãÂöF—cãÆF—cãÆÆ&VÃî{X.K¨nizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&VæFVEööâ#ãÂöF—cãÆF—cãÆÆ&VÃîx«nhX³ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&V6÷&E÷7FGW2#ãÆ÷F–öãîXÙY¹ãÂö÷F–öããÆ÷F–öãî{i{i®KŠÓÂö÷F–öããÆ÷F–öãî{X.K¨cÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîjÊY¹îK¨Zé®izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&æW‡EöGVUööâ#ãÂöF—cãÆF—cãÆÆ&VÃîX¹^xšyx^™š#ÂöÆ&VÃãÆ–çWBæÖSÒ&6Æ–æ–2#ãÂöF—cãÂöF—cârÀ¢&F—6V6R#¢sÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃîŠ‹®ijŞizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ"r²7G"†FFRçFöF’‚’’²r"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃîykîh*>YÓÂöÆ&VÃãÆ–çWBæÖSÒ&F—6V6UöæÖR"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃîXˆnšãÂöÆ&VÃãÇ6VÆV7BæÖSÒ&F—6V6Uö6FVv÷'’#ãÆ÷F–öâfÇVSÒ&F–vW7F—fR#îkhXÉnYšƒÂö÷F–öããÆ÷F–öâfÇVSÒ'&W7—&F÷'’#îYÎYYšƒÂö÷F–öããÆ÷F–öâfÇVSÒ'6¶–â#îyªîˆi£Âö÷F–öããÆ÷F–öâfÇVSÒ&÷'F†÷VF–2#îi[N[Ú.8;¾™j.zøÂö÷F–öããÆ÷F–öâfÇVSÒ&6&F–2#î[ê®y+YšƒÂö÷F–öããÆ÷F–öâfÇVSÒ'W&–æ'’#îk8Î[şYšƒÂö÷F–öããÆ÷F–öâfÇVSÒ'&W&öGV7F—fR#îyIşjénYšƒÂö÷F–öããÆ÷F–öâfÇVSÒ&–æfV7F–÷W2#îhIşiù>yxsÂö÷F–öããÆ÷F–öâfÇVSÒ&÷F†W"#î8Ş8îK¹cÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîx«nhX³ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&V6÷&E÷7FGW2#ãÆ÷F–öãîk+¾y˜.KŠÓÂö÷F–öããÆ÷F–öãî{XÎ˜îŠk>ZùóÂö÷F–öããÆ÷F–öãîZèÎk+³Âö÷F–öããÆ÷F–öãîhZ.h
sÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîk+¾y˜.™h¾Zx¾izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'G&VFÖVçE÷7F'FVEööâ#ãÂöF—cãÆF—cãÆÆ&VÃîk+¾y˜.{X.K¨nizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'G&VFÖVçEöVæFVEööâ#ãÂöF—cãÆF—cãÆÆ&VÃîX¹^xšyx^™š#ÂöÆ&VÃãÆ–çWBæÖSÒ&6Æ–æ–2#ãÂöF—cãÆF—cãÆÆ&VÃîh¸^[Ù>xÚ>XË¾[Š³ÂöÆ&VÃãÆ–çWBæÖSÒ'fWFW&–æ&–â#ãÂöF—cãÆF—cãÆÆ&VÃîjÊY¹îŠ‹®ZùşizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&æW‡EöGVUööâ#ãÂöF—cãÂöF—cãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'&V7W'&Væ6R"fÇVSÒ'G'VR#âYÎ8ykîh*>8îXhŞy›®88~8nŠ‰˜Ë.88(³ÂöÆ&VÃãÆÆ&VÃîyx~x«cÂöÆ&VÃãÇFW‡F&VæÖSÒ'7–×Fö×2#ãÂ÷FW‡F&VârÀ¢&fööB#¢sÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃîXŠyJ™h¾Zx¾izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'&V6÷&FVEööâ"fÇVSÒ"r²7G"†FFRçFöF’‚’’²r"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃî89^8;Î88YÓÂöÆ&VÃãÆ–çWBæÖSÒ&fööEöæÖR"&WV—&VCãÂöF—cãÆF—cãÆÆ&VÃî8:8;Î8*¾8;ÃÂöÆ&VÃãÆ–çWBæÖSÒ&ÖçVf7GW&W"#ãÂöF—cãÆF—cãÆÆ&VÃîzŠîšãÂöÆ&VÃãÇ6VÆV7BæÖSÒ&fööE÷G—R#ãÆ÷F–öâfÇVSÒ&G'’#î888:8*CÂö÷F–öããÆ÷F–öâfÇVSÒ'vWB#î8*n8*~88>88ƒÂö÷F–öããÆ÷F–öâfÇVSÒ'&r#îyIşš9óÂö÷F–öããÆ÷F–öâfÇVSÒ'&W67&—F–öâ#îy˜.k9^š9óÂö÷F–öããÆ÷F–öâfÇVSÒ'7WÆVÖVçB#î8+^89~8:®8:8;>88ƒÂö÷F–öããÆ÷F–öâfÇVSÒ&÷F†W"#î8Ş8îK¹cÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃãiz^˜xşûÈ†~ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&çVÖ&W""7FWÒ#ã"Ö–ãÒ#ã"æÖSÒ&Ö÷VçEör#ãÂöF—cãÆF—cãÆÆ&VÃãiz^8î{ZnKˆîY¹îi[ÂöÆ&VÃãÆ–çWBG—SÒ&çVÖ&W""Ö–ãÒ#"ÖƒÒ#"æÖSÒ'F–ÖW5÷W%öF’#ãÂöF—cãÆF—cãÆÆ&VÃîx«nhX³ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&V6÷&E÷7FGW2#ãÆ÷F–öãîXŠyJKŠÓÂö÷F–öããÆ÷F–öãî{X.K¨cÂö÷F–öããÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîXŠyJ{X.K¨nizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&VæFVEööâ#ãÂöF—cãÆF—cãÆÆ&VÃîZHi»N8;¾{X.K¨nynyKÂöÆ&VÃãÆ–çWBæÖSÒ&6†ævU÷&V6öâ#ãÂöF—cãÂöF—câp¢Ğ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚#î8n88îZÙX^[«~zêyn8h‹¾8(³ÂöãÆƒç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8ç¶Æ&VÇ5¶6FVv÷'•×ŞzêycÂöƒãÇîZûî‹xªÎ8÷¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8¾Y»®Zé®8^8(Î8n8N8î88#Â÷ç¶6FVv÷'•÷7VÖÖ'—Ğ¢Æƒ#ç¶Æ&VÇ5¶6FVv÷'•×ŞŠ‰˜Ë.8).‹ûŞXªÂöƒ#ãÆf÷&Ò6Æ73Ò&†VÇF‚ÖVçG'’Öf÷&Ò"ÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷¶6FVv÷'—Ò÷&V6÷&G2"Væ7G—SÒ&×VÇF—'Böf÷&ÒÖFF#ç¶f÷&×5¶6FVv÷'•×ÓÆÆ&VÃîŠ›>{K8;¾8:8:#ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FWF–Ç2#ãÂ÷FW‡F&VãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†&U÷Fõö'&VVFW""fÇVSÒ'G'VR#â89n8:®8;Î888;Î8X[iÈ88(³ÂöÆ&VÃãÇ6ÖÆÃîX[iÈXXûÉ§¶‡FÖÂæW66R‡FVæçBææÖR–bFVæçBVÇ6R~ZY{HNxªÎˆˆâr—Ş8.89n8:®8;Î888;Î8ş™k.Šj~8î8ş8~ZHi»N8;¾X˜®™šN8~8Ş8î8¾8)>8#Â÷6ÖÆÃãÆ'WGFöãç¶Æ&VÇ5¶6FVv÷'•×ŞŠ‰˜Ë.8).‹ûŞXªÂö'WGFöããÂöf÷&Óà¢Æƒ#î89n8:®8;Î888;Î8¾8([É^8Ş{i8N8Š‰˜Ë#Âöƒ#ãÆF—b7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆSãÇG#ãÇFƒîiz^K¹ƒÂ÷FƒãÇFƒîXh^Zë“Â÷FƒãÇFƒî8:8:#Â÷FƒãÇFƒîjŠ™™Â÷FƒãÂ÷G#ç¶–æ†W&—FVE÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îX[iÈ8^8(Î8şŠ‰˜Ë.8ş8î88.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSãÂöF—cà¢Æƒ#î8*®8;Î88®8;Î8Î{i{i®XZ^X©¾8~8şŠ‰˜Ë#Âöƒ#ãÆF—b7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆSãÇG#ãÇFƒîiz^K¹ƒÂ÷FƒãÇFƒîXh^Zë“Â÷FƒãÇFƒîŠ›>{KÂ÷FƒãÇFƒîXZ^X©¾ˆ^8;¾i8ŞKÙÃÂ÷FƒãÂ÷G#ç¶÷væW%÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#î8*®8;Î88®8;ÎŠ‰˜Ë.8ş8î88.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSãÂöF—cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶Föræ6ÆÅöæÖWŞ8ç¶Æ&VÇ5¶6FVv÷'•×ŞzêynûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷¶6FVv÷'—Ò÷&V6÷&G2"¦7–æ2FVbfÖ–Ç•ö÷væW%ö†VÇF…ö6FVv÷'•ö7&VFR†Föuö–C¢–çBÂ6FVv÷'“¢7G"Â&V6÷&FVEööã¢7G"Òf÷&Ò‚âââ’ÂvV–v‡Eö¶s¢7G"Òf÷&Ò‚""’Â6öæF—F–öã¢7G"Òf÷&Ò‚""’Âf66–æU÷G—S¢7G"Òf÷&Ò‚&÷F†W""’Âf66–æUöæÖS¢7G"Òf÷&Ò‚""’ÂF÷6S¢7G"Òf÷&Ò‚""’ÂæW‡EöGVUööã¢7G"Òf÷&Ò‚""’Â6Æ–æ–3¢7G"Òf÷&Ò‚""’Â&W7VÇC¢7G"Òf÷&Ò‚""’Â‡—6–6ÅöW†Ó¢&ööÂÒf÷&Ò„fÇ6R’Â&ÆööE÷FW7C¢&ööÂÒf÷&Ò„fÇ6R’ÂVÇG&6÷VæC¢&ööÂÒf÷&Ò„fÇ6R’Â6†W7E÷‡&“¢&ööÂÒf÷&Ò„fÇ6R’ÂÖVF–6–æUöæÖS¢7G"Òf÷&Ò‚""’ÂÖVF–6F–öå÷G—S¢7G"Òf÷&Ò‚'G&VFÖVçB"’ÂW'÷6S¢7G"Òf÷&Ò‚""’ÂF÷6vS¢7G"Òf÷&Ò‚""’Âg&WVVæ7“¢7G"Òf÷&Ò‚""’Â7F'FVEööã¢7G"Òf÷&Ò‚""’Â&V6÷&E÷7FGW3¢7G"Òf÷&Ò‚""’ÂF—6V6UöæÖS¢7G"Òf÷&Ò‚""’ÂF—6V6Uö6FVv÷'“¢7G"Òf÷&Ò‚&÷F†W""’Â7–×Fö×3¢7G"Òf÷&Ò‚""’ÂG&VFÖVçE÷7F'FVEööã¢7G"Òf÷&Ò‚""’ÂG&VFÖVçEöVæFVEööã¢7G"Òf÷&Ò‚""’ÂfWFW&–æ&–ã¢7G"Òf÷&Ò‚""’Â&V7W'&Væ6S¢&ööÂÒf÷&Ò„fÇ6R’ÂfööEöæÖS¢7G"Òf÷&Ò‚""’ÂÖçVf7GW&W#¢7G"Òf÷&Ò‚""’ÂfööE÷G—S¢7G"Òf÷&Ò‚&G'’"’Â6†ævU÷&V6öã¢7G"Òf÷&Ò‚""’ÂÖ÷VçEös¢7G"Òf÷&Ò‚""’ÂF–ÖW5÷W%öF“¢7G"Òf÷&Ò‚""’ÂVæFVEööã¢7G"Òf÷&Ò‚""’ÂFWF–Ç3¢7G"Òf÷&Ò‚""’Â6†&U÷Fõö'&VVFW#¢&ööÂÒf÷&Ò„fÇ6R’ÂGF6†ÖVçEöf–ÆS¢WÆöDf–ÆRÂæöæRÒf–ÆR„æöæR’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÒ÷væV@¢–b6FVv÷'’æ÷B–â²'vV–v‡B"Â'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R"Â&fööB'Ó¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.X^[«~zêyn8*¾88n8+N8:®8;Î8ÎŠh¾8N8¾8(®8î8¾8)2"¢W‡G&2ÒµĞ¢–b6FVv÷'’ÓÒ'vV–v‡B# ¢G'“¢vV–v‡BÒfÆöB‡vV–v‡Eö¶r¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.KÙ>˜xŞ8).z+®Š¨Ş8~8n8ş88^8B"¢–bvV–v‡BÃÒ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.KÙ>˜xŞ8).z+®Š¨Ş8~8n8ş88^8B"¢F—FÆRÂfÇVRÒ.KÙ>˜xŞkŠÎZé¢"Âb'·vV–v‡C¦wÖ¶r#²W‡G&2Ò¶b.X^[«~x«nhX¾ûÉ§¶6öæF—F–öçÒ"–b6öæF—F–öâVÇ6R"%Ğ¢VÆ–b6FVv÷'’ÓÒ'f66–æF–öâ# ¢–bf66–æU÷G—Ræ÷B–â²'&&–W2"Â&Ö—†VB"Â&÷F†W"'Ò÷"æ÷Bf66–æUöæÖRç7G&—‚“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8:ş8*ş888;>h8^Z8).z+®Š¨Ş8~8n8ş88^8B"¢G—UöÆ&VÂÒ²'&&–W2#¢.x¸.xªÎyxR"Â&Ö—†VB#¢.k{~Y8:ş8*ş888;2"Â&÷F†W"#¢.8Ş8îK¹b'Õ·f66–æU÷G—UĞ¢F—FÆRÂfÇVRÒf66–æUöæÖRç7G&—‚’ÂG—UöÆ&VÂ²†b.8;·¶F÷6Rç7G&—‚—Ò"–bF÷6Rç7G&—‚’VÇ6R""“²W‡G&2Ò¶b.jÊY¹îK¨Zé®ûÉ§¶æW‡EöGVUööçÒ"–bæW‡EöGVUööâVÇ6R""Âb.X¹^xšyx^™š.ûÉ§¶6Æ–æ–2ç7G&—‚—Ò"–b6Æ–æ–2ç7G&—‚’VÇ6R"%Ğ¢VÆ–b6FVv÷'’ÓÒ&6†V6·W# ¢FW7G2Ò¶æÖRf÷"Væ&ÆVBÂæÖR–â²‡‡—6–6ÅöW†ÒÂ.ŠznŠ‹¢"’Â†&ÆööE÷FW7BÂ.Škk.jIÎiû²"’Â‡VÇG&6÷VæBÂ.8*8+>8;Â"’Â†6†W7E÷‡&’Â.ˆ;˜:…{y¢"•Ò–bVæ&ÆVEĞ¢–bæ÷BFW7G3¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.X^Š‹®š^yºî8)#8NKº^Kˆ®˜h©î8~8n8ş88^8B"¢F—FÆRÂfÇVRÒ.X^[«~Š‹®ijÒ"Â&W7VÇBç7G&—‚“²W‡G&2Ò².jIÎiû¾ûÉ¢"².8;²"æ¦ö–â‡FW7G2’Âb.jÊY¹îK¨Zé®ûÉ§¶æW‡EöGVUööçÒ"–bæW‡EöGVUööâVÇ6R""Âb.X¹^xšyx^™š.ûÉ§¶6Æ–æ–2ç7G&—‚—Ò"–b6Æ–æ–2ç7G&—‚’VÇ6R"%Ğ¢VÆ–b6FVv÷'’ÓÒ&ÖVF–6F–öâ# ¢–bæ÷BÖVF–6–æUöæÖRç7G&—‚’÷"ÖVF–6F–öå÷G—Ræ÷B–â²'G&VFÖVçB"Â'&WfVçF–öâ"Â'7WÆVÖVçB"Â&÷F†W"'Ò÷"&V6÷&E÷7FGW2æ÷B–â².XÙY¹â"Â.{i{i®KŠÒ"Â.{X.K¨b'Ó¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.h©^‰jÎh8^Z8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢7F'EöF’ÒFFRæg&öÖ—6öf÷&ÖB‡7F'FVEööâ’–b7F'FVEööâVÇ6RæöæS²VæEöF’ÒFFRæg&öÖ—6öf÷&ÖB†VæFVEööâ’–bVæFVEööâVÇ6RæöæP¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.h©^‰jÎiÉş™i>8).z+®Š¨Ş8~8n8ş88^8B"¢–b7F'EöF’æBVæEöF’æBVæEöF’Â7F'EöF“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢G—UöÆ&VÂÒ²'G&VFÖVçB#¢.k+¾y˜.‰jÂ"Â'&WfVçF–öâ#¢.K¨™‹.‰jÂ"Â'7WÆVÖVçB#¢.8+^89~8:®8:8;>88‚"Â&÷F†W"#¢.8Ş8îK¹b'Õ¶ÖVF–6F–öå÷G—UĞ¢F—FÆRÂfÇVRÒÖVF–6–æUöæÖRç7G&—‚’Â&V6÷&E÷7FGW2ç7G&—‚“²W‡G&2Ò¶b.XË®XˆnûÉ§·G—UöÆ&VÇÒ"Âb.yºîy¨N8;¾Zûî‹yx~x«nûÉ§·W'÷6Rç7G&—‚—Ò"–bW'÷6Rç7G&—‚’VÇ6R""Âb#Y¹î˜xşûÉ§¶F÷6vRç7G&—‚—Ò"–bF÷6vRç7G&—‚’VÇ6R""Âb.š¾[ªnûÉ§¶g&WVVæ7’ç7G&—‚—Ò"–bg&WVVæ7’ç7G&—‚’VÇ6R""Âb.™h¾Zx¾iz^ûÉ§·7F'EöF—Ò"–b7F'EöF’VÇ6R""Âb.{X.K¨niz^ûÉ§¶VæEöF—Ò"–bVæEöF’VÇ6R""Âb.jÊY¹îK¨Zé®ûÉ§¶æW‡EöGVUööçÒ"–bæW‡EöGVUööâVÇ6R""Âb.X¹^xšyx^™š.ûÉ§¶6Æ–æ–2ç7G&—‚—Ò"–b6Æ–æ–2ç7G&—‚’VÇ6R"%Ğ¢VÆ–b6FVv÷'’ÓÒ&F—6V6R# ¢fÆ–Eö6FVv÷&–W2Ò²&F–vW7F—fR#¢.khXÉnYš‚"Â'&W7—&F÷'’#¢.YÎYYš‚"Â'6¶–â#¢.yªîˆi¢"Â&÷'F†÷VF–2#¢.i[N[Ú.8;¾™j.zø"Â&6&F–2#¢.[ê®y+Yš‚"Â'W&–æ'’#¢.k8Î[şYš‚"Â'&W&öGV7F—fR#¢.yIşjénYš‚"Â&–æfV7F–÷W2#¢.hIşiù>yxr"Â&÷F†W"#¢.8Ş8îK¹b'Ğ¢–bæ÷BF—6V6UöæÖRç7G&—‚’÷"F—6V6Uö6FVv÷'’æ÷B–âfÆ–Eö6FVv÷&–W2÷"&V6÷&E÷7FGW2æ÷B–â².k+¾y˜.KŠÒ"Â.{XÎ˜îŠk>Zùò"Â.ZèÎk+²"Â.hZ.h
r'Ó¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.yx^jÛNh8^Z8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢G&VFÖVçE÷7F'BÒFFRæg&öÖ—6öf÷&ÖB‡G&VFÖVçE÷7F'FVEööâ’–bG&VFÖVçE÷7F'FVEööâVÇ6RæöæS²G&VFÖVçEöVæBÒFFRæg&öÖ—6öf÷&ÖB‡G&VFÖVçEöVæFVEööâ’–bG&VFÖVçEöVæFVEööâVÇ6RæöæP¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.k+¾y˜.iÉş™i>8).z+®Š¨Ş8~8n8ş88^8B"¢–bG&VFÖVçE÷7F'BæBG&VFÖVçEöVæBæBG&VFÖVçEöVæBÂG&VFÖVçE÷7F'C¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.k+¾y˜.{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢F—FÆRÂfÇVRÒF—6V6UöæÖRç7G&—‚’Â&V6÷&E÷7FGW2ç7G&—‚“²W‡G&2Ò¶b.XˆnšîûÉ§·fÆ–Eö6FVv÷&–W5¶F—6V6Uö6FVv÷'•×Ò"Âb.yx~x«nûÉ§·7–×Fö×2ç7G&—‚—Ò"–b7–×Fö×2ç7G&—‚’VÇ6R""Âb.k+¾y˜.™h¾Zx¾iz^ûÉ§·G&VFÖVçE÷7F'GÒ"–bG&VFÖVçE÷7F'BVÇ6R""Âb.k+¾y˜.{X.K¨niz^ûÉ§·G&VFÖVçEöVæGÒ"–bG&VFÖVçEöVæBVÇ6R""Âb.XhŞy›®ûÉ§²~8ş8Br–b&V7W'&Væ6RVÇ6R~8N8N8‚wÒ"Âb.X¹^xšyx^™š.ûÉ§¶6Æ–æ–2ç7G&—‚—Ò"–b6Æ–æ–2ç7G&—‚’VÇ6R""Âb.h¸^[Ù>xÚ>XË¾[Š¾ûÉ§·fWFW&–æ&–âç7G&—‚—Ò"–bfWFW&–æ&–âç7G&—‚’VÇ6R""Âb.jÊY¹îŠ‹®ZùşûÉ§¶æW‡EöGVUööçÒ"–bæW‡EöGVUööâVÇ6R"%Ğ¢VÇ6S ¢–bæ÷BfööEöæÖRç7G&—‚’÷"fööE÷G—Ræ÷B–â²&G'’"Â'vWB"Â'&r"Â'&W67&—F–öâ"Â'7WÆVÖVçB"Â&÷F†W"'Ò÷"&V6÷&E÷7FGW2æ÷B–â².XŠyJKŠÒ"Â.{X.K¨b'Ó¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.89^8;Î88h8^Z8).z+®Š¨Ş8~8n8ş88^8B"¢G'“¢Ö÷VçBÒfÆöB†Ö÷VçEör’–bÖ÷VçEörVÇ6RæöæS²F–ÖW2Ò–çB‡F–ÖW5÷W%öF’’–bF–ÖW5÷W%öF’VÇ6RæöæP¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{ZnKˆî˜xş8;¾Y¹îi[8).z+®Š¨Ş8~8n8ş88^8B"¢–b†Ö÷VçB—2æ÷BæöæRæBÖ÷VçBÃÒ’÷"‡F–ÖW2—2æ÷BæöæRæBæ÷BÃÒF–ÖW2ÃÒ“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{ZnKˆî˜xş8;¾Y¹îi[8).z+®Š¨Ş8~8n8ş88^8B"¢G'“¢VæEöfööBÒFFRæg&öÖ—6öf÷&ÖB†VæFVEööâ’–bVæFVEööâVÇ6RæöæP¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XŠyJ{X.K¨niz^8).z+®Š¨Ş8~8n8ş88^8B"¢–bVæEöfööBæBVæEöfööBÂFFRæg&öÖ—6öf÷&ÖB‡&V6÷&FVEööâ“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XŠyJ{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢–b&V6÷&E÷7FGW2ÓÒ.{X.K¨b"æBæ÷BVæEöfööC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{X.K¨nkˆ8ş8îZNY8şXŠyJ{X.K¨niz^8).XZ^X©¾8~8n8ş88^8B"¢G—UöÆ&VÂÒ²&G'’#¢.888:8*B"Â'vWB#¢.8*n8*~88>88‚"Â'&r#¢.yIşš9ò"Â'&W67&—F–öâ#¢.y˜.k9^š9ò"Â'7WÆVÖVçB#¢.8+^89~8:®8:8;>88‚"Â&÷F†W"#¢.8Ş8îK¹b'Õ¶fööE÷G—UĞ¢F—FÆRÂfÇVRÒfööEöæÖRç7G&—‚’Â&V6÷&E÷7FGW2ç7G&—‚“²W‡G&2Ò¶b.8:8;Î8*¾8;ÎûÉ§¶ÖçVf7GW&W"ç7G&—‚—Ò"–bÖçVf7GW&W"ç7G&—‚’VÇ6R""Âb.zŠîšîûÉ§·G—UöÆ&VÇÒ"Âb#iz^˜xşûÉ§¶Ö÷VçC¦wÖr"–bÖ÷VçB—2æ÷BæöæRVÇ6R""Âb#izW·F–ÖW7ŞY¹â"–bF–ÖW2VÇ6R""Âb.{X.K¨niz^ûÉ§¶VæEöfööGÒ"–bVæEöfööBVÇ6R""Âb.ZHi»N8;¾{X.K¨nynyKûÉ§¶6†ævU÷&V6öâç7G&—‚—Ò"–b6†ævU÷&V6öâç7G&—‚’VÇ6R"%Ğ¢GVRÒæöæP¢–bæW‡EöGVUööã ¢G'“¢GVRÒFFRæg&öÖ—6öf÷&ÖB†æW‡EöGVUööâ¢W†6WBfÇVTW'&÷#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jÊY¹îK¨Zé®iz^8).z+®Š¨Ş8~8n8ş88^8B"¢GF6†ÖVçEöæÖRÒGF6†ÖVçE÷G—RÒæöæS²GF6†ÖVçEöFFÒæöæP¢–b6FVv÷'’–â²'f66–æF–öâ"Â&6†V6·W'ÒæBGF6†ÖVçEöf–ÆRæBGF6†ÖVçEöf–ÆRæf–ÆVæÖS ¢ÆÆ÷vVBÒ²&Æ–6F–öâ÷Fb"Â&–ÖvRö§Vr"Â&–ÖvR÷ær'Ğ¢GF6†ÖVçEöFFÒv—BGF6†ÖVçEöf–ÆRç&VBƒ‚¢#B¢#B²¢–bGF6†ÖVçEöf–ÆRæ6öçFVçE÷G—Ræ÷B–âÆÆ÷vVB÷"æ÷BGF6†ÖVçEöFF÷"ÆVâ†GF6†ÖVçEöFF’â‚¢#B¢#C¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.k{¾K¹89^8*8*N8:¾8õDn8;´¥~8;µä~8ã„Ô.Kº^Kˆ¾8¾8~8n8ş88^8B"¢GF6†ÖVçEöæÖRÒF‚†GF6†ÖVçEöf–ÆRæf–ÆVæÖR’ææÖU³£#SUÓ²GF6†ÖVçE÷G—RÒGF6†ÖVçEöf–ÆRæ6öçFVçE÷G—P¢6öÖ&–æVBÒ%Æâ"æ¦ö–â‡'Bf÷"'B–âW‡G&2²¶FWF–Ç2ç7G&—‚•Ò–b'B¢F’ÒfÆ–FFUö÷væW%ö†VÇF…÷&V6÷&B†6FVv÷'’Â&V6÷&FVEööâÂF—FÆRÂfÇVRÂ6öÖ&–æVB¢6W76–öâæFB„÷væW$†VÇF…&V6÷&B‡FVæçEö–CÖ÷væW'6†—çFVæçEö–BÂFöuö–CÖFöræ–BÂ÷væW%ö–C×W6W"æ–BÂ6FVv÷'“Ö6FVv÷'’Â&V6÷&FVEööãÖF’ÂF—FÆS×F—FÆRÂfÇVS×fÇVR÷"æöæRÂFWF–Ç3Ö6öÖ&–æVB÷"æöæRÂæW‡EöGVUööãÖGVRÂGF6†ÖVçEöf–ÆVæÖSÖGF6†ÖVçEöæÖRÂGF6†ÖVçEö6öçFVçE÷G—SÖGF6†ÖVçE÷G—RÂGF6†ÖVçEöFFÖGF6†ÖVçEöFFÂ6†&U÷Fõö'&VVFW#×6†&U÷Fõö'&VVFW"’“²6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚÷¶6FVv÷'—Ò"Â7FGW5ö6öFSÓ32  ¦FVbfÆ–FFUö÷væW%ö†VÇF…÷&V6÷&B†6FVv÷'“¢7G"Â&V6÷&FVEööã¢7G"ÂF—FÆS¢7G"ÂfÇVS¢7G"ÂFWF–Ç3¢7G"“ ¢–b6FVv÷'’æ÷B–â²'vV–v‡B"Â'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R"Â&fööB"Â&÷F†W"'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.X^[«~Š‰˜Ë.8î8*¾88n8+N8:®8;Î8).z+®Š¨Ş8~8n8ş88^8B"¢–bæ÷BF—FÆRç7G&—‚’÷"ÆVâ‡F—FÆRç7G&—‚’’âS÷"ÆVâ‡fÇVRç7G&—‚’’âS÷"ÆVâ†FWF–Ç2’â3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.X^[«~Š‰˜Ë.8îXZ^X©¾Xh^Zë8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢F’ÒFFRæg&öÖ—6öf÷&ÖB‡&V6÷&FVEööâ¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Š‰˜Ë.iz^8).z+®Š¨Ş8~8n8ş88^8B"¢&WGW&âF  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷&V6÷&G2"¦FVbfÖ–Ç•ö÷væW%ö†VÇF…ö7&VFR†Föuö–C¢–çBÂ6FVv÷'“¢7G"Òf÷&Ò‚âââ’Â&V6÷&FVEööã¢7G"Òf÷&Ò‚âââ’ÂF—FÆS¢7G"Òf÷&Ò‚âââ’ÂfÇVS¢7G"Òf÷&Ò‚""’ÂFWF–Ç3¢7G"Òf÷&Ò‚""’Â6†&U÷Fõö'&VVFW#¢&ööÂÒf÷&Ò„fÇ6R’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂFörÒ÷væV@¢F’ÒfÆ–FFUö÷væW%ö†VÇF…÷&V6÷&B†6FVv÷'’Â&V6÷&FVEööâÂF—FÆRÂfÇVRÂFWF–Ç2¢6W76–öâæFB„÷væW$†VÇF…&V6÷&B‡FVæçEö–CÖ÷væW'6†—çFVæçEö–BÂFöuö–CÖFöræ–BÂ÷væW%ö–C×W6W"æ–BÂ6FVv÷'“Ö6FVv÷'’Â&V6÷&FVEööãÖF’ÂF—FÆS×F—FÆRç7G&—‚’ÂfÇVS×fÇVRç7G&—‚’÷"æöæRÂFWF–Ç3ÖFWF–Ç2ç7G&—‚’÷"æöæRÂ6†&U÷Fõö'&VVFW#×6†&U÷Fõö'&VVFW"’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föræ–GÒö†VÇF‚"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷&V6÷&G2÷·&V6÷&Eö–GÒ"¦FVbfÖ–Ç•ö÷væW%ö†VÇF…÷WFFR†Föuö–C¢–çBÂ&V6÷&Eö–C¢–çBÂ6FVv÷'“¢7G"Òf÷&Ò‚âââ’Â&V6÷&FVEööã¢7G"Òf÷&Ò‚âââ’ÂF—FÆS¢7G"Òf÷&Ò‚âââ’ÂfÇVS¢7G"Òf÷&Ò‚""’ÂFWF–Ç3¢7G"Òf÷&Ò‚""’Â6†&U÷Fõö'&VVFW#¢&ööÂÒf÷&Ò„fÇ6R’Â&WGW&å÷Fó¢7G"Òf÷&Ò‚&†VÇF‚"’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&Bæ–BÓÒ&V6÷&Eö–BÂ÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöuö–BÂ÷væW$†VÇF…&V6÷&Bæ÷væW%ö–BÓÒW6W"æ–B’¢–bæ÷B—FVÓ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.8>8îX^[«~Š‰˜Ë.8).ZHi»N88(¾jŠ™™8Î8.8(®8î8¾8)2"¢F’ÒfÆ–FFUö÷væW%ö†VÇF…÷&V6÷&B†6FVv÷'’Â&V6÷&FVEööâÂF—FÆRÂfÇVRÂFWF–Ç2¢—FVÒæ6FVv÷'’Ò6FVv÷'“²—FVÒç&V6÷&FVEööâÒF“²—FVÒçF—FÆRÒF—FÆRç7G&—‚“²—FVÒçfÇVRÒfÇVRç7G&—‚’÷"æöæS²—FVÒæFWF–Ç2ÒFWF–Ç2ç7G&—‚’÷"æöæS²—FVÒç6†&U÷Fõö'&VVFW"Ò6†&U÷Fõö'&VVFW#²—FVÒçWFFVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢FW7F–æF–öâÒb"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷·&WGW&å÷F÷Ò"–b&WGW&å÷Fò–â²'vV–v‡B"Â'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R"Â&fööB'ÒVÇ6Rb"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚ ¢&WGW&â&VF—&V7E&W7öç6R†FW7F–æF–öâÂ7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷&V6÷&G2÷·&V6÷&Eö–GÒöFVÆWFR"¦FVbfÖ–Ç•ö÷væW%ö†VÇF…öFVÆWFR†Föuö–C¢–çBÂ&V6÷&Eö–C¢–çBÂ6öæf—&ÕöFVÆWFS¢&ööÂÒf÷&Ò„fÇ6R’Â&WGW&å÷Fó¢7G"Òf÷&Ò‚&†VÇF‚"’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&Bæ–BÓÒ&V6÷&Eö–BÂ÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöuö–BÂ÷væW$†VÇF…&V6÷&Bæ÷væW%ö–BÓÒW6W"æ–B’¢–bæ÷B—FVÓ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.8>8îX^[«~Š‰˜Ë.8).X˜®™šN88(¾jŠ™™8Î8.8(®8î8¾8)2"¢–bæ÷B6öæf—&ÕöFVÆWFS¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.X˜®™šN8îz+®Š¨Ş8Î[ø^Šh8~8’"¢6W76–öâæFVÆWFR†—FVÒ“²6W76–öâæ6öÖÖ—B‚¢FW7F–æF–öâÒb"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷·&WGW&å÷F÷Ò"–b&WGW&å÷Fò–â²'vV–v‡B"Â'f66–æF–öâ"Â&6†V6·W"Â&ÖVF–6F–öâ"Â&F—6V6R"Â&fööB'ÒVÇ6Rb"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚ ¢&WGW&â&VF—&V7E&W7öç6R†FW7F–æF–öâÂ7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö†VÇF‚÷&V6÷&G2÷·&V6÷&Eö–GÒöGF6†ÖVçB"¦FVbfÖ–Ç•ö÷væW%ö†VÇF…öGF6†ÖVçB†Föuö–C¢–çBÂ&V6÷&Eö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—ÂòÒ÷væV@¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&Bæ–BÓÒ&V6÷&Eö–BÂ÷væW$†VÇF…&V6÷&BæFöuö–BÓÒFöuö–BÂ÷væW$†VÇF…&V6÷&BçFVæçEö–BÓÒ÷væW'6†—çFVæçEö–B’¢–bæ÷B—FVÒ÷"æ÷B—FVÒæGF6†ÖVçEöFF¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.Š‹Îiˆîi»8ÎŠh¾8N8¾8(®8î8¾8)2"¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒæGF6†ÖVçEöFFÂÖVF–÷G—SÖ—FVÒæGF6†ÖVçEö6öçFVçE÷G—R÷"&Æ–6F–öâöö7FWB×7G&VÒ"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R"Â$6öçFVçBÔF—7÷6—F–öâ#¢b&–æÆ–æS²f–ÆVæÖR£ÕUDbÓ‚rw·V÷FR†—FVÒæGF6†ÖVçEöf–ÆVæÖR÷"vFö7VÖVçBr—Ò'Ò  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒ÷f66–æF–öç2÷·f66–æF–öåö–GÒö6W'F–f–6FR"¦FVbfÖ–Ç•÷f66–æF–öåö6W'F–f–6FR†Föuö–C¢–çBÂf66–æF–öåö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B…f66–æF–öâ’çv†W&R…f66–æF–öâæ–BÓÒf66–æF–öåö–BÂf66–æF–öâæFöuö–BÓÒFöuö–B’¢6†&RÒ†VÇF…÷6†&Uöf÷"‡6W76–öâÂ'f66–æF–öâ"Âf66–æF–öåö–B¢–bæ÷B—FVÒ÷"æ÷B—FVÒæ6W'F–f–6FUöFF÷"æ÷B6†&R÷"æ÷B6†&Ræ÷væW%÷f—6–&ÆR÷"6†&RæFöuö–BÒFöuö–C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.X[iÈ8^8(Î8şŠ‹Îiˆîi»8ÎŠh¾8N8¾8(®8î8¾8)2"¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒæ6W'F–f–6FUöFFÂÖVF–÷G—SÖ—FVÒæ6W'F–f–6FUö6öçFVçE÷G—R÷"&Æ–6F–öâöö7FWB×7G&VÒ"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R'Ò  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒö6†V6·W2÷·&V6÷&Eö–GÒöGF6†ÖVçB"¦FVbfÖ–Ç•ö6†V6·WöGF6†ÖVçB†Föuö–C¢–çBÂ&V6÷&Eö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.™k.Šj~8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–BÓÒ&V6÷&Eö–BÂ†VÇF…&V6÷&BæFöuö–BÓÒFöuö–BÂ†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&6†V6·W"’¢6†&RÒ†VÇF…÷6†&Uöf÷"‡6W76–öâÂ&†VÇF‚"Â&V6÷&Eö–B¢–bæ÷B—FVÒ÷"æ÷B—FVÒæGF6†ÖVçEöFF÷"æ÷B6†&R÷"æ÷B6†&Ræ÷væW%÷f—6–&ÆR÷"6†&RæFöuö–BÒFöuö–C¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.X[iÈ8^8(Î8şjIÎiû¾{YiéÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒæGF6†ÖVçEöFFÂÖVF–÷G—SÖ—FVÒæGF6†ÖVçEö6öçFVçE÷G—R÷"&Æ–6F–öâöö7FWB×7G&VÒ"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R'Ò  ¤ævWB‚"öfÖ–Ç’öw&÷wF‚öFB"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öw&÷wF…öFE÷6VÆV7B‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFör’æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’¢æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢–bÆVâ‡&V6÷&G2’ÓÒ ¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öw&÷wF‚öFB÷·&V6÷&G5³Õ³Òæ–GÒ"Â7FGW5ö6öFSÓ32¢–bæ÷B&V6÷&G3 ¢&öG’ÒsÆƒîh‰™[~Š‰˜Ë.8).‹ûŞXªÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇîh©^z‹ş8~8Ş8(¾hI¾xªÎ8Î8î8˜
>i®8^8(Î8n8N8î8¾8)>8#Â÷ãÇîxªÎˆˆî8y›¾˜Ë.8:8;Î8:¾8*.888:Î8+8).8®yú^8(8¾8ş88^8N8#Â÷ãÂöF—cãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR#î8+ş8*N8:8:8*N8;>8h‹¾8(³Âöâp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.h‰™[~Š‰˜Ë.8).‹ûŞXªûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ¢6&G2Ò""æ¦ö–â†brrsÆ6Æ73Ò&ÖöGVÆR"‡&VcÒ"öfÖ–Ç’öw&÷wF‚öFB÷¶Föræ–GÒ#ãÆƒ3ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöƒ3à¢Çç¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ÓÂ÷ãÇî8>8îhI¾xªÎ8îh‰™[~Š‰˜Ë.8).‹ûŞXª(i#Â÷ãÂöârrrf÷"òÂFör–â&V6÷&G2¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR#î8+ş8*N8:8:8*N8;>8h‹¾8(³ÂöãÆƒîh‰™[~Š‰˜Ë.8).‹ûŞXªÂöƒà¢Çîh©^z‹ş88(¾hI¾xªÎ8).˜8)>8~8ş88^8N8#Â÷ãÆF—b6Æ73Ò&w&–B#ç¶6&G7ÓÂöF—cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.h‰™[~Š‰˜Ë.8).‹ûŞXªûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’öw&÷wF‚öFB÷¶Föuö–GÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öw&÷wF…öFE÷vR†Föuö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B&V6÷&C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.h©^z‹ş8~8Ş8(¾hI¾xªÎ8ÎŠh¾8N8¾8(®8î8¾8)2"¢FörÒ&V6÷&E³Ğ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR#î8+ş8*N8:8:8*N8;>8h‹¾8(³ÂöãÆƒîh‰™[~Š‰˜Ë.8).‹ûŞXªÂöƒà¢ÆF—b6Æ73Ò'FVæçB#ãÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂ÷7G&öæsî8îh‰™[~Š‰˜Ë.8).h©^z‹ş8~8î88#Â÷ãÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öFöw2÷¶Föræ–GÒöÆ'VÒ"Væ7G—SÒ&×VÇF—'Böf÷&ÒÖFF#à¢Æ–çWBG—SÒ&†–FFVâ"æÖSÒ'&WGW&å÷Fò"fÇVSÒ'F–ÖVÆ–æR#à¢ÆÆ&VÃîXiyÉşûÈƒh©^z‹ş8¾8N8ŞiÈZJsié®ûÈşYC„Ô.8î8~ûÈ“ÂöÆ&VÃãÆ–çWBG—SÒ&f–ÆR"æÖSÒ'†÷F÷2"66WCÒ&–ÖvRö§VrÆ–ÖvR÷ærÆ–ÖvR÷vV'"×VÇF—ÆR&WV—&VCà¢ÆÆ&VÃîi*î[ÛizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ'F¶Våööâ#à¢ÆÆ&VÃî8+>8:8;>88ûÈƒ3ih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&6F–öâ"Ö†ÆVæwFƒÒ#3"Æ6V†öÆFW#Ò.X‰Ş8(8n8î8®iZ>jÚ8jÛ>8î8®Š©^yIşiz^8®8’#ãÂ÷FW‡F&Và¢ÆÆ&VÃîXZÎ™h¾zøNY»#ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'f—6–&–Æ—G’#ãÆ÷F–öâfÇVSÒ'&—fFR#î™ÙîXZÎ™h¾ûÈˆz®Xˆn88ûÈ“Âö÷F–öããÆ÷F–öâfÇVSÒ'&VÆF—fW2#îŠj®h‰®xªÎ8î8*®8;Î88®8;Î8î8sÂö÷F–öããÆ÷F–öâfÇVSÒ&fÖ–Ç’#ädÔ”ÅXZKÙ3Âö÷F–öããÂ÷6VÆV7Cà¢Æ'WGFöâ6Æ73Ò'7V66W72#îh‰™[~Š‰˜Ë.8).h©^z‹óÂö'WGFöããÂöf÷&Óà¢ÇãÇ6ÖÆÃî8>8î89®8;Î8+8~8ş89~8:Ş89^8*>8;Î8:¾XiyÉş8(N{KK¸¾ih~8şZHi»N8^8(Î8î8¾8)>8#Â÷6ÖÆÃãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶Föræ6ÆÅöæÖWŞ8îh‰™[~Š‰˜Ë.8).‹ûŞXªûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒ÷†÷Fò"¦FVbfÖ–Ç•öFöu÷†÷Fò†Föuö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöuö–B’¢–bæ÷B&öf–ÆR÷"æ÷B&öf–ÆRç†÷FõöFF ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçC×&öf–ÆRç†÷FõöFFÂÖVF–÷G—S×&öf–ÆRç†÷Fõö6öçFVçE÷G—R÷"&–ÖvRö§Vr"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒ÷&öf–ÆR"¦7–æ2FVbfÖ–Ç•öFöu÷&öf–ÆU÷6fR†Föuö–C¢–çBÂ–çG&öGV7F–öã¢7G"Òf÷&Ò‚""’Â†÷Fó¢WÆöDf–ÆRÂæöæRÒf–ÆR„æöæR’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B&V6÷&B÷"&V6÷&E³Òç&VÆF–öç6†—Ò'&–Ö'’# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.K‹¾8*®8;Î88®8;Î888ÎhI¾xªÎ89~8:Ş89^8*>8;Î8:¾8).ZHi»N8~8Ş8î8’"¢–çG&öGV7F–öâÒ–çG&öGV7F–öâç7G&—‚¢–bÆVâ†–çG&öGV7F–öâ’â3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{KK¸¾ih~8ó3ih~ZÙ~Kº^Xh^8~XZ^X©¾8~8n8ş88^8B"¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöuö–B’¢–bæ÷B&öf–ÆS ¢&öf–ÆRÒfÖ–Ç”Föu&öf–ÆR†Föuö–CÖFöuö–BÂWFFVEö'•ö–C×W6W"æ–B¢6W76–öâæFB‡&öf–ÆR¢–b†÷FòæB†÷Fòæf–ÆVæÖS ¢6öçFVçBÒv—B†÷Fòç&VBƒ‚¢#B¢#B²¢–bÆVâ†6öçFVçB’â‚¢#B¢#C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XiyÉş8ó„Ô.Kº^Kˆ¾8¾8~8n8ş88^8B"¢G'“ ¢v—F‚–ÖvRæ÷Vâ†–òä'—FW4”ò†6öçFVçB’’26÷W&6S ¢–b6÷W&6Rçv–GF‚¢6÷W&6Ræ†V–v‡Bâ#Uóó ¢&—6RfÇVTW'&÷"‚&–ÖvRF–ÖVç6–öç2&RFöòÆ&vR"¢–ÖvRÒ–ÖvT÷2æW†–e÷G&ç7÷6R‡6÷W&6R¢–ÖvRçF‡VÖ&æ–Â‚ƒcÂc’Â–ÖvRå&W6×Æ–æräÄä5¤õ2¢–b–ÖvRæÖöFR–â²%$t$"Â$Ä'Ó ¢&6¶w&÷VæBÒ–ÖvRææWr‚%$t""Â–ÖvRç6—¦RÂ'v†—FR"¢&6¶w&÷VæBç7FR†–ÖvRÂÖ6³Ö–ÖvRævWF6†ææVÂ‚$"’¢–ÖvRÒ&6¶w&÷Væ@¢VÇ6S ¢–ÖvRÒ–ÖvRæ6öçfW'B‚%$t""¢÷WGWBÒ–òä'—FW4”ò‚¢–ÖvRç6fR†÷WGWBÂf÷&ÖCÒ$¥Tr"ÂVÆ—G“Óƒ‚Â÷F–Ö—¦SÕG'VR¢W†6WBW†6WF–öã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ$¥~8;µä~8;µvV%[Ú.[Èş8îXiyÉş8).˜h©î8~8n8ş88^8B"¢&öf–ÆRç†÷FõöFFÂ&öf–ÆRç†÷Fõö6öçFVçE÷G—RÒ÷WGWBævWGfÇVR‚’Â&–ÖvRö§Vr ¢&öf–ÆRæ–çG&öGV7F–öâÂ&öf–ÆRçWFFVEö'•ö–BÂ&öf–ÆRçWFFVEöBÒ–çG&öGV7F–öâ÷"æöæRÂW6W"æ–BÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föuö–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒ÷†÷FòöFVÆWFR"¦FVbfÖ–Ç•öFöu÷†÷FõöFVÆWFR†Föuö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B&V6÷&B÷"&V6÷&E³Òç&VÆF–öç6†—Ò'&–Ö'’# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöuö–B’¢–b&öf–ÆS ¢&öf–ÆRç†÷FõöFFÂ&öf–ÆRç†÷Fõö6öçFVçE÷G—RÒæöæRÂæöæP¢&öf–ÆRçWFFVEö'•ö–BÂ&öf–ÆRçWFFVEöBÒW6W"æ–BÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föuö–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒöÆ'VÒ"¦7–æ2FVbfÖ–Ç•öFöuöÆ'VÕöFB†Föuö–C¢–çBÂ†÷F÷3¢Æ—7EµWÆöDf–ÆUÒÒf–ÆR‚âââ’ÂF¶Våööã¢7G"Òf÷&Ò‚""’Â6F–öã¢7G"Òf÷&Ò‚""’Âf—6–&–Æ—G“¢7G"Òf÷&Ò‚'&—fFR"’Â&WGW&å÷Fó¢7G"Òf÷&Ò‚""’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢÷væVBÒfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ¢–bæ÷B÷væVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.8>8îxªÎ8î8*.8:¾898:8‹ûŞXª8~8Ş8î8¾8)2"¢–bfÖ–Ç•ö7F–öåöF—6&ÆVB‡W6W"æ–BÂ÷væVE³ÒçFVæçEö–BÂ'÷7F–ær"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.xªÎˆˆî8¾8(8(®h©^z‹şj™şˆ;Ş8ÎXÎjÚ.8^8(Î8n8N8î8’"¢6F–öâÒ6F–öâç7G&—‚¢–bÆVâ†6F–öâ’â3÷"f—6–&–Æ—G’æ÷B–â²'&—fFR"Â'&VÆF—fW2"Â&fÖ–Ç’'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8+>8:8;>888î8ş8şXZÎ™h¾zøNY».8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢F¶VåöFFRÒFFRæg&öÖ—6öf÷&ÖB‡F¶Våööâ’–bF¶VåööâVÇ6RæöæP¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.i*î[Ûiz^8).z+®Š¨Ş8~8n8ş88^8B"¢†÷F÷2Ò·†÷Fòf÷"†÷Fò–â†÷F÷2–b†÷Fòæf–ÆVæÖUĞ¢–bæ÷B†÷F÷2÷"ÆVâ‡†÷F÷2’â ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XiyÉş8óié®8¾8(“ié®8î8~˜h©î8~8n8ş88^8B"¢w&÷WÒ6V7&WG2çFö¶Våö†W‚ƒb¢f÷"÷6—F–öâÂ†÷Fò–âVçVÖW&FR‡†÷F÷2“ ¢6öçFVçBÒv—B†÷Fòç&VBƒ‚¢#B¢#B²¢–bæ÷B6öçFVçB÷"ÆVâ†6öçFVçB’â‚¢#B¢#C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XiyÉş8óié£„Ô.Kº^Kˆ¾8¾8~8n8ş88^8B"¢G'“ ¢v—F‚–ÖvRæ÷Vâ†–òä'—FW4”ò†6öçFVçB’’26÷W&6S ¢–b6÷W&6Rçv–GF‚¢6÷W&6Ræ†V–v‡Bâ#Uóó ¢&—6RfÇVTW'&÷"‚&–ÖvRF–ÖVç6–öç2&RFöòÆ&vR"¢–ÖvRÒ–ÖvT÷2æW†–e÷G&ç7÷6R‡6÷W&6R“²–ÖvRçF‡VÖ&æ–Â‚ƒƒÂƒ’Â–ÖvRå&W6×Æ–æräÄä5¤õ2¢–b–ÖvRæÖöFR–â²%$t$"Â$Ä'Ó ¢&6¶w&÷VæBÒ–ÖvRææWr‚%$t""Â–ÖvRç6—¦RÂ'v†—FR"“²&6¶w&÷VæBç7FR†–ÖvRÂÖ6³Ö–ÖvRævWF6†ææVÂ‚$"’“²–ÖvRÒ&6¶w&÷Væ@¢VÇ6S ¢–ÖvRÒ–ÖvRæ6öçfW'B‚%$t""¢÷WGWBÒ–òä'—FW4”ò‚“²–ÖvRç6fR†÷WGWBÂf÷&ÖCÒ$¥Tr"ÂVÆ—G“Óƒ‚Â÷F–Ö—¦SÕG'VR¢W†6WBW†6WF–öã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ$¥~8;µä~8;µvV%[Ú.[Èş8îXiyÉş8).˜h©î8~8n8ş88^8B"¢6W76–öâæFB„fÖ–Ç”FötÆ'VÔ—FVÒ†Föuö–CÖFöuö–BÂWÆöFVEö'•ö–C×W6W"æ–BÂ†÷FõöFFÖ÷WGWBævWGfÇVR‚’Â†÷Fõö6öçFVçE÷G—SÒ&–ÖvRö§Vr"ÂF¶Våööã×F¶VåöFFRÂ6F–öãÖ6F–öâ÷"æöæRÂf—6–&–Æ—G“×f—6–&–Æ—G’Â÷7Eöw&÷WÖw&÷WÂ†÷Fõö÷&FW#×÷6—F–öâ’¢6W76–öâæ6öÖÖ—B‚¢FW7F–æF–öâÒ"öfÖ–Ç’÷F–ÖVÆ–æR"–b&WGW&å÷FòÓÒ'F–ÖVÆ–æR"VÇ6Rb"öfÖ–Ç’öFöw2÷¶Föuö–GÒ ¢&WGW&â&VF—&V7E&W7öç6R†FW7F–æF–öâÂ7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒöÆ'VÒ÷¶—FVÕö–GÒ÷†÷Fò"¦FVbfÖ–Ç•öFöuöÆ'VÕ÷†÷Fò†Föuö–C¢–çBÂ—FVÕö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒ—FVÕö–BÂfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–BÓÒFöuö–B’¢–bæ÷B—FVÒ÷"†—FVÒçf—6–&–Æ—G’ÓÒ'&—fFR"æB—FVÒçWÆöFVEö'•ö–BÒW6W"æ–B“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒç†÷FõöFFÂÖVF–÷G—SÖ—FVÒç†÷Fõö6öçFVçE÷G—RÂ†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒöÆ'VÒ÷¶—FVÕö–GÒöFVÆWFR"¦FVbfÖ–Ç•öFöuöÆ'VÕöFVÆWFR†Föuö–C¢–çBÂ—FVÕö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒ—FVÕö–BÂfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–BÓÒFöuö–BÂfÖ–Ç”FötÆ'VÔ—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–B’¢–bæ÷B—FVÓ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢F&vWG2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒç÷7Eöw&÷WÓÒ—FVÒç÷7Eöw&÷W’’æÆÂ‚’–b—FVÒç÷7Eöw&÷WVÇ6R¶—FVÕĞ¢f÷"F&vWB–âF&vWG3 ¢6W76–öâæFVÆWFR‡F&vWB¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föuö–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öFöw2÷¶Föuö–GÒöÆ'VÒ÷¶—FVÕö–GÒöVF—B"¦FVbfÖ–Ç•öFöuöÆ'VÕöVF—B†Föuö–C¢–çBÂ—FVÕö–C¢–çBÂF¶Våööã¢7G"Òf÷&Ò‚""’Â6F–öã¢7G"Òf÷&Ò‚""’Âf—6–&–Æ—G“¢7G"Òf÷&Ò‚'&—fFR"’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷BfÖ–Ç•ö÷væVEöFör†Föuö–BÂW6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R€¢fÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒ—FVÕö–BÂfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–BÓÒFöuö–BÂfÖ–Ç”FötÆ'VÔ—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–BÀ¢’¢6F–öâÒ6F–öâç7G&—‚¢–bæ÷B—FVÒ÷"ÆVâ†6F–öâ’â3÷"f—6–&–Æ—G’æ÷B–â²'&—fFR"Â'&VÆF—fW2"Â&fÖ–Ç’'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{z™¸nXh^Zë8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢'6VE÷F¶VåööâÒFFRæg&öÖ—6öf÷&ÖB‡F¶Våööâ’–bF¶VåööâVÇ6RæöæP¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.i*î[Ûiz^8).z+®Š¨Ş8~8n8ş88^8B"¢F&vWG2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒç÷7Eöw&÷WÓÒ—FVÒç÷7Eöw&÷W’’æÆÂ‚’–b—FVÒç÷7Eöw&÷WVÇ6R¶—FVÕĞ¢f÷"F&vWB–âF&vWG3 ¢F&vWBçF¶VåööâÂF&vWBæ6F–öâÂF&vWBçf—6–&–Æ—G’Ò'6VE÷F¶VåööâÂ6F–öâ÷"æöæRÂf—6–&–Æ—G¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öFöw2÷¶Föuö–GÒ"Â7FGW5ö6öFSÓ32  ¦FVb÷væW%÷&öf–ÆUöf÷"‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’Óâ÷væW%&öf–ÆS ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçW6W%ö–BÓÒW6W"æ–B’¢–bæ÷B&öf–ÆS ¢&öf–ÆRÒ÷væW%&öf–ÆR‡W6W%ö–C×W6W"æ–BÂV&Æ–5ö–C×6V7&WG2çFö¶Vå÷W&Ç6fRƒ"’¢6W76–öâæFB‡&öf–ÆR¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&öf–ÆP  ¤ævWB‚"öfÖ–Ç’÷&öf–ÆR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷&öf–ÆUöVF—B‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&öf–ÆRÒ÷væW%÷&öf–ÆUöf÷"‡W6W"Â6W76–öâ¢&VfV7GW&Uö÷F–öç2ÒsÆ÷F–öâfÇVSÒ"#îiÊ®ŠŠŞZé£Âö÷F–öãâr²""æ¦ö–â€¢bsÆ÷F–öâfÇVSÒ'·fÇVWÒ"²'6VÆV7FVB"–b&öf–ÆRç&VfV7GW&RÓÒfÇVRVÇ6R"'Óç·fÇVWÓÂö÷F–öãârf÷"fÇVR–â$TdT5EU$U0¢¢6†V6¶VBÒÆÖ&FfÇVS¢&6†V6¶VB"–bfÇVRVÇ6R" ¢†÷FòÒbsÆ–Ör7&3Ò"öfÖ–Ç’÷&öf–ÆR÷†÷Fò"ÇCÒ.89~8:Ş89^8*>8;Î8:¾XiyÉò"7G–ÆSÒ'v–GFƒ£Sƒ¶†V–v‡C£Sƒ¶ö&¦V7BÖf—C¦6÷fW#¶&÷&FW"×&F—W3£SS¶&÷&FW#£G‚6öÆ–B6VCCR#âr–b&öf–ÆRç†÷FõöFFVÇ6RsÇî89~8:Ş89^8*>8;Î8:¾XiyÉş8şiÊ®y›¾˜Ë.8~88#Â÷âp¢V&Æ–5÷W&ÂÒbröfÖ–Ç’öÖVÖ&W'2÷·&öf–ÆRçV&Æ–5ö–GÒp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒî89~8:Ş89^8*>8;Î8:¾ŠŠŞZé£Âöƒà¢Æƒ#î8*.8*¾8*n8;>88ŠŠŞZé£Âöƒ#à¢Çî8:Ş8+8*.8*n8889Î8+ş8;>8îjŠ®8®888NiÊÎK«®8îyK¾™Ú.8¾ŠzK®8^8(Î8(¾YŞX˜Ş8~88.XZÎ™h¾89~8:Ş89^8*>8;Î8:¾8î88¾88>8*ş88Ş8;Î8:88şXŠ^8¾zêyn8^8(Î8î88#Â÷à¢Æf÷&ÒÖWF†öCÒ'÷7B"Væ7G—SÒ&×VÇF—'Böf÷&ÒÖFF#à¢ÆÆ&VÃî8*.8*¾8*n8;>88YŞûÈƒih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÆ–çWBæÖSÒ&66÷VçEöæÖR"fÇVSÒ'¶‡FÖÂæW66R‡W6W"ææÖR—Ò"Ö†ÆVæwFƒÒ#"&WV—&VBÆ6V†öÆFW#Ò.Kè¾ûÉ®Xh^[ˆšşKˆ#à¢ÆÆ&VÃîy›¾˜Ë.8:8;Î8:¾8*.888:Î8+“ÂöÆ&VÃãÆ–çWBG—SÒ&VÖ–Â"fÇVSÒ'¶‡FÖÂæW66R‡W6W"æVÖ–Â—Ò"&VFöæÇ’&–×&VFöæÇ“Ò'G'VR"7G–ÆSÒ&&6¶w&÷VæC¢6cVcc¶6öÆ÷#¢3ccSS’#à¢ÇãÇ6ÖÆÃî8>8î8:8;Î8:¾8*.888:Î8+8ş8:Ş8+8*N8;>8hI¾xªÎ8î˜
>i®8¾KÛşyJ8^8(Î8n8N8î88$dÔ”Å8îK¹n8î8:8;>898;Î8¾8şXZÎ™h¾8^8(Î8î8¾8)>8.ZHi»N8Î[ø^Šh8®ZNY8şxªÎˆˆî88N˜
>{Z8ş88^8N8#Â÷6ÖÆÃãÂ÷à¢Æƒ#îXZÎ™h¾89~8:Ş89^8*>8;Î8:¾ŠŠŞZé£Âöƒ#à¢Çî89~8:Ş89^8*>8;Î8:¾XZKÙ>88YNš^yºî8îXZÎ™h¾zøNY».8).8Nˆz®‹ª¾8~ŠŠŞZé®8~8Ş8î88.™ÙîXZÎ™h¾š^yºî8şK¹n8î8:8;>898;Î8¾ŠzK®8^8(Î8î8¾8)>8#Â÷à¢ÆF—b6Æ73Ò'FVæçB#ç·†÷F÷ÓÇãÆ‡&VcÒ'·V&Æ–5÷W&ÇÒ#îXZÎ™h¾x«nhX¾8).z+®Š¨Ş88(³ÂöãÂ÷ãÂöF—cà¢ÆÆ&VÃî88¾88>8*ş88Ş8;Î8:ÂöÆ&VÃãÆ–çWBæÖSÒ&æ–6¶æÖR"fÇVSÒ'¶‡FÖÂæW66R‡&öf–ÆRææ–6¶æÖR÷"rr—Ò"Ö†ÆVæwFƒÒ#c"Æ6V†öÆFW#Ò.Kè¾ûÉ®8(®8(~8b#à¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷uöæ–6¶æÖR"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷uöæ–6¶æÖR—Óâ88¾88>8*ş88Ş8;Î8:8).XZÎ™h¾88(³ÂöÆ&VÃà¢ÆÆ&VÃî˜;Ş˜>[©ÎyÈÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&VfV7GW&R#ç·&VfV7GW&Uö÷F–öç7ÓÂ÷6VÆV7Cà¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷u÷&VfV7GW&R"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷u÷&VfV7GW&R—Óâ˜;Ş˜>[©ÎyÈÎ8).XZÎ™h¾88(³ÂöÆ&VÃà¢ÆÆ&VÃîˆz®[{{KK¸¾ûÈƒSih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&&–ò"Ö†ÆVæwFƒÒ#S"Æ6V†öÆFW#Ò.hI¾xªÎ88îiªî8(8~8(N88Nˆz®‹ª¾8¾8N8N8n8N{KK¸¾8ş88^8N8"#ç¶‡FÖÂæW66R‡&öf–ÆRæ&–ò÷"rr—ÓÂ÷FW‡F&Và¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷uö&–ò"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷uö&–ò—Óâˆz®[{{KK¸¾8).XZÎ™h¾88(³ÂöÆ&VÃà¢ÆÆ&VÃä–ç7Fw&ŞûÈ8:n8;Î8+n8;Î88Ş8;Î8:8î8ş8ş89~8:Ş89^8*>8;Î8:µU$ÎûÈ“ÂöÆ&VÃãÆ–çWBæÖSÒ&–ç7Fw&Ò"fÇVSÒ'¶‡FÖÂæW66R‡&öf–ÆRæ–ç7Fw&Õ÷W6W&æÖR÷"rr—Ò"Ö†ÆVæwFƒÒ#"Æ6V†öÆFW#Ò.Kè¾ûÉ¤W7G&VÆÆöFör8î8ş8ò‡GG3¢ò÷wwræ–ç7Fw&Òæ6öÒöW7G&VÆÆöFörò#à¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷uö–ç7Fw&Ò"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷uö–ç7Fw&Ò—Óâ–ç7Fw&Ş8).XZÎ™h¾88(³ÂöÆ&VÃà¢ÇãÇ6ÖÆÃîXZÎ™h¾88(¾8889~8:Ş89^8*>8;Î8:¾8¾8(”–ç7Fw&Ş8).XŠ^yK¾™Ú.8~™h¾88î88.898+8:ş8;Î888şXZ^X©¾8~8®8N8~8ş88^8N8#Â÷6ÖÆÃãÂ÷à¢ÆÆ&VÃî89~8:Ş89^8*>8;Î8:¾XiyÉşûÈ„¥~8;µä~8;µvV%ûÈó„Ô.8î8~ûÈ“ÂöÆ&VÃãÆ–çWBæÖSÒ'†÷Fò"G—SÒ&f–ÆR"66WCÒ&–ÖvRö§VrÆ–ÖvR÷ærÆ–ÖvR÷vV'#à¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷u÷†÷Fò"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷u÷†÷Fò—Óâ89~8:Ş89^8*>8;Î8:¾XiyÉş8).XZÎ™h¾88(³ÂöÆ&VÃà¢Æƒ#îhI¾xªÎ8;¾Š{[8îXZÎ™h¾ŠŠŞZé£Âöƒ#à¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷uöFöw2"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷uöFöw2—Óâ˜
>i®8^8(Î8n8N8(¾hI¾xªÎ8).XZÎ™h¾88(³ÂöÆ&VÃà¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷u÷&VçG2"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷u÷&VçG2—ÓâhI¾xªÎ8îx‹nxªÎ8;¾jøŞxªÎ8(.XZÎ™h¾88(³ÂöÆ&VÃà¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'6†÷u÷&VÆF—fW2"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç6†÷u÷&VÆF—fW2—ÓâYÎˆ[XXN[Éş8;¾Šj®h‰®xªÎ8).ˆz®X¹^ŠzK®88(³ÂöÆ&VÃà¢ÇãÇ6ÖÆÃîx‹njøŞ8).XZÎ™h¾8~8n8(.8Š{[i»yZ®Xû~8;¾89î8*N8*ş8:Ş8888>89~yZ®Xû~8;¾h˜iÈˆ^h8^Z8şŠzK®8^8(Î8î8¾8)>8#Â÷6ÖÆÃãÂ÷à¢ÆF—b6Æ73Ò'FVæçB#ãÆÆ&VÂ7G–ÆSÒ&föçB×6—¦S£g‚#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'&öf–ÆU÷V&Æ–2"fÇVSÒ'G'VR"¶6†V6¶VB‡&öf–ÆRç&öf–ÆU÷V&Æ–2—Óâ89~8:Ş89^8*>8;Î8:¾XZKÙ>8).xªÎˆˆädÔ”ÅKÉ®8XZÎ™h¾88(³ÂöÆ&VÃà¢ÇãÇ6ÖÆÃî8>8>8).8*®89^8¾88(¾88YNš^yºî8Î8*®8;>8~8(.89~8:Ş89^8*>8;Î8:¾XZKÙ>8Î™ÙîXZÎ™h¾8¾8®8(®8î88#Â÷6ÖÆÃãÂ÷ãÂöF—cà¢Æ'WGFöãîŠŠŞZé®8).KùŞZÙƒÂö'WGFöããÂöf÷&Óà¢¶bsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷&öf–ÆR÷†÷FòöFVÆWFR#ãÆ'WGFöâ6Æ73Ò&FævW"#îy›¾˜Ë.XiyÉş8).X˜®™šCÂö'WGFöããÂöf÷&Óâr–b&öf–ÆRç†÷FõöFFVÇ6RrwÒrrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.XZÎ™h¾89~8:Ş89^8*>8;Î8:¾ŠŠŞZé¢"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’÷&öf–ÆR"¦7–æ2FVbfÖ–Ç•÷&öf–ÆU÷6fR€¢66÷VçEöæÖS¢7G"Òf÷&Ò‚""’Âæ–6¶æÖS¢7G"Òf÷&Ò‚""’Â&VfV7GW&S¢7G"Òf÷&Ò‚""’Â&–ó¢7G"Òf÷&Ò‚""’Â–ç7Fw&Ó¢7G"Òf÷&Ò‚""’Â†÷Fó¢WÆöDf–ÆRÂæöæRÒf–ÆR„æöæR’À¢&öf–ÆU÷V&Æ–3¢&ööÂÒf÷&Ò„fÇ6R’Â6†÷uöæ–6¶æÖS¢&ööÂÒf÷&Ò„fÇ6R’Â6†÷u÷&VfV7GW&S¢&ööÂÒf÷&Ò„fÇ6R’À¢6†÷uö&–ó¢&ööÂÒf÷&Ò„fÇ6R’Â6†÷u÷†÷Fó¢&ööÂÒf÷&Ò„fÇ6R’Â6†÷uöFöw3¢&ööÂÒf÷&Ò„fÇ6R’Â6†÷u÷&VçG3¢&ööÂÒf÷&Ò„fÇ6R’À¢6†÷u÷&VÆF—fW3¢&ööÂÒf÷&Ò„fÇ6R’Â6†÷uö–ç7Fw&Ó¢&ööÂÒf÷&Ò„fÇ6R’À¢W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’À¢“ ¢æ÷&ÖÆ—¦VEö66÷VçEöæÖRÒ""æ¦ö–â†66÷VçEöæÖRç7Æ—B‚’¢–bæ÷Bæ÷&ÖÆ—¦VEö66÷VçEöæÖR÷"ÆVâ†æ÷&ÖÆ—¦VEö66÷VçEöæÖR’â ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚.YŞX˜Ş8îXZ^X©¾8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#î8*.8*¾8*n8;>88YŞ8óih~ZÙ~Kº^Kˆ£ih~ZÙ~Kº^Xh^8~XZ^X©¾8~8n8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷&öf–ÆR#îh‹¾8(³ÂöârÂW6W"Â6W76–öâ’Â7FGW5ö6öFSÓC¢–b&VfV7GW&RæB&VfV7GW&Ræ÷B–â$TdT5EU$U3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.˜;Ş˜>[©ÎyÈÎ8).z+®Š¨Ş8~8n8ş88^8B"¢–bÆVâ†æ–6¶æÖRç7G&—‚’’âc÷"ÆVâ†&–òç7G&—‚’’âS ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.89~8:Ş89^8*>8;Î8:¾8îih~ZÙ~i[8).z+®Š¨Ş8~8n8ş88^8B"¢–ç7Fw&Õ÷fÇVRÒ–ç7Fw&Òç7G&—‚’ç'7G&—‚"ò"¢–ç7Fw&ÕöÖF6‚Ò&RægVÆÆÖF6‚‡""ƒó¦‡GG3ó¢òò“òƒó§wwuÂâ“ö–ç7Fw&ÕÂæ6öÒò…´Õ¦×£Ó’åõ×³Ã3Ò’"Â–ç7Fw&Õ÷fÇVRÂ&Rä”täõ$T44R¢–ç7Fw&Õ÷W6W&æÖRÒ–ç7Fw&ÕöÖF6‚æw&÷Wƒ’–b–ç7Fw&ÕöÖF6‚VÇ6R–ç7Fw&Õ÷fÇVRç&VÖ÷fW&Vf—‚‚$"¢–b–ç7Fw&Õ÷W6W&æÖRæBæ÷B&RægVÆÆÖF6‚‡"%´Õ¦×£Ó’åõ×³Ã3Ò"Â–ç7Fw&Õ÷W6W&æÖR“ ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚$–ç7Fw&ŞXZ^X©¾8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#ä–ç7Fw&Ş8î8:n8;Î8+n8;Î88Ş8;Î8:88î8ş8ò–ç7Fw&Òæ6öÒ8î89~8:Ş89^8*>8;Î8:µU$Î8).XZ^X©¾8~8n8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷&öf–ÆR#îh‹¾8(³ÂöârÂW6W"Â6W76–öâ’Â7FGW5ö6öFSÓC¢&öf–ÆRÒ÷væW%÷&öf–ÆUöf÷"‡W6W"Â6W76–öâ¢–b†÷FòæB†÷Fòæf–ÆVæÖS ¢6öçFVçBÒv—B†÷Fòç&VBƒ‚¢#B¢#B²¢–bÆVâ†6öçFVçB’â‚¢#B¢#C ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚.XiyÉş8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#îXiyÉş8ó„Ô.Kº^Kˆ¾8¾8~8n8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷&öf–ÆR#îh‹¾8(³ÂöârÂW6W"Â6W76–öâ’Â7FGW5ö6öFSÓC¢G'“ ¢v—F‚–ÖvRæ÷Vâ†–òä'—FW4”ò†6öçFVçB’’26÷W&6S ¢–b6÷W&6Rçv–GF‚¢6÷W&6Ræ†V–v‡Bâ#Uóó ¢&—6RfÇVTW'&÷"‚&–ÖvRF–ÖVç6–öç2&RFöòÆ&vR"¢–ÖvRÒ–ÖvT÷2æW†–e÷G&ç7÷6R‡6÷W&6R¢–ÖvRçF‡VÖ&æ–Â‚ƒ#Â#’Â–ÖvRå&W6×Æ–æräÄä5¤õ2¢–b–ÖvRæÖöFR–â²%$t$"Â$Ä'Ó ¢&6¶w&÷VæBÒ–ÖvRææWr‚%$t""Â–ÖvRç6—¦RÂ'v†—FR"¢&6¶w&÷VæBç7FR†–ÖvRÂÖ6³Ö–ÖvRævWF6†ææVÂ‚$"’¢–ÖvRÒ&6¶w&÷Væ@¢VÇ6S ¢–ÖvRÒ–ÖvRæ6öçfW'B‚%$t""¢÷WGWBÒ–òä'—FW4”ò‚¢–ÖvRç6fR†÷WGWBÂf÷&ÖCÒ$¥Tr"ÂVÆ—G“ÓƒbÂ÷F–Ö—¦SÕG'VR¢W†6WBW†6WF–öã ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚.XiyÉş8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#ä¥~8;µä~8;µvV%[Ú.[Èş8îXiyÉş8).˜h©î8~8n8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷&öf–ÆR#îh‹¾8(³ÂöârÂW6W"Â6W76–öâ’Â7FGW5ö6öFSÓC¢&öf–ÆRç†÷FõöFFÒ÷WGWBævWGfÇVR‚¢&öf–ÆRç†÷Fõö6öçFVçE÷G—RÒ&–ÖvRö§Vr ¢VÆ–v–&ÆRÒW6W"çÆFf÷&ÕöFÖ–â÷"6W76–öâç66Æ"‡6VÆV7B„ÖVÖ&W'6†—æ–B’çv†W&R„ÖVÖ&W'6†—çW6W%ö–BÓÒW6W"æ–B’æÆ–Ö—Bƒ’’—2æ÷BæöæRÀ¢÷"6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’æÆ–Ö—Bƒ’’—2æ÷BæöæP¢–b&öf–ÆU÷V&Æ–2æBæ÷BVÆ–v–&ÆS ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚.XZÎ™h¾ŠŠŞZé®8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#î89~8:Ş89^8*>8;Î8:¾8).XZÎ™h¾8~8Ş8(¾8î8ş8xªÎˆˆî8¾h˜[î8~8n8N8(¾ik8î8ş8şxªÎ8˜
>i®kˆ8ş8î8*®8;Î88®8;Îjy8~88#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷&öf–ÆR#îh‹¾8(³ÂöârÂW6W"Â6W76–öâ’Â7FGW5ö6öFSÓC2¢W6W"ææÖRÒæ÷&ÖÆ—¦VEö66÷VçEöæÖP¢&öf–ÆRææ–6¶æÖRÒæ–6¶æÖRç7G&—‚’÷"æöæP¢&öf–ÆRç&VfV7GW&RÒ&VfV7GW&R÷"æöæP¢&öf–ÆRæ&–òÒ&–òç7G&—‚’÷"æöæP¢&öf–ÆRæ–ç7Fw&Õ÷W6W&æÖRÒ–ç7Fw&Õ÷W6W&æÖR÷"æöæP¢&öf–ÆRç&öf–ÆU÷V&Æ–2Â&öf–ÆRç6†÷uöæ–6¶æÖRÒ&öf–ÆU÷V&Æ–2Â6†÷uöæ–6¶æÖP¢&öf–ÆRç6†÷u÷&VfV7GW&RÂ&öf–ÆRç6†÷uö&–òÂ&öf–ÆRç6†÷u÷†÷FòÒ6†÷u÷&VfV7GW&RÂ6†÷uö&–òÂ6†÷u÷†÷Fğ¢&öf–ÆRç6†÷uöFöw2Â&öf–ÆRç6†÷u÷&VçG2Ò6†÷uöFöw2Â6†÷u÷&VçG2æB6†÷uöFöw0¢&öf–ÆRç6†÷u÷&VÆF—fW2Ò6†÷u÷&VÆF—fW2æB6†÷uöFöw0¢&öf–ÆRç6†÷uö–ç7Fw&ÒÒ6†÷uö–ç7Fw&ÒæB&ööÂ†–ç7Fw&Õ÷W6W&æÖR¢&öf–ÆRçWFFVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷&öf–ÆR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷&öf–ÆR÷†÷Fò"¦FVbfÖ–Ç•÷&öf–ÆUö÷vå÷†÷Fò‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçW6W%ö–BÓÒW6W"æ–B’¢–bæ÷B&öf–ÆR÷"æ÷B&öf–ÆRç†÷FõöFF ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçC×&öf–ÆRç†÷FõöFFÂÖVF–÷G—S×&öf–ÆRç†÷Fõö6öçFVçE÷G—R÷"&–ÖvRö§Vr"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ç÷7B‚"öfÖ–Ç’÷&öf–ÆR÷†÷FòöFVÆWFR"¦FVbfÖ–Ç•÷&öf–ÆU÷†÷FõöFVÆWFR‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçW6W%ö–BÓÒW6W"æ–B’¢–b&öf–ÆS ¢&öf–ÆRç†÷FõöFFÂ&öf–ÆRç†÷Fõö6öçFVçE÷G—RÂ&öf–ÆRç6†÷u÷†÷FòÒæöæRÂæöæRÂfÇ6P¢&öf–ÆRçWFFVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷&öf–ÆR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öÖVÖ&W'2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÖVÖ&W%öÆ—7B‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’ö¶VææVÂ"Â7FGW5ö6öFSÓ32  ¦FVbfÖ–Ç•öæ6W7F÷%öFWF‡2‡6W76–öã¢6W76–öâÂFös¢FörÂÖ…öFWFƒ¢–çBÒ2’ÓâF–7E¶–çBÂ–çEÓ ¢"".YÎKˆ88n88®8;>88Xh^8îzYnXX„”N8‹ù8^8).‹ùN88.[ê®y+8;¾ŠªNy›¾˜Ë.8~8(.xJ™™XhŞ[‹8~8®8N8""" ¢FWF‡3¢F–7E¶–çBÂ–çEÒÒ·Ğ¢g&öçF–W"Ò²†Förç6—&Uö–BÂ’Â†FöræFÕö–BÂ•Ğ¢v†–ÆRg&öçF–W# ¢Föuö–BÂFWF‚Òg&öçF–W"ç÷ƒ¢–bæ÷BFöuö–B÷"FWF‚âÖ…öFWF‚÷"†Föuö–B–âFWF‡2æBFWF‡5¶Föuö–EÒÃÒFWF‚“ ¢6öçF–çVP¢æ6W7F÷"Ò6W76–öâævWB„FörÂFöuö–B¢–bæ÷Bæ6W7F÷"÷"æ6W7F÷"çFVæçEö–BÒFörçFVæçEö–C ¢6öçF–çVP¢FWF‡5¶Föuö–EÒÒFWF€¢g&öçF–W"æW‡FVæB…²†æ6W7F÷"ç6—&Uö–BÂFWF‚²’Â†æ6W7F÷"æFÕö–BÂFWF‚²•Ò¢&WGW&âFWF‡0  ¦FVbfÖ–Ç•÷&VÆF–öç6†—‡6W76–öã¢6W76–öâÂ6÷W&6S¢FörÂ6æF–FFS¢För’ÓâGWÆU·7G"Â7G%ÒÂæöæS ¢"".XZÎ™h¾yJ8î™j.Kø.Xˆnšî8.YÎˆ[8).iÈXJ®XX8~8jÊ8¾y»N{;¾8;¾x˜~Šj®8;¾X[˜	®zYnXX8).XŠNZé®88(¾8""" ¢–b6÷W&6Ræ–BÓÒ6æF–FFRæ–B÷"6÷W&6RçFVæçEö–BÒ6æF–FFRçFVæçEö–C ¢&WGW&âæöæP¢6ÖU÷6—&RÒ&ööÂ‡6÷W&6Rç6—&Uö–BæB6÷W&6Rç6—&Uö–BÓÒ6æF–FFRç6—&Uö–B¢6ÖUöFÒÒ&ööÂ‡6÷W&6RæFÕö–BæB6÷W&6RæFÕö–BÓÒ6æF–FFRæFÕö–B¢–b6ÖU÷6—&RæB6ÖUöFÓ ¢–b6÷W&6Ræ&—'F…öFFRæB6÷W&6Ræ&—'F…öFFRÓÒ6æF–FFRæ&—'F…öFFS ¢&WGW&â&Æ—GFW""Â.YÎˆ[XXN[Éò ¢&WGW&â'&VÆF—fR"Â.x‹njøŞ8ÎYÎ88Ş8(~8n88NûÈXŠ^8îX{®yJ>ûÈ’ ¢6÷W&6Uöæ6W7F÷'2ÒfÖ–Ç•öæ6W7F÷%öFWF‡2‡6W76–öâÂ6÷W&6R¢6æF–FFUöæ6W7F÷'2ÒfÖ–Ç•öæ6W7F÷%öFWF‡2‡6W76–öâÂ6æF–FFR¢–b6÷W&6Ræ–B–â6æF–FFUöæ6W7F÷'2÷"6æF–FFRæ–B–â6÷W&6Uöæ6W7F÷'3 ¢&WGW&â'&VÆF—fR"Â.Šj®ZÙ8;¾y»N{;¾8îŠj®h‰®xªÂ ¢–b6ÖU÷6—&S ¢&WGW&â'&VÆF—fR"Â.x‹nxªÎ8ÎYÎ88Ş8(~8n88B ¢–b6ÖUöFÓ ¢&WGW&â'&VÆF—fR"Â.jøŞxªÎ8ÎYÎ88Ş8(~8n88B ¢6öÖÖöâÒ6WB‡6÷W&6Uöæ6W7F÷'2’b6WB†6æF–FFUöæ6W7F÷'2¢–b6öÖÖöã ¢æV&W7BÒÖ–â†6öÖÖöâÂ¶W“ÖÆÖ&FFöuö–C¢6÷W&6Uöæ6W7F÷'5¶Föuö–EÒ²6æF–FFUöæ6W7F÷'5¶Föuö–EÒ¢æ6W7F÷"Ò6W76–öâævWB„FörÂæV&W7B¢æ6W7F÷%öæÖRÒæ6W7F÷"ç&Vv—7FW&VEöæÖR÷"æ6W7F÷"æ6ÆÅöæÖR–bæ6W7F÷"VÇ6R.X[˜	®zYnXX‚ ¢&WGW&â'&VÆF—fR"Âb'¶æ6W7F÷%öæÖWŞ8).X[˜	®zYnXX8¾hÈ8NŠj®h‰®xªÂ ¢&WGW&âæöæP  ¦FVbfÖ–Ç•÷&VÆF—fUöÖF6†W2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâF–7E¶–çBÂGWÆU¶–çBÂ7G"Â7G"ÂFörÂ÷væW%&öf–ÆUÕÓ ¢"".™k.Šj~ˆ^8îhI¾xªÎ88XZÎ™h¾8¾YÎhHş8~8şK¹n8*®8;Î88®8;Î8îŠj®h‰®xªÎ8).xZ~Y88(¾8""" ¢6÷W&6UöFöw2Ò6W76–öâç66Æ'2€¢6VÆV7B„För’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’¢’æÆÂ‚¢6æF–FFW2Ò6W76–öâæW†V7WFR€¢6VÆV7B„FörÂ÷væW%&öf–ÆR’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B¢æ¦ö–â„÷væW%&öf–ÆRÂ÷væW%&öf–ÆRçW6W%ö–BÓÒFöt÷væW'6†—çW6W%ö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’Â÷væW%&öf–ÆRç&öf–ÆU÷V&Æ–2æ—5ò…G'VR’À¢÷væW%&öf–ÆRç6†÷uöFöw2æ—5ò…G'VR’Â÷væW%&öf–ÆRç6†÷u÷&VÆF—fW2æ—5ò…G'VR’Â÷væW%&öf–ÆRçW6W%ö–BÒW6W"æ–BÀ¢FVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢’æÆÂ‚¢ÖF6†W3¢F–7E¶–çBÂGWÆU¶–çBÂ7G"Â7G"ÂFörÂ÷væW%&öf–ÆUÕÒÒ·Ğ¢f÷"6æF–FFRÂ&öf–ÆR–â6æF–FFW3 ¢f÷"6÷W&6R–â6÷W&6UöFöw3 ¢&VÆF–öç6†—ÒfÖ–Ç•÷&VÆF–öç6†—‡6W76–öâÂ6÷W&6RÂ6æF–FFR¢–bæ÷B&VÆF–öç6†— ¢6öçF–çVP¢w&÷WÂÆ&VÂÒ&VÆF–öç6†— ¢&–÷&—G’Ò–bw&÷WÓÒ&Æ—GFW""VÇ6R¢7W'&VçBÒÖF6†W2ævWB†6æF–FFRæ–B¢–bæ÷B7W'&VçB÷"&–÷&—G’Â7W'&VçE³Ó ¢ÖF6†W5¶6æF–FFRæ–EÒÒ‡&–÷&—G’Âw&÷WÂb'·6÷W&6Ræ6ÆÅöæÖWŞ8‡¶Æ&VÇÒ"Â6æF–FFRÂ&öf–ÆR¢&WGW&âÖF6†W0  ¦FVbfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’Óâ6WE¶–çEÓ ¢"".™k.Šj~ˆ^8Îh˜[î88(¾88î8ş8şhI¾xªÎ8).‹øî88şxªÎˆˆî888).‹ùN88""" ¢FVæçEö–G2Ò6WB‡6W76–öâç66Æ'2€¢6VÆV7B„Föt÷væW'6†—çFVæçEö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’À¢FVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢’æÆÂ‚’¢FVæçEö–G2çWFFR‡6W76–öâç66Æ'2€¢6VÆV7B„ÖVÖ&W'6†—çFVæçEö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒÖVÖ&W'6†—çFVæçEö–B¢çv†W&R„ÖVÖ&W'6†—çW6W%ö–BÓÒW6W"æ–BÂFVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢’æÆÂ‚’¢–bW6W"çÆFf÷&ÕöFÖ–ã ¢FVæçEö–G2çWFFR‡6W76–öâç66Æ'2€¢6VÆV7B…FVæçBæ–B’çv†W&R…FVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢’æÆÂ‚’¢&WGW&âFVæçEö–G0  ¦FVbfÖ–Ç•÷Vç&VEöÖW76vUö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´fÖ–Ç”6öçfW'6F–öâÂfÖ–Ç”ÖW76vUÕÓ ¢"".XŠyJˆ^Zé¾8n8î8KÉ®Š›8N88îiÈikiÊ®ŠªŞ8:88>8+¾8;Î8+8).‹ùN88""" ¢6öçfW'6F–öç2Ò6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç”6öçfW'6F–öâ’çv†W&R€¢„fÖ–Ç”6öçfW'6F–öâçW6W#ö–BÓÒW6W"æ–B’Â„fÖ–Ç”6öçfW'6F–öâçW6W#%ö–BÓÒW6W"æ–B¢¢’æÆÂ‚¢Vç&VC¢Æ—7E·GWÆU´fÖ–Ç”6öçfW'6F–öâÂfÖ–Ç”ÖW76vUÕÒÒµĞ¢f÷"6öçfW'6F–öâ–â6öçfW'6F–öç3 ¢ÆFW7BÒ6W76–öâç66Æ"€¢6VÆV7B„fÖ–Ç”ÖW76vR’çv†W&R€¢fÖ–Ç”ÖW76vRæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–BÀ¢fÖ–Ç”ÖW76vRç6VæFW%ö–BÒW6W"æ–BÀ¢fÖ–Ç”ÖW76vRçv—F†G&våöBæ—5ò„æöæR’À¢fÖ–Ç”ÖW76vRæ†–FFVåöBæ—5ò„æöæR’À¢’æ÷&FW%ö'’„fÖ–Ç”ÖW76vRç6VçEöBæFW62‚’’æÆ–Ö—Bƒ¢¢–bæ÷BÆFW7C ¢6öçF–çVP¢&VBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vU&VB’çv†W&R€¢fÖ–Ç”ÖW76vU&VBæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–BÀ¢fÖ–Ç”ÖW76vU&VBçW6W%ö–BÓÒW6W"æ–BÀ¢’¢–bæ÷B&VB÷"ÆFW7Bç6VçEöBâ&VBæÆ7E÷&VEöC ¢Vç&VBæVæB‚†6öçfW'6F–öâÂÆFW7B’¢&WGW&â6÷'FVB‡Vç&VBÂ¶W“ÖÆÖ&F—FVÓ¢—FVÕ³Òç6VçEöBÂ&WfW'6SÕG'VR  ¦FVbfÖ–Ç•÷Vç&VEöææ÷Væ6VÖVçG2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´fÖ–Ç”ææ÷Væ6VÖVçBÂFVæçEÕÓ ¢FVæçEö–G2ÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ¢–bæ÷BFVæçEö–G3 ¢&WGW&âµĞ¢&WGW&âÆ—7B‡6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçBÂFVæçB’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒfÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–B¢æ÷WFW&¦ö–â„fÖ–Ç”ææ÷Væ6VÖVçE&VBÂæEò€¢fÖ–Ç”ææ÷Væ6VÖVçE&VBæææ÷Væ6VÖVçEö–BÓÒfÖ–Ç”ææ÷Væ6VÖVçBæ–BÀ¢fÖ–Ç”ææ÷Væ6VÖVçE&VBçW6W%ö–BÓÒW6W"æ–BÀ¢’¢çv†W&R€¢fÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–Bæ–åò‡FVæçEö–G2’ÂfÖ–Ç”ææ÷Væ6VÖVçBæ7F—fRæ—5ò…G'VR’À¢FVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’ÂfÖ–Ç”ææ÷Væ6VÖVçE&VBæ–Bæ—5ò„æöæR’À¢’æ÷&FW%ö'’„fÖ–Ç”ææ÷Væ6VÖVçBæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ¢’æÆÂ‚’  ¦FVbfÖ–Ç•÷Vç&VEöÆ–¶Uö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´fÖ–Ç•F–ÖVÆ–æTÆ–¶RÂfÖ–Ç”FötÆ'VÔ—FVÒÂFöuÕÓ ¢"".ˆz®Xˆn8îh©^z‹ş8K¹8N8ş8iÊ®z+®Š¨Ş8î8N8N8Ş8).‹ùN88""" ¢f—6–&ÆUö–G2Ò6WB†fÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’¢–bæ÷Bf—6–&ÆUö–G3 ¢&WGW&âµĞ¢&WGW&âÆ—7B‡6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æTÆ–¶RÂfÖ–Ç”FötÆ'VÔ—FVÒÂFör¢æ¦ö–â„fÖ–Ç”FötÆ'VÔ—FVÒÂfÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒfÖ–Ç•F–ÖVÆ–æTÆ–¶RæÆ'VÕö—FVÕö–B¢æ¦ö–â„FörÂFöræ–BÓÒfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–B¢æ÷WFW&¦ö–â„fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBÂæEò€¢fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBæÆ–¶Uö–BÓÒfÖ–Ç•F–ÖVÆ–æTÆ–¶Ræ–BÀ¢fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBçW6W%ö–BÓÒW6W"æ–BÀ¢’¢çv†W&R€¢fÖ–Ç”FötÆ'VÔ—FVÒæ–Bæ–åò‡f—6–&ÆUö–G2’ÂfÖ–Ç”FötÆ'VÔ—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–BÀ¢fÖ–Ç•F–ÖVÆ–æTÆ–¶RçW6W%ö–BÒW6W"æ–BÂfÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBæ–Bæ—5ò„æöæR’À¢’æ÷&FW%ö'’„fÖ–Ç•F–ÖVÆ–æTÆ–¶Ræ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ¢’æÆÂ‚’  ¦FVbfÖ–Ç•÷Vç&VEö6öÖÖVçEö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBÂfÖ–Ç”FötÆ'VÔ—FVÒÂFöuÕÓ ¢"".ˆz®Xˆn8îh©^z‹ş8[®8N8ş8iÊ®z+®Š¨Ş8î8+>8:8;>888).‹ùN88""" ¢f—6–&ÆUö–G2Ò6WB†fÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’¢–bæ÷Bf—6–&ÆUö–G3 ¢&WGW&âµĞ¢&WGW&âÆ—7B‡6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBÂfÖ–Ç”FötÆ'VÔ—FVÒÂFör¢æ¦ö–â„fÖ–Ç”FötÆ'VÔ—FVÒÂfÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–B¢æ¦ö–â„FörÂFöræ–BÓÒfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–B¢æ÷WFW&¦ö–â„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBÂæEò€¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBæ6öÖÖVçEö–BÓÒfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ–BÀ¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBçW6W%ö–BÓÒW6W"æ–BÀ¢’¢çv†W&R€¢fÖ–Ç”FötÆ'VÔ—FVÒæ–Bæ–åò‡f—6–&ÆUö–G2’ÂfÖ–Ç”FötÆ'VÔ—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–BÀ¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBçW6W%ö–BÒW6W"æ–BÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæFVÆWFVEöBæ—5ò„æöæR’À¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ†–FFVåöBæ—5ò„æöæR’ÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBæ–Bæ—5ò„æöæR’À¢’æ÷&FW%ö'’„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ¢’æÆÂ‚’  ¦FVbfÖ–Ç•öææ—fW'6'•öæ÷F–f–6F–öåö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÓ ¢Föw2Ò6W76–öâç66Æ'2‡6VÆV7B„För’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B’çv†W&R€¢Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR¢’’æÆÂ‚¢FöF’ÒFFRçFöF’‚¢—FV×3¢Æ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÒÒµĞ¢f÷"För–âFöw3 ¢6æF–FFW3¢Æ—7E·GWÆU·7G"ÂFFUÕÒÒµĞ¢–bFöræ&—'F…öFFS ¢6æF–FFW2æVæB‚‚&&—'F†F’"ÂæW‡EöfÖ–Ç•öææ—fW'6'’†Föræ&—'F…öFFRæÖöçF‚ÂFöræ&—'F…öFFRæF’ÂFöF’’’¢†æF÷fW"Ò6W76–öâç66Æ"‡6VÆV7B…W•6ÆRæ†æF÷fW%öFFR’çv†W&R…W•6ÆRæFöuö–BÓÒFöræ–BÂW•6ÆRæ†æF÷fW%öFFRæ—5öæ÷B„æöæR’’æ÷&FW%ö'’…W•6ÆRæ†æF÷fW%öFFRæFW62‚’’æÆ–Ö—Bƒ’¢–bæ÷B†æF÷fW# ¢†æF÷fW"Ò6W76–öâç66Æ"‡6VÆV7B„FöuG&ç6fW"çG&ç6fW'&VEööâ’çv†W&R„FöuG&ç6fW"æFöuö–BÓÒFöræ–B’æ÷&FW%ö'’„FöuG&ç6fW"çG&ç6fW'&VEööâæFW62‚’’æÆ–Ö—Bƒ’¢–b†æF÷fW# ¢6æF–FFW2æVæB‚‚&†öÖV6öÖ–ær"ÂæW‡EöfÖ–Ç•öææ—fW'6'’††æF÷fW"æÖöçF‚Â†æF÷fW"æF’ÂFöF’’’¢f÷"WfVçE÷G—RÂWfVçEöFFR–â6æF–FFW3 ¢F—2Ò†WfVçEöFFRÒFöF’’æF—0¢–bF—2æ÷B–â³ÂÂwÓ ¢6öçF–çVP¢F—6Ö—76VBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ææ—fW'6'”F—6Ö—76Âæ–B’çv†W&R€¢fÖ–Ç”ææ—fW'6'”F—6Ö—76ÂçW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç”ææ—fW'6'”F—6Ö—76ÂæFöuö–BÓÒFöræ–BÀ¢fÖ–Ç”ææ—fW'6'”F—6Ö—76ÂæWfVçE÷G—RÓÒWfVçE÷G—RÂfÖ–Ç”ææ—fW'6'”F—6Ö—76ÂæWfVçEöFFRÓÒWfVçEöFFRÀ¢’¢–bæ÷BF—6Ö—76VC ¢—FV×2æVæB‚†FörÂWfVçE÷G—RÂWfVçEöFFRÂF—2’¢&WGW&â—FV×0  ¦FVbfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W%ö–C¢–çBÂFöuö–C¢–çBÂ6FVv÷'“¢7G"ÂF—FÆS¢7G"ÂGVUööã¢FFRÂ6W76–öã¢6W76–öâ’Óâ&ööÃ ¢&WGW&â6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæ–B’çv†W&R€¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâçW6W%ö–BÓÒW6W%ö–BÀ¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæFöuö–BÓÒFöuö–BÀ¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæ6FVv÷'’ÓÒ6FVv÷'’À¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâçF—FÆRÓÒF—FÆRÀ¢fÖ–Ç”†VÇF…66†VGVÆT6ö×ÆWF–öâæGVUööâÓÒGVUööâÀ¢’’—2æ÷BæöæP  ¦FVbfÖ–Ç•÷f66–æUöGVUö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÓ ¢÷væW'6†—2Ò6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚¢Föuö–G2Ò¶—FVÒæFöuö–Bf÷"—FVÒ–â÷væW'6†—5Ğ¢–bæ÷BFöuö–G3¢&WGW&âµĞ¢Föw2Ò¶Föræ–C¢Förf÷"För–â6W76–öâç66Æ'2‡6VÆV7B„För’çv†W&R„Föræ–Bæ–åò†Föuö–G2’ÂFöræ7F—fRæ—5ò…G'VR’’’æÆÂ‚—Ğ¢FöF’ÒFFRçFöF’‚“²&W7VÇG3¢Æ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÒÒµĞ¢÷væW%÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&BæFöuö–Bæ–åò†Föuö–G2’Â÷væW$†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ'f66–æF–öâ"Â÷væW$†VÇF…&V6÷&BææW‡EöGVUööâæ—5öæ÷B„æöæR’’’æÆÂ‚¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢F—2Ò†—FVÒææW‡EöGVUööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ'f66–æF–öâ"Â—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂF—2’¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R„†VÇF…&V6÷&E6†&RæFöuö–Bæ–åò†Föuö–G2’Â†VÇF…&V6÷&E6†&Rç&V6÷&E÷G—RÓÒ'f66–æF–öâ"Â†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR’’’æÆÂ‚¢6†&VEö–G2Ò·6†&Rç&V6÷&Eö–Bf÷"6†&R–â6†&W5Ğ¢–b6†&VEö–G3 ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B…f66–æF–öâ’çv†W&R…f66–æF–öâæ–Bæ–åò‡6†&VEö–G2’Âf66–æF–öâææW‡EöGVUööâæ—5öæ÷B„æöæR’’’æÆÂ‚“ ¢F—2Ò†—FVÒææW‡EöGVUööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ'f66–æF–öâ"Â—FVÒçf66–æUöæÖRÂ—FVÒææW‡EöGVUööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ—FVÒçf66–æUöæÖRÂ—FVÒææW‡EöGVUööâÂF—2’¢&WGW&â6÷'FVB‡&W7VÇG2Â¶W“ÖÆÖ&F&÷s¢&÷u³%Ò  ¦FVbfÖ–Ç•ö6†V6·WöGVUö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÓ ¢÷væW'6†—2Ò6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚¢Föuö–G2Ò¶—FVÒæFöuö–Bf÷"—FVÒ–â÷væW'6†—5Ğ¢–bæ÷BFöuö–G3¢&WGW&âµĞ¢Föw2Ò¶Föræ–C¢Förf÷"För–â6W76–öâç66Æ'2‡6VÆV7B„För’çv†W&R„Föræ–Bæ–åò†Föuö–G2’ÂFöræ7F—fRæ—5ò…G'VR’’’æÆÂ‚—Ğ¢FöF’ÒFFRçFöF’‚“²&W7VÇG3¢Æ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÒÒµĞ¢÷væW%÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&BæFöuö–Bæ–åò†Föuö–G2’Â÷væW$†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&6†V6·W"Â÷væW$†VÇF…&V6÷&BææW‡EöGVUööâæ—5öæ÷B„æöæR’’’æÆÂ‚¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢F—2Ò†—FVÒææW‡EöGVUööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ&6†V6·W"Â—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂF—2’¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R„†VÇF…&V6÷&E6†&RæFöuö–Bæ–åò†Föuö–G2’Â†VÇF…&V6÷&E6†&Rç&V6÷&E÷G—RÓÒ&†VÇF‚"Â†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR’’’æÆÂ‚¢6†&VEö–G2Ò·6†&Rç&V6÷&Eö–Bf÷"6†&R–â6†&W5Ğ¢–b6†&VEö–G3 ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&B’çv†W&R„†VÇF…&V6÷&Bæ–Bæ–åò‡6†&VEö–G2’Â†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&6†V6·W"Â†VÇF…&V6÷&BææW‡EöGVUööâæ—5öæ÷B„æöæR’’’æÆÂ‚“ ¢F—2Ò†—FVÒææW‡EöGVUööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ&6†V6·W"Â.X^[«~Š‹®ijÒ"Â—FVÒææW‡EöGVUööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ.X^[«~Š‹®ijÒ"Â—FVÒææW‡EöGVUööâÂF—2’¢&WGW&â6÷'FVB‡&W7VÇG2Â¶W“ÖÆÖ&F&÷s¢&÷u³%Ò  ¦FVbfÖ–Ç•öÖVF–6F–öåöGVUö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÓ ¢÷væW'6†—2Ò6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚¢Föuö–G2Ò¶—FVÒæFöuö–Bf÷"—FVÒ–â÷væW'6†—5Ğ¢–bæ÷BFöuö–G3¢&WGW&âµĞ¢Föw2Ò¶Föræ–C¢Förf÷"För–â6W76–öâç66Æ'2‡6VÆV7B„För’çv†W&R„Föræ–Bæ–åò†Föuö–G2’ÂFöræ7F—fRæ—5ò…G'VR’’’æÆÂ‚—Ğ¢FöF’ÒFFRçFöF’‚“²&W7VÇG3¢Æ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÒÒµĞ¢÷væW%÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&BæFöuö–Bæ–åò†Föuö–G2’Â÷væW$†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&ÖVF–6F–öâ"Â÷væW$†VÇF…&V6÷&BææW‡EöGVUööâæ—5öæ÷B„æöæR’Â÷væW$†VÇF…&V6÷&BçfÇVRÒ.{X.K¨b"’’æÆÂ‚¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢F—2Ò†—FVÒææW‡EöGVUööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ&ÖVF–6F–öâ"Â—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂF—2’¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R„†VÇF…&V6÷&E6†&RæFöuö–Bæ–åò†Föuö–G2’Â†VÇF…&V6÷&E6†&Rç&V6÷&E÷G—RÓÒ&ÖVF–6F–öâ"Â†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR’’’æÆÂ‚¢6†&VEö–G2Ò·6†&Rç&V6÷&Eö–Bf÷"6†&R–â6†&W5Ğ¢–b6†&VEö–G3 ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„ÖVF–6F–öâ’çv†W&R„ÖVF–6F–öâæ–Bæ–åò‡6†&VEö–G2’ÂÖVF–6F–öâææW‡EöGVUööâæ—5öæ÷B„æöæR’ÂÖVF–6F–öâç7FGW2Ò&6ö×ÆWFVB"’’æÆÂ‚“ ¢F—2Ò†—FVÒææW‡EöGVUööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ&ÖVF–6F–öâ"Â—FVÒæÖVF–6–æUöæÖRÂ—FVÒææW‡EöGVUööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ—FVÒæÖVF–6–æUöæÖRÂ—FVÒææW‡EöGVUööâÂF—2’¢&WGW&â6÷'FVB‡&W7VÇG2Â¶W“ÖÆÖ&F&÷s¢&÷u³%Ò  ¦FVbfÖ–Ç•öF—6V6UöGVUö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâÆ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÓ ¢÷væW'6†—2Ò6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚¢Föuö–G2Ò¶—FVÒæFöuö–Bf÷"—FVÒ–â÷væW'6†—5Ğ¢–bæ÷BFöuö–G3¢&WGW&âµĞ¢Föw2Ò¶Föræ–C¢Förf÷"För–â6W76–öâç66Æ'2‡6VÆV7B„För’çv†W&R„Föræ–Bæ–åò†Föuö–G2’ÂFöræ7F—fRæ—5ò…G'VR’’’æÆÂ‚—Ğ¢FöF’ÒFFRçFöF’‚“²&W7VÇG3¢Æ—7E·GWÆU´FörÂ7G"ÂFFRÂ–çEÕÒÒµĞ¢÷væW%÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$†VÇF…&V6÷&B’çv†W&R„÷væW$†VÇF…&V6÷&BæFöuö–Bæ–åò†Föuö–G2’Â÷væW$†VÇF…&V6÷&Bæ6FVv÷'’ÓÒ&F—6V6R"Â÷væW$†VÇF…&V6÷&BææW‡EöGVUööâæ—5öæ÷B„æöæR’Â÷væW$†VÇF…&V6÷&BçfÇVRÒ.ZèÎk+²"’’æÆÂ‚¢f÷"—FVÒ–â÷væW%÷&V6÷&G3 ¢F—2Ò†—FVÒææW‡EöGVUööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ&F—6V6R"Â—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ—FVÒçF—FÆRÂ—FVÒææW‡EöGVUööâÂF—2’¢6†&W2Ò6W76–öâç66Æ'2‡6VÆV7B„†VÇF…&V6÷&E6†&R’çv†W&R„†VÇF…&V6÷&E6†&RæFöuö–Bæ–åò†Föuö–G2’Â†VÇF…&V6÷&E6†&Rç&V6÷&E÷G—RÓÒ&F—6V6R"Â†VÇF…&V6÷&E6†&Ræ÷væW%÷f—6–&ÆRæ—5ò…G'VR’’’æÆÂ‚¢6†&VEö–G2Ò·6†&Rç&V6÷&Eö–Bf÷"6†&R–â6†&W5Ğ¢–b6†&VEö–G3 ¢f÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B„F—6V6T†—7F÷'’’çv†W&R„F—6V6T†—7F÷'’æ–Bæ–åò‡6†&VEö–G2’ÂF—6V6T†—7F÷'’ææW‡EöföÆÆ÷wWööâæ—5öæ÷B„æöæR’ÂF—6V6T†—7F÷'’ç7FGW2Ò'&V6÷fW&VB"’’æÆÂ‚“ ¢F—2Ò†—FVÒææW‡EöföÆÆ÷wWööâÒFöF’’æF—0¢–bÓ“ÃÒF—2ÃÒ3æB—FVÒæFöuö–B–âFöw2æBæ÷BfÖ–Ç•ö†VÇF…÷66†VGVÆUö6ö×ÆWFVB‡W6W"æ–BÂ—FVÒæFöuö–BÂ&F—6V6R"Â—FVÒæF—6V6UöæÖRÂ—FVÒææW‡EöföÆÆ÷wWööâÂ6W76–öâ“¢&W7VÇG2æVæB‚†Föw5¶—FVÒæFöuö–EÒÂ—FVÒæF—6V6UöæÖRÂ—FVÒææW‡EöföÆÆ÷wWööâÂF—2’¢&WGW&â6÷'FVB‡&W7VÇG2Â¶W“ÖÆÖ&F&÷s¢&÷u³%Ò  ¦FVbfÖ–Ç•öæ÷F–f–6F–öåö6÷VçB‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’Óâ–çC ¢6WGF–ærÒfÖ–Ç•öæ÷F–f–6F–öå÷6WGF–ær‡W6W"Â6W76–öâ¢&WGW&â‚†ÆVâ†fÖ–Ç•÷Vç&VEöÖW76vUö—FV×2‡W6W"Â6W76–öâ’’–b6WGF–æræÖW76vW2VÇ6R¢²†ÆVâ†fÖ–Ç•÷Vç&VEöææ÷Væ6VÖVçG2‡W6W"Â6W76–öâ’’–b6WGF–æræææ÷Væ6VÖVçG2VÇ6R¢²‚†ÆVâ†fÖ–Ç•÷Vç&VEöÆ–¶Uö—FV×2‡W6W"Â6W76–öâ’’²ÆVâ†fÖ–Ç•÷Vç&VEö6öÖÖVçEö—FV×2‡W6W"Â6W76–öâ’’’–b6WGF–æræÆ–¶W2VÇ6R¢²†ÆVâ†fÖ–Ç•öææ—fW'6'•öæ÷F–f–6F–öåö—FV×2‡W6W"Â6W76–öâ’’–b6WGF–æræææ—fW'6&–W2VÇ6R¢²†ÆVâ†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•÷f66–æUöGVUö—FV×2‡W6W"Â6W76–öâ’’’–b6WGF–æræ†VÇF…÷f66–æF–öç2VÇ6R¢²†ÆVâ†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•ö6†V6·WöGVUö—FV×2‡W6W"Â6W76–öâ’’’–b6WGF–æræ†VÇF…ö6†V6·W2VÇ6R¢²†ÆVâ†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•öÖVF–6F–öåöGVUö—FV×2‡W6W"Â6W76–öâ’’’–b6WGF–æræ†VÇF…öÖVF–6F–öç2VÇ6R¢²†ÆVâ†fÖ–Ç•ö†VÇF…öæ÷F–f–6F–öå÷F–Ö–ær†fÖ–Ç•öF—6V6UöGVUö—FV×2‡W6W"Â6W76–öâ’’’–b6WGF–æræ†VÇF…öföÆÆ÷wW2VÇ6R’  ¦FVbfÖ–Ç•öÖW76vUöæÖR‡W6W%ö–C¢–çBÂ6W76–öã¢6W76–öâ’Óâ7G# ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçW6W%ö–BÓÒW6W%ö–B’¢–b&öf–ÆRæB&öf–ÆRç&öf–ÆU÷V&Æ–2æB&öf–ÆRç6†÷uöæ–6¶æÖRæB&öf–ÆRææ–6¶æÖS ¢&WGW&â&öf–ÆRææ–6¶æÖP¢&WGW&â$dÔ”Å8:8;>898;Â   ¦FVbfÖ–Ç•ö7F–öåöF—6&ÆVB‡W6W%ö–C¢–çBÂFVæçEö–C¢–çBÂ7F–öã¢7G"Â6W76–öã¢6W76–öâ’Óâ&ööÃ ¢&W7G&–7F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•W6W%&W7G&–7F–öâ’çv†W&R€¢fÖ–Ç•W6W%&W7G&–7F–öâçW6W%ö–BÓÒW6W%ö–BÂfÖ–Ç•W6W%&W7G&–7F–öâçFVæçEö–BÓÒFVæçEö–B’¢&WGW&â&ööÂ‡&W7G&–7F–öâæBvWFGG"‡&W7G&–7F–öâÂb'¶7F–öçÕöF—6&ÆVB"ÂfÇ6R’  ¦FVbfÖ–Ç•öÖW76vUö6öçfW'6F–öâ†6öçfW'6F–öåö–C¢–çBÂW6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâfÖ–Ç”6öçfW'6F–öã ¢6öçfW'6F–öâÒ6W76–öâævWB„fÖ–Ç”6öçfW'6F–öâÂ6öçfW'6F–öåö–B¢–bæ÷B6öçfW'6F–öâ÷"W6W"æ–Bæ÷B–â¶6öçfW'6F–öâçW6W#ö–BÂ6öçfW'6F–öâçW6W#%ö–GÓ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â6öçfW'6F–öà  ¦FVbfÖ–Ç•öÖW76vUö&Æö6¶VB†6öçfW'6F–öã¢fÖ–Ç”6öçfW'6F–öâÂ6W76–öã¢6W76–öâ’Óâ&ööÃ ¢&WGW&â6W76–öâç66Æ"€¢6VÆV7B„fÖ–Ç”ÖW76vT&Æö6²æ–B’çv†W&R€¢fÖ–Ç”ÖW76vT&Æö6²çFVæçEö–BÓÒ6öçfW'6F–öâçFVæçEö–BÀ¢fÖ–Ç”ÖW76vT&Æö6²æ&Æö6¶W%ö–Bæ–åò…¶6öçfW'6F–öâçW6W#ö–BÂ6öçfW'6F–öâçW6W#%ö–EÒ’À¢fÖ–Ç”ÖW76vT&Æö6²æ&Æö6¶VEö–Bæ–åò…¶6öçfW'6F–öâçW6W#ö–BÂ6öçfW'6F–öâçW6W#%ö–EÒ’À¢¢’—2æ÷BæöæP  ¤dÔ”Å•ôÔU54tUôäõD”4RÒ.ZèXZzêyn8®8(8>888:89n8:¾Zûî[ùÎ8î8ş8(8[ø^Šh8®ZNY8¾™™8(®8xªÎˆˆîzêynˆ^8Î8:88>8+¾8;Î8+[^jÛN8).z+®Š¨Ş88(¾8>88Î8.8(®8î88"   ¤ævWB‚"öfÖ–Ç’öÖW76vW2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÖW76vW5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢6öçfW'6F–öç2Ò6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç”6öçfW'6F–öâ’çv†W&R„fÖ–Ç”6öçfW'6F–öâçFVæçEö–BÓÒFVæçBæ–B¢æ÷&FW%ö'’„fÖ–Ç”6öçfW'6F–öâæ7&VFVEöBæFW62‚’¢’æÆÂ‚¢&÷w2Ò" ¢f÷"6öçfW'6F–öâ–â6öçfW'6F–öç3 ¢ÆFW7BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vR’çv†W&R„fÖ–Ç”ÖW76vRæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–B’æ÷&FW%ö'’„fÖ–Ç”ÖW76vRç6VçEöBæFW62‚’’¢&Wf–WrÒ.8:88>8+¾8;Î8+8®8r"–bæ÷BÆFW7BVÇ6R‚.˜KúXùnkhkˆ8ò"–bÆFW7Bçv—F†G&våöBVÇ6RÆFW7Bæ&öG•³£CÒ¢&÷w2³ÒbrrsÇG#ãÇFCç¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†6öçfW'6F–öâçW6W#ö–BÂ6W76–öâ’—ÓÂ÷FCà¢ÇFCç¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†6öçfW'6F–öâçW6W#%ö–BÂ6W76–öâ’—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R‡&Wf–Wr—ÓÂ÷FCà¢ÇFCç².XŠyJKŠÒ"–b6öçfW'6F–öâæ7F—fRVÇ6R.XÎjÚ.KŠÒ'ÓÂ÷FCãÇFCãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öâæ–GÒ#î[^jÛN8).z+®Š¨ÓÂöãÂ÷FCãÂ÷G#ârrp¢&öG’ÒbrrsÆƒädÔ”Å8:88>8+¾8;Î8+zêycÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇç´dÔ”Å•ôÔU54tUôäõD”4WÓÂ÷à¢Çî[^jÛN8).™h¾8N8şi8ŞKÙÎ8(.Š‰˜Ë.8^8(Î8î88.Xéşih~8şZHi»N8¾8®8KˆŞ˜Xˆ~8®h©^z‹ş8î™ÙîŠzK®8zêyn8:8:.8î8şŠÎ88î88#Â÷ãÂöF—cà¢ÇF&ÆSãÇG#ãÇFƒîXø.XªˆSÂ÷FƒãÇFƒîXø.XªˆS#Â÷FƒãÇFƒîiÈikÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#R#îKÉ®Š›8ş8î88.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚$dÔ”Å8:88>8+¾8;Î8+zêyb"Â&öG’ÂW6W"  ¤ævWB‚"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öåö–GÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÖW76vW5öÖævUöFWF–Â†6öçfW'6F–öåö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢6öçfW'6F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”6öçfW'6F–öâ’çv†W&R„fÖ–Ç”6öçfW'6F–öâæ–BÓÒ6öçfW'6F–öåö–BÂfÖ–Ç”6öçfW'6F–öâçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B6öçfW'6F–öã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6W76–öâæFB„fÖ–Ç”ÖW76vTVF—B†6öçfW'6F–öåö–CÖ6öçfW'6F–öâæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂ7F–öãÒ'f–Wr"ÂFWF–Ç3Ò.zêynˆ^8Î[^jÛN8).™k.Šjr"’¢6W76–öâæ6öÖÖ—B‚¢ÖW76vW2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”ÖW76vR’çv†W&R„fÖ–Ç”ÖW76vRæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–B’æ÷&FW%ö'’„fÖ–Ç”ÖW76vRç6VçEöB’’æÆÂ‚¢6&G2Ò" ¢f÷"ÖW76vR–âÖW76vW3 ¢7FFW2Ò"ò"æ¦ö–â‡fÇVRf÷"fÇVR–â².˜KúXùnkhkˆ8ò"–bÖW76vRçv—F†G&våöBVÇ6R""Â.™ÙîŠzK¢"–bÖW76vRæ†–FFVåöBVÇ6R"%Ò–bfÇVR’÷".ŠzK®KŠÒ ¢6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÇãÇ7G&öæsç¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†ÖW76vRç6VæFW%ö–BÂ6W76–öâ’—ÓÂ÷7G&öæsî8¶ÖW76vRç6VçEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—Ş8Ç7â6Æ73Ò&&FvR#ç·7FFW7ÓÂ÷7ããÂ÷à¢Ç7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†ÖW76vRæ&öG’—ÓÂ÷à¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öâæ–GÒöÖW76vW2÷¶ÖW76vRæ–GÒöÖöFW&FR#à¢ÆÆ&VÃîzêyn8:8:#ÂöÆ&VÃãÆ–çWBæÖSÒ&FÖ–åöæ÷FR"Ö†ÆVæwFƒÒ#S"fÇVSÒ'¶‡FÖÂæW66R†ÖW76vRæFÖ–åöæ÷FR÷"rr—Ò#à¢Æ'WGFöâæÖSÒ&7F–öâ"fÇVSÒ'²wVæ†–FRr–bÖW76vRæ†–FFVåöBVÇ6Rv†–FRwÒ#ç²~XhŞŠzK¢r–bÖW76vRæ†–FFVåöBVÇ6R~XŠyJˆ^yK¾™Ú.8¾8(™ÙîŠzK¢wÓÂö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öÖW76vW2öÖævR#îKˆŠj~8h‹¾8(³ÂöãÆƒî8:88>8+¾8;Î8+[^jÛCÂöƒà¢Çç¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†6öçfW'6F–öâçW6W#ö–BÂ6W76–öâ’—Ò(iB¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†6öçfW'6F–öâçW6W#%ö–BÂ6W76–öâ’—ÓÂ÷à¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öâæ–GÒ÷7FFR#ãÆ'WGFöâæÖSÒ&7F—fR"fÇVSÒ'²wG'VRr–bæ÷B6öçfW'6F–öâæ7F—fRVÇ6RvfÇ6RwÒ#ç²~XŠyJ8).XhŞ™h²r–bæ÷B6öçfW'6F–öâæ7F—fRVÇ6R~8>8îKÉ®Š›8).XÎjÚ"wÓÂö'WGFöããÂöf÷&Óç¶6&G2÷"sÇî8:88>8+¾8;Î8+8ş8.8(®8î8¾8)>8#Â÷âwÒrrp¢&WGW&âÆ–÷WB‚.8:88>8+¾8;Î8+[^jÛB"Â&öG’ÂW6W"  ¤ç÷7B‚"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öåö–GÒ÷7FFR"¦FVbfÖ–Ç•öÖW76vW5öÖævU÷7FFR†6öçfW'6F–öåö–C¢–çBÂ7F—fS¢7G"Òf÷&Ò‚âââ’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢6öçfW'6F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”6öçfW'6F–öâ’çv†W&R„fÖ–Ç”6öçfW'6F–öâæ–BÓÒ6öçfW'6F–öåö–BÂfÖ–Ç”6öçfW'6F–öâçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B6öçfW'6F–öã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6öçfW'6F–öâæ7F—fRÒ7F—fRÓÒ'G'VR ¢6W76–öâæFB„fÖ–Ç”ÖW76vTVF—B†6öçfW'6F–öåö–CÖ6öçfW'6F–öâæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂ7F–öãÒ'&W7VÖR"–b6öçfW'6F–öâæ7F—fRVÇ6R'7W7VæB"ÂFWF–Ç3Ò.KÉ®Š›x«nhX¾8).ZHi»B"’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öâæ–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öåö–GÒöÖW76vW2÷¶ÖW76vUö–GÒöÖöFW&FR"¦FVbfÖ–Ç•öÖW76vUöÖöFW&FR†6öçfW'6F–öåö–C¢–çBÂÖW76vUö–C¢–çBÂ7F–öã¢7G"Òf÷&Ò‚âââ’ÂFÖ–åöæ÷FS¢7G"Òf÷&Ò‚""’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢6öçfW'6F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”6öçfW'6F–öâ’çv†W&R„fÖ–Ç”6öçfW'6F–öâæ–BÓÒ6öçfW'6F–öåö–BÂfÖ–Ç”6öçfW'6F–öâçFVæçEö–BÓÒFVæçBæ–B’¢ÖW76vRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vR’çv†W&R„fÖ–Ç”ÖW76vRæ–BÓÒÖW76vUö–BÂfÖ–Ç”ÖW76vRæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öåö–B’¢–bæ÷B6öçfW'6F–öâ÷"æ÷BÖW76vR÷"7F–öâæ÷B–â²&†–FR"Â'Væ†–FR'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢ÖW76vRæ†–FFVåöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’–b7F–öâÓÒ&†–FR"VÇ6RæöæP¢ÖW76vRæ†–FFVåö'•ö–BÒW6W"æ–B–b7F–öâÓÒ&†–FR"VÇ6RæöæP¢ÖW76vRæFÖ–åöæ÷FRÒFÖ–åöæ÷FRç7G&—‚•³£SÒ÷"æöæP¢6W76–öâæFB„fÖ–Ç”ÖW76vTVF—B†6öçfW'6F–öåö–CÖ6öçfW'6F–öâæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂ7F–öãÖ7F–öâÂFWF–Ç3Öb&ÖW76vUö–C×¶ÖW76vRæ–GÒ"’¢6W76–öâæFB„fÖ–Ç”ÖöFW&F–öäVF—B‡FVæçEö–C×FVæçBæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂF&vWE÷G—SÒ&ÖW76vR"ÂF&vWEö–CÖÖW76vRæ–BÂ7F–öãÖ7F–öâÂFWF–Ç3ÖÖW76vRæFÖ–åöæ÷FR’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öÖW76vW2öÖævR÷¶6öçfW'6F–öâæ–GÒ"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öÖW76vW2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÖW76vW2‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢6öçfW'6F–öç2Ò6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç”6öçfW'6F–öâ’çv†W&R‚„fÖ–Ç”6öçfW'6F–öâçW6W#ö–BÓÒW6W"æ–B’Â„fÖ–Ç”6öçfW'6F–öâçW6W#%ö–BÓÒW6W"æ–B’¢æ÷&FW%ö'’„fÖ–Ç”6öçfW'6F–öâæ7&VFVEöBæFW62‚’¢’æÆÂ‚¢6&G2Ò" ¢f÷"6öçfW'6F–öâ–â6öçfW'6F–öç3 ¢÷F†W%ö–BÒ6öçfW'6F–öâçW6W#%ö–B–b6öçfW'6F–öâçW6W#ö–BÓÒW6W"æ–BVÇ6R6öçfW'6F–öâçW6W#ö–@¢ÆFW7BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vR’çv†W&R„fÖ–Ç”ÖW76vRæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–B’æ÷&FW%ö'’„fÖ–Ç”ÖW76vRç6VçEöBæFW62‚’’¢&VBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vU&VB’çv†W&R„fÖ–Ç”ÖW76vU&VBæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–BÂfÖ–Ç”ÖW76vU&VBçW6W%ö–BÓÒW6W"æ–B’¢Vç&VBÒ&ööÂ†ÆFW7BæBÆFW7Bç6VæFW%ö–BÒW6W"æ–BæB†æ÷B&VB÷"ÆFW7Bç6VçEöBâ&VBæÆ7E÷&VEöB’¢&Wf–WrÒ.8î88:88>8+¾8;Î8+8ş8.8(®8î8¾8)2"–bæ÷BÆFW7BVÇ6R‚.˜Kú8ÎXùn8(®kh8^8(Î8î8~8ò"–bÆFW7Bçv—F†G&våöBVÇ6R‚.zêynˆ^8¾8(8(®™ÙîŠzK¢"–bÆFW7Bæ†–FFVåöBVÇ6RÆFW7Bæ&öG•³£SUÒ’¢6&G2³ÒbrrsÆ6Æ73Ò&ÖöGVÆR"‡&VcÒ"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ#ãÆƒ3ç¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†÷F†W%ö–BÂ6W76–öâ’—Ò²sÇ7â6Æ73Ò&&FvR#îiÊ®ŠªÓÂ÷7ãâr–bVç&VBVÇ6RrwÓÂöƒ3à¢Çç¶‡FÖÂæW66R‡&Wf–Wr—ÓÂ÷ãÇãÇ6ÖÆÃç²~XŠyJKŠÒr–b6öçfW'6F–öâæ7F—fRVÇ6R~xªÎˆˆî8¾8(8(®XÎjÚ.KŠÒwÓÂ÷6ÖÆÃãÂ÷ãÂöârrp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒî8:88>8+¾8;Î8+ƒÂöƒà¢ÆF—b6Æ73Ò'FVæçB#ãÇç´dÔ”Å•ôÔU54tUôäõD”4WÓÂ÷ãÇî˜Kú[èÎ8îXéşih~{z™¸n8ş8~8Ş8î8¾8)>8.[ø^Šh8®ZNY8ş˜KúXùnkh8).8NXŠyJ8ş88^8N8#Â÷ãÂöF—cà¢ÆF—b6Æ73Ò&w&–B#ç¶6&G2÷"sÇîKÉ®Š›8ş8î88.8(®8î8¾8)>8.XZÎ™h¾89~8:Ş89^8*>8;Î8:¾8î8Î8:88>8+¾8;Î8+8).˜8(¾8Ş8¾8(™h¾Zx¾8~8Ş8î88#Â÷âwÓÂöF—cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.8:88>8+¾8;Î8+ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öÖW76vW2÷7F'B÷·V&Æ–5ö–GÒ"¦FVbfÖ–Ç•öÖW76vU÷7F'B‡V&Æ–5ö–C¢7G"ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçV&Æ–5ö–BÓÒV&Æ–5ö–BÂ÷væW%&öf–ÆRç&öf–ÆU÷V&Æ–2æ—5ò…G'VR’’¢–bæ÷B&öf–ÆR÷"&öf–ÆRçW6W%ö–BÓÒW6W"æ–C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8>8îy»h˜¾88şKÉ®Š›8).™h¾Zx¾8~8Ş8î8¾8)2"¢6†&VBÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ’bfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡6W76–öâævWB…W6W"Â&öf–ÆRçW6W%ö–B’Â6W76–öâ¢–bæ÷B6†&VC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.YÎ8xªÎˆˆî8ädÔ”Å™i>8~8î8şXŠyJ8~8Ş8î8’"¢FVæçEö–BÒ6÷'FVB‡6†&VB•³Ğ¢W6W#ö–BÂW6W#%ö–BÒ6÷'FVB…·W6W"æ–BÂ&öf–ÆRçW6W%ö–EÒ¢6öçfW'6F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”6öçfW'6F–öâ’çv†W&R„fÖ–Ç”6öçfW'6F–öâçFVæçEö–BÓÒFVæçEö–BÂfÖ–Ç”6öçfW'6F–öâçW6W#ö–BÓÒW6W#ö–BÂfÖ–Ç”6öçfW'6F–öâçW6W#%ö–BÓÒW6W#%ö–B’¢–bæ÷B6öçfW'6F–öã ¢6öçfW'6F–öâÒfÖ–Ç”6öçfW'6F–öâ‡FVæçEö–C×FVæçEö–BÂW6W#ö–C×W6W#ö–BÂW6W#%ö–C×W6W#%ö–B¢6W76–öâæFB†6öçfW'6F–öâ¢6W76–öâæ6öÖÖ—B‚¢6W76–öâç&Vg&W6‚†6öçfW'6F–öâ¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öåö–GÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÖW76vUöFWF–Â†6öçfW'6F–öåö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢6öçfW'6F–öâÒfÖ–Ç•öÖW76vUö6öçfW'6F–öâ†6öçfW'6F–öåö–BÂW6W"Â6W76–öâ¢÷F†W%ö–BÒ6öçfW'6F–öâçW6W#%ö–B–b6öçfW'6F–öâçW6W#ö–BÓÒW6W"æ–BVÇ6R6öçfW'6F–öâçW6W#ö–@¢&VBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vU&VB’çv†W&R„fÖ–Ç”ÖW76vU&VBæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–BÂfÖ–Ç”ÖW76vU&VBçW6W%ö–BÓÒW6W"æ–B’¢–b&VC ¢&VBæÆ7E÷&VEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢VÇ6S ¢6W76–öâæFB„fÖ–Ç”ÖW76vU&VB†6öçfW'6F–öåö–CÖ6öçfW'6F–öâæ–BÂW6W%ö–C×W6W"æ–B’¢6W76–öâæ6öÖÖ—B‚¢ÖW76vW2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”ÖW76vR’çv†W&R„fÖ–Ç”ÖW76vRæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öâæ–B’æ÷&FW%ö'’„fÖ–Ç”ÖW76vRç6VçEöB’’æÆÂ‚¢6&G2Ò" ¢f÷"ÖW76vR–âÖW76vW3 ¢Ö–æRÒÖW76vRç6VæFW%ö–BÓÒW6W"æ–@¢–bÖW76vRæ†–FFVåöC ¢6öçFVçBÒ.zêynˆ^8¾8(8(®™ÙîŠzK®8¾8®8(®8î8~8ò ¢VÆ–bÖW76vRçv—F†G&våöC ¢6öçFVçBÒ.˜Kú8ÎXùn8(®kh8^8(Î8î8~8ò ¢VÇ6S ¢6öçFVçBÒ‡FÖÂæW66R†ÖW76vRæ&öG’¢v—F†G&rÒbsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ÷¶ÖW76vRæ–GÒ÷v—F†G&r#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#î˜KúXùnkhƒÂö'WGFöããÂöf÷&Óâr–bÖ–æRæBæ÷BÖW76vRçv—F†G&våöBæBæ÷BÖW76vRæ†–FFVåöBVÇ6R" ¢&W÷'EöÆ–æ²ÒbsÆ‡&VcÒ"öfÖ–Ç’÷6fWG’÷&W÷'C÷F&vWE÷G—SÖÖW76vRf×·F&vWEö–C×¶ÖW76vRæ–GÒf×·FVæçEö–C×¶6öçfW'6F–öâçFVæçEö–GÒ#ãÇ6ÖÆÃîxªÎˆˆî8˜	®ZÂ÷6ÖÆÃãÂöâr–bæ÷BÖ–æRæBæ÷BÖW76vRçv—F†G&våöBVÇ6R" ¢6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò'FVæçB"7G–ÆSÒ&Ö&v–âÖÆVgC§²s‚Rr–bÖ–æRVÇ6RswÓ¶Ö&v–â×&–v‡C§²sr–bÖ–æRVÇ6Rs‚RwÒ#ãÇãÇ7G&öæsç²~8.8®8òr–bÖ–æRVÇ6R‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†÷F†W%ö–BÂ6W76–öâ’—ÓÂ÷7G&öæsâÇ6ÖÆÃç¶ÖW76vRç6VçEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—ÓÂ÷6ÖÆÃãÂ÷ãÇ7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶6öçFVçGÓÂ÷ç·v—F†G&wÒ·&W÷'EöÆ–æ·ÓÂö'F–6ÆSârrp¢&Æö6¶VBÒfÖ–Ç•öÖW76vUö&Æö6¶VB†6öçfW'6F–öâÂ6W76–öâ¢6VæEöf÷&ÒÒbrrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ#ãÆÆ&VÃî8:88>8+¾8;Î8+ûÈƒih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&&öG’"Ö†ÆVæwFƒÒ#"&WV—&VCãÂ÷FW‡F&VãÆ'WGFöãî˜Kú88(³Âö'WGFöããÂöf÷&Óârrr–b6öçfW'6F–öâæ7F—fRæBæ÷B&Æö6¶VBVÇ6RsÆF—b6Æ73Ò'FVæçB#ãÇîxûîYÊ88>8îKÉ®Š›8¾8ş˜Kú8~8Ş8î8¾8)>8#Â÷ãÂöF—câp¢÷våö&Æö6²Ò6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vT&Æö6²’çv†W&R„fÖ–Ç”ÖW76vT&Æö6²çFVæçEö–BÓÒ6öçfW'6F–öâçFVæçEö–BÂfÖ–Ç”ÖW76vT&Æö6²æ&Æö6¶W%ö–BÓÒW6W"æ–BÂfÖ–Ç”ÖW76vT&Æö6²æ&Æö6¶VEö–BÓÒ÷F†W%ö–B’¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öÖW76vW2#î8:88>8+¾8;Î8+KˆŠj~8h‹¾8(³ÂöãÆƒç¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†÷F†W%ö–BÂ6W76–öâ’—Ş8^8)3Âöƒà¢ÇãÇ6ÖÆÃç´dÔ”Å•ôÔU54tUôäõD”4WÓÂ÷6ÖÆÃãÂ÷ç¶6&G2÷"sÇîiÈX‰Ş8î8:88>8+¾8;Î8+8).˜8>8n8ş8î8~8(~8n8#Â÷âw×·6VæEöf÷&×Ğ¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒö&Æö6²#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#ç²~89n8:Ş88>8*ş8).Šz>™šBr–b÷våö&Æö6²VÇ6R~8>8îy»h˜¾8).89n8:Ş88>8*òwÓÂö'WGFöããÂöf÷&Óârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.8:88>8+¾8;Î8+ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öåö–GÒ"¦FVbfÖ–Ç•öÖW76vU÷6VæB†6öçfW'6F–öåö–C¢–çBÂ&öG“¢7G"Òf÷&Ò‚âââ’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢6öçfW'6F–öâÒfÖ–Ç•öÖW76vUö6öçfW'6F–öâ†6öçfW'6F–öåö–BÂW6W"Â6W76–öâ¢–bfÖ–Ç•ö7F–öåöF—6&ÆVB‡W6W"æ–BÂ6öçfW'6F–öâçFVæçEö–BÂ&ÖW76vW2"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.xªÎˆˆî8¾8(8(®8:88>8+¾8;Î8+j™şˆ;Ş8ÎXÎjÚ.8^8(Î8n8N8î8’"¢ÖW76vUö&öG’Ò&öG’ç7G&—‚¢–bæ÷BÖW76vUö&öG’÷"ÆVâ†ÖW76vUö&öG’’â ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8:88>8+¾8;Î8+8ó8	Ãih~ZÙ~8~XZ^X©¾8~8n8ş88^8B"¢–bæ÷B6öçfW'6F–öâæ7F—fR÷"fÖ–Ç•öÖW76vUö&Æö6¶VB†6öçfW'6F–öâÂ6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.xûîYÊ88>8îKÉ®Š›8¾8ş˜Kú8~8Ş8î8¾8)2"¢&V6—–VçEö–BÒ6öçfW'6F–öâçW6W#%ö–B–b6öçfW'6F–öâçW6W#ö–BÓÒW6W"æ–BVÇ6R6öçfW'6F–öâçW6W#ö–@¢&V6—–VçBÒ6W76–öâævWB…W6W"Â&V6—–VçEö–B¢6VæEöVÖ–ÂÒ&ööÂ‡&V6—–VçBæBVÖ–Åöæ÷F–f–6F–öåöÆÆ÷vVB‡&V6—–VçBÂ&ÖW76vW2"Â6W76–öâ’¢ÖW76vRÒfÖ–Ç”ÖW76vR†6öçfW'6F–öåö–CÖ6öçfW'6F–öâæ–BÂ6VæFW%ö–C×W6W"æ–BÂ&öG“ÖÖW76vUö&öG’¢6W76–öâæFB†ÖW76vR¢6W76–öâæfÇW6‚‚¢–b6VæEöVÖ–Ã ¢&6U÷W&ÂÒ÷2æVçf—&öâævWB‚$ô$4UõU$Â"Â&‡GG3¢òöFörÖÖævVÖVçBæ&VæVf—BÖæf’æ6öÒ"’ç'7G&—‚"ò"¢&Wf–WrÒÖW76vUö&öG•³£#Ò²‚.(
b"–bÆVâ†ÖW76vUö&öG’’â#VÇ6R""¢VWVUöVÖ–Â‡6W76–öâÂ&V6—–VçBæVÖ–ÂÂ&æWuöÖW76vR"Â.8	U5E$TÄÄdÔ”Å8	ik8~8N8:88>8+¾8;Î8+8Î[®8Ş8î8~8ò"À¢b'·&V6—–VçBææÖWÒjy…ÆåÆç¶fÖ–Ç•öÖW76vUöæÖR‡W6W"æ–BÂ6W76–öâ—Ş8^8)>8¾8(8:88>8+¾8;Î8+8Î[®8Ş8î8~8ş8%ÆåÆç·&Wf–WwÕÆåÆîz+®Š¨Ş88(¾ûÉ§¶&6U÷W&ÇÒöfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ"À¢6öçfW'6F–öâçFVæçEö–BÂ&V6—–VçBæ–BÂb&ÖW76vS§¶ÖW76vRæ–GÒ"¢–b&V6—–VçBæB&V6—–VçBæ7F—fS ¢6VæE÷vV%÷W6‚‡&V6—–VçBæ–BÂ&ÖW76vW2"Â.ik8~8N8:88>8+¾8;Î8+8Î[®8Ş8î8~8ò"Â&Wf–Wr–b6VæEöVÖ–ÂVÇ6RÖW76vUö&öG•³£#ÒÀ¢b"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ"Âb'W6ƒ¦ÖW76vS§¶ÖW76vRæ–GÒ"Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öåö–GÒ÷¶ÖW76vUö–GÒ÷v—F†G&r"¦FVbfÖ–Ç•öÖW76vU÷v—F†G&r†6öçfW'6F–öåö–C¢–çBÂÖW76vUö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢fÖ–Ç•öÖW76vUö6öçfW'6F–öâ†6öçfW'6F–öåö–BÂW6W"Â6W76–öâ¢ÖW76vRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vR’çv†W&R„fÖ–Ç”ÖW76vRæ–BÓÒÖW76vUö–BÂfÖ–Ç”ÖW76vRæ6öçfW'6F–öåö–BÓÒ6öçfW'6F–öåö–BÂfÖ–Ç”ÖW76vRç6VæFW%ö–BÓÒW6W"æ–B’¢–bæ÷BÖW76vS ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢ÖW76vRçv—F†G&våöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öåö–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öåö–GÒö&Æö6²"¦FVbfÖ–Ç•öÖW76vUö&Æö6²†6öçfW'6F–öåö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢6öçfW'6F–öâÒfÖ–Ç•öÖW76vUö6öçfW'6F–öâ†6öçfW'6F–öåö–BÂW6W"Â6W76–öâ¢÷F†W%ö–BÒ6öçfW'6F–öâçW6W#%ö–B–b6öçfW'6F–öâçW6W#ö–BÓÒW6W"æ–BVÇ6R6öçfW'6F–öâçW6W#ö–@¢&Æö6²Ò6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”ÖW76vT&Æö6²’çv†W&R„fÖ–Ç”ÖW76vT&Æö6²çFVæçEö–BÓÒ6öçfW'6F–öâçFVæçEö–BÂfÖ–Ç”ÖW76vT&Æö6²æ&Æö6¶W%ö–BÓÒW6W"æ–BÂfÖ–Ç”ÖW76vT&Æö6²æ&Æö6¶VEö–BÓÒ÷F†W%ö–B’¢–b&Æö6³ ¢6W76–öâæFVÆWFR†&Æö6²¢VÇ6S ¢6W76–öâæFB„fÖ–Ç”ÖW76vT&Æö6²‡FVæçEö–CÖ6öçfW'6F–öâçFVæçEö–BÂ&Æö6¶W%ö–C×W6W"æ–BÂ&Æö6¶VEö–CÖ÷F†W%ö–B’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’ö¶VææVÂ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö¶VææVÅ÷vR‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢"".YÎ8xªÎˆˆî8¾8(‹øî88ş8XZÎ™h¾8¾YÎhHşkˆ8ş8ädÔ”Å8).xªÎˆˆîXŠ^8¾ŠzK®88(¾8""" ¢FVæçEö–G2ÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ¢–bæ÷BFVæçEö–G3 ¢&öG’ÒrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒîxªÎˆˆädÔ”ÅKÉ£Âöƒà¢ÆF—b6Æ73Ò'FVæçB#ãÇîhI¾xªÎ8î8ş8şxªÎˆˆî88î˜
>i®8Î8î88.8(®8î8¾8)>8#Â÷ãÇîxªÎˆˆî88y›¾˜Ë.8~8ş8:8;Î8:¾8*.888:Î8+8).8®yú^8(8¾8ş88^8N8#Â÷ãÂöF—cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.xªÎˆˆädÔ”ÅKÉ¢"Â&öG’ÂW6W"Â6W76–öâ ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B…FVæçBÂ÷væW%&öf–ÆRÂFör’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–B¢æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B’æ¦ö–â„÷væW%&öf–ÆRÂ÷væW%&öf–ÆRçW6W%ö–BÓÒFöt÷væW'6†—çW6W%ö–B¢çv†W&R…FVæçBæ–Bæ–åò‡FVæçEö–G2’ÂFVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’À¢Föt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’Â÷væW%&öf–ÆRç&öf–ÆU÷V&Æ–2æ—5ò…G'VR’À¢÷væW%&öf–ÆRç6†÷uöFöw2æ—5ò…G'VR’¢æ÷&FW%ö'’…FVæçBææÖRÂ÷væW%&öf–ÆRçWFFVEöBæFW62‚’ÂFöræ6ÆÅöæÖR¢’æÆÂ‚¢w&÷WVC¢F–7E¶–çBÂF–7EÒÒ·Ğ¢f÷"FVæçBÂ&öf–ÆRÂFör–â&V6÷&G3 ¢FVæçEöw&÷WÒw&÷WVBç6WFFVfVÇB‡FVæçBæ–BÂ²'FVæçB#¢FVæçBÂ&ÖVÖ&W'2#¢·×Ò¢ÖVÖ&W"ÒFVæçEöw&÷W²&ÖVÖ&W'2%Òç6WFFVfVÇB‡&öf–ÆRæ–BÂ²'&öf–ÆR#¢&öf–ÆRÂ&Föw2#¢·×Ò¢ÖVÖ&W%²&Föw2%Õ¶Föræ–EÒÒFöp ¢6V7F–öç2Ò" ¢f÷"w&÷W–âw&÷WVBçfÇVW2‚“ ¢FVæçBÂÖVÖ&W%ö6&G2Òw&÷W²'FVæçB%ÒÂ" ¢f÷"ÖVÖ&W"–âw&÷W²&ÖVÖ&W'2%ÒçfÇVW2‚“ ¢&öf–ÆRÂFöw2ÒÖVÖ&W%²'&öf–ÆR%ÒÂÆ—7B†ÖVÖ&W%²&Föw2%ÒçfÇVW2‚’¢ÖVÖ&W%öæÖRÒ&öf–ÆRææ–6¶æÖR–b&öf–ÆRç6†÷uöæ–6¶æÖRæB&öf–ÆRææ–6¶æÖRVÇ6R$dÔ”Å8:8;>898;Â ¢Æö6F–öâÒ&öf–ÆRç&VfV7GW&R–b&öf–ÆRç6†÷u÷&VfV7GW&RæB&öf–ÆRç&VfV7GW&RVÇ6R.YËYùş™ÙîXZÎ™h² ¢†÷FòÒbsÆ–Ör7&3Ò"öfÖ–Ç’öÖVÖ&W'2÷·&öf–ÆRçV&Æ–5ö–GÒ÷†÷Fò"ÇCÒ""7G–ÆSÒ'v–GFƒ£s'ƒ¶†V–v‡C£s'ƒ¶ö&¦V7BÖf—C¦6÷fW#¶&÷&FW"×&F—W3£SS¶Ö&v–âÖ&÷GFöÓ£‚#âr–b&öf–ÆRç6†÷u÷†÷FòæB&öf–ÆRç†÷FõöFFVÇ6RsÆF—b7G–ÆSÒ'v–GFƒ£s'ƒ¶†V–v‡C£s'ƒ¶&÷&FW"×&F—W3£SS¶F—7Æ“¦w&–C·Æ6RÖ—FV×3¦6VçFW#¶&6¶w&÷VæC¢6VCCS¶föçB×6—¦S£#gƒ¶Ö&v–âÖ&÷GFöÓ£‚#î)šÂöF—câp¢FöuöæÖW2Ò.8"æ¦ö–â†‡FÖÂæW66R†Föræ6ÆÅöæÖR’f÷"För–âFöw5³£EÒ¢–bÆVâ†Föw2’âC ¢FöuöæÖW2³Òb"8¾8·¶ÆVâ†Föw2’ÒGŞš
Ò ¢÷våö&FvRÒrÇ7â6Æ73Ò&&FvR#î8.8®8óÂ÷7ãâr–b&öf–ÆRçW6W%ö–BÓÒW6W"æ–BVÇ6R" ¢–ç7Fw&ÒÒbsÇä–ç7Fw&ŞûÉ¤¶‡FÖÂæW66R‡&öf–ÆRæ–ç7Fw&Õ÷W6W&æÖR—ÓÂ÷âr–b&öf–ÆRç6†÷uö–ç7Fw&ÒæB&öf–ÆRæ–ç7Fw&Õ÷W6W&æÖRVÇ6R" ¢ÖVÖ&W%ö6&G2³ÒbrrsÆ6Æ73Ò&ÖöGVÆR"‡&VcÒ"öfÖ–Ç’öÖVÖ&W'2÷·&öf–ÆRçV&Æ–5ö–GÒ#ç·†÷F÷ÓÆƒ3ç¶‡FÖÂæW66R†ÖVÖ&W%öæÖR—×¶÷våö&FvWÓÂöƒ3à¢Çç¶‡FÖÂæW66R†Æö6F–öâ—ÓÂ÷ç¶–ç7Fw&×ÓÇãÇ7G&öæsîhI¾xªÎûÉ£Â÷7G&öæsç¶FöuöæÖW7ÓÂ÷ãÇãÇ7â6Æ73Ò&&FvR#ç¶ÆVâ†Föw2—Şš
ÓÂ÷7ããÂ÷ãÂöârrp¢6V7F–öç2³ÒbrrsÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ"7G–ÆSÒ&Ö&v–â×F÷£#ç¶‡FÖÂæW66R‡FVæçBææÖR—ÒdÔ”ÅKÉ£Âöƒ#à¢ÇîYÎ8xªÎˆˆî8¾8(hI¾xªÎ8).‹øî88ş8XZÎ™h¾KŠŞ8î8*®8;Î88®8;Îjy8~88#Â÷ãÆF—b6Æ73Ò&w&–B#ç¶ÖVÖ&W%ö6&G2÷"sÇîXZÎ™h¾KŠŞ8î8:8;>898;Î8ş8î88N8î8¾8)>8#Â÷âwÓÂöF—cãÂ÷6V7F–öãârrp¢–bæ÷B6V7F–öç3 ¢FVæçEöæÖW2Ò6W76–öâç66Æ'2‡6VÆV7B…FVæçBææÖR’çv†W&R…FVæçBæ–Bæ–åò‡FVæçEö–G2’’æ÷&FW%ö'’…FVæçBææÖR’’æÆÂ‚¢6V7F–öç2Ò""æ¦ö–â†bsÇ6V7F–öâ6Æ73Ò'FVæçB#ãÆƒ"7G–ÆSÒ&Ö&v–â×F÷£#ç¶‡FÖÂæW66R†æÖR—ÒdÔ”ÅKÉ£Âöƒ#ãÇîXZÎ™h¾KŠŞ8î8:8;>898;Î8ş8î88N8î8¾8)>8#Â÷ãÂ÷6V7F–öãârf÷"æÖR–âFVæçEöæÖW2¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒîxªÎˆˆädÔ”ÅKÉ£Âöƒà¢ÇîŠ{ˆ8¾8¾8¾8(ş8(8®8YÎ8xªÎˆˆî8¾8(hI¾xªÎ8).‹øî88ôdÔ”ÅYÎZ:¾8Î8N8®8Î8(¾89®8;Î8+8~88.XZÎ™h¾8).Š‹Xúş8~8ş89~8:Ş89^8*>8;Î8:¾8hI¾xªÎ888).ŠzK®8~8î88#Â÷ç·6V7F–öç7Ğ¢ÇãÇ6ÖÆÃîŠzK®Xh^Zë8şYN8*®8;Î88®8;Îjy8îXZÎ™h¾89~8:Ş89^8*>8;Î8:¾ŠŠŞZé®8¾[é>8N8î88#Â÷6ÖÆÃãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.xªÎˆˆädÔ”ÅKÉ®ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¦FVbfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W#¢W6W"Â6W76–öã¢6W76–öâ’ÓâF–7E¶–çBÂGWÆU´fÖ–Ç”FötÆ'VÔ—FVÒÂFörÂFVæçBÂ÷væW%&öf–ÆUÕÓ ¢"".™k.Šj~ˆ^8¾XZÎ™h¾8~8Ş8(¾h‰™[~8*.8:¾898:h©^z‹ş8).‹ùN88""" ¢6÷W&6UöFöw2Ò6W76–öâç66Æ'2€¢6VÆV7B„För’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’¢’æÆÂ‚¢FVæçEö–G2ÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒÂFörÂFVæçBÂ÷væW%&öf–ÆR¢æ÷F–öç2†FVfW"„fÖ–Ç”FötÆ'VÔ—FVÒç†÷FõöFF’¢æ¦ö–â„FörÂFöræ–BÓÒfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFörçFVæçEö–B¢æ¦ö–â„÷væW%&öf–ÆRÂ÷væW%&öf–ÆRçW6W%ö–BÓÒfÖ–Ç”FötÆ'VÔ—FVÒçWÆöFVEö'•ö–B¢çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒçf—6–&–Æ—G’æ–åò…²&fÖ–Ç’"Â'&VÆF—fW2%Ò’ÂFöræ7F—fRæ—5ò…G'VR’À¢FVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’Â÷væW%&öf–ÆRç&öf–ÆU÷V&Æ–2æ—5ò…G'VR’À¢÷væW%&öf–ÆRç6†÷uöFöw2æ—5ò…G'VR’¢æ÷&FW%ö'’„fÖ–Ç”FötÆ'VÔ—FVÒæ7&VFVEöBæFW62‚’ÂfÖ–Ç”FötÆ'VÔ—FVÒç†÷Fõö÷&FW"’æÆ–Ö—Bƒ¢’æÆÂ‚¢f—6–&ÆS¢F–7E¶–çBÂGWÆU´fÖ–Ç”FötÆ'VÔ—FVÒÂFörÂFVæçBÂ÷væW%&öf–ÆUÕÒÒ·Ğ¢6†÷våöw&÷W3¢6WE·7G%ÒÒ6WB‚¢f÷"—FVÒÂFörÂFVæçBÂ&öf–ÆR–â&V6÷&G3 ¢ÆÆ÷vVBÒ—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–@¢–b—FVÒçf—6–&–Æ—G’ÓÒ&fÖ–Ç’"æBFörçFVæçEö–B–âFVæçEö–G3 ¢ÆÆ÷vVBÒG'VP¢–b—FVÒçf—6–&–Æ—G’ÓÒ'&VÆF—fW2"æBç’†fÖ–Ç•÷&VÆF–öç6†—‡6W76–öâÂ6÷W&6RÂFör’f÷"6÷W&6R–â6÷W&6UöFöw2“ ¢ÆÆ÷vVBÒG'VP¢–bÆÆ÷vVC ¢–b—FVÒç÷7Eöw&÷WæB—FVÒç÷7Eöw&÷W–â6†÷våöw&÷W3 ¢6öçF–çVP¢–b—FVÒç÷7Eöw&÷W ¢6†÷våöw&÷W2æFB†—FVÒç÷7Eöw&÷W¢f—6–&ÆU¶—FVÒæ–EÒÒ†—FVÒÂFörÂFVæçBÂ&öf–ÆR¢&WGW&âf—6–&ÆP  ¤ævWB‚"öfÖ–Ç’÷F–ÖVÆ–æR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷F–ÖVÆ–æR†¶VææVÅö–C¢–çBÒÂFöuö–C¢–çBÒÂ66÷S¢7G"Ò""ÂvS¢–çBÒÀ¢W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢f—6–&ÆRÒfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ¢ÆÅ÷&V6÷&G2ÒÆ—7B‡f—6–&ÆRçfÇVW2‚’¢¶VææVÇ2Ò·FVæçBæ–C¢FVæçBææÖRf÷"òÂòÂFVæçBÂò–âÆÅ÷&V6÷&G7Ğ¢Föw2Ò¶Föræ–C¢Föræ6ÆÅöæÖRf÷"òÂFörÂòÂò–âÆÅ÷&V6÷&G2–bæ÷B¶VææVÅö–B÷"FörçFVæçEö–BÓÒ¶VææVÅö–GĞ¢f–ÇFW&VBÒµĞ¢f÷"&V6÷&B–âÆÅ÷&V6÷&G3 ¢—FVÒÂFörÂFVæçBÂòÒ&V6÷&@¢–b¶VææVÅö–BæBFVæçBæ–BÒ¶VææVÅö–C ¢6öçF–çVP¢–bFöuö–BæBFöræ–BÒFöuö–C ¢6öçF–çVP¢–b66÷RÓÒ&Ö–æR"æB—FVÒçWÆöFVEö'•ö–BÒW6W"æ–C ¢6öçF–çVP¢–b66÷R–â²&fÖ–Ç’"Â'&VÆF—fW2'ÒæB—FVÒçf—6–&–Æ—G’Ò66÷S ¢6öçF–çVP¢f–ÇFW&VBæVæB‡&V6÷&B¢vU÷6—¦RÒC€¢F÷FÂÒÆVâ†f–ÇFW&VB¢F÷FÅ÷vW2ÒÖ‚ƒÂ‡F÷FÂ²vU÷6—¦RÒ’òòvU÷6—¦R¢vRÒÖ–â†Ö‚‡vRÂ’ÂF÷FÅ÷vW2¢vU÷&V6÷&G2Òf–ÇFW&VE²‡vRÒ’¢vU÷6—¦S§vR¢vU÷6—¦UĞ¢vUö–G2Ò¶—FVÒæ–Bf÷"—FVÒÂòÂòÂò–âvU÷&V6÷&G5Ğ¢Æ–¶Uö6÷VçG2ÒF–7B‡6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æTÆ–¶RæÆ'VÕö—FVÕö–BÂgVæ2æ6÷VçB„fÖ–Ç•F–ÖVÆ–æTÆ–¶Ræ–B’’çv†W&R€¢fÖ–Ç•F–ÖVÆ–æTÆ–¶RæÆ'VÕö—FVÕö–Bæ–åò‡vUö–G2’’æw&÷Wö'’„fÖ–Ç•F–ÖVÆ–æTÆ–¶RæÆ'VÕö—FVÕö–B’’æÆÂ‚’’–bvUö–G2VÇ6R·Ğ¢6öÖÖVçEö6÷VçG2ÒF–7B‡6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–BÂgVæ2æ6÷VçB„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ–B’’çv†W&R€¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–Bæ–åò‡vUö–G2’ÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæFVÆWFVEöBæ—5ò„æöæR’À¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ†–FFVåöBæ—5ò„æöæR’’æw&÷Wö'’„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–B’’æÆÂ‚’’–bvUö–G2VÇ6R·Ğ¢÷7G2Ò" ¢f÷"—FVÒÂFörÂFVæçBÂ&öf–ÆR–âvU÷&V6÷&G3 ¢F¶VâÒ—FVÒçF¶Våööâç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"’–b—FVÒçF¶VåööâVÇ6R—FVÒæ7&VFVEöBæFFR‚’ç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"¢Æ–¶Uö6÷VçBÂ6öÖÖVçEö6÷VçBÒÆ–¶Uö6÷VçG2ævWB†—FVÒæ–BÂ’Â6öÖÖVçEö6÷VçG2ævWB†—FVÒæ–BÂ¢†÷Fõö6÷VçBÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç”FötÆ'VÔ—FVÒæ–B’’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒç÷7Eöw&÷WÓÒ—FVÒç÷7Eöw&÷W’’–b—FVÒç÷7Eöw&÷WVÇ6R¢÷7G2³ÒbrrsÆ6Æ73Ò'F–ÖVÆ–æR×F–ÆR"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ#à¢Æ–Ör7&3Ò"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ÷†÷Fò"ÇCÒ'¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îh‰™[~XiyÉò"ÆöF–æsÒ&Æ§’#à¢Ç7â6Æ73Ò'F–ÖVÆ–æRÖ÷fW&Æ’#ãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—×²~8)j2r²7G"‡†÷Fõö6÷VçB’–b†÷Fõö6÷VçBâVÇ6RrwÓÂ÷7G&öæsà¢Ç7â6Æ73Ò'F–ÖVÆ–æR×7FG2#ãÇ7ãç·F¶VçÓÂ÷7ããÇ7ãî)šR¶Æ–¶Uö6÷VçGŞ8	ù*Â¶6öÖÖVçEö6÷VçGÓÂ÷7ããÂ÷7ããÂ÷7ããÂöârrp¢–bæ÷B÷7G3 ¢÷7G2ÒrrsÆF—b6Æ73Ò'FVæçB"7G–ÆSÒ&w&–BÖ6öÇVÖã£òÓ#ãÇîiÚK»n8¾Kˆˆ{N88(¾XiyÉş8ş8.8(®8î8¾8)>8#Â÷ãÇî{Yî8(®‹ëÎ8şiÚK»n8).ZHi»N8~8n8Nz+®Š¨Ş8ş88^8N8#Â÷ãÂöF—cârrp¢¶VææVÅö÷F–öç2ÒsÆ÷F–öâfÇVSÒ##î888n8îxªÎˆˆãÂö÷F–öãâr²""æ¦ö–â€¢bsÆ÷F–öâfÇVSÒ'¶¶W—Ò"²'6VÆV7FVB"–b¶VææVÅö–BÓÒ¶W’VÇ6R"'Óç¶‡FÖÂæW66R‡fÇVR—ÓÂö÷F–öãârf÷"¶W’ÂfÇVR–â6÷'FVB†¶VææVÇ2æ—FV×2‚’Â¶W“ÖÆÖ&F&÷s¢&÷u³Ò’¢Föuö÷F–öç2ÒsÆ÷F–öâfÇVSÒ##î888n8îhI¾xªÃÂö÷F–öãâr²""æ¦ö–â€¢bsÆ÷F–öâfÇVSÒ'¶¶W—Ò"²'6VÆV7FVB"–bFöuö–BÓÒ¶W’VÇ6R"'Óç¶‡FÖÂæW66R‡fÇVR—ÓÂö÷F–öãârf÷"¶W’ÂfÇVR–â6÷'FVB†Föw2æ—FV×2‚’Â¶W“ÖÆÖ&F&÷s¢&÷u³Ò’¢66÷Uö÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶¶W—Ò"²'6VÆV7FVB"–b66÷RÓÒ¶W’VÇ6R"'Óç¶Æ&VÇÓÂö÷F–öãârf÷"¶W’ÂÆ&VÂ–â°¢‚""Â.888n8îXZÎ™h¾h©^z‹ò"’Â‚&fÖ–Ç’"Â.YÎ8xªÎˆˆî8ädÔ”Å’"’Â‚'&VÆF—fW2"Â.XXN[Éş8;¾Šj®h‰®xªÂ"’Â‚&Ö–æR"Â.ˆz®Xˆn8îh©^z‹ò"•Ò¢&6U÷&×2Ò²&¶VææVÅö–B#¢¶VææVÅö–BÂ&Föuö–B#¢Föuö–BÂ'66÷R#¢66÷WĞ¢&WeöÆ–æ²ÒbsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æS÷·W&ÆVæ6öFR‡²¢¦&6U÷&×2Â'vR#¢vRÒÒ—Ò#îik8~8NXiyÉş8ƒÂöâr–bvRâVÇ6R" ¢æW‡EöÆ–æ²ÒbsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æS÷·W&ÆVæ6öFR‡²¢¦&6U÷&×2Â'vR#¢vR²Ò—Ò#î˜îXë¾8îXiyÉş8ƒÂöâr–bvRÂF÷FÅ÷vW2VÇ6R" ¢vW"ÒbsÆF—b7G–ÆSÒ&F—7Æ“¦fÆWƒ¶§W7F–g’Ö6öçFVçC¦6VçFW#¶Æ–vâÖ—FV×3¦6VçFW#¶v£'ƒ¶Ö&v–ã£#'‚#ç·&WeöÆ–æ·ÓÇ7ãç·vWÒò·F÷FÅ÷vW7Ş89®8;Î8+ƒÂ÷7ãç¶æW‡EöÆ–æ·ÓÂöF—câr–bF÷FÂVÇ6R" ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒädÔ”Å8+ş8*N8:8:8*N8;3Âöƒà¢ÇîYÎ8xªÎˆˆî8ädÔ”Å8(NXXN[Éş8;¾Šj®h‰®xªÎ8ÎXZÎ™h¾8~8şh‰™[~XiyÉş8).8ik8~8Nšn8¾ŠzK®8~8n8N8î88#Â÷à¢ÇãÆ6Æ73Ò&'WGFöâ7V66W72"‡&VcÒ"öfÖ–Ç’öw&÷wF‚öFB#îûÈ²h‰™[~Š‰˜Ë.8).‹ûŞXªÂöãÂ÷à¢Æf÷&ÒÖWF†öCÒ&vWB"7F–öãÒ"öfÖ–Ç’÷F–ÖVÆ–æR"6Æ73Ò'FVæçB#ãÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃîxªÎˆˆãÂöÆ&VÃãÇ6VÆV7BæÖSÒ&¶VææVÅö–B#ç¶¶VææVÅö÷F–öç7ÓÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîhI¾xªÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ&Föuö–B#ç¶Föuö÷F–öç7ÓÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃîXZÎ™h¾XË®XˆcÂöÆ&VÃãÇ6VÆV7BæÖSÒ'66÷R#ç·66÷Uö÷F–öç7ÓÂ÷6VÆV7CãÂöF—cãÂöF—cãÆ'WGFöãî8>8îiÚK»n8~ŠzK£Âö'WGFöãâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR#îiÚK»n8).Šz>™šCÂöãÂöf÷&Óà¢ÇãÇ7G&öæsç·F÷FÇŞK»cÂ÷7G&öæsî8îXiyÉş8ÎŠh¾8N8¾8(®8î8~8ş8#Â÷ãÆF—b6Æ73Ò'F–ÖVÆ–æRÖw&–B#ç·÷7G7ÓÂöF—cç·vW'Ğ¢ÇãÇ6ÖÆÃî8Îˆz®Xˆn888Ş8¾ŠŠŞZé®8~8şXiyÉş8ş8+ş8*N8:8:8*N8;>8¾8şŠzK®8^8(Î8î8¾8)>8#Â÷6ÖÆÃãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚$dÔ”Å8+ş8*N8:8:8*N8;2"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷F–ÖVÆ–æUöFWF–Â†—FVÕö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’ævWB†—FVÕö–B¢–bæ÷B&V6÷&C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÂFörÂFVæçBÂ&öf–ÆRÒ&V6÷&@¢–b—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–C ¢Vç&VEöÆ–¶W2Ò6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æTÆ–¶R’æ÷WFW&¦ö–â„fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBÂæEò€¢fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBæÆ–¶Uö–BÓÒfÖ–Ç•F–ÖVÆ–æTÆ–¶Ræ–BÀ¢fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBçW6W%ö–BÓÒW6W"æ–BÀ¢’’çv†W&R„fÖ–Ç•F–ÖVÆ–æTÆ–¶RæÆ'VÕö—FVÕö–BÓÒ—FVÒæ–BÂfÖ–Ç•F–ÖVÆ–æTÆ–¶RçW6W%ö–BÒW6W"æ–BÀ¢fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VBæ–Bæ—5ò„æöæR’¢’æÆÂ‚¢f÷"Vç&VEöÆ–¶R–âVç&VEöÆ–¶W3 ¢6W76–öâæFB„fÖ–Ç•F–ÖVÆ–æTÆ–¶U&VB†Æ–¶Uö–C×Vç&VEöÆ–¶Ræ–BÂW6W%ö–C×W6W"æ–B’¢Vç&VEö6öÖÖVçG2Ò6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçB’æ÷WFW&¦ö–â„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBÂæEò€¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBæ6öÖÖVçEö–BÓÒfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ–BÀ¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBçW6W%ö–BÓÒW6W"æ–BÀ¢’’çv†W&R„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–BÓÒ—FVÒæ–BÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBçW6W%ö–BÒW6W"æ–BÀ¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæFVÆWFVEöBæ—5ò„æöæR’ÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ†–FFVåöBæ—5ò„æöæR’À¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VBæ–Bæ—5ò„æöæR’¢’æÆÂ‚¢f÷"Vç&VEö6öÖÖVçB–âVç&VEö6öÖÖVçG3 ¢6W76–öâæFB„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçE&VB†6öÖÖVçEö–C×Vç&VEö6öÖÖVçBæ–BÂW6W%ö–C×W6W"æ–B’¢–bVç&VEöÆ–¶W2÷"Vç&VEö6öÖÖVçG3 ¢6W76–öâæ6öÖÖ—B‚¢÷væW%öæÖRÒ&öf–ÆRææ–6¶æÖR–b&öf–ÆRç6†÷uöæ–6¶æÖRæB&öf–ÆRææ–6¶æÖRVÇ6R$dÔ”Å8:8;>898;Â ¢F¶VâÒ—FVÒçF¶Våööâç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"’–b—FVÒçF¶VåööâVÇ6R—FVÒæ7&VFVEöBæFFR‚’ç7G&gF–ÖR‚"U[›BVŞiÈ‚VNizR"¢f—6–&–Æ—G’Ò.YÎ8xªÎˆˆî8ädÔ”Å8¾XZÎ™h²"–b—FVÒçf—6–&–Æ—G’ÓÒ&fÖ–Ç’"VÇ6R.XXN[Éş8;¾Šj®h‰®xªÎ8¾XZÎ™h² ¢Æ–¶W2Ò6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æTÆ–¶RÂ÷væW%&öf–ÆR’æ÷WFW&¦ö–â„÷væW%&öf–ÆRÂ÷væW%&öf–ÆRçW6W%ö–BÓÒfÖ–Ç•F–ÖVÆ–æTÆ–¶RçW6W%ö–B¢çv†W&R„fÖ–Ç•F–ÖVÆ–æTÆ–¶RæÆ'VÕö—FVÕö–BÓÒ—FVÒæ–B’æ÷&FW%ö'’„fÖ–Ç•F–ÖVÆ–æTÆ–¶Ræ7&VFVEöB¢’æÆÂ‚¢Æ–¶VBÒç’†Æ–¶RçW6W%ö–BÓÒW6W"æ–Bf÷"Æ–¶RÂò–âÆ–¶W2¢Æ–¶UöæÖW2ÒµĞ¢f÷"Æ–¶RÂÆ–¶U÷&öf–ÆR–âÆ–¶W5³£Ó ¢–bÆ–¶RçW6W%ö–BÓÒW6W"æ–C ¢Æ–¶UöæÖW2æVæB‚.8.8®8ò"¢VÆ–bÆ–¶U÷&öf–ÆRæBÆ–¶U÷&öf–ÆRç&öf–ÆU÷V&Æ–2æBÆ–¶U÷&öf–ÆRç6†÷uöæ–6¶æÖRæBÆ–¶U÷&öf–ÆRææ–6¶æÖS ¢Æ–¶UöæÖW2æVæB†Æ–¶U÷&öf–ÆRææ–6¶æÖR¢VÇ6S ¢Æ–¶UöæÖW2æVæB‚$dÔ”Å8:8;>898;Â"¢Ö÷&RÒb"8¾8·¶ÆVâ†Æ–¶W2’ÒŞK«¢"–bÆVâ†Æ–¶W2’âVÇ6R" ¢Æ–¶VEö'’ÒbsÇãÇ6ÖÆÃç¶‡FÖÂæW66R‚.8"æ¦ö–â†Æ–¶UöæÖW2’—×¶Ö÷&WÓÂ÷6ÖÆÃãÂ÷âr–bÆ–¶UöæÖW2VÇ6RsÇãÇ6ÖÆÃîiÈX‰Ş8î8N8N8Ş8).˜8(®8î8~8(~8cÂ÷6ÖÆÃãÂ÷âp¢6öÖÖVçE÷&÷w2Ò6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBÂ÷væW%&öf–ÆR’æ÷WFW&¦ö–â„÷væW%&öf–ÆRÂ÷væW%&öf–ÆRçW6W%ö–BÓÒfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBçW6W%ö–B¢çv†W&R„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–BÓÒ—FVÒæ–BÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæFVÆWFVEöBæ—5ò„æöæR’À¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ†–FFVåöBæ—5ò„æöæR’’æ÷&FW%ö'’„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ7&VFVEöB¢’æÆÂ‚¢6öÖÖVçG2Ò" ¢&W÷'FVE÷F&vWG2Ò²‡&W÷'BçF&vWE÷G—RÂ&W÷'BçF&vWEö–B’f÷"&W÷'B–â6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'B’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'Bç&W÷'FW%ö–BÓÒW6W"æ–BÀ¢fÖ–Ç•F–ÖVÆ–æU&W÷'BæÆ'VÕö—FVÕö–BÓÒ—FVÒæ–B’’æÆÂ‚—Ğ¢f÷"6öÖÖVçBÂ6öÖÖVçE÷&öf–ÆR–â6öÖÖVçE÷&÷w3 ¢6öÖÖVçEöæÖRÒ.8.8®8ò"–b6öÖÖVçBçW6W%ö–BÓÒW6W"æ–BVÇ6R†6öÖÖVçE÷&öf–ÆRææ–6¶æÖR–b6öÖÖVçE÷&öf–ÆRæB6öÖÖVçE÷&öf–ÆRç&öf–ÆU÷V&Æ–2æB6öÖÖVçE÷&öf–ÆRç6†÷uöæ–6¶æÖRæB6öÖÖVçE÷&öf–ÆRææ–6¶æÖRVÇ6R$dÔ”Å8:8;>898;Â"¢FVÆWFUöf÷&ÒÒbrrsÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒö6öÖÖVçG2÷¶6öÖÖVçBæ–GÒöFVÆWFR#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’"7G–ÆSÒ'FF–æs£W‚—‚#îX˜®™šCÂö'WGFöããÂöf÷&Óârrr–b6öÖÖVçBçW6W%ö–BÓÒW6W"æ–BVÇ6R" ¢&W÷'EöÆ–æ²Ò†bsÆ‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ÷&W÷'C÷F&vWE÷G—SÖ6öÖÖVçBf×·F&vWEö–C×¶6öÖÖVçBæ–GÒ#ãÇ6ÖÆÃîxªÎˆˆî8˜	®ZÂ÷6ÖÆÃãÂöâr–b‚&6öÖÖVçB"Â6öÖÖVçBæ–B’æ÷B–â&W÷'FVE÷F&vWG2VÇ6RsÇ6ÖÆÃî˜	®ZXù~K¹kˆ8óÂ÷6ÖÆÃâr’–b6öÖÖVçBçW6W%ö–BÒW6W"æ–BVÇ6R" ¢6öÖÖVçG2³ÒbrrsÆF—b6Æ73Ò'FVæçB"7G–ÆSÒ&Ö&v–ã£‚·FF–æs£'‚#ãÇ7G–ÆSÒ&Ö&v–ã£W‚#ãÇ7G&öæsç¶‡FÖÂæW66R†6öÖÖVçEöæÖR—ÓÂ÷7G&öæsâÇ6ÖÆÃç¶6öÖÖVçBæ7&VFVEöBç7G&gF–ÖR‚rU[›BVŞiÈ‚VNizRTƒ¢TÒr—ÓÂ÷6ÖÆÃãÂ÷ãÇ7G–ÆSÒ'v†—FR×76S§&R×w&¶Ö&v–ã£#ç¶‡FÖÂæW66R†6öÖÖVçBæ&öG’—ÓÂ÷ç¶FVÆWFUöf÷&×Ò·&W÷'EöÆ–æ·ÓÂöF—cârrp¢6öÖÖVçG2Ò6öÖÖVçG2÷"sÇãÇ6ÖÆÃîiÈX‰Ş8î8+>8:8;>888).˜8(®8î8~8(~8n8#Â÷6ÖÆÃãÂ÷âp¢6F–öâÒbsÇ7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†—FVÒæ6F–öâ—ÓÂ÷âr–b—FVÒæ6F–öâVÇ6R" ¢÷7E÷†÷F÷2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒç÷7Eöw&÷WÓÒ—FVÒç÷7Eöw&÷W’æ÷&FW%ö'’„fÖ–Ç”FötÆ'VÔ—FVÒç†÷Fõö÷&FW"’’æÆÂ‚’–b—FVÒç÷7Eöw&÷WVÇ6R¶—FVÕĞ¢†÷FõövÆÆW'’Òrræ¦ö–â†bsÆF—b6Æ73Ò&fÖ–Ç’×†÷Fò×7FvR#ãÆ–Ör6Æ73Ò&fÖ–Ç’ÖFör×†÷Fò"7&3Ò"öfÖ–Ç’÷F–ÖVÆ–æR÷·†÷Fõö—FVÒæ–GÒ÷†÷Fò"ÇCÒ'¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8îh‰™[~XiyÉò¶–æFW‚²Ò#ãÂöF—cârf÷"–æFW‚Â†÷Fõö—FVÒ–âVçVÖW&FR‡÷7E÷†÷F÷2’¢†÷Fõ÷&W÷'BÒ" ¢–b—FVÒçWÆöFVEö'•ö–BÒW6W"æ–C ¢†÷Fõ÷&W÷'BÒsÇ6ÖÆÃîxªÎˆˆî8˜	®Zkˆ8óÂ÷6ÖÆÃâr–b‚'†÷Fò"Â—FVÒæ–B’–â&W÷'FVE÷F&vWG2VÇ6RbsÆ‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ÷&W÷'C÷F&vWE÷G—S×†÷Fòf×·F&vWEö–C×¶—FVÒæ–GÒ#ãÇ6ÖÆÃî8>8îh©^z‹ş8).xªÎˆˆî8˜	®ZÂ÷6ÖÆÃãÂöâp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR#î8+ş8*N8:8:8*N8;>8h‹¾8(³ÂöãÆ'F–6ÆR7G–ÆSÒ&Ö‚×v–GFƒ£ƒ#ƒ¶Ö&v–ã£#‚WFò#à¢ÆF—b7G–ÆSÒ&F—7Æ“¦fÆWƒ¶§W7F–g’Ö6öçFVçC§76RÖ&WGvVVã¶v£'ƒ¶Æ–vâÖ—FV×3§7F'B#ãÆF—cãÇ7G&öæsç¶‡FÖÂæW66R†÷væW%öæÖR—ÓÂ÷7G&öæsà¢Ç7G–ÆSÒ&Ö&v–ã£7‚#ãÆ‡&VcÒ"öfÖ–Ç’öÖVÖ&W'2÷·&öf–ÆRçV&Æ–5ö–GÒ#ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöî8Ç6ÖÆÃç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷6ÖÆÃãÂ÷ãÂöF—cà¢Ç7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R‡f—6–&–Æ—G’—ÓÂ÷7ããÂöF—cà¢·†÷FõövÆÆW'—Ğ¢¶6F–öçÓÇãÇ6ÖÆÃîi*î[Ûiz^ûÉ§·F¶VçÓÂ÷6ÖÆÃî8·†÷Fõ÷&W÷'GÓÂ÷à¢Æf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒöÆ–¶S÷&WGW&å÷FóÖFWF–Â#ãÆ'WGFöâ6Æ73Ò'²w6V6öæF'’r–bÆ–¶VBVÇ6RrwÒ"&–×&W76VCÒ'²wG'VRr–bÆ–¶VBVÇ6RvfÇ6RwÒ#ç²~)šR8N8N8Şkˆ8òr–bÆ–¶VBVÇ6R~)š8N8N8ÒwŞ8¶ÆVâ†Æ–¶W2—ÓÂö'WGFöããÂöf÷&Óç¶Æ–¶VEö'—Ğ¢Ç6V7F–öâ7G–ÆSÒ&Ö&v–â×F÷£#W‚#ãÆƒ#î8+>8:8;>88ƒÂöƒ#ç¶6öÖÖVçG7ÓÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒö6öÖÖVçG2#ãÆÆ&VÃî8+>8:8;>88ûÈƒ3ih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&&öG’"Ö†ÆVæwFƒÒ#3"&WV—&VCãÂ÷FW‡F&VãÆ'WGFöãî8+>8:8;>888).˜8(³Âö'WGFöããÂöf÷&ÓãÇãÇ6ÖÆÃî8+>8:8;>888şYÎ8XiyÉş8).™k.Šj~8~8Ş8(´dÔ”Å8¾ŠzK®8^8(Î8î88.KˆŞ˜Xˆ~8®Xh^Zë8şxªÎˆˆîzêynˆ^8Î™ÙîŠzK®8¾8~8Ş8î88#Â÷6ÖÆÃãÂ÷ãÂ÷6V7F–öããÂö'F–6ÆSârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'¶Föræ6ÆÅöæÖWŞûÙÄdÔ”Å8+ş8*N8:8:8*N8;2"Â&öG’ÂW6W"Â6W76–öâ  ¥D”ÔTÄ”äUõ$Uõ%Eõ$T4ôå2Ò°¢&†&76ÖVçB#¢.Z¸Î8Î8(8¾8;¾iK¾i(>y¨N8®Xh^Zë’"À¢'&—f7’#¢.X¾K«®h8^Z8;¾89~8:8*N898+~8;Â"À¢&–æ&÷&–FR#¢.KˆŞ˜Xˆ~8®XiyÉş8;¾Šxûâ"À¢'7Ò#¢.Zê>KÉŞ8;¾‹û~h9ŠÎx+¢"À¢&÷F†W"#¢.8Ş8îK¹b"À§Ğ  ¦FVbfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'E÷F&vWB†—FVÕö–C¢–çBÂF&vWE÷G—S¢7G"ÂF&vWEö–C¢–çBÂW6W#¢W6W"Â6W76–öã¢6W76–öâ“ ¢&V6÷&BÒfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’ævWB†—FVÕö–B¢–bæ÷B&V6÷&B÷"F&vWE÷G—Ræ÷B–â²'†÷Fò"Â&6öÖÖVçB'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÂFörÂFVæçBÂòÒ&V6÷&@¢–bF&vWE÷G—RÓÒ'†÷Fò# ¢–bF&vWEö–BÒ—FVÒæ–B÷"—FVÒçWÆöFVEö'•ö–BÓÒW6W"æ–C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢VÇ6S ¢6öÖÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçB’çv†W&R€¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ–BÓÒF&vWEö–BÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–BÓÒ—FVÒæ–BÀ¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæFVÆWFVEöBæ—5ò„æöæR’ÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ†–FFVåöBæ—5ò„æöæR’’¢–bæ÷B6öÖÖVçB÷"6öÖÖVçBçW6W%ö–BÓÒW6W"æ–C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â—FVÒÂFörÂFVæç@  ¤ævWB‚"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ÷&W÷'B"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'E÷vR†—FVÕö–C¢–çBÂF&vWE÷G—S¢7G"ÂF&vWEö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFörÂòÒfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'E÷F&vWB†—FVÕö–BÂF&vWE÷G—RÂF&vWEö–BÂW6W"Â6W76–öâ¢W†—7F–ærÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'B’çv†W&R€¢fÖ–Ç•F–ÖVÆ–æU&W÷'Bç&W÷'FW%ö–BÓÒW6W"æ–BÂfÖ–Ç•F–ÖVÆ–æU&W÷'BçF&vWE÷G—RÓÒF&vWE÷G—RÀ¢fÖ–Ç•F–ÖVÆ–æU&W÷'BçF&vWEö–BÓÒF&vWEö–B’¢–bW†—7F–æs ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ#îh©^z‹ş8h‹¾8(³ÂöãÆƒî˜	®ZXù~K¹kˆ8óÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇî8>8îXh^Zë8şxªÎˆˆî8˜
>{Zkˆ8ş8~88.z+®Š¨Ş8Zûî[ùÎ8).8®[è^88ş88^8N8#Â÷ãÂöF—cârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.˜	®ZXù~K¹kˆ8şûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ¢÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶¶W—Ò#ç¶Æ&VÇÓÂö÷F–öãârf÷"¶W’ÂÆ&VÂ–âD”ÔTÄ”äUõ$Uõ%Eõ$T4ôå2æ—FV×2‚’¢F&vWEöÆ&VÂÒ.h©^z‹şXiyÉò"–bF&vWE÷G—RÓÒ'†÷Fò"VÇ6R.8+>8:8;>88‚ ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ#îh©^z‹ş8h‹¾8(³ÂöãÆƒîxªÎˆˆî8˜	®ZÂöƒà¢ÆF—b6Æ73Ò'FVæçB#ãÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ş8ç·F&vWEöÆ&VÇÓÂ÷7G&öæsî8¾8N8N8nxªÎˆˆî8˜
>{Z8~8î88#Â÷ãÇî{x®h
^h
~8Î8.8(¾ZNY8ş88>8îj™şˆ;Ş888~8®8şxªÎˆˆî8y»Nhê^8N˜
>{Z8ş88^8N8#Â÷ãÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ÷&W÷'B#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F&vWE÷G—R"fÇVSÒ'·F&vWE÷G—WÒ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F&vWEö–B"fÇVSÒ'·F&vWEö–GÒ#ãÆÆ&VÃîynyKÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&V6öâ"&WV—&VCç¶÷F–öç7ÓÂ÷6VÆV7CãÆÆ&VÃîŠ›>8~8Nx«nk8ûÈK»¾hHş8;³Sih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FWF–Ç2"Ö†ÆVæwFƒÒ#S#ãÂ÷FW‡F&VãÆ'WGFöãîxªÎˆˆî8˜	®Z88(³Âö'WGFöããÂöf÷&Óârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.xªÎˆˆî8˜	®ZûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ÷&W÷'B"¦FVbfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'Eö7&VFR†—FVÕö–C¢–çBÂF&vWE÷G—S¢7G"Òf÷&Ò‚âââ’ÂF&vWEö–C¢–çBÒf÷&Ò‚âââ’Â&V6öã¢7G"Òf÷&Ò‚âââ’ÂFWF–Ç3¢7G"Òf÷&Ò‚""’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢—FVÒÂòÂFVæçBÒfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'E÷F&vWB†—FVÕö–BÂF&vWE÷G—RÂF&vWEö–BÂW6W"Â6W76–öâ¢–b&V6öâæ÷B–âD”ÔTÄ”äUõ$Uõ%Eõ$T4ôå3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.˜	®ZynyK8).˜h©î8~8n8ş88^8B"¢W†—7F–ærÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'B’çv†W&R€¢fÖ–Ç•F–ÖVÆ–æU&W÷'Bç&W÷'FW%ö–BÓÒW6W"æ–BÂfÖ–Ç•F–ÖVÆ–æU&W÷'BçF&vWE÷G—RÓÒF&vWE÷G—RÀ¢fÖ–Ç•F–ÖVÆ–æU&W÷'BçF&vWEö–BÓÒF&vWEö–B’¢–bæ÷BW†—7F–æs ¢6W76–öâæFB„fÖ–Ç•F–ÖVÆ–æU&W÷'B‡FVæçEö–C×FVæçBæ–BÂ&W÷'FW%ö–C×W6W"æ–BÂÆ'VÕö—FVÕö–CÖ—FVÒæ–BÀ¢F&vWE÷G—S×F&vWE÷G—RÂF&vWEö–C×F&vWEö–BÂ&V6öã×&V6öâÀ¢FWF–Ç3ÖFWF–Ç2ç7G&—‚•³£SÒ÷"æöæR’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒöÆ–¶R"¦FVbfÖ–Ç•÷F–ÖVÆ–æUöÆ–¶U÷FövvÆR†—FVÕö–C¢–çBÂ&WGW&å÷Fó¢7G"Ò""ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’ævWB†—FVÕö–B¢–bæ÷B&V6÷&C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÂFörÂFVæçBÂòÒ&V6÷&@¢–bfÖ–Ç•ö7F–öåöF—6&ÆVB‡W6W"æ–BÂFVæçBæ–BÂ&Æ–¶W2"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.xªÎˆˆî8¾8(8(®8N8N8Şj™şˆ;Ş8ÎXÎjÚ.8^8(Î8n8N8î8’"¢Æ–¶RÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æTÆ–¶R’çv†W&R€¢fÖ–Ç•F–ÖVÆ–æTÆ–¶RæÆ'VÕö—FVÕö–BÓÒ—FVÕö–BÂfÖ–Ç•F–ÖVÆ–æTÆ–¶RçW6W%ö–BÓÒW6W"æ–@¢’¢–bÆ–¶S ¢6W76–öâæFVÆWFR†Æ–¶R¢VÇ6S ¢Æ–¶RÒfÖ–Ç•F–ÖVÆ–æTÆ–¶R†Æ'VÕö—FVÕö–CÖ—FVÕö–BÂW6W%ö–C×W6W"æ–B¢6W76–öâæFB†Æ–¶R¢6W76–öâæfÇW6‚‚¢÷væW"Ò6W76–öâævWB…W6W"Â—FVÒçWÆöFVEö'•ö–B¢–b÷væW"æB÷væW"æ–BÒW6W"æ–BæBVÖ–Åöæ÷F–f–6F–öåöÆÆ÷vVB†÷væW"Â&Æ–¶W2"Â6W76–öâ“ ¢&6U÷W&ÂÒ÷2æVçf—&öâævWB‚$ô$4UõU$Â"Â&‡GG3¢òöFörÖÖævVÖVçBæ&VæVf—BÖæf’æ6öÒ"’ç'7G&—‚"ò"¢VWVUöVÖ–Â‡6W76–öâÂ÷væW"æVÖ–ÂÂ'F–ÖVÆ–æUöÆ–¶R"Âb.8	U5E$TÄÄdÔ”Å8	¶Föræ6ÆÅöæÖWŞ8îXiyÉş8¾8N8N8Ş8Î[®8Ş8î8~8ò"À¢b'¶÷væW"ææÖWÒjy…ÆåÆç¶fÖ–Ç•öÖW76vUöæÖR‡W6W"æ–BÂ6W76–öâ—Ş8^8)>8Ç¶Föræ6ÆÅöæÖWŞ8îXiyÉş8¾8N8N8Ş8~8î8~8ş8%Æç¶&6U÷W&ÇÒöfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ"À¢FVæçBæ–BÂ÷væW"æ–BÂb&Æ–¶S§¶Æ–¶Ræ–GÒ"¢–b÷væW"æB÷væW"æ–BÒW6W"æ–C ¢6VæE÷vV%÷W6‚†÷væW"æ–BÂ&Æ–¶W2"Âb'¶Föræ6ÆÅöæÖWŞ8îXiyÉş8¾8N8N8Ò"Âb'¶fÖ–Ç•öÖW76vUöæÖR‡W6W"æ–BÂ6W76–öâ—Ş8^8)>8¾8([®8Ş8î8~8ò"À¢b"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ"Âb'W6ƒ¦Æ–¶S§¶Æ–¶Ræ–GÒ"Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢FW7F–æF–öâÒb"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ"–b&WGW&å÷FòÓÒ&FWF–Â"VÇ6R"öfÖ–Ç’÷F–ÖVÆ–æR ¢&WGW&â&VF—&V7E&W7öç6R†FW7F–æF–öâÂ7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ÷†÷Fò"¦FVbfÖ–Ç•÷F–ÖVÆ–æU÷†÷Fò†—FVÕö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢f—6–&ÆRÒfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ¢&V6÷&BÒf—6–&ÆRævWB†—FVÕö–B¢—FVÒÒ6W76–öâævWB„fÖ–Ç”FötÆ'VÔ—FVÒÂ—FVÕö–B¢–bæ÷B&V6÷&BæB—FVÒæB—FVÒç÷7Eöw&÷W ¢&V6÷&BÒæW‡B‚‡fÇVRf÷"fÇVR–âf—6–&ÆRçfÇVW2‚’–bfÇVU³Òç÷7Eöw&÷WÓÒ—FVÒç÷7Eöw&÷W’ÂæöæR¢–bæ÷B&V6÷&B÷"æ÷B—FVÓ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒç†÷FõöFFÂÖVF–÷G—SÖ—FVÒç†÷Fõö6öçFVçE÷G—RÂ†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ç÷7B‚"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒö6öÖÖVçG2"¦FVbfÖ–Ç•÷F–ÖVÆ–æUö6öÖÖVçEö7&VFR†—FVÕö–C¢–çBÂ&öG“¢7G"Òf÷&Ò‚âââ’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’ævWB†—FVÕö–B¢–bæ÷B&V6÷&C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢FW‡BÒ&öG’ç7G&—‚¢–bæ÷BFW‡B÷"ÆVâ‡FW‡B’â3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8+>8:8;>888ó8	Ã3ih~ZÙ~8~XZ^X©¾8~8n8ş88^8B"¢—FVÒÂFörÂFVæçBÂòÒ&V6÷&@¢–bfÖ–Ç•ö7F–öåöF—6&ÆVB‡W6W"æ–BÂFVæçBæ–BÂ'÷7F–ær"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.xªÎˆˆî8¾8(8(®8+>8:8;>88h©^z‹ş8ÎXÎjÚ.8^8(Î8n8N8î8’"¢6öÖÖVçBÒfÖ–Ç•F–ÖVÆ–æT6öÖÖVçB†Æ'VÕö—FVÕö–CÖ—FVÒæ–BÂW6W%ö–C×W6W"æ–BÂ&öG“×FW‡B¢6W76–öâæFB†6öÖÖVçB¢6W76–öâæfÇW6‚‚¢÷væW"Ò6W76–öâævWB…W6W"Â—FVÒçWÆöFVEö'•ö–B¢–b÷væW"æB÷væW"æ–BÒW6W"æ–BæBVÖ–Åöæ÷F–f–6F–öåöÆÆ÷vVB†÷væW"Â&Æ–¶W2"Â6W76–öâ“ ¢&6U÷W&ÂÒ÷2æVçf—&öâævWB‚$ô$4UõU$Â"Â&‡GG3¢òöFörÖÖævVÖVçBæ&VæVf—BÖæf’æ6öÒ"’ç'7G&—‚"ò"¢VWVUöVÖ–Â‡6W76–öâÂ÷væW"æVÖ–ÂÂ'F–ÖVÆ–æUö6öÖÖVçB"Âb.8	U5E$TÄÄdÔ”Å8	¶Föræ6ÆÅöæÖWŞ8îXiyÉş8¾8+>8:8;>888Î[®8Ş8î8~8ò"À¢b'¶÷væW"ææÖWÒjy…ÆåÆç¶fÖ–Ç•öÖW76vUöæÖR‡W6W"æ–BÂ6W76–öâ—Ş8^8)>8Ç¶Föræ6ÆÅöæÖWŞ8îXiyÉş8¾8+>8:8;>888~8î8~8ş8%ÆåÆç·FW‡GÕÆåÆç¶&6U÷W&ÇÒöfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ"À¢FVæçBæ–BÂ÷væW"æ–BÂb&6öÖÖVçC§¶6öÖÖVçBæ–GÒ"¢–b÷væW"æB÷væW"æ–BÒW6W"æ–C ¢6VæE÷vV%÷W6‚†÷væW"æ–BÂ&Æ–¶W2"Âb'¶Föræ6ÆÅöæÖWŞ8îXiyÉş8¾8+>8:8;>88‚"ÂFW‡E³£#ÒÀ¢b"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ"Âb'W6ƒ¦6öÖÖVçC§¶6öÖÖVçBæ–GÒ"Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒö6öÖÖVçG2÷¶6öÖÖVçEö–GÒöFVÆWFR"¦FVbfÖ–Ç•÷F–ÖVÆ–æUö6öÖÖVçEöFVÆWFR†—FVÕö–C¢–çBÂ6öÖÖVçEö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–b—FVÕö–Bæ÷B–âfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6öÖÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçB’çv†W&R€¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ–BÓÒ6öÖÖVçEö–BÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–BÓÒ—FVÕö–BÀ¢fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBçW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæFVÆWFVEöBæ—5ò„æöæR’’¢–bæ÷B6öÖÖVçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6öÖÖVçBæFVÆWFVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’÷F–ÖVÆ–æR÷¶—FVÕö–GÒ"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷F–ÖVÆ–æRö6öÖÖVçG2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷F–ÖVÆ–æUö6öÖÖVçG5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢&÷w2Ò6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBÂfÖ–Ç”FötÆ'VÔ—FVÒÂFör’æ¦ö–â€¢fÖ–Ç”FötÆ'VÔ—FVÒÂfÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–B’æ¦ö–â€¢FörÂFöræ–BÓÒfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–B’çv†W&R„FörçFVæçEö–BÓÒFVæçBæ–B¢æ÷&FW%ö'’„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ3¢’æÆÂ‚¢6&G2Ò" ¢f÷"6öÖÖVçBÂ—FVÒÂFör–â&÷w3 ¢7FFRÒ.h©^z‹şˆ^8ÎX˜®™šB"–b6öÖÖVçBæFVÆWFVEöBVÇ6R‚.zêynˆ^8Î™ÙîŠzK¢"–b6öÖÖVçBæ†–FFVåöBVÇ6R.ŠzK®KŠÒ"¢7F–öâÒ'Væ†–FR"–b6öÖÖVçBæ†–FFVåöBVÇ6R&†–FR ¢'WGFöâÒ.XhŞŠzK¢"–b6öÖÖVçBæ†–FFVåöBVÇ6R.XŠyJˆ^yK¾™Ú.8¾8(™ÙîŠzK¢ ¢6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÇãÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂ÷7G&öæsâûÈò¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR†6öÖÖVçBçW6W%ö–BÂ6W76–öâ’—Ş8Ç7â6Æ73Ò&&FvR#ç·7FFWÓÂ÷7ããÂ÷ãÇ7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†6öÖÖVçBæ&öG’—ÓÂ÷ãÇ6ÖÆÃç¶6öÖÖVçBæ7&VFVEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—ÓÂ÷6ÖÆÃãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷F–ÖVÆ–æRö6öÖÖVçG2öÖævR÷¶6öÖÖVçBæ–GÒ#ãÆÆ&VÃîzêyn8:8:#ÂöÆ&VÃãÆ–çWBæÖSÒ&FÖ–åöæ÷FR"Ö†ÆVæwFƒÒ#S"fÇVSÒ'¶‡FÖÂæW66R†6öÖÖVçBæFÖ–åöæ÷FR÷"rr—Ò#ãÆ'WGFöâæÖSÒ&7F–öâ"fÇVSÒ'¶7F–öçÒ#ç¶'WGFöçÓÂö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrp¢&öG’ÒbrrsÆƒî8+ş8*N8:8:8*N8;>8+>8:8;>88zêycÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇî888:89n8:¾Zûî[ùÎ8î8ş8(Xéşih~8i8ŞKÙÎX˜Ş8î[^jÛN8).KùŞhÈ8~8î88.zêynˆ^8şXéşih~8).i»8Şhù¾88®8XZÎ™h¾x«nhX¾8zêyn8:8:.8î8şZHi»N8~8Ş8î88#Â÷ãÂöF—cç¶6&G2÷"sÇî8+>8:8;>888ş8î88.8(®8î8¾8)>8#Â÷âwÒrrp¢&WGW&âÆ–÷WB‚.8+ş8*N8:8:8*N8;>8+>8:8;>88zêyb"Â&öG’ÂW6W"  ¤ç÷7B‚"öfÖ–Ç’÷F–ÖVÆ–æRö6öÖÖVçG2öÖævR÷¶6öÖÖVçEö–GÒ"¦FVbfÖ–Ç•÷F–ÖVÆ–æUö6öÖÖVçEöÖöFW&FR†6öÖÖVçEö–C¢–çBÂ7F–öã¢7G"Òf÷&Ò‚âââ’ÂFÖ–åöæ÷FS¢7G"Òf÷&Ò‚""’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢6öÖÖVçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçB’æ¦ö–â€¢fÖ–Ç”FötÆ'VÔ—FVÒÂfÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒfÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæÆ'VÕö—FVÕö–B’æ¦ö–â€¢FörÂFöræ–BÓÒfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–B’çv†W&R„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBæ–BÓÒ6öÖÖVçEö–BÂFörçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B6öÖÖVçB÷"7F–öâæ÷B–â²&†–FR"Â'Væ†–FR'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6öÖÖVçBæ†–FFVåöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’–b7F–öâÓÒ&†–FR"VÇ6RæöæP¢6öÖÖVçBæ†–FFVåö'•ö–BÒW6W"æ–B–b7F–öâÓÒ&†–FR"VÇ6RæöæP¢6öÖÖVçBæFÖ–åöæ÷FRÒFÖ–åöæ÷FRç7G&—‚•³£SÒ÷"æöæP¢6W76–öâæFB„fÖ–Ç”ÖöFW&F–öäVF—B‡FVæçEö–C×FVæçBæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂF&vWE÷G—SÒ&6öÖÖVçB"ÂF&vWEö–CÖ6öÖÖVçBæ–BÂ7F–öãÖ7F–öâÂFWF–Ç3Ö6öÖÖVçBæFÖ–åöæ÷FR’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷F–ÖVÆ–æRö6öÖÖVçG2öÖævR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷F–ÖVÆ–æR÷&W÷'G2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'G5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢&W÷'G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'BÂFör’æ¦ö–â„fÖ–Ç”FötÆ'VÔ—FVÒÂfÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒfÖ–Ç•F–ÖVÆ–æU&W÷'BæÆ'VÕö—FVÕö–B¢æ¦ö–â„FörÂFöræ–BÓÒfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–B’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'BçFVæçEö–BÓÒFVæçBæ–B¢æ÷&FW%ö'’„fÖ–Ç•F–ÖVÆ–æU&W÷'Bç7FGW2ÂfÖ–Ç•F–ÖVÆ–æU&W÷'Bæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ3¢’æÆÂ‚¢6&G2Ò" ¢f÷"&W÷'BÂFör–â&W÷'G3 ¢&V6öâÒD”ÔTÄ”äUõ$Uõ%Eõ$T4ôå2ævWB‡&W÷'Bç&V6öâÂ&W÷'Bç&V6öâ¢F&vWBÒ.h©^z‹şXiyÉò"–b&W÷'BçF&vWE÷G—RÓÒ'†÷Fò"VÇ6R.8+>8:8;>88‚ ¢7FGW5öÆ&VÂÒ²&÷Vâ#¢.iÊ®Zûî[ùÂ"Â'&Wf–Wv–ær#¢.z+®Š¨ŞKŠÒ"Â'&W6öÇfVB#¢.Zûî[ùÎkˆ8ò"Â&F—6Ö—76VB#¢.Zûî[ùÎKˆŞŠh'ÒævWB‡&W÷'Bç7FGW2Â&W÷'Bç7FGW2¢–b&W÷'BçF&vWE÷G—RÓÒ'†÷Fò# ¢F&vWE÷&Wf–WrÒbsÆF—b6Æ73Ò&fÖ–Ç’×†÷Fò×7FvR#ãÆ–Ör6Æ73Ò&fÖ–Ç’ÖFör×†÷Fò"7&3Ò"öfÖ–Ç’÷F–ÖVÆ–æR÷&W÷'G2öÖævR÷·&W÷'Bæ–GÒ÷†÷Fò"ÇCÒ.˜	®ZZûî‹XiyÉò#ãÂöF—câp¢VÇ6S ¢&W÷'FVEö6öÖÖVçBÒ6W76–öâævWB„fÖ–Ç•F–ÖVÆ–æT6öÖÖVçBÂ&W÷'BçF&vWEö–B¢F&vWE÷&Wf–WrÒbsÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsî˜	®ZZûî‹8+>8:8;>88XéşihsÂ÷7G&öæsãÇ7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R‡&W÷'FVEö6öÖÖVçBæ&öG’–b&W÷'FVEö6öÖÖVçBVÇ6R.Zûî‹8+>8:8;>888şz+®Š¨Ş8~8Ş8î8¾8)2"—ÓÂ÷ãÂöF—câp¢6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÇãÇ7â6Æ73Ò&&FvR#ç·7FGW5öÆ&VÇÓÂ÷7ãâÇ7G&öæsç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ŞûÈ÷·F&vWGÓÂ÷7G&öæsãÂ÷ç·F&vWE÷&Wf–WwÓÇãÇ7G&öæsîynyKûÉ£Â÷7G&öæsç¶‡FÖÂæW66R‡&V6öâ—ÓÂ÷ãÇ7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R‡&W÷'BæFWF–Ç2÷".Š›>{K8®8r"—ÓÂ÷ãÇãÇ6ÖÆÃî˜	®Zˆ^ûÉ§¶‡FÖÂæW66R†fÖ–Ç•öÖW76vUöæÖR‡&W÷'Bç&W÷'FW%ö–BÂ6W76–öâ’—ÒûÈò·&W÷'Bæ7&VFVEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—ÓÂ÷6ÖÆÃãÂ÷ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷F–ÖVÆ–æR÷&W÷'G2öÖævR÷·&W÷'Bæ–GÒ#ãÆÆ&VÃîZûî[ùÎx«nk8ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'7FGW2#ãÆ÷F–öâfÇVSÒ&÷Vâ"²w6VÆV7FVBr–b&W÷'Bç7FGW2ÓÒv÷VârVÇ6RrwÓîiÊ®Zûî[ùÃÂö÷F–öããÆ÷F–öâfÇVSÒ'&Wf–Wv–ær"²w6VÆV7FVBr–b&W÷'Bç7FGW2ÓÒw&Wf–Wv–ærrVÇ6RrwÓîz+®Š¨ŞKŠÓÂö÷F–öããÆ÷F–öâfÇVSÒ'&W6öÇfVB"²w6VÆV7FVBr–b&W÷'Bç7FGW2ÓÒw&W6öÇfVBrVÇ6RrwÓîZûî[ùÎkˆ8óÂö÷F–öããÆ÷F–öâfÇVSÒ&F—6Ö—76VB"²w6VÆV7FVBr–b&W÷'Bç7FGW2ÓÒvF—6Ö—76VBrVÇ6RrwÓîZûî[ùÎKˆŞŠhÂö÷F–öããÂ÷6VÆV7CãÆÆ&VÃîzêyn8:8:.ûÈXŠyJˆ^8¾8şŠzK®8^8(Î8î8¾8)>ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FÖ–åöæ÷FR"Ö†ÆVæwFƒÒ#S#ç¶‡FÖÂæW66R‡&W÷'BæFÖ–åöæ÷FR÷"rr—ÓÂ÷FW‡F&VãÆ'WGFöãîZûî[ùÎXh^Zë8).KùŞZÙƒÂö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrp¢&öG’ÒbrrsÆƒî8+ş8*N8:8:8*N8;>˜	®ZzêycÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇî8*®8;Î88®8;Îjy8¾8([®8N8şXiyÉş8;¾8+>8:8;>8888î˜	®Z8~88.Zûî‹Xh^Zë8).z+®Š¨Ş8~8[ø^Šh8¾[ùÎ88n8+>8:8;>88zêyn8¾8(™ÙîŠzK®8¾8~8n8ş88^8N8#Â÷ãÂöF—cç¶6&G2÷"sÇî˜	®Z8ş8.8(®8î8¾8)>8#Â÷âwÒrrp¢&WGW&âÆ–÷WB‚.8+ş8*N8:8:8*N8;>˜	®Zzêyb"Â&öG’ÂW6W"  ¤ævWB‚"öfÖ–Ç’÷F–ÖVÆ–æR÷&W÷'G2öÖævR÷·&W÷'Eö–GÒ÷†÷Fò"¦FVbfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'E÷†÷Fò‡&W÷'Eö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢&W÷'BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'B’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'Bæ–BÓÒ&W÷'Eö–BÀ¢fÖ–Ç•F–ÖVÆ–æU&W÷'BçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B&W÷'C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÒ6W76–öâævWB„fÖ–Ç”FötÆ'VÔ—FVÒÂ&W÷'BæÆ'VÕö—FVÕö–B¢–bæ÷B—FVÓ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒç†÷FõöFFÂÖVF–÷G—SÖ—FVÒç†÷Fõö6öçFVçE÷G—RÂ†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ç÷7B‚"öfÖ–Ç’÷F–ÖVÆ–æR÷&W÷'G2öÖævR÷·&W÷'Eö–GÒ"¦FVbfÖ–Ç•÷F–ÖVÆ–æU÷&W÷'E÷WFFR‡&W÷'Eö–C¢–çBÂ7FGW3¢7G"Òf÷&Ò‚âââ’ÂFÖ–åöæ÷FS¢7G"Òf÷&Ò‚""’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢&W÷'BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'B’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'Bæ–BÓÒ&W÷'Eö–BÀ¢fÖ–Ç•F–ÖVÆ–æU&W÷'BçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B&W÷'B÷"7FGW2æ÷B–â²&÷Vâ"Â'&Wf–Wv–ær"Â'&W6öÇfVB"Â&F—6Ö—76VB'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&W÷'Bç7FGW2Ò7FGW0¢&W÷'BæFÖ–åöæ÷FRÒFÖ–åöæ÷FRç7G&—‚•³£SÒ÷"æöæP¢&W÷'Bæ†æFÆVEö'•ö–BÒW6W"æ–@¢&W÷'Bæ†æFÆVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæFB„fÖ–Ç”ÖöFW&F–öäVF—B‡FVæçEö–C×FVæçBæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂF&vWE÷G—SÒ'&W÷'B"À¢F&vWEö–C×&W÷'Bæ–BÂ7F–öãÖb'7FGW3§·7FGW7Ò"ÂFWF–Ç3×&W÷'BæFÖ–åöæ÷FR’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷F–ÖVÆ–æR÷&W÷'G2öÖævR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷6fWG’÷&W÷'B"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷6fWG•÷&W÷'E÷vR‡F&vWE÷G—S¢7G"ÂF&vWEö–C¢–çBÂFVæçEö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bFVæçEö–Bæ÷B–âfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ’÷"F&vWE÷G—Ræ÷B–â²'&öf–ÆR"Â&ÖW76vR'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢–bF&vWE÷G—RÓÒ'&öf–ÆR# ¢F&vWBÒ6W76–öâævWB…W6W"ÂF&vWEö–B¢–bæ÷BF&vWB÷"F&vWBæ–BÓÒW6W"æ–B÷"FVæçEö–Bæ÷B–âfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡F&vWBÂ6W76–öâ“¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢Æ&VÂÒb'¶fÖ–Ç•öÖW76vUöæÖR‡F&vWBæ–BÂ6W76–öâ—Ş8^8)>8î89~8:Ş89^8*>8;Î8:² ¢VÇ6S ¢ÖW76vRÒ6W76–öâævWB„fÖ–Ç”ÖW76vRÂF&vWEö–B“²6öçfW'6F–öâÒ6W76–öâævWB„fÖ–Ç”6öçfW'6F–öâÂÖW76vRæ6öçfW'6F–öåö–B’–bÖW76vRVÇ6RæöæP¢–bæ÷BÖW76vR÷"æ÷B6öçfW'6F–öâ÷"6öçfW'6F–öâçFVæçEö–BÒFVæçEö–B÷"W6W"æ–Bæ÷B–â¶6öçfW'6F–öâçW6W#ö–BÂ6öçfW'6F–öâçW6W#%ö–GÒ÷"ÖW76vRç6VæFW%ö–BÓÒW6W"æ–C¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢Æ&VÂÒ.Xù~Kú8:88>8+¾8;Î8+‚ ¢÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶¶W—Ò#ç·fÇVWÓÂö÷F–öãârf÷"¶W’ÂfÇVR–âD”ÔTÄ”äUõ$Uõ%Eõ$T4ôå2æ—FV×2‚’¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒîxªÎˆˆî8˜	®ZÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇç¶‡FÖÂæW66R†Æ&VÂ—Ş8¾8N8N8nxªÎˆˆî8˜
>{Z8~8î88#Â÷ãÂöF—cãÆf÷&ÒÖWF†öCÒ'÷7B#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F&vWE÷G—R"fÇVSÒ'·F&vWE÷G—WÒ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'F&vWEö–B"fÇVSÒ'·F&vWEö–GÒ#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'FVæçEö–B"fÇVSÒ'·FVæçEö–GÒ#ãÆÆ&VÃîynyKÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&V6öâ#ç¶÷F–öç7ÓÂ÷6VÆV7CãÆÆ&VÃîŠ›>8~8Nx«nk8ûÈƒSih~ZÙ~8î8~ûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FWF–Ç2"Ö†ÆVæwFƒÒ#S#ãÂ÷FW‡F&VãÆ'WGFöãîxªÎˆˆî8˜	®Z88(³Âö'WGFöããÂöf÷&Óârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.xªÎˆˆî8˜	®Z"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’÷6fWG’÷&W÷'B"¦FVbfÖ–Ç•÷6fWG•÷&W÷'Eö7&VFR‡F&vWE÷G—S¢7G"Òf÷&Ò‚âââ’ÂF&vWEö–C¢–çBÒf÷&Ò‚âââ’ÂFVæçEö–C¢–çBÒf÷&Ò‚âââ’Â&V6öã¢7G"Òf÷&Ò‚âââ’ÂFWF–Ç3¢7G"Òf÷&Ò‚""’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢fÖ–Ç•÷6fWG•÷&W÷'E÷vR‡F&vWE÷G—RÂF&vWEö–BÂFVæçEö–BÂW6W"Â6W76–öâ¢–b&V6öâæ÷B–âD”ÔTÄ”äUõ$Uõ%Eõ$T4ôå3¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC¢W†—7F–ærÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'Bæ–B’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'Bç&W÷'FW%ö–BÓÒW6W"æ–BÀ¢fÖ–Ç•F–ÖVÆ–æU&W÷'BçF&vWE÷G—RÓÒF&vWE÷G—RÂfÖ–Ç•F–ÖVÆ–æU&W÷'BçF&vWEö–BÓÒF&vWEö–B’¢–bæ÷BW†—7F–æs ¢6W76–öâæFB„fÖ–Ç•F–ÖVÆ–æU&W÷'B‡FVæçEö–C×FVæçEö–BÂ&W÷'FW%ö–C×W6W"æ–BÂÆ'VÕö—FVÕö–CÔæöæRÂF&vWE÷G—S×F&vWE÷G—RÀ¢F&vWEö–C×F&vWEö–BÂ&V6öã×&V6öâÂFWF–Ç3ÖFWF–Ç2ç7G&—‚•³£SÒ÷"æöæR’“²6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷6fWG’÷&W÷'G2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷6fWG•÷&W÷'G5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢&W÷'G2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'B’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'BçFVæçEö–BÓÒFVæçBæ–BÀ¢fÖ–Ç•F–ÖVÆ–æU&W÷'BçF&vWE÷G—Ræ–åò…²'&öf–ÆR"Â&ÖW76vR%Ò’’æ÷&FW%ö'’„fÖ–Ç•F–ÖVÆ–æU&W÷'Bç7FGW2ÂfÖ–Ç•F–ÖVÆ–æU&W÷'Bæ7&VFVEöBæFW62‚’’’æÆÂ‚¢6&G2Ò" ¢f÷"&W÷'B–â&W÷'G3 ¢–b&W÷'BçF&vWE÷G—RÓÒ'&öf–ÆR#¢6öçFVçBÒb.89~8:Ş89^8*>8;Î8:¾ûÉ§¶fÖ–Ç•öÖW76vUöæÖR‡&W÷'BçF&vWEö–BÂ6W76–öâ—Ò ¢VÇ6S ¢ÖW76vRÒ6W76–öâævWB„fÖ–Ç”ÖW76vRÂ&W÷'BçF&vWEö–B“²6öçFVçBÒb.8:88>8+¾8;Î8+Xéşih~ûÉ§¶ÖW76vRæ&öG’–bÖW76vRVÇ6R~z+®Š¨Ş8~8Ş8î8¾8)2wÒ ¢6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÇãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R‡&W÷'Bç7FGW2—ÓÂ÷7ãâÇ7G&öæsç¶‡FÖÂæW66R†6öçFVçB—ÓÂ÷7G&öæsãÂ÷ãÇîynyKûÉ§¶‡FÖÂæW66R…D”ÔTÄ”äUõ$Uõ%Eõ$T4ôå2ævWB‡&W÷'Bç&V6öâÂ&W÷'Bç&V6öâ’—ÓÂ÷ãÇç¶‡FÖÂæW66R‡&W÷'BæFWF–Ç2÷"~Š›>{K8®8rr—ÓÂ÷ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷6fWG’÷&W÷'G2öÖævR÷·&W÷'Bæ–GÒ#ãÇ6VÆV7BæÖSÒ'7FGW2#ãÆ÷F–öâfÇVSÒ&÷Vâ#îiÊ®Zûî[ùÃÂö÷F–öããÆ÷F–öâfÇVSÒ'&Wf–Wv–ær#îz+®Š¨ŞKŠÓÂö÷F–öããÆ÷F–öâfÇVSÒ'&W6öÇfVB#îZûî[ùÎkˆ8óÂö÷F–öããÆ÷F–öâfÇVSÒ&F—6Ö—76VB#îZûî[ùÎKˆŞŠhÂö÷F–öããÂ÷6VÆV7CãÆÆ&VÃîzêyn8:8:#ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FÖ–åöæ÷FR"Ö†ÆVæwFƒÒ#S#ç¶‡FÖÂæW66R‡&W÷'BæFÖ–åöæ÷FR÷"rr—ÓÂ÷FW‡F&VãÆ'WGFöãîKùŞZÙƒÂö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrp¢&WGW&âÆ–÷WB‚.89~8:Ş89^8*>8;Î8:¾8;¾8:88>8+¾8;Î8+˜	®Z"ÂbrrsÆƒî89~8:Ş89^8*>8;Î8:¾8;¾8:88>8+¾8;Î8+˜	®ZÂöƒç¶6&G2÷"sÇî˜	®Z8ş8.8(®8î8¾8)>8#Â÷âwÒrrrÂW6W"  ¤ç÷7B‚"öfÖ–Ç’÷6fWG’÷&W÷'G2öÖævR÷·&W÷'Eö–GÒ"¦FVbfÖ–Ç•÷6fWG•÷&W÷'E÷WFFR‡&W÷'Eö–C¢–çBÂ7FGW3¢7G"Òf÷&Ò‚âââ’ÂFÖ–åöæ÷FS¢7G"Òf÷&Ò‚""’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W73²&W÷'BÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•F–ÖVÆ–æU&W÷'B’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'Bæ–BÓÒ&W÷'Eö–BÂfÖ–Ç•F–ÖVÆ–æU&W÷'BçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B&W÷'B÷"7FGW2æ÷B–â²&÷Vâ"Â'&Wf–Wv–ær"Â'&W6öÇfVB"Â&F—6Ö—76VB'Ó¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&W÷'Bç7FGW2Â&W÷'BæFÖ–åöæ÷FRÂ&W÷'Bæ†æFÆVEö'•ö–BÂ&W÷'Bæ†æFÆVEöBÒ7FGW2ÂFÖ–åöæ÷FRç7G&—‚•³£SÒ÷"æöæRÂW6W"æ–BÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæFB„fÖ–Ç”ÖöFW&F–öäVF—B‡FVæçEö–C×FVæçBæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂF&vWE÷G—S×&W÷'BçF&vWE÷G—RÂF&vWEö–C×&W÷'BçF&vWEö–BÂ7F–öãÖb'&W÷'C§·7FGW7Ò"ÂFWF–Ç3×&W÷'BæFÖ–åöæ÷FR’“²6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷6fWG’÷&W÷'G2öÖævR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷&W7G&–7F–öç2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷&W7G&–7F–öç5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢÷væW'2Ò6W76–öâæW†V7WFR‡6VÆV7B…W6W"’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—çW6W%ö–BÓÒW6W"æ–B’çv†W&R€¢Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’æF—7F–æ7B‚’æ÷&FW%ö'’…W6W"ææÖR’’ç66Æ'2‚’æÆÂ‚¢6&G2Ò" ¢f÷"÷væW"–â÷væW'3 ¢&W7G&–7F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•W6W%&W7G&–7F–öâ’çv†W&R„fÖ–Ç•W6W%&W7G&–7F–öâçFVæçEö–BÓÒFVæçBæ–BÀ¢fÖ–Ç•W6W%&W7G&–7F–öâçW6W%ö–BÓÒ÷væW"æ–B’¢6&G2³ÒbrrsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ3ç¶‡FÖÂæW66R†÷væW"ææÖR—ÓÂöƒ3ãÇç¶‡FÖÂæW66R†÷væW"æVÖ–Â—ÓÂ÷ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷&W7G&–7F–öç2öÖævR÷¶÷væW"æ–GÒ#ãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ'÷7F–æuöF—6&ÆVB"fÇVSÒ'G'VR"²v6†V6¶VBr–b&W7G&–7F–öâæB&W7G&–7F–öâç÷7F–æuöF—6&ÆVBVÇ6RrwÓâh©^z‹ş8;¾8+>8:8;>888).XÎjÚ#ÂöÆ&VÃãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&Æ–¶W5öF—6&ÆVB"fÇVSÒ'G'VR"²v6†V6¶VBr–b&W7G&–7F–öâæB&W7G&–7F–öâæÆ–¶W5öF—6&ÆVBVÇ6RrwÓâ8N8N8Ş8).XÎjÚ#ÂöÆ&VÃãÆÆ&VÃãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&ÖW76vW5öF—6&ÆVB"fÇVSÒ'G'VR"²v6†V6¶VBr–b&W7G&–7F–öâæB&W7G&–7F–öâæÖW76vW5öF—6&ÆVBVÇ6RrwÓâ8:88>8+¾8;Î8+8).XÎjÚ#ÂöÆ&VÃãÆÆ&VÃîXÎjÚ.ynyK8;¾zêyn8:8:#ÂöÆ&VÃãÇFW‡F&VæÖSÒ'&V6öâ"Ö†ÆVæwFƒÒ#S#ç¶‡FÖÂæW66R‡&W7G&–7F–öâç&V6öâ–b&W7G&–7F–öâæB&W7G&–7F–öâç&V6öâVÇ6Rrr—ÓÂ÷FW‡F&VãÆ'WGFöãîXŠyJx«nhX¾8).KùŞZÙƒÂö'WGFöããÂöf÷&ÓãÂö'F–6ÆSârrp¢&WGW&âÆ–÷WB‚$dÔ”ÅXŠyJXÎjÚ""ÂbrrsÆƒädÔ”ÅXŠyJXÎjÚ#ÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇî™k.Šj~8(NhI¾xªÎ88~8;Î8+ş8şjè¾8~8ş8î8î8KªNkXj™şˆ;Ş888).X¾XŠ^8¾XÎjÚ.8~8Ş8î88.888n8îZHi»N8şi8ŞKÙÎ[^jÛN8KùŞZÙ8^8(Î8î88#Â÷ãÂöF—cç¶6&G2÷"sÇî˜
>i®8*®8;Î88®8;Î8ş8N8î8¾8)>8#Â÷âwÒrrrÂW6W"  ¤ç÷7B‚"öfÖ–Ç’÷&W7G&–7F–öç2öÖævR÷¶÷væW%ö–GÒ"¦FVbfÖ–Ç•÷&W7G&–7F–öå÷6fR†÷væW%ö–C¢–çBÂ÷7F–æuöF—6&ÆVC¢&ööÂÒf÷&Ò„fÇ6R’ÂÆ–¶W5öF—6&ÆVC¢&ööÂÒf÷&Ò„fÇ6R’ÂÖW76vW5öF—6&ÆVC¢&ööÂÒf÷&Ò„fÇ6R’Â&V6öã¢7G"Òf÷&Ò‚""’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢Æ–æ¶VBÒ6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÀ¢Föt÷væW'6†—çW6W%ö–BÓÒ÷væW%ö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’¢–bæ÷BÆ–æ¶VC¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&W7G&–7F–öâÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•W6W%&W7G&–7F–öâ’çv†W&R„fÖ–Ç•W6W%&W7G&–7F–öâçFVæçEö–BÓÒFVæçBæ–BÀ¢fÖ–Ç•W6W%&W7G&–7F–öâçW6W%ö–BÓÒ÷væW%ö–B’¢–bæ÷B&W7G&–7F–öã ¢&W7G&–7F–öâÒfÖ–Ç•W6W%&W7G&–7F–öâ‡FVæçEö–C×FVæçBæ–BÂW6W%ö–CÖ÷væW%ö–BÂWFFVEö'•ö–C×W6W"æ–B“²6W76–öâæFB‡&W7G&–7F–öâ¢&W7G&–7F–öâç÷7F–æuöF—6&ÆVBÂ&W7G&–7F–öâæÆ–¶W5öF—6&ÆVBÂ&W7G&–7F–öâæÖW76vW5öF—6&ÆVBÒ÷7F–æuöF—6&ÆVBÂÆ–¶W5öF—6&ÆVBÂÖW76vW5öF—6&ÆV@¢&W7G&–7F–öâç&V6öâÂ&W7G&–7F–öâçWFFVEö'•ö–BÂ&W7G&–7F–öâçWFFVEöBÒ&V6öâç7G&—‚•³£SÒ÷"æöæRÂW6W"æ–BÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæFB„fÖ–Ç”ÖöFW&F–öäVF—B‡FVæçEö–C×FVæçBæ–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂF&vWE÷G—SÒ'W6W""ÂF&vWEö–CÖ÷væW%ö–BÀ¢7F–öãÒ'&W7G&–7F–öå÷WFFR"ÂFWF–Ç3Öb'÷7F–æs×·÷7F–æuöF—6&ÆVGÒÂÆ–¶W3×¶Æ–¶W5öF—6&ÆVGÒÂÖW76vW3×¶ÖW76vW5öF—6&ÆVGÒ"’¢6W76–öâæ6öÖÖ—B‚“²&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷&W7G&–7F–öç2öÖævR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’ö66÷VçB"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö66÷VçE÷vR‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFörÂFVæçB’æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’æ÷&FW%ö'’…FVæçBææÖRÂFöræ6ÆÅöæÖR¢’æÆÂ‚¢G&ç6fW%ö6&G2Ò" ¢f÷"÷væW'6†—ÂFörÂFVæçB–â&V6÷&G3 ¢–b÷væW'6†—ç&VÆF–öç6†—Ò'&–Ö'’# ¢6öçF–çVP¢7V66W76÷'2Ò6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒFöt÷væW'6†—çW6W%ö–B¢çv†W&R„Föt÷væW'6†—æFöuö–BÓÒFöræ–BÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÀ¢Föt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöt÷væW'6†—ç&VÆF–öç6†—ÓÒ&fÖ–Ç’"ÂFöt÷væW'6†—çW6W%ö–BÒW6W"æ–B¢æ÷&FW%ö'’…W6W"ææÖR¢’æÆÂ‚¢÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶—FVÒæ–GÒ#ç¶‡FÖÂæW66R†ÖVÖ&W"ææÖR—ŞûÈ‡¶‡FÖÂæW66R†ÖVÖ&W"æVÖ–Â—ŞûÈ“Âö÷F–öãârf÷"—FVÒÂÖVÖ&W"–â7V66W76÷'2¢7F–öâÒbrrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’ö66÷VçB÷G&ç6fW"#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ&÷væW'6†—ö–B"fÇVSÒ'¶÷væW'6†—æ–GÒ#à¢ÆÆ&VÃîik8~8NK‹¾8*®8;Î88®8;ÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ'7V66W76÷%ö÷væW'6†—ö–B"&WV—&VCç¶÷F–öç7ÓÂ÷6VÆV7Cà¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&ÖVB"fÇVSÒ'G'VR"&WV—&VCâK‹¾8*®8;Î88®8;Î8).ZHi»N88(¾8>88).z+®Š¨Ş8~8î8~8óÂöÆ&VÃãÆ'WGFöãîK‹¾8*®8;Î88®8;Î8).[É^8Ş{i8Âö'WGFöããÂöf÷&Óârrr–b÷F–öç2VÇ6RsÇãÇ6ÖÆÃîXX8¾xªÎˆˆî8¾8(8NZënixş8).8>8îhI¾xªÎ8˜
>i®8~8n8(.8(8n88K‹¾8*®8;Î88®8;Î8).[É^8Ş{i8.8î88#Â÷6ÖÆÃãÂ÷âp¢G&ç6fW%ö6&G2³ÒbsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ3ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ŞûÙÇ¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂöƒ3ç¶7F–öçÓÂö'F–6ÆSâp¢FVæçEö–G2Ò6÷'FVB‡¶÷væW'6†—çFVæçEö–Bf÷"÷væW'6†—ÂòÂò–â&V6÷&G7Ò¢FVæçEö÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'·FVæçBæ–GÒ#ç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂö÷F–öãârf÷"FVæçB–â6W76–öâç66Æ'2‡6VÆV7B…FVæçB’çv†W&R…FVæçBæ–Bæ–åò‡FVæçEö–G2’’æ÷&FW%ö'’…FVæçBææÖR’’æÆÂ‚’’–bFVæçEö–G2VÇ6R" ¢&WVW7G2Ò6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç•v—F†G&vÅ&WVW7BÂFVæçB’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒfÖ–Ç•v—F†G&vÅ&WVW7BçFVæçEö–B¢çv†W&R„fÖ–Ç•v—F†G&vÅ&WVW7BçW6W%ö–BÓÒW6W"æ–B’æ÷&FW%ö'’„fÖ–Ç•v—F†G&vÅ&WVW7Bç&WVW7FVEöBæFW62‚’’’æÆÂ‚¢&WVW7E÷&÷w2Ò""æ¦ö–â†bsÇG#ãÇFCç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷FCãÇFCç·&WVW7Bç&WVW7FVEöBç7G&gF–ÖR‚"U’ÒVÒÒVB"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R‡&WVW7Bç7FGW2—ÓÂ÷FCãÇFCç².KùŞZÙ‚"–b&WVW7BæFF÷öÆ–7’ÓÒ'&WF–â"VÇ6R.X˜®™šN[ˆÎiÉ²'ÓÂ÷FCãÂ÷G#ârf÷"&WVW7BÂFVæçB–â&WVW7G2¢v—F†G&vÂÒbrrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’ö66÷VçB÷v—F†G&r#ãÆÆ&VÃî˜KÉ®88(¾xªÎˆˆãÂöÆ&VÃãÇ6VÆV7BæÖSÒ'FVæçEö–B"&WV—&VCç·FVæçEö÷F–öç7ÓÂ÷6VÆV7Cà¢ÆÆ&VÃîh©^z‹ş8;¾89~8:Ş89^8*>8;Î8:¾88~8;Î8+óÂöÆ&VÃãÇ6VÆV7BæÖSÒ&FF÷öÆ–7’#ãÆ÷F–öâfÇVSÒ'&WF–â#îh	Ş8NX{®88~8nKùŞZÙ88(³Âö÷F–öããÆ÷F–öâfÇVSÒ'&VÖ÷fU÷W'6öæÂ#î89~8:Ş89^8*>8;Î8:¾8ˆz®Xˆn8îh©^z‹ş8îX˜®™šN8).[ˆÎiÉ¾88(³Âö÷F–öããÂ÷6VÆV7Cà¢ÆÆ&VÃî˜KÉ®ynyKûÈK»¾hHşûÈ“ÂöÆ&VÃãÇFW‡F&VæÖSÒ'&V6öâ"Ö†ÆVæwFƒÒ#S#ãÂ÷FW‡F&Và¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&ÖVB"fÇVSÒ'G'VR"&WV—&VCâxªÎˆˆî8ÎXh^Zë8).z+®Š¨Ş[èÎ8dÔ”Å˜
>i®8ÎŠz>™šN8^8(Î8(¾8>88).ynŠz>8~8î8~8óÂöÆ&VÃãÆ'WGFöâ6Æ73Ò&FævW"#î˜KÉ®8).yK>Š¸¾88(³Âö'WGFöããÂöf÷&Óârrr–bFVæçEö÷F–öç2VÇ6RsÇî˜KÉ®Zûî‹8îxªÎˆˆî˜
>i®8ş8.8(®8î8¾8)>8#Â÷âp¢&öG’ÒbrrsÆƒî˜KÉ®8;¾K‹¾8*®8;Î88®8;Î[É^{i8ãÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇîK‹¾8*®8;Î88®8;Î8).ZHi»N88(¾ZNY8ş8˜KÉ®yK>Š¸¾8(8(®XX8¾[É^{i8î8).ŠÎ8>8n8ş88^8N8#Â÷ãÂöF—cà¢Æƒ#îK‹¾8*®8;Î88®8;Î8).Zënixş8[É^8Ş{i8Âöƒ#ç·G&ç6fW%ö6&G2÷"sÇî[É^{i8îXúşˆ;Ş8®hI¾xªÎ8ş8.8(®8î8¾8)>8#Â÷âwÓÆƒ#ädÔ”Å˜KÉ®yK>Š¸³Âöƒ#ç·v—F†G&vÇĞ¢Æƒ#îyK>Š¸¾[^jÛCÂöƒ#ãÇF&ÆSãÇG#ãÇFƒîxªÎˆˆãÂ÷FƒãÇFƒîyK>Š¸¾izSÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒî88~8;Î8+óÂ÷FƒãÂ÷G#ç·&WVW7E÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îyK>Š¸¾8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.˜KÉ®8;¾[É^{i8îûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’ö66÷VçB÷G&ç6fW""¦FVbfÖ–Ç•ö66÷VçE÷G&ç6fW"†÷væW'6†—ö–C¢–çBÒf÷&Ò‚âââ’Â7V66W76÷%ö÷væW'6†—ö–C¢–çBÒf÷&Ò‚âââ’Â6öæf—&ÖVC¢&ööÂÒf÷&Ò„fÇ6R’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7W'&VçBÒ6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—æ–BÓÒ÷væW'6†—ö–BÂFöt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÀ¢Föt÷væW'6†—ç&VÆF–öç6†—ÓÒ'&–Ö'’"ÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’¢7V66W76÷"Ò6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—æ–BÓÒ7V66W76÷%ö÷væW'6†—ö–BÀ¢Föt÷væW'6†—ç&VÆF–öç6†—ÓÒ&fÖ–Ç’"ÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’¢–bæ÷B6öæf—&ÖVB÷"æ÷B7W'&VçB÷"æ÷B7V66W76÷"÷"†7W'&VçBçFVæçEö–BÂ7W'&VçBæFöuö–B’Ò‡7V66W76÷"çFVæçEö–BÂ7V66W76÷"æFöuö–B“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.[É^{i8îXh^Zë8).z+®Š¨Ş8~8Ş8î8¾8)2"¢7W'&VçBç&VÆF–öç6†—Â7V66W76÷"ç&VÆF–öç6†—Ò&fÖ–Ç’"Â'&–Ö'’ ¢6W76–öâæFB„fÖ–Ç”ÖöFW&F–öäVF—B‡FVæçEö–CÖ7W'&VçBçFVæçEö–BÂFÖ–å÷W6W%ö–C×W6W"æ–BÂF&vWE÷G—SÒ&÷væW'6†—"À¢F&vWEö–CÖ7W'&VçBæFöuö–BÂ7F–öãÒ'&–Ö'•ö÷væW%÷G&ç6fW""ÂFWF–Ç3Öb&g&öÓ×·W6W"æ–GÒÇFó×·7V66W76÷"çW6W%ö–GÒ"’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’ö66÷VçB"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’ö66÷VçB÷v—F†G&r"¦FVbfÖ–Ç•ö66÷VçE÷v—F†G&r‡FVæçEö–C¢–çBÒf÷&Ò‚âââ’ÂFF÷öÆ–7“¢7G"Òf÷&Ò‚'&WF–â"’Â&V6öã¢7G"Òf÷&Ò‚""’Â6öæf—&ÖVC¢&ööÂÒf÷&Ò„fÇ6R’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢Æ–æ¶VBÒ6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçEö–BÀ¢Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’¢–bæ÷B6öæf—&ÖVB÷"æ÷BÆ–æ¶VB÷"FF÷öÆ–7’æ÷B–â²'&WF–â"Â'&VÖ÷fU÷W'6öæÂ'Ò÷"FVæçEö–Bæ÷B–âfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.˜KÉ®yK>Š¸¾8îXh^Zë8).z+®Š¨Ş8~8n8ş88^8B"¢VæF–ærÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•v—F†G&vÅ&WVW7Bæ–B’çv†W&R„fÖ–Ç•v—F†G&vÅ&WVW7BçFVæçEö–BÓÒFVæçEö–BÀ¢fÖ–Ç•v—F†G&vÅ&WVW7BçW6W%ö–BÓÒW6W"æ–BÂfÖ–Ç•v—F†G&vÅ&WVW7Bç7FGW2ÓÒ'&WVW7FVB"’¢–bæ÷BVæF–æs ¢6W76–öâæFB„fÖ–Ç•v—F†G&vÅ&WVW7B‡FVæçEö–C×FVæçEö–BÂW6W%ö–C×W6W"æ–BÂFF÷öÆ–7“ÖFF÷öÆ–7’Â&V6öã×&V6öâç7G&—‚•³£SÒ÷"æöæR’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’ö66÷VçB"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷v—F†G&vÇ2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷v—F†G&vÇ5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢&V6÷&G2Ò6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç•v—F†G&vÅ&WVW7BÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒfÖ–Ç•v—F†G&vÅ&WVW7BçW6W%ö–B¢çv†W&R„fÖ–Ç•v—F†G&vÅ&WVW7BçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç•v—F†G&vÅ&WVW7Bç7FGW2ÂfÖ–Ç•v—F†G&vÅ&WVW7Bç&WVW7FVEöBæFW62‚’’’æÆÂ‚¢6&G2Ò" ¢f÷"&WVW7BÂ÷væW"–â&V6÷&G3 ¢öÆ–7’Ò.88~8;Î8+şKùŞZÙ‚"–b&WVW7BæFF÷öÆ–7’ÓÒ'&WF–â"VÇ6R.89~8:Ş89^8*>8;Î8:¾8;¾iÊÎK«®h©^z‹ş8îX˜®™šN[ˆÎiÉ² ¢f÷&ÒÒbrrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’÷v—F†G&vÇ2öÖævR÷·&WVW7Bæ–GÒ#ãÇ6VÆV7BæÖSÒ&7F–öâ#ãÆ÷F–öâfÇVSÒ&&÷fR#îh›şŠ¨Ş8~8n˜
>i®Šz>™šCÂö÷F–öããÆ÷F–öâfÇVSÒ'&V¦V7B#îyK>Š¸¾8).[zî8~h‹¾8“Âö÷F–öããÂ÷6VÆV7CãÆÆ&VÃîzêyn8:8:#ÂöÆ&VÃãÇFW‡F&VæÖSÒ&FÖ–åöæ÷FR"Ö†ÆVæwFƒÒ#S#ãÂ÷FW‡F&VãÆ'WGFöãîXznyn88(³Âö'WGFöããÂöf÷&Óârrr–b&WVW7Bç7FGW2ÓÒ'&WVW7FVB"VÇ6R" ¢6&G2³ÒbsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ3ç¶‡FÖÂæW66R†÷væW"ææÖR—ŞûÙÇ¶‡FÖÂæW66R†÷væW"æVÖ–Â—ÓÂöƒ3ãÇãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R‡&WVW7Bç7FGW2—ÓÂ÷7ãâ·öÆ–7—ÓÂ÷ãÇç¶‡FÖÂæW66R‡&WVW7Bç&V6öâ÷".ynyK8®8r"—ÓÂ÷ç¶f÷&×ÓÂö'F–6ÆSâp¢&WGW&âÆ–÷WB‚$dÔ”Å˜KÉ®yK>Š¸²"ÂbsÆƒädÔ”Å˜KÉ®yK>Š¸³Âöƒç¶6&G2÷"#ÇîyK>Š¸¾8ş8.8(®8î8¾8)>8#Â÷â'ÒrÂW6W"  ¤ç÷7B‚"öfÖ–Ç’÷v—F†G&vÇ2öÖævR÷·&WVW7Eö–GÒ"¦FVbfÖ–Ç•÷v—F†G&vÅö†æFÆR‡&WVW7Eö–C¢–çBÂ7F–öã¢7G"Òf÷&Ò‚âââ’ÂFÖ–åöæ÷FS¢7G"Òf÷&Ò‚""’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢FÖ–âÂFVæçBÒ66W70¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•v—F†G&vÅ&WVW7B’çv†W&R„fÖ–Ç•v—F†G&vÅ&WVW7Bæ–BÓÒ&WVW7Eö–BÀ¢fÖ–Ç•v—F†G&vÅ&WVW7BçFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç•v—F†G&vÅ&WVW7Bç7FGW2ÓÒ'&WVW7FVB"’¢–bæ÷B—FVÒ÷"7F–öâæ÷B–â²&&÷fR"Â'&V¦V7B'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢–b7F–öâÓÒ&&÷fR# ¢&–Ö'•ö6÷VçBÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„Föt÷væW'6†—æ–B’’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÀ¢Föt÷væW'6†—çW6W%ö–BÓÒ—FVÒçW6W%ö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöt÷væW'6†—ç&VÆF–öç6†—ÓÒ'&–Ö'’"’’÷" ¢–b&–Ö'•ö6÷VçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.K‹¾8*®8;Î88®8;Î8îhI¾xªÎ8Î8.8(®8î88.XX8¾Zënixş88î[É^{i8î8).ŠÎ8>8n8ş88^8B"¢6W76–öâæW†V7WFR‡FW‡B‚%UDDRFöuö÷væW'6†—24UB7F—fRÒdÅ4Rt„U$RFVæçEö–BÒ§FVæçEö–BäBW6W%ö–BÒ§W6W%ö–B"’Â²'FVæçEö–B#¢FVæçBæ–BÂ'W6W%ö–B#¢—FVÒçW6W%ö–GÒ¢–b—FVÒæFF÷öÆ–7’ÓÒ'&VÖ÷fU÷W'6öæÂ# ¢Föuö–G2Ò6VÆV7B„Föræ–B’çv†W&R„FörçFVæçEö–BÓÒFVæçBæ–B¢f÷"÷7B–â6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒçWÆöFVEö'•ö–BÓÒ—FVÒçW6W%ö–BÂfÖ–Ç”FötÆ'VÔ—FVÒæFöuö–Bæ–åò†Föuö–G2’’’æÆÂ‚“ ¢6W76–öâæFVÆWFR‡÷7B¢÷F†W%öÆ–æ·2Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„Föt÷væW'6†—æ–B’’çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒ—FVÒçW6W%ö–BÀ¢Föt÷væW'6†—çFVæçEö–BÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’÷" ¢–bæ÷B÷F†W%öÆ–æ·3 ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçW6W%ö–BÓÒ—FVÒçW6W%ö–B’¢–b&öf–ÆS ¢&öf–ÆRç&öf–ÆU÷V&Æ–2ÒfÇ6S²&öf–ÆRç†÷FõöFFÒæöæS²&öf–ÆRæ&–òÒæöæS²&öf–ÆRææ–6¶æÖRÒæöæP¢—FVÒç7FGW2Ò&&÷fVB ¢VÇ6S ¢—FVÒç7FGW2Ò'&V¦V7FVB ¢—FVÒæ†æFÆVEö'•ö–BÂ—FVÒæ†æFÆVEöBÂ—FVÒæFÖ–åöæ÷FRÒFÖ–âæ–BÂFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’ÂFÖ–åöæ÷FRç7G&—‚•³£SÒ÷"æöæP¢6W76–öâæFB„fÖ–Ç”ÖöFW&F–öäVF—B‡FVæçEö–C×FVæçBæ–BÂFÖ–å÷W6W%ö–CÖFÖ–âæ–BÂF&vWE÷G—SÒ'v—F†G&vÂ"ÂF&vWEö–CÖ—FVÒæ–BÀ¢7F–öãÖb'v—F†G&vÅ÷¶7F–öçÒ"ÂFWF–Ç3Ö—FVÒæFÖ–åöæ÷FR’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷v—F†G&vÇ2öÖævR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’öF6†&ö&BöÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öF6†&ö&EöÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢÷væW%ö–G2Ò6VÆV7B„Föt÷væW'6†—çW6W%ö–B’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’æF—7F–æ7B‚¢÷væW'2Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB‚’’ç6VÆV7Eög&öÒ†÷væW%ö–G2ç7V'VW'’‚’’’÷" ¢Föuö–G2Ò6VÆV7B„Föræ–B’çv†W&R„FörçFVæçEö–BÓÒFVæçBæ–B¢÷7G2Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç”FötÆ'VÔ—FVÒæ–B’’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒæFöuö–Bæ–åò†Föuö–G2’’’÷" ¢÷Vå÷&W÷'G2Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç•F–ÖVÆ–æU&W÷'Bæ–B’’çv†W&R„fÖ–Ç•F–ÖVÆ–æU&W÷'BçFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç•F–ÖVÆ–æU&W÷'Bç7FGW2æ–åò…²&÷Vâ"Â'&Wf–Wv–ær%Ò’’’÷" ¢ææ÷Væ6VÖVçG2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”ææ÷Væ6VÖVçB’çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçBçFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç”ææ÷Væ6VÖVçBæ7F—fRæ—5ò…G'VR’’’æÆÂ‚¢Vç&VBÒ ¢f÷"ææ÷Væ6VÖVçB–âææ÷Væ6VÖVçG3 ¢&VEö6÷VçBÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç”ææ÷Væ6VÖVçE&VBæ–B’’çv†W&R„fÖ–Ç”ææ÷Væ6VÖVçE&VBæææ÷Væ6VÖVçEö–BÓÒææ÷Væ6VÖVçBæ–BÀ¢fÖ–Ç”ææ÷Væ6VÖVçE&VBçW6W%ö–Bæ–åò†÷væW%ö–G2’’’÷" ¢Vç&VB³ÒÖ‚†÷væW'2Ò&VEö6÷VçBÂ¢WfVçEö–G2Ò¶—FVÒæ–Bf÷"—FVÒ–âææ÷Væ6VÖVçG2–b—FVÒæWfVçEöFFUĞ¢GFVæF–ærÒ6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB†gVæ2æF—7F–æ7B„fÖ–Ç”WfVçE&W7öç6RçW6W%ö–B’’’çv†W&R„fÖ–Ç”WfVçE&W7öç6Ræææ÷Væ6VÖVçEö–Bæ–åò†WfVçEö–G2’ÂfÖ–Ç”WfVçE&W7öç6Rç7FGW2ÓÒ&GFVæF–ær"’’–bWfVçEö–G2VÇ6R ¢'F–6—F–öâÒ&÷VæB‚†GFVæF–ær÷"’¢òÖ‚†÷væW'2¢ÆVâ†WfVçEö–G2’Â’Â’–bWfVçEö–G2VÇ6R ¢6&G2ÒbrrsÆF—b6Æ73Ò&w&–B#ãÆ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ#ç¶÷væW'7ÓÂöƒ#ãÇîy›¾˜Ë.8*®8;Î88®8;ÃÂ÷ãÂö'F–6ÆSãÆ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ#ç·÷7G7ÓÂöƒ#ãÇî8*.8:¾898:h©^z‹óÂ÷ãÂö'F–6ÆSà¢Æ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ#ç·Vç&VGÓÂöƒ#ãÇî8®yú^8(8¾iÊ®ŠªŞûÈ[»n8ûÈ“Â÷ãÂö'F–6ÆSãÆ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ#ç¶÷Vå÷&W÷'G7ÓÂöƒ#ãÇîiÊ®Zûî[ùÎ8;¾z+®Š¨ŞKŠŞ8î˜	®ZÂ÷ãÂö'F–6ÆSãÆ'F–6ÆR6Æ73Ò'FVæçB#ãÆƒ#ç·'F–6—F–öçÒSÂöƒ#ãÇî8*N898;>88Xø.XªxèsÂ÷ãÂö'F–6ÆSãÂöF—cârrp¢&V6VçBÒ6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç”ÖöFW&F–öäVF—BÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒfÖ–Ç”ÖöFW&F–öäVF—BæFÖ–å÷W6W%ö–B¢çv†W&R„fÖ–Ç”ÖöFW&F–öäVF—BçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç”ÖöFW&F–öäVF—Bæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ#’’æÆÂ‚¢&÷w2Ò""æ¦ö–â†bsÇG#ãÇFCç¶VF—Bæ7&VFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†FÖ–âææÖR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†VF—Bæ7F–öâ—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†VF—BæFWF–Ç2÷".ûÈÒ"—ÓÂ÷FCãÂ÷G#ârf÷"VF—BÂFÖ–â–â&V6VçB¢&WGW&âÆ–÷WB‚$dÔ”Åzêyn8888>8+~8:^89Î8;Î88’"ÂbsÆƒädÔ”Åzêyn8888>8+~8:^89Î8;Î88“Âöƒç¶6&G7ÓÆƒ#îiÈ‹ù8îzêyni8ŞKÙÃÂöƒ#ãÇF&ÆSãÇG#ãÇFƒîiz^i˜#Â÷FƒãÇFƒîh¸^[Ù>ˆSÂ÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÇFƒîXh^Zë“Â÷FƒãÂ÷G#ç·&÷w2÷"#ÇG#ãÇFB6öÇ7ãÕÂ#EÂ#î[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#â'ÓÂ÷F&ÆSârÂW6W"  ¤dÔ”Å•ôDô5TÔTåEõE•U2Ò²'FW&×2#¢$dÔ”ÅXŠyJŠhş{HB"Â&ÖW76vUöÖöæ—F÷&–ær#¢.8:88>8+¾8;Î8+™k.Šj~ik˜yÒ"Â'†÷Fõ÷&—f7’#¢.XiyÉşXZÎ™h¾8;¾X¾K«®h8^Zik˜yÒ'Ğ  ¤ævWB‚"öfÖ–Ç’÷FW&×2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷FW&×5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢fW'6–öç2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç•FW&×5fW'6–öâ’çv†W&R„fÖ–Ç•FW&×5fW'6–öâçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç•FW&×5fW'6–öâçV&Æ—6†VEöBæFW62‚’’’æÆÂ‚¢&÷w2Ò""æ¦ö–â†bsÇG#ãÇFCç¶‡FÖÂæW66R„dÔ”Å•ôDô5TÔTåEõE•U2ævWB†—FVÒæFö7VÖVçE÷G—RÂ—FVÒæFö7VÖVçE÷G—R’—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒçfW'6–öâ—ÓÂ÷FCãÇFCç².XZÎ™h¾KŠÒ"–b—FVÒæ7F—fRVÇ6R.iz~x˜‚'ÓÂ÷FCãÇFCç¶—FVÒçV&Æ—6†VEöBç7G&gF–ÖR‚"U’ÒVÒÒVB"—ÓÂ÷FCãÂ÷G#ârf÷"—FVÒ–âfW'6–öç2¢÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶¶W—Ò#ç·fÇVWÓÂö÷F–öãârf÷"¶W’ÂfÇVR–âdÔ”Å•ôDô5TÔTåEõE•U2æ—FV×2‚’¢6öç6VçE÷&V6÷&G2Ò6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç”6öç6VçBÂfÖ–Ç•FW&×5fW'6–öâÂW6W"¢æ¦ö–â„fÖ–Ç•FW&×5fW'6–öâÂfÖ–Ç•FW&×5fW'6–öâæ–BÓÒfÖ–Ç”6öç6VçBçFW&×5÷fW'6–öåö–B¢æ¦ö–â…W6W"ÂW6W"æ–BÓÒfÖ–Ç”6öç6VçBçW6W%ö–B¢çv†W&R„fÖ–Ç”6öç6VçBçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç”6öç6VçBæw&VVEöBæFW62‚’’æÆ–Ö—Bƒ’’æÆÂ‚¢6öç6VçE÷&÷w2Ò""æ¦ö–â†bsÇG#ãÇFCç¶6öç6VçBæw&VVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†÷væW"ææÖR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R‡FW&×2çF—FÆR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R‡FW&×2çfW'6–öâ—ÓÂ÷FCãÂ÷G#ârf÷"6öç6VçBÂFW&×2Â÷væW"–â6öç6VçE÷&V6÷&G2¢&öG’ÒbrrsÆƒîXŠyJŠhş{HN8;¾YÎhHşzêycÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇîik8~8Nx˜8).XZÎ™h¾88(¾88YÎ8zŠîšî8îiz~x˜8şˆz®X¹^y¨N8¾{X.K¨n8~88*®8;Î88®8;Î8XhŞYÎhHş8ÎŠzK®8^8(Î8î88#Â÷ãÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃîih~i»8îzŠîšãÂöÆ&VÃãÇ6VÆV7BæÖSÒ&Fö7VÖVçE÷G—R#ç¶÷F–öç7ÓÂ÷6VÆV7CãÆÆ&VÃîx˜yZ®XûsÂöÆ&VÃãÆ–çWBæÖSÒ'fW'6–öâ"Ö†ÆVæwFƒÒ#3"Æ6V†öÆFW#Ò.Kè¾ûÉ£##bÓ’"&WV—&VCà¢ÆÆ&VÃîŠzK®8+ş8*N888:³ÂöÆ&VÃãÆ–çWBæÖSÒ'F—FÆR"Ö†ÆVæwFƒÒ#S"&WV—&VCãÆÆ&VÃîiÊÎihsÂöÆ&VÃãÇFW‡F&VæÖSÒ&&öG’"&÷w3Ò#B"&WV—&VCãÂ÷FW‡F&VãÆ'WGFöãîik8~8Nx˜8).XZÎ™h¾88(³Âö'WGFöããÂöf÷&Óà¢Æƒ#îXZÎ™h¾[^jÛCÂöƒ#ãÇF&ÆSãÇG#ãÇFƒîzŠîšãÂ÷FƒãÇFƒîx˜ƒÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîXZÎ™h¾izSÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îŠhş{HN8şiÊ®y›¾˜Ë.8~88#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSà¢Æƒ#îYÎhHş[^jÛNûÈiÈikK»nûÈ“Âöƒ#ãÇF&ÆSãÇG#ãÇFƒîYÎhHşiz^i˜#Â÷FƒãÇFƒî8*®8;Î88®8;ÃÂ÷FƒãÇFƒîih~i»ƒÂ÷FƒãÇFƒîx˜ƒÂ÷FƒãÂ÷G#ç¶6öç6VçE÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îYÎhHş[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚.XŠyJŠhş{HN8;¾YÎhHşzêyb"Â&öG’ÂW6W"  ¤ç÷7B‚"öfÖ–Ç’÷FW&×2öÖævR"¦FVbfÖ–Ç•÷FW&×5÷V&Æ—6‚†Fö7VÖVçE÷G—S¢7G"Òf÷&Ò‚âââ’ÂfW'6–öã¢7G"Òf÷&Ò‚âââ’ÂF—FÆS¢7G"Òf÷&Ò‚âââ’Â&öG“¢7G"Òf÷&Ò‚âââ’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢fW'6–öâÂF—FÆRÂ&öG’ÒfW'6–öâç7G&—‚’ÂF—FÆRç7G&—‚’Â&öG’ç7G&—‚¢–bFö7VÖVçE÷G—Ræ÷B–âdÔ”Å•ôDô5TÔTåEõE•U2÷"æ÷BfW'6–öâ÷"æ÷BF—FÆR÷"æ÷B&öG“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Šhş{HN8îXh^Zë8).z+®Š¨Ş8~8n8ş88^8B"¢–b6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•FW&×5fW'6–öâæ–B’çv†W&R„fÖ–Ç•FW&×5fW'6–öâçFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç•FW&×5fW'6–öâæFö7VÖVçE÷G—RÓÒFö7VÖVçE÷G—RÂfÖ–Ç•FW&×5fW'6–öâçfW'6–öâÓÒfW'6–öâ’“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.YÎ8x˜yZ®Xû~8Î88~8¾y›¾˜Ë.8^8(Î8n8N8î8’"¢f÷"öÆB–â6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç•FW&×5fW'6–öâ’çv†W&R„fÖ–Ç•FW&×5fW'6–öâçFVæçEö–BÓÒFVæçBæ–BÂfÖ–Ç•FW&×5fW'6–öâæFö7VÖVçE÷G—RÓÒFö7VÖVçE÷G—RÂfÖ–Ç•FW&×5fW'6–öâæ7F—fRæ—5ò…G'VR’’’æÆÂ‚“ ¢öÆBæ7F—fRÒfÇ6P¢6W76–öâæFB„fÖ–Ç•FW&×5fW'6–öâ‡FVæçEö–C×FVæçBæ–BÂFö7VÖVçE÷G—SÖFö7VÖVçE÷G—RÂfW'6–öã×fW'6–öâÂF—FÆS×F—FÆRÂ&öG“Ö&öG’Â7&VFVEö'•ö–C×W6W"æ–B’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’÷FW&×2öÖævR"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’ö6öç6VçG2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö6öç6VçG5÷vR‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢FVæçEö–G2ÒfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ¢fW'6–öç2Ò6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç•FW&×5fW'6–öâÂFVæçB’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒfÖ–Ç•FW&×5fW'6–öâçFVæçEö–B¢çv†W&R„fÖ–Ç•FW&×5fW'6–öâçFVæçEö–Bæ–åò‡FVæçEö–G2’ÂfÖ–Ç•FW&×5fW'6–öâæ7F—fRæ—5ò…G'VR’’æ÷&FW%ö'’…FVæçBææÖRÂfÖ–Ç•FW&×5fW'6–öâæFö7VÖVçE÷G—R’’æÆÂ‚’–bFVæçEö–G2VÇ6RµĞ¢6&G2Ò" ¢f÷"—FVÒÂFVæçB–âfW'6–öç3 ¢6öç6VçBÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”6öç6VçB’çv†W&R„fÖ–Ç”6öç6VçBçFW&×5÷fW'6–öåö–BÓÒ—FVÒæ–BÂfÖ–Ç”6öç6VçBçW6W%ö–BÓÒW6W"æ–B’¢7FFRÒbsÇ7â6Æ73Ò&&FvR#îYÎhHşkˆ8ò¶6öç6VçBæw&VVEöBç7G&gF–ÖR‚"U’ÒVÒÒVB"—ÓÂ÷7ãâr–b6öç6VçBVÇ6RbrrsÆf÷&ÒÖWF†öCÒ'÷7B#ãÆ–çWBG—SÒ&†–FFVâ"æÖSÒ'FW&×5÷fW'6–öåö–B"fÇVSÒ'¶—FVÒæ–GÒ#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&66WFVB"fÇVSÒ'G'VR"&WV—&VCâXh^Zë8).z+®Š¨Ş8~8YÎhHş8~8î8“ÂöÆ&VÃãÆ'WGFöãîYÎhHş8).Š‰˜Ë.88(³Âö'WGFöããÂöf÷&Óârrp¢6&G2³ÒbsÆ'F–6ÆR6Æ73Ò'FVæçB#ãÇãÇ6ÖÆÃç¶‡FÖÂæW66R‡FVæçBææÖR—ŞûÙÎzÊÇ¶‡FÖÂæW66R†—FVÒçfW'6–öâ—Şx˜ƒÂ÷6ÖÆÃãÂ÷ãÆƒ#ç¶‡FÖÂæW66R†—FVÒçF—FÆR—ÓÂöƒ#ãÆF—b7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R†—FVÒæ&öG’—ÓÂöF—cç·7FFWÓÂö'F–6ÆSâp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.Šhş{HN8;¾YÎhHşûÙÄdÔ”Å’"ÂbsÆƒîŠhş{HN8;¾YÎhHóÂöƒç¶6&G2÷"#ÇîxûîYÊ8z+®Š¨Ş8Î[ø^Šh8®Šhş{HN8ş8.8(®8î8¾8)>8#Â÷â'ÒrÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’ö6öç6VçG2"¦FVbfÖ–Ç•ö6öç6VçEö66WB‡&WVW7C¢&WVW7BÂFW&×5÷fW'6–öåö–C¢–çBÒf÷&Ò‚âââ’Â66WFVC¢&ööÂÒf÷&Ò„fÇ6R’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç•FW&×5fW'6–öâ’çv†W&R„fÖ–Ç•FW&×5fW'6–öâæ–BÓÒFW&×5÷fW'6–öåö–BÂfÖ–Ç•FW&×5fW'6–öâæ7F—fRæ—5ò…G'VR’’¢–bæ÷B66WFVB÷"æ÷B—FVÒ÷"—FVÒçFVæçEö–Bæ÷B–âfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.YÎhHşZûî‹8).z+®Š¨Ş8~8Ş8î8¾8)2"¢–bæ÷B6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”6öç6VçBæ–B’çv†W&R„fÖ–Ç”6öç6VçBçFW&×5÷fW'6–öåö–BÓÒ—FVÒæ–BÂfÖ–Ç”6öç6VçBçW6W%ö–BÓÒW6W"æ–B’“ ¢&VÖ÷FRÒ&WVW7Bæ6Æ–VçBæ†÷7B–b&WVW7Bæ6Æ–VçBVÇ6R'Væ¶æ÷vâ ¢6W76–öâæFB„fÖ–Ç”6öç6VçB‡FVæçEö–CÖ—FVÒçFVæçEö–BÂFW&×5÷fW'6–öåö–CÖ—FVÒæ–BÂW6W%ö–C×W6W"æ–BÀ¢—ö†6ƒÖ†6†Æ–"ç6†#Sb‡&VÖ÷FRæVæ6öFR‚’’æ†W†F–vW7B‚’’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’ö6öç6VçG2"Â7FGW5ö6öFSÓ32  ¦FVb&6·Wö§6öå÷fÇVR‡fÇVR“ ¢–b—6–ç7Fæ6R‡fÇVRÂ†FFWF–ÖRÂFFR’“ ¢&WGW&âfÇVRæ—6öf÷&ÖB‚¢–b—6–ç7Fæ6R‡fÇVRÂVçVÒ“ ¢&WGW&âfÇVRçfÇVP¢&WGW&âfÇVP  ¦FVb&6·WöÖöFVÂ†—FVÒÂW†6ÇVFS¢6WE·7G%ÒÂæöæRÒæöæR’ÓâF–7C ¢W†6ÇVFVBÒW†6ÇVFR÷"6WB‚¢&WGW&â¶6öÇVÖâææÖS¢&6·Wö§6öå÷fÇVR†vWFGG"†—FVÒÂ6öÇVÖâææÖR’’f÷"6öÇVÖâ–â—FVÒåõ÷F&ÆUõòæ6öÇVÖç0¢–b6öÇVÖâææÖRæ÷B–âW†6ÇVFVBæBæ÷B6öÇVÖâææÖRæVæG7v—F‚‚%öFF"—Ğ  ¤ævWB‚"öfÖ–Ç’ö&6·W2öÖævR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö&6·W5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢&V6÷&G2Ò6W76–öâæW†V7WFR‡6VÆV7B„fÖ–Ç”&6·WVF—BÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒfÖ–Ç”&6·WVF—Bæ7&VFVEö'•ö–B¢çv†W&R„fÖ–Ç”&6·WVF—BçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç”&6·WVF—Bæ7&VFVEöBæFW62‚’’æÆ–Ö—BƒS’’æÆÂ‚¢&÷w2Ò""æ¦ö–â†bsÇG#ãÇFCç¶VF—Bæ7&VFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†7F÷"ææÖR—ÓÂ÷FCãÇFCç¶VF—Bç&V6÷&Eö6÷VçGÓÂ÷FCãÇFCç¶‡FÖÂæW66R†VF—Bæf÷&ÖBçWW"‚’—ÓÂ÷FCãÂ÷G#ârf÷"VF—BÂ7F÷"–â&V6÷&G2¢&öG’ÒbrrsÆƒädÔ”Å88~8;Î8+şX{®X©¾8;¾8988>8*ş8*.88>89sÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇî˜h©îKŠŞ8îxªÎˆˆî8¾[î88(¾8*®8;Î88®8;Î˜
>i®8hI¾xªÎ8h©^z‹ş8YÎhHş8yº>iû¾[^jÛN8)%¤•8¾8î88(8î88.898+8:ş8;Î888(N8:Ş8+8*N8;>888;Î8*ş8;>8şY
¾8ş8î8¾8)>8#Â÷ãÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’ö&6·W2öF÷væÆöB#ãÆÆ&VÃîZèXZz+®Š¨Ş8î8ş8(zêynˆ^898+8:ş8;Î888).XZ^X©³ÂöÆ&VÃãÆ–çWBG—SÒ'77v÷&B"æÖSÒ&FÖ–å÷77v÷&B"&WV—&VBWFö6ö×ÆWFSÒ&7W'&VçB×77v÷&B#à¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&ÖVB"fÇVSÒ'G'VR"&WV—&VCâX¾K«®h8^Z8).Y
¾8(89^8*8*N8:¾88~8nZèXZ8¾KùŞzê8~8î8“ÂöÆ&VÃãÆ'WGFöâ6Æ73Ò'7V66W72#å¤•8988>8*ş8*.88>89~8).KÙÎh‰8;¾888*n8;>8:Ş8;Î88“Âö'WGFöããÂöf÷&Óà¢Æƒ#î8988>8*ş8*.88>89~i[NYh
~z+®Š¨ÓÂöƒ#ãÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’ö&6·W2÷fW&–g’"Væ7G—SÒ&×VÇF—'Böf÷&ÒÖFF#ãÆÆ&VÃîz+®Š¨Ş88(µ¤•89^8*8*N8:³ÂöÆ&VÃãÆ–çWBG—SÒ&f–ÆR"æÖSÒ&&6·Wöf–ÆR"66WCÒ"ç¦—ÆÆ–6F–öâ÷¦—"&WV—&VCãÆ'WGFöâ6Æ73Ò'6V6öæF'’#îzNiŞ8;¾iK8n8)>8).z+®Š¨ÓÂö'WGFöããÂöf÷&Óà¢Æƒ#îX{®X©¾[^jÛCÂöƒ#ãÇF&ÆSãÇG#ãÇFƒîiz^i˜#Â÷FƒãÇFƒîZéşŠÎˆSÂ÷FƒãÇFƒî8:Î8+>8;Î88i[Â÷FƒãÇFƒî[Ú.[ÈóÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îX{®X©¾[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚$dÔ”Å88~8;Î8+şX{®X©²"Â&öG’ÂW6W"  ¤ç÷7B‚"öfÖ–Ç’ö&6·W2öF÷væÆöB"¦FVbfÖ–Ç•ö&6·WöF÷væÆöB†FÖ–å÷77v÷&C¢7G"Òf÷&Ò‚âââ’Â6öæf—&ÖVC¢&ööÂÒf÷&Ò„fÇ6R’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢–bæ÷B6öæf—&ÖVB÷"æ÷B77v÷&G2çfW&–g’†FÖ–å÷77v÷&BÂW6W"ç77v÷&Eö†6‚“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.zêynˆ^898+8:ş8;Î888î8ş8şz+®Š¨Şš^yºî8).z+®Š¨Ş8~8n8ş88^8B"¢÷væW'6†—2Ò6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–B’’æÆÂ‚¢÷væW%ö–G2Ò6÷'FVB‡¶—FVÒçW6W%ö–Bf÷"—FVÒ–â÷væW'6†—7Ò¢÷væW'2Ò6W76–öâç66Æ'2‡6VÆV7B…W6W"’çv†W&R…W6W"æ–Bæ–åò†÷væW%ö–G2’’æ÷&FW%ö'’…W6W"æ–B’’æÆÂ‚’–b÷væW%ö–G2VÇ6RµĞ¢Föw2Ò6W76–öâç66Æ'2‡6VÆV7B„För’çv†W&R„FörçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„Föræ–B’’æÆÂ‚¢Föuö–G2Ò¶Föræ–Bf÷"För–âFöw5Ğ¢÷7G2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒæFöuö–Bæ–åò†Föuö–G2’’æ÷&FW%ö'’„fÖ–Ç”FötÆ'VÔ—FVÒæ–B’’æÆÂ‚’–bFöuö–G2VÇ6RµĞ¢VF—G2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”ÖöFW&F–öäVF—B’çv†W&R„fÖ–Ç”ÖöFW&F–öäVF—BçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç”ÖöFW&F–öäVF—Bæ–B’’æÆÂ‚¢6öç6VçG2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç”6öç6VçB’çv†W&R„fÖ–Ç”6öç6VçBçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç”6öç6VçBæ–B’’æÆÂ‚¢FW&×2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç•FW&×5fW'6–öâ’çv†W&R„fÖ–Ç•FW&×5fW'6–öâçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„fÖ–Ç•FW&×5fW'6–öâæ–B’’æÆÂ‚¢Öæ–fW7BÒ²'66†VÖ÷fW'6–öâ#¢Â'FVæçB#¢&6·WöÖöFVÂ‡FVæçB’Â&W‡÷'FVEöB#¢FFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’æ—6öf÷&ÖB‚’À¢&6÷VçG2#¢²&÷væW'2#¢ÆVâ†÷væW'2’Â&Föw2#¢ÆVâ†Föw2’Â&÷væW'6†—2#¢ÆVâ†÷væW'6†—2’Â'÷7G2#¢ÆVâ‡÷7G2’Â&VF—G2#¢ÆVâ†VF—G2’Â&6öç6VçG2#¢ÆVâ†6öç6VçG2—×Ğ¢÷WGWBÒ–òä'—FW4”ò‚¢v—F‚¦—f–ÆRå¦—f–ÆR†÷WGWBÂ'r"Â¦—f–ÆRå¤•ôDTdÄDTB’2&6†—fS ¢FF6WG2Ò²&÷væW'2æ§6öâ#¢¶&6·WöÖöFVÂ†—FVÒÂ²'77v÷&Eö†6‚'Ò’f÷"—FVÒ–â÷væW'5ÒÂ&Föw2æ§6öâ#¢¶&6·WöÖöFVÂ†—FVÒ’f÷"—FVÒ–âFöw5ÒÀ¢&÷væW'6†—2æ§6öâ#¢¶&6·WöÖöFVÂ†—FVÒ’f÷"—FVÒ–â÷væW'6†—5ÒÂ'÷7G2æ§6öâ#¢¶&6·WöÖöFVÂ†—FVÒ’f÷"—FVÒ–â÷7G5ÒÀ¢&ÖöFW&F–öåöVF—G2æ§6öâ#¢¶&6·WöÖöFVÂ†—FVÒ’f÷"—FVÒ–âVF—G5ÒÂ'FW&×2æ§6öâ#¢¶&6·WöÖöFVÂ†—FVÒ’f÷"—FVÒ–âFW&×5ÒÀ¢&6öç6VçG2æ§6öâ#¢¶&6·WöÖöFVÂ†—FVÒÂ²&—ö†6‚'Ò’f÷"—FVÒ–â6öç6VçG5×Ğ¢6†V6·7V×2Ò·Ğ¢f÷"f–ÆVæÖRÂ&V6÷&G2–âFF6WG2æ—FV×2‚“ ¢6öçFVçBÒ§6öâæGV×2‡&V6÷&G2ÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’æVæ6öFR‚¢&6†—fRçw&—FW7G"†f–ÆVæÖRÂ6öçFVçB“²6†V6·7V×5¶f–ÆVæÖUÒÒ†6†Æ–"ç6†#Sb†6öçFVçB’æ†W†F–vW7B‚¢÷væW%ö77bÒ–òå7G&–æt”ò†æWvÆ–æSÒ""“²w&—FW"Ò77bçw&—FW"†÷væW%ö77b“²w&—FW"çw&—FW&÷r…²'W6W%ö–B"Â&æÖR"Â&VÖ–Â"Â&7F—fR%Ò¢f÷"÷væW"–â÷væW'3¢w&—FW"çw&—FW&÷r…¶÷væW"æ–BÂ÷væW"ææÖRÂ÷væW"æVÖ–ÂÂ÷væW"æ7F—fUÒ¢77eö6öçFVçBÒ‚%ÇVfVfb"²÷væW%ö77bævWGfÇVR‚’’æVæ6öFR‚“²&6†—fRçw&—FW7G"‚&÷væW'2æ77b"Â77eö6öçFVçB¢6†V6·7V×5²&÷væW'2æ77b%ÒÒ†6†Æ–"ç6†#Sb†77eö6öçFVçB’æ†W†F–vW7B‚¢f÷"÷7B–â÷7G3 ¢W‡FVç6–öâÒ'ær"–b÷7Bç†÷Fõö6öçFVçE÷G—RÓÒ&–ÖvR÷ær"VÇ6R‚'vV'"–b÷7Bç†÷Fõö6öçFVçE÷G—RÓÒ&–ÖvR÷vV'"VÇ6R&§r"¢†÷FõöæÖRÒb'†÷F÷2÷÷7B×·÷7Bæ–GÒç¶W‡FVç6–öçÒ#²&6†—fRçw&—FW7G"‡†÷FõöæÖRÂ÷7Bç†÷FõöFF¢6†V6·7V×5·†÷FõöæÖUÒÒ†6†Æ–"ç6†#Sb‡÷7Bç†÷FõöFF’æ†W†F–vW7B‚¢Öæ–fW7E²&6†V6·7V×2%ÒÒ6†V6·7V×0¢&6†—fRçw&—FW7G"‚&Öæ–fW7Bæ§6öâ"Â§6öâæGV×2†Öæ–fW7BÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’¢6÷VçBÒ7VÒ†Öæ–fW7E²&6÷VçG2%ÒçfÇVW2‚’¢6W76–öâæFB„fÖ–Ç”&6·WVF—B‡FVæçEö–C×FVæçBæ–BÂ7&VFVEö'•ö–C×W6W"æ–BÂ&V6÷&Eö6÷VçCÖ6÷VçB’“²6W76–öâæ6öÖÖ—B‚¢f–ÆVæÖRÒb&fÖ–Ç’Ö&6·W×·FVæçBæ–GÒ×¶FFRçFöF’‚’æ—6öf÷&ÖB‚—Òç¦— ¢&WGW&â&W7öç6R†6öçFVçCÖ÷WGWBævWGfÇVR‚’ÂÖVF–÷G—SÒ&Æ–6F–öâ÷¦—"Â†VFW'3×²$6öçFVçBÔF—7÷6—F–öâ#¢bvGF6†ÖVçC²f–ÆVæÖSÒ'¶f–ÆVæÖWÒ"rÂ$66†RÔ6öçG&öÂ#¢&æò×7F÷&R'Ò  ¤ç÷7B‚"öfÖ–Ç’ö&6·W2÷fW&–g’"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦7–æ2FVbfÖ–Ç•ö&6·W÷fW&–g’†&6·Wöf–ÆS¢WÆöDf–ÆRÒf–ÆR‚âââ’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢6öçFVçBÒv—B&6·Wöf–ÆRç&VBƒ¢#B¢#B²¢W'&÷'3¢Æ—7E·7G%ÒÒµĞ¢–bÆVâ†6öçFVçB’â¢#B¢#C ¢W'&÷'2æVæB‚.89^8*8*N8:¾8+^8*N8+®8ÃÔ.8).‹h^88n8N8î8’"¢G'“ ¢v—F‚¦—f–ÆRå¦—f–ÆR†–òä'—FW4”ò†6öçFVçB’’2&6†—fS ¢–æf÷2Ò&6†—fRæ–æföÆ—7B‚¢–bÆVâ†–æf÷2’âS÷"7VÒ†—FVÒæf–ÆU÷6—¦Rf÷"—FVÒ–â–æf÷2’â#B¢#B¢#C ¢W'&÷'2æVæB‚.[^™h¾[èÎ8îZë˜xş8î8ş8ş89^8*8*N8:¾i[8ÎZèXZKˆ®™™8).‹h^88n8N8î8’"¢æÖW2Ò¶—FVÒæf–ÆVæÖRf÷"—FVÒ–â–æf÷7Ğ¢–b&Öæ–fW7Bæ§6öâ"æ÷B–âæÖW3 ¢W'&÷'2æVæB‚&Öæ–fW7Bæ§6öî8Î8.8(®8î8¾8)2"¢VÇ6S ¢Öæ–fW7BÒ§6öâæÆöG2†&6†—fRç&VB‚&Öæ–fW7Bæ§6öâ"’¢–bÖæ–fW7BævWB‚'66†VÖ÷fW'6–öâ"’Ò÷"Öæ–fW7BævWB‚'FVæçB"Â·Ò’ævWB‚&–B"’ÒFVæçBæ–C ¢W'&÷'2æVæB‚.˜h©îKŠŞ8îxªÎˆˆî8î8988>8*ş8*.88>89~8~8ş8.8(®8î8¾8)2"¢6†V6·7V×2ÒÖæ–fW7BævWB‚&6†V6·7V×2"’÷"·Ğ¢–bæ÷B6†V6·7V×3 ¢W'&÷'2æVæB‚.i[NYh
~h8^Z8Î8®8Niz~[Ú.[Èş8î8988>8*ş8*.88>89~8~8’"¢f÷"f–ÆVæÖRÂW‡V7FVB–â6†V6·7V×2æ—FV×2‚“ ¢–bf–ÆVæÖRæ÷B–âæÖW2÷"†6†Æ–"ç6†#Sb†&6†—fRç&VB†f–ÆVæÖR’’æ†W†F–vW7B‚’ÒW‡V7FVC ¢W'&÷'2æVæB†b'¶f–ÆVæÖWŞ8îi[NYh
~8).z+®Š¨Ş8~8Ş8î8¾8)2"¢W†6WB‡¦—f–ÆRä&E¦—f–ÆRÂ§6öâä¥4ôäFV6öFTW'&÷"Â¶W”W'&÷"ÂG—TW'&÷"ÂfÇVTW'&÷"“ ¢W'&÷'2æVæB‚.iÈX«8¤dÔ”Å8988>8*ş8*.88>89u¤•8~8ş8.8(®8î8¾8)2"¢&W7VÇBÒ&f–ÆVB"–bW'&÷'2VÇ6R'7V66W72 ¢&V6÷&Eö÷W&F–öâ‡6W76–öâÂ&&6·W÷fW&–g’"Â&W7VÇBÂ.8988>8*ş8*.88>89~i[NYh
~z+®Š¨Ò"ÂFVæçBæ–BÀ¢"ò"æ¦ö–â†W'&÷'2’–bW'&÷'2VÇ6Rb&f–ÆS×¶&6·Wöf–ÆRæf–ÆVæÖR÷"v&6·Wç¦—wÒ"¢6W76–öâæ6öÖÖ—B‚¢–bW'&÷'3 ¢&öG’ÒsÆƒîi[NYh
~z+®Š¨ŞûÉ®YXşšÎ8.8(£ÂöƒãÇ6Æ73Ò&W'&÷"#âr²‡FÖÂæW66R‚.ûÈò"æ¦ö–â†W'&÷'2’’²sÂ÷âp¢&WGW&â…DÔÅ&W7öç6R†Æ–÷WB‚.8988>8*ş8*.88>89~i[NYh
~z+®Š¨Ò"Â&öG’²sÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö&6·W2öÖævR#îh‹¾8(³ÂöârÂW6W"’Â7FGW5ö6öFSÓC¢&WGW&âÆ–÷WB‚.8988>8*ş8*.88>89~i[NYh
~z+®Š¨Ò"ÂsÆƒîi[NYh
~z+®Š¨ŞûÉ®jÚ>[‹ƒÂöƒãÇîzNiŞ8(NXh^Zë8îiKZH8şjIÎX{®8^8(Î8î8¾8)>8~8~8ş8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö&6·W2öÖævR#îh‹¾8(³ÂöârÂW6W"  ¦FVb&WV—&UöÖö&–ÆU÷W6W"†WF†÷&—¦F–öã¢7G"ÂæöæRÒ†VFW"„æöæR’Â6W76–öã¢6W76–öâÒFWVæG2†F"’’ÓâW6W# ¢–bæ÷BWF†÷&—¦F–öâ÷"æ÷BWF†÷&—¦F–öâç7F'G7v—F‚‚$&V&W""“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Š¨ŞŠ‹Î8Î[ø^Šh8~8’"¢&rÒWF†÷&—¦F–öâç&VÖ÷fW&Vf—‚‚$&V&W""’ç7G&—‚¢Fö¶VâÒ6W76–öâç66Æ"‡6VÆV7B„Öö&–ÆT•Fö¶Vâ’çv†W&R„Öö&–ÆT•Fö¶VâçFö¶Våö†6‚ÓÒFö¶Våö†6‚‡&r’ÂÖö&–ÆT•Fö¶Vâç&Wfö¶VEöBæ—5ò„æöæR’’¢–bæ÷BFö¶Vã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Š¨ŞŠ‹Î888;Î8*ş8;>8ÎxJX«8~8’"¢W‡—&W2ÒFö¶VâæW‡—&W5öB–bFö¶VâæW‡—&W5öBçG¦–æfòVÇ6RFö¶VâæW‡—&W5öBç&WÆ6R‡G¦–æfó×F–ÖW¦öæRçWF2¢–bW‡—&W2ÃÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.Š¨ŞŠ‹Î888;Î8*ş8;>8îiÉş™™8ÎXˆ~8(Î8n8N8î8’"¢W6W"Ò6W76–öâævWB…W6W"ÂFö¶VâçW6W%ö–B¢–bæ÷BW6W"÷"æ÷BW6W"æ7F—fS ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8*.8*¾8*n8;>888).XŠyJ8~8Ş8î8¾8)2"¢Fö¶VâæÆ7E÷W6VEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2“²6W76–öâæ6öÖÖ—B‚¢&WGW&âW6W   ¤ç÷7B‚"ö’÷cöWF‚÷Fö¶Vâ"¦7–æ2FVbÖö&–ÆUöWF…÷Fö¶Vâ‡&WVW7C¢&WVW7BÂ6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–ÆöBÒv—B&WVW7Bæ§6öâ‚¢VÖ–ÂÂ77v÷&BÒæ÷&ÖÆ—¦UöVÖ–Â‡7G"‡–ÆöBævWB‚&VÖ–Â"Â""’’’Â7G"‡–ÆöBævWB‚'77v÷&B"Â""’¢F‡&÷GFÆUö¶W’ÒWF…÷F‡&÷GFÆUö¶W’‡&WVW7BÂ&Öö&–ÆRÖÆöv–â"ÂVÖ–Â¢–bWF…÷F‡&÷GFÆUö&Æö6¶VB‡F‡&÷GFÆUö¶W’Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC#’ÂFWF–ÃÒ.8:Ş8+8*N8;>ŠšnŠÎ8ÎZI®8N8ş8(8^Xˆn[èÎ8¾8(.8nKˆ[ªn8®Ššn8~8ş88^8B"¢W6W"Ò6W76–öâç66Æ"‡6VÆV7B…W6W"’çv†W&R…W6W"æVÖ–ÂÓÒVÖ–ÂÂW6W"æ7F—fRæ—5ò…G'VR’’¢–bæ÷BW6W"÷"æ÷B77v÷&B÷"æ÷B77v÷&G2çfW&–g’‡77v÷&BÂW6W"ç77v÷&Eö†6‚“ ¢WF…÷F‡&÷GFÆUöf–ÇW&R‡F‡&÷GFÆUö¶W’Â6W76–öâ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8:8;Î8:¾8*.888:Î8+8î8ş8ş898+8:ş8;Î888Î˜^8N8î8’"¢WF…÷F‡&÷GFÆU÷7V66W72‡F‡&÷GFÆUö¶W’Â6W76–öâ¢&rÒ6V7&WG2çFö¶Vå÷W&Ç6fRƒC‚¢Fö¶VâÒÖö&–ÆT•Fö¶Vâ‡W6W%ö–C×W6W"æ–BÂFö¶Våö†6ƒ×Fö¶Våö†6‚‡&r’ÂFWf–6UöæÖS×7G"‡–ÆöBævWB‚&FWf–6UöæÖR"Â.8+89î8;Î8889^8*8;2"’•³£Ò÷".8+89î8;Î8889^8*8;2"À¢W‡—&W5öCÖFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’²F–ÖVFVÇF†F—3Ó“’¢6W76–öâæFB‡Fö¶Vâ“²6W76–öâæ6öÖÖ—B‚¢&WGW&â²&66W75÷Fö¶Vâ#¢&rÂ'Fö¶Vå÷G—R#¢&&V&W""Â&W‡—&W5ö–â#¢“¢ƒcCÂ&•÷fW'6–öâ#¢'c'Ğ  ¤ç÷7B‚"ö’÷cöWF‚÷&Wfö¶R"¦FVbÖö&–ÆUöWF…÷&Wfö¶R†WF†÷&—¦F–öã¢7G"ÂæöæRÒ†VFW"„æöæR’ÂW6W#¢W6W"ÒFWVæG2‡&WV—&UöÖö&–ÆU÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&rÒ†WF†÷&—¦F–öâ÷"""’ç&VÖ÷fW&Vf—‚‚$&V&W""’ç7G&—‚¢Fö¶VâÒ6W76–öâç66Æ"‡6VÆV7B„Öö&–ÆT•Fö¶Vâ’çv†W&R„Öö&–ÆT•Fö¶VâçFö¶Våö†6‚ÓÒFö¶Våö†6‚‡&r’ÂÖö&–ÆT•Fö¶VâçW6W%ö–BÓÒW6W"æ–B’¢–bFö¶Vã¢Fö¶Vâç&Wfö¶VEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2“²6W76–öâæ6öÖÖ—B‚¢&WGW&â²&ö²#¢G'VWĞ  ¤ævWB‚"ö’÷cöÖR"¦FVbÖö&–ÆUöÖR‡W6W#¢W6W"ÒFWVæG2‡&WV—&UöÖö&–ÆU÷W6W"’“ ¢&WGW&â²&–B#¢W6W"æ–BÂ&æÖR#¢W6W"ææÖRÂ&VÖ–Â#¢W6W"æVÖ–ÇĞ  ¤ævWB‚"ö’÷cöFöw2"¦FVbÖö&–ÆUöFöw2‡W6W#¢W6W"ÒFWVæG2‡&WV—&UöÖö&–ÆU÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&G2Ò6W76–öâæW†V7WFR‡6VÆV7B„Föt÷væW'6†—ÂFörÂFVæçB’æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’’æ÷&FW%ö'’„Föræ6ÆÅöæÖR’’æÆÂ‚¢&WGW&â²&Föw2#¢·²&–B#¢Föræ–BÂ&6ÆÅöæÖR#¢Föræ6ÆÅöæÖRÂ'&Vv—7FW&VEöæÖR#¢Förç&Vv—7FW&VEöæÖRÂ&'&VVB#¢Föræ'&VVBÂ'6W‚#¢Förç6W‚À¢&&—'F…öFFR#¢Föræ&—'F…öFFRæ—6öf÷&ÖB‚’–bFöræ&—'F…öFFRVÇ6RæöæRÂ&6öÆ÷"#¢Föræ6öÆ÷"Â'&VÆF–öç6†—#¢÷væW'6†—ç&VÆF–öç6†—À¢'FVæçB#¢²&–B#¢FVæçBæ–BÂ&æÖR#¢FVæçBææÖWÒÂ'†÷Fõ÷W&Â#¢b"ö’÷cöFöw2÷¶Föræ–GÒ÷†÷Fò'Òf÷"÷væW'6†—ÂFörÂFVæçB–â&V6÷&G5×Ğ  ¤ævWB‚"ö’÷cöFöw2÷¶Föuö–GÒ÷†÷Fò"¦FVbÖö&–ÆUöFöu÷†÷Fò†Föuö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&UöÖö&–ÆU÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bæ÷B6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R„Föt÷væW'6†—æFöuö–BÓÒFöuö–BÂFöt÷væW'6†—çW6W%ö–BÓÒW6W"æ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöuö–B’¢–bæ÷B&öf–ÆR÷"æ÷B&öf–ÆRç†÷FõöFF¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçC×&öf–ÆRç†÷FõöFFÂÖVF–÷G—S×&öf–ÆRç†÷Fõö6öçFVçE÷G—R÷"&–ÖvRö§Vr"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ævWB‚"ö’÷cöæ÷F–f–6F–öç2"¦FVbÖö&–ÆUöæ÷F–f–6F–öç2‡W6W#¢W6W"ÒFWVæG2‡&WV—&UöÖö&–ÆU÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢—FV×2ÒµĞ¢f÷"6öçfW'6F–öâÂÖW76vR–âfÖ–Ç•÷Vç&VEöÖW76vUö—FV×2‡W6W"Â6W76–öâ“ ¢—FV×2æVæB‡²'G—R#¢&ÖW76vR"Â&–B#¢ÖW76vRæ–BÂ'F—FÆR#¢.ikyØ8:88>8+¾8;Î8+‚"Â&&öG’#¢ÖW76vRæ&öG•³£#ÒÂ&7&VFVEöB#¢ÖW76vRç6VçEöBæ—6öf÷&ÖB‚’Â'W&Â#¢b"öfÖ–Ç’öÖW76vW2÷¶6öçfW'6F–öâæ–GÒ'Ò¢f÷"ææ÷Væ6VÖVçBÂFVæçB–âfÖ–Ç•÷Vç&VEöææ÷Væ6VÖVçG2‡W6W"Â6W76–öâ“ ¢—FV×2æVæB‡²'G—R#¢&ææ÷Væ6VÖVçB"Â&–B#¢ææ÷Væ6VÖVçBæ–BÂ'F—FÆR#¢ææ÷Væ6VÖVçBçF—FÆRÂ&&öG’#¢FVæçBææÖRÂ&7&VFVEöB#¢ææ÷Væ6VÖVçBæ7&VFVEöBæ—6öf÷&ÖB‚’Â'W&Â#¢b"öfÖ–Ç’öææ÷Væ6VÖVçG2÷f–Wr÷¶ææ÷Væ6VÖVçBæ–GÒ'Ò¢—FV×2ç6÷'B†¶W“ÖÆÖ&F—FVÓ¢—FVÕ²&7&VFVEöB%ÒÂ&WfW'6SÕG'VR¢&WGW&â²&æ÷F–f–6F–öç2#¢—FV×5³£×Ğ  ¤ævWB‚"ö’÷c÷F–ÖVÆ–æR"¦FVbÖö&–ÆU÷F–ÖVÆ–æR†Æ–Ö—C¢–çBÒ3Âöfg6WC¢–çBÒÂW6W#¢W6W"ÒFWVæG2‡&WV—&UöÖö&–ÆU÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢Æ–Ö—BÂöfg6WBÒÖ–â†Ö‚†Æ–Ö—BÂ’Â’ÂÖ‚†öfg6WBÂ¢&V6÷&G2Ò6÷'FVB†fÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’çfÇVW2‚’Â¶W“ÖÆÖ&FfÇVS¢fÇVU³Òæ7&VFVEöBÂ&WfW'6SÕG'VR¢vRÒ&V6÷&G5¶öfg6WC¦öfg6WB²Æ–Ö—EĞ¢&WGW&â²&—FV×2#¢·²&–B#¢—FVÒæ–BÂ&För#¢²&–B#¢Föræ–BÂ&6ÆÅöæÖR#¢Föræ6ÆÅöæÖWÒÂ'FVæçB#¢²&–B#¢FVæçBæ–BÂ&æÖR#¢FVæçBææÖWÒÀ¢&6F–öâ#¢—FVÒæ6F–öâÂ'F¶Våööâ#¢—FVÒçF¶Våööâæ—6öf÷&ÖB‚’–b—FVÒçF¶VåööâVÇ6RæöæRÂ'f—6–&–Æ—G’#¢—FVÒçf—6–&–Æ—G’À¢&7&VFVEöB#¢—FVÒæ7&VFVEöBæ—6öf÷&ÖB‚’Â'†÷Fõ÷W&Â#¢b"ö’÷c÷F–ÖVÆ–æR÷¶—FVÒæ–GÒ÷†÷Fò'Òf÷"—FVÒÂFörÂFVæçBÂò–âvUÒÀ¢&Æ–Ö—B#¢Æ–Ö—BÂ&öfg6WB#¢öfg6WBÂ&†5öÖ÷&R#¢öfg6WB²Æ–Ö—BÂÆVâ‡&V6÷&G2—Ğ  ¤ævWB‚"ö’÷c÷F–ÖVÆ–æR÷¶—FVÕö–GÒ÷†÷Fò"¦FVbÖö&–ÆU÷F–ÖVÆ–æU÷†÷Fò†—FVÕö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&UöÖö&–ÆU÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&V6÷&BÒfÖ–Ç•÷F–ÖVÆ–æUö—FV×2‡W6W"Â6W76–öâ’ævWB†—FVÕö–B¢–bæ÷B&V6÷&C¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢—FVÒÒ&V6÷&E³Ğ¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒç†÷FõöFFÂÖVF–÷G—SÖ—FVÒç†÷Fõö6öçFVçE÷G—RÂ†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ævWB‚"öfÖ–Ç’öFWf–6W2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öFWf–6W2‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢Fö¶Vç2Ò6W76–öâç66Æ'2‡6VÆV7B„Öö&–ÆT•Fö¶Vâ’çv†W&R„Öö&–ÆT•Fö¶VâçW6W%ö–BÓÒW6W"æ–B’æ÷&FW%ö'’„Öö&–ÆT•Fö¶Vâæ7&VFVEöBæFW62‚’’’æÆÂ‚¢&÷w2Ò""æ¦ö–â†bsÇG#ãÇFCç¶‡FÖÂæW66R‡Fö¶VâæFWf–6UöæÖR—ÓÂ÷FCãÇFCç·Fö¶Vâæ7&VFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVB"—ÓÂ÷FCãÇFCç·Fö¶VâæÆ7E÷W6VEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–bFö¶VâæÆ7E÷W6VEöBVÇ6R.iÊ®KÛşyJ‚'ÓÂ÷FCãÇFCç².Šz>™šNkˆ8ò"–bFö¶Vâç&Wfö¶VEöBVÇ6R.˜
>i®KŠÒ'ÓÂ÷FCãÇFCç¶b#Æf÷&ÒÖWF†öCÕÂ'÷7EÂ"7F–öãÕÂ"öfÖ–Ç’öFWf–6W2÷·Fö¶Vâæ–GÒ÷&Wfö¶UÂ#ãÆ'WGFöâ6Æ73ÕÂ'6V6öæF'•Â#îŠz>™šCÂö'WGFöããÂöf÷&Óâ"–bæ÷BFö¶Vâç&Wfö¶VEöBVÇ6R.ûÈÒ'ÓÂ÷FCãÂ÷G#ârf÷"Fö¶Vâ–âFö¶Vç2¢&öG’ÒbrrsÆƒî8*.89~8:®8;¾˜	®yú^zºşiÊ³ÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇî[niÚ^8æ”õ>ûÈôæG&ö–N8*.89~8:®8ş8dÔ”Å8YÎ88:8;Î8:¾8*.888:Î8+8;¾898+8:ş8;Î888~˜
>i®8~8î88.zºşiÊ¾8N88³“iz^™i>iÈX«8®[.yJ888;Î8*ş8;>8).y›®ŠÎ8~8898+8:ş8;Î88ˆz®KÙ>8şzºşiÊ¾8KùŞZÙ8~8î8¾8)>8#Â÷ãÂöF—cà¢ÇãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öæ÷F–f–6F–öâ×6WGF–æw2#î89n8:8*n8+n˜	®yú^8).ŠŠŞZé£ÂöãÂ÷ãÆƒ#î8+89î8;Î8889^8*8;>8*.89~8:®˜
>i£Âöƒ#ãÇF&ÆSãÇG#ãÇFƒîzºşiÊ³Â÷FƒãÇFƒî˜
>i®izSÂ÷FƒãÇFƒîiÈ{X.XŠyJƒÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#R#î8*.89~8:®˜
>i®zºşiÊ¾8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.8*.89~8:®8;¾zºşiÊ¾ûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ç÷7B‚"öfÖ–Ç’öFWf–6W2÷·Fö¶Våö–GÒ÷&Wfö¶R"¦FVbfÖ–Ç•öFWf–6U÷&Wfö¶R‡Fö¶Våö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢Fö¶VâÒ6W76–öâç66Æ"‡6VÆV7B„Öö&–ÆT•Fö¶Vâ’çv†W&R„Öö&–ÆT•Fö¶Vâæ–BÓÒFö¶Våö–BÂÖö&–ÆT•Fö¶VâçW6W%ö–BÓÒW6W"æ–B’¢–bæ÷BFö¶Vã¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢Fö¶Vâç&Wfö¶VEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2“²6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’öFWf–6W2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’÷&VÆF—fW2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•÷&VÆF—fW5÷vR‡W6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢ÖF6†W2ÒfÖ–Ç•÷&VÆF—fUöÖF6†W2‡W6W"Â6W76–öâ¢Æ—GFW%ö6&G2Â&VÆF—fUö6&G2Ò""Â" ¢f÷"òÂw&÷WÂÆ&VÂÂFörÂ&öf–ÆR–â6÷'FVB†ÖF6†W2çfÇVW2‚’Â¶W“ÖÆÖ&FfÇVS¢‡fÇVU³ÒÂfÇVU³5Òæ6ÆÅöæÖR’“ ¢÷væW%öæÖRÒ&öf–ÆRææ–6¶æÖR–b&öf–ÆRç6†÷uöæ–6¶æÖRæB&öf–ÆRææ–6¶æÖRVÇ6R$dÔ”Å8:8;>898;Â ¢fÖ–Ç•÷&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöræ–B’¢Föu÷†÷FòÒbsÆ–Ör6Æ73Ò&fÖ–Ç’ÖFör×F‡VÖ""7&3Ò"öfÖ–Ç’÷&VÆF—fW2öFöw2÷¶Föræ–GÒ÷†÷Fò"ÇCÒ'¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—Ò#âr–bfÖ–Ç•÷&öf–ÆRæBfÖ–Ç•÷&öf–ÆRç†÷FõöFFVÇ6Rrp¢Æ'VÕö—FV×2Ò6W76–öâç66Æ'2€¢6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒæFöuö–BÓÒFöræ–BÂfÖ–Ç”FötÆ'VÔ—FVÒçf—6–&–Æ—G’æ–åò…²'&VÆF—fW2"Â&fÖ–Ç’%Ò’¢æ÷&FW%ö'’„fÖ–Ç”FötÆ'VÔ—FVÒçF¶VåööâæFW62‚’ÂfÖ–Ç”FötÆ'VÔ—FVÒæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ2¢’æÆÂ‚¢6†&VE÷†÷F÷2Ò""æ¦ö–â€¢bsÆ‡&VcÒ"öfÖ–Ç’÷&VÆF—fW2öÆ'VÒ÷¶—FVÒæ–GÒ÷†÷Fò"F&vWCÒ%ö&Ææ²#ãÆ–Ör7&3Ò"öfÖ–Ç’÷&VÆF—fW2öÆ'VÒ÷¶—FVÒæ–GÒ÷†÷Fò"ÇCÒ.X[iÈXiyÉò"7G–ÆSÒ'v–GFƒ£sgƒ¶†V–v‡C£sgƒ¶ö&¦V7BÖf—C¦6öçF–ã¶&6¶w&÷VæC¢6cvVFVc¶&÷&FW"×&F—W3£—‚#ãÂöârf÷"—FVÒ–âÆ'VÕö—FV×0¢¢6&BÒbrrsÆ'F–6ÆR6Æ73Ò&ÖöGVÆR#ç¶Föu÷†÷F÷ÓÆƒ3ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöƒ3ãÇç¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ÓÂ÷à¢ÇãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R†Æ&VÂ—ÓÂ÷7ããÂ÷ãÇç¶‡FÖÂæW66R†Föræ'&VVB÷".xªÎzŠîiÊ®y›¾˜Ë""—ÒûÈò¶‡FÖÂæW66R†Föræ6öÆ÷"÷".jù¾ˆ›.iÊ®y›¾˜Ë""—ÓÂ÷à¢Çî8*®8;Î88®8;ÎûÉ£Æ‡&VcÒ"öfÖ–Ç’öÖVÖ&W'2÷·&öf–ÆRçV&Æ–5ö–GÒ#ç¶‡FÖÂæW66R†÷væW%öæÖR—ÓÂöãÂ÷ç¶bsÆF—b7G–ÆSÒ&F—7Æ“¦fÆWƒ¶v£wƒ¶Ö&v–â×F÷£'‚#ç·6†&VE÷†÷F÷7ÓÂöF—câr–b6†&VE÷†÷F÷2VÇ6RrwÓÂö'F–6ÆSârrp¢–bw&÷WÓÒ&Æ—GFW"# ¢Æ—GFW%ö6&G2³Ò6&@¢VÇ6S ¢&VÆF—fUö6&G2³Ò6&@¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’#ädÔ”Å89¾8;Î8:8h‹¾8(³ÂöãÆƒîXXN[Éş8;¾Šj®h‰®xªÎ88î8N8®8Î8(£Âöƒà¢Çîy›¾˜Ë.8^8(Î8şŠ{[88~8;Î8+ş8¾8(™j.Kø.8).ˆz®X¹^XŠNZé®8~8XZÎ™h¾8¾YÎhHş8~8ş8*®8;Î88®8;Îjy8hI¾xªÎ888).ŠzK®8~8î88#Â÷à¢Æƒ#îYÎˆ[XXN[ÉóÂöƒ#ãÆF—b6Æ73Ò&w&–B#ç¶Æ—GFW%ö6&G2÷"sÇîxûîYÊ8XZÎ™h¾KŠŞ8îYÎˆ[XXN[Éş8ş8N8î8¾8)>8#Â÷âwÓÂöF—cà¢Æƒ#îŠj®h‰®xªÃÂöƒ#ãÆF—b6Æ73Ò&w&–B#ç·&VÆF—fUö6&G2÷"sÇîxûîYÊ8XZÎ™h¾KŠŞ8îŠj®h‰®xªÎ8ş8N8î8¾8)>8#Â÷âwÓÂöF—cà¢ÇãÇ6ÖÆÃîŠ{[i»8¾x‹nxªÎ8;¾jøŞxªÎ8;¾XXzYn8ÎjÚ>8~8şy›¾˜Ë.8^8(Î8n8N8(¾8¾888(8(®jÚ>z+®8¾XŠNZé®8~8Ş8î88#Â÷6ÖÆÃãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.XXN[Éş8;¾Šj®h‰®xªÎûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’÷&VÆF—fW2öFöw2÷¶Föuö–GÒ÷†÷Fò"¦FVbfÖ–Ç•÷&VÆF—fUöFöu÷†÷Fò†Föuö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–bFöuö–Bæ÷B–âfÖ–Ç•÷&VÆF—fUöÖF6†W2‡W6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”Föu&öf–ÆR’çv†W&R„fÖ–Ç”Föu&öf–ÆRæFöuö–BÓÒFöuö–B’¢–bæ÷B&öf–ÆR÷"æ÷B&öf–ÆRç†÷FõöFF ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçC×&öf–ÆRç†÷FõöFFÂÖVF–÷G—S×&öf–ÆRç†÷Fõö6öçFVçE÷G—R÷"&–ÖvRö§Vr"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ævWB‚"öfÖ–Ç’÷&VÆF—fW2öÆ'VÒ÷¶—FVÕö–GÒ÷†÷Fò"¦FVbfÖ–Ç•÷&VÆF—fUöÆ'VÕ÷†÷Fò†—FVÕö–C¢–çBÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢—FVÒÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”FötÆ'VÔ—FVÒ’çv†W&R„fÖ–Ç”FötÆ'VÔ—FVÒæ–BÓÒ—FVÕö–BÂfÖ–Ç”FötÆ'VÔ—FVÒçf—6–&–Æ—G’æ–åò…²'&VÆF—fW2"Â&fÖ–Ç’%Ò’’¢–bæ÷B—FVÒ÷"—FVÒæFöuö–Bæ÷B–âfÖ–Ç•÷&VÆF—fUöÖF6†W2‡W6W"Â6W76–öâ“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçCÖ—FVÒç†÷FõöFFÂÖVF–÷G—SÖ—FVÒç†÷Fõö6öçFVçE÷G—RÂ†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¤ævWB‚"öfÖ–Ç’öÖVÖ&W'2÷·V&Æ–5ö–GÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•öÖVÖ&W%öFWF–Â‡V&Æ–5ö–C¢7G"ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçV&Æ–5ö–BÓÒV&Æ–5ö–BÂ÷væW%&öf–ÆRç&öf–ÆU÷V&Æ–2æ—5ò…G'VR’’¢–bæ÷B&öf–ÆS ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚.™ÙîXZÎ™h¾89~8:Ş89^8*>8;Î8:²"ÂsÆƒî89~8:Ş89^8*>8;Î8:¾8ş™ÙîXZÎ™h¾8~8“ÂöƒãÇîxûîYÊ88>8î89~8:Ş89^8*>8;Î8:¾8şXZÎ™h¾8^8(Î8n8N8î8¾8)>8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö¶VææVÂ#îxªÎˆˆädÔ”ÅKÉ®8h‹¾8(³ÂöârÂW6W"Â6W76–öâ’Â7FGW5ö6öFSÓCB¢F—FÆRÒ&öf–ÆRææ–6¶æÖR–b&öf–ÆRç6†÷uöæ–6¶æÖRæB&öf–ÆRææ–6¶æÖRVÇ6R$dÔ”Å8:8;>898;Â ¢†÷FòÒbsÆ–Ör7&3Ò"öfÖ–Ç’öÖVÖ&W'2÷·&öf–ÆRçV&Æ–5ö–GÒ÷†÷Fò"ÇCÒ.89~8:Ş89^8*>8;Î8:¾XiyÉò"7G–ÆSÒ'v–GFƒ£ƒƒ¶†V–v‡C£ƒƒ¶ö&¦V7BÖf—C¦6÷fW#¶&÷&FW"×&F—W3£SS¶&÷&FW#£W‚6öÆ–B6VCCR#âr–b&öf–ÆRç6†÷u÷†÷FòæB&öf–ÆRç†÷FõöFFVÇ6R" ¢&VfV7GW&RÒbsÇãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R‡&öf–ÆRç&VfV7GW&R—ÓÂ÷7ããÂ÷âr–b&öf–ÆRç6†÷u÷&VfV7GW&RæB&öf–ÆRç&VfV7GW&RVÇ6R" ¢&–òÒbsÆF—b6Æ73Ò'FVæçB"7G–ÆSÒ'v†—FR×76S§&R×w&#ç¶‡FÖÂæW66R‡&öf–ÆRæ&–ò—ÓÂöF—câr–b&öf–ÆRç6†÷uö&–òæB&öf–ÆRæ&–òVÇ6R" ¢–ç7Fw&ÒÒbrrsÇãÆ6Æ73Ò&'WGFöâ"‡&VcÒ&‡GG3¢ò÷wwræ–ç7Fw&Òæ6öÒ÷¶‡FÖÂæW66R‡&öf–ÆRæ–ç7Fw&Õ÷W6W&æÖR—Òò"F&vWCÒ%ö&Ææ²"&VÃÒ&æö÷VæW"æ÷&VfW'&W"#ä–ç7Fw&Ò¶‡FÖÂæW66R‡&öf–ÆRæ–ç7Fw&Õ÷W6W&æÖR—Ò8).Šh¾8(²(isÂöãÂ÷ârrr–b&öf–ÆRç6†÷uö–ç7Fw&ÒæB&öf–ÆRæ–ç7Fw&Õ÷W6W&æÖRVÇ6R" ¢ÖW76vUö'WGFöâÒ" ¢F&vWE÷W6W"Ò6W76–öâævWB…W6W"Â&öf–ÆRçW6W%ö–B¢–b&öf–ÆRçW6W%ö–BÒW6W"æ–BæBF&vWE÷W6W"æBfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ’bfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡F&vWE÷W6W"Â6W76–öâ“ ¢6öÖÖöå÷FVæçBÒÖ–â†fÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡W6W"Â6W76–öâ’bfÖ–Ç•ö¶VææVÅ÷FVæçEö–G2‡F&vWE÷W6W"Â6W76–öâ’¢ÖW76vUö'WGFöâÒbrrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’öÖW76vW2÷7F'B÷·&öf–ÆRçV&Æ–5ö–GÒ#ãÆ'WGFöãî8:88>8+¾8;Î8+8).˜8(³Âö'WGFöããÂöf÷&ÓãÇãÆ‡&VcÒ"öfÖ–Ç’÷6fWG’÷&W÷'C÷F&vWE÷G—S×&öf–ÆRf×·F&vWEö–C×·&öf–ÆRçW6W%ö–GÒf×·FVæçEö–C×¶6öÖÖöå÷FVæçGÒ#ãÇ6ÖÆÃî8>8î89~8:Ş89^8*>8;Î8:¾8).xªÎˆˆî8˜	®ZÂ÷6ÖÆÃãÂöãÂ÷ârrp¢Föw5÷6V7F–öâÒ" ¢&V6÷&G2ÒµĞ¢–b&öf–ÆRç6†÷uöFöw3 ¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFörÂFVæçB’æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒ&öf–ÆRçW6W%ö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’ÂFVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢Föuö6&G2Ò" ¢f÷"÷væW'6†—ÂFörÂFVæçB–â&V6÷&G3 ¢6W‚Ò²&ÖÆR#¢.xš"Â&fVÖÆR#¢.x™Ò'ÒævWB†Förç6W‚ÂFörç6W‚¢&VÆF–öâÒ.K‹¾8*®8;Î88®8;Â"–b÷væW'6†—ç&VÆF–öç6†—ÓÒ'&–Ö'’"VÇ6R.8NZënixò ¢&VçEö‡FÖÂÒ" ¢–b&öf–ÆRç6†÷u÷&VçG3 ¢&VçEö6&G2Ò" ¢f÷"Æ&VÂÂ&VçEö–B–â‚‚.x‹nxªÂ"ÂFörç6—&Uö–B’Â‚.jøŞxªÂ"ÂFöræFÕö–B’“ ¢&VçBÒ6W76–öâævWB„FörÂ&VçEö–B’–b&VçEö–BVÇ6RæöæP¢–b&VçBæB&VçBçFVæçEö–BÓÒFörçFVæçEö–C ¢&VçEöæÖRÒ&VçBç&Vv—7FW&VEöæÖR÷"&VçBæ6ÆÅöæÖP¢&VçEö6&G2³ÒbrrsÆF—b6Æ73Ò'FVæçB"7G–ÆSÒ&Ö&v–ã£#ãÇ7G&öæsç¶Æ&VÇÓÂ÷7G&öæsãÇç¶‡FÖÂæW66R‡&VçEöæÖR—ÓÂ÷à¢Çç·F—FÆUöÖ&·2‡&VçBçF—FÆW2’÷".z{Xû~8®8r'ÓÂ÷ãÇãÇ6ÖÆÃîjù¾ˆ›.ûÉ§¶‡FÖÂæW66R‡&VçBæ6öÆ÷"÷".iÊ®y›¾˜Ë""—ÓÂ÷6ÖÆÃãÂ÷ãÂöF—cârrp¢VÇ6S ¢&VçEö6&G2³ÒbsÆF—b6Æ73Ò'FVæçB"7G–ÆSÒ&Ö&v–ã£#ãÇ7G&öæsç¶Æ&VÇÓÂ÷7G&öæsãÇîiÊ®y›¾˜Ë#Â÷ãÂöF—câp¢&VçEö‡FÖÂÒbsÆƒ27G–ÆSÒ&Ö&v–â×F÷£‡‚#îx‹njøÓÂöƒ3ãÆF—b6Æ73Ò&w&–B#ç·&VçEö6&G7ÓÂöF—câp¢Föuö6&G2³ÒbrrsÇ6V7F–öâ6Æ73Ò'FVæçB#ãÇãÇ7â6Æ73Ò&&FvR#ç·&VÆF–öçÓÂ÷7ãâÇ6ÖÆÃç¶‡FÖÂæW66R‡FVæçBææÖR—ÓÂ÷6ÖÆÃãÂ÷à¢Æƒ"7G–ÆSÒ&Ö&v–â×F÷£‡‚#ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöƒ#ãÇç¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ÓÂ÷à¢Çç·F—FÆUöÖ&·2†FörçF—FÆW2’÷".z{Xû~8®8r'ÓÂ÷ãÇç¶‡FÖÂæW66R†Föræ'&VVB÷".xªÎzŠîiÊ®y›¾˜Ë""—ÒûÈò¶‡FÖÂæW66R‡6W‚—ÒûÈò¶‡FÖÂæW66R†Föræ6öÆ÷"÷".jù¾ˆ›.iÊ®y›¾˜Ë""—ÓÂ÷ç·&VçEö‡FÖÇÓÂ÷6V7F–öãârrp¢Föw5÷6V7F–öâÒbsÆƒ#îhI¾xªÃÂöƒ#ç¶Föuö6&G2÷"#ÇîXZÎ™h¾8~8Ş8(¾hI¾xªÎ8ş8î8y›¾˜Ë.8^8(Î8n8N8î8¾8)>8#Â÷â'Òp¢&VÆF—fW5÷6V7F–öâÒ" ¢–b&öf–ÆRç6†÷uöFöw2æB&öf–ÆRç6†÷u÷&VÆF—fW2æB&V6÷&G3 ¢6÷W&6UöFöw2Ò¶Föræ–C¢Förf÷"òÂFörÂò–â&V6÷&G7Ğ¢6æF–FFW2Ò6W76–öâæW†V7WFR€¢6VÆV7B„FörÂ÷væW%&öf–ÆR’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B¢æ¦ö–â„÷væW%&öf–ÆRÂ÷væW%&öf–ÆRçW6W%ö–BÓÒFöt÷væW'6†—çW6W%ö–B’æ¦ö–â…FVæçBÂFVæçBæ–BÓÒFöt÷væW'6†—çFVæçEö–B¢çv†W&R„Föt÷væW'6†—æ7F—fRæ—5ò…G'VR’ÂFöræ7F—fRæ—5ò…G'VR’Â÷væW%&öf–ÆRç&öf–ÆU÷V&Æ–2æ—5ò…G'VR’À¢÷væW%&öf–ÆRç6†÷uöFöw2æ—5ò…G'VR’Â÷væW%&öf–ÆRæ–BÒ&öf–ÆRæ–BÂFVæçBæ7F—fRæ—5ò…G'VR’ÂFVæçBæFVÆWFVBæ—5ò„fÇ6R’¢æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢ÖF6†W3¢F–7E¶–çBÂGWÆU¶–çBÂ7G"Â7G"ÂFörÂ÷væW%&öf–ÆUÕÒÒ·Ğ¢f÷"6æF–FFRÂ6æF–FFU÷&öf–ÆR–â6æF–FFW3 ¢–b6æF–FFRæ–B–â6÷W&6UöFöw3 ¢6öçF–çVP¢f÷"6÷W&6R–â6÷W&6UöFöw2çfÇVW2‚“ ¢&VÆF–öç6†—ÒfÖ–Ç•÷&VÆF–öç6†—‡6W76–öâÂ6÷W&6RÂ6æF–FFR¢–bæ÷B&VÆF–öç6†— ¢6öçF–çVP¢w&÷WÂÆ&VÂÒ&VÆF–öç6†— ¢&–÷&—G’Ò–bw&÷WÓÒ&Æ—GFW""VÇ6R¢7W'&VçBÒÖF6†W2ævWB†6æF–FFRæ–B¢–bæ÷B7W'&VçB÷"&–÷&—G’Â7W'&VçE³Ó ¢ÖF6†W5¶6æF–FFRæ–EÒÒ‡&–÷&—G’Âw&÷WÂb'·6÷W&6Ræ6ÆÅöæÖWŞ8‡¶Æ&VÇÒ"Â6æF–FFRÂ6æF–FFU÷&öf–ÆR¢Æ—GFW%ö6&G2Â&VÆF—fUö6&G2Ò""Â" ¢f÷"òÂw&÷WÂÆ&VÂÂFörÂ6æF–FFU÷&öf–ÆR–â6÷'FVB†ÖF6†W2çfÇVW2‚’Â¶W“ÖÆÖ&FfÇVS¢‡fÇVU³ÒÂfÇVU³5Òæ6ÆÅöæÖR’“ ¢ÖVÖ&W%öæÖRÒ6æF–FFU÷&öf–ÆRææ–6¶æÖR–b6æF–FFU÷&öf–ÆRç6†÷uöæ–6¶æÖRæB6æF–FFU÷&öf–ÆRææ–6¶æÖRVÇ6R$dÔ”Å8:8;>898;Â ¢6&BÒbrrsÆ6Æ73Ò&ÖöGVÆR"‡&VcÒ"öfÖ–Ç’öÖVÖ&W'2÷¶6æF–FFU÷&öf–ÆRçV&Æ–5ö–GÒ#ãÆƒ3ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöƒ3à¢Çç¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ÓÂ÷ãÇãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R†Æ&VÂ—ÓÂ÷7ããÂ÷à¢Çç¶‡FÖÂæW66R†Föræ'&VVB÷".xªÎzŠîiÊ®y›¾˜Ë""—ÒûÈò¶‡FÖÂæW66R†Föræ6öÆ÷"÷".jù¾ˆ›.iÊ®y›¾˜Ë""—ÓÂ÷ãÇî8*®8;Î88®8;ÎûÉ§¶‡FÖÂæW66R†ÖVÖ&W%öæÖR—ÓÂ÷ãÂöârrp¢–bw&÷WÓÒ&Æ—GFW"# ¢Æ—GFW%ö6&G2³Ò6&@¢VÇ6S ¢&VÆF—fUö6&G2³Ò6&@¢–bÆ—GFW%ö6&G2÷"&VÆF—fUö6&G3 ¢&VÆF—fW5÷6V7F–öâÒbrrsÆƒ#îYÎˆ[XXN[Éş8;¾Šj®h‰®xªÃÂöƒ#à¢¶bsÆƒ3îYÎˆ[XXN[ÉóÂöƒ3ãÆF—b6Æ73Ò&w&–B#ç¶Æ—GFW%ö6&G7ÓÂöF—câr–bÆ—GFW%ö6&G2VÇ6RrwĞ¢¶bsÆƒ3îŠj®h‰®xªÃÂöƒ3ãÆF—b6Æ73Ò&w&–B#ç·&VÆF—fUö6&G7ÓÂöF—câr–b&VÆF—fUö6&G2VÇ6RrwÒrrp¢VÇ6S ¢&VÆF—fW5÷6V7F–öâÒsÆƒ#îYÎˆ[XXN[Éş8;¾Šj®h‰®xªÃÂöƒ#ãÇîxûîYÊ8XZÎ™h¾KŠŞ8ädÔ”Å8:8;>898;Î8¾8şŠ›.[Ù>88(¾xªÎ8Î8N8î8¾8)>8#Â÷âp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö¶VææVÂ#îxªÎˆˆädÔ”ÅKÉ®8h‹¾8(³ÂöãÆƒç¶‡FÖÂæW66R‡F—FÆR—ÓÂöƒç·†÷F÷×·&VfV7GW&W×¶–ç7Fw&××¶ÖW76vUö'WGFöç×¶&–÷×¶Föw5÷6V7F–öç×·&VÆF—fW5÷6V7F–öçĞ¢ÇãÇ6ÖÆÃî8>8î89®8;Î8+8¾8ş88NiÊÎK«®8ÎXZÎ™h¾8).Š‹Xúş8~8şš^yºî888).ŠzK®8~8n8N8î88#Â÷6ÖÆÃãÂ÷ârrp¢&WGW&âfÖ–Ç•öÆ–÷WB†b'·F—FÆWŞûÙÄdÔ”Å’"Â&öG’ÂW6W"Â6W76–öâ  ¤ævWB‚"öfÖ–Ç’öÖVÖ&W'2÷·V&Æ–5ö–GÒ÷†÷Fò"¦FVbfÖ–Ç•öÖVÖ&W%÷†÷Fò‡V&Æ–5ö–C¢7G"ÂW6W#¢W6W"ÒFWVæG2‡&WV—&U÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢&öf–ÆRÒ6W76–öâç66Æ"‡6VÆV7B„÷væW%&öf–ÆR’çv†W&R„÷væW%&öf–ÆRçV&Æ–5ö–BÓÒV&Æ–5ö–BÂ÷væW%&öf–ÆRç&öf–ÆU÷V&Æ–2æ—5ò…G'VR’Â÷væW%&öf–ÆRç6†÷u÷†÷Fòæ—5ò…G'VR’’¢–bæ÷B&öf–ÆR÷"æ÷B&öf–ÆRç†÷FõöFF ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&WGW&â&W7öç6R†6öçFVçC×&öf–ÆRç†÷FõöFFÂÖVF–÷G—S×&öf–ÆRç†÷Fõö6öçFVçE÷G—R÷"&–ÖvRö§Vr"Â†VFW'3×²$66†RÔ6öçG&öÂ#¢'&—fFRÂÖ‚ÖvSÓ3'Ò  ¦FVb7F—fUö÷væW%ö–çf—FF–öâ‡&u÷Fö¶Vã¢7G"Â6W76–öã¢6W76–öâ’Óâ÷væW$–çf—FF–öâÂæöæS ¢–çf—FF–öâÒ6W76–öâç66Æ"‡6VÆV7B„÷væW$–çf—FF–öâ’çv†W&R„÷væW$–çf—FF–öâçFö¶Våö†6‚ÓÒFö¶Våö†6‚‡&u÷Fö¶Vâ’’¢–bæ÷B–çf—FF–öâ÷"–çf—FF–öâæ66WFVEöB÷"–çf—FF–öâç&Wfö¶VEöC ¢&WGW&âæöæP¢W‡—&W2Ò–çf—FF–öâæW‡—&W5öB–b–çf—FF–öâæW‡—&W5öBçG¦–æfòVÇ6R–çf—FF–öâæW‡—&W5öBç&WÆ6R‡G¦–æfó×F–ÖW¦öæRçWF2¢&WGW&â–çf—FF–öâ–bW‡—&W2âFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’VÇ6RæöæP  ¦FVb÷væW%ö–çf—FF–öåöFÖ–åö&öG’‡W6W#¢W6W"ÂFVæçC¢FVæçBÂ6W76–öã¢6W76–öâÂ–çf—FU÷W&Ã¢7G"Ò""Â–çf—FUöVÖ–Ã¢7G"Ò""’Óâ7G# ¢Föw2Ò6W76–öâç66Æ'2€¢6VÆV7B„För’çv†W&R„FörçFVæçEö–BÓÒFVæçBæ–BÂFöræ7F—fRæ—5ò…G'VR’ÂFöræ6FVv÷'’Ò&W‡FW&æÂ"’æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢Föuö÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶Föræ–GÒ#ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ŞûÈ‡¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ŞûÈ“Âö÷F–öãârf÷"För–âFöw2¢vVæW&FVBÒ" ¢–b–çf—FU÷W&Ã ¢7V&¦V7BÒV÷FR†b.8	·FVæçBææÖWŞ8	8*®8;Î88®8;Îy›¾˜Ë.8î8NjXhR"¢ÖW76vRÒV÷FR†b'·FVæçBææÖWŞ8¾8(8*®8;Î88®8;Îy›¾˜Ë.8î8NjXh^8~88%ÆåÆîKº^Kˆ¾8î[.yJ…U$Î8).™h¾8Ş8y›¾˜Ë.8).ZèÎK¨n8~8n8ş88^8N8%Æç¶–çf—FU÷W&ÇÕÆåÆî8>8åU$Î8ó~iz^™i>8;³Y¹î8î8şXŠyJ8~8Ş8î88""¢Ö–ÇFòÒb&Ö–ÇFó§·V÷FR†–çf—FUöVÖ–Â—Ó÷7V&¦V7C×·7V&¦V7GÒf&öG“×¶ÖW76vWÒ ¢vVæW&FVBÒbrrsÆF—b6Æ73Ò'FVæçB#ãÆƒ#îh¹¾[èUU$Î8).y›®ŠÎ8~8î8~8óÂöƒ#ãÇî8>8åU$Î8ó~iz^™i>8;³Y¹î8î8şXŠyJ8~8Ş8î88#Â÷à¢Æ–çWB–CÒ&–çf—FR×W&Â"&VFöæÇ’fÇVSÒ'¶‡FÖÂæW66R†–çf—FU÷W&Â—Ò#ãÆ'WGFöâG—SÒ&'WGFöâ"öæ6Æ–6³Ò&æf–vF÷"æ6Æ—&ö&Bçw&—FUFW‡B†Fö7VÖVçBævWDVÆVÖVçD'”–B‚v–çf—FR×W&Âr’çfÇVR“·F†—2çFW‡D6öçFVçCÒ~8+>89N8;Î8~8î8~8òr#åU$Î8).8+>89N8;ÃÂö'WGFöãà¢Æ6Æ73Ò&'WGFöâ7V66W72"‡&VcÒ'¶‡FÖÂæW66R†Ö–ÇFò—Ò#î8:8;Î8:¾8*.89~8:®8~y›¾˜Ë.jXh^8).˜8(³ÂöãÇãÇ6ÖÆÃî8:8;Î8:¾8*.89~8:®8Î™h¾8N8ş8(8Xh^Zë8).z+®Š¨Ş8~8n˜Kú8~8n8ş88^8N8#Â÷6ÖÆÃãÂ÷ãÂöF—cârrp¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„÷væW$–çf—FF–öâÂFör’æ¦ö–â„FörÂFöræ–BÓÒ÷væW$–çf—FF–öâæFöuö–B¢çv†W&R„÷væW$–çf—FF–öâçFVæçEö–BÓÒFVæçBæ–B’æ÷&FW%ö'’„÷væW$–çf—FF–öâæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ¢’æÆÂ‚¢&÷w2Ò" ¢æ÷rÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢f÷"–çf—FF–öâÂFör–â&V6÷&G3 ¢W‡—&W2Ò–çf—FF–öâæW‡—&W5öB–b–çf—FF–öâæW‡—&W5öBçG¦–æfòVÇ6R–çf—FF–öâæW‡—&W5öBç&WÆ6R‡G¦–æfó×F–ÖW¦öæRçWF2¢–b–çf—FF–öâæ66WFVEöC ¢7FFRÒ.y›¾˜Ë.ZèÎK¨b ¢VÆ–b–çf—FF–öâç&Wfö¶VEöC ¢7FFRÒ.Xùnkhkˆ8ò ¢VÆ–bW‡—&W2ÃÒæ÷s ¢7FFRÒ.iÉş™™Xˆ~8(Â ¢VÇ6S ¢7FFRÒ.h¹¾[è^KŠÒ ¢&VÆF–öâÒ.K‹¾8*®8;Î88®8;Â"–b–çf—FF–öâç&VÆF–öç6†—ÓÒ'&–Ö'’"VÇ6R.8NZënixò ¢7F–öâÒbsÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’ö–çf—FF–öç2÷¶–çf—FF–öâæ–GÒ÷&Wfö¶R#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#îXùn8(®kh8“Âö'WGFöããÂöf÷&Óâr–b7FFRÓÒ.h¹¾[è^KŠÒ"VÇ6R.ûÈÒ ¢&÷w2³ÒbsÇG#ãÇFCç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†–çf—FF–öâæVÖ–Â—ÓÂ÷FCãÇFCç·&VÆF–öçÓÂ÷FCãÇFCç·7FFWÓÂ÷FCãÇFCç¶W‡—&W2æFFR‚—ÓÂ÷FCãÇFCç¶7F–öçÓÂ÷FCãÂ÷G#âp¢&WGW&âbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö÷væW'2#î8*®8;Î88®8;Î˜
>i®8h‹¾8(³ÂöãÆƒç¶‡FÖÂæW66R‡FVæçBææÖR—Ò8*®8;Î88®8;Îh¹¾[èSÂöƒà¢ÇîxªÎ88*®8;Î88®8;Îjy8).˜8>8[.yJ8îy›¾˜Ë.jXh^8).y›®ŠÎ8~8î88#Â÷ç¶vVæW&FVGĞ¢Æf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃîxªÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ&Föuö–B"&WV—&VCç¶Föuö÷F–öç7ÓÂ÷6VÆV7Cà¢ÆÆ&VÃîh¹¾[è^88(¾8:8;Î8:¾8*.888:Î8+“ÂöÆ&VÃãÆ–çWBæÖSÒ&VÖ–Â"G—SÒ&VÖ–Â"&WV—&VCà¢ÆÆ&VÃî™j.Kø#ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&VÆF–öç6†—#ãÆ÷F–öâfÇVSÒ'&–Ö'’#îK‹¾8*®8;Î88®8;ÃÂö÷F–öããÆ÷F–öâfÇVSÒ&fÖ–Ç’#î8NZënixóÂö÷F–öããÂ÷6VÆV7Cà¢Æ'WGFöãîiÉş™™K¹8Şh¹¾[èUU$Î8).y›®ŠÃÂö'WGFöããÂöf÷&ÓãÆƒ#îh¹¾[è^[^jÛCÂöƒ#à¢ÇF&ÆSãÇG#ãÇFƒîxªÃÂ÷FƒãÇFƒî8:8;Î8:³Â÷FƒãÇFƒî™j.Kø#Â÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîiÉş™™Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#b#îh¹¾[è^[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp  ¤ævWB‚"öfÖ–Ç’ö–çf—FF–öç2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö–çf—FF–öç2†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢&WGW&âÆ–÷WB‚.8*®8;Î88®8;Îh¹¾[èR"Â÷væW%ö–çf—FF–öåöFÖ–åö&öG’‡W6W"ÂFVæçBÂ6W76–öâ’ÂW6W"  ¤ç÷7B‚"öfÖ–Ç’ö–çf—FF–öç2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö–çf—FF–öåö7&VFR‡&WVW7C¢&WVW7BÂFöuö–C¢–çBÒf÷&Ò‚âââ’ÂVÖ–Ã¢7G"Òf÷&Ò‚âââ’Â&VÆF–öç6†—¢7G"Òf÷&Ò‚'&–Ö'’"’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢–b&VÆF–öç6†—æ÷B–â²'&–Ö'’"Â&fÖ–Ç’'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.™j.Kø.8îhÈ~Zé®8ÎjÚ>8~8ş8.8(®8î8¾8)2"¢FörÒFVæçEöFör‡6W76–öâÂFVæçBæ–BÂFöuö–B¢–bæ÷BFöræ7F—fR÷"Föræ6FVv÷'’ÓÒ&W‡FW&æÂ# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8>8îxªÎ8şh¹¾[è^8¾KÛşyJ8~8Ş8î8¾8)2"¢æ÷&ÖÆ—¦VBÒæ÷&ÖÆ—¦UöVÖ–Â†VÖ–Â¢&Wf–÷W2Ò6W76–öâç66Æ'2‡6VÆV7B„÷væW$–çf—FF–öâ’çv†W&R€¢÷væW$–çf—FF–öâçFVæçEö–BÓÒFVæçBæ–BÂ÷væW$–çf—FF–öâæFöuö–BÓÒFöræ–BÀ¢÷væW$–çf—FF–öâæVÖ–ÂÓÒæ÷&ÖÆ—¦VBÂ÷væW$–çf—FF–öâæ66WFVEöBæ—5ò„æöæR’Â÷væW$–çf—FF–öâç&Wfö¶VEöBæ—5ò„æöæR’À¢’’æÆÂ‚¢æ÷rÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢f÷"–çf—FF–öâ–â&Wf–÷W3 ¢–çf—FF–öâç&Wfö¶VEöBÒæ÷p¢&u÷Fö¶VâÒ6V7&WG2çFö¶Vå÷W&Ç6fRƒ3"¢6W76–öâæFB„÷væW$–çf—FF–öâ‡FVæçEö–C×FVæçBæ–BÂFöuö–CÖFöræ–BÂVÖ–ÃÖæ÷&ÖÆ—¦VBÂ&VÆF–öç6†—×&VÆF–öç6†—À¢Fö¶Våö†6ƒ×Fö¶Våö†6‚‡&u÷Fö¶Vâ’ÂW‡—&W5öCÖæ÷r²F–ÖVFVÇF†F—3Ór’Â7&VFVEö'•ö–C×W6W"æ–B’¢6W76–öâæ6öÖÖ—B‚¢V&Æ–5ö&6U÷W&ÂÒ÷2æVçf—&öâævWB‚%T$Ä”5ô$4UõU$Â"Â7G"‡&WVW7Bæ&6U÷W&Â’’ç'7G&—‚"ò"¢–bV&Æ–5ö&6U÷W&Âç7F'G7v—F‚‚&‡GG¢òò"’æB&WVW7Bæ†VFW'2ævWB‚'‚Öf÷'v&FVB×&÷Fò"’ÓÒ&‡GG2# ¢V&Æ–5ö&6U÷W&ÂÒ&‡GG3¢òò"²V&Æ–5ö&6U÷W&Âç&VÖ÷fW&Vf—‚‚&‡GG¢òò"¢–çf—FU÷W&ÂÒV&Æ–5ö&6U÷W&Â²b"öfÖ–Ç’ö–çf—FR÷·&u÷Fö¶VçÒ ¢&WGW&âÆ–÷WB‚.h¹¾[èUU$Îy›®ŠÎZèÎK¨b"Â÷væW%ö–çf—FF–öåöFÖ–åö&öG’‡W6W"ÂFVæçBÂ6W76–öâÂ–çf—FU÷W&ÂÂæ÷&ÖÆ—¦VB’ÂW6W"  ¤ç÷7B‚"öfÖ–Ç’ö–çf—FF–öç2÷¶–çf—FF–öåö–GÒ÷&Wfö¶R"¦FVbfÖ–Ç•ö–çf—FF–öå÷&Wfö¶R†–çf—FF–öåö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢–çf—FF–öâÒ6W76–öâç66Æ"‡6VÆV7B„÷væW$–çf—FF–öâ’çv†W&R„÷væW$–çf—FF–öâæ–BÓÒ–çf—FF–öåö–BÂ÷væW$–çf—FF–öâçFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B–çf—FF–öã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.h¹¾[è^8ÎŠh¾8N8¾8(®8î8¾8)2"¢–bæ÷B–çf—FF–öâæ66WFVEöC ¢–çf—FF–öâç&Wfö¶VEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’ö–çf—FF–öç2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öfÖ–Ç’ö–çf—FR÷·&u÷Fö¶VçÒ"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö–çf—FU÷vR‡&u÷Fö¶Vã¢7G"Âf–WvW#¢W6W"ÂæöæRÒFWVæG2†7W'&VçE÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–çf—FF–öâÒ7F—fUö÷væW%ö–çf—FF–öâ‡&u÷Fö¶VâÂ6W76–öâ¢–bæ÷B–çf—FF–öã ¢&WGW&âÆ–÷WB‚.h¹¾[èUU$Î8*8:8;Â"ÂsÆƒî8>8îh¹¾[èUU$Î8şXŠyJ8~8Ş8î8¾8)3ÂöƒãÇ6Æ73Ò&W'&÷"#îiÉş™™Xˆ~8(Î8KÛşyJkˆ8ş88î8ş8şXùn8(®kh8^8(Î8şh¹¾[è^8~88.xªÎˆˆî8XhŞy›®ŠÎ8).8NKéŞšÎ8ş88^8N8#Â÷âr¢FörÂFVæçBÒ6W76–öâævWB„FörÂ–çf—FF–öâæFöuö–B’Â6W76–öâævWB…FVæçBÂ–çf—FF–öâçFVæçEö–B¢–bæ÷BFör÷"æ÷BFVæçC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢66÷VçBÒ6W76–öâç66Æ"‡6VÆV7B…W6W"’çv†W&R…W6W"æVÖ–ÂÓÒ–çf—FF–öâæVÖ–Â’¢–bf–WvW"æBf–WvW"æVÖ–ÂÒ–çf—FF–öâæVÖ–Ã ¢f÷&ÒÒsÇ6Æ73Ò&W'&÷"#îxûîYÊ8:Ş8+8*N8;>KŠŞ8î8*.8*¾8*n8;>888ş8h¹¾[è^XX8î8:8;Î8:¾8*.888:Î8+8y[8®8(®8î88.Kˆ[ªn8:Ş8+8*.8*n888~8n8¾8(h¹¾[èUU$Î8).™h¾8N8n8ş88^8N8#Â÷âp¢VÆ–bf–WvW# ¢f÷&ÒÒsÇî8:Ş8+8*N8;>KŠŞ8î8*.8*¾8*n8;>888~˜
>i®8~8Ş8î88#Â÷ãÆ'WGFöãîh¹¾[è^8).Xù~8Xùn8(³Âö'WGFöãâp¢VÆ–b66÷VçC ¢f÷&ÒÒbsÇç¶‡FÖÂæW66R†–çf—FF–öâæVÖ–Â—Ò8îy›¾˜Ë.kˆ8ş8*.8*¾8*n8;>888˜
>i®8~8î88#Â÷ãÆÆ&VÃî898+8:ş8;Î88“ÂöÆ&VÃãÆ–çWBæÖSÒ'77v÷&B"G—SÒ'77v÷&B"&WV—&VCãÆ'WGFöãî8:Ş8+8*N8;>8~8nh¹¾[è^8).Xù~8Xùn8(³Âö'WGFöãâp¢VÇ6S ¢f÷&ÒÒbsÇç¶‡FÖÂæW66R†–çf—FF–öâæVÖ–Â—Ò8~8*®8;Î88®8;Î8*.8*¾8*n8;>888).KÙÎh‰8~8î88#Â÷ãÆÆ&VÃî8®YŞX˜ÓÂöÆ&VÃãÆ–çWBæÖSÒ&æÖR"&WV—&VBÖ†ÆVæwFƒÒ##ãÆÆ&VÃî898+8:ş8;Î88ûÈƒih~ZÙ~Kº^Kˆ®ûÈ“ÂöÆ&VÃãÆ–çWBæÖSÒ'77v÷&B"G—SÒ'77v÷&B"Ö–æÆVæwFƒÒ#‚"&WV—&VCãÆ'WGFöãîy›¾˜Ë.8~8nh¹¾[è^8).Xù~8Xùn8(³Âö'WGFöãâp¢&öG’ÒbrrsÆƒç¶‡FÖÂæW66R‡FVæçBææÖR—Ş8¾8(8î8Nh¹¾[èSÂöƒãÆF—b6Æ73Ò'FVæçB#ãÆƒ#ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂöƒ#ãÇç¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ÓÂ÷ãÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’ö–çf—FR÷¶‡FÖÂæW66R‡&u÷Fö¶Vâ—Òö66WB#ç¶f÷&×ÓÂöf÷&Óârrp¢&WGW&âfÖ–Ç•öÆ–÷WB‚.8*®8;Î88®8;Îy›¾˜Ë.8î8NjXhR"Â&öG’Âf–WvW"Â6W76–öâ’–bf–WvW"VÇ6RÆ–÷WB‚.8*®8;Î88®8;Îy›¾˜Ë.8î8NjXhR"Â&öG’  ¤ç÷7B‚"öfÖ–Ç’ö–çf—FR÷·&u÷Fö¶VçÒö66WB"¦FVbfÖ–Ç•ö–çf—FUö66WB‡&u÷Fö¶Vã¢7G"Â&WVW7C¢&WVW7BÂæÖS¢7G"Òf÷&Ò‚""’Â77v÷&C¢7G"Òf÷&Ò‚""’Âf–WvW#¢W6W"ÂæöæRÒFWVæG2†7W'&VçE÷W6W"’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢–çf—FF–öâÒ7F—fUö÷væW%ö–çf—FF–öâ‡&u÷Fö¶VâÂ6W76–öâ¢–bæ÷B–çf—FF–öã ¢&WGW&â…DÔÅ&W7öç6R†Æ–÷WB‚.h¹¾[èUU$Î8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#î8>8îh¹¾[èUU$Î8şiÉş™™Xˆ~8(Î8KÛşyJkˆ8ş88î8ş8şXùn8(®kh8^8(Î8n8N8î88#Â÷âr’Â7FGW5ö6öFSÓC¢÷væW"Òf–WvW ¢–b÷væW"æB÷væW"æVÖ–ÂÒ–çf—FF–öâæVÖ–Ã ¢&WGW&â…DÔÅ&W7öç6R†fÖ–Ç•öÆ–÷WB‚.8*.8*¾8*n8;>888*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#îh¹¾[è^XX88şy[8®8(¾8*.8*¾8*n8;>888~8:Ş8+8*N8;>8~8n8N8î88#Â÷ârÂ÷væW"Â6W76–öâ’Â7FGW5ö6öFSÓC2¢–bæ÷B÷væW# ¢÷væW"Ò6W76–öâç66Æ"‡6VÆV7B…W6W"’çv†W&R…W6W"æVÖ–ÂÓÒ–çf—FF–öâæVÖ–Â’¢–b÷væW# ¢–bæ÷B÷væW"æ7F—fR÷"æ÷B77v÷&B÷"æ÷B77v÷&G2çfW&–g’‡77v÷&BÂ÷væW"ç77v÷&Eö†6‚“ ¢&WGW&â…DÔÅ&W7öç6R†Æ–÷WB‚.8:Ş8+8*N8;>8*8:8;Â"ÂbsÇ6Æ73Ò&W'&÷"#î898+8:ş8;Î888Î˜^8N8î88#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö–çf—FR÷¶‡FÖÂæW66R‡&u÷Fö¶Vâ—Ò#îh‹¾8(³Âöâr’Â7FGW5ö6öFSÓC¢VÇ6S ¢–bÆVâ‡77v÷&B’Â‚÷"æ÷BæÖRç7G&—‚“ ¢&WGW&â…DÔÅ&W7öç6R†Æ–÷WB‚.y›¾˜Ë.8*8:8;Â"ÂbsÇ6Æ73Ò&W'&÷"#î8®YŞX˜Ş8ƒih~ZÙ~Kº^Kˆ®8î898+8:ş8;Î888).XZ^X©¾8~8n8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö–çf—FR÷¶‡FÖÂæW66R‡&u÷Fö¶Vâ—Ò#îh‹¾8(³Âöâr’Â7FGW5ö6öFSÓC¢÷væW"ÒW6W"†æÖSÖæÖRç7G&—‚’ÂVÖ–ÃÖ–çf—FF–öâæVÖ–ÂÂ77v÷&Eö†6ƒ×77v÷&G2æ†6‚‡77v÷&B’Â&öÆSÕ&öÆRæ7W7FöÖW"¢6W76–öâæFB†÷væW"¢6W76–öâæfÇW6‚‚¢7W7FöÖW"Ò6W76–öâç66Æ"‡6VÆV7B„7W7FöÖW"’çv†W&R„7W7FöÖW"çFVæçEö–BÓÒ–çf—FF–öâçFVæçEö–BÂgVæ2æÆ÷vW"„7W7FöÖW"æVÖ–Â’ÓÒ–çf—FF–öâæVÖ–Â’æÆ–Ö—Bƒ’¢÷væW'6†—Ò6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒ–çf—FF–öâçFVæçEö–BÂFöt÷væW'6†—æFöuö–BÓÒ–çf—FF–öâæFöuö–BÂFöt÷væW'6†—çW6W%ö–BÓÒ÷væW"æ–B’¢–b÷væW'6†— ¢÷væW'6†—ç&VÆF–öç6†—Â÷væW'6†—æ7F—fRÒ–çf—FF–öâç&VÆF–öç6†—ÂG'VP¢÷væW'6†—æ7W7FöÖW%ö–BÒ7W7FöÖW"æ–B–b7W7FöÖW"VÇ6R÷væW'6†—æ7W7FöÖW%ö–@¢VÇ6S ¢6W76–öâæFB„Föt÷væW'6†—‡FVæçEö–CÖ–çf—FF–öâçFVæçEö–BÂFöuö–CÖ–çf—FF–öâæFöuö–BÂW6W%ö–CÖ÷væW"æ–BÀ¢7W7FöÖW%ö–CÖ7W7FöÖW"æ–B–b7W7FöÖW"VÇ6RæöæRÂ&VÆF–öç6†—Ö–çf—FF–öâç&VÆF–öç6†—’¢–çf—FF–öâæ66WFVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢&u÷6W76–öâÒæöæP¢–bæ÷Bf–WvW# ¢&u÷6W76–öâÒ6V7&WG2çFö¶Vå÷W&Ç6fRƒ3"¢6W76–öâæFB„Æöv–å6W76–öâ‡Fö¶Våö†6ƒ×Fö¶Våö†6‚‡&u÷6W76–öâ’ÂW6W%ö–CÖ÷væW"æ–BÂW‡—&W5öCÖFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’²F–ÖVFVÇF†F—3Õ4U54”ôåôD•2’’¢6W76–öâæ6öÖÖ—B‚¢&W7öç6RÒ&VF—&V7E&W7öç6R‚"öfÖ–Ç’"Â7FGW5ö6öFSÓ32¢–b&u÷6W76–öã ¢&W7öç6Rç6WEö6öö¶–R‚&Föu÷6W76–öâ"Â&u÷6W76–öâÂ‡GGöæÇ“ÕG'VRÂ6V7W&SÔ4ôô´”Uõ4T5U$RÂ6ÖW6—FSÒ&Æ‚"ÂÖ…övSÕ4U54”ôåôD•2¢ƒcC¢&WGW&â&W7öç6P  ¤ævWB‚"öfÖ–Ç’ö÷væW'2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö÷væW%öÆ–æ·2†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢Föw2Ò6W76–öâç66Æ'2€¢6VÆV7B„För’çv†W&R„FörçFVæçEö–BÓÒFVæçBæ–BÂFöræ7F—fRæ—5ò…G'VR’ÂFöræ6FVv÷'’Ò&W‡FW&æÂ"’æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢Föuö÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'¶Föræ–GÒ#ç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ŞûÈ‡¶‡FÖÂæW66R†Förç&Vv—7FW&VEöæÖR÷".Š{[i»YŞiÊ®y›¾˜Ë""—ŞûÈ“Âö÷F–öãârf÷"För–âFöw2¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B„Föt÷væW'6†—ÂFörÂW6W"¢æ¦ö–â„FörÂFöræ–BÓÒFöt÷væW'6†—æFöuö–B¢æ¦ö–â…W6W"ÂW6W"æ–BÓÒFöt÷væW'6†—çW6W%ö–B¢çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’¢æ÷&FW%ö'’„Föræ6ÆÅöæÖRÂW6W"ææÖR¢’æÆÂ‚¢&÷w2Ò" ¢f÷"÷væW'6†—ÂFörÂ÷væW"–â&V6÷&G3 ¢&VÆF–öâÒ.K‹¾8*®8;Î88®8;Â"–b÷væW'6†—ç&VÆF–öç6†—ÓÒ'&–Ö'’"VÇ6R.8NZënixò ¢G'“ ¢VÖ–Åö6†ævU÷F&vWB†÷væW"æ–BÂW6W"ÂFVæçBÂ6W76–öâ¢VÖ–Åö7F–öâÒbsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö÷væW'2÷¶÷væW"æ–GÒöVÖ–Â#î8:8;Î8:¾ZHi»CÂöâp¢W†6WB…EEW†6WF–öã ¢VÖ–Åö7F–öâÒsÇ7â6Æ73Ò&&FvR#î˜¾Yknzêynˆ^8î8şZHi»NXúóÂ÷7ãâp¢&÷w2³ÒbrrsÇG#ãÇFCç¶‡FÖÂæW66R†Föræ6ÆÅöæÖR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†÷væW"ææÖR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†÷væW"æVÖ–Â—ÓÂ÷FCãÇFCç·&VÆF–öçÓÂ÷FCà¢ÇFCç¶VÖ–Åö7F–öçÒÆf÷&Ò6Æ73Ò&–æÆ–æR"ÖWF†öCÒ'÷7B"7F–öãÒ"öfÖ–Ç’ö÷væW'2÷¶÷væW'6†—æ–GÒ÷&VÖ÷fR#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#î˜
>i®Šz>™šCÂö'WGFöããÂöf÷&ÓãÂ÷FCãÂ÷G#ârrp¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öFÖ–â÷W6W'2#î8:n8;Î8+n8;Îzêyn8h‹¾8(³ÂöâÆ6Æ73Ò&'WGFöâ7V66W72"‡&VcÒ"öfÖ–Ç’ö–çf—FF–öç2#î8*®8;Î88®8;Îjy8).h¹¾[èSÂöà¢Æƒç¶‡FÖÂæW66R‡FVæçBææÖR—Ò8*®8;Î88®8;Î˜
>i£Âöƒà¢Çî8*®8;Î88®8;Î8Îy›¾˜Ë.8~8ş8:8;Î8:¾8*.888:Î8+8xªÎ8).{Y8>K¹88î88#K«®8¾ŠH~i[š
Ş88NZënixş8¾YÎ8xªÎ8).˜
>i®8~8Ş8î88#Â÷à¢Æf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃîxªÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ&Föuö–B"&WV—&VCç¶Föuö÷F–öç7ÓÂ÷6VÆV7Cà¢ÆÆ&VÃîy›¾˜Ë.kˆ8ş8*®8;Î88®8;Î8î8:8;Î8:¾8*.888:Î8+“ÂöÆ&VÃãÆ–çWBæÖSÒ&VÖ–Â"G—SÒ&VÖ–Â"&WV—&VCà¢ÆÆ&VÃî™j.Kø#ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&VÆF–öç6†—#ãÆ÷F–öâfÇVSÒ'&–Ö'’#îK‹¾8*®8;Î88®8;ÃÂö÷F–öããÆ÷F–öâfÇVSÒ&fÖ–Ç’#î8NZënixóÂö÷F–öããÂ÷6VÆV7Cà¢Æ'WGFöãîxªÎ88*®8;Î88®8;Î8).˜
>i£Âö'WGFöããÂöf÷&Óà¢Æƒ#îxûîYÊ8î˜
>i£Âöƒ#ãÇF&ÆSãÇG#ãÇFƒîxªÃÂ÷FƒãÇFƒî8*®8;Î88®8;ÃÂ÷FƒãÇFƒî8:8;Î8:³Â÷FƒãÇFƒî™j.Kø#Â÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w7ÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚.8*®8;Î88®8;Î˜
>i¢"Â&öG’ÂW6W"  ¦FVbVÖ–Åö6†ævU÷F&vWB‡W6W%ö–C¢–çBÂ7F÷#¢W6W"ÂFVæçC¢FVæçBÂ6W76–öã¢6W76–öâ’ÓâGWÆUµW6W"Â6WE¶–çEÕÓ ¢F&vWBÒ6W76–öâævWB…W6W"ÂW6W%ö–B¢–bæ÷BF&vWB÷"æ÷BF&vWBæ7F—fR÷"F&vWBæ–BÓÒ7F÷"æ–C ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.ZHi»NZûî‹8î8*.8*¾8*n8;>888ÎŠh¾8N8¾8(®8î8¾8)2"¢FVæçEö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—çFVæçEö–B’çv†W&R€¢Föt÷væW'6†—çW6W%ö–BÓÒF&vWBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR¢’’æÆÂ‚’¢FVæçEö–G2çWFFR‡6W76–öâç66Æ'2‡6VÆV7B„ÖVÖ&W'6†—çFVæçEö–B’çv†W&R„ÖVÖ&W'6†—çW6W%ö–BÓÒF&vWBæ–B’’æÆÂ‚’¢–bFVæçBæ–Bæ÷B–âFVæçEö–G3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.8>8îxªÎˆˆî8™j.Kø.88(¾8*.8*¾8*n8;>888~8ş8.8(®8î8¾8)2"¢&öÆW2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„ÖVÖ&W'6†—ç&öÆR’çv†W&R„ÖVÖ&W'6†—çW6W%ö–BÓÒF&vWBæ–B’’æÆÂ‚’¢7W7FöÖW%ööæÇ’Òæ÷BF&vWBçÆFf÷&ÕöFÖ–âæBF&vWBç&öÆRÓÒ&öÆRæ7W7FöÖW"æB&öÆW2æ—77V'6WB‡µ&öÆRæ7W7FöÖW'Ò¢–bæ÷B7F÷"çÆFf÷&ÕöFÖ–âæB‡FVæçEö–G2Ò·FVæçBæ–GÒ÷"æ÷B7W7FöÖW%ööæÇ’“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.ŠH~i[xªÎˆˆî8¾™j.Kø.88(¾8*.8*¾8*n8;>888zêynˆ^8;¾[é>jZŞY:8î8:8;Î8:¾ZHi»N8ş˜¾Yknzêynˆ^888ÎŠÎ88î8’"¢&WGW&âF&vWBÂFVæçEö–G0  ¤ævWB‚"öfÖ–Ç’ö÷væW'2÷·W6W%ö–GÒöVÖ–Â"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbfÖ–Ç•ö÷væW%öVÖ–ÅöVF—B‡W6W%ö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢F&vWBÂFVæçEö–G2ÒVÖ–Åö6†ævU÷F&vWB‡W6W%ö–BÂ7F÷"ÂFVæçBÂ6W76–öâ¢Föw2Ò6W76–öâç66Æ'2€¢6VÆV7B„Föræ6ÆÅöæÖR’æ¦ö–â„Föt÷væW'6†—ÂFöt÷væW'6†—æFöuö–BÓÒFöræ–B¢çv†W&R„Föt÷væW'6†—çW6W%ö–BÓÒF&vWBæ–BÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’¢æ÷&FW%ö'’„Föræ6ÆÅöæÖR¢’æÆÂ‚¢†—7F÷&–W2Ò6W76–öâæW†V7WFR€¢6VÆV7B„66÷VçDVÖ–Ä6†ævTVF—BÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒ66÷VçDVÖ–Ä6†ævTVF—Bæ6†ævVEö'•ö–B¢çv†W&R„66÷VçDVÖ–Ä6†ævTVF—BçF&vWE÷W6W%ö–BÓÒF&vWBæ–B’æ÷&FW%ö'’„66÷VçDVÖ–Ä6†ævTVF—Bæ6†ævVEöBæFW62‚’’æÆ–Ö—Bƒ#¢’æÆÂ‚¢†—7F÷'•÷&÷w2Ò""æ¦ö–â€¢brrsÇG#ãÇFCç¶VF—Bæ6†ævVEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†VF—BæöÆEöVÖ–Â—ÓÂ÷FCà¢ÇFCç¶‡FÖÂæW66R†VF—BææWuöVÖ–Â—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†6†ævW"ææÖR—ÓÂ÷FCãÂ÷G#ârrrf÷"VF—BÂ6†ævW"–â†—7F÷&–W0¢¢66÷Uöæ÷F–6RÒ.ŠH~i[xªÎˆˆî8¾™j.Kø.88(¾8ş8(8˜¾Yknzêynˆ^jŠ™™8~ZHi»N8~8î88""–bÆVâ‡FVæçEö–G2’âVÇ6R.8>8îxªÎˆˆî888¾™j.Kø.88(¾8*®8;Î88®8;Î8*.8*¾8*n8;>888~88" ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö÷væW'2#î8*®8;Î88®8;Î˜
>i®8h‹¾8(³ÂöãÆƒîy›¾˜Ë.8:8;Î8:¾8*.888:Î8+ZHi»CÂöƒà¢ÆF—b6Æ73Ò'FVæçB#ãÇãÇ7G&öæsî8*®8;Î88®8;ÎûÉ£Â÷7G&öæsç¶‡FÖÂæW66R‡F&vWBææÖR—ÓÂ÷ãÇãÇ7G&öæsîhI¾xªÎûÉ£Â÷7G&öæsç¶‡FÖÂæW66R‚.8"æ¦ö–â†Föw2’÷".˜
>i®8®8r"—ÓÂ÷à¢ÇãÇ7G&öæsîxûîYÊûÉ£Â÷7G&öæsç¶‡FÖÂæW66R‡F&vWBæVÖ–Â—ÓÂ÷ãÇãÇ6ÖÆÃç·66÷Uöæ÷F–6WÓÂ÷6ÖÆÃãÂ÷ãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÇãÇ7G&öæsî˜xŞŠh8®i8ŞKÙÎ8~8“Â÷7G&öæsãÂ÷ãÇîZHi»N[èÎ8şiz~8:8;Î8:¾8*.888:Î8+8~8:Ş8+8*N8;>8~8Ş8î8¾8)>8.ZèXZ8î8ş8(88>8î8*.8*¾8*n8;>888î8:Ş8+8*N8;>KŠŞ8+¾88>8+~8:~8;>8).888n{X.K¨n8~8î88#Â÷ãÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃîik8~8N8:8;Î8:¾8*.888:Î8+“ÂöÆ&VÃãÆ–çWBG—SÒ&VÖ–Â"æÖSÒ&æWuöVÖ–Â"&WV—&VBWFö6ö×ÆWFSÒ&öfb#à¢ÆÆ&VÃîz+®Š¨Ş8î8ş8(88.8®8ş8îzêynˆ^898+8:ş8;Î888).XZ^X©³ÂöÆ&VÃãÆ–çWBG—SÒ'77v÷&B"æÖSÒ&FÖ–å÷77v÷&B"&WV—&VBWFö6ö×ÆWFSÒ&7W'&VçB×77v÷&B#à¢ÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C#ãÆ–çWB7G–ÆSÒ'v–GFƒ¦WFò"G—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&ÖVB"fÇVSÒ'G'VR"&WV—&VCâ8*®8;Î88®8;ÎjyiÊÎK«®8¾8(ZHi»NKéŞšÎ8).Xù~88Xh^Zë8).z+®Š¨Ş8~8î8~8óÂöÆ&VÃà¢Æ'WGFöâ6Æ73Ò&FævW"#îy›¾˜Ë.8:8;Î8:¾8*.888:Î8+8).ZHi»N88(³Âö'WGFöããÂöf÷&Óà¢Æƒ#îZHi»N[^jÛCÂöƒ#ãÇF&ÆSãÇG#ãÇFƒîZHi»Niz^i˜#Â÷FƒãÇFƒîZHi»NX˜ÓÂ÷FƒãÇFƒîZHi»N[èÃÂ÷FƒãÇFƒîh¸^[Ù>ˆSÂ÷FƒãÂ÷G#ç¶†—7F÷'•÷&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îZHi»N[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚.y›¾˜Ë.8:8;Î8:¾8*.888:Î8+ZHi»B"Â&öG’Â7F÷"  ¤ç÷7B‚"öfÖ–Ç’ö÷væW'2÷·W6W%ö–GÒöVÖ–Â"¦FVbfÖ–Ç•ö÷væW%öVÖ–Å÷WFFR€¢W6W%ö–C¢–çBÂæWuöVÖ–Ã¢7G"Òf÷&Ò‚âââ’ÂFÖ–å÷77v÷&C¢7G"Òf÷&Ò‚âââ’Â6öæf—&ÖVC¢&ööÂÒf÷&Ò„fÇ6R’À¢66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’À¢“ ¢7F÷"ÂFVæçBÒ66W70¢F&vWBÂFVæçEö–G2ÒVÖ–Åö6†ævU÷F&vWB‡W6W%ö–BÂ7F÷"ÂFVæçBÂ6W76–öâ¢æ÷&ÖÆ—¦VBÒæ÷&ÖÆ—¦UöVÖ–Â†æWuöVÖ–Â¢–bæ÷B6öæf—&ÖVB÷"æ÷B77v÷&G2çfW&–g’†FÖ–å÷77v÷&BÂ7F÷"ç77v÷&Eö†6‚“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.zêynˆ^898+8:ş8;Î888î8ş8şz+®Š¨Şš^yºî8).z+®Š¨Ş8~8n8ş88^8B"¢–bÆVâ†æ÷&ÖÆ—¦VB’â#SR÷"æ÷B&RægVÆÆÖF6‚‡"%µäÇ5Ò´µäÇ5ÒµÂåµäÇ5Ò²"Âæ÷&ÖÆ—¦VB“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.ik8~8N8:8;Î8:¾8*.888:Î8+8î[Ú.[Èş8).z+®Š¨Ş8~8n8ş88^8B"¢GWÆ–6FRÒ6W76–öâç66Æ"‡6VÆV7B…W6W"æ–B’çv†W&R†gVæ2æÆ÷vW"…W6W"æVÖ–Â’ÓÒæ÷&ÖÆ—¦VBÂW6W"æ–BÒF&vWBæ–B’æÆ–Ö—Bƒ’¢–bGWÆ–6FS ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8>8î8:8;Î8:¾8*.888:Î8+8şXŠ^8î8*.8*¾8*n8;>888~KÛşyJ8^8(Î8n8N8î8’"¢–bæ÷&ÖÆ—¦VBÓÒæ÷&ÖÆ—¦UöVÖ–Â‡F&vWBæVÖ–Â“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.xûîYÊ8YÎ88:8;Î8:¾8*.888:Î8+8~8’"¢öÆEöVÖ–ÂÒF&vWBæVÖ–À¢7W7FöÖW%ö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—æ7W7FöÖW%ö–B’çv†W&R€¢Föt÷væW'6†—çW6W%ö–BÓÒF&vWBæ–BÂFöt÷væW'6†—çFVæçEö–Bæ–åò‡FVæçEö–G2’À¢Föt÷væW'6†—æ7W7FöÖW%ö–Bæ—5öæ÷B„æöæR’ÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’À¢’’æÆÂ‚’¢Æ–æ¶VEö7W7FöÖW'2Ò6W76–öâç66Æ'2‡6VÆV7B„7W7FöÖW"’çv†W&R€¢7W7FöÖW"æ–Bæ–åò†7W7FöÖW%ö–G2’ÂgVæ2æÆ÷vW"„7W7FöÖW"æVÖ–Â’ÓÒæ÷&ÖÆ—¦UöVÖ–Â†öÆEöVÖ–Â¢’’æÆÂ‚’–b7W7FöÖW%ö–G2VÇ6RµĞ¢F&vWBæVÖ–ÂÒæ÷&ÖÆ—¦V@¢f÷"7W7FöÖW"–âÆ–æ¶VEö7W7FöÖW'3 ¢7W7FöÖW"æVÖ–ÂÒæ÷&ÖÆ—¦V@¢6W76–öâæFB„66÷VçDVÖ–Ä6†ævTVF—B€¢FVæçEö–C×FVæçBæ–BÂF&vWE÷W6W%ö–C×F&vWBæ–BÂ6†ævVEö'•ö–CÖ7F÷"æ–BÀ¢öÆEöVÖ–ÃÖöÆEöVÖ–ÂÂæWuöVÖ–ÃÖæ÷&ÖÆ—¦VBÂÆ–æ¶VEö7W7FöÖW'5÷WFFVCÖÆVâ†Æ–æ¶VEö7W7FöÖW'2’À¢’¢æ÷F–6RÒbrrw·F&vWBææÖWÒjy€ ¤U5E$TÄÄdÔ”Å8îy›¾˜Ë.8:8;Î8:¾8*.888:Î8+8ÎZHi»N8^8(Î8î8~8ş8 ®ZHi»NX˜ŞûÉ§¶öÆEöVÖ–ÇĞ®ZHi»N[èÎûÉ§¶æ÷&ÖÆ—¦VGĞ ®K¸®[èÎ8şik8~8N8:8;Î8:¾8*.888:Î8+8~8:Ş8+8*N8;>8~8n8ş88^8N8.8®[ø>[Ù>8ş8(®8Î8®8NZNY8ş8888¾xªÎˆˆî88N˜
>{Z8ş88^8N8"rrp¢VWVUöVÖ–Â‡6W76–öâÂöÆEöVÖ–ÂÂ&VÖ–Åö6†ævVB"Â.8	U5E$TÄÄdÔ”Å8	y›¾˜Ë.8:8;Î8:¾8*.888:Î8+ZHi»N8î8®yú^8(8²"Âæ÷F–6RÂFVæçBæ–BÂF&vWBæ–B¢VWVUöVÖ–Â‡6W76–öâÂæ÷&ÖÆ—¦VBÂ&VÖ–Åö6†ævVB"Â.8	U5E$TÄÄdÔ”Å8	y›¾˜Ë.8:8;Î8:¾8*.888:Î8+ZHi»N8î8®yú^8(8²"Âæ÷F–6RÂFVæçBæ–BÂF&vWBæ–B¢6W76–öâæW†V7WFR‡FW‡B‚$DTÄUDRe$ôÒÆöv–å÷6W76–öç2t„U$RW6W%ö–BÒ§W6W%ö–B"’Â²'W6W%ö–B#¢F&vWBæ–GÒ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öfÖ–Ç’ö÷væW'2÷·F&vWBæ–GÒöVÖ–Â"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’ö÷væW'2"¦FVbfÖ–Ç•ö÷væW%öÆ–æµöFB†Föuö–C¢–çBÒf÷&Ò‚âââ’ÂVÖ–Ã¢7G"Òf÷&Ò‚âââ’Â&VÆF–öç6†—¢7G"Òf÷&Ò‚'&–Ö'’"’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢–b&VÆF–öç6†—æ÷B–â²'&–Ö'’"Â&fÖ–Ç’'Ó ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.™j.Kø.8îhÈ~Zé®8ÎjÚ>8~8ş8.8(®8î8¾8)2"¢FörÒFVæçEöFör‡6W76–öâÂFVæçBæ–BÂFöuö–B¢–bæ÷BFöræ7F—fR÷"Föræ6FVv÷'’ÓÒ&W‡FW&æÂ# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.8>8îxªÎ8ş8*®8;Î88®8;Î˜
>i®8~8Ş8î8¾8)2"¢æ÷&ÖÆ—¦VBÒæ÷&ÖÆ—¦UöVÖ–Â†VÖ–Â¢÷væW"Ò6W76–öâç66Æ"‡6VÆV7B…W6W"’çv†W&R…W6W"æVÖ–ÂÓÒæ÷&ÖÆ—¦VBÂW6W"æ7F—fRæ—5ò…G'VR’’¢–bæ÷B÷væW# ¢&WGW&â…DÔÅ&W7öç6R†Æ–÷WB‚.˜
>i®8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#î8>8î8:8;Î8:¾8*.888:Î8+8î8*.8*¾8*n8;>888Î8.8(®8î8¾8)>8.XX8¾8*®8;Î88®8;Îjy8¾8Î8®Zê.jyy›¾˜Ë.8Ş8).8~8n8N8ş88N8n8ş88^8N8#Â÷ãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’ö÷væW'2#îh‹¾8(³ÂöârÂW6W"’Â7FGW5ö6öFSÓC¢7W7FöÖW"Ò6W76–öâç66Æ"‡6VÆV7B„7W7FöÖW"’çv†W&R„7W7FöÖW"çFVæçEö–BÓÒFVæçBæ–BÂgVæ2æÆ÷vW"„7W7FöÖW"æVÖ–Â’ÓÒæ÷&ÖÆ—¦VB’æÆ–Ö—Bƒ’¢÷væW'6†—Ò6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æFöuö–BÓÒFöræ–BÂFöt÷væW'6†—çW6W%ö–BÓÒ÷væW"æ–B’¢–b÷væW'6†— ¢÷væW'6†—ç&VÆF–öç6†—Ò&VÆF–öç6†— ¢÷væW'6†—æ7W7FöÖW%ö–BÒ7W7FöÖW"æ–B–b7W7FöÖW"VÇ6R÷væW'6†—æ7W7FöÖW%ö–@¢÷væW'6†—æ7F—fRÒG'VP¢VÇ6S ¢6W76–öâæFB„Föt÷væW'6†—‡FVæçEö–C×FVæçBæ–BÂFöuö–CÖFöræ–BÂW6W%ö–CÖ÷væW"æ–BÂ7W7FöÖW%ö–CÖ7W7FöÖW"æ–B–b7W7FöÖW"VÇ6RæöæRÂ&VÆF–öç6†—×&VÆF–öç6†—’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’ö÷væW'2"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öfÖ–Ç’ö÷væW'2÷¶÷væW'6†—ö–GÒ÷&VÖ÷fR"¦FVbfÖ–Ç•ö÷væW%öÆ–æµ÷&VÖ÷fR†÷væW'6†—ö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢÷væW'6†—Ò6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—’çv†W&R„Föt÷væW'6†—æ–BÓÒ÷væW'6†—ö–BÂFöt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–B’¢–bæ÷B÷væW'6†— ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCBÂFWF–ÃÒ.˜
>i®8ÎŠh¾8N8¾8(®8î8¾8)2"¢÷væW'6†—æ7F—fRÒfÇ6P¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öfÖ–Ç’ö÷væW'2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öFÖ–â÷W6W'2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbW6W%öÆ—7B‡&WVW7C¢&WVW7BÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢ÖVÖ&W'6†—2Ò6W76–öâç66Æ'2‡6VÆV7B„ÖVÖ&W'6†—’çv†W&R„ÖVÖ&W'6†—çFVæçEö–BÓÒFVæçBæ–B’’æÆÂ‚¢&÷w2Ò" ¢f÷"ÖVÖ&W"–âÖVÖ&W'6†—3 ¢66÷VçBÒ6W76–öâævWB…W6W"ÂÖVÖ&W"çW6W%ö–B¢&÷w2³Òb#ÇG#ãÇFCç¶‡FÖÂæW66R†66÷VçBææÖR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†66÷VçBæVÖ–Â—ÓÂ÷FCãÇFCç¶ÖVÖ&W"ç&öÆRçfÇVWÓÂ÷FCãÂ÷G#â ¢&öG’ÒbsÆƒç¶‡FÖÂæW66R‡FVæçBææÖR—Ş8î8:n8;Î8+n8;ÃÂöƒãÆ6Æ73Ò&'WGFöâ"‡&VcÒ"öfÖ–Ç’ö÷væW'2#î8*®8;Î88®8;Î8xªÎ8).˜
>i£ÂöãÆf÷&ÒÖWF†öCÒ'÷7B#ãÆÆ&VÃîy›¾˜Ë.kˆ8ş8:n8;Î8+n8;Î8î8:8;Î8:¾8*.888:Î8+“ÂöÆ&VÃãÆ–çWBæÖSÒ&VÖ–Â"G—SÒ&VÖ–Â"&WV—&VCãÆÆ&VÃîjŠ™™ÂöÆ&VÃãÇ6VÆV7BæÖSÒ'&öÆR#ãÆ÷F–öâfÇVSÒ&V×Æ÷–VR#î[é>jZŞY:Âö÷F–öããÆ÷F–öâfÇVSÒ&7W7FöÖW"#î8®Zê.jyƒÂö÷F–öããÆ÷F–öâfÇVSÒ&FÖ–â#îzêynˆSÂö÷F–öããÂ÷6VÆV7CãÆ'WGFöãîh˜[î8).‹ûŞXªÂö'WGFöããÂöf÷&ÓãÇF&ÆSãÇG#ãÇFƒîYŞX˜ÓÂ÷FƒãÇFƒî8:8;Î8:³Â÷FƒãÇFƒîjŠ™™Â÷FƒãÂ÷G#ç·&÷w7ÓÂ÷F&ÆSâp¢&WGW&âÆ–÷WB‚.8:n8;Î8+n8;Îzêyb"Â&öG’ÂW6W"  ¤ævWB‚"öFÖ–â÷77v÷&B×&W6WG2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVb77v÷&E÷&W6WEöÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢&VÆFVEö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—çW6W%ö–B’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚’¢&VÆFVEö–G2çWFFR‡6W76–öâç66Æ'2‡6VÆV7B„ÖVÖ&W'6†—çW6W%ö–B’çv†W&R„ÖVÖ&W'6†—çFVæçEö–BÓÒFVæçBæ–B’’æÆÂ‚’¢&V6÷&G2Ò6W76–öâæW†V7WFR€¢6VÆV7B…77v÷&E&W6WE&WVW7BÂW6W"’æ¦ö–â…W6W"ÂW6W"æ–BÓÒ77v÷&E&W6WE&WVW7BçW6W%ö–B¢çv†W&R…77v÷&E&W6WE&WVW7BçW6W%ö–Bæ–åò‡&VÆFVEö–G2’Â77v÷&E&W6WE&WVW7Bç&W6öÇfVEöBæ—5ò„æöæR’¢æ÷&FW%ö'’…77v÷&E&W6WE&WVW7Bç&WVW7FVEöBæFW62‚’’æÆ–Ö—Bƒ¢’æÆÂ‚’–b&VÆFVEö–G2VÇ6RµĞ¢&÷w2Ò" ¢f÷"&WVW7Eö—FVÒÂ66÷VçB–â&V6÷&G3 ¢G'“ ¢VÖ–Åö6†ævU÷F&vWB†66÷VçBæ–BÂ7F÷"ÂFVæçBÂ6W76–öâ¢7F–öâÒbsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öFÖ–â÷77v÷&B×&W6WG2÷·&WVW7Eö—FVÒæ–GÒö—77VR#ãÆÆ&VÃîzêynˆ^898+8:ş8;Î88“ÂöÆ&VÃãÆ–çWBG—SÒ'77v÷&B"æÖSÒ&FÖ–å÷77v÷&B"&WV—&VCãÆ'WGFöãîXhŞŠŠŞZé®8:®8;>8*ş8).y›®ŠÃÂö'WGFöããÂöf÷&Óâp¢W†6WB…EEW†6WF–öã ¢7F–öâÒsÇ7â6Æ73Ò&&FvR#î˜¾Yknzêynˆ^8î8şZûî[ùÎXúóÂ÷7ãâp¢&÷w2³ÒbrrsÇG#ãÇFCç¶‡FÖÂæW66R†66÷VçBææÖR—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†66÷VçBæVÖ–Â—ÓÂ÷FCãÇFCç·&WVW7Eö—FVÒç&WVW7FVEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—ÓÂ÷FCãÇFCç¶7F–öçÓÂ÷FCãÂ÷G#ârrp¢&öG’ÒbrrsÆƒî898+8:ş8;Î88XhŞŠŠŞZé®yK>‹ëÎ8óÂöƒãÇîiÊÎK«®z+®Š¨Ş[èÎ8¾Kˆ[ªn88KÛş88(¾XhŞŠŠŞZé®8:®8;>8*ş8).y›®ŠÎ8~88*®8;Î88®8;Îjy8ZèXZ8®ikk9^8~8®KÉŞ88ş88^8N8.iÈX«iÉş™™8ó3Xˆn8~88#Â÷à¢ÇF&ÆSãÇG#ãÇFƒî8®YŞX˜ÓÂ÷FƒãÇFƒîy›¾˜Ë.8:8;Î8:³Â÷FƒãÇFƒîyK>‹ëÎiz^i˜#Â÷FƒãÇFƒîZûî[ùÃÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#B#îiÊ®Zûî[ùÎ8îyK>‹ëÎ8ş8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚.898+8:ş8;Î88XhŞŠŠŞZé®zêyb"Â&öG’Â7F÷"  ¤ævWB‚"öFÖ–âöVÖ–ÂÖFVÆ—fW&–W2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbVÖ–ÅöFVÆ—fW&–W5öÖævR†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢&VÆFVEö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—çW6W%ö–B’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚’¢6öæF—F–öâÒVÖ–ÄFVÆ—fW'’çFVæçEö–BÓÒFVæçBæ–@¢–b&VÆFVEö–G3 ¢6öæF—F–öâÒ6öæF—F–öâÂVÖ–ÄFVÆ—fW'’çW6W%ö–Bæ–åò‡&VÆFVEö–G2¢&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„VÖ–ÄFVÆ—fW'’’çv†W&R†6öæF—F–öâ’æ÷&FW%ö'’„VÖ–ÄFVÆ—fW'’æ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ#’’æÆÂ‚¢&÷w2Ò" ¢f÷"FVÆ—fW'’–â&V6÷&G3 ¢&WG'’ÒbsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öFÖ–âöVÖ–ÂÖFVÆ—fW&–W2÷¶FVÆ—fW'’æ–GÒ÷&WG'’#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#îXhŞ˜Âö'WGFöããÂöf÷&Óâr–bFVÆ—fW'’ç7FGW2Ò'6VçB"æBFVÆ—fW'’çW'÷6RÒ'77v÷&E÷&W6WB"VÇ6R.ûÈÒ ¢&÷w2³ÒbrrsÇG#ãÇFCç¶FVÆ—fW'’æ7&VFVEöBç7G&gF–ÖR‚rU’ÒVÒÒVBTƒ¢TÒr—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†FVÆ—fW'’ç&V6—–VçB—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†FVÆ—fW'’ç7V&¦V7B—ÓÂ÷FCà¢ÇFCç¶‡FÖÂæW66R†FVÆ—fW'’ç7FGW2—ÓÂ÷FCãÇFCç¶FVÆ—fW'’æGFV×G7ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†FVÆ—fW'’æW'&÷"÷".ûÈÒ"—ÓÂ÷FCãÇFCç·&WG'—ÓÂ÷FCãÂ÷G#ârrp¢7FFRÒ.˜KúXúşˆ;Ò"–b6×G÷&VG’‚’VÇ6R.iÊ®ŠŠŞZé®ûÈ…4ÕEô„õ5N8;µ4ÕEôe$ôÕôTÔ”ÎzØ8).ŠŠŞZé®8~8n8ş88^8NûÈ’ ¢&öG’ÒbrrsÆƒî8:8;Î8:¾˜Kú[^jÛCÂöƒãÆF—b6Æ73Ò'FVæçB#ãÇãÇ7G&öæsî˜XŞKúŠŠŞZé®ûÉ£Â÷7G&öæsç·7FFWÓÂ÷ãÇîZKiY~8~8ş˜	®[‹˜	®yú^8şŠŠŞZé®KúîjÚ>[èÎ8¾XhŞ˜8~8Ş8î88.898+8:ş8;Î88XhŞŠŠŞZé®8:®8;>8*ş8şZèXZ8î8ş8(XhŞ˜8¾8®8ik8~8N8:®8;>8*ş8).y›®ŠÎ8~8î88#Â÷ãÂöF—cà¢ÇF&ÆSãÇG#ãÇFƒîKÙÎh‰iz^i˜#Â÷FƒãÇFƒîZé¾XXƒÂ÷FƒãÇFƒîK»nYÓÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîŠšnŠÃÂ÷FƒãÇFƒî8*8:8;ÃÂ÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#r#î˜Kú[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚.8:8;Î8:¾˜Kú[^jÛB"Â&öG’Â7F÷"  ¦FVbæ÷F–f–6F–öåöFVÆ—fW'•öW‡÷'Eö—FV×2‡FVæçC¢FVæçBÂFVÆ—fW'•÷7FGW3¢7G"Â6†ææVÃ¢7G"Âæ÷F–f–6F–öåö6FVv÷'“¢7G"À¢FFUög&öÓ¢7G"ÂFFU÷Fó¢7G"Â÷væW%ö¶W—v÷&C¢7G"Â6W76–öã¢6W76–öâ“ ¢ÆÆ÷vVE÷7FGW6W2Ò²""Â'6VçB"Â&f–ÆVB"Â'VæF–ær'Ó²ÆÆ÷vVEö6†ææVÇ2Ò²""Â&Æ–æR"Â&VÖ–Â"Â&'&÷w6W"'Ó²ÆÆ÷vVEö6FVv÷&–W2Ò²""Â&ææ—fW'6'’"Â&†VÇF‚"Â'FW7B'Ğ¢–bFVÆ—fW'•÷7FGW2æ÷B–âÆÆ÷vVE÷7FGW6W2÷"6†ææVÂæ÷B–âÆÆ÷vVEö6†ææVÇ2÷"æ÷F–f–6F–öåö6FVv÷'’æ÷B–âÆÆ÷vVEö6FVv÷&–W3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jIÎ{J.iÚK»n8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢7F'Eöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFUög&öÒ’–bFFUög&öÒVÇ6RæöæS²VæEöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFU÷Fò’–bFFU÷FòVÇ6RæöæP¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jIÎ{J.iÉş™i>8).z+®Š¨Ş8~8n8ş88^8B"¢–b7F'Eöf–ÇFW"æBVæEöf–ÇFW"æB7F'Eöf–ÇFW"âVæEöf–ÇFW#¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢&VÆFVEö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—çW6W%ö–B’çv†W&R„Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚’¢÷væW'2Ò¶—FVÒæ–C¢—FVÒææÖRf÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B…W6W"’çv†W&R…W6W"æ–Bæ–åò‡&VÆFVEö–G2’’’æÆÂ‚—Ò–b&VÆFVEö–G2VÇ6R·Ğ¢—FV×3¢Æ—7E·GWÆU¶FFWF–ÖRÂ7G"Â7G"Â7G"Â7G"Â–çBÂFFWF–ÖRÂæöæRÂ7G%ÕÒÒµĞ¢Æ–æUö6FVv÷&–W2Ò²&ææ—fW'6&–W2"Â&†VÇF…÷f66–æF–öç2"Â&†VÇF…ö6†V6·W2"Â&†VÇF…öÖVF–6F–öç2"Â&†VÇF…öföÆÆ÷wW2"Â'FW7B'Ğ¢f÷"FVÆ—fW'’–â6W76–öâç66Æ'2‡6VÆV7B„Æ–æTFVÆ—fW'’’çv†W&R„Æ–æTFVÆ—fW'’çFVæçEö–BÓÒFVæçBæ–BÂÆ–æTFVÆ—fW'’æ6FVv÷'’æ–åò†Æ–æUö6FVv÷&–W2’’æ÷&FW%ö'’„Æ–æTFVÆ—fW'’æ7&VFVEöBæFW62‚’’æÆ–Ö—BƒS’’æÆÂ‚“ ¢—FV×2æVæB‚†FVÆ—fW'’æ7&VFVEöBÂ÷væW'2ævWB†FVÆ—fW'’çW6W%ö–BÂ.ûÈÒ"’÷".ûÈÒ"Â$Ä”ä^ûÈK‹¾˜	®yú^ûÈ’"ÂFVÆ—fW'’æ6FVv÷'’ÂFVÆ—fW'’ç7FGW2ÂFVÆ—fW'’æGFV×G2÷"ÂFVÆ—fW'’ç6VçEöBÂFVÆ—fW'’æW'&÷"÷".ûÈÒ"’¢–b&VÆFVEö–G3 ¢f÷"FVÆ—fW'’–â6W76–öâç66Æ'2‡6VÆV7B„VÖ–ÄFVÆ—fW'’’çv†W&R„VÖ–ÄFVÆ—fW'’çW6W%ö–Bæ–åò‡&VÆFVEö–G2’ÂVÖ–ÄFVÆ—fW'’çW'÷6Ræ–åò…²&†VÇF…÷&VÖ–æFW""Â&ææ—fW'6'’%Ò’’æ÷&FW%ö'’„VÖ–ÄFVÆ—fW'’æ7&VFVEöBæFW62‚’’æÆ–Ö—BƒS’’æÆÂ‚“ ¢—FV×2æVæB‚†FVÆ—fW'’æ7&VFVEöBÂ÷væW'2ævWB†FVÆ—fW'’çW6W%ö–BÂ.ûÈÒ"’÷".ûÈÒ"Â.8:8;Î8:¾ûÈK¨X)ûÈ’"ÂFVÆ—fW'’çW'÷6RÂFVÆ—fW'’ç7FGW2ÂFVÆ—fW'’æGFV×G2÷"ÂFVÆ—fW'’ç6VçEöBÂFVÆ—fW'’æW'&÷"÷".ûÈÒ"’¢f÷"&V6V—B–â6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç•W6…&V6V—B’çv†W&R„fÖ–Ç•W6…&V6V—BçW6W%ö–Bæ–åò‡&VÆFVEö–G2’Â„fÖ–Ç•W6…&V6V—BæFVGWUö¶W’æÆ–¶R‚'W6ƒ¦†VÇFƒ¢R"’ÂfÖ–Ç•W6…&V6V—BæFVGWUö¶W’æÆ–¶R‚'W6ƒ¦ææ—fW'6'“¢R"’’’æ÷&FW%ö'’„fÖ–Ç•W6…&V6V—Bæ7&VFVEöBæFW62‚’’æÆ–Ö—BƒS’’æÆÂ‚“ ¢6FVv÷'’Ò&ææ—fW'6'’"–b&ææ—fW'6'’"–â&V6V—BæFVGWUö¶W’VÇ6R&†VÇF‚ ¢—FV×2æVæB‚‡&V6V—Bæ7&VFVEöBÂ÷væW'2ævWB‡&V6V—BçW6W%ö–BÂ.ûÈÒ"’÷".ûÈÒ"Â.89n8:8*n8+nûÈK¨X)ûÈ’"Â6FVv÷'’Â&V6V—Bç7FGW2ÂÂ&V6V—Bæ7&VFVEöB–b&V6V—Bç7FGW2ÓÒ'6VçB"VÇ6RæöæRÂ.ûÈÒ"’¢6FVv÷'•öw&÷WÒÆÖ&FfÇVS¢&ææ—fW'6'’"–b&ææ—fW'6""–âfÇVRVÇ6R‚'FW7B"–bfÇVRÓÒ'FW7B"VÇ6R&†VÇF‚"¢6†ææVÅöÆ&VÇ2Ò²&Æ–æR#¢$Ä”ä^ûÈK‹¾˜	®yú^ûÈ’"Â&VÖ–Â#¢.8:8;Î8:¾ûÈK¨X)ûÈ’"Â&'&÷w6W"#¢.89n8:8*n8+nûÈK¨X)ûÈ’'Ó²æ÷&ÖÆ—¦VEö÷væW"Ò÷væW%ö¶W—v÷&Bç7G&—‚’æÆ÷vW"‚•³£Ğ¢—FV×2Ò¶—FVÒf÷"—FVÒ–â—FV×2–b†æ÷BFVÆ—fW'•÷7FGW2÷"—FVÕ³EÒÓÒFVÆ—fW'•÷7FGW2’æB†æ÷B6†ææVÂ÷"—FVÕ³%ÒÓÒ6†ææVÅöÆ&VÇ5¶6†ææVÅÒ’æ@¢†æ÷Bæ÷F–f–6F–öåö6FVv÷'’÷"6FVv÷'•öw&÷W†—FVÕ³5Ò’ÓÒæ÷F–f–6F–öåö6FVv÷'’’æB†æ÷B7F'Eöf–ÇFW"÷"—FVÕ³ÒæFFR‚’ãÒ7F'Eöf–ÇFW"’æ@¢†æ÷BVæEöf–ÇFW"÷"—FVÕ³ÒæFFR‚’ÃÒVæEöf–ÇFW"’æB†æ÷Bæ÷&ÖÆ—¦VEö÷væW"÷"æ÷&ÖÆ—¦VEö÷væW"–â—FVÕ³ÒæÆ÷vW"‚’•Ğ¢—FV×2ç6÷'B†¶W“ÖÆÖ&F—FVÓ¢—FVÕ³ÒÂ&WfW'6SÕG'VR¢&WGW&â—FV×5³£Ğ  ¤ævWB‚"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVbæ÷F–f–6F–öåöFVÆ—fW&–W5öÖævR‡&WG'“¢7G"Ò""ÂFVÆ—fW'•÷7FGW3¢7G"Ò""Â6†ææVÃ¢7G"Ò""Âæ÷F–f–6F–öåö6FVv÷'“¢7G"Ò""À¢FFUög&öÓ¢7G"Ò""ÂFFU÷Fó¢7G"Ò""Â÷væW%ö¶W—v÷&C¢7G"Ò""À¢66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢ÆÆ÷vVE÷7FGW6W2Ò²""Â'6VçB"Â&f–ÆVB"Â'VæF–ær'Ğ¢ÆÆ÷vVEö6†ææVÇ2Ò²""Â&Æ–æR"Â&VÖ–Â"Â&'&÷w6W"'Ğ¢ÆÆ÷vVEö6FVv÷&–W2Ò²""Â&ææ—fW'6'’"Â&†VÇF‚"Â'FW7B'Ğ¢–bFVÆ—fW'•÷7FGW2æ÷B–âÆÆ÷vVE÷7FGW6W2÷"6†ææVÂæ÷B–âÆÆ÷vVEö6†ææVÇ2÷"æ÷F–f–6F–öåö6FVv÷'’æ÷B–âÆÆ÷vVEö6FVv÷&–W3 ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jIÎ{J.iÚK»n8).z+®Š¨Ş8~8n8ş88^8B"¢G'“ ¢7F'Eöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFUög&öÒ’–bFFUög&öÒVÇ6RæöæP¢VæEöf–ÇFW"ÒFFRæg&öÖ—6öf÷&ÖB†FFU÷Fò’–bFFU÷FòVÇ6RæöæP¢W†6WBfÇVTW'&÷# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.jIÎ{J.iÉş™i>8).z+®Š¨Ş8~8n8ş88^8B"¢–b7F'Eöf–ÇFW"æBVæEöf–ÇFW"æB7F'Eöf–ÇFW"âVæEöf–ÇFW# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.{X.K¨niz^8ş™h¾Zx¾iz^Kº^™˜Ş8¾8~8n8ş88^8B"¢æ÷&ÖÆ—¦VEö÷væW"Ò÷væW%ö¶W—v÷&Bç7G&—‚’æÆ÷vW"‚•³£Ğ¢&VÆFVEö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—çW6W%ö–B’çv†W&R€¢Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚’¢÷væW'2Ò¶—FVÒæ–C¢—FVÒææÖRf÷"—FVÒ–â6W76–öâç66Æ'2‡6VÆV7B…W6W"’çv†W&R…W6W"æ–Bæ–åò‡&VÆFVEö–G2’’’æÆÂ‚—Ò–b&VÆFVEö–G2VÇ6R·Ğ¢—FV×3¢Æ—7E·GWÆU¶FFWF–ÖRÂ7G"Â7G"Â7G"Â7G"Â–çBÂFFWF–ÖRÂæöæRÂ7G"Â7G%ÕÒÒµĞ¢Æ–æUö6FVv÷&–W2Ò²&ææ—fW'6&–W2"Â&†VÇF…÷f66–æF–öç2"Â&†VÇF…ö6†V6·W2"Â&†VÇF…öÖVF–6F–öç2"Â&†VÇF…öföÆÆ÷wW2"Â'FW7B'Ğ¢Æ–æU÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„Æ–æTFVÆ—fW'’’çv†W&R€¢Æ–æTFVÆ—fW'’çFVæçEö–BÓÒFVæçBæ–BÂÆ–æTFVÆ—fW'’æ6FVv÷'’æ–åò†Æ–æUö6FVv÷&–W2¢’æ÷&FW%ö'’„Æ–æTFVÆ—fW'’æ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ#’’æÆÂ‚¢f÷"FVÆ—fW'’–âÆ–æU÷&V6÷&G3 ¢7F–öâÒ†brrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2öÆ–æR÷¶FVÆ—fW'’æ–GÒ÷&WG'’#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C·v†—FR×76S¦æ÷w&#ãÆ–çWBG—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&Õ÷&WG'’"fÇVSÒ'G'VR"7G–ÆSÒ'v–GFƒ¦WFò"&WV—&VCâXhŞ˜z+®Š¨ÓÂöÆ&VÃãÆ'WGFöâ6Æ73Ò'6V6öæF'’"7G–ÆSÒ&Ö&v–ã£G‚#äÄ”ä^XhŞ˜Âö'WGFöããÂöf÷&Óârrp¢–bFVÆ—fW'’ç7FGW2Ò'6VçB"æBFVÆ—fW'’æÖW76vRæBFVÆ—fW'’çF&vWE÷W&ÂVÇ6R.ûÈÒ"¢—FV×2æVæB‚†FVÆ—fW'’æ7&VFVEöBÂ÷væW'2ævWB†FVÆ—fW'’çW6W%ö–BÂ.ûÈÒ"’÷".ûÈÒ"Â$Ä”ä^ûÈK‹¾˜	®yú^ûÈ’"ÂFVÆ—fW'’æ6FVv÷'’À¢FVÆ—fW'’ç7FGW2ÂFVÆ—fW'’æGFV×G2÷"ÂFVÆ—fW'’ç6VçEöBÂFVÆ—fW'’æW'&÷"÷".ûÈÒ"Â7F–öâ’¢–b&VÆFVEö–G3 ¢VÖ–Å÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„VÖ–ÄFVÆ—fW'’’çv†W&R€¢VÖ–ÄFVÆ—fW'’çW6W%ö–Bæ–åò‡&VÆFVEö–G2’ÂVÖ–ÄFVÆ—fW'’çW'÷6Ræ–åò…²&†VÇF…÷&VÖ–æFW""Â&ææ—fW'6'’%Ò¢’æ÷&FW%ö'’„VÖ–ÄFVÆ—fW'’æ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ#’’æÆÂ‚¢f÷"FVÆ—fW'’–âVÖ–Å÷&V6÷&G3 ¢7F–öâÒ†brrsÆf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2öVÖ–Â÷¶FVÆ—fW'’æ–GÒ÷&WG'’#ãÆÆ&VÂ7G–ÆSÒ&föçB×vV–v‡C£C·v†—FR×76S¦æ÷w&#ãÆ–çWBG—SÒ&6†V6¶&÷‚"æÖSÒ&6öæf—&Õ÷&WG'’"fÇVSÒ'G'VR"7G–ÆSÒ'v–GFƒ¦WFò"&WV—&VCâXhŞ˜z+®Š¨ÓÂöÆ&VÃãÆ'WGFöâ6Æ73Ò'6V6öæF'’"7G–ÆSÒ&Ö&v–ã£G‚#î8:8;Î8:¾XhŞ˜Âö'WGFöããÂöf÷&Óârrp¢–bFVÆ—fW'’ç7FGW2Ò'6VçB"æBFVÆ—fW'’çW'÷6RÒ'77v÷&E÷&W6WB"VÇ6R.ûÈÒ"¢—FV×2æVæB‚†FVÆ—fW'’æ7&VFVEöBÂ÷væW'2ævWB†FVÆ—fW'’çW6W%ö–BÂ.ûÈÒ"’÷".ûÈÒ"Â.8:8;Î8:¾ûÈK¨X)ûÈ’"ÂFVÆ—fW'’çW'÷6RÀ¢FVÆ—fW'’ç7FGW2ÂFVÆ—fW'’æGFV×G2÷"ÂFVÆ—fW'’ç6VçEöBÂFVÆ—fW'’æW'&÷"÷".ûÈÒ"Â7F–öâ’¢W6…÷&V6÷&G2Ò6W76–öâç66Æ'2‡6VÆV7B„fÖ–Ç•W6…&V6V—B’çv†W&R€¢fÖ–Ç•W6…&V6V—BçW6W%ö–Bæ–åò‡&VÆFVEö–G2’À¢„fÖ–Ç•W6…&V6V—BæFVGWUö¶W’æÆ–¶R‚'W6ƒ¦†VÇFƒ¢R"’ÂfÖ–Ç•W6…&V6V—BæFVGWUö¶W’æÆ–¶R‚'W6ƒ¦ææ—fW'6'“¢R"’¢’æ÷&FW%ö'’„fÖ–Ç•W6…&V6V—Bæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ#’’æÆÂ‚¢f÷"&V6V—B–âW6…÷&V6÷&G3 ¢6FVv÷'’Ò&ææ—fW'6'’"–b&ææ—fW'6'’"–â&V6V—BæFVGWUö¶W’VÇ6R&†VÇF‚ ¢—FV×2æVæB‚‡&V6V—Bæ7&VFVEöBÂ÷væW'2ævWB‡&V6V—BçW6W%ö–BÂ.ûÈÒ"’÷".ûÈÒ"Â.89n8:8*n8+nûÈK¨X)ûÈ’"Â6FVv÷'’À¢&V6V—Bç7FGW2ÂÂ&V6V—Bæ7&VFVEöB–b&V6V—Bç7FGW2ÓÒ'6VçB"VÇ6RæöæRÂ.ûÈÒ"Â.ûÈÒ"’¢—FV×2ç6÷'B†¶W“ÖÆÖ&F—FVÓ¢—FVÕ³ÒÂ&WfW'6SÕG'VR¢—FV×2Ò—FV×5³£3Ğ¢6–æ6RÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’ÒF–ÖVFVÇF††÷W'3Ó#B¢7V66W75ö6÷VçBÒ7VÒƒf÷"—FVÒ–â—FV×2–b†—FVÕ³Ò–b—FVÕ³ÒçG¦–æfòVÇ6R—FVÕ³Òç&WÆ6R‡G¦–æfó×F–ÖW¦öæRçWF2’’ãÒ6–æ6RæB—FVÕ³EÒÓÒ'6VçB"¢f–ÆVEö6÷VçBÒ7VÒƒf÷"—FVÒ–â—FV×2–b†—FVÕ³Ò–b—FVÕ³ÒçG¦–æfòVÇ6R—FVÕ³Òç&WÆ6R‡G¦–æfó×F–ÖW¦öæRçWF2’’ãÒ6–æ6RæB—FVÕ³EÒæ÷B–â²'6VçB"Â'VæF–ær'Ò¢Æ7E÷6VçBÒÖ‚‚†—FVÕ³eÒf÷"—FVÒ–â—FV×2–b—FVÕ³eÒ’ÂFVfVÇCÔæöæR¢Æ&VÇ2Ò²&ææ—fW'6&–W2#¢.Š‰[û^izR"Â&ææ—fW'6'’#¢.Š‰[û^izR"Â&†VÇF…÷f66–æF–öç2#¢.8:ş8*ş888;2"Â&†VÇF…ö6†V6·W2#¢.X^Š‹¢"À¢&†VÇF…öÖVF–6F–öç2#¢.h©^‰jÂ"Â&†VÇF…öföÆÆ÷wW2#¢.XhŞŠ‹®8;¾{XÎ˜îz+®Š¨Ò"Â&†VÇF…÷&VÖ–æFW"#¢.X^[«~K¨Zé¢"Â&†VÇF‚#¢.X^[«~K¨Zé¢"Â'FW7B#¢.88n8+88‚'Ğ¢ÆÅö6÷VçBÒÆVâ†—FV×2¢FVb6FVv÷'•öw&÷W‡fÇVS¢7G"’Óâ7G# ¢–b&ææ—fW'6""–âfÇVS¢&WGW&â&ææ—fW'6'’ ¢–bfÇVRÓÒ'FW7B#¢&WGW&â'FW7B ¢&WGW&â&†VÇF‚ ¢6†ææVÅöÆ&VÇ2Ò²&Æ–æR#¢$Ä”ä^ûÈK‹¾˜	®yú^ûÈ’"Â&VÖ–Â#¢.8:8;Î8:¾ûÈK¨X)ûÈ’"Â&'&÷w6W"#¢.89n8:8*n8+nûÈK¨X)ûÈ’'Ğ¢—FV×2Ò¶—FVÒf÷"—FVÒ–â—FV×2–`¢†æ÷BFVÆ—fW'•÷7FGW2÷"—FVÕ³EÒÓÒFVÆ—fW'•÷7FGW2’æ@¢†æ÷B6†ææVÂ÷"—FVÕ³%ÒÓÒ6†ææVÅöÆ&VÇ5¶6†ææVÅÒ’æ@¢†æ÷Bæ÷F–f–6F–öåö6FVv÷'’÷"6FVv÷'•öw&÷W†—FVÕ³5Ò’ÓÒæ÷F–f–6F–öåö6FVv÷'’’æ@¢†æ÷B7F'Eöf–ÇFW"÷"—FVÕ³ÒæFFR‚’ãÒ7F'Eöf–ÇFW"’æ@¢†æ÷BVæEöf–ÇFW"÷"—FVÕ³ÒæFFR‚’ÃÒVæEöf–ÇFW"’æ@¢†æ÷Bæ÷&ÖÆ—¦VEö÷væW"÷"æ÷&ÖÆ—¦VEö÷væW"–â—FVÕ³ÒæÆ÷vW"‚’•Ğ¢7FGW5ö÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'·fÇVWÒ"²'6VÆV7FVB"–bFVÆ—fW'•÷7FGW2ÓÒfÇVRVÇ6R"'Óç¶Æ&VÇÓÂö÷F–öãârf÷"fÇVRÂÆ&VÂ–â‚‚""Â.888b"’Â‚'6VçB"Â.h‰X©ò"’Â‚&f–ÆVB"Â.ZKiYr"’Â‚'VæF–ær"Â.KùŞyY’"’’¢6†ææVÅö÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'·fÇVWÒ"²'6VÆV7FVB"–b6†ææVÂÓÒfÇVRVÇ6R"'Óç¶Æ&VÇÓÂö÷F–öãârf÷"fÇVRÂÆ&VÂ–â‚‚""Â.888b"’Â‚&Æ–æR"Â$Ä”äR"’Â‚&VÖ–Â"Â.8:8;Î8:²"’Â‚&'&÷w6W""Â.89n8:8*n8+b"’’¢6FVv÷'•ö÷F–öç2Ò""æ¦ö–â†bsÆ÷F–öâfÇVSÒ'·fÇVWÒ"²'6VÆV7FVB"–bæ÷F–f–6F–öåö6FVv÷'’ÓÒfÇVRVÇ6R"'Óç¶Æ&VÇÓÂö÷F–öãârf÷"fÇVRÂÆ&VÂ–â‚‚""Â.888b"’Â‚&†VÇF‚"Â.X^[«~K¨Zé¢"’Â‚&ææ—fW'6'’"Â.Š‰[û^izR"’Â‚'FW7B"Â.88n8+88‚"’’¢W‡÷'E÷VW'’ÒW&ÆVæ6öFR‡¶¶W“¢fÇVRf÷"¶W’ÂfÇVR–â²&FVÆ—fW'•÷7FGW2#¢FVÆ—fW'•÷7FGW2Â&6†ææVÂ#¢6†ææVÂÂ&æ÷F–f–6F–öåö6FVv÷'’#¢æ÷F–f–6F–öåö6FVv÷'’Â&FFUög&öÒ#¢FFUög&öÒÂ&FFU÷Fò#¢FFU÷FòÂ&÷væW%ö¶W—v÷&B#¢÷væW%ö¶W—v÷&E³£×Òæ—FV×2‚’–bfÇVWÒ¢77e÷W&ÂÒbröFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2÷&W÷'Bæ77g¶b#÷¶W‡÷'E÷VW'—Ò"–bW‡÷'E÷VW'’VÇ6R"'Òs²Fe÷W&ÂÒbröFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2÷&W÷'BçFg¶b#÷¶W‡÷'E÷VW'—Ò"–bW‡÷'E÷VW'’VÇ6R"'Òp¢6V&6…öf÷&ÒÒbrrsÆf÷&ÒÖWF†öCÒ&vWB"7F–öãÒ"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2#ãÆƒ#î˜XŞKú[^jÛN8).jIÎ{J#Âöƒ#ãÆF—b6Æ73Ò&w&–B#ãÆF—cãÆÆ&VÃî{YiéÃÂöÆ&VÃãÇ6VÆV7BæÖSÒ&FVÆ—fW'•÷7FGW2#ç·7FGW5ö÷F–öç7ÓÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃî˜XŞKú{XÎ‹zóÂöÆ&VÃãÇ6VÆV7BæÖSÒ&6†ææVÂ#ç¶6†ææVÅö÷F–öç7ÓÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃî˜	®yú^zŠîšãÂöÆ&VÃãÇ6VÆV7BæÖSÒ&æ÷F–f–6F–öåö6FVv÷'’#ç¶6FVv÷'•ö÷F–öç7ÓÂ÷6VÆV7CãÂöF—cãÆF—cãÆÆ&VÃî™h¾Zx¾izSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&FFUög&öÒ"fÇVSÒ'¶‡FÖÂæW66R†FFUög&öÒ—Ò#ãÂöF—cãÆF—cãÆÆ&VÃî{X.K¨nizSÂöÆ&VÃãÆ–çWBG—SÒ&FFR"æÖSÒ&FFU÷Fò"fÇVSÒ'¶‡FÖÂæW66R†FFU÷Fò—Ò#ãÂöF—cãÆF—cãÆÆ&VÃî8*®8;Î88®8;ÎYÓÂöÆ&VÃãÆ–çWBG—SÒ'6V&6‚"æÖSÒ&÷væW%ö¶W—v÷&B"fÇVSÒ'¶‡FÖÂæW66R†÷væW%ö¶W—v÷&E³£Ò—Ò"Ö†ÆVæwFƒÒ#"Æ6V†öÆFW#Ò.kşYŞ8îKˆ˜:‚#ãÂöF—cãÂöF—cãÆ'WGFöãî[^jÛN8).jIÎ{J#Âö'WGFöãâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2#îiÚK»n8).8*ş8:®8*#ÂöâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ'¶77e÷W&ÇÒ#îŠzK®iÚK»n8t55nX{®X©³ÂöâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ'·Fe÷W&ÇÒ#îŠzK®iÚK»n8uDnX{®X©³ÂöãÂöf÷&ÓãÇãÇ7G&öæsç¶ÆVâ†—FV×2—ŞK»cÂ÷7G&öæsîûÈşXZ‡¶ÆÅö6÷VçGŞK»n8).ŠzK£Â÷ârrp¢&÷w2Ò""æ¦ö–â†brrsÇG#ãÇFCç¶7&VFVBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†÷væW"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†6†ææVÂ—ÓÂ÷FCà¢ÇFCç¶‡FÖÂæW66R†Æ&VÇ2ævWB†6FVv÷'’Â6FVv÷'’’—ÓÂ÷FCãÇFCãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R‡7FGW2—ÓÂ÷7ããÂ÷FCãÇFCç¶GFV×G7ÓÂ÷FCà¢ÇFCç·6VçEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–b6VçEöBVÇ6R.ûÈÒ'ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†W'&÷"—ÓÂ÷FCãÇFCç¶7F–öçÓÂ÷FCãÂ÷G#ârrp¢f÷"7&VFVBÂ÷væW"Â6†ææVÂÂ6FVv÷'’Â7FGW2ÂGFV×G2Â6VçEöBÂW'&÷"Â7F–öâ–â—FV×2¢&WG'•öæ÷F–6RÒ²'6VçB#¢sÇ6Æ73Ò'FVæçB#ãÇ7G&öæsîXhŞ˜8¾h‰X©ş8~8î8~8ş8#Â÷7G&öæsãÂ÷ârÂ&f–ÆVB#¢sÇ6Æ73Ò&W'&÷"#îXhŞ˜8¾ZKiY~8~8î8~8ş8.ZKiY~ynyK8˜XŞKúŠŠŞZé®8).z+®Š¨Ş8~8n8ş88^8N8#Â÷âwÒævWB‡&WG'’Â""¢&öG’ÒbrrsÆƒîX^[«~8;¾Š‰[û^iz^˜	®yú^8î˜XŞKú[^jÛCÂöƒç·&WG'•öæ÷F–6WÓÇäÄ”ä^8).K‹¾˜	®yú^88:8;Î8:¾889n8:8*n8+n˜	®yú^8).K¨X){XÎ‹zş88~8n8î88(8nz+®Š¨Ş8~8î88#Â÷à¢ÆF—b6Æ73Ò&w&–B#ãÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsã#Ni˜.™i>8îh‰X©óÂ÷7G&öæsãÆƒ#ç·7V66W75ö6÷VçGŞK»cÂöƒ#ãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsã#Ni˜.™i>8îZKiYsÂ÷7G&öæsãÆƒ"6Æ73Ò'²vW'&÷"r–bf–ÆVEö6÷VçBVÇ6RrwÒ#ç¶f–ÆVEö6÷VçGŞK»cÂöƒ#ãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsîiÈ{X.˜XŞKúiz^i˜#Â÷7G&öæsãÆƒ#ç¶Æ7E÷6VçBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–bÆ7E÷6VçBVÇ6R.˜XŞKú8®8r'ÓÂöƒ#ãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsîK‹¾˜	®yúSÂ÷7G&öæsãÆƒ#äÄ”äSÂöƒ#ãÇ6ÖÆÃî8:8;Î8:¾8;¾89n8:8*n8+n8şK¨X)“Â÷6ÖÆÃãÂöF—cãÂöF—cà¢ÇãÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öfÖ–Ç’öÆ–æRöÖævR#äÄ”ä^XZÎ[ÈşŠŠŞZé£ÂöâÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öFÖ–âöVÖ–ÂÖFVÆ—fW&–W2#î8:8;Î8:¾˜Kú[^jÛCÂöãÂ÷à¢·6V&6…öf÷&×Ğ¢ÆF—b7G–ÆSÒ&÷fW&fÆ÷r×ƒ¦WFò#ãÇF&ÆSãÇG#ãÇFƒîKÙÎh‰iz^i˜#Â÷FƒãÇFƒî8*®8;Î88®8;ÃÂ÷FƒãÇFƒî{XÎ‹zóÂ÷FƒãÇFƒîzŠîšãÂ÷FƒãÇFƒî{YiéÃÂ÷FƒãÇFƒîŠšnŠÃÂ÷FƒãÇFƒîiÈ{X.˜XŞKúÂ÷FƒãÇFƒîZKiY~ynyKÂ÷FƒãÇFƒîi8ŞKÙÃÂ÷FƒãÂ÷G#à¢·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#’#îiÚK»n8¾Kˆˆ{N88(¾˜XŞKú[^jÛN8ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSãÂöF—cârrp¢&WGW&âÆ–÷WB‚.˜	®yú^˜XŞKú[^jÛB"Â&öG’Â7F÷"  ¤ævWB‚"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2÷&W÷'Bæ77b"¦FVbæ÷F–f–6F–öåöFVÆ—fW&–W5÷&W÷'Eö77b†FVÆ—fW'•÷7FGW3¢7G"Ò""Â6†ææVÃ¢7G"Ò""Âæ÷F–f–6F–öåö6FVv÷'“¢7G"Ò""ÂFFUög&öÓ¢7G"Ò""ÂFFU÷Fó¢7G"Ò""Â÷væW%ö¶W—v÷&C¢7G"Ò""Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢—FV×2Òæ÷F–f–6F–öåöFVÆ—fW'•öW‡÷'Eö—FV×2‡FVæçBÂFVÆ—fW'•÷7FGW2Â6†ææVÂÂæ÷F–f–6F–öåö6FVv÷'’ÂFFUög&öÒÂFFU÷FòÂ÷væW%ö¶W—v÷&BÂ6W76–öâ¢Æ&VÇ2Ò²&ææ—fW'6&–W2#¢.Š‰[û^izR"Â&ææ—fW'6'’#¢.Š‰[û^izR"Â&†VÇF…÷f66–æF–öç2#¢.8:ş8*ş888;2"Â&†VÇF…ö6†V6·W2#¢.X^Š‹¢"Â&†VÇF…öÖVF–6F–öç2#¢.h©^‰jÂ"Â&†VÇF…öföÆÆ÷wW2#¢.XhŞŠ‹®8;¾{XÎ˜îz+®Š¨Ò"Â&†VÇF…÷&VÖ–æFW"#¢.X^[«~K¨Zé¢"Â&†VÇF‚#¢.X^[«~K¨Zé¢"Â'FW7B#¢.88n8+88‚'Ğ¢FVb6fUö77eö6VÆÂ‡fÇVR’Óâ7G# ¢FW‡E÷fÇVRÒ7G"‡fÇVR÷"""’ç&WÆ6R‚%Çƒ"Â""¢&WGW&â"r"²FW‡E÷fÇVR–bFW‡E÷fÇVRç7F'G7v—F‚‚‚#Ò"Â"²"Â"Ò"Â$"’’VÇ6RFW‡E÷fÇVP¢÷WGWBÒ–òå7G&–æt”ò†æWvÆ–æSÒ""“²w&—FW"Ò77bçw&—FW"†÷WGWB“²w&—FW"çw&—FW&÷r…².KÙÎh‰iz^i˜""Â.8*®8;Î88®8;Â"Â.˜XŞKú{XÎ‹zò"Â.˜	®yú^zŠîšâ"Â.{YiéÂ"Â.ŠšnŠÎY¹îi["Â.iÈ{X.˜XŞKúiz^i˜""Â.ZKiY~ynyK%Ò¢f÷"7&VFVBÂ÷væW"ÂFVÆ—fW'•ö6†ææVÂÂ6FVv÷'’Â7FGW5÷fÇVRÂGFV×G2Â6VçEöBÂW'&÷"–â—FV×3 ¢w&—FW"çw&—FW&÷r…·6fUö77eö6VÆÂ‡fÇVR’f÷"fÇVR–â¶7&VFVBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’Â÷væW"ÂFVÆ—fW'•ö6†ææVÂÂÆ&VÇ2ævWB†6FVv÷'’Â6FVv÷'’’Â7FGW5÷fÇVRÂGFV×G2Â6VçEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–b6VçEöBVÇ6R""Â""–bW'&÷"ÓÒ.ûÈÒ"VÇ6RW'&÷%ÕÒ¢&WGW&â&W7öç6R†6öçFVçCÒ%ÇVfVfb"²÷WGWBævWGfÇVR‚’ÂÖVF–÷G—SÒ'FW‡Bö77c²6†'6WC×WFbÓ‚"Â†VFW'3×²$6öçFVçBÔF—7÷6—F–öâ#¢bvGF6†ÖVçC²f–ÆVæÖSÒ&æ÷F–f–6F–öâÖFVÆ—fW&–W2×FVæçB×·FVæçBæ–GÒæ77b"rÂ$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R'Ò  ¤ævWB‚"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2÷&W÷'BçFb"¦FVbæ÷F–f–6F–öåöFVÆ—fW&–W5÷&W÷'E÷Fb†FVÆ—fW'•÷7FGW3¢7G"Ò""Â6†ææVÃ¢7G"Ò""Âæ÷F–f–6F–öåö6FVv÷'“¢7G"Ò""ÂFFUög&öÓ¢7G"Ò""ÂFFU÷Fó¢7G"Ò""Â÷væW%ö¶W—v÷&C¢7G"Ò""Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢—FV×2Òæ÷F–f–6F–öåöFVÆ—fW'•öW‡÷'Eö—FV×2‡FVæçBÂFVÆ—fW'•÷7FGW2Â6†ææVÂÂæ÷F–f–6F–öåö6FVv÷'’ÂFFUög&öÒÂFFU÷FòÂ÷væW%ö¶W—v÷&BÂ6W76–öâ¢Æ&VÇ2Ò²&ææ—fW'6&–W2#¢.Š‰[û^izR"Â&ææ—fW'6'’#¢.Š‰[û^izR"Â&†VÇF…÷f66–æF–öç2#¢.8:ş8*ş888;2"Â&†VÇF…ö6†V6·W2#¢.X^Š‹¢"Â&†VÇF…öÖVF–6F–öç2#¢.h©^‰jÂ"Â&†VÇF…öföÆÆ÷wW2#¢.XhŞŠ‹®8;¾{XÎ˜îz+®Š¨Ò"Â&†VÇF…÷&VÖ–æFW"#¢.X^[«~K¨Zé¢"Â&†VÇF‚#¢.X^[«~K¨Zé¢"Â'FW7B#¢.88n8+88‚'Ğ¢÷WGWBÒ–òä'—FW4”ò‚“²FfÖWG&–72ç&Vv—7FW$föçB…Væ–6öFT4”DföçB‚$†V—6V”¶·TvòÕsR"’“²FbÒ6çf2ä6çf2†÷WGWBÂvW6—¦SÖÆæG66R„B’“²v–GF‚Â†V–v‡BÒÆæG66R„B¢6öæF—F–öç2Ò‚"ò"æ¦ö–â†f–ÇFW"„æöæRÂ¶b.{YiéÃ§¶FVÆ—fW'•÷7FGW7Ò"–bFVÆ—fW'•÷7FGW2VÇ6R""Âb.{XÎ‹zó§¶6†ææVÇÒ"–b6†ææVÂVÇ6R""Âb.zŠîšã§¶æ÷F–f–6F–öåö6FVv÷'—Ò"–bæ÷F–f–6F–öåö6FVv÷'’VÇ6R""Âb.iÉş™i3§¶FFUög&öÒ÷"~hÈ~Zé®8®8rwŞ8	Ç¶FFU÷Fò÷"~hÈ~Zé®8®8rwÒ"–bFFUög&öÒ÷"FFU÷FòVÇ6R""Âb.8*®8;Î88®8;Ã§¶÷væW%ö¶W—v÷&E³£3×Ò"–b÷væW%ö¶W—v÷&BVÇ6R"%Ò’’÷".888b"’ç&WÆ6R‚%Æâ"Â""’ç&WÆ6R‚%Ç""Â""¢FVbG&uö†VFW"‚“ ¢Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"ÂB“²FbæG&u7G&–ærƒ#‚Â†V–v‡BÒ3Âb'·FVæçBææÖWÒ˜	®yú^˜XŞKú[^jÛB"¢Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Â‚“²FbæG&u7G&–ærƒ#‚Â†V–v‡BÒCRÂb.X{®X©¾iz^ûÉ§¶FFRçFöF’‚“¢U[›BVŞiÈ‚VNizWŞ8iÚK»nûÉ§¶6öæF—F–öç5³£×Ş8K»ni[ûÉ§¶ÆVâ†—FV×2—ŞK»b"¢f÷"‚ÂÆ&VÂ–â¦—…³#‚Â"Â#Â3RÂ3ƒÂC3RÂCsRÂScUÒÂ².KÙÎh‰iz^i˜""Â.8*®8;Î88®8;Â"Â.{XÎ‹zò"Â.zŠîšâ"Â.{YiéÂ"Â.ŠšnŠÂ"Â.iÈ{X.˜XŞKú"Â.ZKiY~ynyK%Ò“¢FbæG&u7G&–ær‡‚Â†V–v‡BÒcBÂÆ&VÂ¢G&uö†VFW"‚“²’Ò†V–v‡BÒƒ²Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Âr¢f÷"7&VFVBÂ÷væW"ÂFVÆ—fW'•ö6†ææVÂÂ6FVv÷'’Â7FGW5÷fÇVRÂGFV×G2Â6VçEöBÂW'&÷"–â—FV×3 ¢–b’Â#ƒ¢Fbç6†÷uvR‚“²G&uö†VFW"‚“²’Ò†V–v‡BÒƒ²Fbç6WDföçB‚$†V—6V”¶·TvòÕsR"Âr¢fÇVW2Ò¶7&VFVBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’Â÷væW%³£UÒÂFVÆ—fW'•ö6†ææVÅ³£5ÒÂÆ&VÇ2ævWB†6FVv÷'’Â6FVv÷'’•³£ÒÂ7FGW5÷fÇVU³£…ÒÂ7G"†GFV×G2’Â6VçEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–b6VçEöBVÇ6R.ûÈÒ"ÂW'&÷%³£C%ÕĞ¢f÷"‚ÂfÇVR–â¦—…³#‚Â"Â#Â3RÂ3ƒÂC3RÂCsRÂScUÒÂfÇVW2“¢FbæG&u7G&–ær‡‚Â’ÂfÇVR¢’ÓÒ@¢Fbç6fR‚¢&WGW&â&W7öç6R†6öçFVçCÖ÷WGWBævWGfÇVR‚’ÂÖVF–÷G—SÒ&Æ–6F–öâ÷Fb"Â†VFW'3×²$6öçFVçBÔF—7÷6—F–öâ#¢bvGF6†ÖVçC²f–ÆVæÖSÒ&æ÷F–f–6F–öâÖFVÆ—fW&–W2×FVæçB×·FVæçBæ–GÒçFb"rÂ$66†RÔ6öçG&öÂ#¢'&—fFRÂæò×7F÷&R'Ò  ¤ç÷7B‚"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2öÆ–æR÷¶FVÆ—fW'•ö–GÒ÷&WG'’"¦FVbæ÷F–f–6F–öåöÆ–æUöFVÆ—fW'•÷&WG'’†FVÆ—fW'•ö–C¢–çBÂ6öæf—&Õ÷&WG'“¢&ööÂÒf÷&Ò„fÇ6R’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢–bæ÷B6öæf—&Õ÷&WG'“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XhŞ˜8îz+®Š¨Ş8Î[ø^Šh8~8’"¢FVÆ—fW'’Ò6W76–öâævWB„Æ–æTFVÆ—fW'’ÂFVÆ—fW'•ö–B¢–bæ÷BFVÆ—fW'’÷"FVÆ—fW'’çFVæçEö–BÒFVæçBæ–B÷"FVÆ—fW'’ç7FGW2ÓÒ'6VçB"÷"æ÷BFVÆ—fW'’æÖW76vR÷"æ÷BFVÆ—fW'’çF&vWE÷W&Ã ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6VçBÒ6VæEöÆ–æU÷W6‚†FVÆ—fW'’çW6W%ö–BÂFVÆ—fW'’çFVæçEö–BÂFVÆ—fW'’æ6FVv÷'’ÂFVÆ—fW'’æÖW76vRÂFVÆ—fW'’çF&vWE÷W&ÂÂFVÆ—fW'’æFVGWUö¶W’Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W3÷&WG'“×²w6VçBr–b6VçBVÇ6Rvf–ÆVBwÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W2öVÖ–Â÷¶FVÆ—fW'•ö–GÒ÷&WG'’"¦FVbæ÷F–f–6F–öåöVÖ–ÅöFVÆ—fW'•÷&WG'’†FVÆ—fW'•ö–C¢–çBÂ6öæf—&Õ÷&WG'“¢&ööÂÒf÷&Ò„fÇ6R’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢òÂFVæçBÒ66W70¢–bæ÷B6öæf—&Õ÷&WG'“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCÂFWF–ÃÒ.XhŞ˜8îz+®Š¨Ş8Î[ø^Šh8~8’"¢FVÆ—fW'’Ò6W76–öâævWB„VÖ–ÄFVÆ—fW'’ÂFVÆ—fW'•ö–B¢–bæ÷BFVÆ—fW'’÷"FVÆ—fW'’ç7FGW2ÓÒ'6VçB"÷"FVÆ—fW'’çW'÷6RÓÒ'77v÷&E÷&W6WB# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&VÆFVBÒFVÆ—fW'’çFVæçEö–BÓÒFVæçBæ–B÷"†FVÆ—fW'’çW6W%ö–BæB6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R€¢Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—çW6W%ö–BÓÒFVÆ—fW'’çW6W%ö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR¢’’¢–bæ÷B&VÆFVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢6VçBÒFVÆ—fW%öVÖ–Â†FVÆ—fW'’Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R†b"öFÖ–âöæ÷F–f–6F–öâÖFVÆ—fW&–W3÷&WG'“×²w6VçBr–b6VçBVÇ6Rvf–ÆVBwÒ"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öFÖ–âöVÖ–ÂÖFVÆ—fW&–W2÷¶FVÆ—fW'•ö–GÒ÷&WG'’"¦FVbVÖ–ÅöFVÆ—fW'•÷&WG'’†FVÆ—fW'•ö–C¢–çBÂ66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢FVÆ—fW'’Ò6W76–öâævWB„VÖ–ÄFVÆ—fW'’ÂFVÆ—fW'•ö–B¢–bæ÷BFVÆ—fW'’÷"FVÆ—fW'’ç7FGW2ÓÒ'6VçB"÷"FVÆ—fW'’çW'÷6RÓÒ'77v÷&E÷&W6WB# ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢&VÆFVBÒFVÆ—fW'’çFVæçEö–BÓÒFVæçBæ–B÷"†FVÆ—fW'’çW6W%ö–BæB6W76–öâç66Æ"‡6VÆV7B„Föt÷væW'6†—æ–B’çv†W&R€¢Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—çW6W%ö–BÓÒFVÆ—fW'’çW6W%ö–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR¢’’¢–bæ÷B&VÆFVC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢FVÆ—fW%öVÖ–Â†FVÆ—fW'’Â6W76–öâ¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öFÖ–âöVÖ–ÂÖFVÆ—fW&–W2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"öFÖ–âö÷W&F–öç2"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVb÷W&F–öç5öF6†&ö&B†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢6–æ6RÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’ÒF–ÖVFVÇF††÷W'3Ó#B¢WfVçEö6öæF—F–öâÒ„÷W&F–öäWfVçBçFVæçEö–BÓÒFVæçBæ–B¢–b7F÷"çÆFf÷&ÕöFÖ–ã ¢WfVçEö6öæF—F–öâÒWfVçEö6öæF—F–öâÂ÷W&F–öäWfVçBçFVæçEö–Bæ—5ò„æöæR¢WfVçG2Ò6W76–öâç66Æ'2‡6VÆV7B„÷W&F–öäWfVçB’çv†W&R†WfVçEö6öæF—F–öâ¢æ÷&FW%ö'’„÷W&F–öäWfVçBæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ’’æÆÂ‚¢f–ÆVEöWfVçG2Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„÷W&F–öäWfVçBæ–B’’çv†W&R€¢WfVçEö6öæF—F–öâÂ÷W&F–öäWfVçBç7FGW2ÓÒ&f–ÆVB"Â÷W&F–öäWfVçBæ7&VFVEöBãÒ6–æ6R’’÷" ¢&VÆFVEö–G2Ò6WB‡6W76–öâç66Æ'2‡6VÆV7B„Föt÷væW'6†—çW6W%ö–B’çv†W&R€¢Föt÷væW'6†—çFVæçEö–BÓÒFVæçBæ–BÂFöt÷væW'6†—æ7F—fRæ—5ò…G'VR’’’æÆÂ‚’¢VÖ–Åö6öæF—F–öâÒ„VÖ–ÄFVÆ—fW'’çFVæçEö–BÓÒFVæçBæ–B¢–b&VÆFVEö–G3 ¢VÖ–Åö6öæF—F–öâÒVÖ–Åö6öæF—F–öâÂVÖ–ÄFVÆ—fW'’çW6W%ö–Bæ–åò‡&VÆFVEö–G2¢f–ÆVEöVÖ–Ç2Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„VÖ–ÄFVÆ—fW'’æ–B’’çv†W&R€¢VÖ–Åö6öæF—F–öâÂVÖ–ÄFVÆ—fW'’ç7FGW2ÓÒ&f–ÆVB"ÂVÖ–ÄFVÆ—fW'’æ7&VFVEöBãÒ6–æ6R’’÷" ¢7F—fU÷W6‚Ò6W76–öâç66Æ"‡6VÆV7B†gVæ2æ6÷VçB„fÖ–Ç•W6…7V'67&—F–öâæ–B’’çv†W&R€¢fÖ–Ç•W6…7V'67&—F–öâçW6W%ö–Bæ–åò‡&VÆFVEö–G2’ÂfÖ–Ç•W6…7V'67&—F–öâæ7F—fRæ—5ò…G'VR’’’÷"–b&VÆFVEö–G2VÇ6R ¢Æ7Eö&6·WÒ6W76–öâç66Æ"‡6VÆV7B„fÖ–Ç”&6·WVF—B’çv†W&R„fÖ–Ç”&6·WVF—BçFVæçEö–BÓÒFVæçBæ–B¢æ÷&FW%ö'’„fÖ–Ç”&6·WVF—Bæ7&VFVEöBæFW62‚’’æÆ–Ö—Bƒ’¢&÷w2Ò""æ¦ö–â†brrsÇG#ãÇFCç¶—FVÒæ7&VFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒæ6FVv÷'’—ÓÂ÷FCà¢ÇFCãÇ7â6Æ73Ò&&FvR#ç¶‡FÖÂæW66R†—FVÒç7FGW2—ÓÂ÷7ããÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒç7VÖÖ'’—ÓÂ÷FCãÇFCç¶‡FÖÂæW66R†—FVÒæFWF–Ç2÷".ûÈÒ"—ÓÂ÷FCãÂ÷G#ârrrf÷"—FVÒ–âWfVçG2¢&6·W÷7FFRÒÆ7Eö&6·Wæ7&VFVEöBç7G&gF–ÖR‚"U’ÒVÒÒVBTƒ¢TÒ"’–bÆ7Eö&6·WVÇ6R.iÊ®KÙÎh‰ ¢&öG’ÒbrrsÆƒî˜¾yJyº>ŠicÂöƒãÇî˜	®yú^88988>8*ş8*.88>89~88+~8+88n8:ŠŠŞZé®8îx«nhX¾8).8î88(8nz+®Š¨Ş8~8Ş8î88#Â÷à¢ÆF—b6Æ73Ò&w&–B#ãÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsî8:8;Î8:¾˜XŞKúÂ÷7G&öæsãÆƒ#ç².z‹ÎX8ŞKŠÒ"–b6×G÷&VG’‚’VÇ6R.ŠŠŞZé®[è^8'ÓÂöƒ#ãÇ6ÖÆÃã#Ni˜.™i>8îZKiYr¶f–ÆVEöVÖ–Ç7ŞK»cÂ÷6ÖÆÃãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsî89n8:8*n8+n˜	®yúSÂ÷7G&öæsãÆƒ#ç².z‹ÎX8ŞKŠÒ"–bW6…÷&VG’‚’VÇ6R.XÎjÚ"'ÓÂöƒ#ãÇ6ÖÆÃîiÈX«zºşiÊ²¶7F—fU÷W6‡ŞXûÂ÷6ÖÆÃãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsî˜¾yJ8*N898;>88ƒÂ÷7G&öæsãÆƒ#ç¶f–ÆVEöWfVçG7ŞK»cÂöƒ#ãÇ6ÖÆÃã#Ni˜.™i>8îy[[‹ƒÂ÷6ÖÆÃãÂöF—cà¢ÆF—b6Æ73Ò'FVæçB#ãÇ7G&öæsîiÈ{X.8988>8*ş8*.88>89sÂ÷7G&öæsãÆƒ#ç¶&6·W÷7FFWÓÂöƒ#ãÇ6ÖÆÃîX{®X©¾[^jÛN8).Yû®k©n8¾ŠzK£Â÷6ÖÆÃãÂöF—cãÂöF—cà¢Æf÷&ÒÖWF†öCÒ'÷7B"7F–öãÒ"öFÖ–âö÷W&F–öç2öF–væ÷6R#ãÆ'WGFöâ6Æ73Ò'6V6öæF'’#îK¸®888+~8+88n8:Š‹®ijÓÂö'WGFöããÂöf÷&Óà¢Æƒ#î˜¾yJ8*N898;>88[^jÛCÂöƒ#ãÇF&ÆSãÇG#ãÇFƒîiz^i˜#Â÷FƒãÇFƒîXˆnšãÂ÷FƒãÇFƒîx«nhX³Â÷FƒãÇFƒîjh.ŠhÂ÷FƒãÇFƒîŠ›>{KÂ÷FƒãÂ÷G#ç·&÷w2÷"sÇG#ãÇFB6öÇ7ãÒ#R#î˜¾yJ8*N898;>888ş8.8(®8î8¾8)>8#Â÷FCãÂ÷G#âwÓÂ÷F&ÆSârrp¢&WGW&âÆ–÷WB‚.˜¾yJyº>Šib"Â&öG’Â7F÷"  ¤ç÷7B‚"öFÖ–âö÷W&F–öç2öF–væ÷6R"¦FVb÷W&F–öç5öF–væ÷6R†66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢6†V6·2Ò²&FF&6R#¢G'VRÂ'W6‚#¢W6…÷&VG’‚’Â&VÖ–Â#¢6×G÷&VG’‚—Ğ¢7FGW5÷fÇVRÒ'7V66W72"–b6†V6·5²&FF&6R%ÒæB6†V6·5²'W6‚%ÒVÇ6R'v&æ–ær ¢&V6÷&Eö÷W&F–öâ‡6W76–öâÂ&F–væ÷7F–2"Â7FGW5÷fÇVRÂ.zêynˆ^8Î8+~8+88n8:Š‹®ijŞ8).ZéşŠÎ8~8î8~8ò"ÂFVæçBæ–BÀ¢§6öâæGV×2†6†V6·2ÂVç7W&Uö66–“ÔfÇ6R’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öFÖ–âö÷W&F–öç2"Â7FGW5ö6öFSÓ32  ¤ç÷7B‚"öFÖ–â÷77v÷&B×&W6WG2÷·&WVW7Eö–GÒö—77VR"Â&W7öç6Uö6Æ73Ô…DÔÅ&W7öç6R¦FVb77v÷&E÷&W6WEö—77VR‡&WVW7Eö–C¢–çBÂFÖ–å÷77v÷&C¢7G"Òf÷&Ò‚âââ’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢7F÷"ÂFVæçBÒ66W70¢&WVW7Eö—FVÒÒ6W76–öâævWB…77v÷&E&W6WE&WVW7BÂ&WVW7Eö–B¢–bæ÷B&WVW7Eö—FVÒ÷"&WVW7Eö—FVÒç&W6öÇfVEöC ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓCB¢66÷VçBÂòÒVÖ–Åö6†ævU÷F&vWB‡&WVW7Eö—FVÒçW6W%ö–BÂ7F÷"ÂFVæçBÂ6W76–öâ¢–bæ÷B77v÷&G2çfW&–g’†FÖ–å÷77v÷&BÂ7F÷"ç77v÷&Eö†6‚“ ¢&—6R…EEW†6WF–öâ‡7FGW5ö6öFSÓC2ÂFWF–ÃÒ.zêynˆ^898+8:ş8;Î888Î˜^8N8î8’"¢&u÷Fö¶VâÒ6V7&WG2çFö¶Vå÷W&Ç6fRƒ3"¢6W76–öâæFB…77v÷&E&W6WEFö¶Vâ‡W6W%ö–CÖ66÷VçBæ–BÂFö¶Våö†6ƒ×Fö¶Våö†6‚‡&u÷Fö¶Vâ’ÂW‡—&W5öCÖFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2’²F–ÖVFVÇF†Ö–çWFW3Ó3’Â7&VFVEö'•ö–CÖ7F÷"æ–B’¢&WVW7Eö—FVÒç&W6öÇfVEöBÒFFWF–ÖRææ÷r‡F–ÖW¦öæRçWF2¢6W76–öâæ6öÖÖ—B‚¢&6U÷W&ÂÒ÷2æVçf—&öâævWB‚$ô$4UõU$Â"Â&‡GG3¢òöFörÖÖævVÖVçBæ&VæVf—BÖæf’æ6öÒ"’ç'7G&—‚"ò"¢Æ–æ²Òb'¶&6U÷W&ÇÒ÷&W6WB×77v÷&B÷·&u÷Fö¶VçÒ ¢&öG’ÒbrrsÆ6Æ73Ò&'WGFöâ6V6öæF'’"‡&VcÒ"öFÖ–â÷77v÷&B×&W6WG2#îKˆŠj~8h‹¾8(³ÂöãÆƒîXhŞŠŠŞZé®8:®8;>8*ş8).y›®ŠÎ8~8î8~8óÂöƒà¢ÆF—b6Æ73Ò'FVæçB#ãÇî8>8îyK¾™Ú.8).™h88(¾8XhŞŠzK®8~8Ş8î8¾8)>8.iÊÎK«®z+®Š¨Şkˆ8ş8î8*®8;Î88®8;Îjy88®KÉŞ88ş88^8N8#Â÷à¢ÆÆ&VÃîiÈX«iÉş™™3Xˆn8î8:®8;>8*óÂöÆ&VÃãÇFW‡F&V&VFöæÇ’7G–ÆSÒ&Ö–âÖ†V–v‡C£#‚#ç¶‡FÖÂæW66R†Æ–æ²—ÓÂ÷FW‡F&VãÂöF—cârrp¢&WGW&âÆ–÷WB‚.XhŞŠŠŞZé®8:®8;>8*şy›®ŠÂ"Â&öG’Â7F÷"  ¤ç÷7B‚"öFÖ–â÷W6W'2"¦FVbÖVÖ&W'6†—öFB†VÖ–Ã¢7G"Òf÷&Ò‚âââ’Â&öÆS¢&öÆRÒf÷&Ò‚âââ’Â66W73ÔFWVæG2‡&WV—&U÷FVæçEöFÖ–â’Â6W76–öã¢6W76–öâÒFWVæG2†F"’“ ¢W6W"ÂFVæçBÒ66W70¢66÷VçBÒ6W76–öâç66Æ"‡6VÆV7B…W6W"’çv†W&R…W6W"æVÖ–ÂÓÒæ÷&ÖÆ—¦UöVÖ–Â†VÖ–Â’’¢–bæ÷B66÷VçC ¢&WGW&â…DÔÅ&W7öç6R†Æ–÷WB‚.8*8:8;Â"ÂsÇ6Æ73Ò&W'&÷"#îXX8¾8®Zê.jyy›¾˜Ë.8î8ş8ş8:n8;Î8+n8;Îy›¾˜Ë.8).8~8n8ş88^8N8#Â÷ãÆ‡&VcÒ"öFÖ–â÷W6W'2#îh‹¾8(³ÂöârÂW6W"’¢ÖVÖ&W"Ò6W76–öâç66Æ"‡6VÆV7B„ÖVÖ&W'6†—’çv†W&R„ÖVÖ&W'6†—çFVæçEö–BÓÒFVæçBæ–BÂÖVÖ&W'6†—çW6W%ö–BÓÒ66÷VçBæ–B’¢–bÖVÖ&W# ¢ÖVÖ&W"ç&öÆRÒ&öÆP¢VÇ6S ¢6W76–öâæFB„ÖVÖ&W'6†—‡FVæçEö–C×FVæçBæ–BÂW6W%ö–CÖ66÷VçBæ–BÂ&öÆS×&öÆR’¢6W76–öâæ6öÖÖ—B‚¢&WGW&â&VF—&V7E&W7öç6R‚"öFÖ–â÷W6W'2"Â7FGW5ö6öFSÓ32  ¤ævWB‚"ö†VÇF‚"¦FVb†VÇF‚‚“ ¢&WGW&â²&ö²#¢G'VRÂ'W6…÷&VG’#¢W6…÷&VG’‚’Â&VÖ–Å÷&VG’#¢6×G÷&VG’‚’Â&•÷fW'6–öâ#¢'c'Ğ  ¦æÖ÷VçB‚"öÖ7"ÂÖ7ç76Uö†Ö÷VçE÷FƒÒ"öÖ7"’