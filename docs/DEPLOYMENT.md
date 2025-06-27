# 🚀 EP-X: GCPデプロイ手順書 (完全版)

このドキュメントは、EP-XバックエンドをGoogle Cloud Runにデプロイするための完全な手順書です。
あの激闘を忘れないために、ここに全てを記録します。

## 🔥 0. 前提条件 (Prerequisites)

- `gcloud` CLIがインストールされ、認証済みであること。
  ```
  gcloud auth login
  gcloud config set project edge-presence-x-mvp-463704
  ```
- `Docker`がインストールされていること。
- このリポジトリがローカルにクローンされていること。

## 💎 1. 秘密の鍵を準備！(Secret Manager)

EP-Xは、GoogleのAIサービスと会話するために「サービスアカウントキー」を、感情分析のために「Dialogflow」を使います。（もし他の外部APIキーが必要な場合も同様に準備します）

### 1-1. 必要なAPIを有効化

Cloud Runが他のGCPサービスと連携するために、必要なAPIを有効化します。

```
gcloud services enable secretmanager.googleapis.com
gcloud services enable dialogflow.googleapis.com
gcloud services enable speech.googleapis.com
gcloud services enable aiplatform.googleapis.com
```

### 1-2. Secret Managerに秘密情報を登録

（このプロジェクトでは現在直接のAPIキーは使っていませんが、将来的に必要になった場合の手順です）
例えば、`SOME_API_KEY`という秘密情報を登録する場合：

```
# YOUR_SECRET_API_KEYは実際のキーに置き換えてね！
echo -n "YOUR_SECRET_API_KEY" | gcloud secrets create some-api-secret --data-file=-
```

## 🚀 2. 二段ロケット方式でビルド！ (Two-Stage Build)

EP-Xは依存ライブラリが多く、ビルドに時間がかかります。そのため、**「時間がかかる土台（baseイメージ）」**と**「一瞬で終わるアプリ本体」**を分離する「二段ロケット方式」を採用します。

### 2-1. 第一段ロケット (土台イメージのビルド)

`requirements.txt`の全ライブラリをインストールした、超頑丈な土台イメージを作成します。この作業は時間がかかるため、ハイスペックマシンを指定します。

```
# cloudbuild.base.yaml を使って、土台となるイメージをビルド
gcloud builds submit --config cloudbuild.base.yaml .
```
このコマンドは、`cloudbuild.base.yaml`の設定（`machineType: 'N1_HIGHCPU_8'` と `timeout: 3600s`）を読み込んで実行します。ビルドには10分以上かかりますが、気長に待ちましょう。

### 2-2. 第二段ロケット (アプリ本体のビルド)

土台が完成したら、その上にアプリのソースコードを乗せるだけの、一瞬で終わるビルドを実行します。

```
# cloudbuild.yaml を使って、最終的なアプリケーションイメージをビルド
gcloud builds submit --config cloudbuild.yaml .
```

## 🛰️ 3. Cloud Runに発射！ (Deploy to Cloud Run)

全ての準備が整いました。完成したコンテナをCloud Runにデプロイします！

```
# --set-env-vars で、アプリが必要とする環境変数を渡すのがポイント！
gcloud run deploy ep-x-backend \
  --image gcr.io/edge-presence-x-mvp-463704/ep-x-backend:latest \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars="VERTEX_AI_PROJECT=edge-presence-x-mvp-463704"
```
もしSecret Managerに登録したキーを使う場合は、`--set-secrets`オプションを追加します。
```
# 例：
# --set-secrets="SOME_API_KEY_ENV_NAME=some-api-secret:latest"
```

これでデプロイは完了です！お疲れ様でした！✨ 