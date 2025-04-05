<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import VuePdfEmbed from 'vue-pdf-embed'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { deepClone } from '../utils/objectUtils'
import { fetchAPI, postAPI, patchAPI } from '../utils/api'


const defaultRule = {
  field_name: '',
  data_type: '',
  location_type: '',
  required: false,
  bbox: { x: 0, y: 0, width: 0, height: 0 }
}

const emails = ref([])
const nextPageToken = ref(null)
const loading = ref(false)
const showProcessingModal = ref(false)
const currentInvoice = ref(null)
const dataRules = ref([])
const vendorID = ref('')
const status = ref('')
const pdfError = ref(null)
const pdfLoading = ref(false)
const pdfText = ref('')
const maxResults = ref(10)
const vendors = ref([])
const abortController = ref(null)
const activeVendor = ref(null)
const isDrawing = ref(false)
const startPoint = ref({ x: 0, y: 0 })
const currentPoint = ref({ x: 0, y: 0 })
const pdfScale = ref(1)
const pdfContainer = ref(null)
const drawingEnabled = ref(false)
const newRule = ref(defaultRule)
const columnMappings = ref({})
const displayData = ref(null)
const _showDataModal = ref(false)
const modalTitle = ref('')
const tableData = ref(null)
const textData = ref(null)

// Watch for vendorID changes to update dataRules and active vendor
watch(vendorID, async (newVendorID) => {
  if (newVendorID) {
    const selectedVendor = vendors.value.find(v => v.id === newVendorID)
    if (selectedVendor) {
      activeVendor.value = selectedVendor
      dataRules.value = selectedVendor.data_rules || []
      // Load column mappings from vendor
      columnMappings.value = selectedVendor.spreadsheet_column_mapping || {}
    } else {
      activeVendor.value = null
      dataRules.value = []
      columnMappings.value = {}
    }
  } else {
    activeVendor.value = null
    dataRules.value = []
    columnMappings.value = {}
  }
})

// Add watch for columnMappings changes
watch(columnMappings, (newMappings) => {
  console.log('Column mappings updated:', newMappings)
}, { deep: true })

// Watch for maxResults changes
watch(maxResults, (newValue) => {
  console.log('maxResults changed', newValue)
  loadEmails()
}, { debounce: 500 })

// Watch for location_type changes and initialize appropriate properties
watch(() => newRule.value.location_type, (newType) => {
  // Always enable drawing since coordinates are needed for all types
  drawingEnabled.value = true

  if (newType === 'keyword' && !newRule.value.keyword) {
    newRule.value.keyword = ''
  } else if (newType === 'regex' && !newRule.value.regex_pattern) {
    newRule.value.regex_pattern = ''
  } else if (newType === 'table' && !newRule.value.table_config) {
    newRule.value.table_config = {
      header_text: 'Description',
      start_row_after_header: 1,
      item_columns: {
        id: 0,
        description: 1,
        quantity: 2,
        unit_price: 3
      }
    }
  }
})

watch(isDrawing, (newVal) => {
  console.log('isDrawing', newVal)
})

function setDisplayData(data) {
  if (data === 'Table Data') {
    modalTitle.value = 'Table Data'
    displayData.value = JSON.stringify(tableData.value, null, 2)
  } else if (data === 'Text Data') {
    modalTitle.value = 'Text Data'
    displayData.value = textData.value
  }
}

