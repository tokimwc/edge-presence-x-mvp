import os
import json
import logging
import re
import vertexai
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold, Part
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.models.base_model import DeepEvalBaseLLM
import asyncio
from tenacity import retry, stop_after_attempt, wait_random_exponential
from google.api_core import exceptions as google_exceptions

# ロガー設定
logger = logging.getLogger(__name__)

# --- deepeval用のVertexAIラッパークラス ---
class VertexAI(DeepEvalBaseLLM):
    """
    deepevalでVertex AI Geminiモデルを使うためのラッパークラスだよ。
    DeepEvalBaseLLMを継承して、非同期処理とか必要なメソッドを実装してる。
    """

    def __init__(self, project: str, location: str, model_name: str = "gemini-1.5-pro-001"):
        """
        コンストラクタ。引数をちゃんと受け取れるようにしたよ！
        モデルの初期化はload_modelでやるのがお作法だから、ここでは保持するだけ。
        """
        self.project = project
        self.location = location
        self.model_name = model_name
        # modelインスタンスはload_modelで初期化するから、ここではNoneでOK！
        self.model = None

    def load_model(self):
        """
        ‼️‼️【重要】ここが追加したメソッド！‼️‼️
        DeepEvalBaseLLMのお作法に従って、load_modelを実装するよ。
        ここでVertex AIの初期化とモデルのロードを行うのがイケてるやり方！
        """
        if self.model is None:
            try:
                # GCPプロジェクトの初期化（複数回呼ばれても大丈夫なように）
                vertexai.init(project=self.project, location=self.location)
                # 使用する生成モデルを指定してインスタンス化
                self.model = GenerativeModel(self.model_name)
                logger.info(f"✅ VertexAIラッパー内でGeminiモデル ({self.model_name}) のロード完了！")
            except Exception as e:
                logger.error(f"😱 VertexAIラッパーのload_modelでエラー発生: {e}")
                # エラーが発生したらNoneのままにして、後続処理で判定できるようにする
                self.model = None
        return self.model

    def generate(self, prompt: str) -> str:
        """
        同期処理でプロンプトからテキストを生成するよ。
        DeepEvalBaseLLMの抽象メソッドだから実装が必須！
        今回はa_generateを使うから、ここはシンプルにNotImplementedErrorを発生させる。
        """
        raise NotImplementedError("This model is designed for asynchronous generation.")

    async def a_generate(self, prompt: str) -> str:
        """
        非同期処理でプロンプトからテキストを生成するメソッド。
        generate_content_asyncを使って、I/Oバウンドな処理をブロックしないようにしてる。
        """
        # モデルがロードされてるかチェック！されてなかったらロードする
        if self.model is None:
            self.load_model()
        
        # それでもダメなら、エラーメッセージを返す
        if self.model is None:
            return "Error: Model could not be loaded."

        logger.debug(f"VertexAI a_generateに渡されたプロンプト: {prompt[:100]}...") # 長いプロンプトを考慮
        try:
            # GeminiのGenerationConfigとSafetySettingsを取得
            generation_config = gemini_config.get("generation_config", {})
            safety_settings = gemini_config.get("safety_settings", {})

            # 非同期でコンテンツ生成
            response = await self.model.generate_content_async(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )

            return response.text
        except Exception as e:
            logger.error(f"VertexAI a_generateでエラー: {e}")
            return f"Error: {e}"

    def get_model_name(self):
        """
        モデル名を返すよ。deepevalが内部で使うことがあるんだ。
        """
        return self.model_name

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
# アプリケーション起動時にモデルを読み込んでから動的に生成するため、
# ここでは空の辞書として初期化しておく。
# star_metrics = {} # <- GeminiServiceクラスに移動

# グローバル変数としてモデルを保持（アプリケーション起動時に一度だけ初期化）
# gemini_model_instance = None # <- GeminiServiceクラスに移動
# deepeval_model_instance = None # <- GeminiServiceクラスに移動
# gemini_config = {} # <- GeminiServiceクラスに移動

