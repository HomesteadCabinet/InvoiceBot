<script setup>
import { ref, onMounted, watch } from 'vue'
import VuePdfEmbed from 'vue-pdf-embed'
import { fetchAPI, postAPI } from '../utils/api'

const emails = ref([])
const nextPageToken = ref(null)
const loading = ref(false)
const showProcessingModal = ref(false)
const currentInvoice = ref(null)
const vendorID = ref('')
const status = ref('')
const pdfError = ref(null)
const pdfLoading = ref(false)
const pdfText = ref('')
const maxResults = ref(10)
const vendors = ref([])
const abortController = ref(null)
const activeVendor = ref(null)
const pdfScale = ref(1)
const pdfContainer = ref(null)
const columnMappings = ref({})
const displayData = ref(null)
const _showDataModal = ref(false)
const modalTitle = ref('')
const tableData = ref(null)
const textData = ref(null)
const tab = ref('pdf')
const availableParsers = ref([])
const currentParser = ref('')
const selectedParser = ref('')

// Watch for vendorID changes to update active vendor
watch(vendorID, async (newVendorID) => {
  console.log('vendorID changed', newVendorID)
  if (newVendorID) {
    const selectedVendor = vendors.value.find(v => v.value === newVendorID)
    if (selectedVendor) {
      activeVendor.value = selectedVendor
      // Load column mappings from vendor
      columnMappings.value = selectedVendor.spreadsheet_column_mapping || {}
      // Set selectedParser based on vendor's parser
      if (selectedVendor.parser) {
        selectedParser.value = availableParsers.value.find(p => p.method === selectedVendor.parser) || ''
      }
    } else {
      activeVendor.value = null
      columnMappings.value = {}
      selectedParser.value = ''
    }
  } else {
    activeVendor.value = null
    columnMappings.value = {}
    selectedParser.value = ''
  }
})

// Add watch for columnMappings changes
watch(columnMappings, (newMappings) => {
  console.log('Column mappings updated:', newMappings)
})

// Watch for maxResults changes
watch(maxResults, (newValue) => {
  console.log('maxResults changed', newValue)
  loadEmails()
}, { debounce: 500 })

function saveToGoogleSheet() {
  console.log('saveToGoogleSheet', 1)
}

function setDisplayData(data) {
  if (data === 'Table Data') {
    modalTitle.value = 'Table Data'
    displayData.value = JSON.stringify(tableData.value, null, 2)
  } else if (data === 'Text Data') {
    modalTitle.value = 'Text Data'
    displayData.value = textData.value
  }
}

async function loadEmails(pageToken = null) {
  loading.value = true
  try {
    // Cancel any existing request
    if (abortController.value) {
      abortController.value.abort()
    }
    abortController.value = new AbortController()

    const params = new URLSearchParams({
      maxResults: maxResults.value
    })
    if (pageToken) {
      params.append('pageToken', pageToken)
    }

    const data = await fetchAPI(`/api/emails/?${params}`, {
      signal: abortController.value.signal
    })

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
    currentInvoice.value.email = email.from

    // Find the vendor in the vendors list and use its value property
    let vendor = vendors.value.find(v => v.id === data.vendor.id)
    if (!vendor) {
      // Create new vendor object
      vendor = {
        ...data.vendor,
      }
      // Add to vendors list
      vendors.value.push(vendor)
    }
    vendorID.value = vendor.value
    status.value = data.status
    showProcessingModal.value = true
    tableData.value = data.invoice.tables
    textData.value = data.invoice.text
    tab.value = 'pdf'
  } catch (error) {
    email.status = 'error'
    email.busy = false
    console.error('Error processing email:', error)
    alert('Failed to process invoice. ' + errorMessage)
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

function showDataModal(data) {
  setDisplayData(data)
  _showDataModal.value = true
}

async function getParsers() {
  try {
    const data = await fetchAPI(`/api/vendors/get_invoice_parsers/`)
    availableParsers.value = data.available_parsers || []
    currentParser.value = data.current_parser || ''
  } catch (error) {
    console.error('Error fetching parsers:', error)
  }
}

async function testParser() {
  if (!selectedParser.value) {
    alert('Please select a parser first')
    return
  }

  if (!currentInvoice.value?.attachments?.[0]?.filename) {
    alert('No PDF file available to test the parser')
    return
  }

  try {
    const testData = {
      pdf_filename: currentInvoice.value.attachments[0].filename,
      parser: selectedParser.value
    }

    const response = await fetch('http://localhost:8000/api/test-parser/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(testData)
    })

    if (!response.ok) {
      throw new Error('Network response was not ok')
    }

    const data = await response.json()
    if (data.error) {
      alert(`Error testing parser: ${data.error}`)
    } else {
      alert(`Parser test result: ${JSON.stringify(data.result, null, 2)}`)
    }
  } catch (error) {
    console.error('Error testing parser:', error)
    alert('Failed to test parser. Please try again.')
  }
}

async function saveInvoiceConfig() {
  if (!vendorID.value || !selectedParser.value) {
    alert('Please select both a vendor and an invoice parser')
    return
  }

  try {
    const configData = {
      parser: selectedParser.value.method
    }

    const response = await fetch(`http://localhost:8000/api/vendors/${vendorID.value}/`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(configData)
    })

    if (!response.ok) {
      throw new Error('Network response was not ok')
    }

    const data = await response.json()
    if (data.error) {
      alert(`Error saving configuration: ${data.error}`)
    } else {
      alert('Invoice configuration saved successfully')
    }
  } catch (error) {
    console.error('Error saving invoice configuration:', error)
    alert('Failed to save invoice configuration. Please try again.')
  }
}

