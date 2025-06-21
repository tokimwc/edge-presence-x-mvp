<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 w-full">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-xl font-bold text-gray-900 dark:text-white">{{ title }}</h2>
       <span
        v-if="score"
        :class="getScoreColor(score)"
        class="text-sm font-bold px-2.5 py-0.5 rounded-full"
        data-testid="score-badge"
      >
        {{ score.toFixed(0) }} / 100
      </span>
    </div>
    <div class="prose prose-sm max-w-none dark:prose-invert">
      <slot name="feedback">
        <p class="text-gray-500 dark:text-gray-400">フィードバックはありません。</p>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  title: string;
  score: number | null;
}>();

/**
 * @description スコアに基づいてTailwind CSSのクラスを返す関数
 * @param {number} score - 評価スコア (0-100)
 * @returns {string} Tailwind CSSのクラス文字列
 */
const getScoreColor = (score: number | null): string => {
  if (score === null) return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
  if (score >= 80) {
    return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
  } else if (score >= 60) {
    return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
  } else {
    return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300';
  }
};
</script>

<style scoped>
.prose-invert {
  --tw-prose-body: theme(colors.gray.300);
  --tw-prose-headings: theme(colors.white);
  --tw-prose-lead: theme(colors.gray.400);
  --tw-prose-links: theme(colors.white);
  --tw-prose-bold: theme(colors.white);
  --tw-prose-counters: theme(colors.gray.400);
  --tw-prose-bullets: theme(colors.gray.600);
  --tw-prose-hr: theme(colors.gray.700);
  --tw-prose-quotes: theme(colors.gray.100);
  --tw-prose-quote-borders: theme(colors.gray.700);
  --tw-prose-captions: theme(colors.gray.400);
  --tw-prose-code: theme(colors.white);
  --tw-prose-pre-code: theme(colors.gray.300);
  --tw-prose-pre-bg: theme(colors.gray.900);
  --tw-prose-th-borders: theme(colors.gray.600);
  --tw-prose-td-borders: theme(colors.gray.700);
}
</style> 