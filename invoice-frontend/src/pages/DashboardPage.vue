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
          <div class="row q-col-gutter-md q-mb-lg">
            <div
              v-for="card in summaryCards"
              :key="card.label"
              class="col-12 col-sm-6 col-lg-4"
            >
              <q-card flat bordered class="panel-card">
                <q-card-section class="row items-center q-gutter-md">
                  <q-avatar :color="card.color" text-color="white" size="42px" rounded>
                    <q-icon :name="card.icon" />
                  </q-avatar>
                  <div>
                    <div class="text-caption text-grey-7">{{ card.label }}</div>
                    <div class="text-h6">{{ card.value }}</div>
                  </div>
                </q-card-section>
              </q-card>
            </div>
          </div>
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
            row-click-behavior="emit"
            @row-click="openInvoiceDetails"
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
            row-click-behavior="emit"
            @row-click="openVendorInvoices"
          />
        </q-tab-panel>

        <q-tab-panel name="items">
          <div class="q-gutter-lg">
            <CrudManager
              title="Inventory Items"
              subtitle="Track reusable stock and open line-item history from the table."
              endpoint="/api/inventory-items/"
              :columns="inventoryColumns"
              :fields="inventoryFields"
              :default-record="inventoryDefaults"
              create-label="Add item"
              row-click-behavior="emit"
              @row-click="openInventoryDetails"
            />
          </div>
        </q-tab-panel>

        <q-tab-panel name="item-types">
          <ItemTypeManager />
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

    <q-dialog v-model="inventoryDetailsOpen" full-width>
      <q-card class="inventory-detail-card">
        <q-card-section class="row items-start">
          <div>
            <div class="text-h6">
              {{ selectedInventoryItem?.name || selectedInventoryItem?.item_key || 'Inventory Item' }}
            </div>
            <div class="text-caption text-grey-7">
              {{ selectedInventoryItem?.vendor_name || 'No vendor' }}
              <span v-if="selectedInventoryItem?.item_type_name">• {{ selectedInventoryItem.item_type_name }}</span>
              <span v-if="selectedInventoryItem?.item_id">• {{ selectedInventoryItem.item_id }}</span>
            </div>
          </div>
          <q-space />
          <q-btn icon="close" flat round dense @click="closeInventoryDetails" />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Current Qty</div>
                  <div class="text-h6">{{ formatQuantity(selectedInventoryItem?.current_qty) }}</div>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Line Items</div>
                  <div class="text-h6">{{ inventoryLineItems.length }}</div>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Last Invoiced</div>
                  <div class="text-h6">{{ selectedInventoryItem?.last_invoiced_at || '—' }}</div>
                </q-card-section>
              </q-card>
            </div>
          </div>

          <div class="row q-col-gutter-md q-mb-sm">
            <div class="col-12 col-md-6">
              <q-input
                v-model="inventoryLineItemSearch"
                dense
                outlined
                clearable
                label="Filter line items"
                placeholder="Invoice, item, job, notes…"
              >
                <template #prepend>
                  <q-icon name="search" />
                </template>
              </q-input>
            </div>
          </div>

          <q-table
            v-drag-pan
            flat
            bordered
            dense
            row-key="id"
            :rows="filteredInventoryLineItems"
            :columns="inventoryLineItemColumns"
            :loading="inventoryLineItemsLoading"
            :rows-per-page-options="[10, 25, 50, 0]"
            no-data-label="No line items found for this inventory item"
          >
            <template #body-cell-received="props">
              <q-td :props="props" auto-width>
                <q-badge :color="props.row.received ? 'positive' : 'grey-6'">
                  {{ props.row.received ? 'Yes' : 'No' }}
                </q-badge>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </q-dialog>

    <q-dialog v-model="vendorInvoicesOpen" full-width>
      <q-card class="inventory-detail-card">
        <q-card-section class="row items-start">
          <div>
            <div class="row items-center q-gutter-md">
              <q-img
                v-if="selectedVendorForInvoices?.logo_url"
                :src="selectedVendorForInvoices.logo_url"
                ratio="1"
                class="vendor-dialog-logo"
              />
              <div>
                <div class="text-h6">
                  {{ selectedVendorForInvoices?.name || 'Vendor invoices' }}
                </div>
                <div class="text-caption text-grey-7">
                  {{ vendorInvoiceSubtitle }}
                </div>
              </div>
            </div>
          </div>
          <q-space />
          <q-btn icon="close" flat round dense @click="closeVendorInvoices" />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="row q-col-gutter-md q-mb-sm">
            <div class="col-12 col-md-6">
              <q-input
                v-model="vendorInvoiceSearch"
                dense
                outlined
                clearable
                label="Filter invoices"
                placeholder="Invoice, contact, status, PO…"
              >
                <template #prepend>
                  <q-icon name="search" />
                </template>
              </q-input>
            </div>
          </div>

          <q-table
            v-drag-pan
            flat
            bordered
            dense
            row-key="id"
            :rows="filteredVendorInvoices"
            :columns="vendorInvoiceColumns"
            :loading="vendorInvoicesLoading"
            :rows-per-page-options="[10, 25, 50, 0]"
            no-data-label="No invoices found for this vendor"
            @row-click="(_, row) => openInvoiceDetails(row)"
          >
            <template #body-cell-status="props">
              <q-td :props="props">
                <q-badge :color="invoiceStatusColor(props.row.status)">
                  {{ invoiceStatusLabel(props.row.status) }}
                </q-badge>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </q-dialog>

    <q-dialog v-model="invoiceDetailsOpen" full-width>
      <q-card class="inventory-detail-card">
        <q-card-section class="row items-start">
          <div>
            <div class="text-h6">
              {{ selectedInvoice?.invoice_number || 'Invoice' }}
            </div>
            <div class="text-caption text-grey-7">
              {{ selectedInvoice?.vendor_name || 'No vendor' }}
              <span v-if="selectedInvoice?.contact_name">• {{ selectedInvoice.contact_name }}</span>
              <span v-if="selectedInvoice?.customer_po">• PO {{ selectedInvoice.customer_po }}</span>
            </div>
          </div>
          <q-space />
          <q-btn icon="close" flat round dense @click="closeInvoiceDetails" />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="row q-col-gutter-md q-mb-sm">
            <div class="col-12 col-md-6">
              <q-input
                v-model="invoiceLineItemSearch"
                dense
                outlined
                clearable
                label="Filter line items"
                placeholder="Item, description, job, notes…"
              >
                <template #prepend>
                  <q-icon name="search" />
                </template>
              </q-input>
            </div>
          </div>

          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Status</div>
                  <q-badge :color="invoiceStatusColor(selectedInvoice?.status)">
                    {{ invoiceStatusLabel(selectedInvoice?.status) }}
                  </q-badge>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Progress</div>
                  <div class="text-h6">{{ invoiceReceivedSummary(selectedInvoice) }}</div>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Total</div>
                  <div class="text-h6">{{ formatTypedValue(selectedInvoice?.invoice_total, 'currency') }}</div>
                </q-card-section>
              </q-card>
            </div>
          </div>

          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Job / PO</div>
                  <div class="text-caption text-grey-7 q-mt-sm">{{ invoiceJobSummary(selectedInvoice).label }}</div>
                  <div class="text-body1">{{ invoiceJobSummary(selectedInvoice).value }}</div>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Dates</div>
                  <div
                    v-for="dateField in invoiceDateSummary(selectedInvoice)"
                    :key="dateField.label"
                    class="row items-start justify-between q-mt-xs"
                  >
                    <div class="text-caption text-grey-7">{{ dateField.label }}</div>
                    <div class="text-body1 text-right">{{ dateField.value }}</div>
                  </div>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-sm-4">
              <q-card flat bordered class="panel-card">
                <q-card-section>
                  <div class="text-caption text-grey-7">Line Items</div>
                  <div class="text-h6">{{ invoiceLineItemCount(selectedInvoice) }}</div>
                </q-card-section>
              </q-card>
            </div>
          </div>

          <q-table
            v-drag-pan
            flat
            bordered
            dense
            row-key="id"
            :rows="filteredInvoiceLineItems"
            :columns="invoiceLineItemColumns"
            :loading="invoiceDetailsLoading"
            :rows-per-page-options="[0]"
            hide-pagination
            no-data-label="No line items found for this invoice"
          >
            <template #body-cell-received="props">
              <q-td :props="props" auto-width>
                <div class="row items-center no-wrap q-gutter-xs">
                  <q-checkbox
                    :model-value="props.row.received"
                    :disable="isLineItemSaving(props.row.id)"
                    @update:model-value="value => setInvoiceLineItemReceived(props.row, value)"
                  />
                  <q-spinner v-if="isLineItemSaving(props.row.id)" size="xs" color="primary" />
                </div>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Notify } from 'quasar'
