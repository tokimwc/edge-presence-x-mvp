import { createRouter, createWebHistory } from 'vue-router'
import InterviewLayout from '../components/InterviewLayout.vue'

const routes = [
  {
    path: '/',
    name: 'Interview',
    component: InterviewLayout,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router 