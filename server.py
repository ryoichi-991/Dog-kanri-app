import hashlib
import html
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.context import CryptContext
from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, String, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from mcp.server.fastmcp import FastMCP

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://app:app@db:5432/Dog_kanri_app")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "7"))
BOOTSTRAP_TOKEN = os.environ.get("BOOTSTRAP_TOKEN", "")
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
    role: Mapped[Role] = mapped_column(SQLEnum(Role), default=Role.customer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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


def admin_exists(session: Session) -> bool:
    return session.scalar(select(User.id).where(User.role == Role.admin).limit(1)) is not None


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


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="管理者のみ利用できます")
    return user


def layout(title: str, body: str, user: User | None = None) -> str:
    nav = ""
    if user:
        admin_link = '<a href="/admin/users">ユーザー管理</a>' if user.role == Role.admin else ""
        nav = f'<nav><a href="/dashboard">ホーム</a>{admin_link}<form method="post" action="/logout"><button>ログアウト</button></form></nav>'
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
    <style>body{{margin:0;background:#f6f7fb;color:#24304a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:760px;margin:48px auto;padding:0 20px}}.card{{background:white;padding:32px;border-radius:18px;box-shadow:0 8px 30px #18233b12}}h1{{margin-top:0}}label{{display:block;margin:16px 0 6px}}input,select{{box-sizing:border-box;width:100%;padding:12px;border:1px solid #cfd5e2;border-radius:10px;font-size:16px}}button,.button{{display:inline-block;margin-top:20px;padding:12px 20px;border:0;border-radius:10px;background:#244b86;color:white;text-decoration:none;font-size:15px;cursor:pointer}}.error{{background:#fff0f0;color:#9d2020;padding:12px;border-radius:8px}}nav{{background:#182b4b;padding:14px max(20px,calc((100% - 760px)/2));display:flex;gap:22px;align-items:center}}nav a,nav button{{color:white;background:none;margin:0;padding:0}}nav form{{margin-left:auto}}table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{text-align:left;padding:12px 8px;border-bottom:1px solid #e7eaf0}}.badge{{padding:4px 8px;border-radius:99px;background:#e8eef8;font-size:12px}}</style></head><body>{nav}<main><div class="card">{body}</div></main></body></html>'''


mcp = FastMCP("Dog-kanri-app")


@mcp.tool()
def add(a: int, b: int) -> int:
    return a + b


@mcp.tool()
def db_now() -> str:
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT now()")).scalar())


app = FastAPI(title="Dog-kanri-app")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    email = normalize_email(os.environ.get("INITIAL_ADMIN_EMAIL", ""))
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    if email and password:
        with SessionLocal() as session:
            if not session.scalar(select(User).where(User.email == email)):
                session.add(User(name=os.environ.get("INITIAL_ADMIN_NAME", "管理者"), email=email, password_hash=passwords.hash(password), role=Role.admin))
                session.commit()


@app.get("/", response_class=HTMLResponse)
def index(user: User | None = Depends(current_user), session: Session = Depends(db)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    if not admin_exists(session):
        return RedirectResponse("/setup", status_code=303)
    return layout("Dog管理アプリ", '<h1>Dog管理アプリ</h1><p>犬舎・従業員・お客様をつなぐ管理システムです。</p><a class="button" href="/login">ログイン</a>　<a href="/register">お客様登録</a>')


@app.get("/setup", response_class=HTMLResponse)
def setup_page(session: Session = Depends(db)):
    if admin_exists(session):
        return RedirectResponse("/login", status_code=303)
    if not BOOTSTRAP_TOKEN:
        return layout("初期設定", '<h1>初期設定が必要です</h1><p class="error">サーバーに BOOTSTRAP_TOKEN が設定されていません。環境変数を設定して再起動してください。</p>')
    return layout("初期管理者登録", '<h1>初期管理者登録</h1><p>管理者がまだ登録されていません。最初の管理者を作成します。</p><form method="post"><label>お名前</label><input name="name" required maxlength="100"><label>メールアドレス</label><input name="email" type="email" required><label>パスワード（12文字以上）</label><input name="password" type="password" minlength="12" required><label>セットアップキー</label><input name="bootstrap_token" type="password" required autocomplete="off"><button>初期管理者を登録</button></form>')


@app.post("/setup", response_class=HTMLResponse)
def setup(name: str = Form(...), email: str = Form(...), password: str = Form(...), bootstrap_token: str = Form(...), session: Session = Depends(db)):
    if not BOOTSTRAP_TOKEN or not secrets.compare_digest(bootstrap_token, BOOTSTRAP_TOKEN):
        return layout("初期設定エラー", '<p class="error">セットアップキーが違います。</p><a href="/setup">戻る</a>')
    if len(password) < 12:
        return layout("初期設定エラー", '<p class="error">管理者パスワードは12文字以上にしてください。</p><a href="/setup">戻る</a>')
    # 同時送信があっても、最初の1人だけを管理者にする。
    session.execute(text("SELECT pg_advisory_xact_lock(20260824)"))
    if admin_exists(session):
        session.rollback()
        return RedirectResponse("/login", status_code=303)
    email = normalize_email(email)
    if session.scalar(select(User).where(User.email == email)):
        session.rollback()
        return layout("初期設定エラー", '<p class="error">このメールアドレスは既にお客様として登録されています。別のメールアドレスを使用してください。</p><a href="/setup">戻る</a>')
    session.add(User(name=name.strip(), email=email, password_hash=passwords.hash(password), role=Role.admin))
    session.commit()
    return RedirectResponse("/login?setup=1", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page():
    return layout("お客様登録", '<h1>お客様登録</h1><form method="post"><label>お名前</label><input name="name" required maxlength="100"><label>メールアドレス</label><input name="email" type="email" required><label>パスワード（8文字以上）</label><input name="password" type="password" minlength="8" required><button>登録する</button></form><p><a href="/login">ログインへ戻る</a></p>')


@app.post("/register", response_class=HTMLResponse)
def register(name: str = Form(...), email: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    email = normalize_email(email)
    if len(password) < 8:
        return layout("登録エラー", '<p class="error">パスワードは8文字以上にしてください。</p><a href="/register">戻る</a>')
    if session.scalar(select(User).where(User.email == email)):
        return layout("登録エラー", '<p class="error">このメールアドレスは既に登録されています。</p><a href="/login">ログインする</a>')
    session.add(User(name=name.strip(), email=email, password_hash=passwords.hash(password), role=Role.customer))
    session.commit()
    return RedirectResponse("/login?registered=1", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(registered: int = 0, setup: int = 0):
    notice = "<p>初期管理者の登録が完了しました。ログインしてください。</p>" if setup else ("<p>登録が完了しました。ログインしてください。</p>" if registered else "")
    return layout("ログイン", f'<h1>ログイン</h1>{notice}<form method="post"><label>メールアドレス</label><input name="email" type="email" required autofocus><label>パスワード</label><input name="password" type="password" required><button>ログイン</button></form><p>お客様は <a href="/register">新規登録</a> できます。</p>')


@app.post("/login", response_class=HTMLResponse)
def login(email: str = Form(...), password: str = Form(...), session: Session = Depends(db)):
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not user.active or not passwords.verify(password, user.password_hash):
        return layout("ログイン", '<h1>ログイン</h1><p class="error">メールアドレスまたはパスワードが違います。</p><a href="/login">もう一度入力する</a>')
    raw_token = secrets.token_urlsafe(32)
    session.add(LoginSession(token_hash=token_hash(raw_token), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    session.commit()
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("dog_session", raw_token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=SESSION_DAYS * 86400)
    return response


@app.post("/logout")
def logout(request: Request, session: Session = Depends(db)):
    token = request.cookies.get("dog_session")
    if token:
        login = session.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash(token)))
        if login:
            session.delete(login)
            session.commit()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("dog_session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(user: User = Depends(require_user)):
    labels = {Role.admin: "管理者", Role.employee: "従業員", Role.customer: "お客様"}
    descriptions = {Role.admin: "全ユーザーの登録・権限・利用状態を管理できます。", Role.employee: "担当業務とお客様・犬の情報を管理する画面です。", Role.customer: "ご自身の犬の情報や記録を確認する画面です。"}
    return layout("ホーム", f'<h1>{html.escape(user.name)}さん、こんにちは</h1><p><span class="badge">{labels[user.role]}</span></p><p>{descriptions[user.role]}</p>', user)


@app.get("/admin/users", response_class=HTMLResponse)
def user_list(admin: User = Depends(require_admin), session: Session = Depends(db)):
    users = session.scalars(select(User).order_by(User.created_at.desc())).all()
    labels = {Role.admin: "管理者", Role.employee: "従業員", Role.customer: "お客様"}
    rows = "".join(f"<tr><td>{html.escape(u.name)}</td><td>{html.escape(u.email)}</td><td>{labels[u.role]}</td><td>{'有効' if u.active else '停止'}</td></tr>" for u in users)
    body = f'<h1>ユーザー管理</h1><a class="button" href="/admin/users/new">ユーザーを追加</a><table><thead><tr><th>名前</th><th>メール</th><th>権限</th><th>状態</th></tr></thead><tbody>{rows}</tbody></table>'
    return layout("ユーザー管理", body, admin)


@app.get("/admin/users/new", response_class=HTMLResponse)
def new_user_page(admin: User = Depends(require_admin)):
    body = '<h1>ユーザー追加</h1><form method="post"><label>お名前</label><input name="name" required maxlength="100"><label>メールアドレス</label><input name="email" type="email" required><label>初期パスワード（8文字以上）</label><input name="password" type="password" minlength="8" required><label>権限</label><select name="role"><option value="employee">従業員</option><option value="customer">お客様</option><option value="admin">管理者</option></select><button>追加する</button></form>'
    return layout("ユーザー追加", body, admin)


@app.post("/admin/users/new", response_class=HTMLResponse)
def new_user(name: str = Form(...), email: str = Form(...), password: str = Form(...), role: Role = Form(...), admin: User = Depends(require_admin), session: Session = Depends(db)):
    email = normalize_email(email)
    if len(password) < 8 or session.scalar(select(User).where(User.email == email)):
        return layout("追加エラー", '<p class="error">入力内容を確認してください。メールアドレスは重複できず、パスワードは8文字以上必要です。</p><a href="/admin/users/new">戻る</a>', admin)
    session.add(User(name=name.strip(), email=email, password_hash=passwords.hash(password), role=role))
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/health")
def health():
    return {"ok": True}


app.mount("/mcp", mcp.sse_app(mount_path="/mcp"))
