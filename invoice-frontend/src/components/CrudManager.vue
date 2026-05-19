<template>
  <q-card class="crud-card">
    <q-card-section class="row items-center justify-between q-pb-sm">
      <div>
        <div class="text-h6">{{ title }}</div>
        <div v-if="subtitle" class="text-caption text-grey-7">{{ subtitle }}</div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-input
          v-model="search"
          dense
          outlined
          clearable
          :placeholder="searchPlaceholder"
          style="min-width: 240px"
          @update:model-value="loadRowsDebounced"
          @clear="loadRows"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
        <q-btn color="primary" icon="add" :label="createLabel" @click="openCreate" />
      </div>
    </q-card-section>

    <q-card-section class="q-pt-none">
      <q-table
        flat
        bordered
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="loading"
        :no-data-label="noDataLabel"
        :rows-per-page-options="[10, 25, 50, 0]"
        @row-click="(_, row) => openEdit(row)"
      >
        <template #body-cell-actions="props">
          <q-td :props="props" auto-width>
            <div class="row q-gutter-xs no-wrap">
              <q-btn flat dense icon="edit" color="primary" @click.stop="openEdit(props.row)" />
              <q-btn flat dense icon="delete" color="negative" @click.stop="confirmDelete(props.row)" />
            </div>
          </q-td>
        </template>
      </q-table>
    </q-card-section>
  </q-card>

  <q-dialog v-model="dialogOpen" persistent>
    <q-card class="crud-dialog">
      <q-card-section class="row items-center">
        <div class="text-h6">{{ editingIndex === -1 ? createLabel : editLabel }}</div>
        <q-space />
        <q-btn icon="close" flat round dense @click="closeDialog" />
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-form @submit.prevent="saveRecord">
          <div class="row q-col-gutter-md">
            <div
              v-for="field in fields"
              :key="field.key"
              :class="field.colClass || 'col-12 col-md-6'"
            >
              <q-input
                v-if="field.type === 'text' || field.type === 'number' || field.type === 'date'"
                v-model="form[field.key]"
                :type="field.type"
                :label="field.label"
                :hint="field.hint"
                :outlined="field.outlined !== false"
                :dense="field.dense !== false"
                :disable="field.readonly"
                :step="field.step"
                :min="field.min"
                :max="field.max"
              />

              <q-input
                v-else-if="field.type === 'textarea' || field.type === 'json'"
                v-model="form[field.key]"
                type="textarea"
                :label="field.label"
                :hint="field.hint"
                :outlined="field.outlined !== false"
                :dense="field.dense !== false"
                :disable="field.readonly"
                autogrow
              />

              <q-select
                v-else-if="field.type === 'select'"
                v-model="form[field.key]"
                :options="field.options || []"
                :option-label="field.optionLabel || 'label'"
                :option-value="field.optionValue || 'value'"
                :emit-value="field.emitValue !== false"
                :map-options="field.mapOptions !== false"
                :label="field.label"
                :outlined="field.outlined !== false"
                :dense="field.dense !== false"
                :clearable="field.clearable !== false"
                :multiple="field.multiple"
              />

              <q-toggle
                v-else-if="field.type === 'toggle'"
                v-model="form[field.key]"
                :label="field.label"
              />
            </div>
          </div>
        </q-form>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" @click="closeDialog" />
        <q-btn color="primary" :label="saveButtonLabel" :loading="saving" @click="saveRecord" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Notify, Dialog } from 'quasar'
import { deleteAPI, fetchAPI, patchAPI, postAPI } from '../utils/api'

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  endpoint: { type: String, required: true },
  columns: { type: Array, required: true },
  fields: { type: Array, required: true },
  defaultRecord: { type: Object, default: () => ({}) },
  searchPlaceholder: { type: String, default: 'Search' },
  noDataLabel: { type: String, default: 'No records found' },
  createLabel: { type: String, default: 'Add' },
  editLabel: { type: String, default: 'Edit' },
  saveButtonLabel: { type: String, default: 'Save' },
  transformCreate: { type: Function, default: null },
  transformUpdate: { type: Function, default: null },
})

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogOpen = ref(false)
const editingIndex = ref(-1)
const search = ref('')
const form = ref({})
const searchTimer = ref(null)

