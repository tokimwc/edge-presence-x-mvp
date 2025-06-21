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
let workletNode: AudioWorkletNode | null = null;
const SAMPLE_RATE = 16000; // バックエンドの期待値に合わせる
const audioStream = ref<MediaStream | null>(null);
const localStream = ref<MediaStream | null>(null);

/** 面接の状態を表す型 */
export type InterviewState = 'idle' | 'starting' | 'in_progress' | 'evaluating' | 'finished' | 'error';

export const useInterviewStore = defineStore('interview', () => {
  /**
   * WebSocketの接続状態
   * @type {import('vue').Ref<WebSocketConnectionState>}
   */
  const connectionState = ref<WebSocketConnectionState>('idle');

  /**
   * 面接の状態
   * @type {import('vue').Ref<InterviewState>}
   */
  const interviewState = ref<InterviewState>('idle');

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
   * @deprecated interviewStateを使用してください
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
        interviewState.value = 'evaluating';
        console.log('⌛ AIによる評価が開始されました...');
        break;
      case 'final_evaluation':
        // このイベントはgemini_feedbackに統合されつつあるが、後方互換性のために残す
        // feedbackがオブジェクトの場合があるので、raw_evaluationを優先的に使う
        isEvaluating.value = false;
        interviewState.value = 'finished';
        const rawEval = message.payload.evaluation?.raw_evaluation || JSON.stringify(message.payload.evaluation);
        evaluations.value.push({
            type: '総合評価 (Gemini)',
            score: message.payload.evaluation?.score || 0,
            feedback: rawEval,
        });
        console.log('👑 AIによる最終評価を受信しました！(final_evaluation)');
        break;
      case 'gemini_feedback':
        isEvaluating.value = false;
        interviewState.value = 'finished';
        // 既存の評価があれば更新、なければ追加
        const existingEvalIndex = evaluations.value.findIndex(e => e.type === '総合評価 (Gemini)');
        const newEval = {
          type: '総合評価 (Gemini)',
          score: message.payload.score || 0,
          feedback: message.payload.raw_evaluation,
        };
        if (existingEvalIndex > -1) {
          evaluations.value[existingEvalIndex] = newEval;
        } else {
          evaluations.value.push(newEval);
        }
        console.log('👑 AIによる構造化フィードバックを受信しました！(gemini_feedback)');
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
        interviewState.value = 'error';
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
      isInterviewActive.value = false; // 古い値も更新しておく
      if (interviewState.value !== 'finished') {
        interviewState.value = 'idle';
      }
      console.log('WebSocket connection closed.');
    };
  }

  /**
   * WebSocket接続を閉じます。
   */
  function disconnect() {
    if (socket && socket.readyState === WebSocket.OPEN) {
      if (isInterviewActive.value || interviewState.value === 'in_progress') {
        stopInterview();
      }
      socket.close();
      socket = null;
    }
    stopAudioStreaming();
    console.log('🔌 WebSocket disconnected.');
  }

  /**
   * マイクからの音声ストリーミングを開始します。
   */
  async function startAudioStreaming() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      errorMessage.value = 'WebSocket接続がありません。';
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      localStream.value = stream;
      interviewState.value = 'in_progress'; // 音声取得成功でin_progressへ

      audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });

      // Load the audio worklet processor from the public folder
      await audioContext.audioWorklet.addModule('/audio-processor.js');

      const source = audioContext.createMediaStreamSource(stream);
      workletNode = new AudioWorkletNode(audioContext, 'audio-processor');

      workletNode.port.onmessage = (event) => {
        if (socket?.readyState === WebSocket.OPEN && isInterviewActive.value) {
          // event.data is the ArrayBuffer from the worklet
          const float32Data = new Float32Array(event.data);
          
          // Convert to 16-bit PCM
          const pcmData = new Int16Array(float32Data.length);
          for (let i = 0; i < float32Data.length; i++) {
            let s = Math.max(-1, Math.min(1, float32Data[i]));
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          socket.send(pcmData.buffer);
        }
      };

      source.connect(workletNode);
      workletNode.connect(audioContext.destination);

      console.log('🎤 マイクの準備OK！音声ストリーミング開始！(AudioWorklet)');
    } catch (err) {
      console.error('マイクの取得に失敗しました:', err);
      errorMessage.value = 'マイクへのアクセスが拒否されたか、マイクが見つかりませんでした。';
      interviewState.value = 'error';
    }
  }

  /**
   * 音声ストリーミングを停止します。
   */
  function stopAudioStreaming() {
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    
    localStream.value?.getTracks().forEach((track) => track.stop());
    localStream.value = null;

    workletNode?.port.close();
    workletNode?.disconnect();
    workletNode = null;
    
    audioContext?.close().catch(console.error);
    audioContext = null;

    console.log('🛑 音声ストリーミングを停止しました。');
  }

  /**
   * 面接セッションを開始します。
   */
  async function startInterview() {
    if (interviewState.value === 'in_progress' || interviewState.value === 'starting') {
      console.warn('Interview is already in progress.');
      return;
    }

    console.log('🚀 面接セッションを開始します...');
    isInterviewActive.value = true;
    interviewState.value = 'starting';
    isEvaluating.value = false;
    errorMessage.value = null;
    transcriptions.value = [{ text: '...', is_final: false, timestamp: Date.now() }];
    evaluations.value = [];
    pitchHistory.value = [];
    sentimentHistory.value = [];

    connect();

    // DOM更新を待ってからストリーミングを開始
    await new Promise(resolve => setTimeout(resolve, 100));

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        action: 'start',
        question: '自己紹介をお願いします。', // 将来的には動的に変更
      }));
      await startAudioStreaming();
    } else {
        // もし接続がまだなら、onopenハンドラでstartAudioStreamingを呼ぶ必要がある
        // 今回はconnect()が同期的ではないため、接続完了を待つ必要がある
        // より堅牢な実装は、接続状態を監視して、'connected'になったら後続処理を行うこと
        console.log("WebSocket is not open. Waiting for connection...");
        // ここではエラーとして扱うか、リトライロジックを入れる
        // シンプルにするため、一度`connect`を呼んで少し待つ実装にしている
    }
  }

  /**
   * 面接セッションを停止します。
   */
  function stopInterview() {
    if (interviewState.value !== 'in_progress') return;

    console.log('🛑 面接セッションを終了します...');
    interviewState.value = 'evaluating'; // 評価中に状態を変更
    isInterviewActive.value = false; // 古いフラグも更新

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'end_session' }));
      console.log('📤 セッション終了メッセージを送信しました。');
    }
    
    isEvaluating.value = true;
    stopAudioStreaming();
  }

  /**
   * ストアの状態をリセットします。
   */
  function resetStore() {
    console.log('🔄 ストアの状態をリセットします。');
    disconnect();
    isInterviewActive.value = false;
    isEvaluating.value = false;
    errorMessage.value = null;
    transcriptions.value = [];
    evaluations.value = [];
    pitchHistory.value = [];
    sentimentHistory.value = [];
    interviewState.value = 'idle';
  }

  return {
    connectionState,
    transcriptions,
    evaluations,
    pitchHistory,
    sentimentHistory,
    isInterviewActive, // 後方互換性のために残すが、徐々に使わないようにする
    isEvaluating,
    errorMessage,
    audioStream, // for visualizer
    localStream,
    interviewState,

    connect,
    disconnect,
    startInterview,
    stopInterview,
    resetStore, // 外部からリセットできるように
  };
});
