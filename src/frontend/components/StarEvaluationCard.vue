<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 w-full">
    <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-4">STARメソッド評価</h2>
    <div v-if="evaluation" class="space-y-4">
      <div v-for="(item, key) in evaluation" :key="key" class="border-b border-gray-200 dark:border-gray-700 pb-4 last:border-b-0 last:pb-0">
        <div class="flex justify-between items-center">
          <h3 class="text-lg font-semibold capitalize text-gray-800 dark:text-gray-200">{{ key }}</h3>
          <span
            :class="getScoreColor(item.score)"
            class="text-sm font-bold px-2.5 py-0.5 rounded-full"
            data-testid="score-badge"
          >
            {{ item.score.toFixed(1) }}
          </span>
        </div>
        <p class="text-gray-600 dark:text-gray-400 mt-2">{{ item.feedback }}</p>
      </div>
    </div>
    <div v-else class="text-center text-gray-500 dark:text-gray-400 py-8">
      <p>評価データがまだありません。<br>面接が終了すると、ここに結果が表示されます。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

/**
 * @interface StarCategory
 * @description STARの各カテゴリの評価を表すインターフェース
 * @property {number} score - 評価スコア
 * @property {string} feedback - 評価フィードバック
 */
interface StarCategory {
  score: number;
  feedback: string;
}

/**
 * @interface StarEvaluation
 * @description STAR評価全体の構造を表すインターフェース
 */
interface StarEvaluation {
  situation: StarCategory;
  task: StarCategory;
  action: StarCategory;
  result: StarCategory;
}

const props = defineProps<{
  evaluation: StarEvaluation | null;
}>();

/**
 * @description スコアに基づいてTailwind CSSのクラスを返す関数
 * @param {number} score - 評価スコア
 * @returns {string} Tailwind CSSのクラス文字列
 */
const getScoreColor = (score: number): string => {
  if (score >= 8.5) {
    return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
  } else if (score >= 6.5) {
    return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
  } else {
    return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300';
  }
};
</script>

<style scoped>
/* スタイルが必要な場合はここに追加 */
</style> 