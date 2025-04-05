import { createApp } from 'vue'
import { Quasar, Notify, Dialog, Loading } from 'quasar'
import '@quasar/extras/material-icons/material-icons.css'
import '@quasar/extras/fontawesome-v6/fontawesome-v6.css'
import 'quasar/src/css/index.sass'
import App from './App.vue'
import router from './router'

// Import Font Awesome
import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { fas } from '@fortawesome/free-solid-svg-icons'

// Import v-select
import vSelect from 'vue3-select-component'

// Add all icons to the library
library.add(fas)

const app = createApp(App)

app.use(Quasar, {
  plugins: {
    Notify,
    Dialog,
    Loading
  },
  config: {
    brand: {
      primary: '#1976D2',
      secondary: '#26A69A',
      accent: '#9C27B0',
      dark: '#1D1D1D',
      positive: '#21BA45',
      negative: '#C10015',
      info: '#31CCEC',
      warning: '#F2C037'
    },
    notify: {
      position: 'top-right',
      timeout: 3000,
      textColor: 'white',
      actions: [{ icon: 'close', color: 'white' }]
    },
    loading: {
      spinner: 'QSpinnerGears',
      spinnerColor: 'primary',
      spinnerSize: 140,
      backgroundColor: 'white',
      message: 'Loading...',
    }
  }
})

app.component('font-awesome-icon', FontAwesomeIcon)
app.component('v-select', vSelect)

app.use(router)

app.mount('#q-app')
