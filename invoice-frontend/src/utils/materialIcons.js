import materialIconNames from '@quasar/extras/material-icons/icons.json'

function toMatKey (name) {
  return `mat${name.split('_').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join('')}`
}

const materialIconKeySet = new Set(materialIconNames)

export function isMaterialIconAvailable (name) {
  return Boolean(name && materialIconKeySet.has(toMatKey(name)))
}

const ITEM_TYPE_ICON_CANDIDATES = [
  'access_time',
  'architecture',
  'bathroom',
  'bed',
  'block',
  'bolt',
  'border_all',
  'brush',
  'build_circle',
  'build',
  'carpenter',
  'category',
  'chair',
  'checkroom',
  'computer',
  'construction',
  'content_cut',
  'countertops',
  'deck',
  'design_services',
  'donut_large',
  'door_back',
  'door_front',
  'door_sliding',
  'electrical_services',
  'extension',
  'factory',
  'forest',
  'format_paint',
  'garage',
  'grid_view',
  'group',
  'handyman',
  'hardware',
  'home_repair_service',
  'home',
  'inbox',
  'inventory_2',
  'key',
  'kitchen',
  'label',
  'layers',
  'lightbulb',
  'local_laundry_service',
  'local_shipping',
  'lock',
  'money',
  'palette',
  'plumbing',
  'precision_manufacturing',
  'rectangle',
  'shopping_cart',
  'square_foot',
  'storage',
  'store',
  'square',
  'straighten',
  'table_restaurant',
  'tune',
  'view_column',
  'view_module',
  'view_quilt',
  'warehouse',
  'water_drop',
  'widgets',
]

export const ITEM_TYPE_ICONS = ITEM_TYPE_ICON_CANDIDATES.filter(isMaterialIconAvailable)

export function filterMaterialIcons (icons, query) {
  const needle = (query || '').trim().toLowerCase()
  if (!needle) {
    return icons
  }
  return icons.filter(icon => icon.includes(needle))
}
