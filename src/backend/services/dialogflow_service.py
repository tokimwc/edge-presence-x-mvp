# dialogflow_service.py

import os
import uuid
import google.auth
from google.cloud import dialogflow_v2 as dialogflow
from google.api_core.client_options import ClientOptions
from dotenv import load_dotenv
import logging
import sys
import asyncio
from ..shared_config import DIALOGFLOW_LOCATION

# .envファイルから環境変数を読み込む
load_dotenv()

logger = logging.getLogger(__name__)

# --- 環境変数の設定（GCPプロジェクトID） ---
# 標準的な 'GOOGLE_CLOUD_PROJECT' を使うように変更
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
if not PROJECT_ID:
    # GCP環境で実行されている場合、認証情報からプロジェクトIDを自動取得
    try:
        _, PROJECT_ID = google.auth.default()
        logger.info(f"環境変数が見つからないため、GCPのデフォルトプロジェクトID ({PROJECT_ID}) を使用します。")
    except google.auth.exceptions.DefaultCredentialsError:
        logger.error("GCPのデフォルト認証情報が見つかりませんでした。プロジェクトIDが不明です。")
        PROJECT_ID = None  # フォールバック

async def analyze_sentiment(session_id: str, text: str, language_code: str = 'ja'):
    """
    Dialogflow ESを使用して、指定されたテキストの感情分析を非同期で実行します。

    Args:
        session_id (str): 会話を識別するためのユニークなセッションID。
        text (str): 分析対象のテキスト。
        language_code (str, optional): テキストの言語コード。デフォルトは 'ja'。

    Returns:
        dict または None: 感情のスコアと強度を含む辞書、またはエラー時にNone。
    """
    if not PROJECT_ID:
        logger.error("プロジェクトIDが不明なため、感情分析を実行できません。")
        return None
    if not text or not text.strip():
        logger.debug("テキストが空のため、感情分析をスキップします。")
        return None

    try:
        # --- リージョンに基づいてクライアントオプションとセッションパスを設定 ---
        client_options_instance = None
        session_path = ""
        if DIALOGFLOW_LOCATION:
            # ★★★★★ ここからがマジで超重要！ ★★★★★
            # 1. リージョンを指定するための設定を作成
            api_endpoint = f"{DIALOGFLOW_LOCATION}-dialogflow.googleapis.com"
            client_options_instance = ClientOptions(api_endpoint=api_endpoint)
            logger.info(f"Dialogflowのリージョンエンドポイントを明示的に設定します: {api_endpoint}")
            
            # 2. リージョン設定を使ってクライアントを初期化
            session_client = dialogflow.SessionsAsyncClient(client_options=client_options_instance)

            # 3. セッションパスを【手動で】構築する (v2ライブラリのヘルパーはlocation非対応のため)
            session_path = f"projects/{PROJECT_ID}/locations/{DIALOGFLOW_LOCATION}/agent/sessions/{session_id}"
            # ★★★★★ ここまでがマジで超重要！ ★★★★★
        else:
            # グローバルエンドポイント用のフォールバック
            session_client = dialogflow.SessionsAsyncClient()
            session_path = session_client.session_path(project=PROJECT_ID, session=session_id)
            logger.info("Dialogflowのグローバルエンドポイントを使用します。")
        
        logger.debug(f"Dialogflowセッションパス: {session_path}")

        text_input = dialogflow.TextInput(text=text, language_code=language_code)
        query_input = dialogflow.QueryInput(text=text_input)

        sentiment_config = dialogflow.SentimentAnalysisRequestConfig(
            analyze_query_text_sentiment=True
        )
        query_params = dialogflow.QueryParameters(
            sentiment_analysis_request_config=sentiment_config
        )

        # --- detect_intent APIを非同期で呼び出し ---
        logger.info(f"'{text}' の感情分析をリクエスト中...")
        response = await session_client.detect_intent(
            request={
                "session": session_path,
                "query_input": query_input,
                "query_params": query_params,
            }
        )
        logger.info("感情分析レスポンスを受信しました。")

        sentiment_result = response.query_result.sentiment_analysis_result.query_text_sentiment
        score = sentiment_result.score
        magnitude = sentiment_result.magnitude

        logger.info(f"感情分析結果: スコア={score:.2f}, 強度={magnitude:.2f}")

        return {"score": score, "magnitude": magnitude}

    except Exception as e:
        logger.exception(f"Dialogflowでの感情分析中にエラーが発生しました: {e}")
        return None

# --- テストコードも非同期に対応 ---
async def main_test():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    test_session_id = f"test-session-{uuid.uuid4()}"
    test_texts = [
        "この新しい機能、本当に最高！開発チームに感謝しかないよ！",
        "今日のプレゼンテーションは、正直言って期待外れだったな。",
        "まあ、悪くはないんじゃない？普通だと思うけど。",
        "なんてことだ…信じられないくらい悲しい知らせだ。",
    ]

    if not PROJECT_ID:
        logger.error("テスト実行には、環境変数 'GOOGLE_CLOUD_PROJECT' の設定が必要です。")
    else:
        for t in test_texts:
            result = await analyze_sentiment(test_session_id, t)
            if result:
                print(f"テキスト: '{t}'")
                print(f"  => 感情スコア: {result['score']:.2f}, 感情の強度: {result['magnitude']:.2f}\\n")
            else:
                print(f"テキスト: '{t}' の分析に失敗しました。\\n")

if __name__ == '__main__':
    # このテストを実行するには、事前に `gcloud auth application-default login` を実行し、
    # 環境変数 `GOOGLE_CLOUD_PROJECT` にあなたのGCPプロジェクトIDを設定してください。
    asyncio.run(main_test()) 