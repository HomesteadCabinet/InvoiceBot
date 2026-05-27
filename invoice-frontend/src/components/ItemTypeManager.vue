<template>
  <q-card class="crud-card">
    <q-card-section class="row items-center justify-between q-pb-sm">
      <div>
        <div class="text-h6">Item Types</div>
        <div class="text-caption text-grey-7">
          Organize inventory and line items into nested categories and sub-types.
        </div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-input
          v-model="search"
          dense
          outlined
          clearable
          placeholder="Search types"
          style="min-width: 240px"
          @update:model-value="loadRowsDebounced"
          @clear="loadRows"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
        <q-btn color="primary" icon="add" label="Add root type" @click="openCreate()" />
      </div>
    </q-card-section>

    <q-card-section class="q-pt-none">
      <q-table
        v-drag-pan
        flat
        bordered
        row-key="id"
        :rows="displayRows"
        :columns="columns"
        :loading="loading"
        no-data-label="No item types found"
        v-model:pagination="pagination"
        :rows-per-page-options="[20, 50, 100]"
        @request="handleTableRequest"
        @row-click="(_, row) => openEdit(row)"
      >
        <template #body-cell-name="props">
          <q-td :props="props">
            <div
              class="row items-center q-gutter-sm no-wrap"
              :style="{ paddingLeft: `${rowDepth(props.row) * 20}px` }"
            >
              <q-icon
                v-if="props.row.icon"
                :name="props.row.icon"
                size="sm"
                :style="itemTypeIconStyle(props.row.color)"
              />
              <span class="text-weight-medium">{{ props.row.name }}</span>
            </div>
          </q-td>
        </template>

        <template #body-cell-full_path="props">
          <q-td :props="props">
            <span class="text-grey-8">{{ props.row.full_path || props.row.name }}</span>
          </q-td>
        </template>

        <template #body-cell-icon="props">
          <q-td :props="props">
            <div v-if="props.row.icon" class="row items-center q-gutter-sm no-wrap">
              <q-icon
                :name="props.row.icon"
                size="sm"
                :style="itemTypeIconStyle(props.row.color)"
              />
              <span>{{ props.row.icon }}</span>
            </div>
            <span v-else class="text-grey-6">—</span>
          </q-td>
        </template>

        <template #body-cell-color="props">
          <q-td :props="props">
            <div
              v-if="props.row.color"
              class="row items-center q-gutter-sm no-wrap"
            >
              <div
                class="color-swatch"
                :style="{ backgroundColor: props.row.color }"
              />
              <span>{{ props.row.color }}</span>
            </div>
            <span v-else class="text-grey-6">—</span>
          </q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" auto-width>
            <div class="row q-gutter-xs no-wrap">
              <q-btn
                flat
                dense
                icon="subdirectory_arrow_right"
                color="primary"
                @click.stop="openCreate(props.row)"
              >
                <q-tooltip>Add sub-type</q-tooltip>
              </q-btn>
              <q-btn flat dense icon="edit" color="primary" @click.stop="openEdit(props.row)" />
              <q-btn flat dense icon="delete" color="negative" @click.stop="confirmDelete(props.row)" />
            </div>
          </q-td>
        </template>
      </q-table>
    </q-card-section>
  </q-card>

  <q-dialog v-model="dialogOpen" persistent>
    <q-card class="item-type-dialog">
      <q-card-section class="row items-center">
        <div>
          <div class="text-h6">{{ dialogTitle }}</div>
          <div v-if="pathPreview" class="text-caption text-grey-7 q-mt-xs">
            Full path: {{ pathPreview }}
          </div>
        </div>
        <q-space />
        <q-btn icon="close" flat round dense @click="closeDialog" />
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-form @submit.prevent="saveRecord">
          <div class="row q-col-gutter-md">
            <div class="col-12">
              <q-select
                v-model="form.parent"
                :options="parentOptions"
                option-label="label"
                option-value="value"
                emit-value
                map-options
                label="Parent type"
                hint="Leave empty for a top-level type"
                outlined
                dense
                clearable
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
              </q-select>
            </div>

            <div class="col-12 col-md-6">
              <q-input
                v-model="form.name"
                label="Name"
                hint="Short label for this type"
                outlined
                dense
                :rules="[value => Boolean((value || '').trim()) || 'Name is required']"
              />
            </div>

            <div class="col-12 col-md-6">
              <q-input
                v-model="form.icon"
                label="Icon"
                hint="Material icon name"
                outlined
                dense
                clearable
              >
                <template #prepend>
                  <q-icon
                    :name="form.icon || 'help_outline'"
                    :style="itemTypeIconStyle(form.color)"
                  />
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
                            v-for="iconName in filteredIcons"
                            :key="iconName"
                            v-close-popup
                            flat
                            dense
                            class="icon-picker-btn"
                            @click="form.icon = iconName"
                          >
                            <q-icon
                              :name="iconName"
                              size="md"
                              :style="itemTypeIconStyle(form.color)"
                            />
                            <q-tooltip>{{ iconName }}</q-tooltip>
                          </q-btn>
                        </q-card-section>
                      </q-card>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
            </div>

            <div class="col-12">
              <q-input
                v-model="form.description"
                type="textarea"
                label="Description"
                outlined
                dense
                autogrow
              />
            </div>

            <div class="col-12 col-md-6">
              <q-input
                v-model="form.color"
                label="Color"
                outlined
                dense
              >
                <template #prepend>
                  <div
                    class="color-swatch color-swatch--input"
                    :style="{ backgroundColor: form.color || '#ffffff' }"
                  />
                </template>
                <template #append>
                  <q-icon name="colorize" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-color
                        v-model="form.color"
                        format-model="hex"
                        default-view="palette"
                      />
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
        <q-btn color="primary" label="Save" :loading="saving" @click="saveRecord" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Dialog, Notify } from 'quasar'
