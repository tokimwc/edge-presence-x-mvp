import { setActivePinia, createPinia } from 'pinia';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useInterviewStore } from '../interview';

// --- ここがキモ！WebSocketをモック(ニセモノに)するよ！ ---
const mockSocket = {
  send: vi.fn(),
  close: vi.fn(),
  onopen: vi.fn(),
  onmessage: vi.fn(),
  onerror: vi.fn(),
  onclose: vi.fn(),
  readyState: 0, // Mock initial state
};
vi.stubGlobal('WebSocket', vi.fn(() => mockSocket));
// --- モックここまで ---

describe('useInterviewStore', () => {
  beforeEach(() => {
    // 各テストの前にPiniaを初期化するお作法
    setActivePinia(createPinia());
    // 各テストの前にモックの関数呼び出し履歴をリセット
    vi.clearAllMocks();
    // モックの状態をリセット
    mockSocket.readyState = 0;
    mockSocket.onopen = vi.fn();
    mockSocket.onmessage = vi.fn();
    mockSocket.onerror = vi.fn();
    mockSocket.onclose = vi.fn();
  });

  it('① startInterviewSessionでセッションが開始されること', () => {
    const store = useInterviewStore();
    store.startInterviewSession();

    // "open"イベントを偽装して発火！
    mockSocket.onopen();

    expect(store.isSessionActive).toBe(true);
    expect(WebSocket).toHaveBeenCalledWith('ws://localhost:8080/api/speech/stream');
  });

  it('② サーバーからのメッセージを正しく処理できること', () => {
    const store = useInterviewStore();
    store.startInterviewSession();
    mockSocket.onopen(); // まずは接続

    // 偽の文字起こしデータをサーバーから受信したフリ！
    const transcriptionMessage = { type: 'transcription', payload: 'こんにちは' };
    mockSocket.onmessage({ data: JSON.stringify(transcriptionMessage) });
    expect(store.realtimeTranscription).toBe('こんにちは');

    // 偽のSTAR評価データをサーバーから受信したフリ！
    const evaluationMessage = {
      type: 'star_evaluation',
      payload: { situation: { score: 9.0, feedback: '完璧！' } },
    };
    mockSocket.onmessage({ data: JSON.stringify(evaluationMessage) });
    expect(store.starEvaluation).toEqual(evaluationMessage.payload);
  });

  it('③ WebSocketが閉じたらセッションが終了すること', () => {
    const store = useInterviewStore();
    store.startInterviewSession();
    mockSocket.onopen(); // 一旦セッション開始

    // "close"イベントを偽装して発火！
    mockSocket.onclose({ code: 1000, reason: 'Test complete' });

    expect(store.isSessionActive).toBe(false);
    expect(store.websocket).toBeNull();
  });
}); 