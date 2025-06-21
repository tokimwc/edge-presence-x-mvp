<script setup lang="ts">
import { computed } from 'vue'
import { useInterviewStore } from '@/frontend/stores/interview'
import StarEvaluationCard from './StarEvaluationCard.vue'
import { marked } from 'marked'

const interviewStore = useInterviewStore()

const geminiEvaluation = computed(() => {
  const geminiEval = interviewStore.evaluations.find(
    (e) => e.type === '総合評価 (Gemini)'
  )
  if (!geminiEval || !geminiEval.feedback) {
    return null
  }
  // `feedback`は常に文字列として扱う
  return {
    ...geminiEval,
    // この時点でパースは不要。raw_evaluationをmarkedでHTMLに変換して表示する
    raw_evaluation: geminiEval.feedback,
  }
})

const formattedFeedback = computed(() => {
  if (geminiEvaluation.value?.raw_evaluation) {
    // `raw_evaluation` (string) をHTMLに変換
    return marked.parse(geminiEvaluation.value.raw_evaluation)
  }
  return '<p>フィードバックの解析に失敗しました。</p>'
})

const isLoading = computed(() => interviewStore.isEvaluating)

// A helper to get rating color based on score
const getRatingColor = (score: number) => {
  if (score >= 4) return 'green'
  if (score >= 3) return 'light-green'
  if (score >= 2) return 'orange'
  return 'red'
}
</script>

<template>
  <div class="star-feedback">
    <div v-if="isLoading" class="text-center">
      <v-progress-circular indeterminate color="primary"></v-progress-circular>
      <p class="mt-2 text-medium-emphasis">AIが評価を生成中です...</p>
    </div>
    <div v-else-if="geminiEvaluation">
      <StarEvaluationCard
        :score="geminiEvaluation.score"
        title="STARメソッド評価"
      >
        <template #feedback>
          <!-- v-htmlを使ってMarkdownをレンダリング -->
          <div
            class="prose prose-sm max-w-none"
            v-html="formattedFeedback"
          ></div>
        </template>
      </StarEvaluationCard>
    </div>
    <div v-else class="text-center text-medium-emphasis">
      <p>まだ評価はありません。</p>
      <p>面接を終了すると、ここにAIからのフィードバックが表示されます。</p>
    </div>
  </div>
</template>

<style scoped>
/* Tailwind CSSの@applyを使って、proseのスタイルを微調整 */
.prose {
  @apply text-white;
}
.prose h1,
.prose h2,
.prose h3 {
  @apply text-white font-bold;
}
.prose strong {
  @apply text-white;
}
.prose blockquote {
  @apply border-l-4 border-gray-500 pl-4 text-gray-300;
}
.prose ul > li::before {
  @apply bg-gray-400;
}
</style> 