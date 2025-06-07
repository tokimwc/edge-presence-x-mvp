<template>
  <div class="bg-gray-800 p-6 rounded-lg shadow-inner h-full">
    <h3 class="text-lg font-semibold text-white mb-4">リアルタイムフィードバック</h3>
    <div class="text-gray-300 whitespace-pre-wrap">{{ realtimeTranscription }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  realtimeTranscription: string;
}>();
</script>

<style scoped>
/* スタイルが必要な場合はここに追加 */
</style> 