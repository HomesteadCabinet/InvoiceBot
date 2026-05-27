<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Dialog, Notify } from 'quasar'
import VuePdfEmbed from 'vue-pdf-embed'
import { fetchAPI, postAPI, putAPI } from '../utils/api'
import { dragPanDirective } from '../utils/dragPan'
import { notifyCrudChanged } from '../utils/crudSync'
import { formatTypedValue } from '../utils/formatters'

const CONFIG_STORAGE_KEY = 'invoiceinator.invoiceListConfig'

function defaultStoredConfig () {
  return {
    rememberFilters: true,
    rememberPageSize: true,
    pageSize: 20,
    filters: {
      status: null,
      vendorId: null,
      dateFrom: '',
      dateTo: '',
      search: '',
    },
  }
}

function readStoredConfig () {
  if (typeof window === 'undefined') {
    return defaultStoredConfig()
  }

  try {
    const raw = window.localStorage.getItem(CONFIG_STORAGE_KEY)
    if (!raw) {
      return defaultStoredConfig()
    }

    const parsed = JSON.parse(raw)
    return {
      ...defaultStoredConfig(),
      ...parsed,
      filters: {
        ...defaultStoredConfig().filters,
        ...(parsed?.filters || {}),
      },
    }
  } catch {
    return defaultStoredConfig()
  }
}

function writeStoredConfig (config) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config))
}

function captureCurrentFilters () {
  return {
    status: filterStatus.value,
    vendorId: filterVendorId.value,
    dateFrom: filterDateFrom.value,
    dateTo: filterDateTo.value,
    search: searchQuery.value,
  }
}

function applyFiltersFromConfig (filters) {
  filterStatus.value = filters?.status ?? null
  filterVendorId.value = filters?.vendorId ?? null
  filterDateFrom.value = filters?.dateFrom ?? ''
  filterDateTo.value = filters?.dateTo ?? ''
  searchQuery.value = filters?.search ?? ''
}

const storedConfig = readStoredConfig()
const vDragPan = dragPanDirective

const emails = ref([])
const nextPageToken = ref(null)
const hasMore = ref(false)
const pageSize = ref(storedConfig.rememberPageSize ? storedConfig.pageSize : defaultStoredConfig().pageSize)
const currentPageToken = ref(null)
const pageTokenStack = ref([])
const pageIndex = ref(1)
const filterStatus = ref(storedConfig.rememberFilters ? storedConfig.filters.status : null)
const filterVendorId = ref(storedConfig.rememberFilters ? storedConfig.filters.vendorId : null)
const filterDateFrom = ref(storedConfig.rememberFilters ? storedConfig.filters.dateFrom : '')
const filterDateTo = ref(storedConfig.rememberFilters ? storedConfig.filters.dateTo : '')
const searchQuery = ref(storedConfig.rememberFilters ? storedConfig.filters.search : '')
const loading = ref(false)
const configDialogOpen = ref(false)
const rememberFilters = ref(storedConfig.rememberFilters)
const rememberPageSize = ref(storedConfig.rememberPageSize)
const savedFilters = ref({ ...storedConfig.filters })
const savedPageSize = ref(storedConfig.pageSize)
const googleConnected = ref(false)
const googleConfigured = ref(true)
const googleConfigError = ref('')
const googleRedirectUri = ref('')
const googleScopes = ref([])
const googleLoading = ref(false)
const automationSettings = ref({
  auto_process_enabled: false,
  max_email_age_days: 30,
  poll_interval_seconds: 60,
  last_processed_at: null,
})
const automationSaving = ref(false)
const automationRunning = ref(false)
const exportLoading = ref(false)
const resetLoading = ref(false)
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
  { label: 'Incorrect parsing', value: 'incorrect_parsing' },
  { label: 'Error', value: 'error' },
]

const emailContextMenu = ref(null)
const contextMenuRow = ref(null)
const abortController = ref(null)
const activeVendor = ref(null)
const pdfContainer = ref(null)
const pdfPageCount = ref(0)
const displayData = ref(null)
const _showDataModal = ref(false)
const modalTitle = ref('')
const tableData = ref(null)
const textData = ref(null)
const parsedInvoices = ref([])
const selectedInvoiceIndex = ref(0)
const tab = ref('pdf')
const oauthStatus = new URLSearchParams(window.location.search).get('googleAuth')
const oauthMessage = new URLSearchParams(window.location.search).get('message')

