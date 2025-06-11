<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useInterviewStore } from '../stores/interview';
import { AvatarController } from '../vrm/AvatarController';

const canvasRef = ref<HTMLCanvasElement | null>(null);
let controller: AvatarController | null = null;
const interviewStore = useInterviewStore();

function init() {
  if (canvasRef.value) {
    controller = new AvatarController(canvasRef.value);
    // デモ用のモデルURL。実環境では任意のVRMに変更してね！
    controller.load('https://cdn.jsdelivr.net/npm/@pixiv/three-vrm@2.0.0/examples/models/AliciaSolid.vrm');
  }
}

onMounted(() => {
  init();
});

onUnmounted(() => {
  controller?.dispose();
});

watch(
  () => interviewStore.audioStream,
  (stream) => {
    if (stream) {
      controller?.startLipSync(stream);
    } else {
      controller?.stopLipSync();
    }
  }
);
</script>

<template>
  <canvas ref="canvasRef" class="w-full h-72 md:h-full"></canvas>
</template>
