<script setup>
import { ref, onMounted, watch } from 'vue'
import VuePdfEmbed from 'vue-pdf-embed'

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
const extractedData = ref({})
const newRule = ref({
  field_name: '',
  data_type: '',
  location_type: '',
  required: false
})

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

async function loadEmails(pageToken = null) {
  loading.value = true
  try {
    const url = new URL('http://localhost:8000/api/emails/')
    if (pageToken) {
      url.searchParams.append('pageToken', pageToken)
    }
    const res = await fetch(url)
    const data = await res.json()
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

onMounted(() => {
  loadEmails()
})

async function processEmail(email_id, event) {
  // Prevent processing if clicking on attachments button
  if (event && event.target.closest('.btn-outline-primary')) {
    return
  }

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

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`)
    }

    const data = await res.json()
    if (data.error) {
      alert(`Error processing invoice: ${data.error}`)
      return
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

    // Show processing modal with invoice data
    currentInvoice.value = data.invoice
    vendorName.value = data.vendor_name
    status.value = data.status
    showProcessingModal.value = true
  } catch (error) {
    console.error('Error processing email:', error)
    alert('Failed to process email. Please try again later.')
  }
}

async function saveDataRules() {
  try {
    const res = await fetch('http://localhost:8000/api/data-rules/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        invoice_id: currentInvoice.value.id,
        vendor_name: vendorName.value,
        status: status.value,
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

function extractKeyValuePairs(text) {
  const pairs = {}

  // Common patterns for key-value pairs
  const patterns = [
    // Pattern 1: Key: Value
    /([^:\n]+):\s*([^\n]+)/g,
    // Pattern 2: Key = Value
    /([^=\n]+)=\s*([^\n]+)/g,
    // Pattern 3: Key - Value
    /([^-\n]+)-\s*([^\n]+)/g,
    // Pattern 4: Key Value (where Key is in a predefined list)
    /(Invoice\s+Number|Date|Due\s+Date|Total|Amount|Subtotal|Tax|Vendor|Customer|Order\s+Number)\s+([^\n]+)/gi
  ]

  // Common invoice keys to look for
  const commonKeys = [
    'invoice number', 'invoice date', 'due date', 'total amount',
    'subtotal', 'tax', 'vendor', 'customer', 'order number',
    'payment terms', 'po number', 'account number', 'description'
  ]

  // Extract using patterns
  patterns.forEach(pattern => {
    let match
    while ((match = pattern.exec(text)) !== null) {
      const key = match[1].trim().toLowerCase()
      const value = match[2].trim()

      // Clean up the key
      const cleanKey = key
        .replace(/[^a-z0-9\s]/g, '') // Remove special characters
        .replace(/\s+/g, ' ') // Replace multiple spaces with single space
        .trim()

      if (cleanKey && value) {
        pairs[cleanKey] = value
      }
    }
  })

  // Look for key-value pairs based on common keys
  commonKeys.forEach(key => {
    const regex = new RegExp(`${key}[\\s:]+([^\\n]+)`, 'i')
    const match = text.match(regex)
    if (match) {
      pairs[key] = match[1].trim()
    }
  })

  // Look for table-like structures
  const lines = text.split('\n')
  lines.forEach(line => {
    // Look for tabular data
    const parts = line.split(/\s{2,}/)
    if (parts.length >= 2) {
      const potentialKey = parts[0].trim().toLowerCase()
      const potentialValue = parts[1].trim()

      if (commonKeys.some(key => potentialKey.includes(key))) {
        pairs[potentialKey] = potentialValue
      }
    }
  })

  return pairs
}

function onPdfLoaded(pdf) {
  pdfLoading.value = false
  pdfError.value = null

  // Extract text from all pages
  const numPages = pdf.numPages
  const textPromises = []

  for (let i = 1; i <= numPages; i++) {
    textPromises.push(
      pdf.getPage(i).then(page => {
        return page.getTextContent().then(textContent => {
          // Get text with position information
          const items = textContent.items.map(item => ({
            text: item.str,
            x: item.transform[4],
            y: item.transform[5],
            width: item.width,
            height: item.height
          }))

          // Sort items by position (top to bottom, left to right)
          items.sort((a, b) => {
            if (Math.abs(a.y - b.y) > 5) { // If items are on different lines
              return b.y - a.y
            }
            return a.x - b.x
          })

          return items.map(item => item.text).join(' ')
        })
      })
    )
  }

  Promise.all(textPromises).then(texts => {
    const fullText = texts.join('\n\n')

    // Extract key-value pairs
    extractedData.value = extractKeyValuePairs(fullText)
    pdfText.value = JSON.stringify(extractedData.value, null, 2)

    console.log('Extracted data:', extractedData.value)
  }).catch(error => {
    console.error('Error extracting text from PDF:', error)
    pdfError.value = 'Failed to extract text from PDF'
  })
}

function addDataRule() {
  dataRules.value.push({ ...newRule.value })
  newRule.value = {}
}

function deleteDataRule(index) {
  dataRules.value.splice(index, 1)
}
</script>

<template>
  <div class="container mt-4">
    <h2>Invoice Emails</h2>
    <div class="list-group">
      <div v-for="email in emails"
           :key="email.id"
           :class="{
             'list-group-item list-group-item-action': true,
             'list-group-item-danger': email.status === 'error',
             'list-group-item-success': email.status === 'processed',
             'list-group-item-warning': !email.status || email.status === 'pending'
           }"
           @click="processEmail(email.id, $event)">
        <div class="row header">
          <div class="col">{{ email.snippet }}</div>
          <div class="col-auto">
            <button class="btn btn-outline-primary btn-sm"
                    @click="downloadAttachments(email.id, $event)">
              <i class="bi bi-paperclip me-1"></i>
              {{ email.attachment_count }} attachments
            </button>
          </div>
        </div>
        <div class="mt-2 row justify-content-between text-muted footer">
          <div class="col-auto">From: {{ email.from }}</div>
          <div class="col-auto">Vendor: {{ email.vendor_name || 'N/A' }}</div>
          <div class="col-auto">Status: {{ email.status || 'pending' }}</div>
          <div class="col-auto">Date: {{ email.date }}</div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="text-center mt-3">
      <div class="spinner-border text-primary" role="status">
        <span class="visually-hidden">Loading...</span>
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
    <div v-if="showProcessingModal" class="modal show d-block" tabindex="-1">
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
                    <h6 class="mb-0">Invoice Preview</h6>
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
                                  </select>
                                </div>
                                <div class="col-md-3">
                                  <label class="form-label small">Location Type</label>
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
                            Existing Rules
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
                                      <i :class="rule.required ? 'bi bi-check-circle-fill text-success' : 'bi bi-x-circle-fill text-danger'"></i>
                                    </td>
                                    <td class="text-end">
                                      <button class="btn btn-sm btn-outline-danger" @click="deleteDataRule(index)">
                                        <i class="bi bi-trash"></i>
                                      </button>
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
            <button type="button" class="btn btn-primary" @click="saveDataRules">Save</button>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showProcessingModal" class="modal-backdrop show"></div>
  </div>
</template>


<style scoped lang="scss">
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
</style>
