import os
import json
import logging
import vertexai
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold

# ロガー設定
logger = logging.getLogger(__name__)

# --- 定数 ---
# このファイル (gemini_service.py) のディレクトリ
_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
# プロジェクトルートの絶対パス (src/backend/services -> src/backend -> src -> project_root)
PROJECT_ROOT = os.path.abspath(os.path.join(_SERVICE_DIR, '..', '..', '..'))
GEMINI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "gemini_config.json")

PROMPT_TEMPLATE = """
# プロンプトテンプレート：AI面接評価システム

あなたが、経験豊富なキャリアコンサルタントであり、行動面接のプロフェッショナルです。
特にSTAR手法を用いた回答の分析と、声のトーンや感情表現から候補者のコミュニケーション能力を見抜くことに長けています。
提供された情報に基づき、面接の回答を多角的に評価し、具体的かつ建設的なフィードバックを提供してください。

## 入力情報

### 面接の質問:
```
{interview_question}
```

### 回答の文字起こし:
```
{transcript}
```

### ピッチ解析結果:
- 平均ピッチ: {average_pitch} Hz
- ピッチの変動幅: {pitch_variation} Hz
- 話す速度: {speaking_rate} 文字/分
- ポーズの頻度: {pause_frequency} 回/分
- ポーズの平均時間: {average_pause_duration} 秒

### 感情分析結果:
- 主な感情: {dominant_emotion}
- 感情スコア ({dominant_emotion}): {emotion_score}
- 感情の強さ: {emotion_intensity}
- 発話中の感情の推移: {emotion_transition}

## 評価基準

### 1. STAR手法の評価
*   **Situation（状況）:**
    *   具体的な状況説明が明確になされているか？
    *   回答者がどのような状況に置かれていたのか、背景情報が十分に提供されているか？
    *   いつ、どこで、誰が関わっていたのかが明確か？
*   **Task（課題）:**
    *   取り組むべき課題や目標が明確に定義されているか？
    *   その課題の重要性や困難度が伝わるか？
    *   何を達成する必要があったのかが具体的か？
*   **Action（行動）:**
    *   課題解決のために、どのような思考プロセスを経て、具体的にどのような行動を取ったのか説明されているか？
    *   行動の主体は回答者自身か？
    *   行動の理由や目的が明確か？
    *   複数の行動がある場合、それらが論理的に関連しているか？
*   **Result（結果）:**
    *   行動の結果、どのような具体的な成果が得られたのか明確に説明されているか？
    *   可能な限り定量的なデータ（数値、割合など）を用いて成果を示せているか？
    *   結果から何を学び、次にどう活かそうとしているかが述べられているか？
    *   ポジティブな結果だけでなく、ネガティブな結果やそこからの学びもあれば評価する。

### 2. 回答の構造
*   **論理性と構成:**
    *   回答全体が論理的で分かりやすい構成になっているか？ (例: PREP法、時系列など)
    *   話の導入、本論、結論が明確か？
    *   冗長な部分や話が飛躍している箇所はないか？
*   **具体性:**
    *   抽象的な表現に終始せず、具体的なエピソードや事例を交えて説明できているか？
    *   誰が聞いても情景をイメージできるような詳細さがあるか？

### 3. 声のトーンと話し方
*   **自信と熱意:**
    *   声のトーンは安定しており、自信が感じられるか？
    *   語尾が明瞭で、ハキハキと話せているか？
    *   話の内容に対する熱意や意欲が声から伝わるか？
    *   早口すぎたり、逆に遅すぎて間延びしていないか？
*   **聞き取りやすさ:**
    *   声量や滑舌は適切で、聞き取りやすい話し方か？
    *   不要な「えーっと」「あのー」などのフィラーが多すぎないか？

### 4. 感情表現
*   **適切性と一貫性:**
    *   話の内容と感情表現（声のトーン、話す速度などから推測されるもの）が一貫しているか？
    *   場面に応じた適切な感情が表現できているか？（例：困難を語る際は真剣なトーン、成功を語る際は明るいトーンなど）
    *   感情の起伏が激しすぎたり、逆に乏しすぎたりしないか？

### 5. 全体的な印象
*   **分かりやすさ:**
    *   回答全体を通して、伝えたいことが明確に伝わってくるか？
    *   専門用語を使いすぎず、相手に配慮した言葉遣いができているか？
*   **説得力:**
    *   自己PRや経験談に説得力があり、聞き手を納得させられるか？
    *   根拠に基づいた主張ができているか？
*   **熱意と意欲:**
    *   その企業や職務に対する熱意や入社意欲が感じられるか？
    *   ポジティブな姿勢で面接に臨んでいるか？

## 出力形式

### 1. 総合評価 (5段階)
1.  改善が必要
2.  まだ改善の余地がある
3.  良い
4.  非常に良い
5.  素晴らしい

### 2. 各評価項目の詳細フィードバック
*   **STAR手法:**
    *   Situation: （具体的なフィードバックと改善点）
    *   Task: （具体的なフィードバックと改善点）
    *   Action: （具体的なフィードバックと改善点）
    *   Result: （具体的なフィードバックと改善点）
*   **回答の構造:** （具体的なフィードバックと改善点）
*   **声のトーンと話し方:** （具体的なフィードバックと改善点、ピッチ解析結果を元に）
*   **感情表現:** （具体的なフィードバックと改善点、感情分析結果を元に）
*   **全体的な印象:** （具体的なフィードバックと改善点）

### 3. 回答全体の改善点 (3つ程度)
1.  （具体的な改善点）
2.  （具体的な改善点）
3.  （具体的な改善点）

### 4. アピールポイント (3つ程度)
1.  （特に優れている点、強みとなる点）
2.  （特に優れている点、強みとなる点）
3.  （特に優れている点、強みとなる点）

## 指示

上記の入力情報と評価基準に基づき、面接の回答を詳細に分析・評価してください。
そして、定義された出力形式に従って、総合評価、各評価項目の詳細なフィードバック、回答全体の改善点、およびアピールポイントを生成してください。
フィードバックは、具体的で、候補者が次の面接に活かせるような実践的なアドバイスを心がけてください。

## 制約
*   個人を特定できる情報（氏名、具体的な企業名、製品名など、一般的に公開されていない情報）を生成、または推測して出力しないでください。
*   いかなる形であれ、差別的な表現や、特定の個人・団体を不当に貶めるような内容は絶対に含めないでください。
*   提供された情報のみに基づいて評価を行い、憶測や個人的な偏見を排除してください。
*   法律や倫理に反するような不適切なアドバイスは行わないでください。
*   フィードバックは客観的かつ建設的なものに終始してください。
"""

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


