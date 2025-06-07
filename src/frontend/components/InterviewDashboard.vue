<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-4 sm:p-6 lg:p-8">
    <div class="max-w-7xl mx-auto">
      <h1 class="text-2xl font-bold text-center mb-6">AI面接コーチング</h1>
      
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Left Column: Real-time Feedback -->
        <div class="flex flex-col">
          <RealtimeFeedback :realtime-transcription="store.realtimeTranscription" />
        </div>

        <!-- Right Column: STAR Evaluation -->
        <div class="flex flex-col">
          <StarEvaluationCard v-if="store.starEvaluation" :evaluation="store.starEvaluation" />
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="mt-8 flex justify-center space-x-4">
        <button
          @click="handleStartInterview"
          :disabled="store.isSessionActive"
          class="bg-blue-500 hover:bg-blue-600 text-white font-bold py-3 px-6 rounded-lg shadow-lg transition-transform transform hover:scale-105 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          面接を開始する
        </button>
        <button
          v-if="store.isSessionActive"
          @click="handleStopInterview"
          class="bg-red-500 hover:bg-red-600 text-white font-bold py-3 px-6 rounded-lg shadow-lg transition-transform transform hover:scale-105"
        >
          面接を終了する
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import RealtimeFeedback from './RealtimeFeedback.vue';
import StarEvaluationCard from './StarEvaluationCard.vue';
import { ref, onUnmounted } from 'vue';
import { useInterviewStore } from '../stores/interview';

const store = useInterviewStore();

const mediaRecorder = ref<MediaRecorder | null>(null);
const localStream = ref<MediaStream | null>(null);

/**
 * @description マイクからの音声ストリーミングを開始し、WebSocket経由で送信します。
 */
const startStreaming = async () => {
  if (store.isSessionActive) {
    console.log('すでにセッションが開始されています。');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    localStream.value = stream;
    
    const mimeType = 'audio/webm;codecs=opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      alert(`お使いのブラウザは ${mimeType} 形式に対応していません。`);
      return;
    }

    mediaRecorder.value = new MediaRecorder(stream, { mimeType });
    
    mediaRecorder.value.ondataavailable = (event) => {
      if (event.data.size > 0) {
        store.sendAudioChunk(event.data);
      }
    };

    // WebSocket接続が確立されたら録音を開始
    const unsubscribe = store.$onAction(({ name, after }) => {
      if (name === 'startInterviewSession') {
        after(() => {
          if(store.isSessionActive) {
            mediaRecorder.value?.start(500); // 500msごとにデータを送信
          }
        });
        unsubscribe(); // 一度実行されたら監視を解除
      }
    });

  } catch (err) {
    console.error('マイクへのアクセス中にエラーが発生しました:', err);
    alert('マイクの使用が許可されなかったか、デバイスが見つかりませんでした。');
  }
};

/**
 * @description 面接セッションを開始します。
 */
const handleStartInterview = () => {
  console.log('面接開始ボタンがクリックされました。');
  store.realtimeTranscription = '';
  store.starEvaluation = null;
  store.startInterviewSession(); // WebSocket接続を開始
  startStreaming(); // マイクの準備を開始
};

/**
 * @description 面接セッションを停止します。
 */
const handleStopInterview = () => {
  console.log('面接終了ボタンがクリックされました。');
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    mediaRecorder.value.stop();
  }
  
  if (localStream.value) {
    localStream.value.getTracks().forEach(track => track.stop());
    localStream.value = null;
  }

  store.stopInterviewSession(); // WebSocket接続を閉じる

  // テスト用のダミーデータ
  store.starEvaluation = {
    situation: { score: 8.8, feedback: "具体的な状況設定が明確で、課題の背景がよく理解できました。" },
    task: { score: 7.5, feedback: "担当した役割と目標が具体的でしたが、もう少し定量的な目標設定があるとより良かったです。" },
    action: { score: 9.2, feedback: "主体的に行動し、技術的な課題解決能力の高さが伺えます。素晴らしいです。" },
    result: { score: 8.5, feedback: "プロジェクトへの貢献度が明確で、ポジティブな結果を具体的に示せています。" }
  };
};

/**
 * @description コンポーネントがアンマウントされるときにセッションをクリーンアップします。
 */
onUnmounted(() => {
  if (store.isSessionActive) {
    handleStopInterview();
  }
});
</script>

<style scoped>
/* Scopedスタイルが必要な場合はここに追加 */
</style> 