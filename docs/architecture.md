# EP-X システムアーキテクチャ設計書

## 1. システム概要

### 1.1 目的
面接練習におけるリアルタイムフィードバックシステムの構築

### 1.2 技術スタック
- **フロントエンド**: Vue.js 3, WebRTC, Canvas API
- **バックエンド**: Python, Cloud Functions, Cloud Run
- **AI/ML**: Vertex AI Gemini 1.5, Cloud Speech-to-Text
- **インフラ**: Google Cloud Platform, BigQuery, Firestore

## 2. コンポーネント設計

### 2.1 リアルタイム音声処理
```
# Speech-to-Text gRPC Streaming
latency_target = 300  # ms以下
streaming_config = {
    "enable_automatic_punctuation": True,
    "interim_results": True,
    "single_utterance": False
}
```

### 2.2 AI評価エンジン
- **STAR手法解析**: Gemini 1.5による構造化評価
- **感情分析**: Symbl.ai WebSocket統合
- **LLM-as-Judge**: Confident-AI Metrics採用

### 2.3 リアルタイム通信
- WebRTC: ブラウザ ↔ Cloud Run
- gRPC: 内部サービス間通信
- WebSocket: 感情分析結果配信

## 3. スケーラビリティ設計

### 3.1 Auto-scaling
- Cloud Run: 100並行処理対応
- PubSub: メッセージキュー管理
- BigQuery: 分析データ集約

### 3.2 セキュリティ
- OAuth2 + Cloud IAM
- Cloud KMS暗号化
- HTTPS/WSS通信