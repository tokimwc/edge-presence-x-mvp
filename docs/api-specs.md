# EP-X API仕様書

## Speech Processing API

### POST /api/speech/stream
リアルタイム音声ストリーミング処理

**Request:**
```
{
  "audio_config": {
    "encoding": "WEBM_OPUS",
    "sample_rate": 24000,
    "language_code": "ja-JP"
  },
  "session_id": "uuid-string"
}
```

**Response (WebSocket):**
```
{
  "transcript": "こんにちは、よろしくお願いします",
  "confidence": 0.95,
  "pitch_analysis": {
    "frequency": 220.5,
    "stability": 0.8
  },
  "timestamp": "2025-06-02T22:26:00Z"
}
```

## AI Evaluation API

### POST /api/evaluate/star
STAR手法による回答評価

**Request:**
```
{
  "question": "チームでの困難な状況について教えてください",
  "answer_text": "ユーザーの回答テキスト",
  "audio_features": {
    "pitch_variance": 0.3,
    "speaking_rate": 150,
    "emotion_score": 0.7
  }
}
```

**Response:**
```
{
  "star_evaluation": {
    "situation": {"score": 8.5, "feedback": "状況説明が具体的"},
    "task": {"score": 7.0, "feedback": "課題の明確化が必要"},
    "action": {"score": 9.0, "feedback": "行動が詳細で良い"},
    "result": {"score": 6.5, "feedback": "結果の数値化を推奨"}
  },
  "overall_score": 7.8,
  "confidence_level": "高",
  "improvement_suggestions": [
    "数値を使った具体的な成果表現",
    "感情表現の豊かさ向上"
  ]
}
```

## Emotion Analysis API

### WebSocket /ws/emotion
リアルタイム感情分析

**Message Format:**
```
{
  "type": "emotion_update",
  "data": {
    "primary_emotion": "confidence",
    "intensity": 0.75,
    "emotions": {
      "joy": 0.4,
      "confidence": 0.75,
      "neutral": 0.2,
      "anxiety": 0.1
    }
  }
}
```