import { fetchAPI, patchAPI } from '../utils/api'
import { crudSyncTick, notifyCrudChanged } from '../utils/crudSync'
import CrudManager from '../components/CrudManager.vue'
import ItemTypeManager from '../components/ItemTypeManager.vue'
import InvoiceList from '../components/InvoiceList.vue'
import { dragPanDirective } from '../utils/dragPan'
import { formatTypedValue } from '../utils/formatters'
import { buildItemTypeOptions } from '../utils/itemTypes'

const activeTab = ref('overview')
const loading = ref(false)
const oauthStatus = new URLSearchParams(window.location.search).get('googleAuth')
const vDragPan = dragPanDirective

const vendors = ref([])
const itemTypes = ref([])
const contacts = ref([])
const jobs = ref([])
const invoices = ref([])
const inventoryItems = ref([])
const lineItems = ref([])
const vendorCount = ref(0)
const itemTypeCount = ref(0)
const contactCount = ref(0)
const jobCount = ref(0)
const invoiceCount = ref(0)
const inventoryItemCount = ref(0)
const lineItemCount = ref(0)
const parserOptions = ref([])
const invoiceDetailsOpen = ref(false)
const selectedInvoice = ref(null)
const invoiceDetailsLoading = ref(false)
const lineItemSavingIds = ref([])
const inventoryDetailsOpen = ref(false)
const selectedInventoryItem = ref(null)
const inventoryLineItems = ref([])
const inventoryLineItemsLoading = ref(false)
const inventoryLineItemSearch = ref('')
const vendorInvoicesOpen = ref(false)
const selectedVendorForInvoices = ref(null)
const vendorInvoices = ref([])
const vendorInvoicesLoading = ref(false)
const vendorInvoiceSearch = ref('')
const invoiceLineItemSearch = ref('')

