# Dog-kanri-app

FastAPI・PostgreSQLで動く犬管理Webアプリです。管理者、従業員、お客様の3権限に対応しています。

## ログイン機能

- お客様：`/register` から自分で登録
- 従業員・管理者：管理者が「ユーザー管理」から発行
- パスワード：Argon2でハッシュ化して保存
- セッション：ランダムトークンをDBに保存し、HttpOnly Cookieで管理
- 権限：サーバー側で管理者専用ページへのアクセスを制限

## 起動

`.env` を作成し、初期管理者情報を設定してください。

```env
INITIAL_ADMIN_NAME=管理者名
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=十分に長く推測されにくいパスワード
COOKIE_SECURE=false
```

```bash
docker compose up --build
```

ブラウザで `http://localhost:8080` を開きます。本番のHTTPS環境では `COOKIE_SECURE=true` にしてください。

## 主なURL

- `/login` ログイン
- `/register` お客様登録
- `/dashboard` 権限別ホーム
- `/admin/users` 管理者専用ユーザー管理
- `/health` 稼働確認
- `/mcp/sse` MCP接続先

本番運用前に `.env` の初期パスワードを必ず変更してください。