import { deleteAPI, fetchAPI, patchAPI, postAPI } from '../utils/api'
import { dragPanDirective } from '../utils/dragPan'
import { ITEM_TYPE_ICONS, filterMaterialIcons } from '../utils/materialIcons'
import {
  collectItemTypeDescendantIds,
  itemTypeDepth,
  itemTypeIconStyle,
  orderItemTypesForTable,
  parentOptionsForEditor,
  previewItemTypePath,
} from '../utils/itemTypes'
import { notifyCrudChanged } from '../utils/crudSync'

const vDragPan = dragPanDirective

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogOpen = ref(false)
const editingId = ref(null)
const search = ref('')
const searchTimer = ref(null)
const iconFilter = ref('')
const pagination = ref({
  page: 1,
  rowsPerPage: 50,
  sortBy: '',
  descending: false,
  rowsNumber: 0,
})

const defaultForm = () => ({
  parent: null,
  name: '',
  description: '',
  color: '',
  icon: '',
})

const form = ref(defaultForm())

const columns = [
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: false },
  { name: 'full_path', label: 'Full path', field: 'full_path', align: 'left', sortable: false },
  { name: 'icon', label: 'Icon', field: 'icon', align: 'left' },
  { name: 'description', label: 'Description', field: 'description', align: 'left' },
  { name: 'color', label: 'Color', field: 'color', align: 'left' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const rowsById = computed(() => new Map(rows.value.map(row => [row.id, row])))

const displayRows = computed(() => {
  if (search.value.trim()) {
    return rows.value
  }
  return orderItemTypesForTable(rows.value)
})

const parentOptions = computed(() => parentOptionsForEditor(rows.value, editingId.value))

const pathPreview = computed(() => previewItemTypePath(form.value.name, form.value.parent, rows.value))

const dialogTitle = computed(() => {
  if (editingId.value) {
    return 'Edit item type'
  }
  if (form.value.parent) {
    const parent = rowsById.value.get(form.value.parent)
    return parent ? `Add sub-type under ${parent.name}` : 'Add sub-type'
  }
  return 'Add root item type'
})

const filteredIcons = computed(() => filterMaterialIcons(ITEM_TYPE_ICONS, iconFilter.value))

function rowDepth (row) {
  return itemTypeDepth(row, rowsById.value)
}

function normalizeRows (data) {
  if (Array.isArray(data)) {
    return data
  }
  if (Array.isArray(data?.results)) {
    return data.results
  }
  return []
}

function apiErrorMessage (error) {
  if (!error?.message) {
    return 'Request failed'
  }
  return error.message
}

async function loadRows (nextPagination = {}) {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page_size', '500')
    const query = search.value.trim()
    if (query) {
      params.set('q', query)
    }
    const page = Number(nextPagination.page || pagination.value.page || 1)
    if (page > 1) {
      params.set('page', String(page))
    }
    const data = await fetchAPI(`/api/item-types/?${params.toString()}`)
    rows.value = normalizeRows(data)
    pagination.value = {
      page,
      rowsPerPage: pagination.value.rowsPerPage,
      sortBy: '',
      descending: false,
      rowsNumber: Number(data?.count ?? rows.value.length),
    }
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: 'Failed to load item types',
    })
  } finally {
    loading.value = false
  }
}

