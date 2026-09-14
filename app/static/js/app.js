const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || ''
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
let transactionPreviewTimer
let transactionPreviewHideTimer
let transactionPreviewController
let transactionPreviewElement

/* ---------- modal links ---------- */
document.addEventListener('click', async (event) => {
  const link = event.target.closest('[data-modal-url]')
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  event.stopPropagation()
  hideTransactionPreview()
  await openModal(link.dataset.modalUrl)
}, true)

/* ---------- transaction hover preview ---------- */
document.addEventListener('mouseover', (event) => {
  const trigger = event.target.closest('[data-transaction-preview-url]')
  if (!trigger || trigger.contains(event.relatedTarget)) return
  window.clearTimeout(transactionPreviewHideTimer)
  window.clearTimeout(transactionPreviewTimer)
  transactionPreviewTimer = window.setTimeout(() => showTransactionPreview(trigger), 700)
})

document.addEventListener('mouseout', (event) => {
  const trigger = event.target.closest('[data-transaction-preview-url]')
  if (!trigger || trigger.contains(event.relatedTarget)) return
  window.clearTimeout(transactionPreviewTimer)
  if (transactionPreviewElement?.contains(event.relatedTarget)) return
  scheduleTransactionPreviewHide()
})

/* ---------- ajax forms (modal + row actions) ---------- */
document.addEventListener('submit', async (event) => {
  const form = event.target
  const isTransactionAction = form.matches('[data-transaction-action]')
  const isModalForm = form.closest('#modal-root') !== null
  if (!isTransactionAction && !isModalForm) return

  event.preventDefault()
  event.stopPropagation()
  if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return

  const submitter = event.submitter
  if (submitter) {
    submitter.disabled = true
    submitter.classList.add('is-busy')
  }
  const row = isTransactionAction ? form.closest('tr, [data-dashboard-transaction]') : null
  try {
    const response = await fetch(form.action, {
      method: (form.method || 'post').toUpperCase(),
      body: new FormData(form),
      headers: { 'HX-Request': 'true', 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
    })
    const redirect = response.headers.get('HX-Redirect')
    if (redirect) {
      startNavProgress()
      if (row && form.action.endsWith('/delete')) row.classList.add('is-leaving')
      window.location.assign(redirect)
      return
    }
    if (response.redirected) {
      startNavProgress()
      window.location.assign(response.url)
      return
    }
    const html = await response.text()
    if (isModalForm) {
      const root = document.querySelector('#modal-root')
      root.innerHTML = html
      const panel = root.querySelector('.modal-panel')
      panel?.classList.add('no-enter')
      const rerendered = root.querySelector('form')
      if (rerendered && !response.ok) {
        rerendered.classList.add('is-invalid')
        rerendered.addEventListener('animationend', () => rerendered.classList.remove('is-invalid'), { once: true })
      }
      updateBalance(rerendered)
      enhance(root)
    } else if (!response.ok) {
      window.alert('Η ενέργεια δεν ολοκληρώθηκε. Δοκιμάστε ξανά.')
    }
  } catch (_error) {
    window.alert('Δεν ήταν δυνατή η επικοινωνία με την εφαρμογή.')
  } finally {
    if (submitter) {
      submitter.disabled = false
      submitter.classList.remove('is-busy')
    }
  }
}, true)

document.addEventListener('htmx:configRequest', (event) => {
  event.detail.headers['X-CSRFToken'] = csrfToken()
})

/* ---------- generic click handling ---------- */
document.addEventListener('click', (event) => {
  const drawerToggle = event.target.closest('[data-drawer-toggle]')
  const drawerClose = event.target.closest('[data-drawer-close]')
  if (drawerToggle) document.body.classList.toggle('drawer-open')
  if (drawerClose) document.body.classList.remove('drawer-open')

  const modalClose = event.target.closest('[data-modal-close]')
  if (modalClose) closeModal()

  const flashClose = event.target.closest('[data-flash-close]')
  if (flashClose) dismissFlash(flashClose.closest('[data-flash]'))

  const opener = event.target.closest('[data-open]')
  if (opener) document.getElementById(opener.dataset.open)?.showModal()
  if (event.target.closest('[data-dialog-close]')) event.target.closest('dialog')?.close()

  const datePicker = event.target.closest('[data-date-picker]')
  if (datePicker) {
    const nativeInput = datePicker.closest('[data-greek-date], .date-input-wrap')?.querySelector('[data-native-date]')
    try {
      if (nativeInput?.showPicker) nativeInput.showPicker()
      else nativeInput?.click()
    } catch (_error) {
      nativeInput?.click()
    }
  }

  const pdfExport = event.target.closest('[data-export-pdf]')
  if (pdfExport) {
    event.preventDefault()
    const controls = document.querySelector('[data-report-controls]')
    const reportType = controls.querySelector('[name="report_type"]').value
    const accountId = controls.querySelector('[name="account_id"]').value
    if (reportType === 'general_ledger' && !accountId) {
      window.alert('Επιλέξτε λογαριασμό για την καρτέλα.')
      return
    }
    const parameters = new URLSearchParams(new FormData(controls))
    pdfExport.classList.add('is-busy')
    window.setTimeout(() => pdfExport.classList.remove('is-busy'), 2500)
    window.location.assign(`${pdfExport.dataset.pdfUrl}?${parameters}`)
  }

  const remove = event.target.closest('[data-remove-line]')
  if (remove) {
    const lines = remove.closest('[data-entry-lines]')
    const line = remove.closest('.entry-line')
    if (lines.children.length > 2) {
      const form = lines.closest('form')
      if (reducedMotion()) {
        line.remove()
        updateBalance(form)
      } else {
        line.style.maxHeight = `${line.offsetHeight}px`
        line.classList.add('is-removing')
        line.addEventListener('animationend', () => {
          line.remove()
          updateBalance(form)
        }, { once: true })
      }
    }
    updateBalance(lines.closest('form'))
  }

  const add = event.target.closest('[data-add-line]')
  if (add) {
    const form = add.closest('form')
    const lines = form.querySelector('[data-entry-lines]')
    lines.append(form.querySelector('[data-line-template]').content.cloneNode(true))
    lines.lastElementChild?.querySelector('select')?.focus()
    updateBalance(form)
  }
}, true)

/* ---------- quick entry (many two-line transactions) ---------- */
const QUICK_INHERITED_FIELDS = ['row_date', 'row_debit', 'row_credit']

function addQuickRow(form, previous) {
  const rows = form.querySelector('[data-quick-rows]')
  const fragment = form.querySelector('[data-quick-template]').content.cloneNode(true)
  const row = fragment.querySelector('[data-quick-row]')
  const source = previous || rows.lastElementChild
  if (source) {
    QUICK_INHERITED_FIELDS.forEach((name) => {
      const from = source.querySelector(`[name="${name}"]`)
      const to = row.querySelector(`[name="${name}"]`)
      if (from && to && from.value) to.value = from.value
    })
  }
  const dateInput = row.querySelector('[data-greek-date]')
  if (dateInput) validateGreekDate(dateInput)
  rows.append(fragment)
  updateQuickTotals(form)
  rows.lastElementChild.querySelector('[data-quick-description]')?.focus()
}

function updateQuickTotals(form) {
  if (!form) return
  const rows = [...form.querySelectorAll('[data-quick-row]')]
  const filled = rows.filter((row) => ['row_description', 'row_debit', 'row_credit', 'row_amount']
    .some((name) => row.querySelector(`[name="${name}"]`)?.value.trim()))
  const total = filled.reduce((sum, row) => sum + (Number(row.querySelector('[name="row_amount"]')?.value) || 0), 0)
  form.querySelector('[data-quick-count]').textContent = filled.length
  form.querySelector('[data-quick-total]').textContent = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(total)
  form.querySelectorAll('[data-quick-remove]').forEach((button) => { button.disabled = rows.length <= 1 })
}

document.addEventListener('click', (event) => {
  const add = event.target.closest('[data-quick-add]')
  if (add) addQuickRow(add.closest('[data-quick-form]'))
  const remove = event.target.closest('[data-quick-remove]')
  if (remove) {
    const form = remove.closest('[data-quick-form]')
    const row = remove.closest('[data-quick-row]')
    if (form.querySelectorAll('[data-quick-row]').length > 1) {
      row.remove()
      updateQuickTotals(form)
    }
  }
}, true)

document.addEventListener('input', (event) => {
  const form = event.target.closest?.('[data-quick-form]')
  if (form) updateQuickTotals(form)
})

document.addEventListener('change', (event) => {
  const form = event.target.closest?.('[data-quick-form]')
  if (form) updateQuickTotals(form)
}, true)

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' || !event.target.matches?.('[data-quick-amount]')) return
  event.preventDefault()
  const form = event.target.closest('[data-quick-form]')
  const row = event.target.closest('[data-quick-row]')
  if (row === form.querySelector('[data-quick-rows]').lastElementChild) addQuickRow(form, row)
  else row.nextElementSibling?.querySelector('[data-quick-description]')?.focus()
})