const googleStatusLabel = computed(() => (googleConnected.value ? 'Connected' : 'Not connected'))
const googleStatusColor = computed(() => (googleConnected.value ? 'positive' : 'grey-6'))
const oauthBannerClass = computed(() => (
  oauthStatus === 'success'
    ? 'bg-positive text-white'
    : 'bg-negative text-white'
))
const oauthBannerMessage = computed(() => {
  if (oauthStatus === 'success') {
    return 'Google account connected.'
  }

  if (oauthStatus === 'error') {
    return oauthMessage || 'Google authorization failed.'
  }

  return ''
})
const hasOauthBanner = computed(() => Boolean(oauthBannerMessage.value))
const savedFiltersSummary = computed(() => {
  const filters = savedFilters.value || {}
  const parts = [
    filters.search ? `Search: ${filters.search}` : 'Search: none',
    filters.status ? `Status: ${filters.status}` : 'Status: all',
    filters.vendorId ? `Vendor ID: ${filters.vendorId}` : 'Vendor: all',
    filters.dateFrom ? `From: ${filters.dateFrom}` : 'From: any',
    filters.dateTo ? `To: ${filters.dateTo}` : 'To: any',
  ]
  return parts.join(' · ')
})

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
  { name: 'from', label: 'From', field: 'from', align: 'left', sortable: true },
  { name: 'vendor_name', label: 'Vendor', field: row => row.vendor_name || 'N/A', align: 'left', sortable: true },
  { name: 'date', label: 'Date', field: 'date', align: 'right', sortable: true },
  { name: 'snippet', label: 'Subject', field: 'snippet', align: 'left', sortable: true },
  { name: 'status', label: 'Status', field: 'status', align: 'center', sortable: true },
  { name: 'actions', label: '', field: 'id', align: 'center', sortable: false },
]

function statusBadgeColor(emailStatus) {
  if (emailStatus === 'error') return 'negative'
  if (emailStatus === 'processed') return 'positive'
  if (emailStatus === 'incorrect_parsing') return 'deep-orange'
  return 'warning'
}

function statusLabel(emailStatus) {
  const labels = {
    pending: 'Pending',
    processed: 'Processed',
    error: 'Error',
    incorrect_parsing: 'Incorrect parsing',
  }
  return labels[emailStatus] || emailStatus || 'Pending'
}

function rowClassFn(row) {
  if (row.status === 'error') return 'invoice-row--error'
  if (row.status === 'processed') return 'invoice-row--processed'
  if (row.status === 'incorrect_parsing') return 'invoice-row--incorrect-parsing'
  return 'invoice-row--pending'
}

function onEmailContextMenu(evt, row) {
  contextMenuRow.value = row
  emailContextMenu.value?.show(evt)
}

async function flagIncorrectParsing(row) {
  if (!row?.id) {
    return
  }
  try {
    const data = await postAPI('/api/emails/flag-incorrect-parsing/', { email_id: row.id })
    const emailIndex = emails.value.findIndex(e => e.id === row.id)
    if (emailIndex !== -1) {
      emails.value[emailIndex] = {
        ...emails.value[emailIndex],
        status: data.status || 'incorrect_parsing',
      }
    }
    Notify.create({
      type: 'positive',
      message: 'Marked as incorrect parsing',
    })
  } catch (error) {
    console.error('Failed to flag incorrect parsing:', error)
    Notify.create({
      type: 'negative',
      message: error?.message || 'Failed to flag incorrect parsing',
    })
  }
}

function onEmailRowClick(evt, row) {
  if (evt?.type === 'contextmenu') {
    return
  }
  processEmail(row.id)
}

function formatInvoiceValue(value, type) {
  return formatTypedValue(value, type)
}

function invoiceJobSummary(invoice) {
  const jobValues = [...new Set(
    (invoice?.line_items || [])
      .map(item => [item.job_id, item.job].filter(Boolean).join(' • '))
      .filter(Boolean),
  )]
  const resolvedJob = jobValues.length === 1 ? jobValues[0] : ''
  const po = invoice?.cust_po || ''

  return {
    label: resolvedJob ? 'Job' : 'Customer PO',
    value: resolvedJob || po || '—',
  }
}

function invoiceDateSummary(invoice) {
  return [
    { label: 'Date Ordered', value: formatInvoiceValue(invoice?.date_ordered) },
    { label: 'Ship Date', value: formatInvoiceValue(invoice?.ship_date) },
    { label: 'Due Date', value: formatInvoiceValue(invoice?.invoice_due_date) },
  ]
}

function parsedInvoiceDetailRows (invoice) {
  const job = invoiceJobSummary(invoice)
  return [job, ...invoiceDateSummary(invoice)].filter(
    row => row.value && row.value !== '—',
  )
}

function formatLineItemField(item, field) {
  const value = field.altKey
    ? (item[field.key] ?? item[field.altKey])
    : item[field.key]
  return formatInvoiceValue(value, field.type)
}

function lineItemTitle (item) {
  const parts = []
  for (const value of [item.id, item.name, item.description]) {
    const text = value == null ? '' : String(value).trim()
    if (!text) {
      continue
    }
    if (!parts.some(existing => existing.toLowerCase() === text.toLowerCase())) {
      parts.push(text)
    }
  }
  return parts.join(' · ') || '—'
}

