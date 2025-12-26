import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import { formatCurrency, formatDate } from './utils'
import type {
  TrialBalanceResponse,
  BalanceSheetResponse,
  IncomeStatementResponse,
  GeneralLedgerResponse,
  JournalResponse,
} from '@/types'

const PDF_MARGIN = 20

// Create an iframe with isolated styles for PDF export
// This avoids oklch color issues from TailwindCSS v4
function createReportIframe(
  title: string,
  content: string
): { iframe: HTMLIFrameElement; cleanup: () => void } {
  const iframe = document.createElement('iframe')
  iframe.style.cssText = `
    position: fixed;
    left: -9999px;
    top: 0;
    width: 850px;
    height: 2000px;
    border: none;
    visibility: hidden;
    pointer-events: none;
  `
  document.body.appendChild(iframe)

  const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document
  if (!iframeDoc) {
    throw new Error('Could not access iframe document')
  }

  iframeDoc.open()
  iframeDoc.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }
        body {
          font-family: Arial, Helvetica, sans-serif;
          font-size: 12px;
          color: #000000;
          background-color: #ffffff;
          padding: 40px;
          width: 800px;
        }
        .header {
          margin-bottom: 20px;
          border-bottom: 2px solid #333333;
          padding-bottom: 10px;
        }
        .header h1 {
          margin: 0 0 5px 0;
          font-size: 20px;
          color: #333333;
        }
        .header p {
          margin: 0;
          font-size: 11px;
          color: #666666;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 20px;
          background-color: #ffffff;
        }
        th {
          padding: 8px;
          text-align: left;
          border-bottom: 2px solid #dddddd;
          font-weight: bold;
          background-color: #f3f4f6;
        }
        td {
          padding: 6px 8px;
          border-bottom: 1px solid #eeeeee;
        }
        .text-right {
          text-align: right;
        }
        .footer-row {
          background-color: #f9fafb;
          font-weight: bold;
          border-top: 2px solid #dddddd;
        }
        .footer-row td {
          padding: 8px;
        }
        .section {
          margin-bottom: 20px;
        }
        .section h2 {
          font-size: 14px;
          font-weight: bold;
          margin: 0 0 10px 0;
          color: #333333;
        }
        .section-item {
          display: flex;
          justify-content: space-between;
          padding: 4px 10px;
          border-bottom: 1px solid #eeeeee;
        }
        .section-total {
          display: flex;
          justify-content: space-between;
          padding: 8px 10px;
          font-weight: bold;
          background-color: #f9fafb;
          margin-top: 5px;
        }
        .info-box {
          padding: 10px;
          background-color: #f3f4f6;
          border-radius: 4px;
          margin-bottom: 15px;
        }
        .journal-entry {
          margin-bottom: 20px;
          border: 1px solid #dddddd;
          border-radius: 4px;
          overflow: hidden;
        }
        .journal-header {
          background-color: #f3f4f6;
          padding: 10px;
          border-bottom: 1px solid #dddddd;
        }
        .journal-body {
          padding: 10px;
        }
        .green { color: #16a34a; }
        .red { color: #dc2626; }
        .net-income-box {
          margin-top: 20px;
          padding: 15px;
          background-color: #f9fafb;
          border-top: 2px solid #333333;
        }
        .net-income-row {
          display: flex;
          justify-content: space-between;
          font-size: 16px;
          font-weight: bold;
        }
      </style>
    </head>
    <body>
      <div class="header">
        <h1>${title}</h1>
        <p>Generated: ${new Date().toLocaleString()}</p>
      </div>
      ${content}
    </body>
    </html>
  `)
  iframeDoc.close()

  return {
    iframe,
    cleanup: () => {
      document.body.removeChild(iframe)
    },
  }
}

// Use html2canvas on iframe content for proper Unicode/Greek character support
async function createPDFFromIframe(
  iframe: HTMLIFrameElement,
  filename: string,
  orientation: 'portrait' | 'landscape' = 'portrait'
): Promise<void> {
  // Wait for iframe content to render
  await new Promise((resolve) => setTimeout(resolve, 200))

  const iframeBody = iframe.contentDocument?.body
  if (!iframeBody) {
    throw new Error('Could not access iframe body')
  }

  try {
    const canvas = await html2canvas(iframeBody, {
      scale: 2,
      useCORS: true,
      logging: false,
      backgroundColor: '#ffffff',
    })

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation,
      unit: 'mm',
      format: 'a4',
    })

    const pageWidth = pdf.internal.pageSize.getWidth()
    const pageHeight = pdf.internal.pageSize.getHeight()
    const imgWidth = pageWidth - 2 * PDF_MARGIN
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    let heightLeft = imgHeight
    let position = PDF_MARGIN

    // First page
    pdf.addImage(imgData, 'PNG', PDF_MARGIN, position, imgWidth, imgHeight)
    heightLeft -= pageHeight - 2 * PDF_MARGIN

    // Additional pages if needed
    while (heightLeft > 0) {
      position = heightLeft - imgHeight + PDF_MARGIN
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', PDF_MARGIN, position, imgWidth, imgHeight)
      heightLeft -= pageHeight - 2 * PDF_MARGIN
    }

    // Use blob download for better compatibility
    const blob = pdf.output('blob')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('Error generating PDF:', error)
    throw error
  }
}

function createTableHTML(headers: string[], rows: string[][], options?: { footerRow?: string[] }): string {
  let html = `<table><thead><tr>`
  headers.forEach((h) => {
    html += `<th>${h}</th>`
  })
  html += `</tr></thead><tbody>`

  rows.forEach((row) => {
    html += `<tr>`
    row.forEach((cell, i) => {
      const className = i >= headers.length - 2 ? 'text-right' : ''
      html += `<td class="${className}">${cell}</td>`
    })
    html += `</tr>`
  })

  if (options?.footerRow) {
    html += `<tr class="footer-row">`
    options.footerRow.forEach((cell, i) => {
      const className = i >= headers.length - 2 ? 'text-right' : ''
      html += `<td class="${className}">${cell}</td>`
    })
    html += `</tr>`
  }

  html += `</tbody></table>`
  return html
}

function createSectionHTML(
  title: string,
  items: Array<{ name: string; amount: string }>,
  totalLabel: string,
  totalAmount: string,
  colorClass?: string
): string {
  let html = `<div class="section"><h2>${title}</h2>`

  items.forEach((item) => {
    html += `<div class="section-item"><span>${item.name}</span><span>${item.amount}</span></div>`
  })

  const totalClass = colorClass ? `section-total ${colorClass}` : 'section-total'
  html += `<div class="${totalClass}"><span>${totalLabel}</span><span>${totalAmount}</span></div></div>`

  return html
}

export async function exportTrialBalanceToPDF(data: TrialBalanceResponse): Promise<void> {
  const rows = data.accounts.map((item) => [
    item.account.code,
    item.account.name,
    item.account.account_type,
    parseFloat(item.debit_total) > 0 ? formatCurrency(item.debit_total) : '-',
    parseFloat(item.credit_total) > 0 ? formatCurrency(item.credit_total) : '-',
  ])

  const content = createTableHTML(['Code', 'Account', 'Type', 'Debit', 'Credit'], rows, {
    footerRow: ['', '', 'Total', formatCurrency(data.total_debits), formatCurrency(data.total_credits)],
  })

  const { iframe, cleanup } = createReportIframe(
    `Trial Balance as of ${formatDate(data.as_of_date)}`,
    content
  )

  try {
    await createPDFFromIframe(iframe, `trial-balance-${data.as_of_date}.pdf`)
  } finally {
    cleanup()
  }
}

export async function exportBalanceSheetToPDF(data: BalanceSheetResponse): Promise<void> {
  let content = ''

  // Assets
  content += createSectionHTML(
    'Assets',
    data.assets.map((item) => ({ name: item.account.name, amount: formatCurrency(item.balance) })),
    'Total Assets',
    formatCurrency(data.total_assets)
  )

  // Liabilities
  content += createSectionHTML(
    'Liabilities',
    data.liabilities.map((item) => ({
      name: item.account.name,
      amount: formatCurrency(Math.abs(parseFloat(item.balance))),
    })),
    'Total Liabilities',
    formatCurrency(data.total_liabilities)
  )

  // Equity
  content += createSectionHTML(
    'Equity',
    data.equity.map((item) => ({
      name: item.account.name,
      amount: formatCurrency(Math.abs(parseFloat(item.balance))),
    })),
    'Total Equity',
    formatCurrency(data.total_equity)
  )

  const { iframe, cleanup } = createReportIframe(
    `Balance Sheet as of ${formatDate(data.as_of_date)}`,
    content
  )

  try {
    await createPDFFromIframe(iframe, `balance-sheet-${data.as_of_date}.pdf`)
  } finally {
    cleanup()
  }
}

export async function exportIncomeStatementToPDF(data: IncomeStatementResponse): Promise<void> {
  let content = ''

  // Revenue
  content += createSectionHTML(
    'Revenue',
    data.revenues.map((item) => ({
      name: item.account.name,
      amount: formatCurrency(Math.abs(parseFloat(item.balance))),
    })),
    'Total Revenue',
    formatCurrency(data.total_revenue),
    'green'
  )

  // Expenses
  content += createSectionHTML(
    'Expenses',
    data.expenses.map((item) => ({ name: item.account.name, amount: formatCurrency(item.balance) })),
    'Total Expenses',
    formatCurrency(data.total_expenses),
    'red'
  )

  // Net Income
  const netIncome = parseFloat(data.net_income)
  const netIncomeClass = netIncome >= 0 ? 'green' : 'red'
  content += `<div class="net-income-box"><div class="net-income-row ${netIncomeClass}"><span>Net Income</span><span>${formatCurrency(
    data.net_income
  )}</span></div></div>`

  const { iframe, cleanup } = createReportIframe(
    `Income Statement: ${formatDate(data.start_date)} to ${formatDate(data.end_date)}`,
    content
  )

  try {
    await createPDFFromIframe(iframe, `income-statement-${data.start_date}-to-${data.end_date}.pdf`)
  } finally {
    cleanup()
  }
}

export async function exportGeneralLedgerToPDF(data: GeneralLedgerResponse): Promise<void> {
  let content = `<div class="info-box"><strong>Opening Balance:</strong> ${formatCurrency(
    data.opening_balance
  )}</div>`

  const rows = data.entries.map((entry) => [
    formatDate(entry.date),
    entry.description,
    entry.reference || '-',
    parseFloat(entry.debit) > 0 ? formatCurrency(entry.debit) : '-',
    parseFloat(entry.credit) > 0 ? formatCurrency(entry.credit) : '-',
    formatCurrency(entry.balance),
  ])

  content += createTableHTML(['Date', 'Description', 'Reference', 'Debit', 'Credit', 'Balance'], rows)

  content += `<div class="info-box" style="font-weight: bold;"><strong>Closing Balance:</strong> ${formatCurrency(
    data.closing_balance
  )}</div>`

  const { iframe, cleanup } = createReportIframe(
    `General Ledger: ${data.account.name} (${formatDate(data.start_date)} to ${formatDate(data.end_date)})`,
    content
  )

  try {
    await createPDFFromIframe(
      iframe,
      `general-ledger-${data.account.code}-${data.start_date}-to-${data.end_date}.pdf`
    )
  } finally {
    cleanup()
  }
}

export async function exportJournalToPDF(data: JournalResponse): Promise<void> {
  let content = ''

  data.entries.forEach((entry) => {
    content += `<div class="journal-entry">`
    content += `<div class="journal-header"><strong>${formatDate(
      entry.transaction.transaction_date
    )}</strong> - ${entry.transaction.description}`
    if (entry.transaction.reference) {
      content += ` <span style="color: #666666; margin-left: 10px;">(Ref: ${entry.transaction.reference})</span>`
    }
    content += `</div>`
    content += `<div class="journal-body"><table><thead><tr><th>Account</th><th class="text-right">Debit</th><th class="text-right">Credit</th></tr></thead><tbody>`

    entry.debits.forEach((debit) => {
      content += `<tr><td>${debit.account.name}</td><td class="text-right">${formatCurrency(
        debit.amount
      )}</td><td class="text-right">-</td></tr>`
    })

    entry.credits.forEach((credit) => {
      content += `<tr><td style="padding-left: 20px;">${
        credit.account.name
      }</td><td class="text-right">-</td><td class="text-right">${formatCurrency(credit.amount)}</td></tr>`
    })

    content += `</tbody></table></div></div>`
  })

  const { iframe, cleanup } = createReportIframe(
    `Journal: ${formatDate(data.start_date)} to ${formatDate(data.end_date)}`,
    content
  )

  try {
    await createPDFFromIframe(iframe, `journal-${data.start_date}-to-${data.end_date}.pdf`, 'landscape')
  } finally {
    cleanup()
  }
}
