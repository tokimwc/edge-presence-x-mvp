<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { useInterviewStore } from '@/frontend/stores/interview';
import { AvatarController } from '@/frontend/vrm/AvatarController';
import { IdleAnimation } from '@/lib/vrm/IdleAnimation';
import { LipSync } from '@/lib/vrm/LipSync';
import logger from '@/lib/logger';

const containerRef = ref<HTMLDivElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const avatarError = ref<unknown | null>(null);
const emit = defineEmits(['avatar-error']);
let controller: AvatarController | null = null;
let lipSync: LipSync | null = null;
let idle: IdleAnimation | null = null;
const interviewStore = useInterviewStore();

const init = async () => {
  if (containerRef.value && !controller) {
    controller = new AvatarController(containerRef.value);
    try {
      await controller.load('/Limone.vrm');
      logger.info('🤖 VRMモデルの読み込みと初期化が完了しました。');

      const vrm = controller.vrmModel;
      if (vrm) {
        lipSync = new LipSync(vrm);
        const target = (controller as any).lookAtTarget;
        idle = new IdleAnimation(vrm, target);
        
        // 🔥 重要：IdleAnimation開始前にポーズ設定！
        await setInitialPose();
        
        // 🚨 IdleAnimationを停止してポーズが上書きされないようにする
        // idle.start();
      }
    } catch (error) {
      logger.error('😱 VRMの読み込みに失敗しました:', error);
      avatarError.value = error;
      emit('avatar-error', error);
    }
  }
};

// 🎯 初期ポーズ設定を関数化
const setInitialPose = async () => {
  if (!controller) return;
  
  // 少し待ってからポーズ設定（VRMの完全初期化を待つ）
  await new Promise(resolve => setTimeout(resolve, 100));
  
  // 両腕を下げるためのより大きな回転値
  controller.setPose({
    // 右腕を下げる（Z軸回転をもっと大きく）
    rightUpperArm: { rotation: [0.0, 0.0, -0.5, 0.866] }, // 約60度下向き
    leftUpperArm: { rotation: [0.0, 0.0, 0.5, 0.866] },   // 約60度下向き
    
    // 肘も少し調整（オプション）
    rightLowerArm: { rotation: [0.0, 0.0, 0.1, 0.995] },
    leftLowerArm: { rotation: [0.0, 0.0, -0.1, 0.995] },
  });
  
  logger.info('✨ 初期ポーズ設定完了！両腕下げポーズにしたよ〜');
};

const triggerFileInput = () => {
  fileInputRef.value?.click();
};

const onFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (target.files && target.files[0]) {
    const file = target.files[0];
    const reader = new FileReader();
    reader.onload = (e) => {
      const imageUrl = e.target?.result as string;
      if (imageUrl && controller) {
        controller.setBackground(imageUrl);
      }
    };
    reader.readAsDataURL(file);
  }
};

function handleReset() {
  lipSync?.stop();
  idle?.stop();
  controller?.dispose();
}

const resize = () => {
  if (!controller) return;
  nextTick(() => {
    const container = containerRef.value;
    if (container && controller) {
      controller.resize();
    }
  });
};

defineExpose({
    resize
});

onMounted(() => {
  init();
  window.addEventListener('avatar/reset', handleReset);
});

onUnmounted(() => {
  window.removeEventListener('avatar/reset', handleReset);
  lipSync?.stop();
  idle?.stop();
  controller?.dispose();
  controller = null;
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
  <div ref="containerRef" class="avatar-canvas-container relative">
    <!-- Canvas is now injected by AvatarController -->
    <div class="absolute top-2 right-2 z-10">
      <v-tooltip text="背景を変更" location="bottom">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            icon="mdi-image-plus-outline"
            density="comfortable"
            variant="tonal"
            @click="triggerFileInput"
          />
        </template>
      </v-tooltip>
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*"
        class="hidden"
        @change="onFileChange"
      />
    </div>
    <div
      v-if="avatarError"
      class="absolute inset-0 flex items-center justify-center text-red-500 bg-white/80 z-10"
    >
      Avatar failed to load
    </div>
  </div>
</template>

<style scoped>
.avatar-canvas-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background-color: #000;
}
</style>
