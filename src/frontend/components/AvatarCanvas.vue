<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useInterviewStore } from '@/frontend/stores/interview';
import { AvatarController } from '@/frontend/vrm/AvatarController';
import { IdleAnimation } from '@/lib/vrm/IdleAnimation';
import { LipSync } from '@/lib/vrm/LipSync';
import * as THREE from 'three';
import logger from '@/lib/logger';

const canvasRef = ref<HTMLCanvasElement | null>(null);
const avatarError = ref<unknown | null>(null);
const emit = defineEmits(['avatar-error']);
let controller: AvatarController | null = null;
let lipSync: LipSync | null = null;
let idle: IdleAnimation | null = null;
const interviewStore = useInterviewStore();
const clock = new THREE.Clock();

const init = async () => {
  if (canvasRef.value && !controller) {
    controller = new AvatarController(canvasRef.value);
    try {
      await controller.load('https://pixiv.github.io/three-vrm/models/VRM1_Alicia_Solid.vrm');
      logger.info('🤖 VRMモデルの読み込みと初期化が完了しました。');
      const vrm = controller.vrmModel;
      if (vrm) {
        const target = (controller as any).lookAtTarget ?? new THREE.Object3D();
        idle = new IdleAnimation(vrm, target);
        idle.start();
        lipSync = new LipSync(vrm);

        const animate = () => {
          requestAnimationFrame(animate);
          const delta = clock.getDelta();

          if (vrm) {
            // 瞬きの値を計算 (たまに1に近づくように)
            const blinkValue = Math.sin(Math.PI * (clock.elapsedTime % 1.0)) ** 4;
            vrm.expressionManager?.setValue('blink', blinkValue);

            // VRMモデルの状態を更新
            vrm.update(delta);
          }
        };
        animate();
      }
    } catch (error) {
      logger.error('😱 VRMの読み込みに失敗しました:', error);
      avatarError.value = error;
      emit('avatar-error', error);
    }
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
