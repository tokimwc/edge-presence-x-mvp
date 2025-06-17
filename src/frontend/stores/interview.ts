import { defineStore } from 'pinia';
import { ref } from 'vue';

/** WebSocketの接続状態を表す型 */
export type WebSocketConnectionState = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

// JSDocからTypeScriptのinterfaceに変更
export interface Transcription {
  text: string;
  is_final: boolean;
  timestamp: number;
}

// JSDocからTypeScriptのinterfaceに変更
export interface Evaluation {
  type: string;
  score: number;
  feedback: string;
}

export interface PitchData {
  timestamp: number;
  pitch: number;
}

export interface SentimentData {
  timestamp: number;
  score: number;
  magnitude: number;
}

// --- Audio Streaming ---
// グローバルスコープで宣言して、複数の関数からアクセスできるようにする
let audioContext: AudioContext | null = null;
let stream: MediaStream | null = null;
let processor: ScriptProcessorNode | null = null;
const SAMPLE_RATE = 16000; // バックエンドの期待値に合わせる
const audioStream = ref<MediaStream | null>(null);
const localStream = ref<MediaStream | null>(null);

export const useInterviewStore = defineStore('interview', () => {
  /**
   * WebSocketの接続状態
   * @type {import('vue').Ref<WebSocketConnectionState>}
   */
  const connectionState = ref<WebSocketConnectionState>('idle');

  /**
   * リアルタイム文字起こしデータ
   * @type {import('vue').Ref<Transcription[]>}
   */
  const transcriptions = ref<Transcription[]>([]);

  /**
   * AIからの評価フィードバック
   * @type {import('vue').Ref<Evaluation[]>}
   */
  const evaluations = ref<Evaluation[]>([]);

  /**
   * ピッチデータの履歴
   * @type {import('vue').Ref<PitchData[]>}
   */
  const pitchHistory = ref<PitchData[]>([]);

  /**
   * 感情分析データの履歴
   * @type {import('vue').Ref<SentimentData[]>}
   */
  const sentimentHistory = ref<SentimentData[]>([]);

  /**
   * 面接がアクティブかどうか
   * @type {import('vue').Ref<boolean>}
   */
  const isInterviewActive = ref(false);

  /**
   * AIによる評価が実行中かどうか
   * @type {import('vue').Ref<boolean>}
   */
  const isEvaluating = ref(false);

  /**
   * エラーメッセージ
   * @type {import('vue').Ref<string | null>}
   */
  const errorMessage = ref<string | null>(null);

  /** @type {WebSocket | null} */
  let socket: WebSocket | null = null;

  /**
   * バックエンドから受信したメッセージを処理するハンドラ
   * @param {any} message
   */
  function handleWebsocketMessage(message: any) {
    console.log("📨 メッセージ受信:", message);
    switch (message.type) {
      case 'interim_transcript':
        // 最後の一時的な文字起こしを更新
        const lastTranscription = transcriptions.value[transcriptions.value.length - 1];
        if (lastTranscription && !lastTranscription.is_final) {
          lastTranscription.text = message.payload.transcript;
        } else {
          transcriptions.value.push({
            text: message.payload.transcript,
            is_final: false,
            timestamp: Date.now(),
          });
        }
        break;
      case 'final_transcript_segment':
        // 最後の一時的な文字起こしを確定させるか、新しい確定セグメントを追加
        const finalLast = transcriptions.value[transcriptions.value.length - 1];
         if (finalLast && !finalLast.is_final) {
           finalLast.text = message.payload.transcript;
           finalLast.is_final = true;
         } else {
            transcriptions.value.push({
              text: message.payload.transcript,
              is_final: true,
              timestamp: Date.now(),
            });
         }
        // 次の文字起こしのために、新しい一時的なプレースホルダを追加
        transcriptions.value.push({ text: '...', is_final: false, timestamp: Date.now() + 1 });
        break;
      case 'evaluation_started':
        isEvaluating.value = true;
        console.log('⌛ AIによる評価が開始されました...');
        break;
      case 'final_evaluation':
        isEvaluating.value = false;
        evaluations.value.push({
            type: '総合評価 (Gemini)',
            score: 0, // TODO: 本来はレスポンスからパースすべき
            feedback: message.payload.evaluation,
        });
        console.log('👑 AIによる最終評価を受信しました！');
        break;
      case 'gemini_feedback':
        isEvaluating.value = false;
        evaluations.value.push({
            type: '総合評価 (Gemini)',
            score: message.payload.score || 0, // 仮
            feedback: message.payload.raw_evaluation,
        });
        break;
      case 'pitch_analysis':
        const newPitchData: PitchData = {
          timestamp: message.payload.timestamp,
          pitch: message.payload.pitch,
        };
        pitchHistory.value.push(newPitchData);
        // Optional: Keep the array from growing indefinitely
        if (pitchHistory.value.length > 200) {
          pitchHistory.value.shift();
        }
        break;
      case 'sentiment_analysis':
        const newSentimentData: SentimentData = {
          timestamp: Date.now(),
          score: message.payload.emotions?.score || 0,
          magnitude: message.payload.emotions?.magnitude || 0,
        };
        sentimentHistory.value.push(newSentimentData);
        if (sentimentHistory.value.length > 200) {
          sentimentHistory.value.shift();
        }
        break;
      case 'error':
        errorMessage.value = `サーバーエラー: ${message.payload.message}`;
        break;
      default:
        console.warn('🤔 不明なメッセージタイプ:', message.type);
    }
  }

  /**
   * WebSocketサーバーに接続します。
   */
  function connect() {
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.warn('WebSocket is already connected.');
      return;
    }

    connectionState.value = 'connecting';

    // Viteの開発サーバーのプロキシを経由して接続
    const socketUrl = `ws://${window.location.host}/ws/v1/interview`;
    socket = new WebSocket(socketUrl);

    socket.onopen = () => {
      connectionState.value = 'connected';
      console.log('🎉 WebSocket connection established!');
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebsocketMessage(data); // 新しいハンドラを呼び出す
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
        errorMessage.value = 'Failed to parse server message.';
      }
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      connectionState.value = 'error';
      errorMessage.value = 'WebSocket connection failed.';
    };

    socket.onclose = () => {
      connectionState.value = 'disconnected';
      isInterviewActive.value = false;
      console.log('WebSocket connection closed.');
    };
  }

  /**
   * WebSocket接続を閉じます。
   */
  function disconnect() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        if (isInterviewActive.value) {
            stopInterview();
        }
        socket.close();
        socket = null;
    }
    console.log('🔌 WebSocket disconnected.');
  }

  /**
   * マイクからの音声ストリーミングを開始します。
   */
  async function startAudioStreaming() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
       errorMessage.value = "WebSocket接続がありません。";
       return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      audioStream.value = stream;
      localStream.value = stream;
      audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
      const source = audioContext.createMediaStreamSource(stream);
      processor = audioContext.createScriptProcessor(4096, 1, 1);

      processor.onaudioprocess = (e) => {
        if (socket && socket.readyState === WebSocket.OPEN && isInterviewActive.value) {
          const inputData = e.inputBuffer.getChannelData(0);
          // 16-bit PCMに変換
          const pcmData = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            let s = Math.max(-1, Math.min(1, inputData[i]));
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          console.log(`🎤 音声データ送信中... (${pcmData.byteLength} bytes)`);
          socket.send(pcmData.buffer);
        }
      };

      const analyser = audioContext.createAnalyser();
      source.connect(analyser);

      source.connect(processor);
      // ScriptProcessorNodeをdestinationに接続しないとonaudioprocessが発火しない
      // ユーザーに自分の声が聞こえないようにGainNodeを挟んで無音化する
      const gainNode = audioContext.createGain();
      gainNode.gain.value = 0;
      processor.connect(gainNode);
      gainNode.connect(audioContext.destination);

      console.log("🎤 マイクの準備OK！音声ストリーミング開始！");

    } catch (e) {
      console.error('マイクの取得に失敗しました。', e);
      errorMessage.value = "マイクの使用が許可されていません。ブラウザの設定を確認してください。";
      isInterviewActive.value = false;
    }
  }

  /**
   * 音声ストリーミングを停止します。
   */
  function stopAudioStreaming() {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    if (audioContext) {
      audioContext.close();
    }
    if (processor) {
      processor.disconnect();
    }
    stream = null;
    audioStream.value = null;
    localStream.value = null;
    audioContext = null;
    processor = null;
    console.log("🛑 音声ストリーミングを停止しました。");
  }

  /**
   * 面接セッションを開始します。
   */
  async function startInterview() {
    if (connectionState.value !== 'connected' || !socket) {
      errorMessage.value = 'サーバーに接続されていません。';
      return;
    }
    // 既存のデータをリセット
    transcriptions.value = [];
    evaluations.value = [];
    errorMessage.value = null;

    isInterviewActive.value = true;
    transcriptions.value = [{ text: '...', is_final: false, timestamp: Date.now() }];
    evaluations.value = [];
    errorMessage.value = null;
    isEvaluating.value = false; // 念のためリセット

    await startAudioStreaming();

    if (socket && socket.readyState === WebSocket.OPEN) {
      // バックエンドに面接開始のメッセージを送信
      socket.send(JSON.stringify({ action: 'start' })); // バックエンドの期待値 'start' に修正
      console.log('▶️ 面接開始の合図を送信しました。');
    }
  }

  /**
   * 面接を終了し、最終評価をリクエストします。
   */
  function stopInterview() {
    if (isInterviewActive.value) {
      console.log('🗣️ 面接セッションを終了します。');
      isInterviewActive.value = false;
      // Clear history for the next session
      transcriptions.value = [];
      evaluations.value = [];
      pitchHistory.value = [];
      sentimentHistory.value = [];

      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'end_session' }));
      } else {
        errorMessage.value = "サーバーに接続されていないため、面接を正常に終了できません。";
        isEvaluating.value = false; // エラー時は評価中にしない
      }

      // notify avatar modules to cleanup
      window.dispatchEvent(new Event('avatar/reset'))
    }
  }

  return {
    connectionState,
    transcriptions,
    evaluations,
    pitchHistory,
    sentimentHistory,
    isInterviewActive,
    isEvaluating,
    errorMessage,
    connect,
    disconnect,
    startInterview,
    stopInterview,
    audioStream,
    localStream,
  };
});
