import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import vuetify from './plugins/vuetify';
import './style.css'; // Tailwind CSSをインポート

const app = createApp(App);

// PiniaをVueアプリに登録
app.use(createPinia());
app.use(router);
app.use(vuetify);

app.mount('#app'); 