function loadRowsDebounced () {
  clearTimeout(searchTimer.value)
  searchTimer.value = setTimeout(() => loadRows({ page: 1 }), 250)
}

function handleTableRequest (requestProps) {
  loadRows(requestProps.pagination)
}

function openCreate (parentRow = null) {
  editingId.value = null
  form.value = {
    ...defaultForm(),
    parent: parentRow?.id ?? null,
  }
  iconFilter.value = ''
  dialogOpen.value = true
}

function openEdit (row) {
  editingId.value = row.id
  form.value = {
    parent: row.parent ?? null,
    name: row.name || '',
    description: row.description || '',
    color: row.color || '',
    icon: row.icon || '',
  }
  iconFilter.value = ''
  dialogOpen.value = true
}

function closeDialog () {
  dialogOpen.value = false
  editingId.value = null
  form.value = defaultForm()
}

async function saveRecord () {
  const name = (form.value.name || '').trim()
  if (!name) {
    Notify.create({ type: 'warning', message: 'Name is required' })
    return
  }

  const payload = {
    parent: form.value.parent || null,
    name,
    description: form.value.description || '',
    color: form.value.color || '',
    icon: form.value.icon || '',
  }

  saving.value = true
  try {
    if (editingId.value) {
      await patchAPI(`/api/item-types/${editingId.value}/`, payload)
    } else {
      await postAPI('/api/item-types/', payload)
    }
    Notify.create({ type: 'positive', message: 'Item type saved' })
    closeDialog()
    notifyCrudChanged()
    await loadRows({ page: pagination.value.page })
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: apiErrorMessage(error),
    })
  } finally {
    saving.value = false
  }
}

function confirmDelete (row) {
  const descendantCount = collectItemTypeDescendantIds(rows.value, row.id).length
  Dialog.create({
    title: 'Delete item type?',
    message: descendantCount
      ? `Delete "${row.full_path || row.name}" and ${descendantCount} nested sub-type(s)?`
      : `Delete "${row.full_path || row.name}"? This cannot be undone.`,
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await deleteAPI(`/api/item-types/${row.id}/`)
      Notify.create({ type: 'positive', message: 'Item type deleted' })
      notifyCrudChanged()
      await loadRows({ page: pagination.value.page })
    } catch (error) {
      console.error(error)
      Notify.create({
        type: 'negative',
        message: apiErrorMessage(error),
      })
    }
  })
}

onMounted(() => {
  loadRows({ page: 1 })
})
</script>

<style scoped>
.crud-card {
  border-radius: 18px;
}

.item-type-dialog {
  width: min(720px, 100%);
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
</style>