/* ---------- ripple feedback ---------- */
document.addEventListener('pointerdown', (event) => {
  if (event.button !== 0 || reducedMotion()) return
  const host = event.target.closest('.icon-action, .button, .main-nav a, .page-arrow, .action-tile, .sidebar-icon')
  if (!host || host.matches(':disabled, .disabled')) return
  let layer = host.querySelector(':scope > .ripple-layer')
  if (!layer) {
    layer = document.createElement('span')
    layer.className = 'ripple-layer'
    host.prepend(layer)
  }
  const box = host.getBoundingClientRect()
  const size = Math.max(box.width, box.height)
  const ripple = document.createElement('span')
  ripple.className = 'ripple'
  ripple.style.setProperty('--ripple-size', `${size}px`)
  ripple.style.left = `${event.clientX - box.left - size / 2}px`
  ripple.style.top = `${event.clientY - box.top - size / 2}px`
  layer.append(ripple)
  ripple.addEventListener('animationend', () => ripple.remove(), { once: true })
})

/* ---------- native form confirms ---------- */
document.addEventListener('submit', (event) => {
  const message = event.target.dataset.confirm
  if (message && !window.confirm(message)) event.preventDefault()
})

/* ---------- inputs ---------- */
document.addEventListener('input', (event) => {
  if (event.target.matches('[data-greek-date]')) {
    event.target.value = formatGreekDateInput(event.target.value)
    validateGreekDate(event.target)
  }
  if (event.target.matches('[name="amount"]')) updateBalance(event.target.closest('form'))
})