const summaryCards = computed(() => [
  { label: 'Vendors', value: vendorCount.value, icon: 'business', color: 'primary' },
  { label: 'Invoices', value: invoiceCount.value, icon: 'description', color: 'secondary' },
  { label: 'Inventory Items', value: inventoryItemCount.value, icon: 'inventory_2', color: 'accent' },
  { label: 'Line Items', value: lineItemCount.value, icon: 'view_list', color: 'warning' },
  { label: 'Contacts', value: contactCount.value, icon: 'contacts', color: 'positive' },
  { label: 'Jobs', value: jobCount.value, icon: 'work', color: 'info' },
])

const filteredInventoryLineItems = computed(() => (
  inventoryLineItems.value.filter(item => rowMatchesSearch(item, inventoryLineItemSearch.value, [
    'invoice_number',
    'invoice_date',
    'item_id',
    'description',
    'job_number',
    'job_name',
    'notes',
  ]))
))

const filteredVendorInvoices = computed(() => (
  vendorInvoices.value.filter(invoice => rowMatchesSearch(invoice, vendorInvoiceSearch.value, [
    'invoice_number',
    'invoice_date',
    'received_at',
    'contact_name',
    'status',
    'customer_po',
    'invoice_total',
  ]))
))

const vendorInvoiceSubtitle = computed(() => {
  const vendor = selectedVendorForInvoices.value
  const countLabel = `${vendorInvoices.value.length} invoice${vendorInvoices.value.length === 1 ? '' : 's'}`
  if (!vendor) {
    return countLabel
  }
  const parts = [countLabel]
  const location = [vendor.city, vendor.state].filter(Boolean).join(', ')
  if (location) {
    parts.push(location)
  }
  if (vendor.email) {
    parts.push(vendor.email)
  }
  if (vendor.phone) {
    parts.push(vendor.phone)
  }
  if (vendor.ignore) {
    parts.push('Ignored')
  }
  return parts.join(' · ')
})

const filteredInvoiceLineItems = computed(() => (
  invoiceLineItems(selectedInvoice.value).filter(item => rowMatchesSearch(item, invoiceLineItemSearch.value, [
    'item_id',
    'name',
    'description',
    'job_number',
    'job_name',
    'unit',
    'notes',
  ]))
))

