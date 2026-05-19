<template>
  <q-page class="auth-page q-pa-md flex flex-center">
    <q-card class="auth-card">
      <q-card-section class="q-pb-none">
        <div class="text-overline text-accent">Invoiceinator</div>
        <div class="text-h4 text-weight-bold q-mt-sm">Google account access</div>
        <div class="text-body1 text-grey-7 q-mt-sm">
          Connect a Google account so the backend can read Gmail invoices and write to Sheets.
        </div>
      </q-card-section>

      <q-card-section v-if="statusMessage">
        <q-banner :class="bannerClass" rounded>
          {{ statusMessage }}
        </q-banner>
      </q-card-section>

      <q-card-section class="q-gutter-md">
        <div class="row items-center q-gutter-sm">
          <q-badge :color="connected ? 'positive' : 'grey-6'" class="q-px-sm q-py-xs">
            {{ connected ? 'Connected' : 'Not connected' }}
          </q-badge>
          <q-spinner v-if="loading" size="20px" color="primary" />
        </div>

        <div class="text-caption text-grey-7">
          Connected scopes:
          <span v-if="scopes.length">{{ scopes.join(', ') }}</span>
          <span v-else>none</span>
        </div>

        <div class="row q-gutter-sm">
          <q-btn
            color="primary"
            label="Connect Google Account"
            :disable="loading"
            @click="connectGoogle"
          />
          <q-btn
            v-if="connected"
            outline
            color="negative"
            label="Disconnect"
            :disable="loading"
            @click="disconnectGoogle"
          />
        </div>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Notify } from 'quasar'

const urlParams = new URLSearchParams(window.location.search)

const loading = ref(false)
const connected = ref(false)
const scopes = ref([])

const statusMessage = computed(() => {
  if (urlParams.get('googleAuth') === 'success') {
    return 'Google account connected.'
  }

  if (urlParams.get('googleAuth') === 'error') {
    return urlParams.get('message') || 'Google authorization failed.'
  }

  return ''
})

const bannerClass = computed(() => (
  urlParams.get('googleAuth') === 'success'
    ? 'bg-positive text-white'
    : 'bg-negative text-white'
))

async function refreshStatus () {
  loading.value = true
  try {
    const response = await fetch('/api/google/status/')
    const data = await response.json()
    connected.value = Boolean(data.connected)
    scopes.value = data.scopes || []
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to load Google connection status'
    })
  } finally {
    loading.value = false
  }
}

async function connectGoogle () {
  loading.value = true
  try {
    const response = await fetch('/api/google/auth-url/', {
      credentials: 'include'
    })
    const data = await response.json()
    window.location.href = data.authorization_url
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to start Google authorization'
    })
    loading.value = false
  }
}

async function disconnectGoogle () {
  loading.value = true
  try {
    await fetch('/api/google/disconnect/', {
      method: 'POST'
    })
    await refreshStatus()
    Notify.create({
      type: 'positive',
      message: 'Google account disconnected'
    })
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to disconnect Google account'
    })
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refreshStatus()
})
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(25, 118, 210, 0.18), transparent 32%),
    radial-gradient(circle at bottom right, rgba(38, 166, 154, 0.16), transparent 28%),
    linear-gradient(135deg, #0f172a 0%, #111827 45%, #1f2937 100%);
}

.auth-card {
  width: min(640px, 100%);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(12px);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.25);
}
</style>