document.addEventListener('blur', (event) => {
  if (event.target.matches('[data-greek-date]')) validateGreekDate(event.target)
}, true)

document.addEventListener('change', (event) => {
  if (event.target.matches('.file-drop input[type="file"]')) {
    const drop = event.target.closest('.file-drop')
    drop.classList.toggle('has-file', event.target.files.length > 0)
    return
  }
  if (event.target.matches('[data-native-date]')) {
    event.stopPropagation()
    const visibleInput = event.target.closest('.date-input-wrap').querySelector('[data-greek-date]')
    const [year, month, day] = event.target.value.split('-')
    if (year && month && day) {
      visibleInput.value = `${day}/${month}/${year}`
      validateGreekDate(visibleInput)
      visibleInput.dispatchEvent(new Event('change', { bubbles: true }))
    }
    return
  }
  if (!event.target.matches('[data-report-type]')) return
  const form = event.target.closest('form')
  const reportType = event.target.value
  const usesPeriod = ['income_statement', 'journal'].includes(reportType)
  form.querySelector('[data-as-of]').hidden = !['trial_balance', 'balance_sheet'].includes(reportType)
  form.querySelectorAll('[data-period]').forEach((field) => { field.hidden = !usesPeriod })
  form.querySelector('[data-ledger]').hidden = reportType !== 'general_ledger'
}, true)

/* file drop zones: drag feedback */
document.addEventListener('dragover', (event) => {
  const drop = event.target.closest('.file-drop')
  if (!drop) return
  event.preventDefault()
  drop.classList.add('is-dragover')
})
document.addEventListener('dragleave', (event) => {
  const drop = event.target.closest('.file-drop')
  if (drop && !drop.contains(event.relatedTarget)) drop.classList.remove('is-dragover')
})
document.addEventListener('drop', (event) => {
  const drop = event.target.closest('.file-drop')
  if (!drop) return
  event.preventDefault()
  drop.classList.remove('is-dragover')
  const input = drop.querySelector('input[type="file"]')
  if (input && event.dataTransfer?.files?.length) {
    input.files = event.dataTransfer.files
    input.dispatchEvent(new Event('change', { bubbles: true }))
  }
})

