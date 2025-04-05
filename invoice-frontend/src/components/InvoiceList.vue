<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import VuePdfEmbed from 'vue-pdf-embed'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { Tooltip } from 'bootstrap'
import { deepClone } from '../utils/objectUtils'


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
    const url = new URL('http://localhost:8000/api/emails/')
    if (pageToken) {
      url.searchParams.append('pageToken', pageToken)
    }
    url.searchParams.append('maxResults', maxResults.value)
    const res = await fetch(url, {
      signal: abortController.value.signal
    })
    const data = await res.json()
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
    const res = await fetch('http://localhost:8000/api/vendors/')
    var data = await res.json()
    // Add label and value props for v-select component
    data = data.map(vendor => ({
      ...vendor,
      label: vendor.name,
      value: vendor.id
    }))
    vendors.value = data || []
  } catch (error) {
    console.error('Error fetching vendors:', error)
  }
}

async function processEmail(email_id) {

  const email = emails.value.find(e => e.id === email_id)
  email.busy = true
  let errorMessage = null

  // const email = emails.value.find(e => e.id === email_id)
  // if (email.status === 'error') {
  //   alert('This email has an error status and cannot be processed. Please check the email details.')
  //   return
  // }

  try {
    const res = await fetch('http://localhost:8000/api/process-email/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email_id })
    })

    const data = await res.json()
    if (data.status === 'error') {
      email.status = 'error'
      email.busy = false
      errorMessage = data.message
      // throw new Error(errorMessage)
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
    const res = await fetch('http://localhost:8000/api/data-rules/bulk_create/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        vendor_id: activeVendor.value.id,
        rules: dataRules.value
      })
    })

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`)
    }

    // Then save the column mappings
    const vendorRes = await fetch(`http://localhost:8000/api/vendors/${activeVendor.value.id}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        spreadsheet_column_mapping: columnMappings.value
      })
    })

    if (!vendorRes.ok) {
      throw new Error(`HTTP error! status: ${vendorRes.status}`)
    }

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
  <div class="container mt-4">
    <h2>Invoice Emails</h2>

    <div class="row justify-content-end mb-3">
      <div class="col-auto">
        <div class="input-group">
          <span class="input-group-text">Max Results</span>
          <input type="number" class="form-control" v-model="maxResults" min="1" max="100">
          <button class="btn btn-primary" @click="loadEmails()" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
            {{ loading ? 'Loading...' : 'Reload' }}
          </button>
        </div>
      </div>
    </div>

    <div class="list-group">
      <div v-for="email in emails"
        :key="email.id"
        :class="{
          'list-group-item list-group-item-action row mx-0': true,
          'list-group-item-danger': email.status === 'error',
          'list-group-item-success': email.status === 'processed',
          'list-group-item-warning': !email.status || email.status === 'pending'
        }"
        @click="processEmail(email.id)"
      >
        <div class="col-12 header">
          {{ email.snippet }}
          <!-- <div class="col-auto">
            <button class="btn btn-outline-primary btn-sm"
                    @click="downloadAttachments(email.id, $event)">
              <font-awesome-icon icon="paperclip" class="me-1" />
              {{ email.attachment_count }} attachments
            </button>
          </div> -->
        </div>
        <div class="mt-2 row col-12 justify-content-between text-muted footer">
          <div class="col-auto">From: {{ email.from }}</div>
          <div class="col-auto">Vendor: {{ email.vendor_name || 'N/A' }}</div>
          <div class="col-auto">Status: {{ email.status || 'pending' }}</div>
          <div class="col-auto">Date: {{ email.date }}</div>
        </div>
        <div v-if="email.busy" class="col-12">
          <div class="d-flex justify-content-center">
            <div class="spinner-border spinner-border-sm text-primary" role="status">
              <span class="visually-hidden">Loading...</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="nextPageToken" class="text-center mt-3">
      <button @click="loadMore"
              class="btn btn-primary"
              :disabled="loading">
        Load More
      </button>
    </div>


    <!-- Processing Modal -->
    <div v-if="showProcessingModal" id="processing-modal" class="modal show d-block" tabindex="-1">
      <div class="modal-dialog modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Processing Invoice</h5>

            <button type="button" class="btn-close" @click="showProcessingModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="row">

              <!-- Left side: PDF iframe -->
              <div class="col-12 col-md-8">
                <div class="card">
                  <div class="card-header">
                    <div class="row">
                      <div class="col">
                        <h6 class="mb-0">Invoice Preview</h6>
                      </div>
                    </div>
                  </div>

                  <div class="card-body p-0" style="height: 600px;">
                    <div v-if="currentInvoice?.attachments?.length" class="attachments-container">
                      <div v-for="(attachment, index) in currentInvoice.attachments"
                           :key="index"
                           class="attachment-frame">
                        <div class="attachment-header">
                          <h6 class="mb-0"><a :href="attachment.url" target="_blank">{{ attachment.filename }}</a></h6>
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
                          ></VuePdfEmbed>
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
                            <div class="spinner-border text-primary" role="status">
                              <span class="visually-hidden">Loading PDF...</span>
                            </div>
                          </div>
                          <div v-if="pdfError" class="pdf-error text-danger">
                            Error loading PDF: {{ pdfError }}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div v-else class="p-3 text-center">
                      No preview available
                    </div>
                  </div>
                </div>
              </div>

              <!-- Right side: Form controls -->
              <div class="col-12 col-md-4">
                <div class="card">
                  <div class="card-header">
                    <h6 class="mb-0">Data Rules</h6>
                  </div>
                  <div class="card-body data-rules-card">
                    <div class="accordion" id="dataRulesAccordion">
                      <!-- Add New Data Rule Accordion Item -->
                      <div class="accordion-item">
                        <h2 class="accordion-header">
                          <button class="accordion-button" type="button" data-bs-toggle="collapse" data-bs-target="#addNewRuleCollapse">
                            Add New Data Rule
                          </button>
                        </h2>

                        <!-- DataRule editor -->
                        <div id="addNewRuleCollapse" class="accordion-collapse collapse show" data-bs-parent="#dataRulesAccordion">
                          <div class="accordion-body">
                            <form @submit.prevent="addDataRule" class="mb-3">
                              <div class="row no-gutters px-2">
                                <div class="col-md-6 px-1">
                                  <label class="form-label small">Field Name</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.field_name" required>
                                </div>
                                <div class="col-md-3 px-1">
                                  <label class="form-label small">Data Type</label>
                                  <select class="form-select form-select-sm" v-model="newRule.data_type" required>
                                    <option value="text">Text</option>
                                    <option value="number">Number</option>
                                    <option value="date">Date</option>
                                    <option value="currency">Currency</option>
                                    <option value="email">Email</option>
                                    <option value="phone">Phone</option>
                                    <option value="line_items">Line Items</option>
                                  </select>
                                </div>
                                <div class="col-md-3 px-1">
                                  <label class="form-label small">Locator</label>
                                  <select class="form-select form-select-sm" v-model="newRule.location_type" required>
                                    <option value="keyword">Keyword</option>
                                    <option value="regex">Regular Expression</option>
                                    <option value="table">Table</option>
                                    <option value="header">Header</option>
                                  </select>
                                </div>
                              </div>

                              <!-- Drawing mode toggle button -->
                              <div class="row mt-2">
                                <div class="col-12">
                                  <button
                                    type="button"
                                    class="btn w-100 btn-sm"
                                    :class="drawingEnabled ? 'btn-success' : 'btn-outline-primary'"
                                    @click="drawingEnabled = !drawingEnabled"
                                  >
                                    <font-awesome-icon :icon="drawingEnabled ? 'crosshairs' : 'draw-polygon'" class="me-2" />
                                    {{ drawingEnabled ? 'Drawing Mode Active - Click to Disable' : 'Enable Drawing Mode' }}
                                  </button>
                                </div>
                              </div>

                              <!-- Add coordinates section for all rules -->
                              <div v-if="drawingEnabled" class="row no-gutters mt-2 px-2">
                                <div class="col-3 px-1">
                                  <label class="form-label small">X Position</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.bbox.x" placeholder="X" step="0.01">
                                </div>
                                <div class="col-3 px-1">
                                  <label class="form-label small">Y Position</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.bbox.y" placeholder="Y" step="0.01">
                                </div>
                                <div class="col-3 px-1">
                                  <label class="form-label small">Width</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.bbox.width" placeholder="Width" step="0.01">
                                </div>
                                <div class="col-3 px-1">
                                  <label class="form-label small">Height</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.bbox.height" placeholder="Height" step="0.01">
                                </div>
                              </div>

                              <!-- Add other rule-specific sections -->
                              <div class="row mt-2" v-if="newRule.location_type === 'keyword'">
                                <div class="col-12">
                                  <label class="form-label small">Keyword</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.keyword" placeholder="Enter keyword">
                                </div>
                              </div>

                              <div class="row mt-2" v-if="newRule.location_type === 'regex'">
                                <div class="col-12">
                                  <label class="form-label small">Regular Expression Pattern</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.regex_pattern" placeholder="Enter regex pattern">
                                </div>
                              </div>

                              <div class="row mt-2" v-if="newRule.location_type === 'table'">
                                <div class="col-12 mb-2">
                                  <label class="form-label small">Header Text</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.table_config.header_text" placeholder="Header Text">
                                </div>
                                <div class="col-12 mb-2">
                                  <label class="form-label small">Start Row After Header</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.table_config.start_row_after_header" placeholder="Start Row">
                                </div>
                                <div class="col-12 mb-2">
                                  <button type="button" class="btn btn-outline-primary btn-sm" @click="detectTableColumns(newRule)">
                                    <span v-if="!newRule.table_config?.detected_columns">Detect Columns</span>
                                    <span v-else>Re-detect Columns</span>
                                  </button>
                                </div>
                                <div v-if="newRule.table_config?.detected_columns" class="col-12">
                                  <label class="form-label small">Map Detected Columns</label>
                                  <div class="table-responsive">
                                    <table class="table table-sm">
                                      <thead>
                                        <tr>
                                          <th>Column Name</th>
                                          <th>Map To</th>
                                          <th>Index</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        <tr v-for="(colName, index) in newRule.table_config.detected_columns" :key="colName">
                                          <td>{{ colName }}</td>
                                          <td>
                                            <select class="form-select form-select-sm"
                                              :value="newRule.table_config.item_columns[colName]"
                                              @change="e => handleTableColumnMapping(colName, e)">
                                              <option value="">Not Used</option>
                                              <option value="id">ID</option>
                                              <option value="description">Description</option>
                                              <option value="quantity">Quantity</option>
                                              <option value="unit_price">Unit Price</option>
                                              <option value="total_amount">Total Amount</option>
                                            </select>
                                          </td>
                                          <td>{{ index }}</td>
                                        </tr>
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              </div>

                              <!-- <div class="row mt-2">
                                <div class="col-12">
                                  <div class="form-check form-check-inline">
                                    <input type="checkbox" class="form-check-input" v-model="newRule.required">
                                    <label class="form-check-label small">Required Field</label>
                                  </div>
                                </div>
                              </div> -->

                              <div class="row mt-2">
                                <div class="col-12">
                                  <button type="button" class="btn btn-outline-danger btn-sm" @click="testDataRule(newRule)">Test Rule</button>
                                  <button type="submit" class="btn btn-primary btn-sm">Add Rule</button>
                                </div>
                              </div>


                            </form>
                          </div>
                        </div>
                      </div>

                      <!-- Existing Rules Accordion Item -->
                      <div class="accordion-item">
                        <h2 class="accordion-header">
                          <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#existingRulesCollapse">
                            <div class="w-100">
                              Existing Rules
                              <span v-if="dataRules.length > 0" class="badge bg-primary mx-2 float-end">{{ dataRules.length }}</span>
                            </div>
                          </button>
                        </h2>

                        <div id="existingRulesCollapse" class="accordion-collapse collapse" data-bs-parent="#dataRulesAccordion">
                          <div class="accordion-body">
                            <div class="table-responsive">
                              <table class="table table-sm table-hover">
                                <thead>
                                  <tr>
                                    <th>Field Name</th>
                                    <th>Type</th>
                                    <th>Location</th>
                                    <th>Required</th>
                                    <th class="text-end">Actions</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  <tr v-for="(rule, index) in dataRules" :key="index">
                                    <td>{{ rule.field_name }}</td>
                                    <td><span class="badge bg-secondary">{{ rule.data_type }}</span></td>
                                    <td><span class="badge bg-info">{{ rule.location_type }}</span></td>
                                    <td>
                                      <font-awesome-icon :icon="rule.required ? 'check-circle' : 'times-circle'"
                                        :class="rule.required ? 'text-success' : 'text-danger'" />
                                    </td>
                                    <td class="text-end">
                                      <font-awesome-icon
                                        icon="play"
                                        class="text-primary mx-1"
                                        style="cursor: pointer"
                                        data-bs-toggle="tooltip"
                                        data-bs-placement="top"
                                        title="Test this rule"
                                        @click="testDataRule(rule)"
                                      ></font-awesome-icon>
                                      <font-awesome-icon
                                        icon="edit"
                                        class="text-secondary mx-1"
                                        style="cursor: pointer"
                                        data-bs-toggle="tooltip"
                                        data-bs-placement="top"
                                        title="Edit this rule"
                                        @click="editDataRule(rule)"
                                      ></font-awesome-icon>
                                      <font-awesome-icon
                                        icon="trash"
                                        class="text-danger mx-1"
                                        style="cursor: pointer"
                                        data-bs-toggle="tooltip"
                                        data-bs-placement="top"
                                        title="Delete this rule"
                                        @click="deleteDataRule(index)"
                                      ></font-awesome-icon>
                                    </td>
                                  </tr>
                                </tbody>
                              </table>
                            </div>
                          </div>
                        </div>
                      </div>


                      <div class="accordion-item" v-if="dataRules.length > 0">
                        <h2 class="accordion-header">
                          <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#spreadsheetColumnMappingCollapse">
                            Spreadsheet Column Mapping
                          </button>
                        </h2>

                        <div id="spreadsheetColumnMappingCollapse" class="accordion-collapse collapse" data-bs-parent="#dataRulesAccordion">
                          <div class="accordion-body">
                            <div class="table-responsive">
                              <table class="table table-sm table-hover">
                                <thead>
                                  <tr>
                                    <th>Field Name</th>
                                    <th>Column</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  <tr v-for="rule in dataRules" :key="rule.field_name">
                                    <td>{{ rule.field_name }}</td>
                                    <td>
                                      <input
                                        type="text"
                                        class="form-control form-control-sm"
                                        :value="columnMappings[rule.field_name]"
                                        placeholder="A-Z"
                                        pattern="[A-Za-z]"
                                        maxlength="1"
                                        @input="e => handleColumnMapping(rule.field_name, e)"
                                      >
                                    </td>
                                  </tr>
                                </tbody>
                              </table>
                            </div>
                          </div>
                        </div>
                      </div>


                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <div class="row">
              <div class="col-auto">

              <button type="button"
                v-if="tableData && tableData.length > 0"
                class="btn btn-link"
                @click="showDataModal('Table Data')"
              >
                Show Table Data
              </button>
              <button type="button"
                v-if="textData && textData.length > 0"
                class="btn btn-link"
                @click="showDataModal('Text Data')"
              >
                Show Text Data
              </button>

              <!-- Shared Modal -->
              <div
                v-if="_showDataModal"
                class="modal fade show d-block"
                tabindex="-1"
                role="dialog"
              >
                <div class="modal-dialog modal-xl modal-dialog-scrollable">
                  <div class="modal-content">
                    <div class="modal-header">
                      <h5 class="modal-title">{{ modalTitle }}</h5>
                      <button type="button" class="btn-close" @click="closeDataModal"></button>
                    </div>
                    <div class="modal-body">
                      <div class="table-responsive">
                        <code class="d-block">
                          <pre class="mb-0">
                            {{ displayData }}
                          </pre>
                        </code>
                      </div>
                    </div>
                    <div class="modal-footer">
                      <button
                        type="button"
                        class="btn btn-secondary"
                        @click="closeDataModal"
                      >
                        Close
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              </div>
              <div class="col-auto">
                <div class="d-flex flex-row align-items-center">
                  <label class="form-label small">Vendor:</label>
                  <v-select
                    v-model="vendorID"
                    :options="vendors"
                    :is-clearable="false"
                    placeholder="Select a vendor"
                    class="form-select-sm"
                  />
                </div>
              </div>
              <div class="col">
                <button type="button" class="btn btn-secondary btn-sm" @click="processEmail(currentInvoice.email_id)">
                  <font-awesome-icon icon="rotate-left" />
                  Re-process
                </button>
                <button type="button" class="btn btn-info btn-sm" @click="saveToGoogleSheet">Save to Google Sheet</button>
                <button type="button" class="btn btn-primary btn-sm" @click="saveDataRules">Save Invoice Data Rules</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showProcessingModal" class="modal-backdrop show"></div>
  </div>
