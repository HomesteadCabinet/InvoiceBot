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
        v-drag-pan
        flat
        bordered
        :rows="rows"
        :columns="effectiveColumns"
        row-key="id"
        :loading="loading"
        :no-data-label="noDataLabel"
        v-model:pagination="pagination"
        :rows-per-page-options="[20, 50, 100]"
        @request="handleTableRequest"
        @row-click="handleRowClick"
      >
        <template v-for="col in customCellColumns" :key="`cell-${col.name}`" #[`body-cell-${col.name}`]="props">
          <q-td :props="props">
            <div
              v-if="col.format === 'color' && props.row[col.field || col.name]"
              class="row items-center q-gutter-sm no-wrap"
            >
              <div
                class="color-swatch"
                :style="{ backgroundColor: props.row[col.field || col.name] }"
              />
              <span>{{ props.row[col.field || col.name] }}</span>
            </div>
            <span v-else-if="col.format === 'color'" class="text-grey-6">—</span>

            <div
              v-else-if="col.format === 'icon' && props.row[col.field || col.name]"
              class="row items-center q-gutter-sm no-wrap"
            >
              <q-icon
                :name="props.row[col.field || col.name]"
                size="sm"
                :style="itemTypeIconStyle(props.row.color)"
              />
              <span>{{ props.row[col.field || col.name] }}</span>
            </div>
            <span v-else-if="col.format === 'icon'" class="text-grey-6">—</span>

            <q-img
              v-else-if="col.format === 'image' && imageCellUrl(col, props.row)"
              :src="imageCellUrl(col, props.row)"
              ratio="1"
              class="crud-logo-thumb"
            />
            <span v-else-if="col.format === 'image'" class="text-grey-6">—</span>

            <q-badge
              v-else-if="col.format === 'boolean'"
              :color="props.row[col.field || col.name] ? 'positive' : 'grey-6'"
            >
              {{ props.row[col.field || col.name] ? 'Yes' : 'No' }}
            </q-badge>

            <q-badge
              v-else-if="col.format === 'badge'"
              :color="badgeColor(col, props.row)"
            >
              {{ badgeLabel(col, props.row) }}
            </q-badge>
          </q-td>
        </template>

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
              <div v-if="field.type === 'image'" class="column q-gutter-sm">
                <q-img
                  v-if="imagePreview(field)"
                  :src="imagePreview(field)"
                  ratio="1"
                  class="crud-logo-preview"
                />
                <q-file
                  :label="field.label"
                  accept="image/*"
                  outlined
                  dense
                  clearable
                  @update:model-value="value => setImageFile(field, value)"
                />
              </div>

              <q-input
                v-else-if="field.type === 'text' || field.type === 'number' || field.type === 'date' || field.type === 'datetime' || field.type === 'url' || field.type === 'email'"
                v-model="form[field.key]"
                :type="field.type === 'datetime' ? 'datetime-local' : field.type"
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
              >
                <template #option="scope">
                  <q-item v-bind="scope.itemProps">
                    <q-item-section v-if="scope.opt.icon" avatar>
                      <q-icon
                        :name="scope.opt.icon"
                        :style="itemTypeIconStyle(scope.opt.color)"
                      />
                    </q-item-section>
                    <q-item-section>{{ scope.opt.label }}</q-item-section>
                  </q-item>
                </template>
                <template #selected-item="scope">
                  <div v-if="scope.opt" class="row items-center q-gutter-sm no-wrap">
                    <q-icon
                      v-if="scope.opt.icon"
                      :name="scope.opt.icon"
                      :style="itemTypeIconStyle(scope.opt.color)"
                    />
                    <span>{{ scope.opt.label }}</span>
                  </div>
                </template>
              </q-select>

              <q-toggle
                v-else-if="field.type === 'toggle'"
                v-model="form[field.key]"
                :label="field.label"
              />

              <q-input
                v-else-if="field.type === 'color'"
                v-model="form[field.key]"
                :label="field.label"
                :hint="field.hint"
                :outlined="field.outlined !== false"
                :dense="field.dense !== false"
                :disable="field.readonly"
              >
                <template #prepend>
                  <div
                    class="color-swatch color-swatch--input"
                    :style="{ backgroundColor: form[field.key] || '#ffffff' }"
                  />
                </template>
                <template #append>
                  <q-icon name="colorize" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-color
                        v-model="form[field.key]"
                        format-model="hex"
                        default-view="palette"
                      />
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>

              <q-input
                v-else-if="field.type === 'icon'"
                v-model="form[field.key]"
                :label="field.label"
                :hint="field.hint || 'Material icon name'"
                :outlined="field.outlined !== false"
                :dense="field.dense !== false"
                :disable="field.readonly"
                clearable
              >
                <template #prepend>
                  <q-icon :name="form[field.key] || 'help_outline'" />
                </template>
                <template #append>
                  <q-icon name="apps" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-card class="icon-picker-card">
                        <q-card-section class="q-pb-sm">
                          <q-input
                            v-model="iconFilter"
                            dense
                            outlined
                            clearable
                            label="Search icons"
                          >
                            <template #prepend>
                              <q-icon name="search" />
                            </template>
                          </q-input>
                        </q-card-section>
                        <q-card-section class="q-pt-none icon-picker-grid">
                          <q-btn
                            v-for="iconName in filteredIconsForField(field)"
                            :key="iconName"
                            v-close-popup
                            flat
                            dense
                            class="icon-picker-btn"
                            @click="form[field.key] = iconName"
                          >
                            <q-icon :name="iconName" size="md" />
                            <q-tooltip>{{ iconName }}</q-tooltip>
                          </q-btn>
                        </q-card-section>
                      </q-card>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
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
import { deleteAPI, fetchAPI, patchAPI, postAPI, submitFormAPI } from '../utils/api'
import { dragPanDirective } from '../utils/dragPan'
import { ITEM_TYPE_ICONS, filterMaterialIcons } from '../utils/materialIcons'
import { itemTypeIconStyle } from '../utils/itemTypes'
import { crudSyncTick, notifyCrudChanged } from '../utils/crudSync'