const vendorColumns = [
  { name: 'logo', label: 'Logo', field: 'logo', urlField: 'logo_url', align: 'left', format: 'image' },
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'ignore', label: 'Ignore', field: 'ignore', align: 'left', format: 'boolean', sortable: true },
  { name: 'email', label: 'Email', field: 'email', align: 'left', sortable: true },
  { name: 'phone', label: 'Phone', field: 'phone', align: 'left', sortable: true },
  { name: 'city', label: 'City', field: 'city', align: 'left', sortable: true },
  { name: 'invoice_type', label: 'Type', field: 'invoice_type', align: 'left', sortable: true },
  { name: 'parser', label: 'Parser', field: 'parser', align: 'left', sortable: true },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const vendorFields = computed(() => [
  { key: 'ignore', label: 'Ignore vendor (hide from emails and invoices)', type: 'toggle', colClass: 'col-12' },
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'logo', label: 'Logo', type: 'image', colClass: 'col-12 col-md-4' },
  { key: 'invoice_type', label: 'Invoice Type', type: 'select', options: [{ label: 'PDF', value: 'pdf' }] },
  { key: 'parser', label: 'Parser', type: 'select', options: parserOptions.value },
  { key: 'email', label: 'Email', type: 'email' },
  { key: 'phone', label: 'Phone', type: 'text' },
  { key: 'website', label: 'Website', type: 'url' },
  { key: 'address', label: 'Address', type: 'textarea', colClass: 'col-12' },
  { key: 'city', label: 'City', type: 'text' },
  { key: 'state', label: 'State', type: 'text' },
  { key: 'zip_code', label: 'ZIP', type: 'text' },
  { key: 'country', label: 'Country', type: 'text' },
])

