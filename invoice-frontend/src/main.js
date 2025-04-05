import { createApp } from 'vue'
import './style.scss'
import App from './App.vue'

// Import Bootstrap CSS and JS
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'

// Import Font Awesome
import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { fas } from '@fortawesome/free-solid-svg-icons'

// https://vue3-select-component.vercel.app/options.html
import vSelect from 'vue3-select-component'

// Add all icons to the library
library.add(fas)

const app = createApp(App)
app.component('font-awesome-icon', FontAwesomeIcon)
app.component('v-select', vSelect)
app.mount('#app')
