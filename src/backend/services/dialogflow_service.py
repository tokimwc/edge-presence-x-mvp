# dialogflow_service.py

from google.cloud import dialogflow_v2 as dialogflow
import os
import logging

# ロガーを設定
logger = logging.getLogger(__name__)

# --- 環境変数の設定（GCPプロジェクトID） ---
# Cloud Runで設定された環境変数から取得することを推奨
PROJECT_ID = os.environ.get('VERTEX_AI_PROJECT')
if not PROJECT_ID:
    # ローカルでの開発用に、フォールバックの値やエラーハンドリングをしてもOK
    logger.warning("環境変数 'VERTEX_AI_PROJECT' が設定されていません。")
    # 例: raise ValueError("GCPプロジェクトIDが設定されていません。")
    # ここでは、とりあえずNoneのまま進める

def analyze_sentiment(session_id: str, text: str, language_code: str = 'ja'):
    """
    Dialogflow CX（またはES）を使用して、指定されたテキストの感情分析を実行します。

    Args:
        session_id (str): 会話を識別するためのユニークなセッションID。
        text (str): 分析対象のテキスト。
        language_code (str, optional): テキストの言語コード。デフォルトは 'ja'。

    Returns:
        dict: 感情のスコアと強度を含む辞書。
              例: {"score": 0.8, "magnitude": 0.8}
              エラーが発生した場合は、Noneを返します。
    """
    if not PROJECT_ID:
        logger.error("プロジェクトIDが不明なため、感情分析を実行できません。")
        return None
    if not text:
        logger.debug("テキストが空のため、感情分析をスキップします。")
        return None

    try:
        # --- セッションクライアントの初期化 ---
        # このクライアントは、可能であれば再利用するのがベストプラクティス
        session_client = dialogflow.SessionsClient()

        # --- セッションパスの構築 ---
        # Dialogflowエージェントのロケーションに基づいてパスを構築する必要がある場合も
        # 例: projects/project-id/locations/global/agent/sessions/session-id
        session = session_client.session_path(PROJECT_ID, session_id)
        logger.debug(f"Dialogflowセッションパス: {session}")


        # --- クエリ入力の作成 ---
        text_input = dialogflow.TextInput(text=text, language_code=language_code)
        query_input = dialogflow.QueryInput(text=text_input)

        # --- 感情分析リクエストの設定 ---
        # 感情分析を有効にするためのパラメータ
        sentiment_config = dialogflow.SentimentAnalysisRequestConfig(
            analyze_query_text_sentiment=True
        )
        query_params = dialogflow.QueryParameters(
            sentiment_analysis_request_config=sentiment_config
        )

        # --- detect_intent APIの呼び出し ---
        logger.info(f"'{text}' の感情分析をリクエスト中...")
        response = session_client.detect_intent(
            request={
                "session": session,
                "query_input": query_input,
                "query_params": query_params,
            }
        )
        logger.info("感情分析レスポンスを受信しました。")

        # --- 結果の抽出 ---
        sentiment_result = response.query_result.sentiment_analysis_result.query_text_sentiment
        score = sentiment_result.score
        magnitude = sentiment_result.magnitude

        logger.info(f"感情分析結果: スコア={score:.2f}, 強度={magnitude:.2f}")

        return {"score": score, "magnitude": magnitude}

    except Exception as e:
        logger.exception(f"Dialogflowでの感情分析中にエラーが発生しました: {e}")
        return None

# --- このファイルを直接実行した場合のテストコード ---
if __name__ == '__main__':
    # このテストを実行するには、事前に `gcloud auth application-default login` を実行し、
    # 環境変数 `VERTEX_AI_PROJECT` にあなたのGCPプロジェクトIDを設定してください。
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    test_session_id = "test-session-12345"
    test_texts = [
        "この新しい機能、本当に最高！開発チームに感謝しかないよ！",
        "今日のプレゼンテーションは、正直言って期待外れだったな。",
        "まあ、悪くはないんじゃない？普通だと思うけど。",
        "なんてことだ…信じられないくらい悲しい知らせだ。",
    ]

    if not PROJECT_ID:
        logger.error("テスト実行には、環境変数 'VERTEX_AI_PROJECT' の設定が必要です。")
        logger.error("例: export VERTEX_AI_PROJECT='your-gcp-project-id'")
    else:
        for t in test_texts:
            result = analyze_sentiment(test_session_id, t)
            if result:
                print(f"テキスト: '{t}'")
                print(f"  => 感情スコア: {result['score']:.2f}, 感情の強度: {result['magnitude']:.2f}\n")
            else:
                print(f"テキスト: '{t}' の分析に失敗しました。\n") 