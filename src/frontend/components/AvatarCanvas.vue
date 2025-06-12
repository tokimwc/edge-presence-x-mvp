<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useInterviewStore } from '../stores/interview';
import { AvatarController } from '../vrm/AvatarController';
import { IdleAnimation } from '../../lib/vrm/IdleAnimation';
import { LipSync } from '../../lib/vrm/LipSync';
import * as THREE from 'three';

const canvasRef = ref<HTMLCanvasElement | null>(null);
const avatarError = ref<unknown | null>(null);
const emit = defineEmits(['avatar-error']);
let controller: AvatarController | null = null;
let lipSync: LipSync | null = null;
let idle: IdleAnimation | null = null;
const interviewStore = useInterviewStore();

async function init() {
  if (!canvasRef.value) return;
  controller = new AvatarController(canvasRef.value);
  try {
    await controller.load('https://cdn.jsdelivr.net/npm/@pixiv/three-vrm@2.0.0/examples/models/AliciaSolid.vrm');
    const vrm = controller.vrmModel;
    if (vrm) {
      const target = (controller as any).lookAtTarget ?? new THREE.Object3D();
      idle = new IdleAnimation(vrm, target);
      idle.start();
      lipSync = new LipSync(vrm);
    }
  } catch (e) {
    console.error('VRM load failed', e);
    avatarError.value = e;
    emit('avatar-error', e);
  }
}

function handleReset() {
  lipSync?.stop();
  idle?.stop();
  controller?.dispose();
}

onMounted(() => {
  init();
  window.addEventListener('avatar/reset', handleReset);
});

onUnmounted(() => {
  window.removeEventListener('avatar/reset', handleReset);
  handleReset();
});

watch(
  () => interviewStore.audioStream,
  (stream) => {
    if (stream && lipSync) {
      lipSync.start(stream);
    } else {
      lipSync?.stop();
    }
  }
);
</script>

<template>
  <div class="w-full h-72 md:h-full relative">
    <canvas ref="canvasRef" class="w-full h-full"></canvas>
    <div v-if="avatarError" class="absolute inset-0 flex items-center justify-center text-red-500 bg-white/80">
      Avatar failed to load
    </div>
  </div>
</template>
