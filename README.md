# Dog-kanri-app

FastAPI・PostgreSQLで動くマルチテナント型の犬管理Webアプリです。

## マルチテナント

- 運営管理者だけが会社・犬舎（テナント）を作成
- 運営管理者は全テナントを閲覧・編集
- 1人のユーザーが複数テナントに所属可能
- ログイン後に利用するテナントを切り替え
- 管理者・従業員・お客様の権限はテナントごとに設定
- 既存ユーザーは初回起動時に「初期テナント」へ自動移行

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

運営管理者が1人もいない場合は `/setup` に移動します。管理者名・
メールアドレス・最初の会社／犬舎名・8文字以上のパスワードを
入力してください。登録後、初期設定画面は自動的に無効になります。

## 主なURL

- `/login` ログイン
- `/setup` 初回のみの管理者登録
- `/register` お客様登録
- `/dashboard` 権限別ホーム
- `/tenant/switch` 所属テナントの切り替え
- `/admin/users` 選択中テナントのユーザー管理
- `/platform/tenants` 運営管理者専用テナント管理
- `/health` 稼働確認
- `/mcp/sse` MCP接続先

本番運用前に `.env` の初期パスワードを必ず変更してください。
