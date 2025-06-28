<script setup lang="ts">
import { computed } from 'vue'
import { useInterviewStore, type StarEvaluation, type OverallFeedback } from '@/frontend/stores/interview'
import StarEvaluationCard from './StarEvaluationCard.vue'

const interviewStore = useInterviewStore()

const starEvaluation = computed(() => {
  const evalData = interviewStore.evaluations.find(
    (e) => e.type === 'STAR_EVALUATION'
  )
  return evalData ? (evalData.data as StarEvaluation) : null
})

const overallFeedback = computed(() => {
  const evalData = interviewStore.evaluations.find(
    (e) => e.type === 'OVERALL_FEEDBACK'
  )
  return evalData ? (evalData.data as OverallFeedback) : null
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
  <div class="star-feedback-container">
    <div v-if="isLoading" class="text-center">
      <v-progress-circular indeterminate color="primary" size="64"></v-progress-circular>
      <p class="mt-4 text-lg text-medium-emphasis">AIが評価を生成中です...</p>
    </div>
    
    <div v-else-if="starEvaluation && overallFeedback" class="evaluation-grid">
      <h2 class="grid-title">STARメソッド評価 (総合スコア: {{ overallFeedback.overall_score }}/40)</h2>
      
      <StarEvaluationCard
        title="Situation (状況)"
        :score="starEvaluation.situation.score"
        :feedback="starEvaluation.situation.feedback"
      />
      <StarEvaluationCard
        title="Task (課題)"
        :score="starEvaluation.task.score"
        :feedback="starEvaluation.task.feedback"
      />
      <StarEvaluationCard
        title="Action (行動)"
        :score="starEvaluation.action.score"
        :feedback="starEvaluation.action.feedback"
      />
      <StarEvaluationCard
        title="Result (結果)"
        :score="starEvaluation.result.score"
        :feedback="starEvaluation.result.feedback"
      />

      <div class="summary-card strengths">
        <h3 class="summary-title">👍 よかった点 (Strengths)</h3>
        <ul>
          <li v-for="(item, index) in overallFeedback.strengths" :key="index">
            {{ item }}
          </li>
        </ul>
        <p v-if="!overallFeedback.strengths || overallFeedback.strengths.length === 0">
          今回は特にありませんでした。
        </p>
      </div>

      <div class="summary-card improvements">
        <h3 class="summary-title">🚀 改善点 (Suggestions)</h3>
        <ul>
          <li v-for="(item, index) in overallFeedback.improvement_suggestions" :key="index">
            {{ item }}
          </li>
        </ul>
      </div>
    </div>

    <div v-else class="text-center text-medium-emphasis mt-10">
      <p>まだ評価はありません。</p>
      <p>面接を終了すると、ここにAIからのフィードバックが表示されます。</p>
    </div>
  </div>
</template>

<style scoped>
.star-feedback-container {
  padding: 1.5rem;
}

.evaluation-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
}

.grid-title {
  grid-column: 1 / -1;
  font-size: 1.8rem;
  font-weight: bold;
  margin-bottom: 1rem;
  color: #FFFFFF;
  text-align: center;
}

.summary-card {
  grid-column: 1 / -1;
  padding: 1.5rem;
  border-radius: 8px;
  background-color: #2E2E2E;
}

.summary-title {
  font-size: 1.2rem;
  font-weight: bold;
  margin-bottom: 1rem;
}

.summary-card ul {
  padding-left: 1.5rem;
  list-style-type: disc;
}

.summary-card li {
  margin-bottom: 0.5rem;
}
</style> 