const contactColumns = [
  { name: 'name', label: 'Name', field: 'name', align: 'left' },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left', sortField: 'vendor__name' },
  { name: 'email', label: 'Email', field: 'email', align: 'left' },
  { name: 'phone', label: 'Phone', field: 'phone', align: 'left' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const jobColumns = [
  { name: 'job_id', label: 'Job ID', field: 'job_id', align: 'left', sortable: true },
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left', sortField: 'vendor__name' },
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
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left', sortable: true, sortField: 'vendor__name' },
  { name: 'item_type_name', label: 'Type', field: 'item_type_name', align: 'left', sortable: true, sortField: 'item_type__name' },
  { name: 'current_qty', label: 'Qty', field: 'current_qty', align: 'right', type: 'number', format: value => formatTypedValue(value, 'number') },
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
  { name: 'invoice_number', label: 'Invoice #', field: 'invoice_number', align: 'left', sortable: true },
  { name: 'vendor_name', label: 'Vendor', field: 'vendor_name', align: 'left', sortable: true, sortField: 'vendor__name' },
  { name: 'contact_name', label: 'Contact', field: 'contact_name', align: 'left', sortable: true, sortField: 'contact__name' },
  { name: 'invoice_date', label: 'Invoice Date', field: 'invoice_date', align: 'left', sortable: true },
  { name: 'received_at', label: 'Received', field: 'received_at', align: 'left', sortable: true },
  { name: 'status', label: 'Status', field: 'status', align: 'left', sortable: true, format: 'badge', badgeLabel: row => invoiceStatusLabel(row.status), badgeColor: row => invoiceStatusColor(row.status) },
  { name: 'invoice_total', label: 'Total', field: 'invoice_total', align: 'right', type: 'currency', format: value => formatTypedValue(value, 'currency') },
  { name: 'line_item_count', label: 'Items', field: 'line_item_count', align: 'right', type: 'number', format: value => formatTypedValue(value, 'number'), sortField: 'line_item_count_sort' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

const vendorInvoiceColumns = [
  { name: 'invoice_number', label: 'Invoice #', field: 'invoice_number', align: 'left', sortable: true },
  { name: 'invoice_date', label: 'Invoice Date', field: 'invoice_date', align: 'left', sortable: true },
  { name: 'received_at', label: 'Received', field: 'received_at', align: 'left', sortable: true },
  { name: 'contact_name', label: 'Contact', field: 'contact_name', align: 'left', sortable: true },
  { name: 'status', label: 'Status', field: 'status', align: 'left', sortable: true, format: 'badge', badgeLabel: row => invoiceStatusLabel(row.status), badgeColor: row => invoiceStatusColor(row.status) },
  { name: 'invoice_total', label: 'Total', field: 'invoice_total', align: 'right', type: 'currency', format: value => formatTypedValue(value, 'currency'), sortable: true },
  { name: 'line_item_count', label: 'Items', field: 'line_item_count', align: 'right', type: 'number', format: value => formatTypedValue(value, 'number'), sortable: true },
]

const invoiceFields = computed(() => [
  { key: 'vendor', label: 'Vendor', type: 'select', options: vendorOptions.value, clearable: true },
  { key: 'contact', label: 'Contact', type: 'select', options: contactOptions.value, clearable: true },
  { key: 'source_email_id', label: 'Source Email ID', type: 'text' },
  { key: 'source_email_subject', label: 'Source Email Subject', type: 'text' },
  { key: 'source_email_from', label: 'Source Email From', type: 'text' },
  { key: 'received_at', label: 'Received At', type: 'datetime' },
  { key: 'invoice_number', label: 'Invoice #', type: 'text' },
  { key: 'invoice_date', label: 'Invoice Date', type: 'date' },
  { key: 'ship_date', label: 'Ship Date', type: 'date' },
  { key: 'due_date', label: 'Due Date', type: 'date' },
  { key: 'customer_po', label: 'Customer PO', type: 'text' },
  { key: 'invoice_total', label: 'Invoice Total', type: 'number' },
  { key: 'status', label: 'Status', type: 'select', options: [
    { label: 'Pending', value: 'pending' },
    { label: 'Processed', value: 'processed' },
    { label: 'Partially Received', value: 'partially_received' },
    { label: 'Received', value: 'received' },
    { label: 'Error', value: 'error' },
  ] },
  { key: 'error_message', label: 'Error Message', type: 'textarea', colClass: 'col-12' },
])

const vendorDefaults = {
  ignore: false,
  name: '',
  logo: null,
  logo_url: null,
  address: '',
  city: '',
  state: '',
  zip_code: '',
  country: '',
  phone: '',
  email: '',
  website: '',
  invoice_type: 'pdf',
  parser: '',
}
const jobDefaults = { vendor: null, job_id: '', name: '', notes: '' }
const contactDefaults = { vendor: null, name: '', email: '', phone: '', title: '', is_primary: false, notes: '' }
const inventoryDefaults = { vendor: null, item_type: null, item_key: '', item_id: '', name: '', description: '', unit: '', current_qty: 0, last_unit_price: null, last_total_price: null }
const invoiceDefaults = { vendor: null, contact: null, source_email_id: '', source_email_subject: '', source_email_from: '', source_email_date: '', received_at: '', invoice_number: '', invoice_date: '', ship_date: '', due_date: '', customer_po: '', invoice_total: null, status: 'pending', error_message: '' }

const vendorOptions = computed(() => vendors.value.map(v => ({ label: v.name, value: v.id })))
const itemTypeOptions = computed(() => buildItemTypeOptions(itemTypes.value))
const contactOptions = computed(() => contacts.value.map(c => ({
  label: [
    c.name,
    c.email,
    c.vendor_name,
  ].filter(Boolean).join(' • '),
  value: c.id,
})))
const inventoryLineItemColumns = [
  { name: 'invoice_number', label: 'Invoice', field: 'invoice_number', align: 'left', sortable: true },
  { name: 'invoice_date', label: 'Date', field: 'invoice_date', align: 'left', sortable: true },
  { name: 'item_id', label: 'Item ID', field: 'item_id', align: 'left', sortable: true },
  { name: 'description', label: 'Description', field: 'description', align: 'left', sortable: true },
  {
    name: 'job',
    label: 'Job',
    field: row => [row.job_number, row.job_name].filter(Boolean).join(' • '),
    align: 'left',
    sortable: true,
  },
  { name: 'qty', label: 'Qty', field: 'qty', align: 'right', type: 'number', format: value => formatTypedValue(value, 'number'), sortable: true },
  { name: 'unit_price', label: 'Unit Price', field: 'unit_price', align: 'right', type: 'currency', format: value => formatTypedValue(value, 'currency'), sortable: true },
  { name: 'total_price', label: 'Total', field: 'total_price', align: 'right', type: 'currency', format: value => formatTypedValue(value, 'currency'), sortable: true },
  { name: 'received', label: 'Received', field: 'received', align: 'center', sortable: true },
  { name: 'notes', label: 'Notes', field: 'notes', align: 'left', sortable: true },
]

const invoiceLineItemColumns = [
  { name: 'received', label: 'Received', field: 'received', align: 'center', sortable: true },
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'description', label: 'Description', field: 'description', align: 'left', sortable: true },
  { name: 'qty', label: 'Qty', field: 'qty', align: 'right', type: 'number', format: value => formatTypedValue(value, 'number'), sortable: true },
  { name: 'unit', label: 'Unit', field: 'unit', align: 'left', sortable: true },
  { name: 'unit_price', label: 'Unit Price', field: 'unit_price', align: 'right', type: 'currency', format: value => formatTypedValue(value, 'currency'), sortable: true },
  { name: 'total_price', label: 'Total', field: 'total_price', align: 'right', type: 'currency', format: value => formatTypedValue(value, 'currency'), sortable: true },
  { name: 'job', label: 'Job', field: row => [row.job_number, row.job_name].filter(Boolean).join(' • '), align: 'left', sortable: true },
]

function mapList (data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.results)) return data.results
  return []
}

function mapCount (data) {
  if (typeof data?.count === 'number') return data.count
  if (Array.isArray(data)) return data.length
  if (Array.isArray(data?.results)) return data.results.length
  return 0
}

function invoiceStatusLabel (status) {
  const labels = {
    pending: 'Pending',
    processed: 'Processed',
    partially_received: 'Partially Received',
    received: 'Received',
    error: 'Error',
  }
  return labels[status] || status || 'Pending'
}

function invoiceStatusColor (status) {
  const colors = {
    pending: 'grey-6',
    processed: 'primary',
    partially_received: 'warning',
    received: 'positive',
    error: 'negative',
  }
  return colors[status] || 'grey-6'
}

function formatQuantity (value) {
  return formatTypedValue(value, 'number')
}

function normalizeSearchValue (value) {
  return String(value ?? '').toLowerCase()
}

function rowMatchesSearch (row, search, fields) {
  const needle = normalizeSearchValue(search).trim()
  if (!needle) {
    return true
  }
  return fields.some((field) => {
    const value = typeof field === 'function' ? field(row) : row?.[field]
    return normalizeSearchValue(value).includes(needle)
  })
}

async function loadInventoryLineItems (inventoryItemId) {
  inventoryLineItemsLoading.value = true
  try {
    const data = await fetchAPI(`/api/line-items/?inventory_item=${inventoryItemId}`)
    inventoryLineItems.value = mapList(data)
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: 'Failed to load inventory line items',
    })
    inventoryLineItems.value = []
  } finally {
    inventoryLineItemsLoading.value = false
  }
}

