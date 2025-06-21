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
        if not self._stop_event.is_set():
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
                if not self._is_running or self._stop_event.is_set():
                    logger.info("is_runningがFalseまたはstop_eventがセットされたため、レスポンス処理ループを中断します。")
                    break

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
            logger.error(f"😱 _process_speech_streamで予期せぬエラー発生: {e}", exc_info=True)
            await self._send_to_client("error", {"message": f"音声処理中に予期せぬエラーが発生しました: {e}"})
        finally:
            logger.info("🏁 _process_speech_stream ループが終了しました。")
            # ここでワーカーを停止するのが確実！
            await self._stop_workers()

    async def _microphone_stream_generator(self):
        """
        キューから音声データを読み取ってGoogle APIにストリーミングする非同期ジェネレータ。
        WebSocketからのリアルタイム音声入力に対応してるよん！
        """
        # 1. 最初にストリーミング設定を送信
        recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code="ja-JP",
            enable_automatic_punctuation=True,
            # モデル選択: 'telephony'か'medical_conversation'などが用途に合わせて選べる
            # 'default' もあるけど、今回は汎用的な 'latest_long' を試してみる
            model="latest_long", 
            use_enhanced=True, # 高度な音声認識モデルを有効化
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=recognition_config,
            interim_results=True,  # 途中結果を取得する
            single_utterance=False # 複数回の発話を認識
        )
        yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
        logger.info("🎤 ストリーミング設定送信完了！音声待機中...")

        # 2. キューから音声データを読み取って送信
        while self._is_running and not self._stop_event.is_set():
            try:
                # タイムアウト付きでキューからデータを取得
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                yield speech.StreamingRecognizeRequest(audio_content=chunk)
            except asyncio.TimeoutError:
                # タイムアウトはエラーじゃない。データが来てないだけだからループを続ける
                continue
            except asyncio.CancelledError:
                logger.info("🎤 _microphone_stream_generatorがキャンセルされました。")
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
            final_evaluation = await self._run_final_evaluation()
            
            # 7. 最終評価をクライアントに送信
            logger.info("👑 最終評価が完了しました！")
            # logger.debug(f"最終評価ペイロード: {final_evaluation}")
            await self._send_to_client("final_evaluation", {"evaluation": final_evaluation})
            
            # Geminiからの構造化されたフィードバックも送信
            if self.gemini_enabled and isinstance(final_evaluation, dict):
                 # `final_evaluation` が辞書であり、期待するキーを持つか確認
                if "raw_evaluation" in final_evaluation and "score" in final_evaluation:
                    await self._send_to_client("gemini_feedback", final_evaluation)
                else:
                    # 互換性のためのフォールバック
                    await self._send_to_client("gemini_feedback", {
                        "raw_evaluation": str(final_evaluation),
                        "score": 50 # デフォルトスコア
                    })

        except Exception as e:
            logger.error(f"😱 最終評価の生成中にエラーが発生しました: {e}", exc_info=True)
            await self._send_to_client("error", {"message": "最終評価の生成中にエラーが発生しました。"})
        
        logger.info("✅ セッションが正常に終了しました。")


    async def _run_final_evaluation(self) -> dict | str:
        """
        セッション終了後に、収集したデータを使ってGeminiに最終評価をリクエストするよ！
        """
        logger.info("🧠 Geminiによる最終評価を準備中...")
        
        # 収集したデータをサマリー
        self.last_pitch_analysis_summary = self._summarize_pitch_data()

        # Geminiに渡すためのコンテキストを作成
        evaluation_context = {
            "question": self.current_interview_question,
            "full_transcript": self.full_transcript,
            "pitch_analysis": self.last_pitch_analysis_summary,
            "emotion_analysis": self.last_emotion_analysis_summary
        }
        
        if self.gemini_enabled:
            try:
                # gemini_service モジュールの関数を呼び出す
                response_data = await gemini_service.generate_structured_feedback(evaluation_context)
                logger.info("💎 Geminiから評価を取得しました！")
                # response_data は既に辞書のはず
                return response_data
            except Exception as e:
                logger.error(f"😱 Geminiへのリクエスト中にエラー: {e}", exc_info=True)
                return f"Gemini評価中にエラーが発生しました: {e}"
        else:
            logger.warning("😢 Geminiが無効なため、最終評価をスキップします。")
            return "Gemini評価は現在無効です。"


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