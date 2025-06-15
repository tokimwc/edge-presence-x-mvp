import asyncio
import json
import logging
import os
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# --- パス設定 ---
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_BACKEND_DIR, '..')
_PROJECT_ROOT = os.path.join(_SRC_DIR, '..')

if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from backend.services.speech_processor import SpeechProcessor

# --- ロギング設定 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- FastAPIアプリの初期化 ---
app = FastAPI()

# --- WebSocketエンドポイント ---
@app.websocket("/ws/v1/interview")
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket接続がきたよ！クライアントとご対面〜！")
    speech_processor = SpeechProcessor()

    async def send_to_client(message: dict):
        try:
            await websocket.send_json(message)
            logger.info(f"📤 クライアントへのメッセージ送信完了: type={message.get('type')}")
        except WebSocketDisconnect:
            logger.warning("❗️ クライアントへの送信中にWebSocketが切断されました。")
        except Exception as e:
            logger.error(f"💣 クライアントへのメッセージ送信中に予期せぬエラー: {e}", exc_info=True)
    
    speech_processor.set_send_to_client_callback(send_to_client)

    try:
        while True:
            message = await websocket.receive()
            
            if message.get("type") == "websocket.disconnect":
                logger.info(f"👋 クライアントからの切断メッセージ受信 (code: {message.get('code', 'N/A')})。ループを抜けます。")
                break

            if 'text' in message:
                data = json.loads(message['text'])
                logger.info(f"クライアントからJSONメッセージ受信: {data}")
                action = data.get("action")
                if action == "start":
                    question = data.get("question", "自己紹介をお願いします。")
                    speech_processor.set_interview_question(question)
                    asyncio.create_task(speech_processor.start_transcription_and_evaluation())
                elif action == "stop":
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
    logger.info("🚀 サーバー起動！ http://localhost:8000 で待ってるよん！")
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
