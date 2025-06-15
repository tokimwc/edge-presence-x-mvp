<script setup lang="ts">
import InterviewControls from './InterviewControls.vue';
import TranscriptionPanel from './TranscriptionPanel.vue';
import FeedbackPanel from './FeedbackPanel.vue';
import AvatarCanvas from './AvatarCanvas.vue';
import { useInterviewStore } from '../stores/interview';
import { onMounted, ref, watch } from 'vue';

const interviewStore = useInterviewStore();

const localVideo = ref<HTMLVideoElement | null>(null);

watch(
  () => interviewStore.localStream,
  (s) => {
    if (s && localVideo.value) {
      localVideo.value.srcObject = s;
    }
  }
);

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
      <div v-else>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 h-[calc(100vh-140px)]">
          <div class="relative md:col-span-3 flex items-center justify-center bg-black rounded-lg">
            <AvatarCanvas class="w-full h-full" />
            <video
              v-if="interviewStore.localStream"
              ref="localVideo"
              class="absolute top-4 right-4 w-40 aspect-video rounded shadow-lg border-2 border-white"
              autoplay
              playsinline
              muted
            />
          </div>
          <div class="md:col-span-1 flex flex-col h-full overflow-hidden">
            <div class="flex-1 overflow-y-auto space-y-6">
              <TranscriptionPanel />
              <FeedbackPanel />
            </div>
          </div>
          <div class="md:col-span-4 mt-4 flex justify-center">
            <InterviewControls />
          </div>
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