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
import time # タイムスタンプのために追加

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
    内部にキューを持っていて、非同期でテキストを処理するよ！
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
        self._is_running = False
        self._text_queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None

        try:
            self.language_client = language_v1.LanguageServiceClient()
            logger.info("🔑 Google Cloud Natural Language API クライアントの初期化に成功しました。")
        except Exception as e:
            logger.exception("😱 Google Cloud Natural Language API クライアントの初期化中にエラーが発生しました。")
            self.language_client = None

        logger.info("😊 SentimentWorker (Google Cloud NL API版) 初期化完了！✨")

    async def add_text(self, text: str, timestamp: Optional[float] = None):
        """
        外部（SpeechProcessor）から感情分析したいテキストを受け取って、
        キューに追加するメソッドだよん！
        タイムスタンプも一緒に受け取る！
        """
        if self._is_running:
            await self._text_queue.put({"text": text, "timestamp": timestamp or time.time()})
        else:
            logger.warning("SentimentWorkerが停止中にテキストが追加されようとしました。スキップします。")

    async def _process_queue(self):
        """
        キューを監視して、テキストが来たら分析処理を叩くメインループ！
        """
        while self._is_running or not self._text_queue.empty():
            try:
                item = await asyncio.wait_for(self._text_queue.get(), timeout=1.0)
                if item is None:  # 終了の合図
                    break

                text = item.get("text")
                timestamp = item.get("timestamp")

                if not self.language_client or not text:
                    logger.error("Natural Language APIクライアントがないかテキストが空なので分析できないっ🥺")
                    continue
                
                logger.debug(f"📝 感情分析のためにテキスト受信: '{text[:100]}...'")

                # Natural Language API の呼び出しはブロッキングするので、別スレッドで実行
                response_sentiment = await asyncio.to_thread(
                    self._analyze_sentiment_sync, text
                )

                if response_sentiment:
                    score = response_sentiment.score
                    magnitude = response_sentiment.magnitude
                    emotion_data = {
                        "emotions": {"score": score, "magnitude": magnitude},
                        "text_processed": text,
                        "timestamp": timestamp, # SpeechProcessorから受け取ったタイムスタンプをそのまま使う
                    }
                    if self.on_emotion_callback:
                        # create_taskはコールバックが非同期(async def)の場合に使う。
                        # 今回のコールバックは同期なので、直接呼び出すのが正解！
                        self.on_emotion_callback(emotion_data)
                else:
                    logger.warning(f"感情分析APIから有効なレスポンスが得られませんでした: '{text[:50]}...'")

            except asyncio.TimeoutError:
                # タイムアウトは問題なし！ループを継続して、_is_running を再チェック
                continue
            except Exception as e:
                logger.exception(f"😱 感情分析処理中にエラーが発生: {e}")
        
        logger.info("😊 SentimentWorkerの処理ループが正常に終了しました。")

    def _analyze_sentiment_sync(self, text_content: str) -> Optional[language_v1.types.Sentiment]:
        """
        Google Cloud Natural Language API を使って同期的に感情分析を行う内部メソッド。
        """
        if not self.language_client or not text_content.strip():
            return None
            
        document = language_v1.types.Document(
            content=text_content,
            type_=language_v1.types.Document.Type.PLAIN_TEXT,
            language=self.language_code
        )
        encoding_type = language_v1.EncodingType.UTF8
        try:
            response = self.language_client.analyze_sentiment(
                request={"document": document, "encoding_type": encoding_type}
            )
            return response.document_sentiment
        except Exception as e:
            logger.error(f"💥 感情分析APIリクエスト失敗 ({text_content[:30]}...): {e}")
            return None

    async def start(self):
        """ワーカーを起動するよん！"""
        if self._is_running:
            logger.warning("SentimentWorkerはすでに実行中です。")
            return
        if not self.language_client:
            logger.error("😱 Natural Language APIクライアントが初期化されてないから、開始できないよ！")
            return

        logger.info("😊 SentimentWorkerを起動します...")
        self._is_running = True
        self._processing_task = asyncio.create_task(self._process_queue())
        logger.info("😊 SentimentWorker (Google Cloud NL API版) が開始されました。テキスト待機中...")

    async def stop(self):
        """ワーカーを停止するよん！"""
        if not self._is_running:
            return
        logger.info("😊 SentimentWorkerを停止します...")
        self._is_running = False
        
        # 終了の目印としてNoneをキューに入れる
        try:
            await asyncio.wait_for(self._text_queue.put(None), timeout=1.0)
        except asyncio.TimeoutError:
            logger.warning("SentimentWorkerのキューに終了マーカーを配置中にタイムアウトしました。")

        if self._processing_task:
            try:
                # タスクの完了を待つ
                await asyncio.wait_for(self._processing_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("SentimentWorkerの処理タスクの停止がタイムアウトしました。キャンセルします。")
                self._processing_task.cancel()
            except Exception as e:
                logger.error(f"SentimentWorkerの停止中にエラーが発生: {e}")

        logger.info("😊 SentimentWorkerが安全に停止しました。")

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
        await worker.add_text(text)
        await asyncio.sleep(1) # API呼び出しの間に少し待機（レートリミット対策にもなるかも）

    # 英語のテストもしてみる
    worker_en = SentimentWorker(on_emotion_callback=dummy_emotion_callback, language_code="en")
    await worker_en.start()
    await worker_en.add_text("I am so happy and excited about this!")
    await worker_en.add_text("This is a very sad and disappointing situation.")
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