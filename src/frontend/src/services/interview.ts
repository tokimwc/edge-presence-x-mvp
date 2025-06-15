import logger from '@/lib/logger';
import { useInterviewStore } from '@/stores/interviewStore';
import { ref } from 'vue';

const isInitialized = ref(false);

// --- オーディオ関連のグローバル変数 ---
let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let audioWorkletNode: AudioWorkletNode | null = null;
let sourceNode: MediaStreamAudioSourceNode | null = null; // sourceNodeも管理対象に

// WebSocket接続を管理
let socket: WebSocket | null = null;

/**
 * マイクへのアクセス許可を要求し、メディアストリームを取得します。
 * @returns {Promise<MediaStream>} 許可されたMediaStreamオブジェクト
 * @throws {Error} マイクへのアクセスが拒否された場合
 */
async function getMediaStream(): Promise<MediaStream> {
  if (mediaStream) {
    logger.info('🎤 既存のMediaStreamを再利用します。');
    return mediaStream;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        // バックエンドの期待するサンプルレートに合わせる
        sampleRate: 16000,
        // モノラル
        channelCount: 1,
        // エコーキャンセルやノイズ抑制を有効にする
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    mediaStream = stream;
    logger.info('🎤 マイクへのアクセス許可を新規に取得しました。');
    return stream;
  } catch (error) {
    logger.error('😱 マイクへのアクセスに失敗しました:', error);
    throw new Error('マイクへのアクセスが拒否されました。ブラウザの設定を確認してください。');
  }
}

/**
 * オーディオストリーミングを開始します。
 * AudioWorkletを使用して、マイクからの音声をリアルタイムで処理し、
 * WebSocket経由でサーバーに送信します。
 *
 * @param {MediaStream} stream - マイクからのMediaStream
 */
async function startAudioStreaming(stream: MediaStream) {
  if (!audioContext || audioContext.state === 'closed') {
    audioContext = new AudioContext({
      sampleRate: 16000
    });
    logger.info('🎧 AudioContextを新規作成または再作成しました。');
  }

  // AudioWorkletが利用可能かチェック
  if (!audioContext.audioWorklet) {
    logger.error("😱 AudioWorkletはこのブラウザではサポートされていません。");
    throw new Error("AudioWorklet is not supported in this browser.");
  }

  if (audioWorkletNode) {
    logger.warn('⚠️ Audio Workletはすでに実行中です。');
    return;
  }

  try {
    // AudioWorkletプロセッサを登録
    await audioContext.audioWorklet.addModule('/audio-processor.js');

    // MediaStreamからソースノードを作成
    sourceNode = audioContext.createMediaStreamSource(stream);

    // AudioWorkletノードを作成
    audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-processor');

    // Workletからのメッセージ（PCMデータ）をWebSocketで送信
    audioWorkletNode.port.onmessage = (event) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        const pcmData = event.data;
        socket.send(pcmData);
      }
    };
    
    // ソースノードをWorkletノードに接続
    sourceNode.connect(audioWorkletNode);
    // WorkletノードをAudioContextの出力に接続 (これにより処理が開始される)
    audioWorkletNode.connect(audioContext.destination);

    logger.info('🎤 AudioWorkletの準備OK！音声ストリーミング開始！');

  } catch(error) {
    logger.error('😱 AudioWorkletの初期化に失敗しました:', error);
    throw error;
  }
}

/**
 * 音声ストリーミングを停止します。
 * マイクからのストリームトラックを停止し、AudioWorkletノードをクリーンアップします。
 */
function stopAudioStreaming() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
    logger.info('🎤 マイクのトラックを停止しました。');
  }

  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
    logger.info('🎧 ソースノードを切断しました。');
  }

  if (audioWorkletNode) {
    audioWorkletNode.port.close();
    audioWorkletNode.disconnect();
    audioWorkletNode = null;
    logger.info('🎧 AudioWorkletノードを切断・クリーンアップしました。');
  }

  // AudioContextはすぐには閉じない。もし閉じると次の面接で再作成が必要になる。
  // if (audioContext && audioContext.state !== 'closed') {
  //   audioContext.close();
  //   audioContext = null;
  // }

  logger.info('🛑 音声ストリーミングを停止しました。');
}

/**
 * WebSocketサーバーに接続します。
 * @param {string} url - 接続先のWebSocket URL
 * @param {(event: MessageEvent) => void} onMessageCallback - メッセージ受信時のコールバック
 */
function connectWebSocket(url: string, onMessageCallback: (event: MessageEvent) => void) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    logger.warn('⚠️ WebSocketはすでに接続されています。');
    return;
  }

  socket = new WebSocket(url);

  socket.onopen = () => {
    logger.info('✅ WebSocket接続が確立しました。');
    const interviewStore = useInterviewStore();
    interviewStore.isWebSocketConnected = true;
  };

  socket.onmessage = onMessageCallback;

  socket.onerror = (event) => {
    logger.error('❌ WebSocketエラーが発生しました:', event);
  };

  socket.onclose = (event) => {
    logger.info(`🔌 WebSocket接続が閉じられました: Code=${event.code}, Reason=${event.reason}`);
    const interviewStore = useInterviewStore();
    interviewStore.isWebSocketConnected = false;
    socket = null; // 閉じたソケットはnullにする
  };
}

/**
 * WebSocket接続を切断します。
 */
function disconnectWebSocket() {
  if (socket) {
    socket.close();
  }
}

/**
 * アプリケーションの初期化処理
 * - マイクへのアクセス許可
 */
export async function initialize() {
  if (isInitialized.value) {
    logger.info('✅ アプリはすでに初期化済みです。');
    return;
  }
  try {
    await getMediaStream();
    isInitialized.value = true;
  } catch (error) {
    logger.error('😱 初期化中にエラーが発生しました:', error);
    throw error;
  }
}

/**
 * 面接を開始するメインの関数
 * 1. WebSocketに接続
 * 2. 音声ストリーミングを開始
 * 3. サーバーに面接開始の合図を送る
 * @param {(event: MessageEvent) => void} onMessageCallback メッセージ受信時のコールバック
 * @param {string} question 最初の質問
 */
export async function startInterview(onMessageCallback: (event: MessageEvent) => void, question: string) {
  try {
    const stream = await getMediaStream();
    
    const wsUrl = `ws://${window.location.hostname}:8000/ws/v1/interview`;
    connectWebSocket(wsUrl, onMessageCallback);
    
    await new Promise<void>((resolve, reject) => {
      const checkInterval = setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);
      const timeout = setTimeout(() => {
        clearInterval(checkInterval);
        reject(new Error('WebSocket connection timed out.'));
      }, 5000);
    });

    await startAudioStreaming(stream);
    
    if (socket) {
      socket.send(JSON.stringify({ action: 'start', question: question }));
      logger.info('▶️ 面接開始の合図を送信しました。');
    }
  } catch (error) {
    logger.error('😱 面接の開始に失敗しました:', error);
    await stopInterview();
    throw error;
  }
}

/**
 * 面接を停止する
 */
export async function stopInterview() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'stop' }));
    logger.info('⏹️ 面接停止の合図を送信しました。');
  }

  stopAudioStreaming();

  // サーバーからの最終評価を受け取るために、すぐには切断しない
  // disconnectWebSocket();
} 