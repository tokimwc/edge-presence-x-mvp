FROM python:3.11-slim

WORKDIR /app

# まずはrequirements.txtをコピーして、ライブラリをインストール
# これを先にやることで、コードの変更だけだとDockerのキャッシュが効いてビルドが爆速になるっしょ！
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# その後に、アプリケーションコードを全部コピー
COPY . .

# FastAPIが動くポートを開けとく
EXPOSE 8080

# コンテナが起動したら、このコマンドでサーバーを起動！
# main.pyの中のappインスタンスを、0.0.0.0の8080ポートで動かすよん
CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8080"] 