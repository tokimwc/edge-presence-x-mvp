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
    Symbl.aiのリアルタイムWebSocket APIを使用して、音声ストリームから感情分析を行うワーカー。
    """
    def __init__(self, on_emotion_callback: Callable, access_token: str, connection_id: str):
        """
        ワーカーを初期化します。

        Args:
            on_emotion_callback (Callable): 感情分析データを受信したときに呼び出されるコールバック関数。
            access_token (str): Symbl.aiの認証用アクセストークン。
            connection_id (str): Symbl.aiのWebSocket接続のためのユニークなID。
        """
        self.on_emotion_callback = on_emotion_callback
        self.access_token = access_token
        self.connection_id = connection_id
        
        # wss://api.symbl.ai/v1/streaming/{connectionId}?access_token={accessToken}
        self.symbl_ws_url = f"wss://api.symbl.ai/v1/streaming/{self.connection_id}?access_token={self.access_token}"
        
        self._is_running = False
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._processing_task: Optional[asyncio.Task] = None

        logger.info("😊 Symbl.ai SentimentWorker 初期化完了！✨")

    async def start(self):
        """ワーカーを起動し、Symbl.aiとのWebSocket接続を確立します。"""
        if self._is_running:
            logger.warning("Symbl.ai SentimentWorkerはすでに実行中です。")
            return

        logger.info(f"Symbl.aiに接続します: {self.symbl_ws_url.split('?')[0]}") # URLからトークンを除いてログ出力
        self._is_running = True
        
        try:
            # WebSocketに接続
            self._websocket = await websockets.connect(self.symbl_ws_url)
            logger.info("✅ Symbl.aiとのWebSocket接続が確立されました。")
            
            # メッセージ受信ループを開始
            self._processing_task = asyncio.create_task(self._receive_loop())

        except websockets.exceptions.InvalidURI as e:
            logger.error(f"😱 無効なWebSocket URIです: {e}")
            self._is_running = False
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"😱 WebSocket接続に失敗しました: {e}")
            self._is_running = False
        except Exception as e:
            logger.exception("😱 WebSocket接続中に予期せぬエラーが発生しました。")
            self._is_running = False

    async def _receive_loop(self):
        """Symbl.aiからのメッセージを継続的に受信し、処理します。"""
        logger.info("Symbl.aiからのメッセージ受信待機中...")
        while self._is_running:
            try:
                message = await self._websocket.recv()
                data = json.loads(message)

                # 感情分析の結果をハンドリング
                if data.get('type') == 'insight_response' and data.get('insights'):
                    for insight in data['insights']:
                        if insight.get('type') == 'emotion':
                            # コールバック関数を呼び出して結果をSpeechProcessorに渡す
                            self.on_emotion_callback(insight)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("👋 Symbl.aiとのWebSocket接続が閉じられました。")
                break
            except json.JSONDecodeError:
                logger.warning(f"🤔 Symbl.aiから不正なJSONメッセージを受信しました: {message}")
                continue
            except Exception as e:
                logger.exception("😱 メッセージ受信ループでエラーが発生しました。")
                break
        
        logger.info("メッセージ受信ループが終了しました。")
        self._is_running = False

    async def send_audio(self, audio_chunk: bytes):
        """
        音声データをSymbl.aiに送信します。
        """
        if not self._is_running or not self._websocket or not self._websocket.open:
            logger.warning("WebSocketが接続されていないため、音声を送信できません。")
            return
            
        try:
            await self._websocket.send(audio_chunk)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("音声を送信しようとしましたが、WebSocket接続が閉じていました。")
            await self.stop() # 接続が切れたらワーカーを停止

    async def stop(self):
        """ワーカーを安全に停止します。"""
        if not self._is_running:
            return
            
        logger.info("😊 Symbl.ai SentimentWorkerを停止します...")
        self._is_running = False

        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass # キャンセルは想定内

        if self._websocket and self._websocket.open:
            logger.info("WebSocket接続を閉じています...")
            await self._websocket.close()
            logger.info("WebSocket接続を閉じました。")
            
        logger.info("😊 Symbl.ai SentimentWorkerが安全に停止しました。")

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

    worker = SentimentWorker(on_emotion_callback=dummy_emotion_callback, access_token="your_access_token", connection_id="your_connection_id")

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