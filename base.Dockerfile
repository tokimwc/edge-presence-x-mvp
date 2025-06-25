# base.Dockerfile

# ここではフル機能のPythonイメージを使って、C言語のコンパイルもできるようにする
FROM python:3.12 as builder

# ビルドに必要なシステムライブラリを全部インストール！
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    gcc \
    portaudio19-dev \
    libasound-dev \
    libc6-dev \
    libjack-jackd2-dev

# 作業ディレクトリ設定
WORKDIR /app

# requirements.txtをコピーして、ライブラリをビルド済みのwheel形式で準備
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# --- ここからが本番用の土台イメージ ---
FROM python:3.12-slim

# 作業ディレクトリ設定
WORKDIR /app

# ビルド環境からシステムライブラリをコピー
COPY --from=builder /usr/lib/x86_64-linux-gnu/libportaudio.so.2 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libasound.so.2 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libjack.so.0 /usr/lib/x86_64-linux-gnu/

# ビルド環境で作成したホイール（ビルド済みライブラリ）をコピーしてインストール
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*