class GeminiService:
    """
    Geminiモデルとのやり取りを全部担当するサービスクラス。
    設定の読み込み、モデルの初期化、フィードバック生成、評価まで、
    このクラス一つで完結するようになってるよ！
    """
    def __init__(self):
        """
        コンストラクタ。Vertex AIの初期化とモデルのロードをここで行う。
        """
        self.gemini_model_instance = None
        self.deepeval_model_instance = None
        self.gemini_config = {}
        self.star_metrics = {}
        try:
            if os.path.exists(GEMINI_CONFIG_PATH):
                with open(GEMINI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self.gemini_config = json.load(f)
                logger.info(f"Gemini設定ファイルを読み込みました: {GEMINI_CONFIG_PATH}")

            # 環境変数または設定ファイルから値を取得
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or self.gemini_config.get("project_id")
            location = self.gemini_config.get("location", "us-central1") # 推奨リージョン
            model_name = self.gemini_config.get("model_name", "gemini-1.5-flash-002") # 公式モデル名

            if not project_id:
                raise ValueError("GCPプロジェクトIDが設定されていません。")

            # Vertex AIを正しく初期化
            vertexai.init(project=project_id, location=location)
            
            # 生成モデルをインスタンス化
            self.gemini_model_instance = GenerativeModel(model_name)
            logger.info(f"✅ Vertex AI Geminiモデル ({model_name} in {location}) の準備ができました。")

            # DeepEval関連の初期化
            self.deepeval_model_instance = VertexAI(project=project_id, location=location, model_name=model_name)
            self._initialize_deepeval_metrics()

        except Exception as e:
            logger.error(f"❌ Vertex AI Gemini の初期化中に致命的なエラー: {e}", exc_info=True)
            # アプリケーションが起動しないように例外を再送出
            raise

    def _initialize_deepeval_metrics(self):
        """
        DeepEvalの評価メトリクスを初期化する。
        モデルの準備ができた後に呼ばれる必要があるから、別のメソッドに分けたよ。
        """
        if not self.deepeval_model_instance:
            logger.error("DeepEvalモデルインスタンスが初期化されてないため、メトリクスを作成できません。")
            return
            
        common_params = {
            "evaluation_params": [LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            "model": self.deepeval_model_instance
        }

        self.star_metrics = {
            "situation": GEval(
                name="Situation (状況説明)",
                criteria="具体的で明確な状況説明ができているか評価してください...",
                evaluation_steps=["..."],
                **common_params
            ),
            "task": GEval(
                name="Task (課題設定)",
                criteria="取り組むべき課題や目標が明確に定義されているか評価してください...",
                evaluation_steps=["..."],
                 **common_params
            ),
            "action": GEval(
                name="Action (行動)",
                criteria="具体的な行動や思考プロセスが説明されているか評価してください...",
                evaluation_steps=["..."],
                **common_params
            ),
            "result": GEval(
                name="Result (結果)",
                criteria="行動の結果として得られた成果が具体的に示されているか評価してください...",
                evaluation_steps=["..."],
                **common_params
            ),
        }
        logger.info("✅ DeepEvalのSTAR評価メトリクスが初期化されました。")

    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
    async def generate_structured_feedback(self, evaluation_context: dict) -> dict:
        """
        【再修正】Vertex AI Gemini API を使ってフィードバックを生成する。
        """
        if not self.gemini_model_instance:
            logger.error("Vertex AIモデルが初期化されていません。フィードバックを生成できません。")
            return {"error": "Vertex AI model not initialized"}

        prompt = PROMPT_TEMPLATE.format(**evaluation_context)
        logger.info("Vertex AI Gemini APIにフィードバック生成をリクエストします。")
        
        try:
            # 正しいVertex AI SDKの非同期呼び出し
            response = await self.gemini_model_instance.generate_content_async(prompt)
            
            logger.info("Vertex AI Gemini APIからのレスポンスを受信しました。")
            
            parsed_data = self._parse_gemini_response_data(response.text)
            return parsed_data

        except Exception as e:
            logger.error(f"Vertex AI Gemini APIでのフィードバック生成中にエラー: {e}", exc_info=True)
            return {"error": f"An unexpected error occurred with Vertex AI Gemini API: {e}"}

    async def _evaluate_with_deepeval(self, context: dict, llm_output: dict) -> dict:
        """
        DeepEvalを使って、生成されたフィードバックの品質をメタ評価する内部メソッド。
        """
        if not self.star_metrics:
            logger.warning("DeepEvalメトリクスが利用できません。メタ評価をスキップします。")
            return {}
            
        # 評価用のテストケースを作成
        test_case = LLMTestCase(
            input=context['transcript'],
            actual_output=json.dumps(llm_output, ensure_ascii=False)
        )
        
        evaluation_results = {}
        tasks = []
        for name, metric in self.star_metrics.items():
            async def measure_metric(metric_name, metric_instance):
                try:
                    await metric_instance.a_measure_async(test_case)
                    evaluation_results[metric_name] = {
                        "score": metric_instance.score,
                        "reason": metric_instance.reason
                    }
                    logger.info(f"DeepEval評価 ({metric_name}): Score={metric_instance.score}")
                except Exception as e:
                    logger.error(f"DeepEval評価 ({metric_name}) でエラーが発生: {e}")
                    evaluation_results[metric_name] = {"score": None, "reason": str(e)}
            
            tasks.append(measure_metric(name, metric))
        
        await asyncio.gather(*tasks)
        return evaluation_results

    def _parse_gemini_response_data(self, response_text: str) -> dict:
        """
        Geminiからの生のテキストレスポンスをパースして、JSON形式の辞書に変換する。
        マークダウンの```json ... ```ブロックがあっても大丈夫なようにしてるよ。
        """
        logger.debug(f"パース対象のレスポンス: {response_text}")
        try:
            # ```json ... ``` のようなマークダウンコードブロックを抽出
            match = re.search(r"```json\s*([\s\S]+?)\s*```", response_text)
            if match:
                json_str = match.group(1)
            else:
                # JSONコードブロックが見つからない場合は、テキスト全体をJSONとしてパース試行
                json_str = response_text

            # JSON文字列をPythonの辞書に変換
            data = json.loads(json_str)
            
            # スコアの合計が正しいかチェック・修正
            if "star_evaluation" in data and "overall_score" in data:
                # scoreがNoneになる可能性も考慮
                valid_scores = [
                    item.get("score") for item in data["star_evaluation"].values() 
                    if isinstance(item.get("score"), (int, float))
                ]
                calculated_score = sum(valid_scores)
                
                # 比較対象も数値か確認
                provided_score = data["overall_score"]
                if isinstance(provided_score, (int, float)) and provided_score != calculated_score:
                    logger.warning(
                        f"Overall score mismatch. Provided: {provided_score}, "
                        f"Calculated: {calculated_score}. "
                        "Using calculated score."
                    )
                    data["overall_score"] = calculated_score
            
            logger.info("GeminiレスポンスのJSONパースに成功しました。")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSONパースエラー: {e}\n対象テキスト: {response_text[:500]}")
            return {"error": "Failed to parse JSON response", "raw_response": response_text}
        except Exception as e:
            logger.error(f"レスポンスパース中に予期せぬエラー: {e}", exc_info=True)
            return {"error": f"An unexpected error occurred during parsing: {e}", "raw_response": response_text}

# --- シングルトンインスタンス管理 ---
gemini_service_instance = None

def get_gemini_service():
    """シングルトンパターンでGeminiServiceのインスタンスを返す"""
    global gemini_service_instance
    if gemini_service_instance is None:
        logger.info("GeminiServiceの新しいインスタンスを作成します。")
        gemini_service_instance = GeminiService()
    return gemini_service_instance

# --- 後方互換性のためのラッパー関数 ---
# 古い関数に依存している他のモジュールを壊さないための一時的な措置
async def generate_structured_feedback(evaluation_context: dict) -> dict:
    """古い関数呼び出し用の非同期ラッパー。新しいGeminiServiceを経由して実行する。"""
    logger.warning("非推奨: 'generate_structured_feedback' を直接呼び出しています。'get_gemini_service' を使用してください。")
    service = get_gemini_service()
    return await service.generate_structured_feedback(evaluation_context)

# 以下のグローバル変数の初期化は、GeminiServiceクラスの__init__に統合されたため不要
# def load_gemini_config_and_init(): ...
# def parse_gemini_response_data(response_text: str) -> dict: ...
# async def generate_structured_feedback(evaluation_context: dict) -> dict: ...
# はクラスメソッドに移動したため、グローバルスコープからは削除 