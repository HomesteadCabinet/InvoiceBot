<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Notify } from 'quasar'
import VuePdfEmbed from 'vue-pdf-embed'
import { fetchAPI, postAPI, putAPI } from '../utils/api'

const emails = ref([])
const nextPageToken = ref(null)
const hasMore = ref(false)
const pageSize = ref(20)
const currentPageToken = ref(null)
const pageTokenStack = ref([])
const pageIndex = ref(1)
const filterStatus = ref(null)
const filterVendorId = ref(null)
const filterDateFrom = ref('')
const filterDateTo = ref('')
const searchQuery = ref('')
const loading = ref(false)
const showProcessingModal = ref(false)
const currentInvoice = ref(null)
const selectedVendor = ref('')
const status = ref('')
const pdfError = ref(null)
const pdfLoading = ref(false)
const vendors = ref([])

const STATUS_OPTIONS = [
  { label: 'All statuses', value: null },
  { label: 'Pending', value: 'pending' },
  { label: 'Processed', value: 'processed' },
  { label: 'Error', value: 'error' },
]
const abortController = ref(null)
const activeVendor = ref(null)
const pdfContainer = ref(null)
const pdfPageCount = ref(0)
const columnMappings = ref({})
const displayData = ref(null)
const _showDataModal = ref(false)
const modalTitle = ref('')
const tableData = ref(null)
const textData = ref(null)
const parsedInvoices = ref([])
const selectedInvoiceIndex = ref(0)
const tab = ref('pdf')

const INVOICE_HEADER_FIELDS = [
  { key: 'invoice_number', label: 'Invoice #' },
  { key: 'vendor_name', label: 'Vendor' },
  { key: 'ship_date', label: 'Ship Date' },
  { key: 'date_ordered', label: 'Date Ordered' },
  { key: 'invoice_due_date', label: 'Due Date' },
  { key: 'invoice_total', label: 'Total' },
  { key: 'cust_po', label: 'Customer PO' },
]

const LINE_ITEM_FIELDS = [
  { key: 'id', label: 'ID' },
  { key: 'name', label: 'Name' },
  { key: 'description', label: 'Description' },
  { key: 'width', label: 'Width' },
  { key: 'length', label: 'Length / Height', altKey: 'height' },
  { key: 'qty', label: 'Qty' },
  { key: 'unit', label: 'Unit' },
  { key: 'unit_price', label: 'Unit Price' },
  { key: 'total_price', label: 'Total' },
]

function parserResultInvoices(result) {
  if (!result?.invoices?.length) {
    return []
  }
  return result.invoices
}

const parsedInvoice = computed(() => {
  const list = parsedInvoices.value
  if (!list.length) return null
  const idx = Math.min(selectedInvoiceIndex.value, list.length - 1)
  return list[idx]
})

const hasExtractedData = computed(() =>
  parsedInvoices.value.length > 0 || (textData.value && textData.value.length > 0)
)

const vendorFilterOptions = computed(() => [
  { label: 'All vendors', value: null },
  ...vendors.value.map(v => ({ label: v.name, value: v.id })),
])

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

const tableColumns = [
  { name: 'from', label: 'From', field: 'from', align: 'left', sortable: false },
  { name: 'vendor_name', label: 'Vendor', field: row => row.vendor_name || 'N/A', align: 'left', sortable: false },
  { name: 'date', label: 'Date', field: 'date', align: 'right', sortable: false },
  { name: 'snippet', label: 'Subject', field: 'snippet', align: 'left', sortable: false },
  { name: 'status', label: 'Status', field: 'status', align: 'center', sortable: false },
  { name: 'actions', label: '', field: 'id', align: 'center', sortable: false },
]

function statusBadgeColor(emailStatus) {
  if (emailStatus === 'error') return 'negative'
  if (emailStatus === 'processed') return 'positive'
  return 'warning'
}

function statusLabel(emailStatus) {
  return emailStatus || 'pending'
}

function rowClassFn(row) {
  if (row.status === 'error') return 'invoice-row--error'
  if (row.status === 'processed') return 'invoice-row--processed'
  return 'invoice-row--pending'
}

function formatInvoiceValue(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  if (typeof value === 'number') {
    if (Number.isInteger(value)) {
      return String(value)
    }
    return String(parseFloat(value.toFixed(4)))
  }
  return String(value)
}

