const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || ''

document.addEventListener('click', async (event) => {
  const link = event.target.closest('[data-modal-url]')
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  event.stopPropagation()
  await openModal(link.dataset.modalUrl)
}, true)

document.addEventListener('submit', async (event) => {
  const form = event.target
  const isTransactionAction = form.matches('[data-transaction-action]')
  const isModalForm = form.closest('#modal-root') !== null
  if (!isTransactionAction && !isModalForm) return

  event.preventDefault()
  event.stopPropagation()
  if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return

  const submitter = event.submitter
  if (submitter) submitter.disabled = true
  try {
    const response = await fetch(form.action, {
      method: (form.method || 'post').toUpperCase(),
      body: new FormData(form),
      headers: { 'HX-Request': 'true', 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
    })
    const redirect = response.headers.get('HX-Redirect')
    if (redirect) {
      window.location.assign(redirect)
      return
    }
    if (response.redirected) {
      window.location.assign(response.url)
      return
    }
    const html = await response.text()
    if (isModalForm) {
      const root = document.querySelector('#modal-root')
      root.innerHTML = html
      updateBalance(root.querySelector('form'))
    } else if (!response.ok) {
      window.alert('Η ενέργεια δεν ολοκληρώθηκε. Δοκιμάστε ξανά.')
    }
  } catch (_error) {
    window.alert('Δεν ήταν δυνατή η επικοινωνία με την εφαρμογή.')
  } finally {
    if (submitter) submitter.disabled = false
  }
}, true)

document.addEventListener('htmx:configRequest', (event) => {
  event.detail.headers['X-CSRFToken'] = csrfToken()
})

document.addEventListener('click', (event) => {
  const drawerToggle = event.target.closest('[data-drawer-toggle]')
  const drawerClose = event.target.closest('[data-drawer-close]')
  if (drawerToggle) document.body.classList.toggle('drawer-open')
  if (drawerClose) document.body.classList.remove('drawer-open')

  const modalClose = event.target.closest('[data-modal-close]')
  if (modalClose) closeModal()

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
    window.location.assign(`${pdfExport.dataset.pdfUrl}?${parameters}`)
  }

  const remove = event.target.closest('[data-remove-line]')
  if (remove) {
    const lines = remove.closest('[data-entry-lines]')
    if (lines.children.length > 2) remove.closest('.entry-line').remove()
    updateBalance(lines.closest('form'))
  }

  const add = event.target.closest('[data-add-line]')
  if (add) {
    const form = add.closest('form')
    form.querySelector('[data-entry-lines]').append(form.querySelector('[data-line-template]').content.cloneNode(true))
    updateBalance(form)
  }
}, true)

document.addEventListener('submit', (event) => {
  const message = event.target.dataset.confirm
  if (message && !window.confirm(message)) event.preventDefault()
})

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
})

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
  state.textContent = balanced ? 'Ισοσκελισμένη' : `Διαφορά ${(debits - credits).toFixed(2)}`
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
    root.querySelector('input:not([type="hidden"]), select, button')?.focus()
  } catch (_error) {
    closeModal()
    window.alert('Δεν ήταν δυνατό το άνοιγμα της φόρμας.')
  }
}

function closeModal() {
  const root = document.querySelector('#modal-root')
  if (root) root.innerHTML = ''
  document.body.classList.remove('modal-open')
}

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
