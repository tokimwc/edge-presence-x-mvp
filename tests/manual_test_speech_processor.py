import asyncio
import os
import sys
import json

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
    # テストスクリプトからはクライアントに送信する機能はないので、ダミーのコールバックを設定
    async def dummy_send_to_client(data):
        # 評価結果などをコンソールに出力する
        if data.get("type") == "gemini_feedback":
            print("--- ✨👑 Gemini AI面接評価結果 (手動テスト) 👑✨ ---")
            print(json.dumps(data.get("payload", {}), indent=2, ensure_ascii=False))
            print("--- 👑 Gemini評価終了 👑 ---")
        else:
            print(f"[TO_CLIENT_DUMMY] {data}")

    processor.set_send_to_client_callback(dummy_send_to_client)

    test_interview_question = "自己PRを1分程度でお願いします。"
    print(f"[テストスクリプト] SpeechProcessorに面接の質問を設定します: '{test_interview_question}'")
    processor.set_interview_question(test_interview_question)

    stop_keyword = "終了"
    should_stop = False
    transcription_task = None

    try:
        # マイクからの文字起こしを開始
        # この関数はすぐにリターンし、バックグラウンドで処理を開始する
        await processor.start_realtime_transcription_from_mic()

        print("🎤 話し始めてください。約30秒後に自動で停止します。")
        
        # 30秒間、処理を続ける
        await asyncio.sleep(30)

    except KeyboardInterrupt:
        print("\n🛑 Ctrl+C を検知！処理を優雅に中断するよ...")
    except Exception as e:
        print(f"😱 テスト実行中に予期せぬエラーが発生しちゃった: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n⏳ 文字起こしと評価の処理を停止中...")
        await processor.stop_transcription_and_evaluation()
        
        # PyAudioインスタンスの解放
        if hasattr(processor, 'pyaudio_instance') and processor.pyaudio_instance:
            processor.pyaudio_instance.terminate()
            print("💨 PyAudioインスタンス、ちゃんと解放したよ！")

        print("👋 テスト完了！お疲れ様でした～！")


if __name__ == "__main__":
    try:
        asyncio.run(run_mic_test())
    except Exception as e:
        # asyncio.run の外でキャッチできなかった例外の最終防衛ライン
        print(f"💥 スクリプトの実行に致命的なエラー: {e}")
        print("   GCP認証とか、Python環境とか、もう一回確認してみてね！") 