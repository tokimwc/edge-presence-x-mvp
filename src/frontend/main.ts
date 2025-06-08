import { createApp } from 'vue';
import { createPinia } from 'pinia';
import './style.css'; // Tailwind CSSをインポート
import App from './App.vue'; // Assuming App.vue is the root component

const app = createApp(App);

// PiniaをVueアプリに登録
app.use(createPinia());

app.mount('#app'); 