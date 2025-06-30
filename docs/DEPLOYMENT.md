# 🚀 EP-X: デプロイ手順書 (完全版)

このドキュメントは、EP-XアプリケーションをGoogle Cloud (バックエンド) と Firebase Hosting (フロントエンド) にデプロイするための完全な手順書です。
数々の激闘の末に確立された、最も確実な方法をここに記録します。

---

## 🔥 Part 1: バックエンド (Cloud Run) のデプロイ

バックエンドのPythonサーバーは、DockerコンテナとしてCloud Runにデプロイします。

### 0. 前提条件
- `gcloud` CLIがインストールされ、認証済みであること。
  ```bash
  gcloud auth login
  gcloud config set project [YOUR_GCP_PROJECT_ID]
  ```
- `Docker`がローカルにインストールされていること。

### 1. サービスアカウントキーの準備
アプリケーションがGCPのAIサービス（Speech-to-Text, Vertex AIなど）と通信するために、認証情報が必要です。

1.  GCPコンソールでサービスアカウントキー（JSONファイル）を作成・ダウンロードします。
2.  ダウンロードしたキーを、プロジェクトの `config` フォルダに `gcp-key.json` という名前で配置します。

### 2. コンテナイメージのビルドとプッシュ
`Dockerfile` を使って、アプリケーションのコンテナイメージをビルドし、Google Container Registry (GCR) にプッシュします。

```powershell
# まずはDockerイメージをビルドするよ！
docker build -t gcr.io/edge-presence-x-mvp-463704/ep-x-backend .

# 次に、ビルドしたイメージをGCRにプッシュ！
docker push gcr.io/edge-presence-x-mvp-463704/ep-x-backend
```
このコマンドは、プロジェクトルートにある `Dockerfile` の内容に従って、`ep-x-backend` という名前のコンテナイメージを作成・プッシュします。

### 3. Cloud Run へのデプロイ
ビルドしたコンテナイメージをCloud Runにデプロイします。
**⚡注意:** 以下のコマンドはPowerShell用だよ！各行の末尾にあるバッククォート(\`)は、コマンドが次の行に続くことを示す記号だから、消さないでね！

```powershell
# PowerShellを使ってCloud Runにデプロイ
gcloud run deploy ep-x-backend `
  --image gcr.io/edge-presence-x-mvp-463704/ep-x-backend `
  --platform managed `
  --region asia-northeast1 `
  --set-env-vars "GOOGLE_CLOUD_PROJECT=edge-presence-x-mvp-463704" `
  --set-env-vars "GOOGLE_APPLICATION_CREDENTIALS=/app/config/gcp-key.json" `
  --allow-unauthenticated `
  --memory 2Gi `
  --cpu 2 `
  --timeout 300s
```
- `--allow-unauthenticated`: フロントエンドから誰でもアクセスできるようにします。
- `--set-env-vars`: アプリケーション内で必要な環境変数を設定します。
- `--memory`, `--cpu`, `--timeout`: パフォーマンス向上のためのおまじない✨

これでバックエンドのデプロイは完了です！🎉

---

## 🚀 Part 2: フロントエンド (Firebase Hosting) のデプロイ

フロントエンドのVue.jsアプリケーションは、Firebase Hostingにデプロイします。
**警告:** ここの設定は非常に複雑で、多くの罠があります。必ずこの手順通りに進めてください。

### 0. 前提条件
- `node` と `npm` がインストールされていること。
- `firebase-tools` がグローバルにインストールされていること。
  ```bash
  npm install -g firebase-tools
  ```
- Firebaseプロジェクトが作成済みで、Hostingが有効になっていること。

### 1. Firebase プロジェクトとの連携
ローカル環境をFirebaseプロジェクトに接続します。

```bash
# プロジェクトのルートディレクトリで実行
firebase login
firebase use [YOUR_FIREBASE_PROJECT_ID]
```

### 2. ビルド設定の最終調整 (最重要！)
Firebase CLIが正しくファイルを認識できるように、Viteのビルド設定とプロジェクトの構成を調整します。これが最も重要なステップです。

1.  **`vite.config.ts` の設定**
    - プロジェクトのルートにある `vite.config.ts` の中身を以下のように設定し、**ビルドの起点(`root`)**と**出力先(`outDir`)**を明確に指定します。

    ```ts
    // vite.config.ts
    import { defineConfig } from 'vite';
    import vue from '@vitejs/plugin-vue';
    import vuetify from 'vite-plugin-vuetify';
    import path from 'path';

    export default defineConfig({
      root: path.resolve(__dirname, 'src/frontend'), // ビルドの起点を指定
      plugins: [ /* ... */ ],
      build: {
        // 出力先をプロジェクトルートの 'dist' に指定
        outDir: path.resolve(__dirname, 'dist'),
        emptyOutDir: true,
      },
      // ... その他の設定
    });
    ```

2.  **`index.html` の移動と修正**
    - プロジェクトのルートにあった `index.html` を `src/frontend/` フォルダに移動します。
    - `src/frontend/index.html` が読み込むスクリプトのパスを、相対パスに修正します。
    ```html
    <!-- src/frontend/index.html -->
    <script type="module" src="./main.ts"></script>
    ```

### 3. ビルドとデプロイ
すべての設定が完了したら、ビルドとデプロイを実行します。**必ずプロジェクトのルートディレクトリで実行してください。**

1.  **依存関係のインストール**
    ```bash
    npm install
    ```

2.  **フロントエンドのビルド**
    ```bash
    npm run build
    ```
    これにより、プロジェクトのルートに `dist` フォルダが作成されます。

3.  **Firebaseへのデプロイ**
    ```bash
    firebase deploy --only hosting
    ```

これでフロントエンドのデプロイも完了です！お疲れ様でした！✨ 