</template>


<style lang="scss">
// Thin scrollbar mixin
@mixin thin-scrollbar {
  &::-webkit-scrollbar {
    width: 4px;
    height: 4px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: #555;
  }
}

// Apply thin scrollbar to all scrollable elements
* {
  @include thin-scrollbar;
}

.list-group-item {
  cursor: pointer;
}

.list-group-item:hover {
  background-color: #f8f9fa;
}

.header {
  font-weight: bold;
}

.footer {
  font-size: 0.8rem;
}

.modal-backdrop {
  background-color: rgba(0, 0, 0, 0.5);
}

.modal {
  background-color: rgba(0, 0, 0, 0.5);
}

.btn-outline-primary {
  border-width: 1px;
  padding: 0.25rem 0.75rem;
  font-size: 0.875rem;
}

.modal-xl {
  max-width: 90%;
}

.card {
  height: 100%;
}

.card-body {
  overflow-y: auto;
}

.attachments-container {
  height: 100%;
  overflow-y: auto;
  padding: 1rem;
}

.attachment-frame {
  margin-bottom: 1rem;
  border: 1px solid #dee2e6;
  border-radius: 0.25rem;
  display: flex;
  flex-direction: column;
}

.attachment-header {
  padding: 0.5rem 1rem;
  background-color: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
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

.selection-box {
  position: absolute;
  border: 2px solid #007bff;
  background-color: rgba(0, 123, 255, 0.1);
  pointer-events: none;
}

// Add cursor styles for drawing mode
.pdf-container {
  position: relative;
  height: 100%;
  min-height: 500px;
  overflow: auto;
  background-color: #f8f9fa;

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

.accordion-body {
  padding: 0.75rem 0.5rem !important;
}

.data-rules-card {
  .table {
    th {
      font-size: 8pt;
      line-height: 1;
    }

    td {
      font-size: 9pt;
      line-height: 1;
      vertical-align: middle;
    }
  }

  label {
    font-size: 8pt;
    line-height: 1;
  }
}

.vue-select {
  padding: 0 !important;
  --vs-option-font-size: 9pt !important;
  --vs-font-size: 9pt !important;
  --vs-min-height: 28px !important;
  --vs-indicator-icon-size: 23px !important;

  .value-container {
    padding: 0.15rem 0.5rem !important;
  }

}

.bounding-box {
  position: absolute;
  border: 2px solid #28a745;
  background-color: rgba(40, 167, 69, 0.1);
  pointer-events: none;

  .rule-label {
    position: absolute;
    top: -20px;
    left: 0;
    background-color: #28a745;
    color: white;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.75rem;
    white-space: nowrap;
  }
}

.modal-body {
  pre {
    white-space: pre-wrap;
    word-wrap: break-word;
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 0.25rem;
  }
}
</style>
