# このモジュールは以下のライブラリに依存しています。
# プロジェクトの requirements.txt に \'websockets\' と \'aiohttp\' が含まれていることを確認してください。
# 例:
# websockets>=10.0
# aiohttp>=3.8.0

import asyncio
import json
import logging
import os
import uuid
import websockets
import aiohttp
from typing import Callable, Dict, Any, Optional
from google.cloud import language_v1
from google.cloud.language_v1.types import Document # type_ の代わりに Document.Type を使えるように
import sys # 環境変数のために追加

# --- Pythonのモジュール検索パスにsrcディレクトリを追加 ---
# この部分は speech_processor.py と同じ構造なので、必要に応じて調整してね！
# sentiment_worker.py のあるディレクトリ (src/backend/workers)
_CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
# src ディレクトリの絶対パス (src/backend/workers -> src/backend -> src)
_SRC_DIR = os.path.abspath(os.path.join(_CURRENT_FILE_DIR, '..', '..'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
# --- ここまで ---

# このモジュール用のロガーを取得
logger = logging.getLogger(__name__)

class SentimentWorker:
    """
    Google Cloud Natural Language API を使用してテキストの感情分析を行うワーカーだよん！
    """
    def __init__(self, on_emotion_callback: callable, language_code: str = "ja"):
        """
        SentimentWorker を初期化するよん！

        Args:
            on_emotion_callback (callable): 感情分析結果を処理するコールバック関数。
                                            {"score": float, "magnitude": float, "text_processed": str}
                                            みたいな辞書を期待してるっしょ！
            language_code (str, optional): 分析するテキストの言語コード。デフォルトは "ja" (日本語)。
        """
        self.on_emotion_callback = on_emotion_callback
        self.language_code = language_code
        self._is_running = False # APIリクエスト/レスポンス型なので、厳密な「実行中」状態は薄いかもだけど、一応ね！

        try:
            self.language_client = language_v1.LanguageServiceClient()
            logger.info("🔑 Google Cloud Natural Language API クライアントの初期化に成功しました。")
        except Exception as e:
            logger.exception("😱 Google Cloud Natural Language API クライアントの初期化中にエラーが発生しました。")
            self.language_client = None # 初期化失敗したらNoneにしとく

        logger.info("😊 SentimentWorker (Google Cloud NL API版) 初期化完了！✨")

    async def start(self) -> bool:
        """
        ワーカーを開始するよん！（Natural Language APIは常時接続不要なので、主に状態管理のため）
        """
        if not self.language_client:
            logger.error("😱 Natural Language APIクライアントが初期化されてないから、開始できないよ！")
            return False
        self._is_running = True
        logger.info("😊 SentimentWorker (Google Cloud NL API版) が開始されました。テキスト待機中...")
        return True

    async def stop(self):
        """
        ワーカーを停止するよん！（Natural Language APIは常時接続不要なので、主に状態管理のため）
        """
        self._is_running = False
        logger.info("😊 SentimentWorker (Google Cloud NL API版) が停止されました。")
        # Natural Language API クライアントは特にクローズ処理不要

    async def send_text_for_analysis(self, text_content: str):
        """
        指定されたテキストの感情分析を非同期で行い、結果をコールバックで通知するよん！

        Args:
            text_content (str): 分析するテキスト。
        """
        if not self._is_running:
            logger.warning("SentimentWorkerが実行されてないから、感情分析スキップするね。")
            return
        if not self.language_client:
            logger.error("Natural Language APIクライアントがないから分析できないっ🥺")
            return
        if not text_content or not text_content.strip():
            logger.debug("空のテキストが来たから、感情分析はスキップするね。")
            return

        logger.debug(f"📝 感情分析のためにテキスト受信: '{text_content[:100]}...'")

        try:
            # Natural Language API の呼び出しはブロッキングする可能性があるから、
            # asyncio.to_thread を使って別スレッドで実行するよん！
            response_sentiment = await asyncio.to_thread(
                self._analyze_sentiment_sync, text_content
            )

            if response_sentiment:
                score = response_sentiment.score
                magnitude = response_sentiment.magnitude
                logger.info(f"😊 感情分析結果: スコア={score:.2f}, 強さ={magnitude:.2f} (テキスト: '{text_content[:50]}...')")

                # コールバック関数を呼び出して結果を通知
                # SpeechProcessor側のコールバックの期待する形式に合わせる
                # ここではscore, magnitudeに加えて、処理したテキストも渡すことで、
                # コールバック側でどのテキストに対する分析結果か分かりやすくする
                emotion_data = {
                    "dominant_emotion": "N/A", # Natural Language API は直接 dominant_emotion を返さない
                    "emotions": { # Natural Language API の score/magnitude を emotions 辞書に格納
                        "score": score,
                        "magnitude": magnitude
                    },
                    "text_processed": text_content # 分析対象のテキスト
                }
                if self.on_emotion_callback:
                    # コールバックは非同期かもしれないし、そうでないかもしれない。
                    # とりあえずそのまま呼ぶけど、もしコールバックが非同期関数なら
                    # asyncio.create_task(self.on_emotion_callback(emotion_data)) みたいにするのもアリ
                    self.on_emotion_callback(emotion_data)
            else:
                logger.warning("感情分析APIから有効なレスポンスが得られませんでした。")

        except Exception as e:
            logger.exception(f"😱 Google Cloud Natural Language APIでの感情分析中にエラー: {e}")

    def _analyze_sentiment_sync(self, text_content: str) -> language_v1.types.Sentiment | None:
        """
        Google Cloud Natural Language API を使って同期的に感情分析を行う内部メソッド。
        asyncio.to_thread から呼び出されることを想定してるよ！
        """
        if not self.language_client:
            return None

        document = language_v1.types.Document(
            content=text_content,
            type_=language_v1.types.Document.Type.PLAIN_TEXT, # `type_` を使用
            language=self.language_code
        )
        # エンコーディングタイプを指定 (UTF8が推奨されてる)
        encoding_type = language_v1.EncodingType.UTF8

        try:
            response = self.language_client.analyze_sentiment(
                request={"document": document, "encoding_type": encoding_type}
            )
            return response.document_sentiment
        except Exception as e:
            logger.error(f"💥 感情分析APIリクエスト失敗 ({text_content[:30]}...): {e}")
            # ここでエラーを再raiseするか、Noneを返すかは設計次第
            # 今回はNoneを返して、呼び出し元でログ出力＆処理継続
            return None

# --- メイン処理のサンプル（テスト用） ---
async def main_test():
    # ロギング設定 (テスト用にDEBUGレベルまで表示)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されているか確認
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.warning("⚠️ 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されていません。")
        logger.warning("   Google Cloud Natural Language API の認証に失敗する可能性があります。")
        logger.warning("   設定例: export GOOGLE_APPLICATION_CREDENTIALS=\"/path/to/your/keyfile.json\"")
        # return # ここで終了させても良い

    def dummy_emotion_callback(data):
        logger.info(f"🤙 コールバック受信！ データ: {data}")

    worker = SentimentWorker(on_emotion_callback=dummy_emotion_callback, language_code="ja")

    if not await worker.start():
        logger.error("ワーカーの開始に失敗したから、テスト中断するね。")
        return

    test_texts = [
        "これは素晴らしい一日ですね！とても嬉しいです。",
        "この映画は本当に最悪だった。二度と見たくない。",
        "まあまあ普通かな。特に良くも悪くもない感じ。",
        "今日はちょっと疲れたけど、明日はきっといい日になるはず。",
        "このプロジェクトの成功を心から願っています！ワクワクが止まらない！",
        "なんてことだ！信じられない出来事が起きてしまった…",
        "", # 空のテキスト
        "      ", # 空白のみのテキスト
        "This is a test in English." # 英語のテキスト（language_code="ja"なのでどうなるか）
    ]

    for text in test_texts:
        await worker.send_text_for_analysis(text)
        await asyncio.sleep(1) # API呼び出しの間に少し待機（レートリミット対策にもなるかも）

    # 英語のテストもしてみる
    worker_en = SentimentWorker(on_emotion_callback=dummy_emotion_callback, language_code="en")
    await worker_en.start()
    await worker_en.send_text_for_analysis("I am so happy and excited about this!")
    await worker_en.send_text_for_analysis("This is a very sad and disappointing situation.")
    await worker_en.stop()


    await worker.stop()
    logger.info("テスト完了！おつかれさま～🎉")

if __name__ == "__main__":
    # poetry run python src/backend/workers/sentiment_worker.py などで実行
    # もしくは、PYTHONPATH=. python src/backend/workers/sentiment_worker.py
    # `PYTHONPATH=.` は、`from backend.workers...` のようなインポートを解決するため
    # src ディレクトリをPYTHONPATHに追加する処理が冒頭にあるので、
    # `python src/backend/workers/sentiment_worker.py` で直接実行できるはず
    asyncio.run(main_test()) 