const emit = defineEmits(['changed', 'row-click'])
const vDragPan = dragPanDirective

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
  rowClickBehavior: { type: String, default: 'edit' },
})

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogOpen = ref(false)
const editingIndex = ref(-1)
const search = ref('')
const form = ref({})
const searchTimer = ref(null)
const iconFilter = ref('')
const pagination = ref({
  page: 1,
  rowsPerPage: 20,
  sortBy: '',
  descending: false,
  rowsNumber: 0,
})

const currentEndpoint = computed(() => props.endpoint.replace(/\/$/, ''))

const effectiveColumns = computed(() => props.columns.map(column => ({
  ...column,
  sortable: column.name === 'actions' ? false : column.sortable !== false,
})))

const customCellColumns = computed(() => props.columns.filter(col => ['badge', 'boolean', 'color', 'icon', 'image'].includes(col.format)))

function iconsForField (field) {
  return field.options?.length ? field.options.map(option => option.value || option) : ITEM_TYPE_ICONS
}

function filteredIconsForField (field) {
  return filterMaterialIcons(iconsForField(field), iconFilter.value)
}

function cellValue (column, row) {
  if (typeof column.field === 'function') {
    return column.field(row)
  }
  return row?.[column.field || column.name]
}

function badgeLabel (column, row) {
  if (typeof column.badgeLabel === 'function') {
    return column.badgeLabel(row)
  }
  const value = cellValue(column, row)
  return value || '—'
}

function badgeColor (column, row) {
  if (typeof column.badgeColor === 'function') {
    return column.badgeColor(row)
  }
  return column.badgeColor || 'grey-6'
}

function cloneDefaultRecord () {
  return JSON.parse(JSON.stringify(props.defaultRecord || {}))
}

function imageFieldKey (field) {
  return `_${field.key}File`
}

function imageCellUrl (column, row) {
  const urlField = column.urlField || `${column.field || column.name}_url`
  return row?.[urlField] || row?.[column.field || column.name] || ''
}

function imagePreview (field) {
  const file = form.value[imageFieldKey(field)]
  if (file instanceof File) {
    return URL.createObjectURL(file)
  }
  return form.value[`${field.key}_url`] || form.value[field.key] || ''
}

function setImageFile (field, value) {
  const file = Array.isArray(value) ? value[0] : value
  form.value[imageFieldKey(field)] = file || null
}

function usesMultipartPayload (payload) {
  return props.fields.some((field) => {
    if (field.type !== 'image') {
      return false
    }
    return payload[imageFieldKey(field)] instanceof File
  })
}

function buildMultipartPayload (payload) {
  const formData = new FormData()
  props.fields.forEach((field) => {
    if (field.type === 'image') {
      const file = payload[imageFieldKey(field)]
      if (file instanceof File) {
        formData.append(field.key, file)
      }
      return
    }
    const value = payload[field.key]
    if (value === null || value === undefined) {
      return
    }
    if (field.type === 'toggle') {
      formData.append(field.key, value ? 'true' : 'false')
      return
    }
    if (field.type === 'json' && typeof value === 'object') {
      formData.append(field.key, JSON.stringify(value))
      return
    }
    formData.append(field.key, value)
  })
  return formData
}

