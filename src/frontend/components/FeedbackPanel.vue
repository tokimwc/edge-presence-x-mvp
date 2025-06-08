<script setup lang="ts">
import FeedbackCard from './FeedbackCard.vue';
import { useInterviewStore } from '../stores/interview';
import { ChartBarIcon, StarIcon, ChatBubbleBottomCenterTextIcon } from '@heroicons/vue/24/outline';

const interviewStore = useInterviewStore();

// アイコンを動的に返すヘルパー関数
function getIconForEvaluation(type: string) {
  switch (type) {
    case 'star_method':
      return StarIcon;
    case 'sentiment_analysis':
      return ChatBubbleBottomCenterTextIcon;
    case 'pitch_analysis':
      return ChartBarIcon;
    default:
      return StarIcon; // デフォルトアイコン
  }
}
</script>

<template>
  <div class="bg-gray-100 border border-gray-200 rounded-lg p-4 h-full flex flex-col">
    <div class="flex-grow overflow-y-auto pr-2 space-y-4">
      <div v-if="interviewStore.evaluations.length === 0" class="text-center text-gray-500 pt-10">
        <p>面接を終了すると、ここにAIによる評価が表示されます。</p>
      </div>
      <div v-else>
        <FeedbackCard 
          v-for="(evaluation, index) in interviewStore.evaluations"
          :key="index"
          :title="evaluation.type"
          :icon="getIconForEvaluation(evaluation.type)"
        >
          <p>{{ evaluation.feedback }}</p>
          <div v-if="evaluation.score" class="mt-2 font-semibold">
            <p>スコア: {{ evaluation.score }} / 5</p>
          </div>
        </FeedbackCard>
      </div>
    </div>
  </div>
</template> 