function lineItemMeta (item) {
  const parts = []
  const job = [item.job_id, item.job].filter(value => value != null && String(value).trim() !== '').join(' ')
  if (job) {
    parts.push(job)
  }
  const width = item.width != null && item.width !== '' ? item.width : null
  const length = item.length ?? item.height
  const lengthText = length != null && length !== '' ? length : null
  if (width || lengthText) {
    parts.push([width, lengthText].filter(Boolean).join('×'))
  }
  if (item.unit) {
    parts.push(item.unit)
  }
  const unitPrice = item.unit_price != null && item.unit_price !== ''
    ? formatInvoiceValue(item.unit_price, 'currency')
    : ''
  if (unitPrice) {
    parts.push(`@ ${unitPrice}`)
  }
  return parts.join(' · ')
}

function formatLineItemQty (item) {
  if (item.qty == null || item.qty === '') {
    return '—'
  }
  return formatInvoiceValue(item.qty, 'number')
}

function persistStoredConfig () {
  writeStoredConfig({
    rememberFilters: rememberFilters.value,
    rememberPageSize: rememberPageSize.value,
    pageSize: savedPageSize.value,
    filters: { ...savedFilters.value },
  })
}

function saveCurrentFilters () {
  rememberFilters.value = true
  rememberPageSize.value = true
  savedFilters.value = captureCurrentFilters()
  savedPageSize.value = pageSize.value
  persistStoredConfig()
  Notify.create({
    type: 'positive',
    message: 'Current filters saved on this device',
  })
}

function restoreSavedFilters () {
  rememberFilters.value = true
  rememberPageSize.value = true
  applyFiltersFromConfig(savedFilters.value)
  pageSize.value = savedPageSize.value
  onFiltersChanged()
  Notify.create({
    type: 'positive',
    message: 'Saved filters restored',
  })
}

function resetSavedFilters () {
  savedFilters.value = { ...defaultStoredConfig().filters }
  if (!rememberFilters.value) {
    applyFiltersFromConfig(savedFilters.value)
  }
  persistStoredConfig()
  Notify.create({
    type: 'positive',
    message: 'Saved filters cleared',
  })
}

async function loadGoogleStatus () {
  googleLoading.value = true
  try {
    const data = await fetchAPI('/api/google/status/')
    googleConnected.value = Boolean(data.connected)
    googleConfigured.value = data.configured !== false
    googleConfigError.value = data.error || ''
    googleRedirectUri.value = data.redirect_uri || ''
    googleScopes.value = data.scopes || []
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to load Google connection status',
    })
  } finally {
    googleLoading.value = false
  }
}

async function loadAutomationSettings () {
  try {
    const data = await fetchAPI('/api/automation/settings/')
    automationSettings.value = {
      ...automationSettings.value,
      ...data,
    }
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to load automation settings',
    })
  }
}

async function saveAutomationSettings (previousSettings = null) {
  automationSaving.value = true
  try {
    const data = await putAPI('/api/automation/settings/', automationSettings.value)
    automationSettings.value = {
      ...automationSettings.value,
      ...data,
    }
    Notify.create({
      type: 'positive',
      message: automationSettings.value.auto_process_enabled
        ? 'Auto-processing enabled'
        : 'Auto-processing disabled',
    })
  } catch {
    if (previousSettings) {
      automationSettings.value = { ...previousSettings }
    }
    Notify.create({
      type: 'negative',
      message: 'Failed to save automation settings',
    })
  } finally {
    automationSaving.value = false
  }
}

async function toggleAutomationEnabled (value) {
  if (automationSaving.value) {
    return
  }

  const previousSettings = { ...automationSettings.value }
  automationSettings.value = {
    ...automationSettings.value,
    auto_process_enabled: value,
  }
  await saveAutomationSettings(previousSettings)
}

async function processInvoicesNow () {
  automationRunning.value = true
  try {
    const data = await postAPI('/api/automation/process-now/', {})
    Notify.create({
      type: 'positive',
      message: `Processed ${data.processed || 0} invoice email(s)`,
    })
    await loadEmails()
    await loadAutomationSettings()
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to start invoice processing',
    })
  } finally {
    automationRunning.value = false
  }
}

function resetProcessingState () {
  currentInvoice.value = null
  parsedInvoices.value = []
  selectedInvoiceIndex.value = 0
  tableData.value = null
  textData.value = null
  status.value = ''
  pdfError.value = null
  pdfLoading.value = false
  pdfPageCount.value = 0
  tab.value = 'pdf'
  showProcessingModal.value = false
}