onMounted(() => {
  loadEmails()
  fetchVendors()
  getParsers()
})

</script>

<template>
  <q-card>
    <div class="q-pa-md">
      <div class="row justify-between q-mb-md">
        <div class="col-auto">
          <h2 class="q-my-none">Invoice Emails</h2>
        </div>
        <div class="col-auto">
          <div class="row items-center">
            <span class="q-mr-sm">Max Results</span>
            <q-input
              type="number"
              v-model="maxResults"
              min="1"
              max="100"
              debounce="3000"
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
              <q-card-section class="q-py-sm">
                <div class="row">
                  <div class="col">
                    <!-- Removed title from here -->
                  </div>
                </div>
              </q-card-section>

              <!-- Add Tabs -->
              <q-tabs
                v-model="tab"
                dense
                class="text-grey"
                active-color="primary"
                indicator-color="primary"
                align="justify"
                narrow-indicator
              >
                <q-tab name="pdf" label="PDF Preview" />
              </q-tabs>

              <q-separator />

              <q-tab-panels v-model="tab" animated keep-alive>
                <q-tab-panel name="pdf" class="q-pa-none" style="height: 70vh;">
                  <div v-if="currentInvoice?.attachments?.length" class="attachments-container">
                    <div
                      v-for="(attachment, index) in currentInvoice.attachments"
                      :key="index"
                      class="attachment-frame"
                    >
                      <div class="pdf-container" ref="pdfContainer">
                        <a :href="attachment.url" target="_blank">
                          {{ attachment.url }}
                        </a>
                          <VuePdfEmbed
                            :source="attachment.url"
                            :page="1"
                            @error="onPdfError"
                            @loading="onPdfLoading"
                            @loaded="onPdfLoaded"
                          />
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
                </q-tab-panel>
              </q-tab-panels>
            </q-card>
          </div>

          <!-- Right side: Form controls -->
          <div class="col-12 col-md-4">
            <q-card style="height: 100% ;">
              <q-card-section class="q-py-sm">
                <div class="text-h6">Invoice Parser</div>
              </q-card-section>
              <q-card-section class="data-rules-card">
                <div class="row">
                  <div class="col-12 q-mb-sm">
                    <q-input
                      v-model="currentInvoice.email"
                      label="Email"
                      dense
                      outlined
                    />
                  </div>

                  <div class="col-6">
                    <q-select
                      v-model="vendorID"
                      :clearable="false"
                      :error="!vendorID"
                      :options="vendors"
                      :rules="[val => !!val || 'Please select a vendor']"
                      behavior="dialog"
                      class="q-mr-sm"
                      dense outlined options-dense
                      error-message="Please select a vendor"
                      label="Vendor"
                      option-label="name"
                      option-value="id"
                    />
                  </div>
                  <div class="col-6">
                    <q-select
                      v-model="selectedParser"
                      :clearable="false"
                      :error="!selectedParser"
                      :options="availableParsers"
                      :rules="[val => !!val || 'Please select a parser']"
                      dense options-dense outlined
                      error-message="Please select a parser"
                      label="Invoice Parser"
                      option-label="name"
                      option-value="method"
                    />
                  </div>
                  <div class="col-12 justify-center flex q-mt-sm">
                    <q-btn
                      color="primary"
                      icon="play_arrow"
                      @click="testParser"
                    >
                      Test Parser
                    </q-btn>
                  </div>
                </div>
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
              @click="saveInvoiceConfig"
            >
              Save Invoice Configuration
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

.pdf-container {
  position: relative;
  height: 100%;
  min-height: 500px;
  overflow: auto;
  background-color: $grey-2;
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

.data-rules-card {
  .q-card__section {
    padding: 0;
  }

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

// Ensure tab panels have consistent height
.q-tab-panels {
  height: 70vh; // Match the height set on individual panels
}

.q-tab-panel {
  height: 100%; // Ensure panel takes full height of container
}


.q-field--dense .q-field__control, .q-field--dense .q-field__marginal {
    height: 36px;
}

</style>