function normalizeFieldValue (field, value) {
  if (field.type === 'json') {
    if (typeof value === 'string') {
      return value
    }
    return JSON.stringify(value ?? {}, null, 2)
  }
  if (field.type === 'datetime' && value) {
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) {
      const pad = n => String(n).padStart(2, '0')
      return [
        date.getFullYear(),
        pad(date.getMonth() + 1),
        pad(date.getDate()),
      ].join('-') + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
    }
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
  if (field.type === 'datetime' && value) {
    return `${value.length === 16 ? `${value}:00` : value}`
  }
  if (field.type === 'datetime' && !value) {
    return null
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

function normalizePagination (nextPagination = {}) {
  const rowsPerPage = Number(nextPagination.rowsPerPage || pagination.value.rowsPerPage || 20)
  return {
    page: Number(nextPagination.page || pagination.value.page || 1),
    rowsPerPage: rowsPerPage > 0 ? rowsPerPage : 20,
    sortBy: nextPagination.sortBy ?? pagination.value.sortBy ?? '',
    descending: Boolean(nextPagination.descending ?? pagination.value.descending ?? false),
    rowsNumber: Number(nextPagination.rowsNumber ?? pagination.value.rowsNumber ?? 0),
  }
}

function buildQueryParams (nextPagination) {
  const params = new URLSearchParams()
  const pageState = normalizePagination(nextPagination)
  if (pageState.page > 1) {
    params.set('page', String(pageState.page))
  }
  params.set('page_size', String(pageState.rowsPerPage))
  const query = search.value.trim()
  if (query) {
    params.set('q', query)
  }
  if (pageState.sortBy) {
    const column = props.columns.find(item => item.name === pageState.sortBy)
    const sortField = column?.sortField || pageState.sortBy
    params.set('ordering', `${pageState.descending ? '-' : ''}${sortField}`)
  }
  return { params, pageState }
}

async function loadRows (nextPagination = {}) {
  const { params, pageState } = buildQueryParams(nextPagination)
  loading.value = true
  try {
    const endpoint = params.toString()
      ? `${currentEndpoint.value}/?${params.toString()}`
      : `${currentEndpoint.value}/`
    const data = await fetchAPI(endpoint)
    rows.value = normalizeRows(data)
    pagination.value = {
      ...pageState,
      rowsNumber: Number(data?.count ?? rows.value.length),
    }
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
  searchTimer.value = setTimeout(() => loadRows({ page: 1, rowsPerPage: pagination.value.rowsPerPage }), 250)
}

function openCreate () {
  editingIndex.value = -1
  form.value = cloneDefaultRecord()
  iconFilter.value = ''
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
  iconFilter.value = ''
  dialogOpen.value = true
}

function handleRowClick (event, row) {
  if (props.rowClickBehavior === 'none') {
    return
  }
  if (props.rowClickBehavior === 'emit') {
    emit('row-click', { event, row })
    return
  }
  openEdit(row)
}

function handleTableRequest (requestProps) {
  loadRows(requestProps.pagination)
}

function closeDialog () {
  dialogOpen.value = false
}

async function saveRecord () {
  saving.value = true
  try {
    const normalizedPayload = { ...form.value }
    props.fields.forEach((field) => {
      if (field.type === 'image') {
        return
      }
      normalizedPayload[field.key] = preparePayloadValue(field, normalizedPayload[field.key])
    })
    const payload = props.transformCreate
      ? props.transformCreate(normalizedPayload)
      : normalizedPayload
    let data
    const multipart = usesMultipartPayload(payload)
    if (editingIndex.value === -1) {
      data = multipart
        ? await submitFormAPI(`${currentEndpoint.value}/`, buildMultipartPayload(payload), 'POST')
        : await postAPI(`${currentEndpoint.value}/`, payload)
    } else {
      const updatePayload = props.transformUpdate
        ? props.transformUpdate(normalizedPayload)
        : payload
      data = multipart
        ? await submitFormAPI(`${currentEndpoint.value}/${form.value.id}/`, buildMultipartPayload(updatePayload), 'PATCH')
        : await patchAPI(`${currentEndpoint.value}/${form.value.id}/`, updatePayload)
    }
    Notify.create({
      type: 'positive',
      message: `${props.title} saved`,
    })
    dialogOpen.value = false
    notifyCrudChanged()
    emit('changed', { action: editingIndex.value === -1 ? 'create' : 'update', endpoint: currentEndpoint.value, data })
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
      notifyCrudChanged()
      emit('changed', { action: 'delete', endpoint: currentEndpoint.value, id: row.id })
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
  loadRows({ page: 1, rowsPerPage: pagination.value.rowsPerPage })
})

watch(crudSyncTick, () => {
  loadRows({
    page: pagination.value.page,
    rowsPerPage: pagination.value.rowsPerPage,
    sortBy: pagination.value.sortBy,
    descending: pagination.value.descending,
  })
})

onMounted(() => {
  loadRows({ page: 1, rowsPerPage: pagination.value.rowsPerPage })
})
</script>

<style scoped>
.crud-card {
  border-radius: 18px;
}

.crud-dialog {
  width: min(920px, 100%);
}

.color-swatch {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  flex-shrink: 0;
}

.color-swatch--input {
  margin-left: 4px;
}

.icon-picker-card {
  width: min(360px, 90vw);
}

.icon-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(44px, 1fr));
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
}

.icon-picker-btn {
  min-width: 44px;
  min-height: 44px;
}

.crud-logo-thumb {
  width: 40px;
  border-radius: 8px;
}

.crud-logo-preview {
  max-width: 160px;
  border-radius: 12px;
}
</style>
