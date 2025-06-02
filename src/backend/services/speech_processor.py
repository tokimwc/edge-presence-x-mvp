# ここに Google Cloud Speech-to-Text のライブラリをインポートする感じで！
from google.cloud import speech_v1p1beta1 as speech # 非同期クライアントを使うよ！
import asyncio
import pyaudio

# PyAudioの設定 (これらの値はマイクや要件に合わせて調整してね！)
FORMAT = pyaudio.paInt16  # 音声フォーマット (16bit)
CHANNELS = 1             # モノラル
RATE = 16000             # サンプルレート (16kHz)
CHUNK = int(RATE / 10)   # 100ms分のフレームサイズ (Speech-to-Textの推奨に合わせて)

class SpeechProcessor:
    def __init__(self):
        self.speech_client = speech.SpeechAsyncClient()
        self.pyaudio_instance = pyaudio.PyAudio()
        self._audio_queue = asyncio.Queue()
        self._is_running = False
        self._microphone_task = None
        self._stop_event = asyncio.Event()
        self.main_loop = asyncio.get_event_loop() # ← メインスレッドのループを保存

        print("✨ SpeechProcessor 初期化完了！✨")
        print(f"PyAudio設定: FORMAT={FORMAT}, CHANNELS={CHANNELS}, RATE={RATE}, CHUNK={CHUNK}")

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
        print("🎤 ストリーミング設定送信完了！音声待機中...")

        while self._is_running and not self._stop_event.is_set():
            try:
                # asyncio.Queueから音声チャンクを取得 (タイムアウト付き)
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                if chunk is None: # 停止の合図
                    break
                yield speech.StreamingRecognizeRequest(audio_content=chunk)
            except asyncio.TimeoutError:
                # タイムアウトの場合は何もしないでループを続ける (まだ音声が来てないだけかも)
                continue
            except Exception as e:
                print(f"😱 _microphone_stream_generator でエラー: {e}")
                break
        print("🎤 _microphone_stream_generator 終了")


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
            print("🎙️ マイクストリーム開始！ 音声収集中...")
            data_counter = 0 # デバッグ用カウンター
            while self._is_running and not self._stop_event.is_set():
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    data_counter += 1
                    # 音声データの中身をちょっとだけ表示 (最初の10バイトとか) と長さ
                    print(f"🎤 [Worker-{data_counter}] チャンク受信！ サイズ: {len(data)}, 先頭10バイト: {data[:10].hex() if data else 'None'}")
                    
                    asyncio.run_coroutine_threadsafe(self._audio_queue.put(data), self.main_loop)
                except IOError as e:
                    print(f"🎤 PyAudio readエラー (たぶんオーバーフロー): {e}")
                    asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), self.main_loop)

            print("🎙️ マイクストリーム停止中...")
            stream.stop_stream()
            stream.close()
            print("🎙️ マイクストリーム正常終了。")
        except Exception as e:
            print(f"😱 _microphone_workerで致命的なエラー: {e}")
            # エラーが発生した場合もキューにNoneを送ってジェネレータを終了させる
        finally:
            if self._is_running: # まだ動いてるなら終了処理
                 # 保存しておいたメインループを使う！
                 asyncio.run_coroutine_threadsafe(self._audio_queue.put(None), self.main_loop)


    async def start_realtime_transcription_from_mic(self):
        """
        マイクからのリアルタイム文字起こしを開始するよん！文字起こし結果を非同期で返す。
        """
        if self._is_running:
            print("既に実行中だよん！")
            return

        print("🚀リアルタイム文字起こし開始準備...")
        self._is_running = True
        self._stop_event.clear()
        # キューをクリア
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()


        # マイクワーカースレッドを開始
        # asyncio.to_thread を使って、同期的な _microphone_worker を別スレッドで実行
        loop = asyncio.get_event_loop()
        self._microphone_task = loop.run_in_executor(None, self._microphone_worker)
        print("🎧 マイクワーカースレッド開始！")

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
                    print(f"✨ 最終結果キタコレ！: {transcript}")
                    yield transcript # 最終結果を返す
                else:
                    print(f"📝 途中結果: {transcript}")
                    # 途中結果も必要ならここで yield transcript とかできるよ！

        except Exception as e:
            print(f"😱 start_realtime_transcription_from_mic でエラー: {e}")
        finally:
            print("🛑 文字起こし処理ループ終了。")
            # await self.stop_realtime_transcription_from_mic() # ここをコメントアウト！呼び出し元でやる！


    async def stop_realtime_transcription_from_mic(self):
        """
        マイク入力と文字起こし処理を停止するよん！
        """
        if not self._is_running:
            print("もう止まってるよん！")
            return

        print("⏳ リアルタイム文字起こし停止処理開始...")
        self._is_running = False
        self._stop_event.set() # ワーカーとジェネレータに停止を通知

        if self._microphone_task is not None:
            print("🎤 マイクワーカースレッドの終了待ち...")
            try:
                # キューにNoneを入れてワーカー内のreadループを安全に抜けさせる試み
                # (既に入っているかもしれないが念のため)
                await asyncio.wait_for(self._audio_queue.put(None), timeout=1.0)
            except asyncio.TimeoutError:
                print("audio_queue.put(None) タイムアウト")
            except Exception as e:
                 print(f"audio_queue.put(None) でエラー: {e}")

            try:
                await asyncio.wait_for(self._microphone_task, timeout=5.0) # タイムアウト付きで待つ
                print("🎤 マイクワーカースレッド正常終了！")
            except asyncio.TimeoutError:
                print("🔥 マイクワーカースレッドの終了タイムアウト！")
            except Exception as e:
                print(f"🔥 マイクワーカースレッド終了時にエラー: {e}")
            self._microphone_task = None
        
        # キューに残っているかもしれないデータをクリア
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        print("✅ リアルタイム文字起こし停止完了！")

    def __del__(self):
        """
        オブジェクトが消えるときにPyAudioリソースを解放するよん
        """
        if hasattr(self, 'pyaudio_instance') and self.pyaudio_instance:
            print("💨 PyAudioインスタンスを解放します...")
            self.pyaudio_instance.terminate()
            print("💨 PyAudioインスタンス解放完了！")


