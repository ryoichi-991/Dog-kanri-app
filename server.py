import hashlib
import html
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from mcp.server.fastmcp import FastMCP
from passlib.context import CryptContext
from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

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
    sex: Mapped[str] = mapped_column(String(10))
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    microchip_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pedigree_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(20), default="parent")
    status: Mapped[str] = mapped_column(String(30), default="resident")
    sire_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id"), nullable=True)
    dam_id: Mapped[int | None] = mapped_column(ForeignKey("dogs.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


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


class PuppySale(Base):
    __tablename__ = "puppy_sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"))
    customer_name: Mapped[str] = mapped_column(String(150))
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contract_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    handover_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="inquiry")


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


def layout(title: str, body: str, user: User | None = None) -> str:
    nav = ""
    if user:
        platform_link = '<a href="/platform/tenants">テナント管理</a>' if user.platform_admin else ""
        nav = f'<nav><a href="/dashboard">ホーム</a><a href="/admin/users">ユーザー管理</a>{platform_link}<form method="post" action="/logout"><button>ログアウト</button></form></nav>'
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{margin:0;background:#f6f7fb;color:#24304a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1050px;margin:45px auto;padding:0 20px}}.card{{background:#fff;padding:32px;border-radius:18px;box-shadow:0 8px 30px #18233b12}}h1{{margin-top:0}}label{{display:block;margin:16px 0 6px}}input,select,textarea{{box-sizing:border-box;width:100%;padding:12px;border:1px solid #cfd5e2;border-radius:10px;font-size:16px}}button,.button{{display:inline-block;margin-top:18px;padding:12px 20px;border:0;border-radius:10px;background:#244b86;color:#fff;text-decoration:none;cursor:pointer}}.secondary{{background:#68748a}}.danger{{background:#a53232}}.success{{background:#247346}}.inline{{display:inline}}.inline button{{margin:3px;padding:8px 11px}}.error{{background:#fff0f0;color:#9d2020;padding:12px;border-radius:8px}}nav{{background:#182b4b;padding:14px max(20px,calc((100% - 1050px)/2));display:flex;gap:20px;align-items:center}}nav a,nav button{{color:#fff;background:none;margin:0;padding:0}}nav form{{margin-left:auto}}table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{text-align:left;padding:11px 7px;border-bottom:1px solid #e7eaf0}}.badge{{padding:4px 8px;border-radius:99px;background:#e8eef8;font-size:12px}}.tenant{{padding:16px;background:#eef3fa;border-radius:12px;margin-bottom:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin-top:22px}}.module{{display:block;padding:20px;border:1px solid #dce3ef;border-radius:14px;text-decoration:none;color:#24304a;background:#fbfcff}}.module:hover{{border-color:#244b86;box-shadow:0 5px 16px #18233b12}}.module h3{{margin:0 0 8px}}.module p{{margin:0;color:#68748a;font-size:14px}}</style></head><body>{nav}<main><div class="card">{body}</div></main></body></html>'''


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
    Base.metadata.create_all(engine)
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
    response = RedirectResponse("/dashboard", status_code=303)
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
    tenant = selected_tenant(request, user, session)
    options = "".join(f'<option value="{t.id}" {"selected" if tenant and t.id == tenant.id else ""}>{html.escape(t.name)}</option>' for t in tenants)
    switcher = f'<div class="tenant"><form method="post" action="/tenant/switch"><label>表示する会社・犬舎</label><select name="tenant_id">{options}</select><button>切り替える</button></form></div>' if tenants else '<p class="error">所属テナントがありません。管理者へ連絡してください。</p>'
    role = tenant_role(user, tenant, session)
    label = "運営管理者" if user.platform_admin else ({Role.admin: "管理者", Role.employee: "従業員", Role.customer: "お客様"}.get(role, "未所属"))
    dog_count = session.scalar(select(func.count(Dog.id)).where(Dog.tenant_id == tenant.id)) if tenant else 0
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
        breeding_rows += f"<tr><td>{html.escape(dam.call_name)}</td><td>{html.escape(sire.call_name)}</td><td>{record.mating_date}</td><td>{record.mating_date + timedelta(days=63)}</td><td>{html.escape(record.status)}</td></tr>"
    body = f'''<h1>交配・ヒート管理</h1>
    <h2>ヒート記録</h2><form method="post" action="/modules/breeding/heat"><div class="grid"><div><label>母犬</label><select name="dog_id" required>{female_options}</select></div><div><label>ヒート開始日</label><input name="start_date" type="date" required></div></div><label>メモ</label><textarea name="notes"></textarea><button>ヒートを登録</button></form>
    <table><tr><th>母犬</th><th>開始日</th><th>次回予測</th></tr>{heat_rows}</table>
    <h2>交配記録</h2><form method="post" action="/modules/breeding/mating"><div class="grid"><div><label>母犬</label><select name="dam_id" required>{female_options}</select></div><div><label>父犬</label><select name="sire_id" required>{male_options}</select></div><div><label>1回目交配日</label><input name="mating_date" type="date" required></div><div><label>交配方法</label><select name="method"><option value="natural">自然交配</option><option value="artificial">人工授精</option></select></div></div><label>メモ</label><textarea name="notes"></textarea><button>交配を登録</button></form>
    <table><tr><th>母犬</th><th>父犬</th><th>交配日</th><th>出産予定日</th><th>状態</th></tr>{breeding_rows}</table>'''
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
    session.add(BreedingRecord(tenant_id=tenant.id, sire_id=sire.id, dam_id=dam.id, mating_date=mated, status="mated", notes=note))
    session.add(TaskEvent(tenant_id=tenant.id, dog_id=dam.id, title=f"{dam.call_name} 出産予定", category="breeding", due_date=mated + timedelta(days=63)))
    session.commit()
    return RedirectResponse("/modules/breeding", status_code=303)


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


@app.get("/modules/dogs", response_class=HTMLResponse)
def dogs_page(access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    dogs = session.scalars(select(Dog).where(Dog.tenant_id == tenant.id).order_by(Dog.call_name)).all()
    category_labels = {"parent": "親犬", "puppy": "子犬", "external": "外部犬"}
    status_labels = {"resident": "在舎中", "reserved": "予約済", "delivered": "引渡済", "retired": "引退", "transferred": "譲渡済"}
    rows = "".join(f"<tr><td>{html.escape(d.call_name)}</td><td>{category_labels.get(d.category, d.category)}</td><td>{html.escape(d.registered_name or '-')}</td><td>{'牡' if d.sex == 'male' else '牝'}</td><td>{d.birth_date or '-'}</td><td>{status_labels.get(d.status, d.status)}</td></tr>" for d in dogs)
    body = f'''<h1>犬・血統書管理</h1><p>{html.escape(tenant.name)}の犬だけが表示されます。</p>
    <form method="post"><div class="grid"><div><label>区分</label><select name="category"><option value="parent">親犬</option><option value="puppy">子犬</option><option value="external">外部犬</option></select></div><div><label>呼び名</label><input name="call_name" required></div><div><label>血統書名</label><input name="registered_name"></div><div><label>性別</label><select name="sex"><option value="male">牡</option><option value="female">牝</option></select></div><div><label>状態</label><select name="status"><option value="resident">在舎中</option><option value="reserved">予約済</option><option value="delivered">引渡済</option><option value="retired">引退</option><option value="transferred">譲渡済</option></select></div><div><label>生年月日</label><input name="birth_date" type="date"></div><div><label>毛色</label><input name="color"></div><div><label>マイクロチップ番号</label><input name="microchip_no"></div><div><label>血統書番号</label><input name="pedigree_no"></div></div><button>犬を登録</button></form>
    <table><tr><th>呼び名</th><th>区分</th><th>血統書名</th><th>性別</th><th>生年月日</th><th>状態</th></tr>{rows}</table>'''
    return layout("犬・血統書管理", body, user)


@app.post("/modules/dogs")
def dog_create(call_name: str = Form(...), registered_name: str = Form(""), sex: str = Form(...), category: str = Form("parent"), status: str = Form("resident"), birth_date: str = Form(""), color: str = Form(""), microchip_no: str = Form(""), pedigree_no: str = Form(""), access=Depends(require_tenant_user), session: Session = Depends(db)):
    user, tenant = access
    if sex not in {"male", "female"}:
        raise HTTPException(status_code=400)
    parsed_birth = date.fromisoformat(birth_date) if birth_date else None
    if category not in {"parent", "puppy", "external"} or status not in {"resident", "reserved", "delivered", "retired", "transferred"}:
        raise HTTPException(status_code=400)
    session.add(Dog(tenant_id=tenant.id, call_name=call_name.strip(), registered_name=registered_name.strip() or None, sex=sex, category=category, status=status, birth_date=parsed_birth, color=color.strip() or None, microchip_no=microchip_no.strip() or None, pedigree_no=pedigree_no.strip() or None))
    session.commit()
    return RedirectResponse("/modules/dogs", status_code=303)


@app.get("/modules/{module_key}", response_class=HTMLResponse)
def module_page(module_key: str, access=Depends(require_tenant_user), session: Session = Depends(db)):
    if module_key not in MODULES or module_key in {"dogs", "todo", "calendar", "breeding", "births"}:
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


@app.get("/admin/users", response_class=HTMLResponse)
def user_list(request: Request, access=Depends(require_tenant_admin), session: Session = Depends(db)):
    user, tenant = access
    memberships = session.scalars(select(Membership).where(Membership.tenant_id == tenant.id)).all()
    rows = ""
    for member in memberships:
        account = session.get(User, member.user_id)
        rows += f"<tr><td>{html.escape(account.name)}</td><td>{html.escape(account.email)}</td><td>{member.role.value}</td></tr>"
    body = f'<h1>{html.escape(tenant.name)}のユーザー</h1><form method="post"><label>登録済みユーザーのメールアドレス</label><input name="email" type="email" required><label>権限</label><select name="role"><option value="employee">従業員</option><option value="customer">お客様</option><option value="admin">管理者</option></select><button>所属を追加</button></form><table><tr><th>名前</th><th>メール</th><th>権限</th></tr>{rows}</table>'
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