function detectTableColumns(rule) {
  if (!currentInvoice.value?.attachments?.[0]?.filename) {
    alert('No PDF file available to detect columns')
    return
  }

  const testData = {
    pdf_filename: currentInvoice.value.attachments[0].filename,
    rule: {
      ...rule,
      data_type: 'line_items',
      location_type: 'table',
      detect_only_header: true  // Add flag to only detect headers
    }
  }

  fetch('http://localhost:8000/api/data-rules/test/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(testData)
  })
  .then(response => {
    if (!response.ok) {
      throw new Error('Network response was not ok')
    }
    return response.json()
  })
  .then(data => {
    if (data.error) {
      alert(`Error detecting columns: ${data.error}`)
    } else if (data.result?.header_row?.length > 0) {
      // Get column names from the header row
      const columnNames = data.result.header_row.map(col => col?.toString().trim().toLowerCase() || '')

      // Update table config with detected columns
      newRule.value.table_config = {
        ...newRule.value.table_config,
        detected_columns: columnNames,
        item_columns: {}  // Reset mappings when columns are detected
      }

      // Update columnMappings with detected columns
      // First, preserve existing non-table column mappings
      const existingMappings = { ...columnMappings.value }

      // Add detected columns with default empty mappings
      columnNames.forEach((colName, index) => {
        // Only add if it's a valid column name
        if (colName) {
          existingMappings[colName] = '' // Initialize with empty column letter
        }
      })

      // Update the columnMappings ref
      columnMappings.value = existingMappings
    } else {
      alert('No table header detected. Please check the header text and try again.')
    }
  })
  .catch(error => {
    console.error('Error detecting columns:', error)
    alert('Failed to detect columns. Please try again.')
  })
}

function testDataRule(rule) {
  if (!currentInvoice.value?.attachments?.[0]?.filename) {
    alert('No PDF file available to test the rule')
    return
  }

  // For table rules, ensure we have column mappings before testing
  if (rule.location_type === 'table' && (!rule.table_config?.detected_columns || !Object.keys(rule.table_config.item_columns).length)) {
    alert('Please detect and map table columns first')
    return
  }

  const testData = {
    pdf_filename: currentInvoice.value.attachments[0].filename,
    rule: rule
  }

  fetch('http://localhost:8000/api/data-rules/test/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(testData)
  })
  .then(response => {
    if (!response.ok) {
      throw new Error('Network response was not ok')
    }
    return response.json()
  })
  .then(data => {
    if (data.error) {
      alert(`Error testing rule: ${data.error}`)
    } else {
      // Format the result based on data type
      let formattedResult = data.result
      if (rule.data_type === 'line_items' && data.result?.items) {
        formattedResult = {
          items: data.result.items.map(item => ({
            id: item.id || '',
            description: item.description || '',
            quantity: item.quantity || '',
            unit_price: item.unit_price || '',
            amount: item.amount || ''
          }))
        }
      }
      alert(`Rule test result: ${JSON.stringify(formattedResult, null, 2)}`)
    }
  })
  .catch(error => {
    console.error('Error testing rule:', error)
    alert('Failed to test rule. Please try again.')
  })
}

async function loadEmails(pageToken = null) {
  // Abort any existing request
  if (abortController.value) {
    abortController.value.abort()
  }

  // Create new AbortController for this request
  abortController.value = new AbortController()

  loading.value = true
  try {
    const params = new URLSearchParams()
    if (pageToken) {
      params.append('pageToken', pageToken)
    }
    params.append('maxResults', maxResults.value)

    const data = await fetchAPI(`/api/emails/?${params.toString()}`, {
      signal: abortController.value.signal
    })

    // Add status property to each email object
    data.emails = data.emails.map(email => ({
      ...email,
      status: email.status || 'pending', // Default to 'pending' if no status
      vendor_id: email.vendor_id || null,
      vendor_name: email.vendor_name || null,
      busy: false,
    }))

    if (pageToken) {
      emails.value = [...emails.value, ...data.emails]
    } else {
      emails.value = data.emails
    }
    nextPageToken.value = data.nextPageToken
  } catch (error) {
    // Only log error if it's not an abort error
    if (error.name !== 'AbortError') {
      console.error('Error loading emails:', error)
    }
  } finally {
    loading.value = false
    // Clear the abort controller after request completes
    abortController.value = null
  }
}

async function fetchVendors() {
  try {
    const data = await fetchAPI('/api/vendors/')
    // Add label and value props for v-select component
    vendors.value = data.map(vendor => ({
      ...vendor,
      label: vendor.name,
      value: vendor.id
    })) || []
  } catch (error) {
    console.error('Error fetching vendors:', error)
  }
}