function formatLineItemField(item, field) {
  const value = field.altKey
    ? (item[field.key] ?? item[field.altKey])
    : item[field.key]
  return formatInvoiceValue(value)
}
const availableParsers = ref([])
const currentParser = ref('')
const selectedParser = ref('')

// Watch for selectedVendor changes to update active vendor
watch(selectedVendor, async (newSelectedVendor) => {
  console.log('selectedVendor changed', newSelectedVendor)
  if (newSelectedVendor) {
    const selectedVendor = vendors.value.find(v => v.id === newSelectedVendor.id)
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

watch(pageSize, () => {
  onFiltersChanged()
})

let searchDebounceTimer = null

function resetPagination() {
  currentPageToken.value = null
  pageTokenStack.value = []
  pageIndex.value = 1
  nextPageToken.value = null
  hasMore.value = false
}

function buildListParams(pageToken = null) {
  const params = new URLSearchParams({
    maxResults: String(pageSize.value),
  })
  if (pageToken) {
    params.append('pageToken', pageToken)
  }
  if (filterStatus.value) {
    params.append('status', filterStatus.value)
  }
  if (filterVendorId.value) {
    params.append('vendorId', String(filterVendorId.value))
  }
  if (searchQuery.value.trim()) {
    params.append('search', searchQuery.value.trim())
  }
  if (filterDateFrom.value) {
    params.append('dateFrom', filterDateFrom.value)
  }
  if (filterDateTo.value) {
    params.append('dateTo', filterDateTo.value)
  }
  return params
}

function onFiltersChanged() {
  resetPagination()
  loadEmails()
}

function onSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    onFiltersChanged()
  }, 400)
}

function saveToGoogleSheet() {
  console.log('saveToGoogleSheet', 1)
}

function getExtractedDataJson() {
  if (parsedInvoices.value.length) {
    return JSON.stringify(
      {
        vendor_name: parsedInvoices.value[0]?.vendor_name || selectedVendor.value?.name,
        invoices: parsedInvoices.value,
      },
      null,
      2,
    )
  }
  return textData.value || ''
}

async function copyExtractedDataToClipboard() {
  const json = getExtractedDataJson()
  if (!json) {
    Notify.create({
      type: 'warning',
      message: 'No extracted data to copy',
    })
    return
  }
  try {
    await navigator.clipboard.writeText(json)
    Notify.create({
      type: 'positive',
      message: 'Copied extracted data to clipboard',
    })
  } catch (error) {
    console.error('Clipboard copy failed:', error)
    Notify.create({
      type: 'negative',
      message: 'Failed to copy to clipboard',
    })
  }
}

function setDisplayData(data) {
  if (data === 'Table Data') {
    modalTitle.value = 'Table Data'
    displayData.value = JSON.stringify(tableData.value, null, 2)
  } else if (data === 'Text Data') {
    modalTitle.value = 'Text Data'
    displayData.value = getExtractedDataJson()
  }
}

async function loadEmails(pageToken = null) {
  loading.value = true
  try {
    if (abortController.value) {
      abortController.value.abort()
    }
    abortController.value = new AbortController()

    const params = buildListParams(pageToken)
    const data = await fetchAPI(`/api/emails/?${params}`, {
      signal: abortController.value.signal,
    })

    emails.value = data.emails || []
    nextPageToken.value = data.nextPageToken || null
    hasMore.value = Boolean(data.hasMore ?? data.nextPageToken)
    currentPageToken.value = pageToken
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Error loading emails:', error)
    }
  } finally {
    loading.value = false
    abortController.value = null
  }
}

