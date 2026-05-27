function isInteractiveElement (element) {
  if (!element || !(element instanceof HTMLElement)) {
    return false
  }

  return Boolean(
    element.closest('button, a, input, textarea, select, option, [role="button"], [data-no-pan="true"]'),
  )
}

function findScrollTarget (root) {
  return (
    root.querySelector('.q-table__middle.scroll')
    || root.querySelector('.q-table__middle')
    || root
  )
}

function attachDragPan (root) {
  const target = findScrollTarget(root)
  if (!target) {
    return () => {}
  }

  let isDown = false
  let isPanning = false
  let startX = 0
  let startY = 0
  let startScrollLeft = 0
  let startScrollTop = 0
  let suppressNextClick = false
  let previousUserSelect = ''
  let previousWebkitUserSelect = ''
  let previousMozUserSelect = ''
  let previousMsUserSelect = ''

  const DRAG_THRESHOLD = 4

  const setDraggingClass = (active) => {
    root.classList.toggle('drag-pan--active', active)
    if (active) {
      previousUserSelect = root.style.userSelect
      previousWebkitUserSelect = root.style.webkitUserSelect
      previousMozUserSelect = root.style.MozUserSelect
      previousMsUserSelect = root.style.msUserSelect
      root.style.userSelect = 'none'
      root.style.webkitUserSelect = 'none'
      root.style.MozUserSelect = 'none'
      root.style.msUserSelect = 'none'
      target.style.userSelect = 'none'
      target.style.webkitUserSelect = 'none'
      target.style.MozUserSelect = 'none'
      target.style.msUserSelect = 'none'
    } else {
      root.style.userSelect = previousUserSelect
      root.style.webkitUserSelect = previousWebkitUserSelect
      root.style.MozUserSelect = previousMozUserSelect
      root.style.msUserSelect = previousMsUserSelect
      target.style.userSelect = ''
      target.style.webkitUserSelect = ''
      target.style.MozUserSelect = ''
      target.style.msUserSelect = ''
    }
  }

  const onMouseMove = (event) => {
    if (!isDown) {
      return
    }

    const deltaX = event.clientX - startX
    const deltaY = event.clientY - startY

    if (!isPanning) {
      const distance = Math.hypot(deltaX, deltaY)
      if (distance < DRAG_THRESHOLD) {
        return
      }
      isPanning = true
      setDraggingClass(true)
    }

    event.preventDefault()
    target.scrollLeft = startScrollLeft - deltaX
    target.scrollTop = startScrollTop - deltaY
  }

  const endDrag = () => {
    if (isPanning) {
      suppressNextClick = true
    }
    isDown = false
    isPanning = false
    setDraggingClass(false)
    window.removeEventListener('mousemove', onMouseMove, true)
    window.removeEventListener('mouseup', endDrag, true)
  }

  const onMouseDown = (event) => {
    if (event.button !== 0 || isInteractiveElement(event.target)) {
      return
    }

    if (typeof target.scrollLeft !== 'number' && typeof target.scrollTop !== 'number') {
      return
    }

    isDown = true
    isPanning = false
    startX = event.clientX
    startY = event.clientY
    startScrollLeft = target.scrollLeft
    startScrollTop = target.scrollTop
    suppressNextClick = false
    target.style.cursor = 'grabbing'
    window.addEventListener('mousemove', onMouseMove, true)
    window.addEventListener('mouseup', endDrag, true)
  }

  const onClickCapture = (event) => {
    if (!suppressNextClick) {
      return
    }
    suppressNextClick = false
    event.preventDefault()
    event.stopImmediatePropagation()
  }

  target.style.cursor = 'grab'
  target.addEventListener('mousedown', onMouseDown)
  target.addEventListener('click', onClickCapture, true)

  return () => {
    target.style.cursor = ''
    root.style.userSelect = previousUserSelect
    root.style.webkitUserSelect = previousWebkitUserSelect
    root.style.MozUserSelect = previousMozUserSelect
    root.style.msUserSelect = previousMsUserSelect
    target.style.userSelect = ''
    target.style.webkitUserSelect = ''
    target.style.MozUserSelect = ''
    target.style.msUserSelect = ''
    target.classList.remove('drag-pan--active')
    target.removeEventListener('mousedown', onMouseDown)
    target.removeEventListener('click', onClickCapture, true)
    window.removeEventListener('mousemove', onMouseMove, true)
    window.removeEventListener('mouseup', endDrag, true)
  }
}

export const dragPanDirective = {
  mounted (el) {
    el._dragPanCleanup = attachDragPan(el)
  },
  updated (el) {
    if (el._dragPanCleanup) {
      el._dragPanCleanup()
    }
    el._dragPanCleanup = attachDragPan(el)
  },
  unmounted (el) {
    if (el._dragPanCleanup) {
      el._dragPanCleanup()
      delete el._dragPanCleanup
    }
  },
}
