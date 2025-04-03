<script setup>
import { ref, onMounted, watch } from 'vue'
import VuePdfEmbed from 'vue-pdf-embed'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { Tooltip } from 'bootstrap'
import vSelect from 'vue-select'
import 'vue-select/dist/vue-select.css'

const emails = ref([])
const nextPageToken = ref(null)
const loading = ref(false)
const selectedEmail = ref(null)
const attachments = ref([])
const showAttachmentsModal = ref(false)
const downloadingAttachment = ref(false)
const showProcessingModal = ref(false)
const currentInvoice = ref(null)
const dataRules = ref([])
const vendorName = ref('')
const status = ref('')
const pdfError = ref(null)
const pdfLoading = ref(false)
const pdfText = ref('')
const maxResults = ref(10)
const extractedData = ref({})
const vendors = ref([])
const newRule = ref({
  field_name: '',
  data_type: '',
  location_type: '',
  required: false
})

// Watch for maxResults changes
watch(maxResults, () => {
  console.log('maxResults changed', maxResults.value)
  loadEmails()
}, { debounce: 5000 })

// Watch for location_type changes and initialize appropriate properties
watch(() => newRule.value.location_type, (newType) => {
  // Clear all location-specific properties
  delete newRule.value.coordinates
  delete newRule.value.keyword
  delete newRule.value.regex_pattern
  delete newRule.value.table_config

  // Initialize properties based on location type
  switch (newType) {
    case 'coordinates':
      newRule.value.coordinates = {
        x: 0,
        y: 0,
        width: 0,
        height: 0
      }
      break
    case 'keyword':
      newRule.value.keyword = ''
      break
    case 'regex':
      newRule.value.regex_pattern = ''
      break
    case 'table':
      newRule.value.table_config = {
        row_index: 0,
        col_index: 0,
        header_text: ''
      }
      break
    case 'header':
      // No additional properties needed for header type
      break
  }
})

function testDataRule(rule) {
  if (!currentInvoice.value?.attachments?.[0]?.filename) {
    alert('No PDF file available to test the rule')
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
      alert(`Rule test result: ${JSON.stringify(data.result, null, 2)}`)
    }
  })
  .catch(error => {
    console.error('Error testing rule:', error)
    alert('Failed to test rule. Please try again.')
  })
}

async function loadEmails(pageToken = null) {
  loading.value = true
  try {
    const url = new URL('http://localhost:8000/api/emails/')
    if (pageToken) {
      url.searchParams.append('pageToken', pageToken)
    }
    url.searchParams.append('maxResults', maxResults.value)
    const res = await fetch(url)
    const data = await res.json()
    // Add status property to each email object
    data.emails = data.emails.map(email => ({
      ...email,
      status: email.status || 'pending', // Default to 'pending' if no status
      busy: false,
    }))

    if (pageToken) {
      emails.value = [...emails.value, ...data.emails]
    } else {
      emails.value = data.emails
    }
    nextPageToken.value = data.nextPageToken
  } catch (error) {
    console.error('Error loading emails:', error)
  } finally {
    loading.value = false
  }
}

async function fetchVendors() {
  try {
    const res = await fetch('http://localhost:8000/api/vendors/')
    const data = await res.json()
    vendors.value = data || []
  } catch (error) {
    console.error('Error fetching vendors:', error)
  }
}

onMounted(() => {
  loadEmails()
  fetchVendors()

  // Initialize Bootstrap tooltips
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new Tooltip(tooltipTriggerEl)
  })
})

async function processEmail(email_id, event) {
  // Prevent processing if clicking on attachments button
  if (event && event.target.closest('.btn-outline-primary')) {
    return
  }
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
        status: data.status
      }
    }

    email.busy = false

    // Show processing modal with invoice data
    currentInvoice.value = data.invoice
    vendorName.value = data.vendor_name
    status.value = data.status
    showProcessingModal.value = true
  } catch (error) {
    email.status = 'error'
    email.busy = false
    console.error('Error processing email:', error)
    alert('Failed to process invoice. ' + errorMessage)
  }
}

async function saveDataRules() {
  try {
    const res = await fetch('http://localhost:8000/api/data-rules/bulk_create/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        vendor_name: vendorName.value,
        rules: dataRules.value
      })
    })

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`)
    }

    const data = await res.json()
    showProcessingModal.value = false
    alert('Data rules saved successfully')
  } catch (error) {
    console.error('Error saving data rules:', error)
    alert('Failed to save data rules. Please try again.')
  }
}

async function downloadAttachments(email_id, event) {
  event.stopPropagation() // Prevent click from bubbling up
  selectedEmail.value = email_id
  showAttachmentsModal.value = true
  attachments.value = []
  try {
    const res = await fetch(`http://localhost:8000/api/emails/${email_id}/attachments/`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    })
    const data = await res.json()
    attachments.value = data.attachments
  } catch (error) {
    console.error('Error downloading attachments:', error)
    alert('Failed to load attachments. Please try again.')
  }
}

async function downloadFile(url, filename) {
  downloadingAttachment.value = true
  try {
    // Open the file in a new tab
    window.open(url, '_blank')
  } catch (error) {
    console.error('Error downloading file:', error)
    alert('Failed to download file. Please try again.')
  } finally {
    downloadingAttachment.value = false
  }
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
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
}

function addDataRule() {
  dataRules.value.push({ ...newRule.value })
  newRule.value = {}
}

