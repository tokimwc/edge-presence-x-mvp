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
export interface StarEvaluationItem {
  score: number;
  feedback: string;
}

export interface StarEvaluation {
  situation: StarEvaluationItem;
  task: StarEvaluationItem;
  action: StarEvaluationItem;
  result: StarEvaluationItem;
}

export interface OverallFeedback {
  overall_score: number;
  strengths: string[];
  improvement_suggestions: string[];
}

export interface Evaluation {
  type: 'STAR_EVALUATION' | 'OVERALL_FEEDBACK' | 'LEGACY_EVALUATION';
  data: StarEvaluation | OverallFeedback | { score: number; feedback: string; };
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

  const currentTranscription = ref<string>('');

  // final transcriptの正規化比較用関数を追加
  function normalizeText(text: string): string {
    return text
      .replace(/[\s　]+/g, '') // 全角・半角スペースを除去
      .replace(/[。、,.]/g, '') // 句読点を除去
      .replace(/\r?\n/g, '') // 改行を除去
      .toLowerCase();
  }

  /**
   * バックエンドから受信したメッセージを処理するハンドラ
   * @param {any} message
   */
  function handleWebsocketMessage(message: any) {
    console.log("📨 メッセージ受信:", message);
    switch (message.type) {
      case 'interim_transcript':
        const latestTranscription = transcriptions.value[transcriptions.value.length - 1];
        if (latestTranscription && !latestTranscription.is_final) {
          latestTranscription.text = message.payload.text;
          latestTranscription.timestamp = message.payload.timestamp * 1000;
        } else {
          transcriptions.value.push({
            text: message.payload.text,
            is_final: false,
            timestamp: message.payload.timestamp * 1000,
          });
        }
        break;
      case 'final_transcript':
        const lastIdx = transcriptions.value.length - 1;
        if (lastIdx >= 0 && !transcriptions.value[lastIdx].is_final) {
          transcriptions.value[lastIdx] = {
            text: message.payload.text,
            is_final: true,
            timestamp: message.payload.timestamp * 1000,
          };
        } else {
           transcriptions.value.push({
            text: message.payload.text,
            is_final: true,
            timestamp: message.payload.timestamp * 1000,
          });
        }
        transcriptions.value.push({ text: '...', is_final: false, timestamp: Date.now() });
        break;
      case 'transcript_update': {
        const { transcript } = message.payload;
        currentTranscription.value = transcript;
        break;
      }
      case 'sentiment_update': {
        const { sentiment } = message.payload;
        if (sentiment && Object.keys(sentiment).length > 0) {
          sentimentHistory.value.push(sentiment);
        }
        break;
      }
      case 'evaluation_started':
        isEvaluating.value = true;
        interviewState.value = 'evaluating';
        console.log('⌛ AIによる評価が開始されました...');
        break;
      case 'final_evaluation':
        isEvaluating.value = false;
        interviewState.value = 'finished';
        // バックエンドから直接評価オブジェクトがpayloadとして送られてくる
        const newEvaluationData = message.payload;
        
        // 既存の評価をクリアして、新しい評価で完全に置き換える
        evaluations.value = [];
        
        if (newEvaluationData.star_evaluation) {
          evaluations.value.push({
            type: 'STAR_EVALUATION',
            data: newEvaluationData.star_evaluation,
          });
        }
        
        if (newEvaluationData.overall_score !== undefined) {
           evaluations.value.push({
            type: 'OVERALL_FEEDBACK',
            data: {
              overall_score: newEvaluationData.overall_score,
              strengths: newEvaluationData.strengths,
              improvement_suggestions: newEvaluationData.improvement_suggestions,
            }
          });
        }

        console.log('👑 AIによる最終評価を受信しました！', evaluations.value);
        break;
      case 'pitch_analysis':
        const newPitchData: PitchData = {
          timestamp: (message.payload.timestamp || Date.now() / 1000) * 1000, // バックエンドのPythonタイムスタンプ(s)をJS(ms)に変換
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
          timestamp: (message.payload.timestamp || Date.now() / 1000) * 1000, // バックエンドのPythonタイムスタンプ(s)をJS(ms)に変換
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
  function connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        console.log('✅ すでに接続済みです');
        resolve();
        return;
      }
      
      // const socketUrl = import.meta.env.VITE_WEBSOCKET_URL || 'ws://localhost:8000/ws/v1/interview';
      const socketUrl = 'wss://ep-x-backend-495003035191.asia-northeast1.run.app/ws/v1/interview';
      console.log(`🔌 Connecting to WebSocket at: ${socketUrl}`);

      try {
        socket = new WebSocket(socketUrl);

        connectionState.value = 'connecting';

        socket.onopen = () => {
          connectionState.value = 'connected';
          console.log('🎉 WebSocket connection established!');
          resolve();
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
          reject(error);
        };

        socket.onclose = () => {
          connectionState.value = 'disconnected';
          isInterviewActive.value = false; // 古い値も更新しておく
          if (interviewState.value !== 'finished' && interviewState.value !== 'error') {
            interviewState.value = 'idle';
          }
          console.log('WebSocket connection closed.');
        };
      } catch (error) {
        console.error('WebSocket connection error:', error);
        connectionState.value = 'error';
        errorMessage.value = 'WebSocket connection failed.';
        reject(error);
      }
    });
  }

  /**
   * WebSocket接続を閉じます。
   */
  function disconnect() {
    if (socket) {
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
        if (socket?.readyState === WebSocket.OPEN && interviewState.value === 'in_progress') {
          // event.data は audio-processor.js から送られてきた ArrayBuffer
          const float32Data = new Float32Array(event.data);
          
          // 16-bit PCM (Int16Array) に変換
          const pcmData = new Int16Array(float32Data.length);
          for (let i = 0; i < float32Data.length; i++) {
            // -1.0 から 1.0 の範囲にクリッピング
            const s = Math.max(-1, Math.min(1, float32Data[i]));
            // 16ビット整数にスケーリング
            // s < 0 ? s * 0x8000 : s * 0x7FFF;
            // 32767.0 は 16bit符号付き整数の最大値
            pcmData[i] = s * 32767.0;
          }
          
          // WebSocket経由でバイナリデータを送信
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
    currentTranscription.value = '';

    // interviewStateの変更がUIに反映されてから処理を進める
    await new Promise(resolve => setTimeout(resolve, 0));

    // 既存の接続があれば一度切断して、きれいな状態で再接続する
    if (socket) {
      disconnect();
    }
    
    try {
      await connect();

      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          action: 'start',
          question: '自己紹介をお願いします。', // 将来的には動的に変更
        }));
        await startAudioStreaming();
      } else {
        throw new Error("WebSocketの接続に失敗しました。面接を開始できません。");
      }
    } catch (error) {
        console.error("WebSocketの接続に失敗しました。面接を開始できません。", error);
        errorMessage.value = "サーバーとの接続に失敗しました。";
        interviewState.value = 'error';
    }
  }

  /**
   * 面接セッションを停止します。
   */
  function stopInterview() {
    if (!['in_progress', 'starting'].includes(interviewState.value)) return;

    console.log('🛑 面接セッションを終了します...');
    isInterviewActive.value = false; // 古いフラグも更新

    // 'starting' 状態では音声ストリーミングは開始されていない
    if (interviewState.value === 'in_progress') {
        stopAudioStreaming();
    }

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'end_session' }));
      console.log('📤 セッション終了メッセージを送信しました。');
    } else {
       // ソケットが開いていない場合は、手動で状態を更新
       interviewState.value = 'finished';
       disconnect(); // リソースのクリーンアップ
    }
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
    currentTranscription.value = '';
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
    currentTranscription,

    connect,
    disconnect,
    startInterview,
    stopInterview,
    resetStore, // 外部からリセットできるように
  };
});
