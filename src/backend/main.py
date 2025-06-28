import sys
import os

# --- 🚀 Pythonのモジュール検索パスを最初に設定する最強のおまじない 🚀 ---
# このファイル(main.py)の場所を基準に、'src'ディレクトリの絶対パスを計算する！
# .../src/backend/main.py -> .../src/backend -> .../src
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# Pythonがモジュールを探す場所リストの先頭に'src'を追加！
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
# --- ここまでがおまじない！ ---

import asyncio
import json
import logging
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# パスの設定と環境変数の読み込み
# ------------------------------------------------------------------------------
# main.pyがどこから実行されてもいいように、プロジェクトのルートパスを取得してる
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Pythonがモジュールを探すパスに、プロジェクトルートを追加！
sys.path.append(ROOT_DIR)

# .envファイルを光の速さで読み込む！
# uvicornのリロード時とかでも、これが一番最初に実行されるから安心なんだ。
load_dotenv(os.path.join(ROOT_DIR, '.env'))

# Windowsでasyncioを使うときのおまじない。
# "RuntimeError: Event loop is closed"みたいなエラーを防いでくれる。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ------------------------------------------------------------------------------

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# --- パス設定 ---
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SRC_DIR, '..')

from backend.services.speech_processor import SpeechProcessor

# --- ロギング設定 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- FastAPIアプリの初期化 ---
app = FastAPI(
    title="Edge Presence X (EP-X) Backend",
    description="リアルタイム音声解析&AI評価API",
    version="1.0.0",
)

# --- CORSミドルウェアの設定 ---
# ローカル開発中のフロントエンドからの接続を許可する
origins = [
    "http://localhost",
    "http://localhost:5173",  # Viteのデフォルトポート
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "EP-X Backend is running! Access /docs for API documentation."}

# --- WebSocketエンドポイント ---
@app.websocket("/ws/v1/interview")
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket接続がきたよ！クライアントとご対面〜！")

    async def send_to_client(message: dict):
        try:
            await websocket.send_json(message)
            logger.debug(f"📤 クライアントへのメッセージ送信完了: type={message.get('type')}")
        except WebSocketDisconnect:
            logger.warning("❗️ クライアントが切断したため、メッセージは送信しませんでした。")
        except RuntimeError as e:
            # 「接続切れてるよ！」エラーをキャッチして、クラッシュを防ぐ
            if "after sending 'websocket.close'" in str(e):
                logger.warning(f"👻 クライアント接続が閉じた後に送信しようとしました: {e}")
            else:
                logger.error(f"💣 WebSocket送信中に予期せぬRuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"💣 クライアントへのメッセージ送信中に予期せぬエラー: {e}", exc_info=True)
    
    # send_to_clientを定義した後に、SpeechProcessorをインスタンス化する
    speech_processor = SpeechProcessor(websocket=websocket, send_to_client=send_to_client)

    try:
        while True:
            message = await websocket.receive()
            
            if message.get("type") == "websocket.disconnect":
                logger.info(f"👋 クライアントからの切断メッセージ受信 (code: {message.get('code', 'N/A')})。ループを抜けます。")
                break

            if 'text' in message:
                data = json.loads(message['text'])
                logger.info(f"クライアントからJSONメッセージ受信: {data}")
                
                # フロントエンドからのメッセージ形式を柔軟に処理する
                action = data.get("action")
                msg_type = data.get("type")

                if action == "start":
                    question = data.get("question", "自己紹介をお願いします。")
                    speech_processor.set_interview_question(question)
                    asyncio.create_task(speech_processor.start_transcription_and_evaluation())
                elif action == "stop" or msg_type == "end_session":
                    logger.info("クライアントからセッション終了リクエストを受信しました。")
                    asyncio.create_task(speech_processor.stop_transcription_and_evaluation())
            elif 'bytes' in message:
                audio_chunk = message['bytes']
                await speech_processor.process_audio_chunk(audio_chunk)
    except WebSocketDisconnect:
        logger.warning(f"👋 クライアント接続が予期せず切れました。")
    except Exception as e:
        logger.error(f"😱 WebSocketハンドラで予期せぬエラーが発生: {e}", exc_info=True)
    finally:
        logger.info("🔌 WebSocket接続ハンドラをクリーンアップします。")
        if speech_processor and speech_processor._is_running:
            logger.info("セッションがまだアクティブな可能性があるため、強制停止を試みます。")
            await speech_processor.stop_transcription_and_evaluation()

# --- 静的ファイルの配信設定 ---
DIST_DIR = os.path.join(_PROJECT_ROOT, 'dist')
ASSETS_DIR = os.path.join(DIST_DIR, 'assets')

if os.path.exists(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

    @app.get("/{full_path:path}")
    async def serve_vue_app(full_path: str):
        index_path = os.path.join(DIST_DIR, 'index.html')
        if not os.path.exists(index_path):
             return {"error": "index.html not found"}
        return FileResponse(index.html)
else:
    logger.warning(f"Frontend build directory not found at: {DIST_DIR}")

# --- サーバー起動 ---
def main():
    """ サーバーを起動するメイン関数 """
    # Cloud RunがPORT環境変数を設定するため、それに従う
    # ローカルで実行する場合は、デフォルトで8000番ポートを使用
    port = int(os.getenv("PORT", 8000))

    logger.info(f"🚀 サーバー起動！ http://localhost:{port} で待ってるよん！")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,  # ローカル開発用にホットリロードを有効にする
        log_level="info"
    )

if __name__ == "__main__":
    main()
