<template>
  <q-page class="dashboard-page q-pa-lg">

    <q-card class="workspace-shell">
      <q-tabs
        v-model="activeTab"
        dense
        inline-label
        align="left"
        class="text-grey-8"
        active-color="primary"
        indicator-color="primary"
      >
        <q-tab name="overview" icon="dashboard" label="Overview" />
        <q-tab name="inbox" icon="mark_email_unread" label="Inbox" />
        <q-tab name="invoices" icon="description" label="Invoices" />
        <q-tab name="vendors" icon="business" label="Vendors" />
        <q-tab name="items" icon="inventory_2" label="Items" />
        <q-tab name="item-types" icon="category" label="Item Types" />
        <q-tab name="contacts" icon="contacts" label="Contacts" />
        <q-tab name="jobs" icon="work" label="Jobs" />
      </q-tabs>

      <q-separator />

      <q-tab-panels v-model="activeTab" animated keep-alive>
        <q-tab-panel name="overview">
          <div class="row q-col-gutter-lg">
            <div class="col-12 col-lg-7">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-subtitle1 text-weight-medium">Workflow</div>
                  <div class="text-body2 text-grey-7 q-mt-sm">
                    Use the Inbox to process new mail, then update vendors, contacts, item types,
                    and inventory records here. The automation controls live in the Inbox
                    configuration dialog, and exports are available there as well.
                  </div>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-lg-5">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-subtitle1 text-weight-medium">Quick Links</div>
                  <div class="q-gutter-sm q-mt-md">
                    <q-btn class="full-width" color="primary" icon="mail" label="Inbox" @click="activeTab = 'inbox'" />
                    <q-btn class="full-width" outline color="primary" icon="download" label="Automation & Export" @click="activeTab = 'inbox'" />
                  </div>
                </q-card-section>
              </q-card>
            </div>
          </div>
        </q-tab-panel>

        <q-tab-panel name="inbox">
          <InvoiceList />
        </q-tab-panel>

        <q-tab-panel name="invoices">
            <CrudManager
              title="Invoices"
              subtitle="Review invoice headers, dates, and status."
              endpoint="/api/invoices/"
              :columns="invoiceColumns"
              :fields="invoiceFields"
            :default-record="invoiceDefaults"
            create-label="Add invoice"
          />
        </q-tab-panel>

        <q-tab-panel name="vendors">
          <CrudManager
            title="Vendors"
            subtitle="Manage vendor profiles, parsers, and default invoice metadata."
            endpoint="/api/vendors/"
            :columns="vendorColumns"
            :fields="vendorFields"
            :default-record="vendorDefaults"
            create-label="Add vendor"
          />
        </q-tab-panel>

        <q-tab-panel name="items">
          <div class="q-gutter-lg">
            <CrudManager
              title="Inventory Items"
              subtitle="Track reusable stock and latest invoice values."
              endpoint="/api/inventory-items/"
              :columns="inventoryColumns"
              :fields="inventoryFields"
              :default-record="inventoryDefaults"
              create-label="Add item"
            />

            <CrudManager
              title="Invoice Line Items"
              subtitle="Manage the line items extracted from invoices."
              endpoint="/api/line-items/"
              :columns="lineItemColumns"
              :fields="lineItemFields"
              :default-record="lineItemDefaults"
              create-label="Add line item"
            />
          </div>
        </q-tab-panel>

        <q-tab-panel name="item-types">
          <CrudManager
            title="Item Types"
            subtitle="Organize inventory and line items into reusable categories."
            endpoint="/api/item-types/"
            :columns="itemTypeColumns"
            :fields="itemTypeFields"
            :default-record="itemTypeDefaults"
            create-label="Add item type"
          />
        </q-tab-panel>

        <q-tab-panel name="contacts">
          <CrudManager
            title="Contacts"
            subtitle="Keep vendor contacts available for routing and follow-up."
            endpoint="/api/contacts/"
            :columns="contactColumns"
            :fields="contactFields"
            :default-record="contactDefaults"
            create-label="Add contact"
          />
        </q-tab-panel>

        <q-tab-panel name="jobs">
          <CrudManager
            title="Jobs"
            subtitle="Jobs group line items by project or customer PO name from invoices."
            endpoint="/api/jobs/"
            :columns="jobColumns"
            :fields="jobFields"
            :default-record="jobDefaults"
            create-label="Add job"
          />
        </q-tab-panel>
      </q-tab-panels>
    </q-card>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Notify } from 'quasar'
