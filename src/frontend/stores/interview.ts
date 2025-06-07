import { defineStore } from 'pinia';

/**
 * @interface StarCategory
 * @description STARの各カテゴリの評価を表すインターフェース
 * @property {number} score - 評価スコア
 * @property {string} feedback - 評価フィードバック
 */
interface StarCategory {
  score: number;
  feedback: string;
}

/**
 * @interface StarEvaluation
 * @description STAR評価全体の構造を表すインターフェース
 */
export interface StarEvaluation {
  situation: StarCategory;
  task: StarCategory;
  action: StarCategory;
  result: StarCategory;
}

/**
 * @interface InterviewState
 * @description 面談のステートを管理するためのインターフェース
 * @property {boolean} isSessionActive - 面談セッションがアクティブかどうか
 * @property {string} realtimeTranscription - リアルタイム文字起こしテキスト
 * @property {StarEvaluation | null} starEvaluation - STAR評価の結果
 * @property {WebSocket | null} websocket - WebSocketのインスタンス
 */
interface InterviewState {
  isSessionActive: boolean;
  realtimeTranscription: string;
  starEvaluation: StarEvaluation | null;
  websocket: WebSocket | null;
}

export const useInterviewStore = defineStore('interview', {
  state: (): InterviewState => ({
    isSessionActive: false,
    realtimeTranscription: '',
    starEvaluation: null,
    websocket: null,
  }),
  actions: {
    /**
     * @description WebSocket接続用のURLを生成するよん
     * @returns {string} WebSocket URL
     */
    _getWebSocketUrl(): string {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = 'localhost:8080'; // 仮のホスト
      return `${protocol}//${host}/api/speech/stream`;
    },

    /**
     * @description 面接セッションを開始し、WebSocketに接続します。
     */
    startInterviewSession() {
      if (this.websocket) {
        console.log('すでにWebSocket接続が存在します。');
        return;
      }
      
      const url = this._getWebSocketUrl();
      this.websocket = new WebSocket(url);

      this.websocket.onopen = () => {
        this.isSessionActive = true;
        console.log('✅ WebSocket接続が正常にオープンしました。');
      };

      this.websocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('📬 WebSocketメッセージ受信:', message);

          if (message.type === 'transcription') {
            this.realtimeTranscription = message.payload;
          } else if (message.type === 'star_evaluation') {
            this.starEvaluation = message.payload;
          }
        } catch (error) {
          console.error('JSONの解析中にエラーが発生しました:', error);
        }
      };

      this.websocket.onerror = (error) => {
        console.error('❌ WebSocketエラー:', error);
      };

      this.websocket.onclose = (event) => {
        console.log(`🔌 WebSocket接続がクローズされました。コード: ${event.code}, 理由: ${event.reason}`);
        this.isSessionActive = false;
        this.websocket = null;
      };
    },
    
    /**
     * @description オーディオデータをWebSocket経由で送信します。
     * @param {Blob} chunk - 送信するオーディオデータ
     */
    sendAudioChunk(chunk: Blob) {
      if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        this.websocket.send(chunk);
      } else {
        console.warn('WebSocketが接続されていないため、オーディオデータを送信できません。');
      }
    },
    
    /**
     * @description WebSocket接続を閉じます。
     */
    stopInterviewSession() {
      if (this.websocket) {
        this.websocket.close();
      }
    }
  }
}); 