const currentEndpoint = computed(() => props.endpoint.replace(/\/$/, ''))

function cloneDefaultRecord () {
  return JSON.parse(JSON.stringify(props.defaultRecord || {}))
}

function normalizeFieldValue (field, value) {
  if (field.type === 'json') {
    if (typeof value === 'string') {
      return value
    }
    return JSON.stringify(value ?? {}, null, 2)
  }
  return value
}

function preparePayloadValue (field, value) {
  if (field.type === 'json') {
    if (value === null || value === undefined || value === '') {
      return {}
    }
    if (typeof value === 'string') {
      try {
        return JSON.parse(value)
      } catch {
        throw new Error(`Invalid JSON in ${field.label}`)
      }
    }
  }
  return value
}

function normalizeRows (data) {
  if (Array.isArray(data)) {
    return data
  }
  if (Array.isArray(data?.results)) {
    return data.results
  }
  if (Array.isArray(data?.items)) {
    return data.items
  }
  return []
}

async function loadRows () {
  loading.value = true
  try {
    const query = search.value.trim()
    const endpoint = query
      ? `${currentEndpoint.value}/?q=${encodeURIComponent(query)}`
      : `${currentEndpoint.value}/`
    const data = await fetchAPI(endpoint)
    rows.value = normalizeRows(data)
  } catch (error) {
    Notify.create({
      type: 'negative',
      message: `Failed to load ${props.title.toLowerCase()}`,
    })
    console.error(error)
  } finally {
    loading.value = false
  }
}

function loadRowsDebounced () {
  clearTimeout(searchTimer.value)
  searchTimer.value = setTimeout(loadRows, 250)
}

function openCreate () {
  editingIndex.value = -1
  form.value = cloneDefaultRecord()
  dialogOpen.value = true
}

function openEdit (row) {
  editingIndex.value = rows.value.findIndex(item => item.id === row.id)
  const nextForm = {
    ...cloneDefaultRecord(),
    ...JSON.parse(JSON.stringify(row)),
  }
  props.fields.forEach((field) => {
    nextForm[field.key] = normalizeFieldValue(field, nextForm[field.key])
  })
  form.value = nextForm
  dialogOpen.value = true
}

function closeDialog () {
  dialogOpen.value = false
}

async function saveRecord () {
  saving.value = true
  try {
    const normalizedPayload = { ...form.value }
    props.fields.forEach((field) => {
      normalizedPayload[field.key] = preparePayloadValue(field, normalizedPayload[field.key])
    })
    const payload = props.transformCreate
      ? props.transformCreate(normalizedPayload)
      : normalizedPayload
    let data
    if (editingIndex.value === -1) {
      data = await postAPI(`${currentEndpoint.value}/`, payload)
    } else {
      const updatePayload = props.transformUpdate
        ? props.transformUpdate(normalizedPayload)
        : payload
      data = await patchAPI(`${currentEndpoint.value}/${form.value.id}/`, updatePayload)
    }
    Notify.create({
      type: 'positive',
      message: `${props.title} saved`,
    })
    dialogOpen.value = false
    await loadRows()
    return data
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: `Failed to save ${props.title.toLowerCase()}`,
    })
  } finally {
    saving.value = false
  }
}

function confirmDelete (row) {
  Dialog.create({
    title: `Delete ${props.title}?`,
    message: 'This action cannot be undone.',
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await deleteAPI(`${currentEndpoint.value}/${row.id}/`)
      Notify.create({
        type: 'positive',
        message: `${props.title} deleted`,
      })
      await loadRows()
    } catch (error) {
      console.error(error)
      Notify.create({
        type: 'negative',
        message: `Failed to delete ${props.title.toLowerCase()}`,
      })
    }
  })
}

watch(() => props.endpoint, () => {
  loadRows()
})

onMounted(() => {
  loadRows()
})
</script>

<style scoped>
.crud-card {
  border-radius: 18px;
}

.crud-dialog {
  width: min(920px, 100%);
}
</style>