/* ---------- htmx lifecycle ---------- */
document.addEventListener('htmx:beforeRequest', () => startNavProgress())
document.addEventListener('htmx:afterSettle', () => finishNavProgress())
document.addEventListener('htmx:responseError', () => finishNavProgress())
document.addEventListener('htmx:sendError', () => finishNavProgress())
document.addEventListener('htmx:timeout', () => finishNavProgress())
window.addEventListener('pageshow', () => finishNavProgress())

document.addEventListener('htmx:afterSwap', (event) => {
  if (event.detail.target.id === 'modal-root') {
    document.body.classList.add('modal-open')
    updateBalance(event.detail.target.querySelector('form'))
  }
  if (event.detail.target.id === 'report-result') {
    document.querySelector('[data-export-pdf]')?.removeAttribute('aria-busy')
  }
})

document.addEventListener('htmx:beforeSwap', (event) => {
  if (event.detail.target.id === 'modal-root' && event.detail.xhr.status >= 400) event.detail.shouldSwap = true
  // Boosted navigation swaps only the main column, keeping the sidebar in place. Select/swap are applied
  // here rather than as inherited hx-select/hx-swap attributes so partial requests (reports) are unaffected.
  if (event.detail.target.id === 'page-content') {
    event.detail.selectOverride = '#page-content'
    event.detail.swapOverride = 'outerHTML show:window:top'
  }
  // Validation re-renders (422) of boosted page forms swap in place like a normal page.
  if (event.detail.target.id === 'page-content' && event.detail.xhr.status === 422) {
    event.detail.shouldSwap = true
    event.detail.isError = false
  }
  // Content-only swaps need a page shell in the response; otherwise (login page, error page) do a full navigation.
  if (event.detail.target.id === 'page-content' && !event.detail.xhr.responseText.includes('id="page-content"')) {
    event.detail.shouldSwap = false
    finishNavProgress()
    window.location.assign(event.detail.xhr.responseURL || event.detail.pathInfo?.finalRequestPath || window.location.href)
  }
})

document.addEventListener('htmx:afterSettle', (event) => {
  if (event.detail.target.id === 'page-content') {
    syncShell()
    document.body.classList.remove('drawer-open')
  }
})
window.addEventListener('popstate', () => window.setTimeout(syncShell, 0))

document.addEventListener('htmx:load', (event) => enhance(event.detail.elt))
document.addEventListener('DOMContentLoaded', () => enhance(document))

document.addEventListener('cancel', (event) => {
  if (event.target.matches('dialog')) event.preventDefault()
})

document.addEventListener('keydown', (event) => {
  const hasOpenModal = document.querySelector('#modal-root')?.children.length || document.querySelector('dialog[open]')
  if (event.key === 'Escape' && hasOpenModal) {
    event.preventDefault()
    event.stopPropagation()
  }
}, true)

/* ---------- keep sidebar + accent in sync with the swapped page ---------- */
function syncShell() {
  const main = document.getElementById('page-content')
  if (!main) return
  if (main.dataset.section) document.body.dataset.section = main.dataset.section
  const path = window.location.pathname
  document.querySelectorAll('.main-nav a[data-nav]').forEach((link) => {
    const href = link.getAttribute('href')
    const active = href === '/' ? path === '/' : path === href || path.startsWith(`${href}/`)
    link.classList.toggle('active', active)
  })
}

/* ---------- progressive enhancement of swapped content ---------- */
function enhance(root) {
  if (!root?.querySelectorAll) return
  root.querySelectorAll('[data-countup]:not([data-enhanced])').forEach((element) => {
    element.dataset.enhanced = 'true'
    countUp(element)
  })
  root.querySelectorAll?.('[data-quick-form]').forEach(updateQuickTotals)
  root.querySelectorAll('[data-flow-chart]:not([data-enhanced])').forEach((panel) => {
    panel.dataset.enhanced = 'true'
    restoreFlowHidden(panel)
  })
  root.querySelectorAll('[data-stream-chart]:not([data-enhanced])').forEach((panel) => {
    panel.dataset.enhanced = 'true'
    if (reducedMotion()) panel.querySelector('svg')?.pauseAnimations?.()
  })
  root.querySelectorAll('[data-flash]:not([data-enhanced])').forEach((flash) => {
    flash.dataset.enhanced = 'true'
    scheduleFlashDismiss(flash)
  })
}

