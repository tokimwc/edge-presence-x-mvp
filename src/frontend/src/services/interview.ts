import logger from '@/lib/logger';
import { useInterviewStore } from '@/frontend/stores/interview';
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
  const store = useInterviewStore();

  if (audioWorkletNode) {
    audioWorkletNode.disconnect();
    audioWorkletNode = null;
    logger.info('🎤 AudioWorkletを停止しました。');
  }
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
    logger.info('🎤 MediaStreamを停止しました。');
  }
  if (audioContext && audioContext.state !== 'closed') {
    audioContext.close();
    logger.info('🎧 AudioContextをクローズしました。');
  }

  // サーバーにセッション終了を通知
  if (store.connectionState === 'connected') {
    socket?.send(JSON.stringify({ type: 'end_session' }));
    logger.info('🔌 セッション終了をサーバーに通知しました。');
  }
}

/**
 * WebSocketを切断します。
 */
function disconnectWebSocket() {
  const store = useInterviewStore();
  if (socket) {
    socket.close();
    socket = null;
    logger.info('🔌 WebSocketを切断しました。');
  }
  store.connectionState = 'disconnected';
}

/**
 * WebSocket接続を初期化し、イベントハンドラを設定します。
 * @param {string} url - 接続先のWebSocket URL
 * @param {(event: MessageEvent) => void} onMessageCallback - メッセージ受信時のコールバック
 */
function connectWebSocket(url: string, onMessageCallback: (event: MessageEvent) => void) {
  const store = useInterviewStore();

  // 既に接続されている、または接続中の場合は何もしない
  if (store.connectionState === 'connected' || store.connectionState === 'connecting') {
    logger.info(`🔌 WebSocketはすでに接続済みまたは接続中です。(状態: ${store.connectionState})`);
    return;
  }
  
  store.connectionState = 'connecting';
  logger.info(`🔌 WebSocket接続を開始します... URL: ${url}`);

  socket = new WebSocket(url);

  socket.onopen = () => {
    store.connectionState = 'connected';
    logger.info('✅ WebSocket接続が確立しました！');
  };

  socket.onmessage = onMessageCallback;

  socket.onerror = (event) => {
    logger.error('❌ WebSocketエラーが発生しました:', event);
    store.connectionState = 'disconnected';
    // 必要であれば、エラー内容をストアに保存する
    // store.setErrorMessage('WebSocketエラーが発生しました。');
  };

  socket.onclose = (event) => {
    // 意図しない切断の場合のみ'disconnected'に設定
    if (store.connectionState !== 'disconnected') {
      logger.warn(`🔌 WebSocket接続がクローズされました。Code: ${event.code}, Reason: ${event.reason}`);
      store.connectionState = 'disconnected';
    }
  };
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
    
    // const wsUrl = `ws://${window.location.hostname}:8000/ws/v1/interview`;
    const wsUrl = `wss://ep-x-backend-495003035191.asia-northeast1.run.app/ws/v1/interview`;
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
 * 面接を完全に停止し、リソースを解放します。
 */
export async function stopInterview() {
  logger.info('🛑 面接の完全停止プロセスを開始します...');
  stopAudioStreaming();
  disconnectWebSocket();
  const store = useInterviewStore();
  store.$reset(); // Piniaストアを初期状態にリセット
  logger.info('✅ 面接の全リソースを解放し、ストアをリセットしました。');
} 