async function fetchVendors() {
  try {
    const data = await fetchAPI('/api/vendors/')
    // Add label and value props for v-select component
    vendors.value = data.map(vendor => ({
      ...vendor,
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
    selectedVendor.value = vendor
    status.value = data.status
    resetPdfPreview()
    showProcessingModal.value = true
    tableData.value = data.invoice.tables
    textData.value = data.invoice.text
    parsedInvoices.value = []
    selectedInvoiceIndex.value = 0
    tab.value = 'pdf'
  } catch (error) {
    email.status = 'error'
    email.busy = false
    console.error('Error processing email:', error)
    alert('Failed to process invoice. ' + errorMessage)
  }
}

async function goToNextPage() {
  if (!nextPageToken.value || loading.value) {
    return
  }
  pageTokenStack.value = [...pageTokenStack.value, currentPageToken.value]
  pageIndex.value += 1
  await loadEmails(nextPageToken.value)
}

async function goToPreviousPage() {
  if (pageTokenStack.value.length === 0 || loading.value) {
    return
  }
  const stack = [...pageTokenStack.value]
  const previousToken = stack.pop()
  pageTokenStack.value = stack
  pageIndex.value = Math.max(1, pageIndex.value - 1)
  await loadEmails(previousToken)
}

const canGoBack = computed(() => pageTokenStack.value.length > 0)

function resetPdfPreview() {
  pdfLoading.value = true
  pdfError.value = null
  pdfPageCount.value = 0
}

function onPdfLoaded(doc) {
  pdfPageCount.value = doc?.numPages ?? 0
}

function onPdfRendered() {
  pdfLoading.value = false
  pdfError.value = null
}

function onPdfLoadingFailed(error) {
  pdfLoading.value = false
  pdfError.value = error?.message ?? String(error)
  console.error('PDF Error:', error)
}

function onPdfRenderingFailed(error) {
  pdfLoading.value = false
  pdfError.value = error?.message ?? String(error)
  console.error('PDF render error:', error)
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

    const data = await postAPI('/api/test-parser/', testData)
    if (data.error) {
      alert(`Error testing parser: ${data.error}`)
    } else {
      const invoices = parserResultInvoices(data.result)
      parsedInvoices.value = invoices
      selectedInvoiceIndex.value = 0
      console.log('data.result', data.result)
      if (!invoices.length) {
        alert('No invoices found in the PDF, please check the parser')
      } else if (invoices.every(inv => !inv.line_items?.length)) {
        alert('No line items found in the invoice(s), please check the parser')
      } else if (invoices.length > 1) {
        console.log(`Parsed ${invoices.length} invoices from PDF`)
      }
    }
  } catch (error) {
    console.error('Error testing parser:', error)
    alert('Failed to test parser. Please try again.')
  }
}

async function saveInvoiceConfig() {
  if (!selectedVendor.value || !selectedParser.value) {
    alert('Please select both a vendor and an invoice parser')
    return
  }

  try {
    const configData = {
      parser: selectedParser.value.method
    }

    const data = await putAPI(`/api/vendors/${selectedVendor.value.id}/`, configData)
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
      <div class="row items-center justify-between q-mb-md">
        <div class="col-auto">
          <h2 class="q-my-none">Invoice Emails</h2>
        </div>
        <div class="col-auto">
          <q-btn
            color="primary"
            icon="refresh"
            label="Reload"
            :loading="loading"
            :disable="loading"
            @click="onFiltersChanged"
          />
        </div>
      </div>

      <q-card flat bordered class="q-mb-md">
        <q-card-section class="q-pb-sm">
          <div class="text-subtitle2 text-grey-8">Filters</div>
        </q-card-section>
        <q-card-section class="q-pt-none">
          <div class="row q-col-gutter-md">
            <div class="col-12 col-md-4">
              <q-input
                v-model="searchQuery"
                dense
                outlined
                clearable
                debounce="400"
                label="Search"
                placeholder="Subject, sender, vendor…"
                @update:model-value="onSearchInput"
                @clear="onFiltersChanged"
              >
                <template #prepend>
                  <q-icon name="search" />
                </template>
              </q-input>
            </div>
            <div class="col-12 col-sm-6 col-md-2">
              <q-select
                v-model="filterStatus"
                :options="STATUS_OPTIONS"
                dense
                outlined
                emit-value
                map-options
                option-label="label"
                option-value="value"
                label="Status"
                @update:model-value="onFiltersChanged"
              />
            </div>
            <div class="col-12 col-sm-6 col-md-3">
              <q-select
                v-model="filterVendorId"
                :options="vendorFilterOptions"
                dense
                outlined
                clearable
                emit-value
                map-options
                option-label="label"
                option-value="value"
                label="Vendor"
                @update:model-value="onFiltersChanged"
              />
            </div>
            <div class="col-12 col-sm-6 col-md-3">
              <q-input
                v-model="filterDateFrom"
                dense
                outlined
                clearable
                type="date"
                label="From date"
                @update:model-value="onFiltersChanged"
              />
            </div>
            <div class="col-12 col-sm-6 col-md-3">
              <q-input
                v-model="filterDateTo"
                dense
                outlined
                clearable
                type="date"
                label="To date"
                @update:model-value="onFiltersChanged"
              />
            </div>
          </div>
        </q-card-section>
      </q-card>

      <q-table
        :rows="emails"
        :columns="tableColumns"
        row-key="id"
        flat
        bordered
        :loading="loading"
        :rows-per-page-options="[0]"
        hide-pagination
        no-data-label="No invoice emails match your filters"
        :table-row-class-fn="rowClassFn"
        @row-click="(_evt, row) => processEmail(row.id)"
      >
        <template #body-cell-snippet="props">
          <q-td :props="props" class="cursor-pointer">
            <div class="ellipsis" style="max-width: 280px">
              {{ props.row.snippet }}
            </div>
          </q-td>
        </template>

        <template #body-cell-from="props">
          <q-td :props="props" class="cursor-pointer">
            <div class="ellipsis" style="max-width: 220px">
              {{ props.row.from }}
            </div>
          </q-td>
        </template>

        <template #body-cell-status="props">
          <q-td :props="props" class="cursor-pointer">
            <q-badge
              :color="statusBadgeColor(props.row.status)"
              :label="statusLabel(props.row.status)"
            />
          </q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" auto-width>
            <q-spinner
              v-if="props.row.busy"
              color="primary"
              size="sm"
            />
            <q-icon
              v-else
              name="chevron_right"
              color="grey-6"
              size="sm"
            />
          </q-td>
        </template>
      </q-table>

      <div class="row items-center justify-between q-mt-md q-gutter-sm">
        <div class="col-auto row items-center q-gutter-sm">
          <span class="text-grey-8">Per page</span>
          <q-select
            v-model="pageSize"
            :options="PAGE_SIZE_OPTIONS"
            dense
            outlined
            style="min-width: 80px"
          />
        </div>
        <div class="col-auto row items-center q-gutter-sm">
          <q-btn
            flat
            color="primary"
            icon="chevron_left"
            label="Previous"
            :disable="!canGoBack || loading"
            @click="goToPreviousPage"
          />
          <span class="text-body2 text-grey-8">Page {{ pageIndex }}</span>
          <q-btn
            flat
            color="primary"
            icon-right="chevron_right"
            label="Next"
            :disable="!hasMore || loading"
            @click="goToNextPage"
          />
        </div>
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
                <q-tab-panel name="pdf">
                  <div v-if="currentInvoice?.attachments?.length" class="attachments-container">
                    <div
                      v-for="(attachment, index) in currentInvoice.attachments"
                      :key="index"
                      class="attachment-frame"
                    >
                      <div class="attachment-toolbar row items-center justify-between q-mb-sm">
                        <span class="text-body2 ellipsis attachment-toolbar__name">
                          {{ attachment.filename }}
                        </span>
                        <q-btn
                          flat
                          dense
                          no-caps
                          color="primary"
                          icon="download"
                          label="Download PDF"
                          tag="a"
                          :href="attachment.url"
                          :download="attachment.filename"
                          target="_blank"
                          rel="noopener noreferrer"
                        />
                      </div>
                      <div class="pdf-container" ref="pdfContainer">
                        <div
                          v-if="pdfPageCount > 1"
                          class="text-caption text-grey-7 q-mb-sm"
                        >
                          {{ pdfPageCount }} pages
                        </div>
                        <VuePdfEmbed
                          :source="attachment.url"
                          class="pdf-embed"
                          @loaded="onPdfLoaded"
                          @rendered="onPdfRendered"
                          @loading-failed="onPdfLoadingFailed"
                          @rendering-failed="onPdfRenderingFailed"
                        />
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
              <q-card-section class="column data-rules-card full-height">
                <div class="col-auto">
                  <div class="col-12 q-mb-sm">
                    <q-input
                      v-model="currentInvoice.email"
                      label="Email"
                      dense
                      outlined
                    />
                  </div>

                  <div class="row">
                    <div class="col-6">
                      <q-select
                        v-model="selectedVendor"
                        :clearable="false"
                        :error="!selectedVendor"
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
                </div>

                <q-space class="col" />
                <div class="col-auto q-pb-xl parsed-results">
                  <template v-if="parsedInvoice">
                    <q-tabs
                      v-if="parsedInvoices.length > 1"
                      v-model="selectedInvoiceIndex"
                      dense
                      class="q-mb-sm"
                      active-color="primary"
                      indicator-color="primary"
                      align="left"
                      narrow-indicator
                      outside-arrows
                      mobile-arrows
                    >
                      <q-tab
                        v-for="(inv, idx) in parsedInvoices"
                        :key="idx"
                        :name="idx"
                        :label="inv.invoice_number || `Invoice ${idx + 1}`"
                      />
                    </q-tabs>
                    <div class="text-subtitle2 q-mb-sm">
                      Extracted Invoice
                      <span
                        v-if="parsedInvoices.length > 1"
                        class="text-grey-7 text-caption"
                      >
                        ({{ selectedInvoiceIndex + 1 }} of {{ parsedInvoices.length }})
                      </span>
                    </div>
                    <q-list dense bordered separator class="rounded-borders bg-white">
                      <q-item
                        v-for="field in INVOICE_HEADER_FIELDS"
                        :key="field.key"
                      >
                        <q-item-section>
                          <q-item-label caption>{{ field.label }}</q-item-label>
                          <q-item-label>{{ formatInvoiceValue(parsedInvoice[field.key]) }}</q-item-label>
                        </q-item-section>
                      </q-item>
                    </q-list>

                    <div v-if="parsedInvoice.line_items?.length" class="q-mt-md">
                      <div class="text-subtitle2 q-mb-sm">
                        Line Items ({{ parsedInvoice.line_items.length }})
                      </div>
                      <q-card
                        v-for="(item, index) in parsedInvoice.line_items"
                        :key="index"
                        flat
                        bordered
                        class="q-mb-sm"
                      >
                        <q-card-section class="q-pa-sm">
                          <div class="text-caption text-grey-7 q-mb-xs">
                            Item {{ index + 1 }}
                          </div>
                          <q-list dense>
                            <q-item
                              v-for="field in LINE_ITEM_FIELDS"
                              :key="field.key"
                            >
                              <q-item-section side class="text-grey-7" style="min-width: 5.5rem">
                                {{ field.label }}
                              </q-item-section>
                              <q-item-section>
                                {{ formatLineItemField(item, field) }}
                              </q-item-section>
                            </q-item>
                          </q-list>
                        </q-card-section>
                      </q-card>
                    </div>
                    <div v-else class="text-grey-7 q-mt-md">
                      No line items extracted
                    </div>
                  </template>
                  <template v-else-if="textData">
                    <div class="text-subtitle2 q-mb-sm">Raw Text</div>
                    <pre class="parsed-results__raw q-pa-sm bg-grey-2 rounded-borders">{{ textData }}</pre>
                  </template>
                  <div v-else class="text-grey-6 text-body2">
                    Run Test Parser to see extracted data
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
              v-if="hasExtractedData"
              flat
              color="primary"
              icon="content_copy"
              label="Copy JSON"
              @click="copyExtractedDataToClipboard"
            />
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

.q-table tbody tr {
  cursor: pointer;
}

.invoice-row--error {
  background-color: rgba($negative, 0.12);
}

.invoice-row--processed {
  background-color: rgba($positive, 0.12);
}

.invoice-row--pending {
  background-color: rgba($warning, 0.12);
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

.attachment-toolbar {
  padding: 0.5rem 0.75rem;
  background-color: $grey-2;
  border-bottom: 1px solid $grey-4;

  &__name {
    max-width: 60%;
    margin-right: 0.5rem;
  }
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
  max-height: 90vh;
  min-height: 500px;
  overflow: auto;
  background-color: $grey-2;
}

.pdf-embed {
  :deep(.vue-pdf-embed__page) {
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  }

  :deep(.vue-pdf-embed__page:last-child) {
    margin-bottom: 0;
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

.data-rules-card {
  // flex-flow: row wrap;

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
  //height: 70vh; // Match the height set on individual panels
}

.q-tab-panel {
  height: 100%; // Ensure panel takes full height of container
}

.parsed-results {
  max-width: 22rem;
  overflow-y: auto;


}

</style>