function countUp(element) {
  if (reducedMotion()) return
  const text = element.textContent.trim()
  const match = text.match(/^(-?)([\d.]+),(\d{2})(.*)$/)
  if (!match) return
  const [, sign, whole, cents, suffix] = match
  const target = Number(`${whole.replace(/\./g, '')}.${cents}`)
  if (!Number.isFinite(target) || target === 0) return
  const formatter = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const duration = 900
  const start = performance.now()
  const frame = (now) => {
    const progress = Math.min(1, (now - start) / duration)
    const eased = 1 - Math.pow(1 - progress, 4)
    element.textContent = `${sign}${formatter.format(target * eased)}${suffix}`
    if (progress < 1) window.requestAnimationFrame(frame)
    else element.textContent = text
  }
  window.requestAnimationFrame(frame)
}

/* ---------- flashes ---------- */
function scheduleFlashDismiss(flash) {
  const life = flash.classList.contains('flash-error') ? 9000 : 6000
  flash.style.setProperty('--flash-life', `${life}ms`)
  let timer = window.setTimeout(() => dismissFlash(flash), life)
  flash.addEventListener('mouseenter', () => window.clearTimeout(timer))
  flash.addEventListener('mouseleave', () => { timer = window.setTimeout(() => dismissFlash(flash), 2500) })
}

function dismissFlash(flash) {
  if (!flash || flash.classList.contains('is-leaving')) return
  if (reducedMotion()) {
    flash.remove()
    return
  }
  flash.classList.add('is-leaving')
  flash.addEventListener('animationend', () => flash.remove(), { once: true })
}

/* ---------- navigation progress bar ---------- */
let navProgressTimer
function startNavProgress() {
  const bar = document.querySelector('[data-nav-progress]')
  if (!bar) return
  window.clearTimeout(navProgressTimer)
  bar.classList.remove('is-done')
  void bar.offsetWidth
  bar.classList.add('is-loading')
}

function finishNavProgress() {
  const bar = document.querySelector('[data-nav-progress]')
  if (!bar || !bar.classList.contains('is-loading')) return
  bar.classList.remove('is-loading')
  bar.classList.add('is-done')
  navProgressTimer = window.setTimeout(() => bar.classList.remove('is-done'), 500)
}

/* ---------- transaction balance ---------- */
function updateBalance(form) {
  if (!form?.matches('[data-transaction-form]')) return
  syncAutoBalance(form)
  const amounts = [...form.querySelectorAll('[name="amount"]')].map((input) => Number(input.value) || 0)
  const debits = amounts.filter((value) => value > 0).reduce((a, b) => a + b, 0)
  const credits = Math.abs(amounts.filter((value) => value < 0).reduce((a, b) => a + b, 0))
  form.querySelector('[data-debits]').textContent = debits.toFixed(2)
  form.querySelector('[data-credits]').textContent = credits.toFixed(2)
  const balanced = Math.abs(debits - credits) < 0.01
  const state = form.querySelector('[data-balance-state]')
  const text = state.querySelector('[data-balance-text]') || state
  text.textContent = balanced ? 'Ισοσκελισμένη' : `Διαφορά ${(debits - credits).toFixed(2)}`
  if (state.classList.contains('unbalanced') === balanced) {
    state.classList.add('is-flipping')
    window.setTimeout(() => state.classList.remove('is-flipping'), 250)
  }
  state.classList.toggle('unbalanced', !balanced)
  form.querySelector('[data-save-transaction]').disabled = !balanced
}

function syncAutoBalance(form) {
  if (!form.matches('[data-auto-balance]')) return
  const inputs = [...form.querySelectorAll('[name="amount"]')]
  if (inputs.length < 2) return

  inputs.forEach((input) => {
    input.readOnly = false
    input.classList.remove('auto-balanced-amount')
    input.removeAttribute('title')
  })

  const lastInput = inputs.at(-1)
  const previousTotalInCents = inputs
    .slice(0, -1)
    .reduce((total, input) => total + Math.round((Number(input.value) || 0) * 100), 0)
  const balancingCents = previousTotalInCents === 0 ? 0 : -previousTotalInCents
  lastInput.value = (balancingCents / 100).toFixed(2)
  lastInput.readOnly = true
  lastInput.classList.add('auto-balanced-amount')
  lastInput.title = 'Αυτόματη εξισορρόπηση'
  lastInput.setAttribute('aria-label', 'Ποσό αυτόματης εξισορρόπησης')
}

