# ここに Google Cloud Speech-to-Text のライブラリをインポートする感じで！
from google.cloud import speech

speech_client = speech.SpeechClient()

def process_audio_stream(audio_stream, sample_rate):
    """
    マイクからの音声ストリームをリアルタイムで文字起こしするよん！

    Args:
        audio_stream: マイクとかから来る音声データのイテレータ的なやつ
        sample_rate: 音声データのサンプルレート (例: 16000)

    Returns:
        文字起こし結果のストリーム（これもイテレータ的な感じになるはず！）
    """
    print(f"🎤 音声ストリーム処理開始！サンプルレート: {sample_rate} Hz")

    requests = (
        speech.StreamingRecognizeRequest(audio_content=chunk) for chunk in audio_stream
    )

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate,
        language_code="ja-JP",  # 日本語でいくっしょ！
        enable_automatic_punctuation=True, # 句読点も自動で入れてくれるとマジ助かる
        # interim_results=True にすると、途中結果も見れてイケてる感じになるはず！
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=config, interim_results=True # 中間結果も見るようにしとこ！
    )

    responses = speech_client.streaming_recognize(
        config=streaming_config,
        requests=requests,
    )

    for response in responses:
        if not response.results:
            continue

        result = response.results[0]
        if not result.alternatives:
            continue

        transcript = result.alternatives[0].transcript
        print(f"📝 文字起こし途中結果: {transcript}") # 途中結果もログに出してみる

        if result.is_final:
            print(f"✨ 最終結果キタコレ！: {transcript}")
            yield transcript # 最終結果だけ返す感じで！

if __name__ == "__main__":
    # 簡単なテスト用 (実際はWebRTCとかから音声データが来る想定)
    print("テスト実行中...")
    # ダミーの音声チャンクをもう少しリアルな感じにしてみる (空のバイト列とか)
    # 実際にはマイクから短い間隔で音声データが送られてくるイメージ
    dummy_audio_chunks = [
        b'\x00\x00' * 1600,  # 0.1秒分の無音データ (16kHz, 16bit モノラル)
        b'\x01\x02' * 1600,
        b'\x03\x04' * 1600,
        b'\x00\x00' * 1600,
    ]
    
    def audio_generator(chunks):
        for chunk in chunks:
            # print(f"送信チャンクサイズ: {len(chunk)}") # デバッグ用
            yield chunk

    # Google Cloud の認証情報が設定されてないとここでエラーになるかも！
    # その場合は、環境変数 GOOGLE_APPLICATION_CREDENTIALS を設定するか、
    # gcloud auth application-default login を実行してね！
    try:
        for transcript_part in process_audio_stream(audio_generator(dummy_audio_chunks), 16000):
            print(f"📢 受信 (最終結果): {transcript_part}")
    except Exception as e:
        print(f"😱 エラー発生！: {e}")
        print("💡 もしかして: Google Cloud の認証設定してないとか？")
        print("   gcloud auth application-default login とか試してみてね！")
    print("テスト完了！") 