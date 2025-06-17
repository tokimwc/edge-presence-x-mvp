<script setup lang="ts">
import { computed } from 'vue'
import { useInterviewStore } from '@/frontend/stores/interview'

const interviewStore = useInterviewStore()

// The raw evaluation from Gemini might be a stringified JSON.
// This computed property parses it and returns the structured feedback.
const starFeedback = computed(() => {
  const feedbackEvaluation = interviewStore.evaluations.find(
    e => e.type === '総合評価 (Gemini)'
  )

  if (!feedbackEvaluation || !feedbackEvaluation.feedback) {
    return null
  }

  try {
    // Assuming the feedback string is a JSON object with STAR details
    // The format from backend might be { situation: { score: 4, feedback: "..." }, ... }
    const parsedFeedback = JSON.parse(feedbackEvaluation.feedback)
    // Let's just return the parsed object for now.
    // The template will handle the structure.
    return parsedFeedback
  } catch (error) {
    console.error('Failed to parse STAR feedback JSON:', error)
    // If parsing fails, return the raw string to display it as is.
    return { raw: feedbackEvaluation.feedback }
  }
})

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
    <v-card v-if="starFeedback" variant="tonal">
      <v-card-title>STARメソッド評価</v-card-title>
      <v-card-text>
        <div v-if="starFeedback.raw">
          <p class="font-weight-bold">フィードバック:</p>
          <pre class="feedback-text">{{ starFeedback.raw }}</pre>
        </div>
        <div v-else>
          <v-list lines="three" bg-color="transparent">
            <template
              v-for="(item, key) in starFeedback"
              :key="key"
            >
              <v-list-item v-if="item && typeof item === 'object'">
                <v-list-item-title class="font-weight-bold text-uppercase">{{ key }}</v-list-item-title>
                <v-list-item-subtitle class="feedback-text">{{ item.feedback }}</v-list-item-subtitle>
                <template v-slot:append>
                  <div class="d-flex flex-column align-center">
                    <v-rating
                      :model-value="item.score"
                      :color="getRatingColor(item.score)"
                      density="compact"
                      readonly
                      half-increments
                    ></v-rating>
                    <span class="text-caption">{{ item.score }} / 5</span>
                  </div>
                </template>
              </v-list-item>
            </template>
          </v-list>
        </div>
      </v-card-text>
    </v-card>
    <div v-else class="text-center text-medium-emphasis pa-8">
      <p>面接が終了すると、ここにAIからのフィードバックが表示されます。</p>
    </div>
  </div>
</template>

<style scoped>
.feedback-text {
  white-space: pre-wrap; /* Ensures line breaks are respected */
  font-family: 'M PLUS 1p', sans-serif;
}
pre {
  background-color: rgba(0,0,0,0.1);
  padding: 1rem;
  border-radius: 4px;
}
</style> 