async function openInventoryDetails (payload) {
  const row = payload?.row || payload
  if (!row?.id) {
    return
  }
  selectedInventoryItem.value = row
  inventoryLineItemSearch.value = ''
  inventoryDetailsOpen.value = true
  await loadInventoryLineItems(row.id)
}

function closeInventoryDetails () {
  inventoryDetailsOpen.value = false
  selectedInventoryItem.value = null
  inventoryLineItems.value = []
  inventoryLineItemSearch.value = ''
}

async function loadVendorInvoices (vendorId) {
  vendorInvoicesLoading.value = true
  try {
    const data = await fetchAPI(`/api/invoices/?vendorId=${vendorId}&page_size=200`)
    vendorInvoices.value = mapList(data)
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: 'Failed to load vendor invoices',
    })
    vendorInvoices.value = []
  } finally {
    vendorInvoicesLoading.value = false
  }
}

async function openVendorInvoices (payload) {
  const row = payload?.row || payload
  if (!row?.id) {
    return
  }
  selectedVendorForInvoices.value = row
  vendorInvoiceSearch.value = ''
  vendorInvoicesOpen.value = true
  await loadVendorInvoices(row.id)
}

function closeVendorInvoices () {
  vendorInvoicesOpen.value = false
  selectedVendorForInvoices.value = null
  vendorInvoices.value = []
  vendorInvoiceSearch.value = ''
}