async function processEmail(email_id) {
  const email = emails.value.find(e => e.id === email_id)
  email.busy = true
  let errorMessage = null

  try {
    const data = await postAPI('/api/process-email/', { email_id })

    if (data.status === 'error') {
      email.status = 'error'
      email.busy = false
      errorMessage = data.message
    }

    // Update the email in the list with new data
    const emailIndex = emails.value.findIndex(e => e.id === email_id)
    if (emailIndex !== -1) {
      emails.value[emailIndex] = {
        ...emails.value[emailIndex],
        vendor_name: data.vendor_name,
        vendor_id: data.vendor_id,
        status: data.status,
        busy: false
      }
    }

    // Show processing modal with invoice data
    currentInvoice.value = data.invoice
    currentInvoice.value.email_id = email_id
    vendorID.value = data.vendor.id
    status.value = data.status
    showProcessingModal.value = true
    tableData.value = data.invoice.tables
    textData.value = data.invoice.text
  } catch (error) {
    email.status = 'error'
    email.busy = false
    console.error('Error processing email:', error)
    alert('Failed to process invoice. ' + errorMessage)
  }
}

async function saveDataRules() {
  if (!activeVendor.value) {
    alert('Please select a vendor first');
    return;
  }

  try {
    // First save the data rules
    await postAPI('/api/data-rules/bulk_create/', {
      vendor_id: activeVendor.value.id,
      rules: dataRules.value
    })

    // Then save the column mappings
    await patchAPI(`/api/vendors/${activeVendor.value.id}/`, {
      spreadsheet_column_mapping: columnMappings.value
    })

    // Update the vendor in the vendors list with new mappings
    const vendorIndex = vendors.value.findIndex(v => v.id === activeVendor.value.id);
    if (vendorIndex !== -1) {
      vendors.value[vendorIndex] = {
        ...vendors.value[vendorIndex],
        data_rules: dataRules.value,
        spreadsheet_column_mapping: columnMappings.value
      };
    }

    showProcessingModal.value = false
    alert('Data rules and column mappings saved successfully')
  } catch (error) {
    console.error('Error saving data:', error)
    alert('Failed to save data. Please try again.')
  }
}

async function loadMore() {
  if (nextPageToken.value) {
    await loadEmails(nextPageToken.value)
  }
}

function onPdfError(error) {
  console.error('PDF Error:', error)
  pdfError.value = error
}

function onPdfLoading() {
  pdfLoading.value = true
}

function onPdfLoaded(pdf) {
  pdfLoading.value = false
  pdfError.value = null

  // Get the PDF scale by comparing the PDF container size to the actual PDF size
  if (pdfContainer.value) {
    const containerWidth = pdfContainer.value.clientWidth
    const pdfWidth = pdf.width
    pdfScale.value = containerWidth / pdfWidth
  }
}

function addDataRule() {
  dataRules.value.push({ ...newRule.value })
  newRule.value = deepClone(defaultRule)
}

function deleteDataRule(index) {
  dataRules.value.splice(index, 1)
}

function editDataRule(rule) {
  newRule.value = deepClone(rule)
  drawingEnabled.value = true
  // Expand the add new rule accordion
  const accordionButton = document.querySelector('#addNewRuleCollapse')
  if (accordionButton) {
    accordionButton.classList.add('show')
  }
}

function handleTableColumnMapping(colName, event) {
  console.log(colName, event)
  const value = event.target.value;
  if (value) {
    newRule.value.table_config.item_columns = {
      ...newRule.value.table_config.item_columns,
      [colName]: value
    }
  } else {
    const { [colName]: _, ...rest } = newRule.value.table_config.item_columns;
    newRule.value.table_config.item_columns = rest;
  }
}

function handleColumnMapping(fieldName, event) {
  if (!activeVendor.value) return;

  const value = event.target.value.toUpperCase();
  if (value.match(/[A-Z]/)) {
    columnMappings.value = {
      ...columnMappings.value,
      [fieldName]: value
    };
  } else if (!value) {
    const { [fieldName]: _, ...rest } = columnMappings.value;
    columnMappings.value = rest;
  }
}