function deleteDataRule(index) {
  dataRules.value.splice(index, 1)
}

function editDataRule(rule) {
  newRule.value = JSON.parse(JSON.stringify(rule))
  // Expand the add new rule accordion
  const accordionButton = document.querySelector('#addNewRuleCollapse')
  if (accordionButton) {
    accordionButton.classList.add('show')
  }
}
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
        @click="processEmail(email.id, $event)"
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

    <!-- Attachments Modal -->
    <div v-if="showAttachmentsModal" class="modal show d-block" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Email Attachments</h5>
            <button type="button" class="btn-close" @click="showAttachmentsModal = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="attachments.length === 0" class="text-center">
              <p>No attachments found</p>
            </div>
            <div v-else class="list-group">
              <div v-for="attachment in attachments"
                   :key="attachment.filename"
                   class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                  <h6 class="mb-0">{{ attachment.filename }}</h6>
                  <small class="text-muted">{{ formatFileSize(attachment.size) }}</small>
                </div>
                <button class="btn btn-sm btn-primary"
                        @click="downloadFile(attachment.url, attachment.filename)"
                        :disabled="downloadingAttachment">
                  <span v-if="downloadingAttachment" class="spinner-border spinner-border-sm me-1"></span>
                  Download
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showAttachmentsModal" class="modal-backdrop show"></div>


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
                      <div class="col-4">
                        <div class="d-flex flex-row align-items-center">
                          <label class="form-label small">Vendor:</label>
                          <v-select
                            v-model="vendorName"
                            :options="vendors"
                            :clearable="false"
                            label="name"
                            placeholder="Select a vendor"
                            class="form-select-sm"
                          />
                        </div>
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
                        <div class="pdf-container">
                          <VuePdfEmbed
                            :source="attachment.url"
                            :page="1"
                            @error="onPdfError"
                            @loading="onPdfLoading"
                            @loaded="onPdfLoaded"
                          ></VuePdfEmbed>
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
                  <div class="card-body">
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
                              <div class="row g-2">
                                <div class="col-md-6">
                                  <label class="form-label small">Field Name</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.field_name" required>
                                </div>
                                <div class="col-md-3">
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
                                <div class="col-md-3">
                                  <label class="form-label small">Locator</label>
                                  <select class="form-select form-select-sm" v-model="newRule.location_type" required>
                                    <option value="coordinates">Coordinates</option>
                                    <option value="keyword">Keyword</option>
                                    <option value="regex">Regular Expression</option>
                                    <option value="table">Table</option>
                                    <option value="header">Header</option>
                                  </select>
                                </div>
                              </div>

                              <div class="row g-2 mt-2" v-if="newRule.location_type === 'coordinates'">
                                <div class="col-3">
                                  <label class="form-label small">X Position</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.coordinates.x" placeholder="X" step="0.1">
                                </div>
                                <div class="col-3">
                                  <label class="form-label small">Y Position</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.coordinates.y" placeholder="Y" step="0.1">
                                </div>
                                <div class="col-3">
                                  <label class="form-label small">Width</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.coordinates.width" placeholder="Width" step="0.1">
                                </div>
                                <div class="col-3">
                                  <label class="form-label small">Height</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.coordinates.height" placeholder="Height" step="0.1">
                                </div>
                              </div>

                              <div class="row g-2 mt-2" v-if="newRule.location_type === 'keyword'">
                                <div class="col-12">
                                  <label class="form-label small">Keyword</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.keyword" placeholder="Enter keyword">
                                </div>
                              </div>

                              <div class="row g-2 mt-2" v-if="newRule.location_type === 'regex'">
                                <div class="col-12">
                                  <label class="form-label small">Regular Expression Pattern</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.regex_pattern" placeholder="Enter regex pattern">
                                </div>
                              </div>

                              <div class="row g-2 mt-2" v-if="newRule.location_type === 'table'">
                                <div class="col-4">
                                  <label class="form-label small">Row Index</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.table_config.row_index" placeholder="Row Index">
                                </div>
                                <div class="col-4">
                                  <label class="form-label small">Column Index</label>
                                  <input type="number" class="form-control form-control-sm" v-model="newRule.table_config.col_index" placeholder="Column Index">
                                </div>
                                <div class="col-4">
                                  <label class="form-label small">Header Text</label>
                                  <input type="text" class="form-control form-control-sm" v-model="newRule.table_config.header_text" placeholder="Header Text">
                                </div>
                              </div>

                              <div class="row g-2 mt-2">
                                <div class="col-12">
                                  <div class="form-check form-check-inline">
                                    <input type="checkbox" class="form-check-input" v-model="newRule.required">
                                    <label class="form-check-label small">Required Field</label>
                                  </div>
                                </div>
                              </div>

                              <div class="row g-2 mt-2">
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
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showProcessingModal = false">Cancel</button>
            <button type="button" class="btn btn-primary" @click="saveDataRules">Save Config and Update Google Sheet</button>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showProcessingModal" class="modal-backdrop show"></div>
  </div>
</template>


<style lang="scss">
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
  height: 500px;
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

.pdf-container {
  position: relative;
  height: 100%;
  min-height: 500px;
  overflow: auto;
  background-color: #f8f9fa;
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
  padding: 0.5rem;
}

.form-select-sm {
  .vs-selected-options {

  }
  .vs__dropdown-toggle {
    background-color: #fff;
  }

  &.vs--open {
    input {
      width: 100%
    }
  }
}
</style>