import { fetchAPI } from '../utils/api'
import CrudManager from '../components/CrudManager.vue'
import InvoiceList from '../components/InvoiceList.vue'

const activeTab = ref('overview')
const loading = ref(false)
const oauthStatus = new URLSearchParams(window.location.search).get('googleAuth')

const vendors = ref([])
const itemTypes = ref([])
const contacts = ref([])
const jobs = ref([])
const invoices = ref([])
const inventoryItems = ref([])
const lineItems = ref([])
const parserOptions = ref([])

const summaryCards = computed(() => [
  { label: 'Vendors', value: vendors.value.length, icon: 'business', color: 'primary' },
  { label: 'Invoices', value: invoices.value.length, icon: 'description', color: 'secondary' },
  { label: 'Inventory Items', value: inventoryItems.value.length, icon: 'inventory_2', color: 'accent' },
  { label: 'Line Items', value: lineItems.value.length, icon: 'view_list', color: 'warning' },
  { label: 'Contacts', value: contacts.value.length, icon: 'contacts', color: 'positive' },
  { label: 'Jobs', value: jobs.value.length, icon: 'work', color: 'info' },
])

const vendorColumns = [
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'invoice_type', label: 'Type', field: 'invoice_type', align: 'left' },
  { name: 'parser', label: 'Parser', field: 'parser', align: 'left' },
  { name: 'spreadsheet_column_mapping', label: 'Sheet Mapping', field: row => JSON.stringify(row.spreadsheet_column_mapping || {}), align: 'left' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const vendorFields = computed(() => [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'invoice_type', label: 'Invoice Type', type: 'select', options: [{ label: 'PDF', value: 'pdf' }] },
  { key: 'parser', label: 'Parser', type: 'select', options: parserOptions.value },
  { key: 'spreadsheet_column_mapping', label: 'Spreadsheet column mapping (JSON)', type: 'json', colClass: 'col-12' },
])

const itemTypeColumns = [
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'description', label: 'Description', field: 'description', align: 'left' },
  { name: 'color', label: 'Color', field: 'color', align: 'left' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const itemTypeFields = [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'description', label: 'Description', type: 'textarea', colClass: 'col-12' },
  { key: 'color', label: 'Color', type: 'text' },
]