// Add new computed property for the selection box dimensions
const selectionBox = computed(() => {
  // if (!isDrawing.value) return null;

  const width = Math.abs(currentPoint.value.x - startPoint.value.x)
  const height = Math.abs(currentPoint.value.y - startPoint.value.y)
  const left = Math.min(startPoint.value.x, currentPoint.value.x)
  const top = Math.min(startPoint.value.y, currentPoint.value.y)

  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`
  }
})

// Add new methods for bounding box selection
function startDrawing(event) {
  if (!drawingEnabled.value) return;

  // Get the specific PDF container that was clicked
  const container = event.currentTarget;
  if (!container) return;

  const rect = container.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top

  isDrawing.value = true
  startPoint.value = { x, y }
  currentPoint.value = { x, y }
}

function updateDrawing(event) {
  if (!isDrawing.value) return;

  // Get the specific PDF container that was clicked
  const container = event.currentTarget;
  if (!container) return;

  const rect = container.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top

  currentPoint.value = { x, y }
}

function stopDrawing() {
  if (!isDrawing.value) return;
  isDrawing.value = false

  // Update bbox for any rule type
  if (selectionBox.value) {
    // Get the current PDF container's scale
    const container = document.querySelector('.pdf-container')
    if (!container) debugger

    // Get the PDF canvas element
    const canvas = container.querySelector('canvas')
    if (!canvas) debugger

    // Calculate scale based on the actual PDF dimensions vs displayed dimensions
    const containerWidth = container.clientWidth
    const pdfWidth = canvas.width
    const scale = pdfWidth / containerWidth // Inverse of what we had before

    // Convert pixel coordinates to PDF coordinates (scaled)
    newRule.value.bbox = {
      x: Number((Math.min(startPoint.value.x, currentPoint.value.x) * scale).toFixed(2)),
      y: Number((Math.min(startPoint.value.y, currentPoint.value.y) * scale).toFixed(2)),
      width: Number((Math.abs(currentPoint.value.x - startPoint.value.x) * scale).toFixed(2)),
      height: Number((Math.abs(currentPoint.value.y - startPoint.value.y) * scale).toFixed(2))
    }
  }
}

// Add new computed property for the current rule's bounding box
const currentBoundingBox = computed(() => {
  if (!newRule.value?.bbox) return null;

  // Convert PDF coordinates back to screen coordinates
  const container = document.querySelector('.pdf-container')
  if (!container) return null;

  // Get the PDF canvas element
  const canvas = container.querySelector('canvas')
  if (!canvas) return null;

  // Calculate scale based on the actual PDF dimensions vs displayed dimensions
  const containerWidth = container.clientWidth
  const pdfWidth = canvas.width
  const scale = containerWidth / pdfWidth // Inverse for display

  return {
    left: `${newRule.value.bbox.x / scale}px`,
    top: `${newRule.value.bbox.y / scale}px`,
    width: `${newRule.value.bbox.width / scale}px`,
    height: `${newRule.value.bbox.height / scale}px`,
    ruleName: newRule.value.field_name
  }
})

function showDataModal(data) {
  setDisplayData(data)
  _showDataModal.value = true
}

function closeDataModal() {
  _showDataModal.value = false
  displayData.value = null
}

onMounted(() => {
  loadEmails()
  fetchVendors()
})

</script>

<template>
  <q-card>
    <div class="q-pa-md">
      <h2>Invoice Emails</h2>
      <div class="row justify-end q-mb-md">
        <div class="col-auto">
          <div class="row items-center">
            <span class="q-mr-sm">Max Results</span>
            <q-input
              type="number"
              v-model="maxResults"
              min="1"
              max="100"
              dense
              outlined
              class="q-mr-sm"
              style="width: 100px"
            />
            <q-btn
              color="primary"
              @click="loadEmails()"
              :loading="loading"
              :disable="loading"
            >
              {{ loading ? 'Loading...' : 'Reload' }}
            </q-btn>
          </div>
        </div>
      </div>
      <q-list bordered separator>
        <q-item
          v-for="email in emails"
          :key="email.id"
          clickable
          v-ripple
          :class="{
            'bg-negative': email.status === 'error',
            'bg-positive': email.status === 'processed',
            'bg-warning': !email.status || email.status === 'pending'
          }"
          @click="processEmail(email.id)"
        >
          <q-item-section>
            <q-item-label>{{ email.snippet }}</q-item-label>
            <q-item-label caption>
              <div class="row justify-between text-grey-7">
                <div>From: {{ email.from }}</div>
                <div>Vendor: {{ email.vendor_name || 'N/A' }}</div>
                <div>Status: {{ email.status || 'pending' }}</div>
                <div>Date: {{ email.date }}</div>
              </div>
            </q-item-label>
          </q-item-section>
          <q-item-section side v-if="email.busy">
            <q-spinner color="primary" size="sm" />
          </q-item-section>
        </q-item>
      </q-list>
      <div v-if="nextPageToken" class="text-center q-mt-md">
        <q-btn
          color="primary"
          @click="loadMore"
          :loading="loading"
          :disable="loading"
        >
          Load More
        </q-btn>
      </div>
    </div>
  </q-card>

  <!-- Processing Dialog -->
  <q-dialog v-model="showProcessingModal" full-width>
    <q-card>
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">Processing Invoice</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section>
        <div class="row">
          <!-- Left side: PDF iframe -->
          <div class="col-12 col-md-8">
            <q-card>
              <q-card-section>
                <div class="text-h6">Invoice Preview</div>
              </q-card-section>

              <q-card-section class="q-pa-none" style="height: 600px;">
                <div v-if="currentInvoice?.attachments?.length" class="attachments-container">
                  <div v-for="(attachment, index) in currentInvoice.attachments"
                       :key="index"
                       class="attachment-frame">
                    <div class="attachment-header">
                      <h6 class="q-ma-none">
                        <a :href="attachment.url" target="_blank">{{ attachment.filename }}</a>
                      </h6>
                    </div>
                    <div class="pdf-container" ref="pdfContainer"
                         @mousedown="startDrawing"
                         @mousemove="updateDrawing"
                         @mouseup="stopDrawing"
                         @mouseleave="stopDrawing">
                      <VuePdfEmbed
                        :source="attachment.url"
                        :page="1"
                        @error="onPdfError"
                        @loading="onPdfLoading"
                        @loaded="onPdfLoaded"
                      />
                      <div v-if="drawingEnabled" class="drawing-overlay">
                        <div v-if="isDrawing" class="bounding-box active" :style="selectionBox"></div>
                        <div v-if="currentBoundingBox && !isDrawing"
                             class="bounding-box active"
                             :style="currentBoundingBox">
                          <span v-if="currentBoundingBox.ruleName" class="rule-label">{{ currentBoundingBox.ruleName }}</span>
                        </div>
                      </div>
                      <pre>{{ pdfText }}</pre>
                      <div v-if="pdfLoading" class="pdf-loading">
                        <q-spinner color="primary" size="3em" />
                      </div>
                      <div v-if="pdfError" class="pdf-error text-negative">
                        Error loading PDF: {{ pdfError }}
                      </div>
                    </div>
                  </div>
                </div>
                <div v-else class="text-center q-pa-md">
                  No preview available
                </div>
              </q-card-section>
            </q-card>
          </div>

          <!-- Right side: Form controls -->
          <div class="col-12 col-md-4">
            <q-card style="height: 100% ;">
              <q-card-section>
                <div class="text-h6">Data Rules</div>
              </q-card-section>
              <q-card-section class="data-rules-card">
                <q-expansion-item
                  group="dataRules"
                  icon="add"
                  label="Add New Data Rule"
                  default-opened
                >
                  <q-card>
                    <q-card-section>
                      <form @submit.prevent="addDataRule" class="q-gutter-md">
                        <div class="row q-col-gutter-sm">
                          <div class="col-md-6">
                            <q-input
                              v-model="newRule.field_name"
                              label="Field Name"
                              dense
                              outlined
                              required
                            />
                          </div>
                          <div class="col-md-3">
                            <q-select
                              v-model="newRule.data_type"
                              :options="['text', 'number', 'date', 'currency', 'email', 'phone', 'line_items']"
                              label="Data Type"
                              dense
                              outlined
                              required
                            />
                          </div>
                          <div class="col-md-3">
                            <q-select
                              v-model="newRule.location_type"
                              :options="['keyword', 'regex', 'table', 'header']"
                              label="Locator"
                              dense
                              outlined
                              required
                            />
                          </div>
                        </div>

                        <q-btn
                          :color="drawingEnabled ? 'positive' : 'primary'"
                          class="full-width"
                          :icon="drawingEnabled ? 'crosshairs' : 'draw-polygon'"
                          :label="drawingEnabled ? 'Drawing Mode Active - Click to Disable' : 'Enable Drawing Mode'"
                          @click="drawingEnabled = !drawingEnabled"
                        />

                        <div v-if="drawingEnabled" class="row q-col-gutter-sm">
                          <div class="col-3">
                            <q-input
                              v-model="newRule.bbox.x"
                              label="X Position"
                              type="number"
                              dense
                              outlined
                              step="0.01"
                            />
                          </div>
                          <div class="col-3">
                            <q-input
                              v-model="newRule.bbox.y"
                              label="Y Position"
                              type="number"
                              dense
                              outlined
                              step="0.01"
                            />
                          </div>
                          <div class="col-3">
                            <q-input
                              v-model="newRule.bbox.width"
                              label="Width"
                              type="number"
                              dense
                              outlined
                              step="0.01"
                            />
                          </div>
                          <div class="col-3">
                            <q-input
                              v-model="newRule.bbox.height"
                              label="Height"
                              type="number"
                              dense
                              outlined
                              step="0.01"
                            />
                          </div>
                        </div>

                        <div v-if="newRule.location_type === 'keyword'" class="q-mt-sm">
                          <q-input
                            v-model="newRule.keyword"
                            label="Keyword"
                            dense
                            outlined
                          />
                        </div>

                        <div v-if="newRule.location_type === 'regex'" class="q-mt-sm">
                          <q-input
                            v-model="newRule.regex_pattern"
                            label="Regular Expression Pattern"
                            dense
                            outlined
                          />
                        </div>

                        <div v-if="newRule.location_type === 'table'" class="q-mt-sm">
                          <q-input
                            v-model="newRule.table_config.header_text"
                            label="Header Text"
                            dense
                            outlined
                          />
                          <q-input
                            v-model="newRule.table_config.start_row_after_header"
                            label="Start Row After Header"
                            type="number"
                            dense
                            outlined
                            class="q-mt-sm"
                          />
                          <q-btn
                            color="primary"
                            class="q-mt-sm"
                            @click="detectTableColumns(newRule)"
                          >
                            <span v-if="!newRule.table_config?.detected_columns">Detect Columns</span>
                            <span v-else>Re-detect Columns</span>
                          </q-btn>

                          <div v-if="newRule.table_config?.detected_columns" class="q-mt-sm">
                            <div class="text-subtitle2">Map Detected Columns</div>
                            <q-table
                              :rows="newRule.table_config.detected_columns.map((colName, index) => ({
                                colName,
                                index,
                                mapping: newRule.table_config.item_columns[colName] || ''
                              }))"
                              :columns="[
                                { name: 'colName', label: 'Column Name', field: 'colName' },
                                { name: 'mapping', label: 'Map To', field: 'mapping' },
                                { name: 'index', label: 'Index', field: 'index' }
                              ]"
                              dense
                              flat
                              bordered
                            >
                              <template v-slot:body="props">
                                <q-tr :props="props">
                                  <q-td key="colName" :props="props">
                                    {{ props.row.colName }}
                                  </q-td>
                                  <q-td key="mapping" :props="props">
                                    <q-select
                                      v-model="newRule.table_config.item_columns[props.row.colName]"
                                      :options="['', 'id', 'description', 'quantity', 'unit_price', 'total_amount']"
                                      dense
                                      outlined
                                      @update:model-value="value => handleTableColumnMapping(props.row.colName, { target: { value } })"
                                    />
                                  </q-td>
                                  <q-td key="index" :props="props">
                                    {{ props.row.index }}
                                  </q-td>
                                </q-tr>
                              </template>
                            </q-table>
                          </div>
                        </div>

                        <div class="row q-mt-md">
                          <div class="col">
                            <q-btn
                              color="negative"
                              class="q-mr-sm"
                              @click="testDataRule(newRule)"
                            >
                              Test Rule
                            </q-btn>
                            <q-btn
                              type="submit"
                              color="primary"
                            >
                              Add Rule
                            </q-btn>
                          </div>
                        </div>
                      </form>
                    </q-card-section>
                  </q-card>
                </q-expansion-item>

                <q-expansion-item
                  group="dataRules"
                  icon="list"
                  :label="`Existing Rules (${dataRules.length})`"
                >
                  <q-card>
                    <q-card-section>
                      <q-table
                        :rows="dataRules"
                        :columns="[
                          { name: 'field_name', label: 'Field Name', field: 'field_name' },
                          { name: 'data_type', label: 'Type', field: 'data_type' },
                          { name: 'location_type', label: 'Location', field: 'location_type' },
                          { name: 'required', label: 'Required', field: 'required' },
                          { name: 'actions', label: 'Actions', field: 'actions' }
                        ]"
                        dense
                        flat
                        bordered
                      >
                        <template v-slot:body="props">
                          <q-tr :props="props">
                            <q-td key="field_name" :props="props">
                              {{ props.row.field_name }}
                            </q-td>
                            <q-td key="data_type" :props="props">
                              <q-badge color="secondary">{{ props.row.data_type }}</q-badge>
                            </q-td>
                            <q-td key="location_type" :props="props">
                              <q-badge color="info">{{ props.row.location_type }}</q-badge>
                            </q-td>
                            <q-td key="required" :props="props">
                              <q-icon
                                :name="props.row.required ? 'check_circle' : 'cancel'"
                                :color="props.row.required ? 'positive' : 'negative'"
                              />
                            </q-td>
                            <q-td key="actions" :props="props">
                              <q-btn
                                flat
                                round
                                color="primary"
                                icon="play_arrow"
                                @click="testDataRule(props.row)"
                              >
                                <q-tooltip>Test this rule</q-tooltip>
                              </q-btn>
                              <q-btn
                                flat
                                round
                                color="secondary"
                                icon="edit"
                                @click="editDataRule(props.row)"
                              >
                                <q-tooltip>Edit this rule</q-tooltip>
                              </q-btn>
                              <q-btn
                                flat
                                round
                                color="negative"
                                icon="delete"
                                @click="deleteDataRule(props.rowIndex)"
                              >
                                <q-tooltip>Delete this rule</q-tooltip>
                              </q-btn>
                            </q-td>
                          </q-tr>
                        </template>
                      </q-table>
                    </q-card-section>
                  </q-card>
                </q-expansion-item>

                <q-expansion-item
                  v-if="dataRules.length > 0"
                  group="dataRules"
                  icon="table_chart"
                  label="Spreadsheet Column Mapping"
                >
                  <q-card>
                    <q-card-section>
                      <q-table
                        :rows="dataRules"
                        :columns="[
                          { name: 'field_name', label: 'Field Name', field: 'field_name' },
                          { name: 'column', label: 'Column', field: 'column' }
                        ]"
                        dense
                        flat
                        bordered
                      >
                        <template v-slot:body="props">
                          <q-tr :props="props">
                            <q-td key="field_name" :props="props">
                              {{ props.row.field_name }}
                            </q-td>
                            <q-td key="column" :props="props">
                              <q-input
                                v-model="columnMappings[props.row.field_name]"
                                dense
                                outlined
                                placeholder="A-Z"
                                pattern="[A-Za-z]"
                                maxlength="1"
                                @update:model-value="value => handleColumnMapping(props.row.field_name, { target: { value } })"
                              />
                            </q-td>
                          </q-tr>
                        </template>
                      </q-table>
                    </q-card-section>
                  </q-card>
                </q-expansion-item>
              </q-card-section>
            </q-card>
          </div>
        </div>
      </q-card-section>

      <q-card-actions>
        <div class="row full-width justify-between">
          <div class="col-auto">
            <q-btn
              v-if="tableData && tableData.length > 0"
              flat
              color="primary"
              @click="showDataModal('Table Data')"
            >
              Show Table Data
            </q-btn>
            <q-btn
              v-if="textData && textData.length > 0"
              flat
              color="primary"
              @click="showDataModal('Text Data')"
            >
              Show Text Data
            </q-btn>
          </div>
          <div class="col-auto">
            <div class="row items-center">
              <span class="q-mr-sm">Vendor:</span>
              <q-select
                v-model="vendorID"
                :options="vendors"
                :clearable="false"
                placeholder="Select a vendor"
                dense
                outlined
                class="q-mr-sm"
                style="width: 200px"
              />
            </div>
          </div>
          <div class="col-auto">
            <q-btn
              color="secondary"
              class="q-mr-sm"
              @click="processEmail(currentInvoice.email_id)"
            >
              <q-icon name="rotate_left" class="q-mr-sm" />
              Re-process
            </q-btn>
            <q-btn
              color="info"
              class="q-mr-sm"
              @click="saveToGoogleSheet"
            >
              Save to Google Sheet
            </q-btn>
            <q-btn
              color="primary"
              @click="saveDataRules"
            >
              Save Invoice Data Rules
            </q-btn>
          </div>
        </div>
      </q-card-actions>
    </q-card>
  </q-dialog>

  <!-- Data Modal -->
  <q-dialog v-model="_showDataModal" full-width>
    <q-card>
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ modalTitle }}</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section>
        <div class="scroll">
          <code class="block">
            <pre class="q-pa-md bg-grey-2 rounded-borders">
              {{ displayData }}
            </pre>
          </code>
        </div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Close" color="primary" v-close-popup />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<style lang="scss">
@use 'quasar/src/css/variables.sass' as *;

// Thin scrollbar mixin
@mixin thin-scrollbar {
  &::-webkit-scrollbar {
    width: 4px;
    height: 4px;
  }

  &::-webkit-scrollbar-track {
    background: $grey-3;
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: $grey-7;
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: $grey-8;
  }
}

// Apply thin scrollbar to all scrollable elements
* {
  @include thin-scrollbar;
}

.q-item {
  cursor: pointer;
  transition: background-color 0.3s ease;

  &:hover {
    background-color: $grey-2;
  }
}

.attachments-container {
  height: 100%;
  overflow-y: auto;
  padding: 1rem;
}

.attachment-frame {
  margin-bottom: 1rem;
  border: 1px solid $grey-4;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
}

.attachment-header {
  padding: 0.5rem 1rem;
  background-color: $grey-2;
  border-bottom: 1px solid $grey-4;
}

.attachment-frame iframe {
  flex: 1;
  border: none;
}

.drawing-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 10;
}

.pdf-container {
  position: relative;
  height: 100%;
  min-height: 500px;
  overflow: auto;
  background-color: $grey-2;

  &:has(.drawing-overlay) {
    cursor: crosshair;
  }
}

.pdf-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.pdf-error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  padding: 1rem;
}

.bounding-box {
  position: absolute;
  border: 2px solid $positive;
  background-color: rgba($positive, 0.1);
  pointer-events: none;

  .rule-label {
    position: absolute;
    top: -20px;
    left: 0;
    background-color: $positive;
    color: white;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.75rem;
    white-space: nowrap;
  }
}

.data-rules-card {
  .q-table {
    th {
      font-size: 0.8rem;
      line-height: 1;
    }

    td {
      font-size: 0.9rem;
      line-height: 1;
      vertical-align: middle;
    }
  }
}

.vue-select {
  padding: 0 !important;
  --vs-option-font-size: 0.9rem !important;
  --vs-font-size: 0.9rem !important;
  --vs-min-height: 28px !important;
  --vs-indicator-icon-size: 23px !important;

  .value-container {
    padding: 0.15rem 0.5rem !important;
  }
}
</style>
