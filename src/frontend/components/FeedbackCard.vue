<script setup lang="ts">
import { FunctionalComponent } from 'vue';

defineProps<{
  title: string;
  icon: FunctionalComponent;
}>();
</script>

<template>
  <div class="border border-gray-200 rounded-lg p-4">
    <div class="flex items-center mb-2">
      <component :is="icon" class="h-6 w-6 text-indigo-500 mr-2" />
      <h4 class="text-md font-semibold text-gray-800">{{ title }}</h4>
    </div>
    <div class="text-sm text-gray-600">
      <slot></slot>
    </div>
  </div>
</template> 