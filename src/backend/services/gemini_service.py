import os
import json
import logging
import vertexai
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase
import asyncio

# ロガー設定
logger = logging.getLogger(__name__)

# --- 定数 ---
# このファイル (gemini_service.py) のディレクトリ
_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
# プロジェクトルートの絶対パス (src/backend/services -> src/backend -> src -> project_root)
PROJECT_ROOT = os.path.abspath(os.path.join(_SERVICE_DIR, '..', '..', '..'))
GEMINI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "gemini_config.json")

PROMPT_TEMPLATE = """
# 指示: あなたは優秀なAI面接評価官です。以下の情報に基づき、候補者の回答をSTARメソッドの観点から厳格に評価し、指定されたJSON形式で結果のみを返却してください。

## 入力情報

### 面接の質問:
{interview_question}

### 候補者の回答（文字起こし）:
{transcript}

### （参考）音声分析データ:
- 平均ピッチ: {average_pitch} Hz
- ピッチ変動: {pitch_variation} Hz
- 主な感情: {dominant_emotion}
- 感情スコア: {emotion_score}

## 評価基準（STARメソッド）

1.  **Situation (状況):**
    -   回答者がどのようなビジネス状況にいたか、具体的かつ明確に説明できているか？
    -   背景、関与者、場所、時期が簡潔に述べられているか？
2.  **Task (課題):**
    -   回答者がその状況で果たすべきだった具体的な役割や目標、課題が明確に述べられているか？
    -   課題の重要性や困難さが客観的に理解できるか？
3.  **Action (行動):**
    -   課題解決のために、回答者自身が取った具体的な行動や思考プロセスが説明されているか？
    -   行動の主体が「私」であり、チームの行動と区別されているか？
    -   なぜその行動を選んだのか、理由が論理的か？
4.  **Result (結果):**
    -   行動の結果として得られた成果が、定量的（数値、パーセンテージなど）または定性的に具体的に示されているか？
    -   行動と結果の因果関係が明確か？
    -   結果から得た学びや、今後の業務にどう活かすかという視点が含まれているか？

## 出力形式（JSON）

以下のJSON形式に従い、評価結果のみを生成してください。説明や前置きは一切不要です。

```json
{{
  "star_evaluation": {{
    "situation": {{
      "score": <0-10の整数評価>,
      "feedback": "<評価理由と具体的な改善案>"
    }},
    "task": {{
      "score": <0-10の整数評価>,
      "feedback": "<評価理由と具体的な改善案>"
    }},
    "action": {{
      "score": <0-10の整数評価>,
      "feedback": "<評価理由と具体的な改善案>"
    }},
    "result": {{
      "score": <0-10の整数評価>,
      "feedback": "<評価理由と具体的な改善案>"
    }}
  }},
  "overall_score": <0-40の合計整数スコア>,
  "strengths": [
    "<強みや良かった点1>",
    "<強みや良かった点2>"
  ],
  "improvement_suggestions": [
    "<総合的な改善提案1>",
    "<総合的な改善提案2>"
  ]
}}
```
"""

# --- DeepEvalのカスタムメトリクス定義 ---
# STAR法の各項目を評価するためのGEvalメトリクスを定義するよん！
star_metrics = {
    "situation": GEval(
        name="Situation (状況説明)",
        criteria="""
        具体的で明確な状況説明ができているか評価してください。
        - 背景情報（いつ、どこで、誰が）は十分か？
        - 聞き手が状況を容易に想像できるか？
        - 簡潔に要点をまとめて話せているか？
        """,
        evaluation_steps=[
            "回答の中からSituation（状況）に関する部分を特定する。",
            "特定した部分が、評価基準を満たしているか確認する。",
            "0から10のスケールでスコアを付け、その理由を明確に記述する。"
        ]
    ),
    "task": GEval(
        name="Task (課題設定)",
        criteria="""
        取り組むべき課題や目標が明確に定義されているか評価してください。
        - 課題の重要性や困難さが伝わるか？
        - 自身の役割と責任範囲が明確か？
        - 目標は具体的で測定可能か？
        """,
        evaluation_steps=[
            "回答の中からTask（課題・目標）に関する部分を特定する。",
            "特定した部分が、評価基準を満たしているか確認する。",
            "0から10のスケールでスコアを付け、その理由を明確に記述する。"
        ]
    ),
    "action": GEval(
        name="Action (行動内容)",
        criteria="""
        課題解決のための具体的な行動が、主体性を持って語られているか評価してください。
        - 行動の主体は回答者自身（「私」）か？
        - 行動の意図や思考プロセスが明確か？
        - 困難な状況にどう立ち向かったかが分かるか？
        """,
         evaluation_steps=[
            "回答の中からAction（行動）に関する部分を特定する。",
            "特定した部分が、評価基準を満たしているか確認する。",
            "0から10のスケールでスコアを付け、その理由を明確に記述する。"
        ]
    ),
    "result": GEval(
        name="Result (成果)",
        criteria="""
        行動の結果として得られた成果が、具体的に示されているか評価してください。
        - 成果は定量的（数値、%）または定性的に明確か？
        - 行動と成果の因果関係は論理的か？
        - 結果からの学びや再現性について言及できているか？
        """,
         evaluation_steps=[
            "回答の中からResult（結果）に関する部分を特定する。",
            "特定した部分が、評価基準を満たしているか確認する。",
            "0から10のスケールでスコアを付け、その理由を明確に記述する。"
        ]
    )
}

