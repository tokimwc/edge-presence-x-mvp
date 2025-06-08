<template>
  <div class="min-h-screen bg-gray-900 text-gray-200 p-8">
    <div class="max-w-7xl mx-auto">
      <h1 class="text-3xl font-bold text-center mb-10 tracking-wider">
        AI Interview Coach ✨
      </h1>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
        <!-- Left Column: Real-time Feedback -->
        <div class="bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 class="text-xl font-bold mb-4">リアルタイムフィードバック</h2>
          <RealtimeFeedback :realtime-transcription="store.realtimeTranscription" />
        </div>

        <!-- Right Column: STAR Evaluation -->
        <div class="bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 class="text-xl font-bold mb-4">STARメソッド評価</h2>
          <Transition name="fade">
            <StarEvaluationCard
              v-if="store.starEvaluation"
              :evaluation="store.starEvaluation"
            />
          </Transition>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="mt-8 flex justify-center space-x-4">
        <button
          @click="toggleRecording"
          :disabled="isProcessing"
          :class="[
            store.isSessionActive 
              ? 'bg-red-500 hover:bg-red-600' 
              : 'bg-blue-500 hover:bg-blue-600',
            'text-white font-bold py-3 px-6 rounded-lg shadow-lg transition-all transform hover:scale-105 disabled:bg-gray-400 disabled:cursor-not-allowed'
          ]"
        >
          {{ store.isSessionActive ? '面接を終了する' : '面接を開始する' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, computed, watch } from "vue";
import { useInterviewStore } from "../stores/interview";
import RealtimeFeedback from "./RealtimeFeedback.vue";
import StarEvaluationCard from "./StarEvaluationCard.vue";
import { MicrophoneIcon } from "@heroicons/vue/24/solid";

const store = useInterviewStore();

const mediaRecorder = ref<MediaRecorder | null>(null);
const localStream = ref<MediaStream | null>(null);
const isProcessing = ref(false);

/**
 * @description 面接の開始・停止を切り替えます。
 */
const toggleRecording = async () => {
  isProcessing.value = true;

  if (store.isSessionActive) {
    // --- 面接を停止 ---
    if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
      mediaRecorder.value.stop();
    }
    // `mediaRecorder.stop()`がトリガーするoncloseイベントで
    // 関連リソースのクリーンアップはPiniaストア側で行われる
  } else {
    // --- 面接を開始 ---
    try {
      store.realtimeTranscription = '';
      store.starEvaluation = null;

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localStream.value = stream;

      const mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        alert(`お使いのブラウザは ${mimeType} 形式に対応していません。`);
        isProcessing.value = false;
        return;
      }
      
      mediaRecorder.value = new MediaRecorder(stream, { mimeType });

      mediaRecorder.value.ondataavailable = (event) => {
        if (event.data.size > 0) {
          store.sendAudioChunk(event.data);
        }
      };
      
      // PiniaストアにWebSocket接続を開始させる
      store.startInterviewSession();

    } catch (err) {
      console.error('マイクへのアクセス中にエラーが発生しました:', err);
      alert('マイクの使用が許可されなかったか、デバイスが見つかりませんでした。');
      isProcessing.value = false;
    }
  }
};

// isSessionActive の状態を監視して後処理を行う
watch(() => store.isSessionActive, (isActive, wasActive) => {
  if (isActive) {
    // セッションが開始されたら録音を開始
    mediaRecorder.value?.start(1000); // 1秒ごとにチャンクを生成
    isProcessing.value = false;
  } else if (wasActive && !isActive) {
    // セッションが終了したらストリームをクリーンアップ
    if (localStream.value) {
      localStream.value.getTracks().forEach(track => track.stop());
      localStream.value = null;
    }
    mediaRecorder.value = null;
    isProcessing.value = false;
    console.log('録音セッションが正常に終了し、リソースがクリーンアップされました。');
  }
});

/**
 * @description コンポーネントがアンマウントされるときにセッションをクリーンアップします。
 */
onUnmounted(() => {
  if (store.isSessionActive) {
    if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
      mediaRecorder.value.stop();
    }
  }
});
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.7s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style> 