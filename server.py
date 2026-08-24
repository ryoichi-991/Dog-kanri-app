import hashlib
import html
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from mcp.server.fastmcp import FastMCP
from passlib.context import CryptContext
from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, String, UniqueConstraint, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://app:app@db:5432/Dog_kanri_app")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "7"))
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
passwords = CryptContext(schemes=["argon2"], deprecated="auto")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Membership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(SQLEnum(Role, name="membership_role"))


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
    query = select(Tenant).where(Tenant.active.is_(True)).order_by(Tenant.name)
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


def layout(title: str, body: str, user: User | None = None) -> str:
    nav = ""
    if user:
        platform_link = '<a href="/platform/tenants">テナント管理</a>' if user.platform_admin else ""
        nav = f'<nav><a href="/dashboard">ホーム</a><a href="/admin/users">ユーザー管理</a>{platform_link}<form method="post" action="/logout"><button>ログアウト</button></form></nav>'
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{margin:0;background:#f6f7fb;color:#24304a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:850px;margin:45px auto;padding:0 20px}}.card{{background:#fff;padding:32px;border-radius:18px;box-shadow:0 8px 30px #18233b12}}h1{{margin-top:0}}label{{display:block;margin:16px 0 6px}}input,select{{box-sizing:border-box;width:100%;padding:12px;border:1px solid #cfd5e2;border-radius:10px;font-size:16px}}button,.button{{display:inline-block;margin-top:18px;padding:12px 20px;border:0;border-radius:10px;background:#244b86;color:#fff;text-decoration:none;cursor:pointer}}.secondary{{background:#68748a}}.error{{background:#fff0f0;color:#9d2020;padding:12px;border-radius:8px}}nav{{background:#182b4b;padding:14px max(20px,calc((100% - 850px)/2));display:flex;gap:20px;align-items:center}}nav a,nav button{{color:#fff;background:none;margin:0;padding:0}}nav form{{margin-left:auto}}table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{text-align:left;padding:11px 7px;border-bottom:1px solid #e7eaf0}}.badge{{padding:4px 8px;border-radius:99px;background:#e8eef8;font-size:12px}}.tenant{{padding:16px;background:#eef3fa;border-radius:12px;margin-bottom:24px}}</style></head><body>{nav}<main><div class="card">{body}</div></main></body></html>'''


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
    return layout("ホーム", f'<h1>{html.escape(user.name)}さん、こんにちは</h1>{switcher}<p><span class="badge">{label}</span></p>', user)


@app.get("/platform/tenants", response_class=HTMLResponse)
def tenant_list(user: User = Depends(require_user), session: Session = Depends(db)):
    if not user.platform_admin:
        raise HTTPException(status_code=403)
    tenants = session.scalars(select(Tenant).order_by(Tenant.name)).all()
    rows = "".join(f"<tr><td>{html.escape(t.name)}</td><td>{'有効' if t.active else '停止'}</td></tr>" for t in tenants)
    return layout("テナント管理", f'<h1>テナント管理</h1><form method="post"><label>新しい会社・犬舎名</label><input name="name" required maxlength="150"><button>作成する</button></form><table><tr><th>名称</th><th>状態</th></tr>{rows}</table>', user)


@app.post("/platform/tenants")
def tenant_create(name: str = Form(...), user: User = Depends(require_user), session: Session = Depends(db)):
    if not user.platform_admin:
        raise HTTPException(status_code=403)
    if session.scalar(select(Tenant).where(Tenant.name == name.strip())):
        return HTMLResponse(layout("エラー", '<p class="error">同じ名前のテナントがあります。</p><a href="/platform/tenants">戻る</a>', user))
    session.add(Tenant(name=name.strip()))
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
