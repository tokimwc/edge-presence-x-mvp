# ここに Google Cloud Speech-to-Text のライブラリをインポートする感じで！
from google.cloud import speech_v1p1beta1 as speech # 非同期クライアントを使うよ！
from google.api_core import exceptions
import asyncio
import pyaudio
import logging # logging モジュールをインポート
import os # 環境変数のために追加
import time
import threading

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
from backend.workers.sentiment_worker import SentimentWorker
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

# --- SpeechProcessorクラスでGemini関連のコードを管理するので、ここの重複は削除！ ---

class SpeechProcessor:
    """
    リアルタイム音声処理のクラスだよん！
    文字起こし、音程解析、感情分析、Gemini評価をまとめてやるぞ！
    """

    def __init__(self):
        self.speech_client = speech.SpeechAsyncClient()
        self._audio_queue = asyncio.Queue()
        self._is_running = False
        self._processing_task = None # メインの処理タスクを保持する
        self._microphone_task = None # 手動テスト用のマイクスレッドを保持する
        self._stop_event = asyncio.Event()
        self.main_loop = asyncio.get_event_loop()
        self.pyaudio_instance = None
        self.microphone_stream = None
        self.send_to_client_callback = None # 送信コールバック関数

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
        # gemini_service モジュールのインポート時に初期化が走るから、ここではインスタンスの有無をチェックするだけ！
        self.gemini_enabled = gemini_service.gemini_model_instance is not None
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
        # --- ここまでセッションデータ変数 ---

    async def process_audio_chunk(self, chunk: bytes):
        """
        WebSocketから受け取った音声チャンクを処理するよ。
        ピッチ解析と、文字起こしキューへの追加を行う。
        """
        if not self._is_running:
            return

        # 1. ピッチを解析
        if self.pitch_worker:
            pitch = self.pitch_worker.analyze_pitch(chunk)
            if pitch is not None:
                self.pitch_values.append(pitch)
                # logger.debug(f"🎤 検出されたピッチ: {pitch:.2f} Hz") # デバッグ用に便利

        # 2. 文字起こし用のキューに音声データを追加
        await self._audio_queue.put(chunk)

    async def _start_workers(self):
        """感情分析ワーカーを起動するよん！"""
        # PitchWorkerは都度呼び出すので、ここでは起動しない
        if self.sentiment_worker:
            # startが非同期メソッドの可能性があるのでawaitする
            await self.sentiment_worker.start()

    async def _stop_workers(self):
        """感情分析ワーカーを停止するよん！"""
        # PitchWorkerは都度呼び出すので、ここでは停止しない
        if self.sentiment_worker:
            # stopが非同期メソッドの可能性があるのでawaitする
            await self.sentiment_worker.stop()

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

    def set_send_to_client_callback(self, callback):
        """フロントエンドにデータを送るための非同期コールバック関数をセットするよ"""
        self.send_to_client_callback = callback

    async def _send_to_client(self, data_type, payload):
        """コールバック経由でクライアントにJSONデータを送信する"""
        if self.send_to_client_callback:
            message = {"type": data_type, "payload": payload}
            await self.send_to_client_callback(message)

    def _get_speech_client(self):
        # ... existing code ...
        pass

    def set_interview_question(self, question: str):
        """現在の面接の質問を設定するよん！"""
        self.current_interview_question = question
        logger.info(f"🎤 設定された面接の質問: {question}")

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

    async def _process_speech_stream(self):
        """
        キューからの音声データをGoogleに送り、結果を処理するメインループだよん！
        WebSocketからのストリーム用に調整したバージョン。
        """
        try:
            # 1. Google Speech-to-Text APIに接続し、ストリーミング設定を送信
            stream_generator = self._microphone_stream_generator()
            # streaming_recognizeはイテレータを返すコルーチンなので、awaitで解決する
            responses_iterator = await self.speech_client.streaming_recognize(requests=stream_generator)
            logger.info("✅ Google Speech-to-Text APIとの接続完了！レスポンス待機中...")

            # 2. ワーカープロセスを開始
            await self._start_workers()

            # 3. レスポンスを非同期で処理
            async for response in responses_iterator:
                if not self._is_running:
                    logger.info("is_runningがFalseになったため、レスポンス処理ループを中断します。")
                    break

                # --- デバッグログ: レスポンス全体を出力 ---
                # logger.debug(f"Googleからのレスポンス受信: {response}")

                if not response.results:
                    continue

                result = response.results[0]
                if not result.alternatives:
                    continue

                transcript = result.alternatives[0].transcript
                
                # ワーカーにテキストデータを渡す
                if self.sentiment_worker:
                    await self.sentiment_worker.add_text(transcript)

                if result.is_final:
                    logger.info(f"✅ 確定した文字起こし: {transcript}")
                    # 全文文字起こしを更新
                    self.full_transcript += transcript + " "
                    await self._send_to_client(
                        "final_transcript_segment", 
                        {"transcript": transcript}
                    )
                else:
                    # logger.info(f"💬 仮の文字起こし: {transcript}")
                    await self._send_to_client(
                        "interim_transcript",
                        {"transcript": transcript}
                    )
        except asyncio.CancelledError:
            logger.info("🚫 _process_speech_stream タスクがキャンセルされました。")
            # キャンセル時は速やかに終了
            raise
        except StopAsyncIteration:
             logger.info("ストリームが正常に終了しました。")
        except exceptions.OutOfRange as e:
            # 音声タイムアウトエラーをここでキャッチ！
            logger.error(f"😱 音声タイムアウトエラーが発生しました: {e}")
            await self._send_to_client("error", {"message": "長時間音声が検出されなかったため、タイムアウトしました。"})
        except Exception as e:
            logger.error(f"😱 _process_speech_streamで予期せぬエラー発生！: {e}", exc_info=True)
            await self._send_to_client("error", {"message": f"音声処理中に予期せぬエラーが発生しました: {e}"})
        finally:
            logger.info("🏁 _process_speech_stream ループが終了しました。")
            # ここではワーカーを止めない。stop_transcription_and_evaluationで制御する。

    async def _microphone_stream_generator(self):
        """
        キューからの音声データを非同期で供給するジェネレータだよん！
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
                    logger.info("キューからNoneを受け取ったのでジェネレータを終了します。")
                    break
                
                # --- PitchWorkerの処理をここに移動しない ---
                # このジェネレータはSpeech-to-Text APIにデータを送ることに専念する
                # ピッチ解析は process_audio_chunk で行われる
                
                yield speech.StreamingRecognizeRequest(audio_content=chunk)
            except asyncio.TimeoutError:
                # タイムアウトは想定内の動作なので、ログレベルをDEBUGに
                # logger.debug("キューからの待機がタイムアウトしました。次のループへ。")
                continue
            except asyncio.CancelledError:
                logger.info("ジェネレータがキャンセルされました。")
                break
            except Exception as e:
                logger.error(f"😱 _microphone_stream_generatorで予期せぬエラー: {e}", exc_info=True)
                break
        logger.info("🎤 _microphone_stream_generator 終了")

    def _microphone_worker(self):
        """
        PyAudioでマイクから音声を取得し、キューに入れるワーカー関数 (スレッドで実行)。
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
        WebSocketからの音声ストリームを受け付けるためのセッションを開始するよん！
        """
        if self._is_running:
            logger.warning("🖥️ すでにセッションが実行中です。")
            return

        logger.info("🚀 WebSocketからのリアルタイムセッションを開始します...")
        self._is_running = True
        self._stop_event.clear()
        
        # --- セッションデータをリセット ---
        self.full_transcript = ""
        self.pitch_values = []
        self.last_pitch_analysis_summary = {}
        self.last_emotion_analysis_summary = {}
        # --- ここまで ---

        self._processing_task = asyncio.create_task(self._process_speech_stream())
        logger.info("🔥 メイン処理ループを開始しました。")

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
        文字起こしと評価のセッションを停止し、最終評価を取得するよん！
        """
        logger.info("⏳ 文字起こしと評価の処理を停止中...")

        if not self._is_running:
            logger.warning("ストリームはすでに停止しています。")
            return

        self._is_running = False
        self._stop_event.set()

        # マイクストリーミングを停止
        # マイク用のキューにNoneを入れてジェネレータを止める
        if self._audio_queue:
            await self._audio_queue.put(None)

        # メイン処理タスクの完了を待つ
        if self._processing_task:
            try:
                await asyncio.wait_for(self._processing_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("⌛ _processing_task の停止がタイムアウトしました。")
                self._processing_task.cancel()
            except Exception as e:
                logger.error(f"😱 _processing_task 停止中にエラー: {e}", exc_info=True)
        
        # マイクスレッドの停止（手動テスト用）
        if self._microphone_task and self._microphone_task.is_alive():
            # この部分は手動テスト用なので、WebSocket経由では直接呼ばれない
            logger.info("🎤 マイクスレッドの終了を待機中...")
            # _microphone_worker内のループは_is_runningフラグで終了するはず
            self._microphone_task.join(timeout=3.0)
            if self._microphone_task.is_alive():
                logger.warning("🎤 マイクスレッドの終了がタイムアウトしました。")


        # ワーカーを停止
        await self._stop_workers()
        logger.info("✅ ワーカーを停止しました。")
        
        # --- 最終評価の実行 ---
        if self.gemini_enabled:
            logger.info("⏳最終評価をGeminiにリクエスト中...")
            
            # ピッチデータのサマリーを作成
            self._summarize_pitch_data()

            # フロントエンドに評価中であることを通知
            await self._send_to_client("evaluation_started", {})
            
            try:
                final_evaluation = await gemini_service.get_gemini_evaluation(
                    interview_question=self.current_interview_question,
                    transcript=self.full_transcript.strip(),
                    pitch_analysis=self.last_pitch_analysis_summary,
                    emotion_analysis=self.last_emotion_analysis_summary,
                )
                logger.info(f"👑 Geminiからの最終評価:\n{final_evaluation}")

                # フロントエンドに最終評価を送信
                await self._send_to_client(
                    "final_evaluation",
                    {"evaluation": final_evaluation}
                )

            except Exception as e:
                logger.error(f"😱 Geminiへの評価リクエスト中にエラーが発生: {e}", exc_info=True)
                await self._send_to_client(
                    "error",
                    {"message": f"Gemini評価中にエラーが発生しました: {e}"}
                )
        else:
            logger.warning("😢 Gemini評価は無効なため、最終評価はスキップされました。")

        logger.info("✅ すべてのセッション処理が完了しました。")

        # リソースのクリーンアップ
        self._stop_event.clear()
        self._processing_task = None
        self._microphone_task = None
        # キューをクリアする
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()
            
    def _summarize_pitch_data(self):
        """セッション中に収集したピッチデータを要約して、last_pitch_analysis_summaryを更新する"""
        if not self.pitch_values:
            logger.info("ピッチデータが収集されなかったので、ピッチの要約はスキップします。")
            self.last_pitch_analysis_summary = {
                "average_pitch": "データなし",
                "pitch_variation": "データなし",
                "pitch_stability": "データなし",
                "min_pitch": "データなし",
                "max_pitch": "データなし",
            }
            return

        try:
            import numpy as np
            
            # NumPy配列に変換
            pitch_array = np.array(self.pitch_values)
            
            # 平均ピッチ
            avg_pitch = np.mean(pitch_array)
            # ピッチの標準偏差（変動）
            std_dev_pitch = np.std(pitch_array)
            # ピッチの安定性（変動係数） - 平均に対する変動の割合
            # avg_pitchが0の場合のゼロ除算を避ける
            cv_pitch = (std_dev_pitch / avg_pitch) * 100 if avg_pitch > 0 else 0
            # 最小・最大ピッチ
            min_pitch = np.min(pitch_array)
            max_pitch = np.max(pitch_array)

            self.last_pitch_analysis_summary = {
                "average_pitch": f"{avg_pitch:.2f} Hz",
                "pitch_variation": f"{std_dev_pitch:.2f} Hz (標準偏差)",
                "pitch_stability": f"{cv_pitch:.2f} % (変動係数)",
                "min_pitch": f"{min_pitch:.2f} Hz",
                "max_pitch": f"{max_pitch:.2f} Hz",
            }
            logger.info(f"🎤 ピッチデータの要約完了: {self.last_pitch_analysis_summary}")

        except ImportError:
            logger.warning("NumPyがインストールされていないため、ピッチの統計情報を計算できません。")
            self.last_pitch_analysis_summary = {"error": "NumPy not found"}
        except Exception as e:
            logger.error(f"ピッチデータの要約中にエラーが発生しました: {e}", exc_info=True)
            self.last_pitch_analysis_summary = {"error": str(e)}


    def __del__(self):
        # オブジェクトが破棄されるときにPyAudioをクリーンアップ
        if self.pyaudio_instance:
            logger.info("PyAudioインスタンスを解放します。")
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None