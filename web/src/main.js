import './style.css'

import { renderPage, initPage } from './page.js'

function mount() {
  const app = document.getElementById('app')
  if (!app) return

  app.innerHTML = renderPage()
  initPage()
}

document.addEventListener('DOMContentLoaded', mount)