# グローバル変数としてモデルを保持（アプリケーション起動時に一度だけ初期化）
gemini_model_instance = None
gemini_config = {}

def load_gemini_config_and_init():
    """
    設定ファイルからGeminiの情報を読み込み、モデルを初期化する。
    """
    global gemini_model_instance, gemini_config
    if gemini_model_instance:
        return

    try:
        if not os.path.exists(GEMINI_CONFIG_PATH):
            logger.error(f"Gemini設定ファイルが見つかりません: {GEMINI_CONFIG_PATH}")
            # .exampleファイルをコピーするなどのフォールバック処理も考えられる
            return

        with open(GEMINI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            gemini_config = json.load(f)
        logger.info(f"Gemini設定ファイルを読み込みました: {GEMINI_CONFIG_PATH}")

        # project_idが空やNoneでないことを確認
        project_id = gemini_config.get("project_id")
        if not project_id:
            logger.error("Gemini設定ファイルに 'project_id' が指定されていません。")
            return
            
        vertexai.init(project=project_id, location=gemini_config.get("location"))
        
        model_name = gemini_config.get("model_name", "gemini-1.5-flash-001")
        gemini_model_instance = GenerativeModel(model_name)
        logger.info(f"Geminiモデル ({model_name}) の準備ができました。")

    except FileNotFoundError:
        # このエラーは上のos.path.existsで捕捉されるはずだが、念のため
        logger.error(f"Gemini設定ファイルが見つかりません: {GEMINI_CONFIG_PATH}")
        gemini_config = {}
    except Exception as e:
        logger.error(f"Geminiの初期化中にエラーが発生しました: {e}", exc_info=True)
        gemini_model_instance = None

# アプリケーション起動時に一度呼び出す
load_gemini_config_and_init()

async def generate_structured_feedback(evaluation_context: dict) -> dict:
    """
    Gemini評価APIとDeepEvalメトリクスを非同期で呼び出し、構造化された評価結果(dict)を返す。
    """
    if not gemini_model_instance:
        logger.error("Geminiモデルが初期化されていないため、評価を実行できません。")
        return {
            "error": "Gemini model not initialized.",
            "raw_evaluation": "評価モデルが初期化されていません。",
            "score": 0
        }

    # --- evaluation_contextから必要な情報を取り出す ---
    # speech_processor._run_final_evaluation() で作成された辞書を想定
    transcript = evaluation_context.get('full_transcript', '')
    pitch_analysis = evaluation_context.get('pitch_analysis', {})
    emotion_analysis = evaluation_context.get('emotion_analysis', {})
    interview_question = evaluation_context.get('question', '指定なし')

    # 1. GeminiにJSON形式での全体評価をリクエスト
    # プロンプトに情報を埋め込む
    prompt = PROMPT_TEMPLATE.format(
        interview_question=interview_question,
        transcript=transcript,
        # speech_processor._summarize_pitch_data() のキー名と完全に一致させる！
        average_pitch=pitch_analysis.get("average_pitch", "N/A"),
        pitch_variation=pitch_analysis.get("pitch_variation", "N/A"),
        # ↓以下の項目は現状の実装では計算していないため、"N/A"とする
        speaking_rate="N/A",
        pause_frequency="N/A",
        average_pause_duration="N/A",
        # speech_processor._handle_emotion_data() のキー名と完全に一致させる！
        dominant_emotion=emotion_analysis.get("dominant_emotion", "N/A"),
        emotion_score=emotion_analysis.get("emotion_score", "N/A"),
        emotion_intensity=emotion_analysis.get("emotion_intensity", "N/A"),
        emotion_transition=emotion_analysis.get("emotion_transition", "N/A")
    )
    
    # --- モデルの設定を読み込む ---
    generation_config = gemini_config.get("generation_config", {
        "temperature": 0.7,
        "top_p": 1.0,
        "max_output_tokens": 2048,
    })
    
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }

    # 2. DeepEvalメトリクスで各項目を個別評価 (非同期で並列実行！)
    test_case = LLMTestCase(
        input=interview_question,
        actual_output=transcript,
        # TODO: 将来的には理想的な回答例(expected_output)も用意して、より高度な評価も可能！
    )
    
    evaluation_tasks = []
    for name, metric in star_metrics.items():
        # measureはブロッキングする可能性があるので、to_threadで別スレッドで実行するのが安全
        task = asyncio.to_thread(metric.measure, test_case)
        evaluation_tasks.append(task)
    
    results = await asyncio.gather(*evaluation_tasks)
    
    deepeval_scores = {}
    for i, name in enumerate(star_metrics.keys()):
        # measure() はメトリクスオブジェクトを返すので、.scoreでスコアを取得
        # スコアは0-1なので、10点満点に変換する
        score = round(results[i].score * 10)
        reasoning = results[i].reason
        deepeval_scores[name] = {"score": score, "reasoning": reasoning}
        logger.info(f"📊 DeepEval - {name}: score={score}/10, reasoning='{reasoning[:50]}...'")

    # 3. Geminiの評価とDeepEvalのスコアをマージする（将来的にはもっと賢くマージする）
    # 現状は、まずGeminiに全体評価のJSONを作らせてから、
    # DeepEvalで算出した客観的スコアで上書き・補強する戦略！

    try:
        logger.info("Geminiに評価をリクエストします...")
        response = await gemini_model_instance.generate_content_async(
            [prompt],
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        logger.info("Geminiからの評価レスポンスを受信しました。")
        
        # レスポンスからJSON文字列をパース
        response_text = response.text
        parsed_json = parse_gemini_response_data(response_text)
        
        # DeepEvalのスコアでJSONを更新！
        if parsed_json and "star_evaluation" in parsed_json:
            total_score = 0
            for name, data in deepeval_scores.items():
                if name in parsed_json["star_evaluation"]:
                    parsed_json["star_evaluation"][name]["score"] = data["score"]
                    # GeminiのfeedbackとDeepEvalのreasoningを組み合わせる
                    parsed_json["star_evaluation"][name]["feedback"] += f" (客観スコア理由: {data['reasoning']})"
                total_score += data["score"]
            
            parsed_json["overall_score"] = total_score
            logger.info("✅ DeepEvalのスコアでGeminiの評価結果を更新しました。")

        return parsed_json

    except Exception as e:
        logger.error(f"Gemini評価の生成または解析中にエラーが発生しました: {e}", exc_info=True)
        return {
            "error": str(e),
            "raw_evaluation": f"Gemini評価中にエラーが発生しました: {e}",
            "score": 0
        }

def parse_gemini_response_data(response_text: str) -> dict:
    """
    Geminiからの生のテキストレスポンスをパースして、
    フロントエンドで使いやすい辞書形式に変換する。
    """
    # ここでは単純な実装例として、テキスト全体と仮のスコアを返す。
    # TODO: 正規表現やキーワード検索を使って、レスポンスから各項目を抽出する
    # 例: 総合評価、STAR評価の各項目、改善点、アピールポイントなど
    
    score = 50  # 仮のスコア
    try:
        # "総合評価 (5段階)" の部分を探してスコアを抽出する
        # 例: "総合評価 (5段階)\n3. 良い" -> 3
        # 簡単な正規表現で実装してみる
        import re
        match = re.search(r"総合評価\s*\(5段階\)\s*[:\n\s]*(\d+)", response_text)
        if match:
            # 評価(1-5)を100点満点に変換 (1->20, 2->40, 3->60, 4->80, 5->100)
            score = int(match.group(1)) * 20
    except Exception:
        # パースに失敗してもエラーにしない
        pass

    return {
        "raw_evaluation": response_text,
        "score": score,
        # "star_situation": "...", # 将来的にパースして追加
        # "star_task": "...",
        # ...
    } 