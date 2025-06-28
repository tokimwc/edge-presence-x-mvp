import pyaudio
import yaml
import os

# --- 設定ファイルの読み込み ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'gcp-config.yaml')
try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    config = {}

# --- アプリケーション全体で共有するオーディオ設定 ---
# speech_processor.py や pitch_worker.py など、
# 複数のモジュールから参照される定数をここに集めるよ！

# Google Cloud Speech-to-Text APIが推奨するサンプルレート
RATE = 16000

# 一度に処理する音声データのサイズ（フレーム数）。
# 100msごとに処理するのが一般的だけど、ここではWebSocketでの送受信も考慮して
# ちょい大きめの 2048 フレームにしてみる！
CHUNK = 1024 * 2

# チャンネル数 (1: モノラル, 2: ステレオ)
# 文字起こしやピッチ解析はモノラルでやるのが基本！
CHANNELS = 1

# PyAudioで使用する音声データのフォーマット。
# pyaudio.paInt16 は、16ビット整数（-32768〜32767）を表すよ。
# PCのマイク入力では、これが一番メジャーな形式！
FORMAT = pyaudio.paInt16

# 1サンプルあたりのバイト数。
# paInt16 は 16bit = 2byte だから、2になるよ。
SAMPLE_WIDTH = 2

# Geminiのモデル設定
GEMINI_MODEL_NAME = config.get("gemini", {}).get("model_name", "gemini-1.5-flash-001")

# Dialogflowの設定
DIALOGFLOW_LANGUAGE_CODE = config.get("dialogflow", {}).get("language_code", "ja")
DIALOGFLOW_LOCATION = config.get("dialogflow", {}).get("location") # デフォルトNoneをやめて、設定ファイルに必須とする

# Pub/Subのトピック名
PUBSUB_TOPIC_ID = config.get("pubsub", {}).get("topic_id", "ep-x-transcriptions")

# Pub/Subのトピック名 