/* ---------- modal ---------- */
async function openModal(url) {
  const root = document.querySelector('#modal-root')
  if (!root) return
  root.innerHTML = '<div class="modal-loader" role="status" aria-label="Φόρτωση"></div>'
  document.body.classList.add('modal-open')
  try {
    const response = await fetch(url, {
      headers: { 'HX-Request': 'true' },
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    root.innerHTML = await response.text()
    updateBalance(root.querySelector('form'))
    enhance(root)
    root.querySelector('input:not([type="hidden"]), select, button')?.focus({ preventScroll: true })
  } catch (_error) {
    closeModal()
    window.alert('Δεν ήταν δυνατό το άνοιγμα της φόρμας.')
  }
}

function closeModal() {
  const root = document.querySelector('#modal-root')
  if (!root) return
  const modal = root.querySelector('[data-modal]')
  const finish = () => {
    root.innerHTML = ''
    document.body.classList.remove('modal-open')
  }
  if (!modal || reducedMotion() || modal.classList.contains('is-closing')) {
    if (!modal?.classList.contains('is-closing')) finish()
    return
  }
  modal.classList.add('is-closing')
  const panel = modal.querySelector('.modal-panel')
  let done = false
  const once = () => { if (!done) { done = true; finish() } }
  panel?.addEventListener('animationend', once, { once: true })
  window.setTimeout(once, 260)
}

/* ---------- transaction preview popover ---------- */
async function showTransactionPreview(trigger) {
  transactionPreviewController?.abort()
  transactionPreviewController = new AbortController()
  try {
    const response = await fetch(trigger.dataset.transactionPreviewUrl, {
      credentials: 'same-origin',
      signal: transactionPreviewController.signal,
    })
    if (!response.ok) return
    const html = await response.text()
    if (!trigger.matches(':hover')) return
    hideTransactionPreview()
    const popover = document.createElement('div')
    popover.className = 'transaction-preview-popover'
    popover.innerHTML = html
    popover.addEventListener('mouseenter', () => window.clearTimeout(transactionPreviewHideTimer))
    popover.addEventListener('mouseleave', scheduleTransactionPreviewHide)
    document.body.append(popover)
    transactionPreviewElement = popover
    positionTransactionPreview(popover, trigger)
  } catch (error) {
    if (error.name !== 'AbortError') hideTransactionPreview()
  }
}

function positionTransactionPreview(popover, trigger) {
  const triggerBox = trigger.getBoundingClientRect()
  const margin = 12
  const width = Math.min(390, window.innerWidth - margin * 2)
  popover.style.width = `${width}px`
  let left = Math.min(triggerBox.right - width, window.innerWidth - width - margin)
  left = Math.max(left, margin)
  let top = triggerBox.bottom + 9
  const height = popover.getBoundingClientRect().height
  if (top + height > window.innerHeight - margin) top = Math.max(margin, triggerBox.top - height - 9)
  popover.style.left = `${left}px`
  popover.style.top = `${top}px`
}

function scheduleTransactionPreviewHide() {
  window.clearTimeout(transactionPreviewHideTimer)
  transactionPreviewHideTimer = window.setTimeout(hideTransactionPreview, 180)
}

function hideTransactionPreview() {
  window.clearTimeout(transactionPreviewTimer)
  window.clearTimeout(transactionPreviewHideTimer)
  transactionPreviewController?.abort()
  transactionPreviewController = undefined
  transactionPreviewElement?.remove()
  transactionPreviewElement = undefined
}

window.addEventListener('scroll', hideTransactionPreview, true)
window.addEventListener('resize', hideTransactionPreview)

/* ---------- money-flow chart: tooltip + legend toggles ---------- */
const FLOW_HIDDEN_KEY = 'ficus.flow-hidden'
const FLOW_ROWS = [
  ['revenue', 'Έσοδα', 'flow-legend-revenue'],
  ['expenses', 'Έξοδα', 'flow-legend-expenses'],
  ['net', 'Αποτέλεσμα', 'flow-legend-net'],
  ['cashIn', 'Ταμειακές εισροές', 'flow-legend-cash-in'],
  ['cashOut', 'Ταμειακές εκροές', 'flow-legend-cash-out'],
]
let flowTooltipElement

document.addEventListener('mouseover', (event) => {
  const month = event.target.closest?.('.flow-month')
  if (!month || month.contains(event.relatedTarget)) return
  showFlowTooltip(month)
})
document.addEventListener('mouseout', (event) => {
  const month = event.target.closest?.('.flow-month')
  if (!month || month.contains(event.relatedTarget)) return
  hideFlowTooltip()
})
document.addEventListener('focusin', (event) => {
  const month = event.target.closest?.('.flow-month')
  if (month) showFlowTooltip(month)
})
document.addEventListener('focusout', (event) => {
  if (event.target.closest?.('.flow-month')) hideFlowTooltip()
})
window.addEventListener('scroll', hideFlowTooltip, true)
window.addEventListener('resize', hideFlowTooltip)

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-flow-toggle]')
  if (!button) return
  const panel = button.closest('[data-flow-chart]')
  const key = button.dataset.flowToggle
  const hidden = new Set((panel.dataset.flowHidden || '').split(' ').filter(Boolean))
  if (hidden.has(key)) hidden.delete(key)
  else hidden.add(key)
  applyFlowHidden(panel, hidden)
  try { localStorage.setItem(FLOW_HIDDEN_KEY, [...hidden].join(' ')) } catch (_error) { /* storage unavailable */ }
})