function isLineItemSaving (lineItemId) {
  return lineItemSavingIds.value.includes(lineItemId)
}

function invoiceLineItems (invoice) {
  return invoice?.line_items || []
}

function invoiceReceivedCount (invoice) {
  return invoiceLineItems(invoice).filter(item => item.received).length
}

function invoiceLineItemCount (invoice) {
  return invoiceLineItems(invoice).length
}

function invoiceJobSummary (invoice) {
  const jobValues = [...new Set(
    invoiceLineItems(invoice)
      .map(item => [item.job_number, item.job_name].filter(Boolean).join(' • '))
      .filter(Boolean),
  )]
  const resolvedJob = jobValues.length === 1 ? jobValues[0] : ''
  const po = invoice?.customer_po || ''

  return {
    label: resolvedJob ? 'Job' : 'Customer PO',
    value: resolvedJob || po || '—',
  }
}

function invoiceDateSummary (invoice) {
  return [
    { label: 'Invoice Date', value: invoice?.invoice_date || '—' },
    { label: 'Ship Date', value: invoice?.ship_date || '—' },
    { label: 'Due Date', value: invoice?.due_date || '—' },
    { label: 'Received At', value: invoice?.received_at || '—' },
  ]
}

function invoiceReceivedSummary (invoice) {
  const total = invoiceLineItemCount(invoice)
  const received = invoiceReceivedCount(invoice)
  return total ? `${received} / ${total} received` : 'No line items'
}

async function loadInvoiceDetails (invoiceId) {
  invoiceDetailsLoading.value = true
  try {
    const data = await fetchAPI(`/api/invoices/${invoiceId}/`)
    selectedInvoice.value = data
    invoiceLineItemSearch.value = ''
    invoiceDetailsOpen.value = true
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: 'Failed to load invoice details',
    })
  } finally {
    invoiceDetailsLoading.value = false
  }
}

async function openInvoiceDetails (payload) {
  const row = payload?.row || payload
  if (!row?.id) {
    return
  }
  await loadInvoiceDetails(row.id)
}

function closeInvoiceDetails () {
  invoiceDetailsOpen.value = false
  selectedInvoice.value = null
  invoiceLineItemSearch.value = ''
}

async function setInvoiceLineItemReceived (lineItem, received) {
  if (!selectedInvoice.value?.id || isLineItemSaving(lineItem.id)) {
    return
  }

  lineItemSavingIds.value = [...lineItemSavingIds.value, lineItem.id]
  try {
    await patchAPI(`/api/line-items/${lineItem.id}/`, {
      received,
    })
    await loadInvoiceDetails(selectedInvoice.value.id)
    notifyCrudChanged()
  } catch (error) {
    console.error(error)
    Notify.create({
      type: 'negative',
      message: 'Failed to update line item',
    })
  } finally {
    lineItemSavingIds.value = lineItemSavingIds.value.filter(id => id !== lineItem.id)
  }
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
      fetchAPI('/api/vendors/?page_size=200'),
      fetchAPI('/api/item-types/?page_size=200'),
      fetchAPI('/api/contacts/?page_size=200'),
      fetchAPI('/api/jobs/?page_size=1'),
      fetchAPI('/api/invoices/?page_size=1'),
      fetchAPI('/api/inventory-items/?page_size=1'),
      fetchAPI('/api/line-items/?page_size=1'),
      fetchAPI('/api/vendors/get_invoice_parsers/'),
    ])

    vendors.value = mapList(vendorData)
    itemTypes.value = mapList(itemTypeData)
    contacts.value = mapList(contactData)
    jobs.value = mapList(jobData)
    invoices.value = mapList(invoiceData)
    inventoryItems.value = mapList(inventoryData)
    lineItems.value = mapList(lineItemData)
    vendorCount.value = mapCount(vendorData)
    itemTypeCount.value = mapCount(itemTypeData)
    contactCount.value = mapCount(contactData)
    jobCount.value = mapCount(jobData)
    invoiceCount.value = mapCount(invoiceData)
    inventoryItemCount.value = mapCount(inventoryData)
    lineItemCount.value = mapCount(lineItemData)
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

watch(crudSyncTick, () => {
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

.vendor-dialog-logo {
  width: 56px;
  border-radius: 12px;
}
</style>
