import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue'; // Assuming App.vue is the root component

const pinia = createPinia();
const app = createApp(App);

app.use(pinia);
app.mount('#app'); 