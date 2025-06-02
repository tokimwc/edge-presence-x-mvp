# ここに Google Cloud Speech-to-Text のライブラリをインポートする感じで！
from google.cloud import speech_v1p1beta1 as speech # 非同期クライアントを使うよ！
import asyncio
import pyaudio
import logging # logging モジュールをインポート

# PitchWorker をインポート
from ..workers.pitch_worker import PitchWorker

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
        # クラス内では、モジュールレベルで取得したロガーを使うか、
        # self.logger = logging.getLogger(self.__class__.__name__) みたいにクラス専用ロガーを作ってもOK
        # ここではモジュールレベルのloggerを使うね！
        self.speech_client = speech.SpeechAsyncClient()
        self.pyaudio_instance = pyaudio.PyAudio()
        self._audio_queue = asyncio.Queue()
        self._is_running = False
        self._microphone_task = None
        self._stop_event = asyncio.Event()
        self.main_loop = asyncio.get_event_loop() # ← メインスレッドのループを保存

        # PitchWorker のインスタンスを作成
        try:
            self.pitch_worker = PitchWorker(
                sample_rate=RATE,
                channels=CHANNELS,
                sample_width=SAMPLE_WIDTH, # PyAudioのFORMATから取得したサンプル幅を使用
                # min_freq, max_freq, confidence_threshold はデフォルト値を使用
            )
            logger.info("🎵 PitchWorker の初期化に成功しました。")
        except Exception as e:
            logger.exception("😱 PitchWorker の初期化中にエラーが発生しました。")
            self.pitch_worker = None # エラー時はNoneに設定

        logger.info("✨ SpeechProcessor 初期化完了！✨")
        logger.info(f"PyAudio設定: FORMAT={FORMAT}, CHANNELS={CHANNELS}, RATE={RATE}, CHUNK={CHUNK}, SAMPLE_WIDTH={SAMPLE_WIDTH}")

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
                # asyncio.Queueから音声チャンクを取得 (タイムアウト付き)
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                if chunk is None: # 停止の合図
                    break
                
                # Speech-to-Text API にチャンクを送信
                yield speech.StreamingRecognizeRequest(audio_content=chunk)

                # PitchWorker でピッチを解析 (同期的に呼び出す)
                if self.pitch_worker and chunk:
                    try:
                        # TODO: analyze_pitch がCPU負荷が高い場合、
                        # loop = asyncio.get_event_loop()
                        # pitch_hz = await loop.run_in_executor(None, self.pitch_worker.analyze_pitch, chunk)
                        # のように別スレッドで実行することを検討
                        pitch_hz = self.pitch_worker.analyze_pitch(chunk)
                        pitch_log_msg = f"{pitch_hz:.2f} Hz" if pitch_hz is not None else "N/A"
                        # 文字起こしログとピッチログをまとめて出力しないように、ピッチはDEBUGレベルにすることも検討
                        # logger.info(f"🎵 推定ピッチ: {pitch_log_msg}") # 個別のINFOログは冗長になる可能性
                    except Exception as e:
                        logger.error(f"😱 PitchWorker でのピッチ解析中にエラー: {e}")
                        # pitch_log_msg = "Error" # エラー時は特定の値にするなど
            
            except asyncio.TimeoutError:
                # タイムアウトの場合は何もしないでループを続ける (まだ音声が来てないだけかも)
                continue
            except Exception as e:
                logger.exception("😱 _microphone_stream_generator で予期せぬエラー") # logger.exception でスタックトレースも記録
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
                    
                    # ピッチ解析結果をここでログに出すか検討。ただし、_microphone_stream_generator 内の方が
                    # Speech APIへの送信とタイミングが近いため、そちらで処理するのが自然か。
                    # ここでピッチ解析を行うと、Speech APIへの送信チャンクとピッチ解析対象チャンクが同じになる保証がある。
                    # 今回は _microphone_stream_generator に任せる。
                    
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
                    logger.warning(f"🎤 PyAudio readエラー (たぶんオーバーフロー): {e}") # Warningレベルでいいかも
                    asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), self.main_loop)

            logger.info("🎙️ マイクストリームループ終了。ストリーム停止処理へ...")
            stream.stop_stream()
            stream.close()
            logger.info("🎙️ マイクストリーム正常終了。")
        except Exception as e:
            logger.exception("😱 _microphone_workerで致命的なエラー")
            # エラーが発生した場合もキューにNoneを送ってジェネレータを終了させる
        finally:
            if self._is_running: # まだ動いてるなら終了処理
                 # 保存しておいたメインループを使う！
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
        # キューをクリア
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()


        # マイクワーカースレッドを開始
        # asyncio.to_thread を使って、同期的な _microphone_worker を別スレッドで実行
        loop = asyncio.get_event_loop()
        self._microphone_task = loop.run_in_executor(None, self._microphone_worker)
        logger.info("🎧 マイクワーカースレッド開始！")

        try:
            responses = await self.speech_client.streaming_recognize(
                requests=self._microphone_stream_generator()
            )
            async for response in responses:
                if not self._is_running: break # 停止リクエストがあったら抜ける

                if not response.results:
                    continue
                result = response.results[0]
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript
                
                if result.is_final:
                    # 最終結果のログにピッチ情報を含めるか検討。
                    # ただし、ピッチ情報はチャンクごとなので、最終結果のタイミングとは必ずしも一致しない。
                    # ここでは文字起こし結果のみにフォーカス。
                    logger.info(f"✨ 最終結果キタコレ！: {transcript}")
                    yield transcript # 最終結果を返す
                else:
                    # 途中結果のログにピッチ情報を含める。
                    # _microphone_stream_generator で取得したピッチ情報をどうやってここまで持ってくるか？
                    # 現状の実装では、_microphone_stream_generator のループ内で Speech API への送信とピッチ解析を
                    # 行っているが、その結果をこの response ループまで伝えるのは少し複雑になる。
                    # 一旦、_microphone_worker 側で DEBUG レベルでピッチをログ出力し、
                    # Speech API レスポンス側では文字起こし結果のみを INFO でログ出力する方針とする。
                    logger.info(f"📝 途中結果: {transcript}")
                    # 途中結果も必要ならここで yield transcript とかできるよ！

        except Exception as e:
            logger.exception("😱 start_realtime_transcription_from_mic 内の streaming_recognize ループでエラー")
        finally:
            logger.info("🛑 文字起こし処理ループ終了。stop_realtime_transcription_from_mic を呼び出すよん！")
            # await self.stop_realtime_transcription_from_mic() # ここをコメントアウト！呼び出し元でやる！


    async def stop_realtime_transcription_from_mic(self):
        """
        マイク入力と文字起こし処理を停止するよん！
        """
        if not self._is_running:
            logger.info("もう止まってるよん！")
            return

        logger.info("⏳ リアルタイム文字起こし停止処理開始...")
        self._is_running = False
        self._stop_event.set() # ワーカーとジェネレータに停止を通知

        if self._microphone_task is not None:
            logger.info("🎤 マイクワーカースレッドの終了待ち...")
            try:
                # キューにNoneを入れてワーカー内のreadループを安全に抜けさせる試み
                # (既に入っているかもしれないが念のため)
                await asyncio.wait_for(self._audio_queue.put(None), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("audio_queue.put(None) タイムアウト (stop時)")
            except Exception as e:
                 logger.error(f"audio_queue.put(None) でエラー (stop時): {e}")

            try:
                await asyncio.wait_for(self._microphone_task, timeout=5.0) # タイムアウト付きで待つ
                logger.info("🎤 マイクワーカースレッド正常終了！")
            except asyncio.TimeoutError:
                logger.warning("🔥 マイクワーカースレッドの終了タイムアウト！")
            except Exception as e:
                logger.error(f"🔥 マイクワーカースレッド終了時にエラー: {e}")
            self._microphone_task = None
        
        # キューに残っているかもしれないデータをクリア
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


async def main():
    # logger.info に変更
    logger.info("🚀 メイン処理開始！ SpeechProcessorのテストだよん！")
    # logger.setLevel(logging.DEBUG) # デバッグログも見たい場合は、ここで一時的にレベル変更！
    processor = SpeechProcessor()

    try:
        # logger.info に変更
        logger.info("マイクからの文字起こしを開始します (約10秒間)...")
        # start_realtime_transcription_from_mic は非同期ジェネレータなので、
        # async for で結果を処理するよん
        async def transcribe_task():
            async for transcript in processor.start_realtime_transcription_from_mic():
                # logger.info に変更
                logger.info(f"📢 メイン受信 (最終結果): {transcript}")
                if not processor._is_running: # stopが呼ばれたら抜ける
                    break
        
        transcription_coro = transcribe_task()
        
        # 10秒後に停止するタスク
        stoppable_task = asyncio.create_task(transcription_coro)
        
        await asyncio.sleep(10) # 10秒間実行
        # logger.info に変更 (改行文字を削除)
        logger.info("⏳ 10秒経過、文字起こしを停止します...")
        
    except KeyboardInterrupt:
        # logger.info に変更 (改行文字を削除)
        logger.info("🛑 Ctrl+C を検知！処理を中断します...")
    except Exception as e:
        # logger.exception に変更してスタックトレースも出力
        logger.exception(f"😱 メイン処理で予期せぬエラー: {e}")
    finally:
        # logger.info に変更
        logger.info("🧹 クリーンアップ処理開始...")
        if hasattr(processor, '_is_running') and processor._is_running:
             await processor.stop_realtime_transcription_from_mic()
        # PyAudioインスタンスの解放は __del__ に任せるか、明示的に呼ぶ
        if hasattr(processor, 'pyaudio_instance') and processor.pyaudio_instance:
             processor.pyaudio_instance.terminate() # 明示的に呼んでおく
        # logger.info に変更
        logger.info("👋 メイン処理完了！またね～！")


if __name__ == "__main__":
    # Google Cloud の認証情報が設定されてないとここでエラーになるかも！
    # 環境変数 GOOGLE_APPLICATION_CREDENTIALS を設定するか、
    # gcloud auth application-default login を実行してね！
    try:
        asyncio.run(main())
    except Exception as e:
        # logger.exception に変更してスタックトレースも出力
        logger.exception(f"😱 asyncio.runでエラー発生！: {e}")
        # logger.error に変更
        logger.error("💡 もしかして: Google Cloud の認証設定してないとか？")
        # logger.error に変更
        logger.error("   gcloud auth application-default login とか試してみてね！") 