<script setup lang="ts">
import { useInterviewStore } from '../stores/interview';

const interviewStore = useInterviewStore();
</script>

<template>
  <div class="bg-gray-100 border border-gray-200 rounded-lg p-4 h-full flex flex-col">
    <div class="flex-grow overflow-y-auto pr-2">
      <div v-if="interviewStore.transcriptions.length === 0" class="text-center text-gray-500 pt-10">
        <p>マイクに向かって話し始めると、ここにリアルタイムで文字起こしが表示されます。</p>
      </div>
      <div v-else>
        <div 
          v-for="(item, index) in interviewStore.transcriptions" 
          :key="item.timestamp || index"
          class="mb-2 p-2 rounded-md"
          :class="{ 'text-gray-900': item.is_final, 'text-gray-500': !item.is_final }"
        >
          {{ item.text }}
        </div>
      </div>
    </div>
  </div>
</template> 