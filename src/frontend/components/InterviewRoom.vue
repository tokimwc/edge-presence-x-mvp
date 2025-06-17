<script setup lang="ts">
import InterviewControls from './InterviewControls.vue';
import TranscriptionPanel from './TranscriptionPanel.vue';
import AvatarCanvas from './AvatarCanvas.vue';
import VoiceAnalyzer from './VoiceAnalyzer.vue';
import EmotionHeatmap from './EmotionHeatmap.vue';
import STARFeedback from './STARFeedback.vue';
import { useInterviewStore } from '../stores/interview';
import { onMounted, ref, watch } from 'vue';

const interviewStore = useInterviewStore();

const localVideo = ref<HTMLVideoElement | null>(null);
const selectedTab = ref('transcription');

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
  <v-container fluid class="fill-height">
    <!-- Connection Status -->
    <v-row
      v-if="interviewStore.connectionState !== 'connected'"
      align="center"
      justify="center"
      class="fill-height"
    >
      <v-col cols="12" md="8" class="text-center">
        <v-progress-circular
          v-if="interviewStore.connectionState === 'connecting'"
          indeterminate
          color="primary"
          size="64"
          class="mb-4"
        ></v-progress-circular>
        <h2 class="text-h5 font-weight-bold mb-2">
          {{
            interviewStore.connectionState === 'connecting'
              ? 'サーバーに接続中...'
              : 'サーバーから切断されました'
          }}
        </h2>
        <p v-if="interviewStore.errorMessage" class="text-red-500 mb-4">
          {{ interviewStore.errorMessage }}
        </p>
        <p
          v-if="
            interviewStore.connectionState === 'disconnected' ||
            interviewStore.connectionState === 'error'
          "
          class="text-medium-emphasis"
        >
          ページを再読み込みして、再接続を試みてください。
        </p>
      </v-col>
    </v-row>

    <!-- Pre-Interview Screen -->
    <v-row
      v-else-if="!interviewStore.isInterviewActive"
      align="center"
      justify="center"
      class="fill-height"
    >
      <v-col cols="12" md="6">
        <v-card class="text-center pa-10" elevation="8">
          <v-card-title class="text-h4 font-weight-bold mb-4"
            >AI面接コーチへようこそ！</v-card-title
          >
          <v-card-text class="text-h6 text-medium-emphasis mb-8">
            準備ができたら、下のボタンを押して面接を開始してください。
          </v-card-text>
          <InterviewControls />
        </v-card>
      </v-col>
    </v-row>

    <!-- Main Interview Room -->
    <v-row v-else class="fill-height">
      <!-- Left Panel: Avatar and Voice -->
      <v-col cols="12" md="8" class="d-flex flex-column pa-2">
        <v-card class="flex-grow-1 d-flex flex-column" elevation="2">
          <div class="flex-grow-1 bg-black rounded-lg position-relative">
            <AvatarCanvas class="w-100 h-100" />
            <video
              v-if="interviewStore.localStream"
              ref="localVideo"
              class="position-absolute top-0 right-0 ma-4 w-25 aspect-video rounded shadow-lg"
              autoplay
              playsinline
              muted
            />
          </div>
        </v-card>
        <v-card class="mt-2 pa-2" elevation="2">
          <VoiceAnalyzer />
        </v-card>
      </v-col>

      <!-- Right Panel: Tabs for Info -->
      <v-col cols="12" md="4" class="d-flex flex-column pa-2">
        <v-card class="flex-grow-1 d-flex flex-column" elevation="2">
          <v-tabs v-model="selectedTab" color="primary" grow>
            <v-tab value="transcription">文字起こし</v-tab>
            <v-tab value="star">STAR評価</v-tab>
            <v-tab value="emotion">感情分析</v-tab>
          </v-tabs>
          <v-card-text class="flex-grow-1 overflow-y-auto">
            <v-window v-model="selectedTab">
              <v-window-item value="transcription">
                <TranscriptionPanel />
              </v-window-item>
              <v-window-item value="star">
                <STARFeedback />
              </v-window-item>
              <v-window-item value="emotion">
                <EmotionHeatmap />
              </v-window-item>
            </v-window>
          </v-card-text>
        </v-card>
        <div class="mt-4 d-flex justify-center">
          <InterviewControls />
        </div>
      </v-col>
    </v-row>
  </v-container>
</template> 