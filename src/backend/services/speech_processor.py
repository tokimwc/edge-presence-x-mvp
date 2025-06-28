# ここに Google Cloud Speech-to-Text のライブラリをインポートする感じで！
from google.cloud import speech_v1p1beta1 as speech # 非同期クライアントを使うよ！
from google.api_core import exceptions
import asyncio
import pyaudio
import logging # logging モジュールをインポート
import os # 環境変数のために追加
import time
import threading
from google.cloud import pubsub_v1 # ◀️ Pub/Subライブラリをインポート！
import json
import uuid # ◀️ セッションID生成のために追加！
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from datetime import datetime

# --- Pythonのモジュール検索パスにsrcディレクトリを追加 ---
import sys
# speech_processor.py のあるディレクトリ (src/backend/services)
_CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
# src ディレクトリの絶対パス (src/backend/services -> src/backend -> src)
_SRC_DIR = os.path.abspath(os.path.join(_CURRENT_FILE_DIR, '..', '..'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
# --- ここまで ---

# --- サービス、ワーカー、設定ファイルのインポート ---
from backend.services import gemini_service # gemini_serviceモジュールとしてインポート！
from backend.workers.pitch_worker import PitchWorker
from backend.services import dialogflow_service # ◀️ sentiment_worker の代わりに dialogflow_service をインポート！
from backend.services.gemini_service import GeminiService
# 新しく作った共通設定ファイルをインポート！
from backend.shared_config import RATE, CHUNK, CHANNELS, FORMAT, SAMPLE_WIDTH

# logging の基本設定 (モジュールレベルで１回だけ実行)
# SpeechProcessor クラスの外で設定するのが一般的だよん！
logging.basicConfig(
    level=logging.INFO,  # 開発中はINFOレベル以上を表示
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# このモジュール用のロガーを取得
logger = logging.getLogger(__name__)

# --- Pub/Sub関連の定数 ---
# 環境変数から取得するのがイケてるけど、まずはハードコードで。後で直す！
# TODO: GCPプロジェクトIDとトピック名を共通設定ファイルか環境変数から読み込むようにする
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "your-gcp-project-id")
TRANSCRIPTION_TOPIC = "ep-x-transcriptions"

# --- SpeechProcessorクラスでGemini関連のコードを管理するので、ここの重複は削除！ ---

class SpeechProcessor:
    """
    リアルタイム音声処理のクラスだよん！
    文字起こし、音程解析、感情分析、Gemini評価をまとめてやるぞ！
    """

    def __init__(self, websocket: WebSocket, send_to_client: callable):
        self.websocket = websocket
        self.send_to_client = send_to_client
        self.session_id = str(uuid.uuid4())
        self.gemini_service = GeminiService() # GeminiServiceを初期化
        self.speech_client = speech.SpeechAsyncClient()
        self._audio_queue = asyncio.Queue()
        self._is_running = False
        self._processing_task = None # メインの処理タスクを保持する
        self._microphone_task = None # 手動テスト用のマイクスレッドを保持する
        self._stop_event = asyncio.Event()
        self.main_loop = asyncio.get_event_loop()
        self.pyaudio_instance = None
        self.microphone_stream = None

        # --- Pub/Sub Publisherの初期化 ---
        try:
            self.publisher = pubsub_v1.PublisherClient()
            self.topic_path = self.publisher.topic_path(GCP_PROJECT_ID, TRANSCRIPTION_TOPIC)
            logger.info(f"✅ Pub/Sub Publisherの初期化完了！トピック: {self.topic_path}")
        except Exception as e:
            logger.exception("😱 Pub/Sub Publisher の初期化中にエラーが発生しました。")
            self.publisher = None
            self.topic_path = None
        # --- ここまでPub/Sub初期化 ---

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

        logger.info("✨ SpeechProcessor 初期化完了！✨")
        logger.info(f"PyAudio設定: FORMAT={FORMAT}, CHANNELS={CHANNELS}, RATE={RATE}, CHUNK={CHUNK}, SAMPLE_WIDTH={SAMPLE_WIDTH}")

        # --- Gemini評価システム関連の初期化 ---
        # __init__で生成したGeminiServiceインスタンスのプロパティをチェックする
        self.gemini_enabled = self.gemini_service.gemini_model_instance is not None
        if self.gemini_enabled:
            logger.info("👑 Gemini評価システムが有効になりました。")
        else:
            logger.warning("😢 Gemini評価システムは無効です。設定または認証情報を確認してください。")
        
        # --- セッション中のデータを保持する変数を初期化 ---
        self.current_interview_question = "自己PRをしてください。" # デフォルトの質問
        self.full_transcript = "" # 文字起こし全文を保持
        self.pitch_values = []    # ピッチの測定値を保持
        self.last_pitch_analysis_summary = {} # ピッチ解析の集計結果
        self.last_emotion_analysis_summary = {} # 感情分析の集計結果
        
        # --- ピッチ解析用のバッファと設定を追加 ---
        self._pitch_buffer = b""
        self._required_pitch_bytes = 0
        if self.pitch_worker:
            # pitch_workerが必要とする最小サンプル数(max_lag)の2倍をバイト数で計算
            # 2倍にすることで、より安定した解析が期待できる
            # 例: 16000Hz / 50Hz(min_freq) = 320サンプル -> 320 * 2(bytes) * 2 = 1280バイト
            self._required_pitch_bytes = self.pitch_worker.max_lag * self.pitch_worker.sample_width * 2
            logger.info(f"ピッチ解析に必要な最小バイト数: {self._required_pitch_bytes}")
        # --- ここまでセッションデータ変数 ---

    def _reset_session_data(self):
        """
        セッションに関連するデータをリセットする内部ヘルパー関数。
        start_transcription_and_evaluation が呼ばれたときに実行する。
        """
        self.session_id = str(uuid.uuid4())
        self._audio_queue = asyncio.Queue()
        self._stop_event.clear()
        self.full_transcript = ""
        self.pitch_values = []
        self._pitch_buffer = b""
        self.last_pitch_analysis_summary = {}
        self.last_emotion_analysis_summary = {}
        logger.info(f"新しいセッションIDでデータをリセットしました: {self.session_id}")

    async def process_audio_chunk(self, chunk: bytes):
        """
        WebSocketから受け取った音声チャンクを処理するよ。
        ピッチ解析、感情分析、文字起こしキューへの追加を行う。
        """
        if not self._is_running:
            return

        # 1. ピッチを解析
        if self.pitch_worker and self._required_pitch_bytes > 0:
            self._pitch_buffer += chunk

            # バッファが十分な大きさになったら解析
            if len(self._pitch_buffer) >= self._required_pitch_bytes:
                pitch = self.pitch_worker.analyze_pitch(self._pitch_buffer)
                
                if pitch is not None:
                    # 最終評価用に蓄積
                    self.pitch_values.append(pitch)
                    # リアルタイムでクライアントに送信！
                    timestamp = time.time()
                    await self._send_to_client(
                        "pitch_analysis",
                        {"pitch": pitch, "timestamp": timestamp}
                    )
                
                # バッファをスライドさせる (古いデータを削除)
                # 今回は解析ウィンドウの半分を削除して、次の解析とオーバーラップさせる
                slide_bytes = self._required_pitch_bytes // 2
                self._pitch_buffer = self._pitch_buffer[slide_bytes:]

        # 2. Symbl.aiへの音声データ送信は不要になったので削除！

        # 3. 文字起こし用のキューに音声データを追加
        if not self._stop_event.is_set():
            await self._audio_queue.put(chunk)

    async def _start_workers(self):
        """ワーカーの起動処理（現在は空）"""
        # PitchWorkerは都度呼び出すので、ここでは起動しない
        # SentimentWorkerもいなくなったので、ここは空っぽ！
        pass

    async def _stop_workers(self):
        """ワーカーの停止処理（現在は空）"""
        # PitchWorkerは都度呼び出すので、ここでは停止しない
        # SentimentWorkerもいなくなったので、ここは空っぽ！
        pass

    def _get_pyaudio_instance(self):
        """PyAudioのインスタンスを取得または生成するよ。マイクテストの時だけね！"""
        if self.pyaudio_instance is None:
            logger.info("PyAudioインスタンスがないので、新しく作るよ！")
            try:
                self.pyaudio_instance = pyaudio.PyAudio()
                logger.info("マイクテスト用にPyAudioインスタンスを新しく作ったよ！")
            except Exception:
                # ここでスタックトレースも出力する
                logger.error("PyAudioの初期化中にガチなエラーでちゃった…", exc_info=True)
                self.pyaudio_instance = None # 失敗したらNoneに戻す
        return self.pyaudio_instance

    async def _send_to_client(self, data_type, payload):
        """インスタンス化時に渡されたsend_to_client関数経由でクライアントにJSONデータを送信する"""
        if self.send_to_client:
            message = {"type": data_type, "payload": payload}
            await self.send_to_client(message)

    def _get_speech_client(self):
        # ... existing code ...
        pass

    def set_interview_question(self, question: str):
        """現在の面接の質問を設定するよん！"""
        self.current_interview_question = question
        logger.info(f"🎤 設定された面接の質問: {question}")

    # --- Symbl.ai用の _handle_emotion_data は不要になったので完全に削除！ ---

    async def _publish_to_pubsub(self, message_data: dict):
        """
        文字起こし結果などのデータをPub/Subに非同期で送信するよん！
        """
        if not self.publisher or not self.topic_path:
            logger.error("Pub/Sub Publisherが初期化されてないため、メッセージを送信できません。")
            return

        try:
            # データをJSON形式のバイト文字列にエンコード
            data = json.dumps(message_data, ensure_ascii=False).encode("utf-8")
            # メッセージをパブリッシュ！
            future = self.publisher.publish(self.topic_path, data)
            # 送信結果を待つ（非同期なので、ここでは待たずにログだけ出す）
            future.add_done_callback(lambda f: logger.info(f"📤 Pub/Subへのメッセージ送信完了: {f.result()}"))
            # await future # ここで待つとブロッキングしちゃうので注意！
        except exceptions.GoogleAPICallError as e:
            logger.error(f"😱 Pub/Subへの送信中にAPIエラーが発生しました: {e}")
        except Exception as e:
            logger.exception("😱 Pub/Subへの送信中に予期せぬエラーが発生しました。")

    async def _process_speech_stream(self):
        """
        音声ストリームを処理して、文字起こしと各種分析を実行するメインループだよん。
        """
        # --- 1. 音声ストリームの生成 ---
        audio_stream_generator = self._audio_stream_generator()

        # --- 2. Google Cloud Speech-to-Text APIへのリクエスト設定 ---
        # ...（中略）...
        recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code="ja-JP",
            enable_automatic_punctuation=True,
            profanity_filter=True, # 不適切な単語をフィルタリング
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=recognition_config,
            interim_results=True, # 暫定的な結果も受け取る
        )

        requests = self._create_streaming_requests(audio_stream_generator)

        try:
            logger.info("🚀 Google Speech-to-Text APIへのストリーミングを開始します...")
            # recognizeメソッドは非同期イテレータを返す！
            # 修正点: streaming_recognizeはコルーチンなのでawaitする
            stream = await self.speech_client.streaming_recognize(
                requests=requests
            )

            # ストリーミングのレスポンスを非同期で処理
            async for response in stream:
                if not self._is_running:
                    break
                
                if response.results:
                    result = response.results[0]
                    if result.alternatives:
                        transcript_chunk = result.alternatives[0].transcript

                        # 確定した文字起こしは全文に結合
                        if result.is_final:
                            self.full_transcript += transcript_chunk + " "
                            logger.info(f"✅ 最終的な文字起こし結果の断片: '{transcript_chunk}' (結合後の全文: '{self.full_transcript[:50]}...')")

                            # 感情分析は確定した断片ごとに行う
                            if len(transcript_chunk.strip()) > 1: # 1文字以上なら
                                try:
                                    logger.info(f"🤖 Dialogflowに感情分析をリクエスト: '{transcript_chunk}'")
                                    sentiment_result = await dialogflow_service.analyze_sentiment(
                                        session_id=self.session_id, text=transcript_chunk
                                    )
                                    # WebSocketクライアントに感情分析結果を送信
                                    if sentiment_result:
                                        await self._send_to_client("sentiment_update", {
                                            "sentiment": sentiment_result,
                                            "timestamp": datetime.now().isoformat()
                                        })
                                except Exception as e:
                                    logger.error(f"感情分析の呼び出しでエラーが発生しましたが、処理を続行します: {e}")

                        # interimもfinalも、常に更新された全文をフロントに送る！
                        # これでフロントは表示を更新するだけでよくなる
                        current_display_transcript = self.full_transcript + transcript_chunk if not result.is_final else self.full_transcript

                        realtime_data = {
                            "transcript": current_display_transcript,
                            "is_final": result.is_final
                        }
                        await self._send_to_client("transcript_update", realtime_data)

        except WebSocketDisconnect:
            logger.warning("🎤 音声ストリームの途中でクライアントが切断したっぽ！処理を終了するね〜👋")
        except exceptions.Cancelled as e:
            logger.warning("ストリーミングがキャンセルされました。これは正常な停止処理の一部である可能性があります。")
        except exceptions.OutOfRange as e:
            logger.error(f"😱 音声ストリームの終端に達しました: {e}")
        except exceptions.GoogleAPICallError as e:
            logger.error(f"😱 Google Speech-to-Text APIでエラー: {e}")
        except Exception as e:
            logger.exception(f"😱 _process_speech_streamで予期せぬエラーが発生しました。")
        finally:
            logger.info("👋 _process_speech_stream ループが終了しました。")
            self._stop_event.set()

    async def _create_streaming_requests(self, audio_generator):
        """
        Google Speech-to-Text APIに送信するリクエストのジェネレータだよん。
        最初に設定情報を送って、そのあとはひたすら音声データを送る！
        """
        # 最初にストリーミング設定を送信
        recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code="ja-JP",
            enable_automatic_punctuation=True,
            profanity_filter=True,
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=recognition_config,
            interim_results=True,
        )
        yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)

        # その後は音声データを非同期でストリーミング
        async for chunk in audio_generator:
            if not chunk:
                break
            yield speech.StreamingRecognizeRequest(audio_content=chunk)

    async def _audio_stream_generator(self):
        """キューから音声データを読み出して、ジェネレータとして返す非同期関数"""
        while self._is_running and not self._stop_event.is_set():
            try:
                # タイムアウト付きでキューからデータを取得
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                yield chunk
            except asyncio.TimeoutError:
                # タイムアウトはエラーじゃない。データが来てないだけだからループを続ける
                continue
            except asyncio.CancelledError:
                logger.info("🎤 _audio_stream_generatorがキャンセルされました。")
                break
        
        logger.info("🎤 音声ストリームジェネレータが終了します。")

    def _microphone_worker(self):
        """
        PyAudioを使ってマイクから音声を取得し、非同期キューに入れるワーカー関数。
        これは手動テスト (`manual_test_speech_processor.py`) のためのものだよん！
        """
        p = self._get_pyaudio_instance()
        if not p:
            logger.error("PyAudioインスタンスの取得に失敗したため、マイクワーカーを開始できません。")
            return

        try:
            self.microphone_stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                stream_callback=self._microphone_callback
            )
            logger.info("🎤 マイクストリームを開きました。録音開始！")

            while self.microphone_stream.is_active() and self._is_running:
                time.sleep(0.1)

        except Exception as e:
            logger.error(f"😱 マイクストリームのオープンまたは実行中にエラー: {e}", exc_info=True)
        finally:
            if self.microphone_stream:
                self.microphone_stream.stop_stream()
                self.microphone_stream.close()
                self.microphone_stream = None
                logger.info("🎤 マイクストリームを停止・クローズしました。")
            # PyAudioインスタンスの終了は __del__ で行う
            # p.terminate()

    def _microphone_callback(self, in_data, frame_count, time_info, status):
        """マイクからの音声データをキューに入れるコールバック"""
        # このコールバックは別スレッドから呼ばれるので、非同期のputではなくput_nowaitを使う
        try:
            # process_audio_chunkを直接呼び出すことでピッチ解析も実行
            # ただし、async関数なのでスレッドから呼び出すには工夫が必要
            # ここでは event_loop を使ってコルーチンをスケジュールする
            asyncio.run_coroutine_threadsafe(
                self.process_audio_chunk(in_data),
                self.main_loop
            )
        except Exception as e:
            logger.error(f"マイクコールバックでのキュー追加中にエラー: {e}")

        return (in_data, pyaudio.paContinue)


    async def start_transcription_and_evaluation(self):
        """
        文字起こしと評価のセッションを開始するメインの関数だよん！
        """
        if self._is_running:
            logger.warning("セッションはすでに実行中です。")
            return

        logger.info("🚀 WebSocketからのリアルタイムセッションを開始します...")
        self._is_running = True
        self._reset_session_data() # ◀️ セッション開始時にデータをリセット！
        
        # _process_speech_stream を非同期タスクとして実行
        self._processing_task = self.main_loop.create_task(self._process_speech_stream())
        
        # 関連するワーカーを起動
        await self._start_workers()

    async def start_realtime_transcription_from_mic(self):
        """
        【手動テスト用】マイクから直接音声を取得して、リアルタイム文字起こしと評価を開始するよん！
        """
        if self._is_running:
            logger.warning("🎙️ すでにマイクからのセッションが実行中です。")
            return
        
        logger.info("🚀 マイクからのリアルタイムセッションを開始します...")
        self._is_running = True
        self._stop_event.clear()
        
        # --- セッションデータをリセット ---
        self.full_transcript = ""
        self.pitch_values = []
        self._pitch_buffer = b"" # ピッチ解析バッファもリセット
        self.last_pitch_analysis_summary = {}
        self.last_emotion_analysis_summary = {}
        # --- ここまで ---

        # メインループを取得
        self.main_loop = asyncio.get_running_loop()

        # マイク入力用のワーカースレッドを開始
        self._microphone_task = threading.Thread(target=self._microphone_worker, daemon=True)
        self._microphone_task.start()
        
        # Speech-to-Textの処理タスクを開始
        self._processing_task = asyncio.create_task(self._process_speech_stream())
        logger.info("🔥 マイク音声のメイン処理ループを開始しました。")


    async def stop_transcription_and_evaluation(self):
        """
        文字起こしと評価の全プロセスを停止し、最終評価を実行するよ！
        """
        if not self._is_running:
            logger.warning("セッションはすでに停止しています。")
            return
        
        logger.info("セッション停止プロセスを開始します...")

        # 1. まずは新しい音声データを受け付けないようにフラグを立てる
        self._is_running = False
        self._stop_event.set()

        # 2. 音声キューをクリアし、ジェネレータに終了を通知するためのダミーデータを送信
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()
        await self._audio_queue.put(b"") #ジェネレータを確実に終了させる

        # 3. メインの処理タスクをキャンセル
        if self._processing_task and not self._processing_task.done():
            logger.info("メイン処理タスクをキャンセルします...")
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                logger.info("メイン処理タスクが正常にキャンセルされました。")

        # 4. ワーカーを停止（これは_process_speech_streamのfinallyでも呼ばれるけど念のため）
        await self._stop_workers()

        # 5. 手動テスト用のマイクスレッドが動いていたら停止
        if self._microphone_task and self._microphone_task.is_alive():
            logger.info("手動テスト用のマイクスレッドを停止します。")
            self._microphone_task.join()
            self._microphone_task = None

        logger.info("⏳ 全てのリアルタイム処理を停止しました。最終評価を開始します...")
        await self._send_to_client("evaluation_started", {})

        try:
            # 6. 最終評価の実行
            final_evaluation_result = await self._run_final_evaluation()
            
            # 7. 最終評価をクライアントに送信
            if final_evaluation_result and "error" not in final_evaluation_result:
                logger.info("👑 最終評価が完了しました！クライアントに送信します。")
                await self._send_to_client("final_evaluation", final_evaluation_result)
            else:
                logger.error("最終評価に失敗したか、エラーが含まれています。")
                error_message = final_evaluation_result.get("error", "最終評価の生成中に不明なエラーが発生しました。") if isinstance(final_evaluation_result, dict) else "最終評価の生成中に不明なエラーが発生しました。"
                await self._send_to_client("error", {"message": error_message})

        except Exception as e:
            logger.error(f"😱 最終評価の生成・送信プロセス全体でエラーが発生しました: {e}", exc_info=True)
            await self._send_to_client("error", {"message": "最終評価の生成中にクリティカルなエラーが発生しました。"})
        
        logger.info("✅ セッションが正常に終了しました。")


    async def _run_final_evaluation(self) -> dict:
        """
        セッション終了後に、収集したデータを使ってGeminiに最終評価をリクエストするよ！
        """
        logger.info("🧠 Geminiによる最終評価を準備中...")

        if not self.gemini_enabled:
            logger.warning("Gemini評価が無効になっているため、評価をスキップします。")
            return {"error": "Gemini evaluation is disabled."}

        # 1. ピッチデータの集計
        pitch_summary = self._summarize_pitch_data()
        
        # TODO: 感情分析データの集計ロジックを実装する
        logger.warning("セッション中の感情分析データは現在集計されていません。最終評価ではダミー値を使用します。")
        emotion_summary = {
            "dominant_emotion": "分析中",
            "emotion_score": "N/A"
        }

        # 2. Geminiに渡すための評価コンテキストを作成
        evaluation_context = {
            "interview_question": self.current_interview_question,
            "transcript": self.full_transcript,
            "average_pitch": pitch_summary.get("average_pitch", "N/A"),
            "pitch_variation": pitch_summary.get("pitch_variation", "N/A"),
            "dominant_emotion": emotion_summary.get("dominant_emotion", "N/A"),
            "emotion_score": emotion_summary.get("emotion_score", "N/A"),
        }
        
        logger.info("Geminiに渡す評価コンテキストを作成しました。")
        
        # 3. Geminiサービスを呼び出し
        try:
            gemini_eval = await self.gemini_service.generate_structured_feedback(
                evaluation_context=evaluation_context
            )
        except Exception as e:
            logger.error(f"Geminiサービス呼び出し中に予期せぬエラーが発生: {e}", exc_info=True)
            return {"error": "An unexpected error occurred while calling the Gemini service."}
        
        # 4. 結果を処理して返す
        if gemini_eval and "error" not in gemini_eval:
            logger.info("💎 Geminiから構造化された評価を取得しました！")
            return gemini_eval
        else:
            error_msg = gemini_eval.get('error') if gemini_eval else 'No response from Gemini'
            logger.error(f"⛑️ Geminiからの評価取得に失敗しました: {error_msg}")
            return {"error": f"Failed to get evaluation from Gemini: {error_msg}"}


    def _summarize_pitch_data(self):
        """ピッチデータのリストから統計情報を計算するよ"""
        if not self.pitch_values:
            logger.info("ピッチデータが収集されなかったので、ピッチの要約はスキップします。")
            return {}

        # npをインポート
        try:
            import numpy as np
        except ImportError:
            logger.warning("numpyがインストールされていないため、ピッチの統計情報を計算できません。")
            return {}

        try:
            pitches = np.array(self.pitch_values)
            average_pitch = np.mean(pitches)
            pitch_variation = np.std(pitches)
            
            summary = {
                "average_pitch": f"{average_pitch:.2f}",
                "pitch_variation": f"{pitch_variation:.2f}",
            }
            return summary
        except Exception as e:
            logger.error(f"ピッチデータの要約中にエラー: {e}", exc_info=True)
            return {}


    def __del__(self):
        # オブジェクトが破棄されるときにPyAudioをクリーンアップ
        if self.pyaudio_instance:
            logger.info("PyAudioインスタンスを解放します。")
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None