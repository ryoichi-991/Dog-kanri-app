# Dog-kanri-app — DB付き Web アプリ + MCP サーバー（両方入り）
# FastAPI で Web ページ(/)と MCP(/mcp/sse)を提供し、PostgreSQL も使えます。
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, text
from mcp.server.fastmcp import FastMCP

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://app:app@db:5432/Dog_kanri_app")
# pool_pre_ping=True で接続は使う時まで遅延（起動時にDB未起動でも落ちない）
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

# ── AI から使えるツール（MCP） ──
mcp = FastMCP("Dog-kanri-app")

@mcp.tool()
def add(a: int, b: int) -> int:
    """2つの整数を足し算して返す（サンプル）。"""
    return a + b

@mcp.tool()
def db_now() -> str:
    """データベースの現在時刻を返す（DB接続のサンプル）。"""
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT now()")).scalar())

# ── 通常の Web アプリ ──
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def index():
    return "<h1>🗄️ Dog-kanri-app</h1><p>DB付き Web アプリ + MCP（接続先: /mcp/sse）が動作中です。</p>"

@app.get("/health")
def health():
    return {"ok": True}

# MCP を /mcp にマウント（Claude からの接続先は  /mcp/sse ）
app.mount("/mcp", mcp.sse_app(mount_path="/mcp"))
