# Dockerfile

# 🔽🔽🔽 ココがマジ重要！さっき作った土台イメージをFROMする！ 🔽🔽🔽
FROM gcr.io/edge-presence-x-mvp-463704/ep-x-backend-base:latest

# 作業ディレクトリ設定
WORKDIR /app

# ソースコードをコピーするだけ！一瞬で終わる！
COPY . .

# サーバー起動コマンド
CMD exec uvicorn src.backend.main:app --host 0.0.0.0 --port $PORT
