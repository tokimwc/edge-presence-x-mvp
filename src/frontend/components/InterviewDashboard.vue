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
          <RealtimeFeedback :realtime-transcription="store.currentTranscription" />
        </div>

        <!-- Right Column: STAR Evaluation -->
        <div class="bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 class="text-xl font-bold mb-4">STARメソッド評価</h2>
          <STARFeedback 
            v-if="starEvaluationForFeedbackComponent"
            :final-evaluation="starEvaluationForFeedbackComponent" 
          />
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="mt-8 flex justify-center space-x-4">
        <button
          @click="toggleInterview"
          :disabled="isProcessing"
          :class="[
            isInterviewInProgress 
              ? 'bg-red-500 hover:bg-red-600' 
              : 'bg-blue-500 hover:bg-blue-600',
            'text-white font-bold py-3 px-6 rounded-lg shadow-lg transition-all transform hover:scale-105 disabled:bg-gray-400 disabled:cursor-not-allowed'
          ]"
        >
          {{ buttonText }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useInterviewStore } from "../stores/interview";
import RealtimeFeedback from "./RealtimeFeedback.vue";
import STARFeedback from "./STARFeedback.vue";
import type { StarEvaluation } from "../stores/interview";

const store = useInterviewStore();

const isInterviewInProgress = computed(() => 
  ['starting', 'in_progress'].includes(store.interviewState)
);

const isProcessing = computed(() => 
  store.interviewState === 'starting' || store.interviewState === 'evaluating'
);

/**
 * Changes the interview state between starting and stopping.
 */
const toggleInterview = async () => {
  if (isInterviewInProgress.value) {
    store.stopInterview();
  } else {
    // For 'finished' or 'idle' state, start a new interview
    await store.startInterview();
  }
};

const buttonText = computed(() => {
  switch (store.interviewState) {
    case 'starting':
      return '開始中...';
    case 'in_progress':
      return '面接を終了する';
    case 'evaluating':
      return '評価中...';
    case 'finished':
      return 'もう一度面接する';
    default:
      return '面接を開始する';
  }
});

const starEvaluationForFeedbackComponent = computed(() => {
  const starEval = store.evaluations.find(e => e.type === 'STAR_EVALUATION');
  if (!starEval) return null;
  // STARFeedback expects an object with a star_evaluation property
  return { star_evaluation: starEval.data as StarEvaluation };
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