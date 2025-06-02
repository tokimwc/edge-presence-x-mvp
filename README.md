# 🚀 Edge Presence X (EP-X) - AI面接練習コーチシステム

[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Ready-4285F4?logo=google-cloud)](https://cloud.google.com/)
[![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Gemini%201.5-34A853)](https://cloud.google.com/vertex-ai)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 プロジェクト概要

EP-Xは、Google Cloud AI技術を活用したリアルタイム面接練習システムです。
音声解析・感情認識・STAR手法評価を組み合わせ、就活生の面接スキル向上を支援します。

### ✨ 主要機能

- 🎤 **リアルタイム音声解析** - Cloud Speech-to-Text gRPC (300ms以下レイテンシ)
- 🧠 **AI評価システム** - Vertex AI Gemini 1.5 + LLM-as-Judge
- 📊 **STAR手法評価** - Situation, Task, Action, Result構造分析
- 💭 **感情分析** - Symbl.ai WebSocket + リアルタイム感情認識
- 📈 **音程解析** - PyAudio autocorrelation による声のトーン分析
- 📋 **総合評価** - 自信度・構造性・感情表現の3軸スコアリング

## 🏗️ システムアーキテクチャ

```
graph TD
    Browser[🌐 ブラウザ] --WebRTC--> CloudRun[☁️ Cloud Run Edge]
    CloudRun --PubSub--> STT[🎤 Speech-to-Text]
    STT --gRPC--> VertexAI[🧠 Vertex AI Audio]
    CloudRun --Stream--> PitchWorker[🎵 Pitch Worker]
    STT & PitchWorker --> Fusion[⚡ Fusion Function]
    Fusion --> Gemini[💎 Gemini 1.5 Judge]
    Fusion --WebSocket--> Sentiment[💭 Symbl Sentiment]
    Gemini & Sentiment --> Firestore[🗃️ Firestore]
    Firestore --> VueUI[🖥️ Vue.js UI]
```

## 🚀 クイックスタート

### 前提条件
- Node.js 18+
- Python 3.9+
- Google Cloud Project (Speech-to-Text, Vertex AI有効化済み)

### セットアップ
```
git clone https://github.com/[username]/edge-presence-x-mvp.git
cd edge-presence-x-mvp
cp .env.example .env
# .envファイルにGCP認証情報を設定
npm install && pip install -r requirements.txt
```

## 📊 成功指標 (MVP)

| 指標 | 目標値 | 現在値 |
|------|--------|--------|
| レスポンス精度 | 90%以上 | - |
| 評価レイテンシ | 1秒以内 | - |
| LLM評価 vs 人間評価 | 相関0.8以上 | - |
| セッション継続時間 | 4分以上 | - |
| 音声解析精度 | 30秒以内 | - |

## 🎖️ ハッカソン目標

**Google Cloud Japan AI Hackathon Vol.2** 参加プロジェクト
- ⏰ 24時間以内にMVP完成
- 📱 GitHub + Devpost提出 (MIT License)
- 🏆 AI Agent部門でのイノベーション評価
```

