export const ITEM_TYPE_ICON_OPACITY = 0.65

function parseHexRgb (color) {
  let hex = (color || '').trim().replace(/^#/, '')
  if (!hex) {
    return null
  }
  if (hex.length === 3) {
    hex = hex.split('').map(ch => ch + ch).join('')
  }
  if (hex.length === 8) {
    hex = hex.slice(0, 6)
  }
  if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
    return null
  }
  return {
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
  }
}

/** CSS color for an item-type icon from its hex/rgb color at reduced opacity. */
export function itemTypeIconColor (color, opacity = ITEM_TYPE_ICON_OPACITY) {
  const trimmed = (color || '').trim()
  if (!trimmed) {
    return null
  }
  const rgbaMatch = trimmed.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)$/i)
  if (rgbaMatch) {
    const alpha = rgbaMatch[4] != null ? Number(rgbaMatch[4]) * opacity : opacity
    return `rgba(${rgbaMatch[1]}, ${rgbaMatch[2]}, ${rgbaMatch[3]}, ${alpha})`
  }
  const rgb = parseHexRgb(trimmed)
  if (!rgb) {
    return trimmed
  }
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${opacity})`
}

export function itemTypeIconStyle (color, opacity = ITEM_TYPE_ICON_OPACITY) {
  const iconColor = itemTypeIconColor(color, opacity)
  return iconColor ? { color: iconColor } : {}
}

/**
 * Build flat select options from nested item types (parent FK).
 */
export function buildItemTypeOptions (itemTypes, { excludeIds = [] } = {}) {
  const excluded = new Set(excludeIds.filter(Boolean))
  const byParent = new Map()

  for (const item of itemTypes) {
    if (excluded.has(item.id)) {
      continue
    }
    const parentKey = item.parent ?? null
    if (!byParent.has(parentKey)) {
      byParent.set(parentKey, [])
    }
    byParent.get(parentKey).push(item)
  }

  const options = []
  const walk = (parentId, prefix) => {
    const siblings = (byParent.get(parentId) || [])
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
    for (const item of siblings) {
      const label = prefix ? `${prefix} › ${item.name}` : item.name
      options.push({
        label,
        value: item.id,
        icon: item.icon || undefined,
        color: item.color || undefined,
        full_path: item.full_path || label,
      })
      walk(item.id, label)
    }
  }

  walk(null, '')
  return options
}

/** Collect this type and all descendant ids (for parent picker exclusion). */
export function collectItemTypeDescendantIds (itemTypes, rootId) {
  if (!rootId) {
    return []
  }
  const byParent = new Map()
  for (const item of itemTypes) {
    const parentKey = item.parent ?? null
    if (!byParent.has(parentKey)) {
      byParent.set(parentKey, [])
    }
    byParent.get(parentKey).push(item.id)
  }
  const ids = []
  const walk = (parentId) => {
    for (const childId of byParent.get(parentId) || []) {
      ids.push(childId)
      walk(childId)
    }
  }
  walk(rootId)
  return ids
}

/** Parent picker options for the editor (excludes self and descendants). */
export function parentOptionsForEditor (itemTypes, editingId = null) {
  const excludeIds = editingId
    ? [editingId, ...collectItemTypeDescendantIds(itemTypes, editingId)]
    : []
  return buildItemTypeOptions(itemTypes, { excludeIds })
}

/** Flat list ordered for tree-style table display. */
export function orderItemTypesForTable (itemTypes) {
  const ordered = buildItemTypeOptions(itemTypes)
  const byId = new Map(itemTypes.map(item => [item.id, item]))
  return ordered.map(option => byId.get(option.value)).filter(Boolean)
}

export function itemTypeDepth (item, itemTypesById) {
  let depth = 0
  let current = item
  const seen = new Set()
  while (current?.parent != null) {
    if (seen.has(current.parent)) {
      break
    }
    seen.add(current.parent)
    current = itemTypesById.get(current.parent)
    if (!current) {
      break
    }
    depth += 1
  }
  return depth
}

export function previewItemTypePath (name, parentId, itemTypes) {
  const trimmed = (name || '').trim()
  if (!parentId) {
    return trimmed
  }
  const parent = itemTypes.find(item => item.id === parentId)
  if (!parent) {
    return trimmed
  }
  const parentPath = parent.full_path || parent.name
  return trimmed ? `${parentPath} › ${trimmed}` : parentPath
}
