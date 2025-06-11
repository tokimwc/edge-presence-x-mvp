# ハッカソン向け MVP（最小実用プロダクト）の要件定義書

---

## 概要（Executive Summary）

近年、Otter AI AgentやLinkedIn面接準備機能など「会話ストリームを解析し即時助言する」ソリューションが台頭しつつありますが ([The Verge](https://www.theverge.com/news/635176/otter-ai-voice-activated-meeting-agent-availability?utm_source=chatgpt.com))([The Verge][1]) ([LinkedIn][2])、生成AIで"声質・論理・印象"を一気通貫で補正する実践的コーチは未だ稀です。提案する **PitchPerfect-AI** は Google Cloud の Vertex AI Agent Builder、Speech-to-Text Streaming、Natural Language API 等を連携し、面接中の音声データを 300 ms 以内で解析・提示。ピッチの高騰、WPM（Words Per Minute）の逸脱、フィラー（えー、あのー）検出、論理構造の薄さを即座にダッシュボードへ赤信号表示し、「シニア即戦力」相当のプレゼンスへ導きます。

---

## 1. 背景と課題

* 緊張によるピッチ上昇・早口化が聴衆の信頼感を損なうことは神経科学的研究で裏付けられています ([フォーブス][3])。
* フィラーや間の不足は「信頼性の低下」要因として Forbes や学術論文で指摘されています ([フォーブス][3]) ([arXiv][4])。
* Google Cloud Speech-to-Text は gRPC Streaming でリアルタイム転写が可能 ([Google Cloud][5])。これを基盤にすれば、面接コーチをライブ化できる素地が整っています。
* Qiita 記事のプレゼン評価アプリは「スライドと音声の同期＋フィラー検出」を実現済みであり、本提案の良質な雛形となります ([Qiita][6])。

---

## 2. プロダクトビジョン

面接者のマイクとカメラ入力を取り込み、

1. **音声系エージェント**が ピッチ・WPM・フィラーカウントを時系列ストリームで算出。
2. **内容系エージェント**が LLM（Gemini 1.5 Flash）で STAR/SCQA 構造を即時採点。
3. **パーソナリティエージェント**が Google Cloud Natural Language API で感情を分析し、「落ち着いた低音・ 2 秒ポーズ」など行動指示を返却。

結果を Flutter Web UI 上で三色信号と改善提案カードとして点灯し、Zoom/Meet の隣に PIP 表示。面接者は視線をずらさずに"今"の課題を把握・修正できます。

---

## 3. 主要ユースケース

| シナリオ        | before                | after (PitchPerfect-AI)                    |
| ----------- | --------------------- | ------------------------------------------ |
| シニアレベル深掘り質問 | 説明が冗長→論点逸脱            | STAR テンプレ欠落箇所を赤表示し、要約候補文を提示                |
| 声が上ずる場面     | 早口110 WPM・ピッチ+30 cent | ダッシュボードが黄色警告。腹式呼吸コマンドを音声 TTS で 0.5 秒挿入     |
| リモート遅延で沈黙   | 焦って filler 連打         | Filler Detected > 8 / min ⇒ ミュート提案＋３拍の間を指示 |

---

## 4. MVP機能要件

### 4.1 リアルタイム音声解析

* Google Speech-to-Text Streaming API で 100 ms 毎に転写 ([Google Cloud][5])
* Librosa/Shennong でピッチ・フォルマント抽出 ([Deepgram][7]) ([SpringerLink][8])
* Filler 判定は PodcastFillers Dataset + Contrastive Learning fine-tune ([arXiv][4])

### 4.2 コンテンツ構造評価

* Vertex AI Generative Models へ逐次転写をウィンドウ送信し、 STAR/SCQA 構造欠落を指摘 ([Google Cloud][9])。
* Google Cloud Natural Language API で感情極性・主語抜けを抽出 ([Google Cloud][10])。

### 4.3 ダッシュボード & フィードバック

* Flutter Web で 60 fps カナリア更新。 Gemma モデル使用なら特別賞対象 ([Zenn][11])。
* 3 レベル信号（緑＝OK／黄＝注意／赤＝修正要）と、ワンフレーズ TTS コーチ。

### 4.4 セッションレポート

* After Action Report を PDF 生成し、Otter-style要約付きで Google Drive 保存 ([The Verge](https://www.theverge.com/news/635176/otter-ai-voice-activated-meeting-agent-availability?utm_source=chatgpt.com))([The Verge][1])。

---

## 5. 非機能要件

| 項目     | 目標                                                   |
| ------ | ---------------------------------------------------- |
| レイテンシ  | 音声解析→UI 反映まで **≦ 300 ms**                            |
| 可用性    | 99.5 %（Cloud Run Regional + Firestore multi-AZ）      |
| セキュリティ | 音声は VPC-SC 内、14 日後自動削除                               |
| コスト    | 1 時間あたり ≤ USD 0.30（Gemini Flash + Speech Lite モデル選定） |

---

## 6. システムアーキテクチャ

1. **前段**

   * Flutter Web → Cloud Run (Edge) へ WebRTC 音声 / gRPC。
2. **AI Pipeline**

   * Cloud Run (AI) コンテナ内で Pipecat フレームワークがマルチモーダルStreamを分配 ([GitHub][12])。
   * Speech API → Transcriber Agent → Pub/Sub
   * Librosa/Shennong → Paralinguistic Agent
   * Google Cloud Natural Language API → Sentiment Agent (感情分析スコアを提供)
   * Vertex AI Agent Builder Orchestrator が最終 Advice JSON を組成 ([Google Cloud][9])。
3. **データストア** : Firestore (Session Logs) ＆ BigQuery (匿名統計)。
4. **外部統合** : Meet/Zoom Overlay は Chrome Extension (WebSocket)。

---

## 7. AIエージェント細分化

| エージェント               | 役割            | 主な API / モデル                                    |
| -------------------- | ------------- | ----------------------------------------------- |
| **Transcriber**      | 音声→テキスト       | Speech-to-Text Streaming v2 ([Google Cloud][5]) |
| **Pitch-Tracker**    | f0・WPM・フィラー   | Librosa + PodcastFillers fine-tune ([arXiv][4]) |
| **Content-Critic**   | STAR/SCQA スコア | Gemini Flash 32k context                        |
| **Sentiment-Analyzer** | 感情分析        | Google Cloud Natural Language API ([Google Cloud][10]) |
| **Persona-Coach**    | 行動指示・TTS      | Gemini + Cloud TTS                              |
| **Session-Reporter** | 要約 & PDF      | Vertex AI Text + Google Docs API                |

---

## 8. 評価指標 (Success Metrics)

* **Filler Rate** < 4 /min → 緑域達成 ([arXiv][4])
* **平均ピッチ変動** ± 20 cent 内
* **STAR 完全性スコア** ≥ 0.85 (LLM self-eval)
* **ユーザ自己効力感向上** ≥ +25 % (アンケート)

---

## 9. ハッカソン要件適合

| 要件                 | 本提案                                                  |
| ------------------ | ---------------------------------------------------- |
| Google Cloud AI 製品 | Vertex AI Agent Builder, Speech-to-Text, TTS, Gemini |
| 〃 Compute 製品       | Cloud Run, Pub/Sub, Firestore                        |
| 追加賞対象              | Flutter Web UI, Gemma optional mode                  |
| 提出物                | GitHub, デモURL、Zenn 技術記事                              |

---

## 10. ロードマップ（2 週間スプリント）

1. **Day 0-2** : Cloud Run 雛形・Speech Streaming PoC
2. **Day 3-6** : Pitch/Filler Analyzer 実装 (PodcastFillers fine-tune)
3. **Day 7-9** : Vertex AI Content-Critic プロンプト設計
4. **Day 10-11** : Flutter UI & Chrome Extension 結合
5. **Day 12-13** : 自己録画でベンチマーク＋パラメータ微調整
6. **Day 14** : デモ、Zenn 記事、GitHub README 整備

---

## 11. 競合・差別化

| 既存サービス              | 特徴                                                                                                                                                    | 差別化要因                   |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| LinkedIn 面接準備       | 録画後バッチ評価 ([LinkedIn][2])                                                                                                                              | **リアルタイム** × ピッチ／STAR同時 |
| Otter Meeting Agent | 商談QA支援 ([The Verge](https://www.theverge.com/news/635176/otter-ai-voice-activated-meeting-agent-availability?utm_source=chatgpt.com))([The Verge][1]) | 面接特化＋声質制御               |
| Talent Palette 面談要約 | HR向け後処理 ([プレスリリース・ニュースリリース配信シェアNo.1｜PR TIMES][13])                                                                                                    | 応答中コーチング                |

---

## 12. 今後拡張アイデア

* Vision API で表情揺らぎ ⇒ 非言語評価。
* Meet Live Caption へダイレクト挿入（字幕ベースコーチ）。
* Gemma ローカル実行でオフライン練習モード。
* 面接官シミュレーション Agent（LLM-driven adversary）。

---

## 13. GUI & 3D アバター拡張要件（V1.1）

### 13.1 目的
* Zoom／Teams 風 UI を模倣し、ユーザーが **「本番さながらの面接環境」** を体験できる視覚・聴覚インターフェースを提供する。  
* 3D アバターがユーザーまたは AI 面接官の音声に同期して **口パク（リップシンク）・瞬き・軽いジェスチャー** を行い、臨場感を向上させる。

### 13.2 機能要件
| ID | 要件 | 詳細 |
|----|------|------|
| GUI-1 | 画面レイアウト | `MeetingView` コンポーネントで <video> 領域・自分のプレビュー小窓・コントロールバー(ミュート・カメラ・退出)を表示する。Zoom/Teams 風のダーク UI を CSS で再現 |
| GUI-2 | ステータスオーバーレイ | 右側に AI フィードバックパネル（信号灯 & 改善カード）を PIP 表示し、3 秒毎に更新する。 |
| AVA-1 | アバター読み込み | Ready Player Me で生成した GLB/VRM を Three.js Loader で読み込み、シーンに配置 |
| AVA-2 | リップシンク | Web Audio API で取得した音声の **振幅** をモーフターゲット “JawOpen” にマッピングし 60 fps で更新 |
| AVA-3 | モーション | 待機時はあらかじめ設定した idle アニメーションをループ再生。DeepMotion の Animate 3D API から取得した BVH を適宜適用可能とする |
| TTS-1 | 音声合成 | 面接官の質問文を Web Speech API `speechSynthesis` または Google TTS で合成し再生 |
| INT-1 | Vue 連携 | Three.js の初期化・レンダリングを `AvatarCanvas.vue` として分離し、Vue ライフサイクルでメモリ管理 |
| ALT-1 | 代替レンダラ | Babylon.js でもレンダリング可能なクラス構成とし、ライブラリ切替が容易な抽象化インターフェースを提供 |

### 13.3 非機能要件（追加）
* **描画性能:** 1080p／60 fps で FPS > 50 を維持（M1 MacBook Air 相当）。  
* **ロード時間:** アバター初回ロード < 2 s（GLB 2 MB 以下、gzip 圧縮）
* **ブラウザ互換:** Chrome 115+ / Edge 115+ / Safari 17+。  
* **拡張性:** 将来 Flutter Web 移植を見据え、Three.js 依存ロジックを `lib/3d/` に隔離。

### 13.4 受入条件
* マイク入力の音量に比例して口モーフが 3 段階以上変化し、動画キャプチャで目視確認できること
* GUI 操作（ミュート・カメラ OFF）が CSS で即時反映し、状態がダッシュボード側にも通知されること。  
* MVP デモ環境でユーザ 3 名が「臨場感がある」と回答（5 段階アンケート平均 ≧ 4）。

---

## 14. 技術スタック選定補足

### 14.1 フロントエンド: Vue 継続 vs Flutter Web
* **Vue 3 + Vite** は既存コード再利用と WebGL 連携の豊富な資料が強み。
* Flutter Web は一貫した UI フレームワークだが、WebRTC・Three.js 連携は追加プラグインを要しハッカソン期間のリスクが高いため V1.1 では採用しない。将来モバイル展開時に再評価。

### 14.2 3D レンダラ: Three.js 優先
* Three.js は VRM, GLTF, srcAlphaBlending 等の実装が豊富でコミュニティサポートも活発。
* Babylon.js は GUI ウィジェットや PBR が充実するが lipsync は自前実装が前提。
* よって **Three.js + VRM Loader + TresJS (Vue ラッパ)** を推奨。

---

## 15. オープン課題 & 次期スプリント候補

| カテゴリ | 課題 | 解決案 |
|----------|------|-------|
| **リップシンク精度** | 音量ベースでは母音区別が粗い | Whisper などで 200 ms ウィンドウ文字起こし → 音素 → Viseme 変換を検証 |
| **モーション多様性** | DeepMotion API はジョブ完了まで数秒遅延 | 短尺ジェスチャーを事前生成し組み合わせるプリセット方式にフォールバック |
| **Flutter 移行調査** | WebGL wrapper, WebRTC plugin の成熟度 | `flutter_unity_widget` + WebGL export の PoC を次期計画に設定 |
| **ライセンス確認** | Ready Player Me アバターデータの商用条件 | RPM FAQ を精査、MIT/GPL 両立可否をレポート化 |

---


[1]: https://www.theverge.com/news/635176/otter-ai-voice-activated-meeting-agent-availability?utm_source=chatgpt.com "Otter's new AI agent can speak up in meetings"
[2]: https://www.linkedin.com/help/linkedin/answer/a1605896/-ai-?lang=ja-JP&utm_source=chatgpt.com "AIのフィードバックを即座に取得して、面接の回答を改善します"
[3]: https://www.forbes.com/sites/scotthutcheson/2025/01/23/the-neuroscience-of-filler-words-and-how-they-can-erode-credibility/?utm_source=chatgpt.com "The Neuroscience Of Filler Words And How They Can Erode ..."
[4]: https://arxiv.org/abs/2203.15135?utm_source=chatgpt.com "Filler Word Detection and Classification: A Dataset and Benchmark"
[5]: https://cloud.google.com/speech-to-text/docs/transcribe-streaming-audio?utm_source=chatgpt.com "Transcribe audio from streaming input | Cloud Speech-to-Text ..."
[6]: https://qiita.com/dnp-yasunobe/items/df1452f2bc0645908190?utm_source=chatgpt.com "AIでプレゼン内容をフィードバックするアプリ実装に挑戦 - Qiita"
[7]: https://deepgram.com/learn/best-python-audio-libraries-for-speech-recognition-in-2023?utm_source=chatgpt.com "The Developer's Guide to Speech Recognition in Python - Deepgram"
[8]: https://link.springer.com/article/10.3758/s13428-022-02029-6?utm_source=chatgpt.com "Shennong: A Python toolbox for audio speech features extraction"
[9]: https://cloud.google.com/products/agent-builder?utm_source=chatgpt.com "Vertex AI Agent Builder | Google Cloud"
[10]: https://cloud.google.com/natural-language?utm_source=chatgpt.com "Natural Language AI - Google Cloud"
[11]: https://zenn.dev/hackathons/google-cloud-japan-ai-hackathon-vol2?utm_source=chatgpt.com "第 2回 AI Agent Hackathon with Google Cloud - Zenn"
[12]: https://github.com/pipecat-ai/pipecat?utm_source=chatgpt.com "pipecat-ai/pipecat: Open Source framework for voice and multimodal ..."
[13]: https://prtimes.jp/main/html/rd/p/000000216.000023180.html?utm_source=chatgpt.com "タレントパレット、採用面談の会話を可視化し生成AIで評価する ..."
