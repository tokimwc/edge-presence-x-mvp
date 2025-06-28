<script setup lang="ts">
import { useInterviewStore } from '../stores/interview';
import { storeToRefs } from 'pinia';

const interviewStore = useInterviewStore();
const { transcriptions, currentTranscription } = storeToRefs(interviewStore);
</script>

<template>
  <div class="transcription-panel">
    <!-- 過去の確定した文字起こしを表示 -->
    <div v-if="transcriptions.length > 0" class="past-transcriptions">
      <p v-for="(item, index) in transcriptions" :key="index" class="final-text">
        {{ item.text }}
      </p>
    </div>

    <!-- 現在のリアルタイム文字起こしを表示 -->
    <p class="realtime-text">
      {{ currentTranscription }}
      <span class="cursor"></span>
    </p>
  </div>
</template>

<style scoped>
.transcription-panel {
  padding: 1rem;
  font-size: 1.1rem;
  line-height: 1.8;
  color: #E0E0E0;
  height: 100%;
  overflow-y: auto;
}

.past-transcriptions {
  color: #9E9E9E; /* 少し色を薄くする */
  margin-bottom: 1rem;
}

.final-text {
  margin-bottom: 0.5rem;
}

.realtime-text {
  color: #FFFFFF; /* 現在の行は白で見やすく */
  font-weight: 500;
  min-height: 2rem; /* カーソルがガタガタしないように高さを確保 */
}

/* 点滅するカーソル */
.cursor {
  display: inline-block;
  width: 8px;
  height: 1.2rem;
  background-color: #4CAF50;
  animation: blink 1s step-end infinite;
  vertical-align: middle;
  margin-left: 4px;
}

@keyframes blink {
  from, to {
    background-color: transparent;
  }
  50% {
    background-color: #4CAF50;
  }
}
</style> 