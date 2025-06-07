# ここに Google Cloud Speech-to-Text のライブラリをインポートする感じで！
from google.cloud import speech_v1p1beta1 as speech # 非同期クライアントを使うよ！
import asyncio
import pyaudio
import logging # logging モジュールをインポート
import os # 環境変数のために追加

# --- Pythonのモジュール検索パスにsrcディレクトリを追加 ---
import sys
# speech_processor.py のあるディレクトリ (src/backend/services)
_CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
# src ディレクトリの絶対パス (src/backend/services -> src/backend -> src)
_SRC_DIR = os.path.abspath(os.path.join(_CURRENT_FILE_DIR, '..', '..'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
# --- ここまで ---

# Worker をインポート (相対パスからsrcを基準とした絶対パス風に変更)
from backend.workers.pitch_worker import PitchWorker
from backend.workers.sentiment_worker import SentimentWorker # SentimentWorker をインポート

# logging の基本設定 (モジュールレベルで１回だけ実行)
# SpeechProcessor クラスの外で設定するのが一般的だよん！
logging.basicConfig(
    level=logging.INFO,  # 開発中はINFOレベル以上を表示
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# このモジュール用のロガーを取得
logger = logging.getLogger(__name__)

# PyAudioの設定 (これらの値はマイクや要件に合わせて調整してね！)
FORMAT = pyaudio.paInt16  # 音声フォーマット (16bit)
CHANNELS = 1             # モノラル
RATE = 16000             # サンプルレート (16kHz)
CHUNK = int(RATE / 10)   # 100ms分のフレームサイズ (Speech-to-Textの推奨に合わせて)
SAMPLE_WIDTH = pyaudio.PyAudio().get_sample_size(FORMAT) # PyAudioからサンプル幅を取得

# --- Gemini評価システム用の追加インポートと設定 ---
import json
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold
import vertexai # vertexaiのメインライブラリもインポート

# Gemini設定ファイルのパス (speech_processor.pyからの相対パスを考慮)
# _SRC_DIR は src ディレクトリを指すので、そこから一つ上がって config を指定
GEMINI_CONFIG_PATH = os.path.join(_SRC_DIR, "..", "config", "gemini_config.json")

PROMPT_TEMPLATE = """
# プロンプトテンプレート：AI面接評価システム

あなたは、経験豊富なキャリアコンサルタントであり、行動面接のプロフェッショナルです。
特にSTAR手法を用いた回答の分析と、声のトーンや感情表現から候補者のコミュニケーション能力を見抜くことに長けています。
提供された情報に基づき、面接の回答を多角的に評価し、具体的かつ建設的なフィードバックを提供してください。

## 入力情報

### 面接の質問:
```
{interview_question}
```

### 回答の文字起こし:
```
{transcript}
```

### ピッチ解析結果:
- 平均ピッチ: {average_pitch} Hz
- ピッチの変動幅: {pitch_range} Hz
- 話す速度: {speaking_rate} 文字/分
- ポーズの頻度: {pause_frequency} 回/分
- ポーズの平均時間: {average_pause_duration} 秒

### 感情分析結果:
- 主な感情: {dominant_emotion}
- 感情スコア ({dominant_emotion}): {emotion_score}
- 感情の強さ: {emotion_intensity}
- 発話中の感情の推移: {emotion_transition}

## 評価基準

### 1. STAR手法の評価
*   **Situation（状況）:**
    *   具体的な状況説明が明確になされているか？
    *   回答者がどのような状況に置かれていたのか、背景情報が十分に提供されているか？
    *   いつ、どこで、誰が関わっていたのかが明確か？
*   **Task（課題）:**
    *   取り組むべき課題や目標が明確に定義されているか？
    *   その課題の重要性や困難度が伝わるか？
    *   何を達成する必要があったのかが具体的か？
*   **Action（行動）:**
    *   課題解決のために、どのような思考プロセスを経て、具体的にどのような行動を取ったのか説明されているか？
    *   行動の主体は回答者自身か？
    *   行動の理由や目的が明確か？
    *   複数の行動がある場合、それらが論理的に関連しているか？
*   **Result（結果）:**
    *   行動の結果、どのような具体的な成果が得られたのか明確に説明されているか？
    *   可能な限り定量的なデータ（数値、割合など）を用いて成果を示せているか？
    *   結果から何を学び、次にどう活かそうとしているかが述べられているか？
    *   ポジティブな結果だけでなく、ネガティブな結果やそこからの学びもあれば評価する。

### 2. 回答の構造
*   **論理性と構成:**
    *   回答全体が論理的で分かりやすい構成になっているか？ (例: PREP法、時系列など)
    *   話の導入、本論、結論が明確か？
    *   冗長な部分や話が飛躍している箇所はないか？
*   **具体性:**
    *   抽象的な表現に終始せず、具体的なエピソードや事例を交えて説明できているか？
    *   誰が聞いても情景をイメージできるような詳細さがあるか？

### 3. 声のトーンと話し方
*   **自信と熱意:**
    *   声のトーンは安定しており、自信が感じられるか？
    *   語尾が明瞭で、ハキハキと話せているか？
    *   話の内容に対する熱意や意欲が声から伝わるか？
    *   早口すぎたり、逆に遅すぎて間延びしていないか？
*   **聞き取りやすさ:**
    *   声量や滑舌は適切で、聞き取りやすい話し方か？
    *   不要な「えーっと」「あのー」などのフィラーが多すぎないか？

### 4. 感情表現
*   **適切性と一貫性:**
    *   話の内容と感情表現（声のトーン、話す速度などから推測されるもの）が一貫しているか？
    *   場面に応じた適切な感情が表現できているか？（例：困難を語る際は真剣なトーン、成功を語る際は明るいトーンなど）
    *   感情の起伏が激しすぎたり、逆に乏しすぎたりしないか？

### 5. 全体的な印象
*   **分かりやすさ:**
    *   回答全体を通して、伝えたいことが明確に伝わってくるか？
    *   専門用語を使いすぎず、相手に配慮した言葉遣いができているか？
*   **説得力:**
    *   自己PRや経験談に説得力があり、聞き手を納得させられるか？
    *   根拠に基づいた主張ができているか？
*   **熱意と意欲:**
    *   その企業や職務に対する熱意や入社意欲が感じられるか？
    *   ポジティブな姿勢で面接に臨んでいるか？

## 出力形式

### 1. 総合評価 (5段階)
1.  改善が必要
2.  まだ改善の余地がある
3.  良い
4.  非常に良い
5.  素晴らしい

### 2. 各評価項目の詳細フィードバック
*   **STAR手法:**
    *   Situation: （具体的なフィードバックと改善点）
    *   Task: （具体的なフィードバックと改善点）
    *   Action: （具体的なフィードバックと改善点）
    *   Result: （具体的なフィードバックと改善点）
*   **回答の構造:** （具体的なフィードバックと改善点）
*   **声のトーンと話し方:** （具体的なフィードバックと改善点、ピッチ解析結果を元に）
*   **感情表現:** （具体的なフィードバックと改善点、感情分析結果を元に）
*   **全体的な印象:** （具体的なフィードバックと改善点）

### 3. 回答全体の改善点 (3つ程度)
1.  （具体的な改善点）
2.  （具体的な改善点）
3.  （具体的な改善点）

### 4. アピールポイント (3つ程度)
1.  （特に優れている点、強みとなる点）
2.  （特に優れている点、強みとなる点）
3.  （特に優れている点、強みとなる点）

## 指示

上記の入力情報と評価基準に基づき、面接の回答を詳細に分析・評価してください。
そして、定義された出力形式に従って、総合評価、各評価項目の詳細なフィードバック、回答全体の改善点、およびアピールポイントを生成してください。
フィードバックは、具体的で、候補者が次の面接に活かせるような実践的なアドバイスを心がけてください。

## 制約
*   個人を特定できる情報（氏名、具体的な企業名、製品名など、一般的に公開されていない情報）を生成、または推測して出力しないでください。
*   いかなる形であれ、差別的な表現や、特定の個人・団体を不当に貶めるような内容は絶対に含めないでください。
*   提供された情報のみに基づいて評価を行い、憶測や個人的な偏見を排除してください。
*   法律や倫理に反するような不適切なアドバイスは行わないでください。
*   フィードバックは客観的かつ建設的なものに終始してください。
"""

gemini_model_instance = None # グローバル変数としてGeminiモデルを保持（クラス内で管理推奨）
gemini_config_data = None    # グローバル変数としてGemini設定を保持

def load_gemini_config_and_init():
    global gemini_model_instance, gemini_config_data
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.warning(
            "環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されていません。"
            "Vertex AI APIへの認証に失敗する可能性があります。"
        )
        # raise EnvironmentError("GOOGLE_APPLICATION_CREDENTIALS is not set.") # 必要ならエラーにする
        return False # 認証情報がない場合はFalseを返す

    try:
        with open(GEMINI_CONFIG_PATH, 'r') as f:
            gemini_config_data = json.load(f)
        logger.info(f"Gemini設定ファイルを読み込みました: {GEMINI_CONFIG_PATH}")

        # project_id -> project に変更！せんぱいの設定に合わせたよん！
        vertexai.init(project=gemini_config_data["project"], location=gemini_config_data["location"])
        gemini_model_instance = GenerativeModel(
            gemini_config_data["model_name"],
            # せんぱいが設定してくれた generation_config を読み込むようにしたよ！
            generation_config=gemini_config_data.get("generation_config", {}),
            # 安全性設定の例 (必要に応じて調整)
            # safety_settings={
            #     HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            #     HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            # }
        )
        logger.info(f"Geminiモデル ({gemini_config_data['model_name']}) の準備ができました。")
        return True
    except FileNotFoundError:
        logger.error(f"Gemini設定ファイルが見つかりません: {GEMINI_CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Gemini設定の読み込みまたは初期化中にエラー: {e}")
    return False

async def get_gemini_evaluation(
    interview_question: str,
    transcript: str,
    pitch_analysis: dict,
    emotion_analysis: dict
) -> str | None:
    if not gemini_model_instance or not gemini_config_data:
        logger.error("Geminiモデルが初期化されていません。")
        return None

    prompt = PROMPT_TEMPLATE.format(
        interview_question=interview_question,
        transcript=transcript,
        average_pitch=pitch_analysis.get("average_pitch", "N/A"),
        pitch_range=pitch_analysis.get("pitch_range", "N/A"),
        speaking_rate=pitch_analysis.get("speaking_rate", "N/A"),
        pause_frequency=pitch_analysis.get("pause_frequency", "N/A"),
        average_pause_duration=pitch_analysis.get("average_pause_duration", "N/A"),
        dominant_emotion=emotion_analysis.get("dominant_emotion", "N/A"),
        emotion_score=emotion_analysis.get("emotion_score", "N/A"),
        emotion_intensity=emotion_analysis.get("emotion_intensity", "N/A"),
        emotion_transition=emotion_analysis.get("emotion_transition", "N/A")
    )
    logger.info("Geminiへの評価リクエストプロンプトを作成しました。")

    try:
        response = await gemini_model_instance.generate_content_async(prompt)
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            evaluation_text = response.candidates[0].content.parts[0].text
            logger.info("Geminiから面接評価を受信しました。")
            return evaluation_text
        else:
            logger.warning("Geminiからのレスポンスに有効な評価テキストが含まれていませんでした。")
            return "評価結果の形式が無効です。"
    except Exception as e:
        logger.error(f"Gemini APIリクエスト中にエラーが発生: {e}")
        return f"Gemini APIエラー: {str(e)}"

def parse_gemini_response_data(response_text: str) -> dict:
    """Geminiからのレスポンスをパースする関数 (今回は未実装、生のテキストを返す)"""
    logger.info("Geminiレスポンスのパース処理 (現在は生テキストを返します)")
    return {"raw_evaluation": response_text}

# --- ここまでGemini評価システム用の追加 ---

class SpeechProcessor:
    def __init__(self):
        self.speech_client = speech.SpeechAsyncClient()
        self.pyaudio_instance = pyaudio.PyAudio()
        self._audio_queue = asyncio.Queue()
        self._is_running = False
        self._microphone_task = None
        self._stop_event = asyncio.Event()
        self.main_loop = asyncio.get_event_loop()

        # PitchWorker のインスタンスを作成
        try:
            self.pitch_worker = PitchWorker(
                sample_rate=RATE,
                channels=CHANNELS,
                sample_width=SAMPLE_WIDTH,
            )
            logger.info("🎵 PitchWorker の初期化に成功しました。")
        except Exception as e:
            logger.exception("😱 PitchWorker の初期化中にエラーが発生しました。")
            self.pitch_worker = None

        # SentimentWorker のインスタンスを作成
        try:
            # Google Cloud Natural Language API を使うので、APIキーは環境変数 GOOGLE_APPLICATION_CREDENTIALS で設定されてる前提だよん！
            self.sentiment_worker = SentimentWorker(
                on_emotion_callback=self._handle_emotion_data,
                language_code="ja" # Google Cloud NL API は "ja" を使うよ！
            )
            logger.info("😊 SentimentWorker (Google Cloud NL API版) の初期化に成功しました。")
        except Exception as e: # SentimentWorker内でクライアント初期化エラーもキャッチできるように汎用的なExceptionに
            logger.exception("😱 SentimentWorker (Google Cloud NL API版) の初期化中にエラーが発生しました。")
            self.sentiment_worker = None

        logger.info("✨ SpeechProcessor 初期化完了！✨")
        logger.info(f"PyAudio設定: FORMAT={FORMAT}, CHANNELS={CHANNELS}, RATE={RATE}, CHUNK={CHUNK}, SAMPLE_WIDTH={SAMPLE_WIDTH}")

        # --- Gemini評価システム関連の初期化 ---
        self.gemini_enabled = load_gemini_config_and_init()
        if self.gemini_enabled:
            logger.info("👑 Gemini評価システムが有効になりました。")
        else:
            logger.warning("😢 Gemini評価システムは無効です。設定または認証情報を確認してください。")
        
        self.current_interview_question = "自己PRをしてください。" # デフォルトの質問
        self.last_pitch_analysis_summary = {} # ピッチ解析の集計結果を保持する場所 (TODO: PitchWorkerと連携)
        self.last_emotion_analysis_summary = {} # 感情分析の集計結果を保持する場所 (TODO: SentimentWorkerと連携)
        # --- ここまでGemini評価システム関連の初期化 ---

    def _handle_emotion_data(self, emotion_data: dict):
        """
        SentimentWorkerからの感情分析結果を処理するコールバック関数。
        Google Cloud Natural Language API の結果に合わせて調整したよん！
        """
        # Natural Language API からは score と magnitude がメインで返ってくる
        score = emotion_data.get("emotions", {}).get("score")
        magnitude = emotion_data.get("emotions", {}).get("magnitude")
        text_processed = emotion_data.get("text_processed", "")

        if score is not None and magnitude is not None:
            logger.info(f"😊 感情分析結果 (Google NL): スコア={score:.2f}, 強さ={magnitude:.2f} (テキスト: '{text_processed[:50]}...')")
            # TODO: この情報を self.last_emotion_analysis_summary に適切に格納する
            # 例: self.last_emotion_analysis_summary = {"dominant_emotion": "解析ロジック", "score": score, "magnitude": magnitude, ...}
            # 今回は単純に最新のものを保持する例
            self.last_emotion_analysis_summary = {
                "dominant_emotion": "不明 (Google NL score/magnitudeベース)",
                "emotion_score": score,
                "emotion_intensity": magnitude,
                "emotion_transition": "N/A (Google NLは発話全体)" # Google NLの基本APIでは推移は取れない
            }
        else:
            logger.warning(f"🤔 感情分析結果が不完全です: {emotion_data}")

    async def _microphone_stream_generator(self):
        """
        マイクからの音声データを非同期で供給するジェネレータだよん！
        Speech-to-Text API が期待する StreamingRecognitionConfig と音声チャンクを yield する。
        """
        streaming_config = speech.StreamingRecognitionConfig(
            config=speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=RATE,
                language_code="ja-JP",
                enable_automatic_punctuation=True,
            ),
            interim_results=True,
        )
        yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
        logger.info("🎤 ストリーミング設定送信完了！音声待機中...")

        while self._is_running and not self._stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                if chunk is None: 
                    break
                yield speech.StreamingRecognizeRequest(audio_content=chunk)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.exception("😱 _microphone_stream_generator で予期せぬエラー")
                break
        logger.info("🎤 _microphone_stream_generator 終了")

    def _microphone_worker(self):
        """
        PyAudioを使ってマイクから音声データを読み込み、キューに入れる同期処理ワーカー。
        これは別スレッドで実行される想定だよん！
        """
        try:
            stream = self.pyaudio_instance.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            logger.info("🎙️ マイクストリーム開始！ 音声収集中...")
            data_counter = 0 # デバッグ用カウンター
            while self._is_running and not self._stop_event.is_set():
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    data_counter += 1
                    
                    log_pitch_str = "N/A"
                    if self.pitch_worker and data:
                        try:
                            pitch_hz = self.pitch_worker.analyze_pitch(data)
                            if pitch_hz is not None:
                                log_pitch_str = f"{pitch_hz:.2f} Hz"
                                # TODO: ピッチ情報を self.last_pitch_analysis_summary に集計・格納する
                                # 例: 平均ピッチ、変動幅などを計算して保持
                                # 今回はダミーとして最新のピッチを一時的に保持するイメージ (実際には集計が必要)
                                if "pitches" not in self.last_pitch_analysis_summary:
                                    self.last_pitch_analysis_summary["pitches"] = []
                                self.last_pitch_analysis_summary["pitches"].append(pitch_hz)
                                if len(self.last_pitch_analysis_summary["pitches"]) > 100: # 最新100件保持など
                                     self.last_pitch_analysis_summary["pitches"].pop(0)

                        except Exception as e:
                            logger.error(f"😱 (Worker) PitchWorkerでのピッチ解析エラー: {e}")
                            log_pitch_str = "Error"

                    logger.debug(f"🎤 [Worker-{data_counter}] チャンク受信！ サイズ: {len(data)}, 先頭10バイト: {data[:10].hex() if data else 'None'} | 🎵 ピッチ: {log_pitch_str}")
                    
                    asyncio.run_coroutine_threadsafe(self._audio_queue.put(data), self.main_loop)
                except IOError as e:
                    logger.warning(f"🎤 PyAudio readエラー (たぶんオーバーフロー): {e}") 
                    asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), self.main_loop)
                except Exception as e:
                    logger.exception(f"😱 _microphone_workerの内部ループで予期せぬエラー: {e}")
                    # ループを継続するために ചെറിയ待機時間を設けることも検討
                    asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), self.main_loop)

            logger.info("🎙️ マイクストリームループ終了。ストリーム停止処理へ...")
            stream.stop_stream()
            stream.close()
            logger.info("🎙️ マイクストリーム正常終了。")
        except Exception as e:
            logger.exception("😱 _microphone_workerで致命的なエラー")
        finally:
            if self._is_running: 
                 logger.info("_microphone_worker の finally でキューにNoneを送信")
                 asyncio.run_coroutine_threadsafe(self._audio_queue.put(None), self.main_loop)

    async def start_realtime_transcription_from_mic(self):
        """
        マイクからのリアルタイム文字起こしを開始するよん！文字起こし結果を非同期で返す。
        """
        if self._is_running:
            logger.warning("既に実行中だよん！")
            return

        logger.info("🚀リアルタイム文字起こし開始準備...")
        self._is_running = True
        self._stop_event.clear()
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()

        # SentimentWorker を開始 (もしあれば)
        if self.sentiment_worker:
            logger.info("😊 SentimentWorkerを開始します...")
            try:
                # SentimentWorkerのstartは非同期なのでawaitする
                success = await self.sentiment_worker.start()
                if success:
                    logger.info("😊 SentimentWorkerが正常に開始されました。")
                else:
                    logger.error("😱 SentimentWorkerの開始に失敗しました。以降の感情分析は行われません。")
                    # self.sentiment_worker = None # 開始失敗したら無効化も検討
            except Exception as e:
                logger.exception("😱 SentimentWorkerのstart呼び出し中にエラーが発生しました。")
                # self.sentiment_worker = None

        loop = asyncio.get_event_loop()
        self._microphone_task = loop.run_in_executor(None, self._microphone_worker)
        logger.info("🎧 マイクワーカースレッド開始！")

        try:
            responses = await self.speech_client.streaming_recognize(
                requests=self._microphone_stream_generator()
            )
            async for response in responses:
                if not self._is_running: break

                if not response.results:
                    continue
                result = response.results[0]
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript
                
                if result.is_final:
                    logger.info(f"✨ 最終結果キタコレ！: {transcript}")
                    # 最終結果テキストをSentimentWorkerに送信
                    if self.sentiment_worker and self.sentiment_worker._is_running and transcript:
                        logger.debug(f"感情分析のためにテキスト送信: '{transcript}'")
                        # send_text_for_analysis は非同期メソッドなので create_task でノンブロッキングに実行
                        asyncio.create_task(self.sentiment_worker.send_text_for_analysis(transcript))
                    
                    # --- Gemini評価をトリガー ---
                    if self.gemini_enabled and transcript:
                        logger.info(f"👑 Gemini評価システムに最終回答を送信します: '{transcript[:50]}...'")
                        # ピッチと感情のサマリーデータを作成 (現在はダミー/部分的)
                        # TODO: PitchWorkerとSentimentWorkerからの集計データを正しく使う
                        current_pitch_summary = {
                            "average_pitch": sum(self.last_pitch_analysis_summary.get("pitches", [0])) / len(self.last_pitch_analysis_summary.get("pitches", [1])) if self.last_pitch_analysis_summary.get("pitches") else "N/A",
                            "pitch_range": max(self.last_pitch_analysis_summary.get("pitches", [0])) - min(self.last_pitch_analysis_summary.get("pitches", [0])) if self.last_pitch_analysis_summary.get("pitches") else "N/A",
                            "speaking_rate": "N/A (TODO)", # TODO: 話速計算ロジック
                            "pause_frequency": "N/A (TODO)", # TODO: ポーズ頻度計算ロジック
                            "average_pause_duration": "N/A (TODO)" # TODO: 平均ポーズ時間計算ロジック
                        }
                        
                        asyncio.create_task(self._trigger_gemini_evaluation(
                            self.current_interview_question,
                            transcript,
                            current_pitch_summary, # 今はダミーに近い
                            self.last_emotion_analysis_summary # SentimentWorkerからの結果
                        ))
                    # --- ここまでGemini評価トリガー ---
                    yield transcript 
                else:
                    logger.info(f"📝 途中結果: {transcript}")

        except Exception as e:
            logger.exception("😱 start_realtime_transcription_from_mic 内の streaming_recognize ループでエラー")
        finally:
            logger.info("🛑 文字起こし処理ループ終了。stop_realtime_transcription_from_mic を呼び出す準備...")
            # await self.stop_realtime_transcription_from_mic() # 呼び出し元でやる！

    async def stop_realtime_transcription_from_mic(self):
        """
        マイク入力と文字起こし処理を停止するよん！
        """
        if not self._is_running:
            logger.info("もう止まってるよん！")
            return

        logger.info("⏳ リアルタイム文字起こし停止処理開始...")
        self._is_running = False
        self._stop_event.set()

        # SentimentWorker を停止 (もしあれば)
        if self.sentiment_worker and self.sentiment_worker._is_running:
            logger.info("😊 SentimentWorkerを停止します...")
            try:
                # SentimentWorkerのstopは非同期なのでawaitする
                await self.sentiment_worker.stop()
                logger.info("😊 SentimentWorkerが正常に停止されました。")
            except Exception as e:
                logger.exception("😱 SentimentWorkerのstop呼び出し中にエラーが発生しました。")

        if self._microphone_task is not None:
            logger.info("🎤 マイクワーカースレッドの終了待ち...")
            try:
                await asyncio.wait_for(self._audio_queue.put(None), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("audio_queue.put(None) タイムアウト (stop時)")
            except Exception as e:
                 logger.error(f"audio_queue.put(None) でエラー (stop時): {e}")

            try:
                await asyncio.wait_for(self._microphone_task, timeout=5.0)
                logger.info("🎤 マイクワーカースレッド正常終了！")
            except asyncio.TimeoutError:
                logger.warning("🔥 マイクワーカースレッドの終了タイムアウト！")
            except Exception as e:
                logger.error(f"🔥 マイクワーカースレッド終了時にエラー: {e}")
            self._microphone_task = None
        
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        logger.info("✅ リアルタイム文字起こし停止完了！")

    def __del__(self):
        """
        オブジェクトが消えるときにPyAudioリソースを解放するよん
        """
        if hasattr(self, 'pyaudio_instance') and self.pyaudio_instance:
            logger.info("💨 PyAudioインスタンスを解放します...")
            self.pyaudio_instance.terminate()
            logger.info("💨 PyAudioインスタンス解放完了！")
        # SentimentWorkerのaiohttpセッションもここで確実に閉じることを検討
        # ただし、非同期のstopメソッドで処理するのが望ましい
        # if hasattr(self, 'sentiment_worker') and self.sentiment_worker:
        #     if hasattr(self.sentiment_worker, '_aiohttp_session') and self.sentiment_worker._aiohttp_session:
        #         if not self.sentiment_worker._aiohttp_session.closed:
        #             # 非同期メソッドを __del__ から呼ぶのは難しいので、通常は stop で処理すべき
        #             logger.warning("SentimentWorkerのaiohttpセッションが __del__ でまだ開いています。プログラム終了前にstopを呼んでください。")

    # --- Gemini評価システム用のメソッド追加 ---
    def set_interview_question(self, question: str):
        """現在の面接の質問を設定するよん！"""
        self.current_interview_question = question
        logger.info(f"🎤 設定された面接の質問: {question}")

    async def _trigger_gemini_evaluation(
        self,
        interview_question: str,
        transcript: str,
        pitch_analysis: dict,
        emotion_analysis: dict
    ):
        """Gemini評価APIを呼び出し、結果をログに出力する内部メソッド"""
        logger.info("👑 Gemini評価処理を開始します...")
        evaluation_result_text = await get_gemini_evaluation(
            interview_question,
            transcript,
            pitch_analysis,
            emotion_analysis
        )
        if evaluation_result_text:
            parsed_evaluation = parse_gemini_response_data(evaluation_result_text)
            logger.info("--- ✨👑 Gemini AI面接評価結果 👑✨ ---")
            # JSON形式でログ出力すると見やすいかも！
            try:
                # 評価結果がもしJSON文字列なら、整形して表示試みる
                # 今回はparse_gemini_response_dataがdictを返すのでそのまま表示
                logger.info(json.dumps(parsed_evaluation, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                logger.info(parsed_evaluation.get("raw_evaluation", "解析済みデータなし")) # 生のテキストを表示
            logger.info("--- 👑 Gemini評価終了 👑 ---")
            # TODO: 必要であれば、この評価結果をどこかに保存したり、UIに通知したりする処理を追加
        else:
            logger.error("😢 Geminiからの評価取得に失敗しました。")
    # --- ここまでGemini評価システム用メソッド ---


async def main():
    # logger.setLevel(logging.DEBUG) # デバッグログも見たい場合は、ここで一時的にレベル変更！
    logger.info("🚀 メイン処理開始！ SpeechProcessorのテストだよん！")
    
    # 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されているか確認
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.warning("⚠️ 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されていません。")
        logger.warning("   Google Cloud Natural Language API の認証に失敗し、感情分析が機能しない可能性があります。")
        logger.warning("   設定例: export GOOGLE_APPLICATION_CREDENTIALS=\"/path/to/your/keyfile.json\"")
        # SentimentWorkerの初期化は language_client が None になるだけで、エラーにはならないはずだから処理は続行

    processor = SpeechProcessor()

    try:
        logger.info("マイクからの文字起こしを開始します (約20秒間)...")
        processor.set_interview_question("あなたの最大の強みと、それをどのように仕事に活かせるか教えてください。") # テスト用の質問を設定

        async def transcribe_task_wrapper():
            # transcribe_task内からprocessorの状態を参照できるようにする
            nonlocal processor 
            async for transcript in processor.start_realtime_transcription_from_mic():
                # logger.info(f"📢 メイン受信 (最終結果): {transcript}") # これは SpeechProcessor 側でログ出力
                if not processor._is_running: 
                    break
        
        transcription_coro = transcribe_task_wrapper()
        main_task = asyncio.create_task(transcription_coro)
        
        await asyncio.sleep(20) # 20秒間実行
        logger.info("\n⏳ 20秒経過、文字起こしを停止します...\n")
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Ctrl+C を検知！処理を中断します...")
    except Exception as e:
        logger.exception(f"😱 メイン処理で予期せぬエラー: {e}")
    finally:
        logger.info("🧹 クリーンアップ処理開始...")
        if hasattr(processor, '_is_running') and processor._is_running:
             await processor.stop_realtime_transcription_from_mic()
        
        # PyAudioインスタンスの解放は __del__ に任せるか、明示的に呼ぶ
        if hasattr(processor, 'pyaudio_instance') and processor.pyaudio_instance:
             processor.pyaudio_instance.terminate() 
        logger.info("👋 メイン処理完了！またね～！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"😱 asyncio.runでエラー発生！: {e}")
        logger.error("💡 もしかして: Google Cloud の認証設定してないとか？")
        logger.error("   gcloud auth application-default login とか試してみてね！") 