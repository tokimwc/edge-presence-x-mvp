import asyncio
import os
import sys

# このスクリプト (manual_test_speech_processor.py) があるディレクトリを取得
current_script_dir = os.path.dirname(os.path.abspath(__file__)) # .../tests/
# プロジェクトのルートディレクトリを取得 (testsの一つ上)
project_root_dir = os.path.dirname(current_script_dir) # .../edge-presence-x-mvp/

# プロジェクトルートの 'src' ディレクトリを直接 sys.path に追加する！
src_dir = os.path.join(project_root_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# これで `from backend.services.speech_processor import ...` でいけるはず！
try:
    # sys.path に src が入ったから、インポートパスを修正
    from backend.services.speech_processor import SpeechProcessor, RATE, CHANNELS, FORMAT
except ImportError as e:
    print("😭 あーん、SpeechProcessor が見つからないっ！")
    print(f"   エラー詳細: {e}")
    print("   もしかして、PYTHONPATHの設定が必要か、スクリプトの場所が違うかも？")
    print(f"   現在のsys.path: {sys.path}")
    print(f"   追加しようとしたsrc_dir: {src_dir}")
    sys.exit(1)

async def run_mic_test():
    """
    マイクからのリアルタイム文字起こしをテストするメイン関数だよん！
    """
    print("✨ マイク入力テスト開始！✨")
    print("話しかけてみてね！「終了」って言うか Ctrl+C で止められるよん。")
    print("-" * 30)
    print("📝 注意事項:")
    print("  - Google Cloud の認証情報 (環境変数 GOOGLE_APPLICATION_CREDENTIALS) が必要だよ！")
    print("    まだなら `gcloud auth application-default login` とか実行しといてね！")
    print("  - Windowsの場合、マイクのプライバシー設定でアプリからのアクセスが許可されてるか確認してね！")
    print("    「設定」 > 「プライバシー」 > 「マイク」でチェックできるはず！")
    print("  - もし「[Errno -9999] Unanticipated host error」みたいなのが出たら、")
    print("    使ってるマイクのサンプルレートとか設定がPyAudioと合ってないかも。")
    print(f"    今のPyAudio設定: RATE={RATE}, CHANNELS={CHANNELS}, FORMAT={FORMAT} (変更は speech_processor.py でね！)")
    print("  - Gemini評価もテストするから、GCPプロジェクトと認証情報、config/gemini_config.json の設定も確認してね！")
    print("-" * 30)

    processor = SpeechProcessor()
    test_interview_question = "自己PRを1分程度でお願いします。あなたの強みや経験、そしてこのAI面接システムを開発する上で最も挑戦的だったことは何ですか？"
    print(f"[テストスクリプト] SpeechProcessorに面接の質問を設定します: '{test_interview_question}'")
    processor.set_interview_question(test_interview_question)

    stop_keyword = "終了" # このキーワードで止まるようにするよん！
    should_stop = False

    try:
        async def transcription_loop():
            nonlocal should_stop
            
            # processor.start_realtime_transcription_from_mic() の結果を一旦変数に入れる
            stream_iterator = processor.start_realtime_transcription_from_mic()
            print(f"🔍 stream_iterator の型: {type(stream_iterator)}") # 型をプリント！
            print(f"🔍 hasattr(__aiter__): {hasattr(stream_iterator, '__aiter__')}") # __aiter__ 持ってるか確認！

            async for transcript in stream_iterator: # 変数を使ってループ
                if not processor._is_running: # processor 内部で停止されたら抜ける
                    print("🔄 processor が停止したからループ抜けるね！")
                    break
                
                print(f"📢 文字起こし結果: {transcript}")
                if stop_keyword in transcript:
                    print(f"🔍 「{stop_keyword}」を検知！そろそろ終わるね...")
                    should_stop = True
                    break # ループを抜けて停止処理へ

        # 文字起こしループをタスクとして実行
        transcription_task = asyncio.create_task(transcription_loop())

        while not should_stop and not transcription_task.done():
            await asyncio.sleep(0.1) # ちょっと待って、Ctrl+Cとかの割り込みをチェック

        if transcription_task.done() and transcription_task.exception():
            # タスク内で例外が発生した場合
            print(f"😱 文字起こしタスクでエラー発生: {transcription_task.exception()}")


    except KeyboardInterrupt:
        print("\n🛑 Ctrl+C を検知！処理を優雅に中断するよ...")
    except Exception as e:
        print(f"😱 テスト実行中に予期せぬエラーが発生しちゃった: {e}")
    finally:
        print("\n⏳ 文字起こし処理を停止中...")
        if hasattr(processor, '_is_running') and processor._is_running:
            await processor.stop_realtime_transcription_from_mic()
        
        # PyAudioインスタンスの解放 (念のため)
        # SpeechProcessorの__del__でも呼ばれるけど、明示的に呼んでおくと安心！
        if hasattr(processor, 'pyaudio_instance') and processor.pyaudio_instance:
            try:
                # PyAudioのterminate()は非同期じゃないので、イベントループが動いてるうちに呼ぶ
                if asyncio.get_event_loop().is_running():
                     await asyncio.to_thread(processor.pyaudio_instance.terminate)
                else:
                    processor.pyaudio_instance.terminate()
                print("💨 PyAudioインスタンス、ちゃんと解放したよ！")
            except Exception as e:
                print(f"🤔 PyAudio解放中にちょっとエラー: {e}")

        print("👋 テスト完了！お疲れ様でした～！")


if __name__ == "__main__":
    try:
        asyncio.run(run_mic_test())
    except Exception as e:
        # asyncio.run の外でキャッチできなかった例外の最終防衛ライン
        print(f"💥 スクリプトの実行に致命的なエラー: {e}")
        print("   GCP認証とか、Python環境とか、もう一回確認してみてね！") 