async def main():
    print("🚀 メイン処理開始！ SpeechProcessorのテストだよん！")
    processor = SpeechProcessor()

    try:
        print("マイクからの文字起こしを開始します (約10秒間)...")
        # start_realtime_transcription_from_mic は非同期ジェネレータなので、
        # async for で結果を処理するよん
        async def transcribe_task():
            async for transcript in processor.start_realtime_transcription_from_mic():
                print(f"📢 メイン受信 (最終結果): {transcript}")
                if not processor._is_running: # stopが呼ばれたら抜ける
                    break
        
        transcription_coro = transcribe_task()
        
        # 10秒後に停止するタスク
        stoppable_task = asyncio.create_task(transcription_coro)
        
        await asyncio.sleep(10) # 10秒間実行
        print("\n⏳ 10秒経過、文字起こしを停止します...\n")
        
    except KeyboardInterrupt:
        print("\n🛑 Ctrl+C を検知！処理を中断します...")
    except Exception as e:
        print(f"😱 メイン処理で予期せぬエラー: {e}")
    finally:
        print("🧹 クリーンアップ処理開始...")
        if hasattr(processor, '_is_running') and processor._is_running:
             await processor.stop_realtime_transcription_from_mic()
        # PyAudioインスタンスの解放は __del__ に任せるか、明示的に呼ぶ
        if hasattr(processor, 'pyaudio_instance') and processor.pyaudio_instance:
             processor.pyaudio_instance.terminate() # 明示的に呼んでおく
        print("👋 メイン処理完了！またね～！")


if __name__ == "__main__":
    # Google Cloud の認証情報が設定されてないとここでエラーになるかも！
    # 環境変数 GOOGLE_APPLICATION_CREDENTIALS を設定するか、
    # gcloud auth application-default login を実行してね！
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"😱 asyncio.runでエラー発生！: {e}")
        print("💡 もしかして: Google Cloud の認証設定してないとか？")
        print("   gcloud auth application-default login とか試してみてね！") 