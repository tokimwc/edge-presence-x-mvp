<script setup lang="ts">
import InterviewControls from './InterviewControls.vue';
import TranscriptionPanel from './TranscriptionPanel.vue';
import FeedbackPanel from './FeedbackPanel.vue';
import { useInterviewStore } from '../stores/interview';
import { onMounted } from 'vue';

const interviewStore = useInterviewStore();

// コンポーネントがマウントされたらWebSocketに接続する
onMounted(() => {
  interviewStore.connect();
});
</script>

<template>
  <div class="w-full h-full bg-white shadow-lg rounded-lg p-6">
    <div v-if="interviewStore.connectionState === 'connected'">
      <div v-if="!interviewStore.isInterviewActive">
        <div class="text-center py-20">
          <h2 class="text-2xl font-bold text-gray-700 mb-4">AI面接コーチへようこそ！</h2>
          <p class="text-gray-500 mb-8">準備ができたら、下のボタンを押して面接を開始してください。</p>
          <InterviewControls />
        </div>
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-6 h-[calc(100vh-200px)]">
        <div>
          <h2 class="text-xl font-semibold text-gray-800 mb-4">リアルタイム文字起こし</h2>
          <TranscriptionPanel />
        </div>
        <div>
          <h2 class="text-xl font-semibold text-gray-800 mb-4">AIフィードバック</h2>
          <FeedbackPanel />
        </div>
        <div class="md:col-span-2 mt-4">
          <InterviewControls />
        </div>
      </div>
    </div>
    <div v-else class="text-center py-20">
       <h2 class="text-2xl font-bold text-gray-700 mb-4">
         {{ interviewStore.connectionState === 'connecting' ? 'サーバーに接続中...' : 'サーバーから切断されました' }}
       </h2>
       <p v-if="interviewStore.errorMessage" class="text-red-500">{{ interviewStore.errorMessage }}</p>
       <p v-if="interviewStore.connectionState === 'disconnected' || interviewStore.connectionState === 'error'" class="mt-4 text-gray-500">
         ページを再読み込みして、再接続を試みてください。
       </p>
    </div>
  </div>
</template> 