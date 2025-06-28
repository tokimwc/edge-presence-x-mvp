<script setup lang="ts">
import { Splitpanes, Pane } from 'splitpanes';
import 'splitpanes/dist/splitpanes.css';
import InterviewControls from './InterviewControls.vue';
import TranscriptionPanel from './TranscriptionPanel.vue';
import AvatarCanvas from './AvatarCanvas.vue';
import VoiceAnalyzer from './VoiceAnalyzer.vue';
import EmotionHeatmap from './EmotionHeatmap.vue';
import STARFeedback from './STARFeedback.vue';
import { useInterviewStore } from '../stores/interview';
import { onMounted, ref, watch } from 'vue';
import type { InterviewState } from '../stores/interview';

const interviewStore = useInterviewStore();

const localVideo = ref<HTMLVideoElement | null>(null);
const selectedTab = ref('transcription');

/**
 * 面接の主要な状態に基づいて、表示するべきUIコンポーネントを決定します。
 * 'idle' -> 待機画面
 * 'error' -> エラー画面
 * それ以外 -> メインの面接画面
 * @returns 'welcome' | 'room' | 'error'
 */
const currentView = ref<'welcome' | 'room' | 'error'>('welcome');

watch(
  () => interviewStore.interviewState,
  (newState: InterviewState) => {
    switch (newState) {
      case 'idle':
        currentView.value = 'welcome';
        break;
      case 'error':
        currentView.value = 'error';
        break;
      default:
        // 'starting', 'in_progress', 'evaluating', 'finished' のすべてでroomを表示
        currentView.value = 'room';
        break;
    }
  },
  { immediate: true }
);

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
  <v-container fluid class="fill-height pa-0">
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

    <!-- Error Screen -->
    <v-row
      v-else-if="currentView === 'error'"
      align="center"
      justify="center"
      class="fill-height"
    >
      <v-col cols="12" md="8" class="text-center">
         <v-icon size="64" color="error" class="mb-4">mdi-alert-circle-outline</v-icon>
         <h2 class="text-h5 font-weight-bold mb-2">
           エラーが発生しました
         </h2>
         <p v-if="interviewStore.errorMessage" class="text-red-500 mb-4">
           {{ interviewStore.errorMessage }}
         </p>
         <v-btn color="primary" @click="interviewStore.resetStore()">
           もう一度試す
         </v-btn>
       </v-col>
    </v-row>

    <!-- Pre-Interview Screen -->
    <v-row
      v-else-if="currentView === 'welcome'"
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
    <splitpanes v-else class="fill-height" style="height: 100%;">
      <!-- Left Panel: Avatar and Voice -->
      <pane min-size="40">
        <splitpanes horizontal style="height: 100%;">
          <pane class="pa-2" style="padding-bottom: 4px;">
            <v-card class="d-flex flex-column h-100" elevation="2">
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
          </pane>
          <pane size="30" min-size="20" max-size="40" class="pa-2" style="padding-top: 4px;">
            <v-card class="h-100 pa-2" elevation="2">
              <VoiceAnalyzer class="h-100" />
            </v-card>
          </pane>
        </splitpanes>
      </pane>

      <!-- Right Panel: Tabs for Info -->
      <pane min-size="30" max-size="50">
        <div class="d-flex flex-column pa-2 fill-height">
          <v-card class="flex-grow-1 d-flex flex-column" elevation="2">
            <v-overlay
              :model-value="interviewStore.interviewState === 'evaluating'"
              class="align-center justify-center"
              contained
            >
              <v-progress-circular
                color="primary"
                indeterminate
                size="64"
              ></v-progress-circular>
              <div class="text-white mt-4">AIが評価中です...</div>
            </v-overlay>

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
                  <div v-if="['in_progress', 'evaluating', 'finished'].includes(interviewStore.interviewState) && interviewStore.sentimentHistory.length > 0" class="pa-4">
                      <EmotionHeatmap />
                  </div>
                  <div v-else class="text-center text-medium-emphasis pa-8">
                      <p>面接を開始すると、ここに感情の分析結果がリアルタイムで表示されます。</p>
                  </div>
                </v-window-item>
              </v-window>
            </v-card-text>
          </v-card>
          <div class="mt-4 d-flex justify-center">
            <InterviewControls />
          </div>
        </div>
      </pane>
    </splitpanes>
  </v-container>
</template>

<style>
.splitpanes__splitter {
  background-color: #2c2c2e;
  position: relative;
}

.splitpanes__splitter:before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  transition: opacity 0.4s;
  background-color: rgba(255, 255, 255, 0.2);
  opacity: 0;
  z-index: 1;
}

.splitpanes__splitter:hover:before {
  opacity: 1;
}

.splitpanes--vertical > .splitpanes__splitter:before {
  left: -2px;
  right: -2px;
  height: 100%;
}

.splitpanes--horizontal > .splitpanes__splitter:before {
  top: -2px;
  bottom: -2px;
  width: 100%;
}
</style> 