const contactColumns = [
  { name: 'name', label: 'Name', field: 'name', align: 'left' },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left' },
  { name: 'email', label: 'Email', field: 'email', align: 'left' },
  { name: 'phone', label: 'Phone', field: 'phone', align: 'left' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const jobColumns = [
  { name: 'job_id', label: 'Job ID', field: 'job_id', align: 'left', sortable: true },
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const jobFields = computed(() => [
  { key: 'vendor', label: 'Vendor', type: 'select', options: vendorOptions.value, clearable: true },
  { key: 'job_id', label: 'Job ID', type: 'text' },
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'notes', label: 'Notes', type: 'textarea', colClass: 'col-12' },
])

const contactFields = computed(() => [
  { key: 'vendor', label: 'Vendor', type: 'select', options: vendorOptions.value, clearable: true },
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'email', label: 'Email', type: 'text' },
  { key: 'phone', label: 'Phone', type: 'text' },
  { key: 'title', label: 'Title', type: 'text' },
  { key: 'is_primary', label: 'Primary contact', type: 'toggle', colClass: 'col-12' },
  { key: 'notes', label: 'Notes', type: 'textarea', colClass: 'col-12' },
])

const inventoryColumns = [
  { name: 'name', label: 'Name', field: 'name', align: 'left' },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left' },
  { name: 'item_type_name', label: 'Type', field: 'item_type_name', align: 'left' },
  { name: 'current_qty', label: 'Qty', field: 'current_qty', align: 'right' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const inventoryFields = computed(() => [
  { key: 'vendor', label: 'Vendor', type: 'select', options: vendorOptions.value, clearable: true },
  { key: 'item_type', label: 'Item Type', type: 'select', options: itemTypeOptions.value, clearable: true },
  { key: 'item_key', label: 'Item Key', type: 'text' },
  { key: 'item_id', label: 'Item ID', type: 'text' },
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'description', label: 'Description', type: 'textarea', colClass: 'col-12' },
  { key: 'unit', label: 'Unit', type: 'text' },
  { key: 'current_qty', label: 'Current Qty', type: 'number' },
  { key: 'last_unit_price', label: 'Last Unit Price', type: 'number' },
  { key: 'last_total_price', label: 'Last Total Price', type: 'number' },
])

const invoiceColumns = [
  { name: 'invoice_number', label: 'Invoice #', field: 'invoice_number', align: 'left' },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left' },
  { name: 'contact_name', label: 'Contact', field: 'contact_name', align: 'left' },
  { name: 'invoice_date', label: 'Invoice Date', field: 'invoice_date', align: 'left' },
  { name: 'received_at', label: 'Received', field: 'received_at', align: 'left' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' },
  { name: 'invoice_total', label: 'Total', field: 'invoice_total', align: 'right' },
  { name: 'line_item_count', label: 'Items', field: 'line_item_count', align: 'right' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const invoiceFields = computed(() => [
  { key: 'vendor', label: 'Vendor', type: 'select', options: vendorOptions.value, clearable: true },
  { key: 'contact', label: 'Contact', type: 'select', options: contactOptions.value, clearable: true },
  { key: 'source_email_id', label: 'Source Email ID', type: 'text' },
  { key: 'source_email_subject', label: 'Source Email Subject', type: 'text' },
  { key: 'source_email_from', label: 'Source Email From', type: 'text' },
  { key: 'invoice_number', label: 'Invoice #', type: 'text' },
  { key: 'invoice_date', label: 'Invoice Date', type: 'date' },
  { key: 'ship_date', label: 'Ship Date', type: 'date' },
  { key: 'due_date', label: 'Due Date', type: 'date' },
  { key: 'customer_po', label: 'Customer PO', type: 'text' },
  { key: 'invoice_total', label: 'Invoice Total', type: 'number' },
  { key: 'status', label: 'Status', type: 'select', options: [
    { label: 'Pending', value: 'pending' },
    { label: 'Processed', value: 'processed' },
    { label: 'Error', value: 'error' },
  ] },
  { key: 'error_message', label: 'Error Message', type: 'textarea', colClass: 'col-12' },
])

const lineItemColumns = [
  { name: 'invoice_number', label: 'Invoice', field: 'invoice_number', align: 'left' },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left' },
  { name: 'invoice_date', label: 'Date', field: 'invoice_date', align: 'left' },
  { name: 'item_type_name', label: 'Type', field: 'item_type_name', align: 'left' },
  { name: 'inventory_item_name', label: 'Inventory Item', field: 'inventory_item_name', align: 'left' },
  { name: 'job_number', label: 'Job ID', field: 'job_number', align: 'left' },
  { name: 'job_name', label: 'Job Name', field: 'job_name', align: 'left' },
  { name: 'name', label: 'Name', field: 'name', align: 'left' },
  { name: 'qty', label: 'Qty', field: 'qty', align: 'right' },
  { name: 'total_price', label: 'Total', field: 'total_price', align: 'right' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const lineItemFields = computed(() => [
  { key: 'invoice', label: 'Invoice', type: 'select', options: invoiceOptions.value, clearable: true },
  { key: 'item_type', label: 'Item Type', type: 'select', options: itemTypeOptions.value, clearable: true },
  { key: 'inventory_item', label: 'Inventory Item', type: 'select', options: inventoryOptions.value, clearable: true },
  { key: 'item_id', label: 'Item ID', type: 'text' },
  { key: 'job', label: 'Job', type: 'select', options: jobOptions.value, clearable: true },
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'description', label: 'Description', type: 'textarea', colClass: 'col-12' },
  { key: 'qty', label: 'Qty', type: 'number' },
  { key: 'unit', label: 'Unit', type: 'text' },
  { key: 'unit_price', label: 'Unit Price', type: 'number' },
  { key: 'total_price', label: 'Total Price', type: 'number' },
  { key: 'width', label: 'Width', type: 'number' },
  { key: 'length', label: 'Length', type: 'number' },
  { key: 'height', label: 'Height', type: 'number' },
])

const vendorDefaults = { name: '', invoice_type: 'pdf', parser: '', spreadsheet_column_mapping: {} }
const itemTypeDefaults = { name: '', description: '', color: '' }
const jobDefaults = { vendor: null, job_id: '', name: '', notes: '' }
const contactDefaults = { vendor: null, name: '', email: '', phone: '', title: '', is_primary: false, notes: '' }
const inventoryDefaults = { vendor: null, item_type: null, item_key: '', item_id: '', name: '', description: '', unit: '', current_qty: 0, last_unit_price: null, last_total_price: null }
const invoiceDefaults = { vendor: null, contact: null, source_email_id: '', source_email_subject: '', source_email_from: '', source_email_date: '', received_at: '', invoice_number: '', invoice_date: '', ship_date: '', due_date: '', customer_po: '', invoice_total: null, status: 'pending', error_message: '' }
const lineItemDefaults = { invoice: null, item_type: null, inventory_item: null, job: null, item_id: '', name: '', description: '', qty: 0, unit: '', unit_price: 0, total_price: 0, width: null, length: null, height: null }

const vendorOptions = computed(() => vendors.value.map(v => ({ label: v.name, value: v.id })))
const itemTypeOptions = computed(() => itemTypes.value.map(t => ({ label: t.name, value: t.id })))
const contactOptions = computed(() => contacts.value.map(c => ({ label: `${c.name}${c.vendor_name ? ` • ${c.vendor_name}` : ''}`, value: c.id })))
const invoiceOptions = computed(() => invoices.value.map(i => ({ label: `${i.invoice_number || i.id} • ${i.vendor_name || 'No vendor'}`, value: i.id })))
const inventoryOptions = computed(() => inventoryItems.value.map(i => ({ label: `${i.name || i.item_key} • ${i.vendor_name || 'No vendor'}`, value: i.id })))
const jobOptions = computed(() => jobs.value.map(j => {
  const idPart = j.job_id ? `${j.job_id}` : ''
  const namePart = j.name ? `${j.name}` : ''
  const label = [idPart, namePart].filter(Boolean).join(' ') || `Job ${j.id}`
  return {
    label: `${label}${j.vendor_name ? ` • ${j.vendor_name}` : ''}`,
    value: j.id,
  }
}))

function mapList (data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.results)) return data.results
  return []
}

async function refreshAll () {
  loading.value = true
  try {
    const [
      vendorData,
      itemTypeData,
      contactData,
      jobData,
      invoiceData,
      inventoryData,
      lineItemData,
      parserData,
    ] = await Promise.all([
      fetchAPI('/api/vendors/'),
      fetchAPI('/api/item-types/'),
      fetchAPI('/api/contacts/'),
      fetchAPI('/api/jobs/'),
      fetchAPI('/api/invoices/'),
      fetchAPI('/api/inventory-items/'),
      fetchAPI('/api/line-items/'),
      fetchAPI('/api/vendors/get_invoice_parsers/'),
    ])

    vendors.value = mapList(vendorData)
    itemTypes.value = mapList(itemTypeData)
    contacts.value = mapList(contactData)
    jobs.value = mapList(jobData)
    invoices.value = mapList(invoiceData)
    inventoryItems.value = mapList(inventoryData)
    lineItems.value = mapList(lineItemData)
    parserOptions.value = (parserData.available_parsers || []).map(parser => ({ label: parser.name, value: parser.method }))
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: 'Failed to load dashboard data',
    })
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (oauthStatus) {
    activeTab.value = 'inbox'
  }
  refreshAll()
})
</script>

<style scoped>
.dashboard-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(13, 71, 161, 0.26), transparent 28%),
    radial-gradient(circle at top right, rgba(0, 121, 107, 0.21), transparent 24%),
    linear-gradient(180deg, #e4ebf5 0%, #d6e0ec 52%, #c8d4e2 100%);
}

.dashboard-kicker {
  color: #93c5fd;
}

.dashboard-title {
  max-width: 18ch;
}

.dashboard-copy {
  max-width: 60ch;
  color: #4b5563;
}

.summary-card,
.workspace-shell,
.panel-card {
  border-radius: 18px;
}

.workspace-shell {
  overflow: hidden;
}
</style>