async function resetAllProcessedData () {
  const resetMode = await new Promise((resolve) => {
    Dialog.create({
      title: 'Reset invoice data',
      message: 'Choose what to clear. The default keeps vendors and item types.',
      options: {
        type: 'radio',
        model: 'imported',
        items: [
          {
            label: 'Reset imported data only',
            value: 'imported',
            color: 'negative',
          },
          {
            label: 'Remove everything',
            value: 'all',
            color: 'negative',
          },
        ],
      },
      cancel: true,
      persistent: true,
      ok: { label: 'Reset selected data', color: 'negative' },
    }).onOk((value) => resolve(value)).onCancel(() => resolve(null))
  })

  if (!resetMode) {
    return
  }

  const removeAll = resetMode === 'all'
  if (removeAll) {
    const confirmed = await new Promise((resolve) => {
      Dialog.create({
        title: 'Remove everything?',
        message: 'This deletes vendors, item types, contacts, jobs, email caches, invoices, inventory, processed emails, automation settings, and stored PDFs.',
        cancel: true,
        persistent: true,
        ok: { label: 'Remove everything', color: 'negative' },
      }).onOk(() => resolve(true)).onCancel(() => resolve(false))
    })

    if (!confirmed) {
      return
    }
  }

  if (!removeAll) {
    const confirmed = await new Promise((resolve) => {
      Dialog.create({
        title: 'Reset imported data?',
        message: 'This deletes email caches, processed emails, contacts, jobs, invoices, inventory, and stored PDFs. Vendors and item types will remain.',
        cancel: true,
        persistent: true,
        ok: { label: 'Reset imported data', color: 'negative' },
      }).onOk(() => resolve(true)).onCancel(() => resolve(false))
    })

    if (!confirmed) {
      return
    }
  }

  resetLoading.value = true
  try {
    const data = await postAPI('/api/automation/reset-data/', { remove_all: removeAll })
    resetProcessingState()
    await loadEmails()
    await fetchVendors()
    notifyCrudChanged()
    Notify.create({
      type: 'positive',
      message: removeAll
        ? `Removed all data and ${data.deleted_files || 0} PDF file(s)`
        : `Cleared imported data and ${data.deleted_files || 0} PDF file(s); vendors and item types were preserved`,
    })
  } catch (error) {
    console.error('Failed to reset invoice data:', error)
    Notify.create({
      type: 'negative',
      message: 'Failed to reset invoice data',
    })
  } finally {
    resetLoading.value = false
  }
}