function applyFlowHidden(panel, hidden) {
  panel.dataset.flowHidden = [...hidden].join(' ')
  panel.querySelectorAll('[data-flow-toggle]').forEach((button) => {
    button.setAttribute('aria-pressed', String(!hidden.has(button.dataset.flowToggle)))
  })
}

function restoreFlowHidden(panel) {
  let stored = ''
  try { stored = localStorage.getItem(FLOW_HIDDEN_KEY) || '' } catch (_error) { /* storage unavailable */ }
  applyFlowHidden(panel, new Set(stored.split(' ').filter(Boolean)))
}

function formatMoney(value, currency) {
  const amount = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0)
  return `${amount} ${(currency || 'EUR').toUpperCase() === 'EUR' ? '€' : currency}`
}

function showFlowTooltip(month) {
  hideFlowTooltip()
  const currency = month.closest('[data-flow-chart]')?.dataset.currency
  const tooltip = document.createElement('div')
  tooltip.className = 'flow-tooltip'
  tooltip.setAttribute('role', 'tooltip')
  const title = document.createElement('strong')
  title.textContent = month.dataset.label
  const list = document.createElement('dl')
  FLOW_ROWS.forEach(([key, label, dotClass]) => {
    const term = document.createElement('dt')
    const dot = document.createElement('i')
    dot.className = `flow-legend-dot ${dotClass}`
    term.append(dot, label)
    const value = document.createElement('dd')
    value.textContent = formatMoney(month.dataset[key], currency)
    if (key === 'net') {
      term.classList.add('is-net')
      value.classList.add('is-net')
      if (Number(month.dataset.net) < 0) value.classList.add('negative')
    }
    list.append(term, value)
  })
  tooltip.append(title, list)
  document.body.append(tooltip)
  flowTooltipElement = tooltip
  const box = (month.querySelector('.flow-hit') || month).getBoundingClientRect()
  const margin = 12
  const { width, height } = tooltip.getBoundingClientRect()
  let left = box.left + box.width / 2 - width / 2
  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin))
  let top = box.top - height - 10
  if (top < margin) top = Math.min(box.bottom + 10, window.innerHeight - height - margin)
  tooltip.style.left = `${left}px`
  tooltip.style.top = `${top}px`
}

function hideFlowTooltip() {
  flowTooltipElement?.remove()
  flowTooltipElement = undefined
}

/* ---------- money-stream chart (where the money goes) ---------- */
let streamTooltipElement

function streamTarget(event) {
  return event.target.closest?.('.stream-link, .stream-node')
}

function streamKey(element) {
  return element.dataset.key
}

