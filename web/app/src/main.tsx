import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { FluentProvider, createLightTheme, type BrandVariants } from '@fluentui/react-components'
import './styles.css'
import App from './App'
import { AuthProvider } from './auth/msal'
import { StoreProvider } from './state/store'

// A Fluent brand ramp around the app's accent, #2a78d6.
const brand: BrandVariants = {
  10: '#020306', 20: '#0b1a2e', 30: '#102a4e', 40: '#143a6c', 50: '#174a8b', 60: '#1b5aab', 70: '#2069c2', 80: '#2a78d6',
  90: '#4588dc', 100: '#5e98e2', 110: '#76a8e8', 120: '#8eb8ed', 130: '#a6c8f2', 140: '#bed8f7', 150: '#d6e7fb', 160: '#edf5fe',
}
const theme = {
  ...createLightTheme(brand),
  fontFamilyBase: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  colorNeutralBackground1: '#ffffff',
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FluentProvider theme={theme} style={{ height: '100%', background: 'transparent' }}>
      <AuthProvider>
        <StoreProvider>
          <App />
        </StoreProvider>
      </AuthProvider>
    </FluentProvider>
  </StrictMode>,
)
