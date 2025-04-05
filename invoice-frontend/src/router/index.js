import { createRouter, createWebHashHistory } from 'vue-router'
import InvoiceList from '../components/InvoiceList.vue'

const routes = [
  {
    path: '/',
    component: InvoiceList
  }
]

export default createRouter({
  history: createWebHashHistory(),
  routes
})
