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

# モジュールレベルのロギング設定 (アプリケーション全体で設定推奨)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class SentimentWorker:
    """
    Symbl.ai のリアルタイムWebSocket APIを使用して、文字起こしされたテキストから感情を分析するワーカー。
    """
    SYMBL_API_DOMAIN = "api.symbl.ai"
    TOKEN_URL_TEMPLATE = f"https://{SYMBL_API_DOMAIN}/oauth2/token:generate"
    WS_ENDPOINT_TEMPLATE = f"wss://{SYMBL_API_DOMAIN}/v1/realtime/text/{{connection_id}}"

    def __init__(self,
                 on_emotion_callback: Callable[[Dict[str, Any]], Any],
                 symbl_app_id: Optional[str] = None,
                 symbl_app_secret: Optional[str] = None,
                 connection_id: Optional[str] = None,
                 language_code: str = "ja-JP"):
        """
        SentimentWorkerを初期化します。

        Args:
            on_emotion_callback (Callable): 感情分析結果が検出された際に呼び出されるコールバック関数。
                                           結果は辞書形式で渡されます。
            symbl_app_id (str, optional): Symbl.ai の App ID。
                                          指定がない場合、環境変数 SYMBL_APP_ID から読み込みます。
            symbl_app_secret (str, optional): Symbl.ai の App Secret。
                                              指定がない場合、環境変数 SYMBL_APP_SECRET から読み込みます。
            connection_id (str, optional): 既存のSymbl.ai接続ID。指定がなければ新しいIDを生成します。
            language_code (str): 分析対象の言語コード (例: "en-US", "ja-JP")。
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self._app_id = symbl_app_id or os.getenv("SYMBL_APP_ID")
        self._app_secret = symbl_app_secret or os.getenv("SYMBL_APP_SECRET")
        
        if not self._app_id or not self._app_secret:
            msg = "Symbl.ai App ID または App Secret が設定されていません。引数または環境変数で指定してください。"
            self.logger.error(msg)
            raise ValueError(msg)

        self._on_emotion_callback = on_emotion_callback
        self._connection_id = connection_id if connection_id else str(uuid.uuid4())
        self._language_code = language_code
        
        self._access_token: Optional[str] = None
        self._websocket: Optional[websockets.client.WebSocketClientProtocol] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._aiohttp_session: Optional[aiohttp.ClientSession] = None
        self._is_running = False # ワーカーの実行状態

        self.logger.info(f"SentimentWorker 初期化完了。Connection ID: {self._connection_id}, Language: {self._language_code}")

    async def _get_aiohttp_session(self) -> aiohttp.ClientSession:
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.ClientSession()
        return self._aiohttp_session

    async def _fetch_access_token(self) -> bool:
        payload = {
            "type": "application",
            "appId": self._app_id,
            "appSecret": self._app_secret
        }
        session = await self._get_aiohttp_session()
        try:
            self.logger.info("Symbl.ai アクセストークンを取得中...")
            async with session.post(self.TOKEN_URL_TEMPLATE, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(
                        f"Symbl.ai アクセストークン取得エラー: {response.status} - {error_text}"
                    )
                    return False
                
                data = await response.json()
                self._access_token = data.get("accessToken")
                expires_in = data.get("expiresIn")
                if self._access_token:
                    self.logger.info(f"Symbl.ai アクセストークン取得成功。有効期限: {expires_in}秒")
                    return True
                else:
                    self.logger.error(f"レスポンスにアクセストークンが含まれていません: {data}")
                    return False
        except aiohttp.ClientError as e:
            self.logger.error(f"Symbl.ai アクセストークン取得中にaiohttpクライアントエラー: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Symbl.ai アクセストークン取得中に予期せぬエラー: {e}")
            return False

    async def start(self) -> bool:
        """
        Symbl.ai とのWebSocket接続を開始し、感情分析セッションを開始します。
        成功した場合は True、失敗した場合は False を返します。
        """
        if self._is_running:
            self.logger.warning("SentimentWorkerは既に実行中です。")
            return True

        if not await self._fetch_access_token() or not self._access_token:
            self.logger.error("Symbl.ai アクセストークンの取得に失敗したため、開始できません。")
            return False

        websocket_url = f"{self.WS_ENDPOINT_TEMPLATE.format(connection_id=self._connection_id)}?accessToken={self._access_token}"
        
        try:
            self.logger.info(f"Symbl.ai WebSocket に接続中: {websocket_url.split('?')[0]}...")
            self._websocket = await websockets.connect(websocket_url)
            self.logger.info(f"Symbl.ai WebSocket 接続成功 (ID: {self._connection_id})")

            await self._send_start_request()
            self._listen_task = asyncio.create_task(self._listen_loop())
            self._is_running = True
            self.logger.info("SentimentWorker が正常に開始されました。")
            return True
        except websockets.exceptions.InvalidURI:
            self.logger.error(f"無効なWebSocket URIです: {websocket_url.split('?')[0]}")
            return False
        except websockets.exceptions.WebSocketException as e:
            self.logger.error(f"Symbl.ai WebSocket 接続失敗: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"SentimentWorker 開始中に予期せぬエラー: {e}")
            return False

    async def _send_start_request(self):
        start_request_payload = {
            "type": "start_request",
            "insightTypes": ["emotion"], # 感情分析にフォーカス
            "config": {
                "confidenceThreshold": 0.6, # 感情の信頼度閾値 (0.0 - 1.0)
                "languageCode": self._language_code,
                # "sentiment": {"enable": True} # "emotion" insightTypeを使用する場合、これは通常不要
            },
            # 必要であれば話者情報を追加
            # "speaker": { "userId": "user@example.com", "name": "User" }
        }
        if self._websocket:
            await self._websocket.send(json.dumps(start_request_payload))
            self.logger.info("start_request を Symbl.ai に送信しました。")
            self.logger.debug(f"start_requestペイロード: {json.dumps(start_request_payload)}")

    async def send_text_for_analysis(self, text_transcript: str):
        """
        文字起こしされたテキストをSymbl.aiに送信して感情分析を依頼します。
        """
        if not self._websocket or not self._websocket.open:
            self.logger.warning("WebSocketが接続されていないか閉じているため、テキストを送信できません。")
            return

        message_payload = {
            "type": "message",
            "message": {
                "type": "text",
                "text": text_transcript
            }
        }
        try:
            await self._websocket.send(json.dumps(message_payload))
            self.logger.debug(f"テキストをSymbl.aiに送信: '{text_transcript[:50]}...'")
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("テキスト送信中にWebSocket接続が閉じられました。")
            self._is_running = False # 停止状態に
        except Exception as e:
            self.logger.exception(f"Symbl.aiへのテキスト送信中にエラー: {e}")

    async def _listen_loop(self):
        self.logger.info("Symbl.ai からのメッセージ監視を開始します...")
        try:
            while self._websocket and self._websocket.open:
                message_str = await self._websocket.recv()
                self.logger.debug(f"Symbl.ai受信: {message_str[:250]}...") # 長すぎる場合は一部表示
                
                try:
                    message_data = json.loads(message_str)
                except json.JSONDecodeError:
                    self.logger.warning(f"Symbl.aiからのメッセージがJSON形式ではありません: {message_str[:250]}")
                    continue
                
                msg_type = message_data.get("type")

                if msg_type == "error":
                    self.logger.error(f"Symbl.ai APIエラー: {message_data.get('details', message_str)}")
                    # TODO: 特定のエラーコードに基づいて再接続や停止を検討

                elif msg_type == "insight_response":
                    for insight in message_data.get("insights", []):
                        if insight.get("type") == "emotion":
                            emotions_map = {
                                val["emotion"].lower(): val["score"] for val in insight.get("emotionValues", [])
                            } # 感情名を小文字に統一
                            dominant_emotion = insight.get("dominantEmotion", "").lower()
                            text_content = insight.get("text", "")
                            
                            formatted_result = {
                                "emotions": emotions_map,
                                "dominant_emotion": dominant_emotion,
                                "text_processed": text_content, # Symbl.aiが処理したテキスト
                                "original_text_length": len(text_content), # 参考情報
                                "timestamp": insight.get("timestamp", "") 
                            }
                            self.logger.info(f"感情分析結果: Dominant={dominant_emotion}, Scores={emotions_map}")
                            if self._on_emotion_callback:
                                try:
                                    # コールバックが非同期関数の場合: await self._on_emotion_callback(formatted_result)
                                    self._on_emotion_callback(formatted_result)
                                except Exception as e:
                                    self.logger.exception(f"on_emotion_callback 呼び出し中にエラー: {e}")
                # 他のメッセージタイプ (例: 'message_response' で文字起こし結果自体が返る場合など) も必要に応じて処理
                # elif msg_type == 'message' and message_data.get('message', {}).get('type') == 'recognition_result':
                #    self.logger.debug(f"Symbl.ai Text Recognition: {message_data}")


        except websockets.exceptions.ConnectionClosed as e:
            self.logger.info(f"Symbl.ai WebSocket接続が閉じられました (コード: {e.code}, 理由: {e.reason})")
        except asyncio.CancelledError:
            self.logger.info("Symbl.ai 監視ループがキャンセルされました。")
        except Exception as e:
            self.logger.exception(f"Symbl.ai 監視ループで予期せぬエラー: {e}")
        finally:
            self.logger.info("Symbl.ai 監視ループ終了。")
            self._is_running = False # 停止状態に
            # TODO: 自動再接続ロジックをここ、または上位の管理コンポーネントで検討

    async def stop(self):
        """
        SentimentWorkerを停止し、WebSocket接続をクリーンに閉じます。
        """
        self.logger.info("SentimentWorker を停止処理中...")
        self._is_running = False # 先にフラグを立てる

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                self.logger.info("Symbl.ai 監視タスクが正常にキャンセルされました。")
            except Exception as e:
                self.logger.exception(f"監視タスクのキャンセル待ち中にエラー: {e}")
        self._listen_task = None

        if self._websocket and self._websocket.open:
            try:
                # Symbl.ai は明示的な stop_request を要求しない場合がある (closeで十分)
                # もし必要なら送信: await self._websocket.send(json.dumps({"type": "stop_request"}))
                await self._websocket.close()
                self.logger.info("Symbl.ai WebSocket接続をクローズしました。")
            except websockets.exceptions.ConnectionClosed:
                self.logger.info("WebSocketは既にクローズされていました (stop時)。")
            except Exception as e:
                self.logger.exception(f"Symbl.ai WebSocketクローズ中にエラー: {e}")
        self._websocket = None
        
        if self._aiohttp_session and not self._aiohttp_session.closed:
            await self._aiohttp_session.close()
            self.logger.info("aiohttpセッションをクローズしました。")
        self._aiohttp_session = None
        
        self.logger.info("SentimentWorker が停止しました。")

# --- (オプション) 簡単なテスト用コード (通常は別ファイルで実行) ---
# async def sample_emotion_callback(emotion_data: Dict[str, Any]):
#     print(f"🎉 感情コールバック受信: {emotion_data}")

# async def main_test():
#     print("SentimentWorkerテスト開始...")
#     # 環境変数 SYMBL_APP_ID と SYMBL_APP_SECRET を設定してください
#     app_id = os.getenv("SYMBL_APP_ID")
#     app_secret = os.getenv("SYMBL_APP_SECRET")

#     if not app_id or not app_secret:
#         print("エラー: 環境変数 SYMBL_APP_ID と SYMBL_APP_SECRET が設定されていません。")
#         print("テストを実行する前にこれらの変数を設定してください。")
#         return

#     worker = SentimentWorker(
#         on_emotion_callback=sample_emotion_callback,
#         symbl_app_id=app_id,
#         symbl_app_secret=app_secret,
#         language_code="ja-JP" # または "en-US" など
#     )

#     if await worker.start():
#         print("SentimentWorkerが開始されました。テキストを送信してください。")
#         try:
#             # テスト用のテキストをいくつか送信
#             await worker.send_text_for_analysis("これは素晴らしい一日ですね！とても嬉しいです。")
#             await asyncio.sleep(2) # APIが処理する時間を少し待つ
#             await worker.send_text_for_analysis("なんてことだ、本当に悲しい出来事です。")
#             await asyncio.sleep(2)
#             await worker.send_text_for_analysis("これは普通の日です。特に何も感じません。")
#             await asyncio.sleep(5) # 結果が来るのを待つ
            
#             print("テスト送信完了。数秒後にワーカーを停止します。")
#             await asyncio.sleep(5)

#         except Exception as e:
#             print(f"テスト実行中にエラー: {e}")
#         finally:
#             print("SentimentWorkerを停止します。")
#             await worker.stop()
#     else:
#         print("SentimentWorkerの開始に失敗しました。")

# if __name__ == '__main__':
#     # Windowsで "RuntimeError: Event loop is closed" が出る場合対策
#     if os.name == 'nt':
#        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     try:
#         asyncio.run(main_test())
#     except KeyboardInterrupt:
#         print("テストが中断されました。")
#     except Exception as e:
#         print(f"メイン実行でエラー: {e}") 