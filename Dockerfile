# Dockerfile
ARG CACHE_BUSTER=unknown

# ベースとなるPythonのイメージを指定
FROM python:3.12-slim

# コンテナの中での作業場所を設定
WORKDIR /app

# 🔽🔽🔽 ココが超重要！ 🔽🔽🔽
# PyAudioのビルドに必要なライブラリを先にインストールする
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    portaudio19-dev \
    libasound-dev \
    libc6-dev

# 最初に必要なライブラリの一覧だけコピー
COPY requirements.txt .

# ライブラリをインストール
# --no-cache-dir はコンテナサイズを小さくするおまじない
RUN pip install --no-cache-dir -r requirements.txt

# --- ここからが本番 ---

# せんぱい、ここがマジで重要！設定ファイルを全部コンテナにコピーするよ！📝
# これで gemini_config.json も gcp-key.json も確実に入る！
COPY ./config ./config

# アプリのソースコードを全部コピー
COPY ./src ./src

# コンテナが起動したときに実行するコマンド
# FastAPIをポート8000で起動するよ
CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