document.addEventListener('mouseover', (event) => {
  const element = streamTarget(event)
  if (!element || element.contains(event.relatedTarget)) return
  activateStream(element, { x: event.clientX, y: event.clientY })
})
document.addEventListener('mousemove', (event) => {
  if (!streamTooltipElement || !streamTarget(event)) return
  positionStreamTooltip(streamTooltipElement, { x: event.clientX, y: event.clientY })
})
document.addEventListener('mouseout', (event) => {
  const element = streamTarget(event)
  if (!element || element.contains(event.relatedTarget)) return
  deactivateStream(element)
})
document.addEventListener('focusin', (event) => {
  const element = streamTarget(event)
  if (!element) return
  const box = element.getBoundingClientRect()
  activateStream(element, { x: box.left + box.width / 2, y: box.top + box.height / 2 })
})
document.addEventListener('focusout', (event) => {
  const element = streamTarget(event)
  if (element) deactivateStream(element)
})
window.addEventListener('scroll', hideStreamTooltip, true)
window.addEventListener('resize', hideStreamTooltip)

function activateStream(element, point) {
  const panel = element.closest('[data-stream-chart]')
  const key = streamKey(element)
  panel.classList.add('is-hovering')
  panel.querySelectorAll('.stream-link, .stream-node').forEach((node) => {
    node.classList.toggle('is-active', streamKey(node) === key)
  })
  const link = panel.querySelector(`.stream-link[data-key="${CSS.escape(key)}"]`)
  if (link) showStreamTooltip(link, point)
}

function deactivateStream(element) {
  const panel = element.closest('[data-stream-chart]')
  panel?.classList.remove('is-hovering')
  panel?.querySelectorAll('.is-active').forEach((node) => node.classList.remove('is-active'))
  hideStreamTooltip()
}

function showStreamTooltip(link, point) {
  hideStreamTooltip()
  const currency = link.closest('[data-stream-chart]')?.dataset.currency
  const tooltip = document.createElement('div')
  tooltip.className = 'flow-tooltip'
  tooltip.setAttribute('role', 'tooltip')
  const title = document.createElement('strong')
  title.textContent = link.dataset.label
  const list = document.createElement('dl')
  const rows = [['Ποσό', formatMoney(link.dataset.amount, currency)], ['Μερίδιο', `${link.dataset.share.replace('.', ',')}%`]]
  rows.forEach(([label, value]) => {
    const term = document.createElement('dt')
    term.textContent = label
    const definition = document.createElement('dd')
    definition.textContent = value
    list.append(term, definition)
  })
  tooltip.append(title, list)
  if (link.dataset.detail) {
    const detail = document.createElement('p')
    detail.className = 'stream-detail'
    detail.textContent = `Περιλαμβάνει: ${link.dataset.detail.split('|').join(', ')}`
    tooltip.append(detail)
  }
  document.body.append(tooltip)
  streamTooltipElement = tooltip
  positionStreamTooltip(tooltip, point)
}

function positionStreamTooltip(tooltip, point) {
  const margin = 12
  const { width, height } = tooltip.getBoundingClientRect()
  let left = point.x + 16
  if (left + width > window.innerWidth - margin) left = point.x - width - 16
  left = Math.max(margin, left)
  let top = point.y - height / 2
  top = Math.max(margin, Math.min(top, window.innerHeight - height - margin))
  tooltip.style.left = `${left}px`
  tooltip.style.top = `${top}px`
}

function hideStreamTooltip() {
  streamTooltipElement?.remove()
  streamTooltipElement = undefined
}

/* ---------- greek dates ---------- */
function formatGreekDateInput(value) {
  const digits = value.replace(/\D/g, '').slice(0, 8)
  if (digits.length <= 2) return digits
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`
}

function validateGreekDate(input) {
  const match = input.value.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  if (!match) {
    input.setCustomValidity(input.value ? 'Χρησιμοποιήστε μορφή ηη/μμ/εεεε.' : '')
    return
  }
  const [, day, month, year] = match.map(Number)
  const parsed = new Date(year, month - 1, day)
  const valid = parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day
  input.setCustomValidity(valid ? '' : 'Η ημερομηνία δεν είναι έγκυρη.')
  if (valid) {
    const nativeInput = input.closest('.date-input-wrap')?.querySelector('[data-native-date]')
    if (nativeInput) nativeInput.value = `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`
  }
}
