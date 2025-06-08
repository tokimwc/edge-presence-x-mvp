<script setup lang="ts">
import { PlayIcon, StopIcon, ArrowPathIcon } from '@heroicons/vue/24/solid';
import { useInterviewStore } from '../stores/interview';

const interviewStore = useInterviewStore();
</script>

<template>
  <div class="flex items-center justify-center">
    <!-- 面接開始前 -->
    <button
      v-if="!interviewStore.isInterviewActive && !interviewStore.isEvaluating"
      @click="interviewStore.startInterview()"
      type="button"
      class="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-transform duration-200 ease-in-out hover:scale-105"
    >
      <PlayIcon class="h-6 w-6 mr-3" />
      面接を開始する
    </button>

    <!-- 面接中 -->
    <button
      v-if="interviewStore.isInterviewActive && !interviewStore.isEvaluating"
      @click="interviewStore.stopInterview()"
      type="button"
      class="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md shadow-sm text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-transform duration-200 ease-in-out hover:scale-105"
    >
      <StopIcon class="h-6 w-6 mr-3" />
      面接を終了する
    </button>

    <!-- 評価中 -->
    <button
      v-if="interviewStore.isEvaluating"
      type="button"
      class="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md shadow-sm text-white bg-gray-400 cursor-not-allowed"
      disabled
    >
      <ArrowPathIcon class="animate-spin h-6 w-6 mr-3" />
      評価中...
    </button>
  </div>
</template> 