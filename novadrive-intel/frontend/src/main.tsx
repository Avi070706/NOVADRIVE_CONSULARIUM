import React from 'react'
import { createRoot } from 'react-dom/client'
import './theme.css'
import { AppProvider } from './store'
import App from './App'

createRoot(document.getElementById('root')!).render(<AppProvider><App /></AppProvider>)