async def get_gemini_evaluation(interview_question: str, transcript: str, pitch_analysis: dict, emotion_analysis: dict) -> str | None:
    """
    Gemini評価APIを非同期で呼び出し、評価結果のテキストを返す。
    """
    if not gemini_model_instance:
        logger.error("Geminiモデルが初期化されていないため、評価を実行できません。")
        return None

    # プロンプトに情報を埋め込む
    prompt = PROMPT_TEMPLATE.format(
        interview_question=interview_question,
        transcript=transcript,
        # speech_processor._summarize_pitch_data() のキー名と完全に一致させる！
        average_pitch=pitch_analysis.get("average_pitch", "N/A"),
        pitch_variation=pitch_analysis.get("pitch_variation", "N/A"),
        pitch_stability=pitch_analysis.get("pitch_stability", "N/A"),
        # ↓以下の項目は現状の実装では計算していないため、"N/A"とするか、プロンプトテンプレートから削除する
        speaking_rate="N/A", # speaking_rate は未計算
        pause_frequency="N/A", # pause_frequency は未計算
        average_pause_duration="N/A", # average_pause_duration は未計算
        # speech_processor._handle_emotion_data() のキー名と完全に一致させる！
        dominant_emotion=emotion_analysis.get("dominant_emotion", "N/A"),
        emotion_score=emotion_analysis.get("emotion_score", "N/A"),
        emotion_intensity=emotion_analysis.get("emotion_intensity", "N/A"),
        emotion_transition=emotion_analysis.get("emotion_transition", "N/A")
    )
    
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

    try:
        logger.info("Geminiに評価をリクエストします...")
        response = await gemini_model_instance.generate_content_async(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings,
            stream=False
        )
        
        evaluation_text = response.text
        logger.info("Geminiから面接評価を受信しました。")
        return evaluation_text
    
    except Exception as e:
        logger.error(f"Gemini APIの呼び出し中にエラーが発生しました: {e}", exc_info=True)
        return None


def parse_gemini_response_data(response_text: str) -> dict:
    """
    Geminiからのレスポンス(テキスト)をパースして辞書形式に変換する。
    現状は単純にテキストをそのまま返す。将来的にはMarkdownをパースするなど。
    """
    logger.info("Geminiレスポンスのパース処理 (現在は生テキストを返します)")
    return {"raw_evaluation": response_text} 