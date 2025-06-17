// src/frontend/plugins/vuetify.ts

// Styles
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

// Vuetify
import { createVuetify } from 'vuetify'
import type { ThemeDefinition } from 'vuetify'

// Define the custom dark theme
const epXDarkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#1a1a1a', // Dark background
    surface: '#242424',    // Slightly lighter surface for cards, etc.
    primary: '#4CAF50',    // A vibrant green for primary actions
    secondary: '#FFC107',  // Amber for secondary accents
    error: '#FF5252',      // A standard red for errors
    info: '#2196F3',       // Blue for informational messages
    success: '#4CAF50',    // Green for success states
    warning: '#FFC107',    // Amber for warnings
  },
}

export default createVuetify({
  theme: {
    defaultTheme: 'epXDarkTheme',
    themes: {
      epXDarkTheme,
    },
  },
  icons: {
    defaultSet: 'mdi',
  },
}) 