async function exportXlsx () {
  exportLoading.value = true
  try {
    const response = await fetch('/api/export/xlsx/', {
      credentials: 'include',
    })
    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`)
    }
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'invoiceinator-export.xlsx'
    link.click()
    window.URL.revokeObjectURL(url)
    Notify.create({
      type: 'positive',
      message: 'Export started',
    })
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to export XLSX',
    })
  } finally {
    exportLoading.value = false
  }
}

function showGoogleSetupDialog () {
  const redirectUri = googleRedirectUri.value || 'http://localhost:9000/api/google/callback/'
  Dialog.create({
    title: 'Set up Google sign-in',
    message: [
      'To open the Google login screen, add OAuth credentials on the server:',
      '',
      '1. In Google Cloud Console → APIs & Services → Credentials, create an OAuth 2.0 Web client.',
      '2. Enable the Gmail API for your project.',
      `3. Add authorized redirect URI: ${redirectUri}`,
      '4. On the server, either:',
      '   • Copy invoiceinator/client.json.example to invoiceinator/client.json and paste your client ID/secret, or',
      '   • Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (see invoiceinator/.env.example).',
      '5. Restart Django (./run.sh django), then click Connect Google again.',
    ].join('\n'),
    ok: { label: 'Got it', color: 'primary' },
    style: 'white-space: pre-line',
  })
}

async function connectGoogle () {
  if (!googleConfigured.value) {
    showGoogleSetupDialog()
    return
  }

  googleLoading.value = true
  try {
    const response = await fetch('/api/google/auth-url/', {
      credentials: 'include',
    })
    const data = await response.json()
    if (!response.ok) {
      if (response.status === 503) {
        googleConfigured.value = false
        googleConfigError.value = data.error || ''
        showGoogleSetupDialog()
        return
      }
      throw new Error(data.error || 'Failed to start Google authorization')
    }
    if (!data.authorization_url) {
      throw new Error('No authorization URL returned from server')
    }
    window.location.href = data.authorization_url
  } catch (err) {
    Notify.create({
      type: 'negative',
      message: err?.message || 'Failed to start Google authorization',
    })
  } finally {
    googleLoading.value = false
  }
}

async function disconnectGoogle () {
  googleLoading.value = true
  try {
    await fetchAPI('/api/google/disconnect/', {
      method: 'POST',
    })
    await loadGoogleStatus()
    Notify.create({
      type: 'positive',
      message: 'Google account disconnected',
    })
  } catch {
    Notify.create({
      type: 'negative',
      message: 'Failed to disconnect Google account',
    })
  } finally {
    googleLoading.value = false
  }
}

function openConfigDialog () {
  configDialogOpen.value = true
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
      // Set selectedParser based on vendor's parser
      if (selectedVendor.parser) {
        selectedParser.value = availableParsers.value.find(p => p.method === selectedVendor.parser) || ''
      }
    } else {
      activeVendor.value = null
      selectedParser.value = ''
    }
  } else {
    activeVendor.value = null
    selectedParser.value = ''
  }
})

watch(pageSize, () => {
  if (rememberPageSize.value) {
    savedPageSize.value = pageSize.value
    persistStoredConfig()
  }
  onFiltersChanged()
})

watch([filterStatus, filterVendorId, filterDateFrom, filterDateTo, searchQuery], () => {
  if (rememberFilters.value) {
    savedFilters.value = captureCurrentFilters()
    persistStoredConfig()
  }
})

watch([rememberFilters, rememberPageSize], () => {
  persistStoredConfig()
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
    const data = await fetchAPI('/api/vendors/?page_size=200&active_only=1')
    const list = Array.isArray(data) ? data : (Array.isArray(data?.results) ? data.results : [])
    vendors.value = list.map(vendor => ({
      ...vendor,
    }))
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

    if (data.vendor?.id) {
      let vendor = vendors.value.find(v => v.id === data.vendor.id)
      if (!vendor) {
        vendor = { ...data.vendor }
        vendors.value.push(vendor)
      }
      selectedVendor.value = vendor
    }

    status.value = data.status
    resetPdfPreview()
    showProcessingModal.value = true
    tableData.value = data.invoice?.tables
    textData.value = data.invoice?.text
    parsedInvoices.value = parserResultInvoices(data.parsed || {})
    selectedInvoiceIndex.value = 0
    tab.value = 'pdf'

    if (!parsedInvoices.value.length && data.status === 'processed') {
      Notify.create({
        type: 'warning',
        message: 'Email processed but no invoice line items were found to display',
      })
    }
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

async function persistParsedToDatabase(parsedEnvelope) {
  if (!selectedVendor.value?.id) {
    Notify.create({
      type: 'warning',
      message: 'Select a vendor before saving parsed data to the database',
    })
    return null
  }

  const envelope = parsedEnvelope || {
    vendor_name: parsedInvoices.value[0]?.vendor_name || selectedVendor.value?.name,
    invoices: parsedInvoices.value,
  }
  if (!envelope.invoices?.length) {
    Notify.create({ type: 'warning', message: 'No parsed invoices to save' })
    return null
  }

  try {
    const data = await postAPI('/api/persist-parsed/', {
      vendor_id: selectedVendor.value.id,
      parsed: envelope,
      email_id: currentInvoice.value?.email_id,
      pdf_filename: currentInvoice.value?.attachments?.[0]?.filename,
      email_payload: {
        from: currentInvoice.value?.email || currentInvoice.value?.from || '',
        subject: currentInvoice.value?.subject || currentInvoice.value?.snippet || '',
        date: currentInvoice.value?.date || '',
      },
    })
    if (data.error) {
      Notify.create({ type: 'negative', message: data.error })
      return null
    }
    const count = data.invoice_ids?.length || 0
    const lineCount = (data.invoices || []).reduce(
      (sum, inv) => sum + (inv.line_items?.length || 0),
      0
    )
    Notify.create({
      type: 'positive',
      message: `Saved ${count} invoice(s) and ${lineCount} line item(s) to the database`,
    })
    return data
  } catch (error) {
    console.error('Error persisting parsed invoice:', error)
    Notify.create({ type: 'negative', message: 'Failed to save parsed data to the database' })
    return null
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
      if (!invoices.length) {
        alert('No invoices found in the PDF, please check the parser')
      } else if (invoices.every(inv => !inv.line_items?.length)) {
        alert('No line items found in the invoice(s), please check the parser')
      } else if (selectedVendor.value) {
        await persistParsedToDatabase(data.result)
      } else {
        Notify.create({
          type: 'info',
          message: 'Select a vendor to save parsed invoices to the database',
        })
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
  if (hasOauthBanner.value) {
    configDialogOpen.value = true
    Notify.create({
      type: oauthStatus === 'success' ? 'positive' : 'negative',
      message: oauthBannerMessage.value,
    })
  }

  if (savedFilters.value && rememberFilters.value) {
    applyFiltersFromConfig(savedFilters.value)
  }

  loadEmails()
  fetchVendors()
  getParsers()
  loadGoogleStatus()
  loadAutomationSettings()
})

</script>

<template>
  <q-card>
    <div class="q-pa-md">
      <div class="row items-center justify-between q-mb-md">
        <div class="col-auto">
          <h2 class="q-my-none">Invoice Emails</h2>
        </div>
        <div class="col-auto row q-gutter-sm">
          <q-btn
            outline
            color="primary"
            icon="download"
            label="Export XLSX"
            :loading="exportLoading"
            :disable="exportLoading"
            @click="exportXlsx"
          />
          <q-btn
            outline
            color="primary"
            icon="settings"
            label="Config"
            @click="openConfigDialog"
          />
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
        v-drag-pan
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
        @row-click="onEmailRowClick"
        @row-contextmenu="onEmailContextMenu"
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

      <q-menu ref="emailContextMenu" context-menu touch-position>
        <q-list dense style="min-width: 200px">
          <q-item
            v-if="contextMenuRow"
            v-close-popup
            clickable
            :disable="contextMenuRow.status === 'incorrect_parsing'"
            @click="flagIncorrectParsing(contextMenuRow)"
          >
            <q-item-section avatar>
              <q-icon name="flag" color="deep-orange" />
            </q-item-section>
            <q-item-section>
              {{
                contextMenuRow.status === 'incorrect_parsing'
                  ? 'Already flagged incorrect parsing'
                  : 'Flag incorrect parsing'
              }}
            </q-item-section>
          </q-item>
        </q-list>
      </q-menu>

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

  <q-dialog v-model="configDialogOpen" full-width>
    <q-card class="config-dialog">
      <q-card-section class="row items-start q-pb-none">
        <div>
          <div class="text-h6">Configuration</div>
          <div class="text-caption text-grey-7">
            Google access, table defaults, and persisted local filters.
          </div>
        </div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section class="q-gutter-md">
        <q-banner v-if="hasOauthBanner" :class="oauthBannerClass" rounded>
          {{ oauthBannerMessage }}
        </q-banner>

        <q-card flat bordered>
          <q-card-section>
            <div class="row items-center justify-between q-mb-sm">
              <div>
                <div class="text-subtitle1">Google account</div>
                <div class="text-caption text-grey-7">
                  Enable Gmail and Sheets access for backend automation.
                </div>
              </div>
              <q-badge :color="googleStatusColor">
                {{ googleStatusLabel }}
              </q-badge>
            </div>

            <q-banner
              v-if="!googleConfigured"
              class="bg-warning text-dark q-mb-sm"
              rounded
            >
              <div>
                {{ googleConfigError || 'Server OAuth credentials are not set up yet.' }}
              </div>
              <template #action>
                <q-btn
                  flat
                  dense
                  color="dark"
                  label="Setup steps"
                  @click="showGoogleSetupDialog"
                />
              </template>
            </q-banner>

            <div class="text-caption text-grey-7 q-mb-sm">
              Connected scopes:
              <span v-if="googleScopes.length">{{ googleScopes.join(', ') }}</span>
              <span v-else>none</span>
            </div>

            <div class="row q-gutter-sm">
              <q-btn
                color="primary"
                :label="googleConnected ? 'Reconnect Google' : 'Connect Google'"
                :loading="googleLoading"
                :disable="googleLoading"
                @click="connectGoogle"
              />
              <q-btn
                v-if="googleConnected"
                outline
                color="negative"
                label="Disconnect"
                :loading="googleLoading"
                :disable="googleLoading"
                @click="disconnectGoogle"
              />
              <q-btn
                flat
                color="primary"
                label="Refresh status"
                :disable="googleLoading"
                @click="loadGoogleStatus"
              />
            </div>
          </q-card-section>
        </q-card>

        <q-card flat bordered>
          <q-card-section>
            <div class="row items-center justify-between q-mb-sm">
              <div>
                <div class="text-subtitle1">Auto processing</div>
                <div class="text-caption text-grey-7">
                  Poll Gmail in the background and skip emails older than the configured age.
                </div>
              </div>
              <q-toggle
                :model-value="automationSettings.auto_process_enabled"
                label="Enabled"
                :disable="automationSaving"
                @update:model-value="toggleAutomationEnabled"
              />
            </div>

            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-6 col-md-4">
                <q-input
                  v-model.number="automationSettings.max_email_age_days"
                  type="number"
                  min="1"
                  dense
                  outlined
                  label="Max email age (days)"
                  :disable="automationSaving"
                />
              </div>
              <div class="col-12 col-sm-6 col-md-4">
                <q-input
                  v-model.number="automationSettings.poll_interval_seconds"
                  type="number"
                  min="10"
                  dense
                  outlined
                  label="Poll interval (seconds)"
                  :disable="automationSaving"
                />
              </div>
            </div>

            <div class="text-caption text-grey-7 q-mt-sm">
              Last run:
              {{ automationSettings.last_processed_at || 'never' }}
            </div>

            <div class="row q-gutter-sm q-mt-md">
              <q-btn
                color="primary"
                :label="automationSettings.auto_process_enabled ? 'Save and keep running' : 'Start auto-processing'"
                :loading="automationSaving"
                :disable="automationSaving"
                @click="saveAutomationSettings"
              />
              <q-btn
                outline
                color="primary"
                label="Process now"
                :loading="automationRunning"
                :disable="automationRunning"
                @click="processInvoicesNow"
              />
            </div>
          </q-card-section>
        </q-card>

        <q-card flat bordered>
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">Local settings</div>
            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-6">
                <q-toggle
                  v-model="rememberFilters"
                  label="Remember filters on this device"
                />
              </div>
              <div class="col-12 col-sm-6">
                <q-toggle
                  v-model="rememberPageSize"
                  label="Remember page size"
                />
              </div>
              <div class="col-12 col-sm-6 col-md-4">
                <q-select
                  v-model="pageSize"
                  :options="PAGE_SIZE_OPTIONS"
                  dense
                  outlined
                  label="Current page size"
                />
              </div>
            </div>
          </q-card-section>
        </q-card>

        <q-card flat bordered>
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">Saved filter state</div>
            <div class="text-caption text-grey-7 q-mb-md">
              {{ savedFiltersSummary }}
            </div>
            <div class="row q-gutter-sm">
              <q-btn
                color="primary"
                label="Save current filters"
                @click="saveCurrentFilters"
              />
              <q-btn
                outline
                color="primary"
                label="Restore saved filters"
                @click="restoreSavedFilters"
              />
              <q-btn
                flat
                color="negative"
                label="Clear saved filters"
                @click="resetSavedFilters"
              />
            </div>
          </q-card-section>
        </q-card>

        <q-card flat bordered>
          <q-card-section>
            <div class="row items-center justify-between q-mb-sm">
              <div>
                <div class="text-subtitle1">Danger zone</div>
                <div class="text-caption text-grey-7">
                  Reset imported invoice data by default, or choose a full wipe that removes vendors and item types too.
                </div>
              </div>
              <q-btn
                color="negative"
                outline
                icon="restart_alt"
                label="Reset data"
                :loading="resetLoading"
                :disable="resetLoading"
                @click="resetAllProcessedData"
              />
            </div>
          </q-card-section>
        </q-card>
      </q-card-section>
    </q-card>
  </q-dialog>

  <!-- Processing Dialog -->
  <q-dialog v-model="showProcessingModal" full-width>
    <q-card class="processing-dialog">
      <q-card-section class="processing-dialog__header row items-center q-pb-none">
        <div class="text-h6">Processing Invoice</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section class="processing-dialog__body q-pt-sm">
        <div class="row processing-dialog__content">
          <!-- Left side: PDF iframe -->
          <div class="col-12 col-md-7 processing-dialog__pdf-col">
            <q-card class="processing-dialog__panel">
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

              <q-tab-panels v-model="tab" animated keep-alive class="processing-dialog__tab-panels">
                <q-tab-panel name="pdf" class="processing-dialog__tab-panel">
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
                          :key="attachment.url"
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
          <div class="col-12 col-md-5 processing-dialog__form-col">
            <q-card class="processing-dialog__panel processing-dialog__form-panel">
              <q-card-section class="q-py-sm processing-dialog__form-header">
                <div class="text-h6">Invoice Parser</div>
              </q-card-section>
              <q-card-section class="row data-rules-card processing-dialog__form-body">
                <div class="col-12">
                  <div class="q-mb-sm">
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

                <div class="col-12 parsed-results processing-dialog__parsed-results">
                  <template v-if="parsedInvoice">
                    <div class="parsed-invoice-details">
                      <q-tabs
                        v-if="parsedInvoices.length > 1"
                        v-model="selectedInvoiceIndex"
                        dense
                        class="parsed-invoice-details__tabs"
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

                      <div class="parsed-invoice-details__header">
                        <div class="parsed-invoice-details__title">
                          <span>
                            {{ parsedInvoice.invoice_number || 'Extracted invoice' }}
                          </span>
                          <span
                            v-if="parsedInvoices.length > 1"
                            class="text-caption text-grey-7 q-ml-xs"
                          >
                            {{ selectedInvoiceIndex + 1 }}/{{ parsedInvoices.length }}
                          </span>
                        </div>
                        <div class="parsed-invoice-details__total">
                          {{ formatInvoiceValue(parsedInvoice.invoice_total, 'currency') }}
                        </div>
                      </div>

                      <dl
                        v-if="parsedInvoiceDetailRows(parsedInvoice).length"
                        class="parsed-invoice-details__meta"
                      >
                        <template
                          v-for="row in parsedInvoiceDetailRows(parsedInvoice)"
                          :key="row.label"
                        >
                          <dt>{{ row.label }}</dt>
                          <dd>{{ row.value }}</dd>
                        </template>
                      </dl>

                      <div v-if="parsedInvoice.line_items?.length" class="parsed-line-items">
                        <div class="parsed-line-items__heading text-caption text-grey-7">
                          {{ parsedInvoice.line_items.length }} line item{{ parsedInvoice.line_items.length === 1 ? '' : 's' }}
                        </div>
                        <q-markup-table
                          dense
                          flat
                          wrap-cells
                          class="parsed-line-items__table"
                        >
                          <thead>
                            <tr>
                              <th class="parsed-line-items__col-idx">#</th>
                              <th>Item</th>
                              <th class="parsed-line-items__col-qty text-right">Qty</th>
                              <th class="parsed-line-items__col-total text-right">Total</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr
                              v-for="(item, index) in parsedInvoice.line_items"
                              :key="index"
                            >
                              <td class="parsed-line-items__idx">{{ index + 1 }}</td>
                              <td>
                                <div class="parsed-line-items__title">{{ lineItemTitle(item) }}</div>
                                <div
                                  v-if="lineItemMeta(item)"
                                  class="parsed-line-items__meta text-grey-7"
                                >
                                  {{ lineItemMeta(item) }}
                                </div>
                              </td>
                              <td class="parsed-line-items__qty text-right">
                                {{ formatLineItemQty(item) }}
                              </td>
                              <td class="parsed-line-items__price text-right">
                                {{ formatLineItemField(item, { key: 'total_price', type: 'currency' }) }}
                              </td>
                            </tr>
                          </tbody>
                        </q-markup-table>
                      </div>
                      <div v-else class="text-caption text-grey-7 q-mt-sm">
                        No line items extracted
                      </div>
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

      <q-card-actions class="processing-dialog__footer">
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
              class="q-mr-sm"
              :disable="!parsedInvoices.length || !selectedVendor"
              @click="persistParsedToDatabase()"
            >
              Save to database
            </q-btn>
            <q-btn
              color="primary"
              outline
              @click="saveInvoiceConfig"
            >
              Save vendor parser
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

.invoice-row--incorrect-parsing {
  background-color: rgba($deep-orange, 0.12);
}

.invoice-row--pending {
  //ckground-color: rgba($warning, 0.12);
}

.attachments-container {
  width: 100%;
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
  min-height: 12rem;
  background-color: $grey-2;
}

.processing-dialog {
  display: flex;
  flex-direction: column;
  width: min(1400px, 100%);
  max-height: 92vh;
  overflow: hidden;
}

.processing-dialog__header,
.processing-dialog__footer {
  flex: 0 0 auto;
}

.processing-dialog__footer {
  border-top: 1px solid $grey-4;
}

.processing-dialog__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.processing-dialog__parsed-results {
  max-width: none;
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


}

// Ensure tab panels have consistent height
.q-tab-panels {
  //height: 70vh; // Match the height set on individual panels
}

.q-tab-panel {
  height: 100%; // Ensure panel takes full height of container
}

.parsed-results {
  overflow-y: auto;
}

.parsed-invoice-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.parsed-invoice-details__tabs {
  margin-bottom: 0;
}

.parsed-invoice-details__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  line-height: 1.25;
}

.parsed-invoice-details__title {
  min-width: 0;
  font-size: 0.8rem;
  font-weight: 500;
  line-height: 1.2;
}

.parsed-invoice-details__total {
  flex-shrink: 0;
  font-size: 0.8rem;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
}

.parsed-invoice-details__meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.15rem 0.75rem;
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.3;

  dt {
    margin: 0;
    color: $grey-7;
    white-space: nowrap;
  }

  dd {
    margin: 0;
    text-align: right;
    word-break: break-word;
  }
}

.parsed-line-items__heading {
  margin-bottom: 0.15rem;
}

.parsed-line-items__table {
  width: 100%;
  font-size: 0.8rem;
  background: transparent;

  thead th {
    font-size: 0.7rem;
    font-weight: 600;
    color: $grey-7;
    padding: 0.15rem 0.35rem 0.25rem;
    line-height: 1.2;
    border: none;
    background: transparent;
  }

  tbody td {
    padding: 0.2rem 0.35rem;
    line-height: 1.25;
    vertical-align: top;
    border: none;
    background: transparent;
  }

  tbody tr + tr td {
    border-top: 1px solid rgba(0, 0, 0, 0.06);
  }
}

.parsed-line-items__col-idx {
  width: 1.25rem;
}

.parsed-line-items__col-qty {
  width: 2.5rem;
  white-space: nowrap;
}

.parsed-line-items__col-total {
  width: 4rem;
  white-space: nowrap;
}

.parsed-line-items__idx {
  color: $grey-7;
  font-size: 0.7rem;
}

.parsed-line-items__title {
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.2;
  word-break: break-word;
}

.parsed-line-items__qty,
.parsed-line-items__price {
  font-size: 0.75rem;
  line-height: 1.2;
  white-space: nowrap;
}

.parsed-line-items__price {
  font-weight: 500;
}

.parsed-line-items__meta {
  font-size: 0.65rem;
  line-height: 1.2;
  margin-top: 1px;
  word-break: break-word;
}

.config-dialog {
  width: min(920px, 100%);
}

</style>
