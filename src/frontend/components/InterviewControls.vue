<script setup lang="ts">
import { computed } from 'vue';
import { PlayIcon, StopIcon, ArrowPathIcon, ArrowUturnLeftIcon } from '@heroicons/vue/24/solid';
import { useInterviewStore } from '../stores/interview';
import type { InterviewState } from '../stores/interview';

const interviewStore = useInterviewStore();

const buttonState = computed<{
  text: string;
  icon: any;
  action: () => void;
  disabled: boolean;
  class: string;
}>(() => {
  const state: InterviewState = interviewStore.interviewState;
  
  switch (state) {
    case 'in_progress':
      return {
        text: '面接を終了する',
        icon: StopIcon,
        action: () => interviewStore.stopInterview(),
        disabled: false,
        class: 'bg-red-600 hover:bg-red-700 focus:ring-red-500',
      };
    case 'evaluating':
      return {
        text: '評価中...',
        icon: ArrowPathIcon,
        action: () => {},
        disabled: true,
        class: 'bg-gray-400 cursor-not-allowed',
      };
    case 'finished':
      return {
        text: 'もう一度面接する',
        icon: PlayIcon,
        action: () => interviewStore.startInterview(),
        disabled: false,
        class: 'bg-indigo-600 hover:bg-indigo-700 focus:ring-indigo-500',
      };
    case 'starting':
       return {
        text: '開始中...',
        icon: ArrowPathIcon,
        action: () => {},
        disabled: true,
        class: 'bg-gray-400 cursor-not-allowed',
      };
    case 'idle':
    default:
      return {
        text: '面接を開始する',
        icon: PlayIcon,
        action: () => interviewStore.startInterview(),
        disabled: false,
        class: 'bg-indigo-600 hover:bg-indigo-700 focus:ring-indigo-500',
      };
  }
});
</script>

<template>
  <div class="flex items-center justify-center">
    <button
      @click="buttonState.action"
      :disabled="buttonState.disabled"
      type="button"
      :class="[
        'inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md shadow-sm text-white focus:outline-none focus:ring-2 focus:ring-offset-2 transition-transform duration-200 ease-in-out',
        buttonState.class,
        buttonState.disabled ? '' : 'hover:scale-105'
      ]"
    >
      <component :is="buttonState.icon" :class="['h-6 w-6 mr-3', { 'animate-spin': buttonState.text.includes('中') }]" />
      {{ buttonState.text }}
    </button>
  </div>
</template> 