<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-4 sm:p-6 lg:p-8">
    <div class="max-w-7xl mx-auto">
      <h1 class="text-2xl font-bold text-center mb-6">AI面接コーチング</h1>
      
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Left Column: Real-time Feedback -->
        <div class="flex flex-col">
          <RealtimeFeedback />
        </div>

        <!-- Right Column: STAR Evaluation -->
        <div class="flex flex-col">
          <StarEvaluationCard />
        </div>
      </div>

      <!-- Action Button -->
      <div class="mt-8 flex justify-center">
        <button
          @click="startInterview"
          class="bg-blue-500 hover:bg-blue-600 text-white font-bold py-3 px-6 rounded-lg shadow-lg transition-transform transform hover:scale-105"
        >
          面接を開始する
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import RealtimeFeedback from './RealtimeFeedback.vue';
import StarEvaluationCard from './StarEvaluationCard.vue';
import { ref } from 'vue';

const isRecording = ref(false);
const mediaRecorder = ref<MediaRecorder | null>(null);
const webSocket = ref<WebSocket | null>(null);

/**
 * @description WebSocket接続用のURLを生成するよん
 * @returns {string} WebSocket URL
 */
const getWebSocketUrl = (): string => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/api/speech/stream`;
};

/**
 * @description オーディオストリーミングを開始するよ
 */
const startStreaming = async () => {
  if (isRecording.value) {
    console.log('すでに録音中だよ！');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    const mimeType = 'audio/webm;codecs=opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      alert(`ブラウザが ${mimeType} に対応してないみたい…😢`);
      return;
    }

    mediaRecorder.value = new MediaRecorder(stream, { mimeType });
    webSocket.value = new WebSocket(getWebSocketUrl());

    webSocket.value.onopen = () => {
      console.log('WebSocket接続がオープンしたよ！設定を送るね！');
      const session_id = crypto.randomUUID(); // 仮のセッションID
      const audioContext = new AudioContext();
      const configMessage = {
        type: 'config',
        data: {
          session_id,
          audio_config: {
            sample_rate: audioContext.sampleRate,
            encoding: 'opus',
            // 他のAPIで要求される設定があればここに追加
          }
        }
      };
      webSocket.value?.send(JSON.stringify(configMessage));

      mediaRecorder.value?.start(500); // 500msごとにデータを取得
    };

    mediaRecorder.value.ondataavailable = (event) => {
      if (event.data.size > 0 && webSocket.value?.readyState === WebSocket.OPEN) {
        webSocket.value.send(event.data);
      }
    };

    webSocket.value.onmessage = (event) => {
      console.log('サーバーからメッセージ受信:', event.data);
      // TODO: ここで文字起こし結果をUIに反映する処理を書く
    };

    webSocket.value.onerror = (error) => {
      console.error('WebSocketでエラー発生！', error);
      alert('WebSocket接続でエラーが起きたみたい…😭');
    };

    webSocket.value.onclose = () => {
      console.log('WebSocket接続がクローズされたよ');
    };

    isRecording.value = true;

  } catch (err) {
    console.error('マイクへのアクセスでエラーが出たよ', err);
    alert('マイクの使用が許可されなかったか、デバイスが見つからなかったみたい…😢');
  }
};

/**
 * @description 面接セッションを開始します。
 * 今はコンソールにメッセージを出すだけだよん！
 */
const startInterview = () => {
  console.log('面接開始ボタンがクリックされたよ！マイクの許可とかセッション開始ロジックはここから！');
  startStreaming();
};
</script>

<style scoped>
/* Scopedスタイルが必要な場合はここに追加 */
</style> 