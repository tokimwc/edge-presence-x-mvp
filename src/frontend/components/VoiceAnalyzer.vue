<script setup lang="ts">
import {
  ref,
  onMounted,
  onUnmounted,
  watch,
  computed,
  nextTick,
  defineExpose,
} from 'vue'
import { useInterviewStore } from '@/frontend/stores/interview'
import { Line, Chart } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

const interviewStore = useInterviewStore()

const volume = ref(0)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)
const lineChartRef = ref<typeof Chart | null>(null)

let audioContext: AudioContext | null = null
let analyser: AnalyserNode | null = null
let source: MediaStreamAudioSourceNode | null = null
let animationFrameId: number | null = null

const pitchChartData = computed(() => {
  const labels = interviewStore.pitchHistory.map(p =>
    new Date(p.timestamp).toLocaleTimeString()
  )
  const data = interviewStore.pitchHistory.map(p => p.pitch)

  return {
    labels,
    datasets: [
      {
        label: '声の高さ (Hz)',
        backgroundColor: 'rgba(76, 175, 80, 0.2)',
        borderColor: 'rgb(76, 175, 80)',
        data: data,
        tension: 0.2,
        pointRadius: 1,
      },
    ],
  }
})

const pitchChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    y: {
      beginAtZero: false,
      title: {
        display: true,
        text: '周波数 (Hz)',
      },
    },
    x: {
      ticks: {
        maxTicksLimit: 10,
      }
    }
  },
  plugins: {
    legend: {
      display: false,
    },
  },
}

/**
 * Draws the voice waveform on the canvas.
 */
function drawWaveform() {
  if (!analyser || !canvasRef.value) return

  const canvas = canvasRef.value
  const canvasCtx = canvas.getContext('2d')
  if (!canvasCtx) return

  const bufferLength = analyser.frequencyBinCount
  const dataArray = new Uint8Array(bufferLength)
  analyser.getByteTimeDomainData(dataArray)

  canvasCtx.fillStyle = 'rgb(26, 26, 26)' // background color from theme
  canvasCtx.fillRect(0, 0, canvas.width, canvas.height)
  canvasCtx.lineWidth = 2
  canvasCtx.strokeStyle = 'rgb(76, 175, 80)' // primary color from theme

  canvasCtx.beginPath()
  const sliceWidth = (canvas.width * 1.0) / bufferLength
  let x = 0

  for (let i = 0; i < bufferLength; i++) {
    const v = dataArray[i] / 128.0
    const y = (v * canvas.height) / 2

    if (i === 0) {
      canvasCtx.moveTo(x, y)
    } else {
      canvasCtx.lineTo(x, y)
    }
    x += sliceWidth
  }

  canvasCtx.lineTo(canvas.width, canvas.height / 2)
  canvasCtx.stroke()
}

/**
 * Sets up the Web Audio API components to analyze the microphone stream.
 * @param {MediaStream} stream The audio stream from the microphone.
 */
function setupAudioAnalysis(stream: MediaStream) {
  if (!audioContext) {
    audioContext = new AudioContext()
  }
  analyser = audioContext.createAnalyser()
  analyser.fftSize = 2048 // Higher FFT size for detailed waveform
  source = audioContext.createMediaStreamSource(stream)
  source.connect(analyser)

  const volumeDataArray = new Uint8Array(analyser.frequencyBinCount)

  function renderLoop() {
    if (!analyser) return
    // Volume calculation
    analyser.getByteFrequencyData(volumeDataArray)
    let sum = 0
    for (const amplitude of volumeDataArray) {
      sum += amplitude * amplitude
    }
    const rms = Math.sqrt(sum / volumeDataArray.length)
    volume.value = Math.min(100, Math.max(0, rms * 1.5))

    // Waveform drawing
    drawWaveform()

    animationFrameId = requestAnimationFrame(renderLoop)
  }

  renderLoop()
}

/**
 * Tears down the audio analysis components.
 */
function stopAudioAnalysis() {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
  source?.disconnect()
  analyser?.disconnect()
  source = null
  analyser = null
  volume.value = 0
}

function resize() {
  nextTick(() => {
    if (canvasRef.value && containerRef.value) {
      const parent = containerRef.value
      canvasRef.value.width = parent.clientWidth - 16 // pa-2
      canvasRef.value.height = 100
      drawWaveform()
    }
    lineChartRef.value?.chart.resize()
  })
}

defineExpose({
  resize,
})

watch(
  () => interviewStore.localStream,
  (newStream, oldStream) => {
    if (newStream) {
      setupAudioAnalysis(newStream)
    } else {
      stopAudioAnalysis()
    }
  },
  { immediate: true }
)

onMounted(() => {
  resize()
})

onUnmounted(() => {
  stopAudioAnalysis()
  audioContext?.close()
})
</script>

<template>
  <div ref="containerRef" class="voice-analyzer d-flex flex-column pa-2">
    <v-row align="center" no-gutters class="flex-shrink-0">
      <v-col cols="auto" class="mr-3">
        <v-icon>mdi-volume-high</v-icon>
      </v-col>
      <v-col>
        <v-progress-linear
          v-model="volume"
          color="primary"
          height="12"
          rounded
        ></v-progress-linear>
      </v-col>
    </v-row>
    <canvas ref="canvasRef" class="mt-2 flex-shrink-0"></canvas>
    <div class="mt-4 flex-grow-1" style="position: relative;">
      <Line ref="lineChartRef" :data="pitchChartData" :options="pitchChartOptions" />
    </div>
  </div>
</template>

<style scoped>
.voice-analyzer {
  width: 100%;
  height: 100%;
}
canvas {
  width: 100%;
  background-color: #1a1a1a;
  border-radius: 4px;
}
</style> 