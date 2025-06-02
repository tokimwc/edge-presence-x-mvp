# ここに Google Cloud Speech-to-Text のライブラリをインポートする感じで！
from google.cloud import speech_v1p1beta1 as speech # 非同期クライアントを使うよ！
import asyncio
import pyaudio
import logging # logging モジュールをインポート
import os # 環境変数のために追加

# Worker をインポート
from ..workers.pitch_worker import PitchWorker
from ..workers.sentiment_worker import SentimentWorker # SentimentWorker をインポート

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
            # SYMBL_APP_ID と SYMBL_APP_SECRET は環境変数から読み込まれる想定
            self.sentiment_worker = SentimentWorker(
                on_emotion_callback=self._handle_emotion_data,
                language_code="ja-JP" # 日本語に設定
            )
            logger.info("😊 SentimentWorker の初期化に成功しました。")
        except ValueError as ve: # APIキー未設定などのValueErrorをキャッチ
            logger.error(f"😱 SentimentWorker の初期化に失敗: {ve}")
            self.sentiment_worker = None
        except Exception as e:
            logger.exception("😱 SentimentWorker の初期化中に予期せぬエラーが発生しました。")
            self.sentiment_worker = None

        logger.info("✨ SpeechProcessor 初期化完了！✨")
        logger.info(f"PyAudio設定: FORMAT={FORMAT}, CHANNELS={CHANNELS}, RATE={RATE}, CHUNK={CHUNK}, SAMPLE_WIDTH={SAMPLE_WIDTH}")

    def _handle_emotion_data(self, emotion_data: dict):
        """
        SentimentWorkerからの感情分析結果を処理するコールバック関数。
        """
        dominant_emotion = emotion_data.get("dominant_emotion", "N/A")
        emotions = emotion_data.get("emotions", {})
        # score を整形してログ出力
        scores_str = ", ".join([f"{key}: {value:.2f}" for key, value in emotions.items()])
        logger.info(f"😊 感情分析結果: 主な感情={dominant_emotion} (スコア: {scores_str if scores_str else 'N/A'}) テキスト: '{emotion_data.get("text_processed", "")[:50]}...'")

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


async def main():
    # logger.setLevel(logging.DEBUG) # デバッグログも見たい場合は、ここで一時的にレベル変更！
    logger.info("🚀 メイン処理開始！ SpeechProcessorのテストだよん！")
    
    # 環境変数 SYMBL_APP_ID と SYMBL_APP_SECRET が設定されているか確認
    if not os.getenv("SYMBL_APP_ID") or not os.getenv("SYMBL_APP_SECRET"):
        logger.warning("⚠️ 環境変数 SYMBL_APP_ID または SYMBL_APP_SECRET が設定されていません。感情分析はスキップされます。")
        # この場合、SentimentWorkerの初期化は失敗するが、プログラムは続行可能

    processor = SpeechProcessor()

    try:
        logger.info("マイクからの文字起こしを開始します (約20秒間)...")
        
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