<script setup lang="ts">
import { computed } from 'vue'
import { useInterviewStore } from '../stores/interview'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  type ChartOptions,
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

const chartData = computed(() => {
  const labels = interviewStore.sentimentHistory.map(s =>
    new Date(s.timestamp).toLocaleTimeString()
  )
  const scoreData = interviewStore.sentimentHistory.map(s => s.score)
  const magnitudeData = interviewStore.sentimentHistory.map(s => s.magnitude)

  return {
    labels,
    datasets: [
      {
        label: '感情スコア (Positive / Negative)',
        backgroundColor: 'rgba(33, 150, 243, 0.2)', // info color
        borderColor: 'rgb(33, 150, 243)',
        data: scoreData,
        yAxisID: 'yScore',
        tension: 0.2,
        pointRadius: 1,
      },
      {
        label: '感情の強さ',
        backgroundColor: 'rgba(255, 193, 7, 0.2)', // secondary color
        borderColor: 'rgb(255, 193, 7)',
        data: magnitudeData,
        yAxisID: 'yMagnitude',
        tension: 0.2,
        pointRadius: 1,
      },
    ],
  }
})

const chartOptions: ChartOptions<'line'> = {
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    yScore: {
      type: 'linear',
      display: true,
      position: 'left',
      title: {
        display: true,
        text: '感情スコア',
      },
      min: -1,
      max: 1,
    },
    yMagnitude: {
      type: 'linear',
      display: true,
      position: 'right',
      title: {
        display: true,
        text: '感情の強さ',
      },
      grid: {
        drawOnChartArea: false, // only have one grid for clarity
      },
      beginAtZero: true,
    },
    x: {
      ticks: {
        maxTicksLimit: 10,
      }
    }
  },
  plugins: {
    legend: {
      position: 'top' as const,
    },
  },
}
</script>

<template>
  <div class="emotion-chart-container">
    <div v-if="interviewStore.sentimentHistory.length > 0" style="height: 250px">
      <Line :data="chartData" :options="chartOptions" />
    </div>
    <div v-else class="text-center text-medium-emphasis pa-8">
      <p>発言すると、ここに感情の分析結果がリアルタイムで表示されます。</p>
    </div>
  </div>
</template>

<style scoped>
.emotion-chart-container {
  width: 100%;
}
</style> 