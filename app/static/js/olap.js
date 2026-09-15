/* OLAP report: cube builder controls + SVG chart renderers (bars, stacks, lines, area, donut, heatmap). */
(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg'
  // Fixed categorical order (validated for CVD separation); "Λοιπά" always takes the neutral slot.
  const PALETTE = ['#19b3a0', '#6273c7', '#f59e0b', '#8b5cf6', '#f0705f', '#3b82f6', '#ec4899', '#0f8a7a']
  const OTHER_KEY = '__other__'
  const OTHER_COLOR = '#9aa39c'
  const SURFACE = '#fffdf8'
  const SEQUENTIAL = ['#fbf0dc', '#a85c0e']
  const DIVERGING = ['#c94b3b', '#e6e3dc', '#2563b8']
  const WIDTH = 960
  const HEIGHT = 330
  const PAD = { top: 22, right: 24, bottom: 46, left: 82 }
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
  let tooltipElement

  /* ---------- number formatting ---------- */
  const numberFormat = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const intFormat = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 })

  function symbolOf(currency) {
    return (currency || 'EUR').toUpperCase() === 'EUR' ? '€' : currency
  }

  function formatValue(value, measure, currency) {
    const number = Number(value) || 0
    if (measure.kind === 'money') return `${numberFormat.format(number)} ${symbolOf(currency)}`
    return intFormat.format(number)
  }

  function formatCompact(value, measure, currency) {
    const number = Number(value) || 0
    const abs = Math.abs(number)
    const sign = number < 0 ? '−' : ''
    let text
    if (abs >= 1e6) text = `${(abs / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace('.', ',')}M`
    else if (abs >= 1e3) text = `${(abs / 1e3).toFixed(abs >= 1e4 ? 0 : 1).replace('.', ',')}K`
    else text = intFormat.format(abs)
    return `${sign}${text}${measure.kind === 'money' ? ` ${symbolOf(currency)}` : ''}`
  }

  /* ---------- scales ---------- */
  function niceStep(span, count = 5) {
    const raw = span / count
    const magnitude = 10 ** Math.floor(Math.log10(raw || 1))
    const candidates = [1, 2, 2.5, 5, 10].map((step) => step * magnitude)
    return candidates.find((step) => step >= raw) || candidates[candidates.length - 1]
  }

  function niceCeil(value) {
    if (value <= 0) return 0
    const magnitude = 10 ** Math.floor(Math.log10(value))
    const mantissa = value / magnitude
    const step = [1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10].find((candidate) => candidate >= mantissa)
    return step * magnitude
  }

  /* Ticks step from the positive span; a small negative tail gets its own tight bound instead of a whole step. */
  function linearScale(min, max) {
    const step = niceStep(Math.max(max, 0) - Math.min(min, 0) || 1)
    const hi = max > 0 ? Math.ceil(max / step) * step : 0
    const lo = min >= 0 ? 0 : -min < step ? -niceCeil(-min) : -Math.ceil(-min / step) * step
    const ticks = []
    for (let value = 0; value <= hi + step / 2; value += step) ticks.push(Number(value.toFixed(10)))
    for (let value = -step; value >= lo - step / 2; value -= step) ticks.push(Number(value.toFixed(10)))
    if (lo < 0 && !ticks.includes(lo)) ticks.push(lo)
    const plotTop = PAD.top
    const plotBottom = HEIGHT - PAD.bottom
    const y = (value) => plotBottom - ((value - lo) / (hi - lo || 1)) * (plotBottom - plotTop)
    return { lo, hi, ticks, y }
  }

  /* ---------- svg helpers ---------- */
  function el(name, attributes = {}, children = []) {
    const node = document.createElementNS(SVG_NS, name)
    Object.entries(attributes).forEach(([key, value]) => {
      if (value !== undefined && value !== null) node.setAttribute(key, value)
    })
    children.forEach((child) => node.append(child))
    return node
  }

  function text(content, attributes) {
    const node = el('text', attributes)
    node.textContent = content
    return node
  }

  /* Bar with 4px rounded data-end, square at the baseline. */
  function barPath(x, baseline, end, width, radius = 4) {
    const up = end < baseline
    const r = Math.min(radius, width / 2, Math.abs(baseline - end))
    if (r <= 0) return ''
    if (up) {
      return `M${x} ${baseline} V${end + r} Q${x} ${end} ${x + r} ${end} H${x + width - r} Q${x + width} ${end} ${x + width} ${end + r} V${baseline} Z`
    }
    return `M${x} ${baseline} V${end - r} Q${x} ${end} ${x + r} ${end} H${x + width - r} Q${x + width} ${end} ${x + width} ${end - r} V${baseline} Z`
  }

  function seriesColor(series, index) {
    return series.key === OTHER_KEY ? OTHER_COLOR : PALETTE[index % PALETTE.length]
  }

  function mixHex(a, b, t) {
    const parse = (hex) => [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16))
    const [r1, g1, b1] = parse(a)
    const [r2, g2, b2] = parse(b)
    const channel = (from, to) => Math.round(from + (to - from) * t)
    return `rgb(${channel(r1, r2)} ${channel(g1, g2)} ${channel(b1, b2)})`
  }

  function luminanceOf(rgb) {
    const [r, g, b] = rgb.match(/\d+/g).map(Number).map((v) => v / 255)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }

  /* ---------- chart state ---------- */
  function readChart(panel) {
    const payload = JSON.parse(panel.querySelector('[data-olap-data]').textContent)
    payload.series.forEach((series) => { series.numbers = series.values.map((value) => Number(value) || 0) })
    return payload
  }

  function visibleSeries(panel, chart) {
    const hidden = new Set((panel.dataset.hidden || '').split(' ').filter(Boolean))
    return chart.series.map((series, index) => ({ ...series, index, color: seriesColor(series, index) }))
      .filter((series) => !hidden.has(series.key))
  }

  function axes(svg, scale, measure, currency, options = {}) {
    const left = PAD.left
    const right = WIDTH - PAD.right
    const drawn = []
    scale.ticks.forEach((tick) => {
      const y = scale.y(tick)
      svg.append(el('line', { class: 'olap-grid', x1: left, x2: right, y1: y, y2: y }))
      if (drawn.some((other) => Math.abs(other - y) < 12)) return  // a tight negative bound can crowd the zero label
      drawn.push(y)
      const label = options.percent ? `${tick}%` : formatCompact(tick, measure, currency)
      svg.append(text(label, { class: 'chart-y-label', x: left - 12, y: y + 4 }))
    })
    if (scale.lo < 0 && scale.hi > 0) {
      const zero = scale.y(0)
      svg.append(el('line', { class: 'olap-zero', x1: left, x2: right, y1: zero, y2: zero }))
    }
  }

  function categoryLabels(svg, categories, slot) {
    const maxLabels = Math.floor((WIDTH - PAD.left - PAD.right) / 58)
    const every = Math.max(1, Math.ceil(categories.length / maxLabels))
    categories.forEach((category, index) => {
      if (index % every !== 0 && index !== categories.length - 1) return
      const x = PAD.left + slot * index + slot / 2
      const label = category.label.length > 14 ? `${category.label.slice(0, 13)}…` : category.label
      svg.append(text(label, { class: 'chart-x-label olap-x-label', x, y: HEIGHT - PAD.bottom + 20 }))
    })
  }

  function hitGroup(chart, series, categoryIndex, x, width, extra = {}) {
    const category = chart.categories[categoryIndex]
    const group = el('g', {
      class: 'olap-hit', tabindex: 0, role: 'img',
      'data-category': categoryIndex, 'data-category-key': category.key,
      'aria-label': `${category.label}: ${series.map((item) => `${item.label} ${item.numbers[categoryIndex]}`).join(', ')}`,
      ...extra,
    })
    group.append(el('rect', { class: 'olap-hit-area', x, y: PAD.top - 6, width, height: HEIGHT - PAD.bottom - PAD.top + 6, rx: 8 }))
    return group
  }

  /* ---------- renderers ---------- */
  function renderBars(svg, chart, series, currency, mode) {
    const { categories, measure } = chart
    const slot = (WIDTH - PAD.left - PAD.right) / Math.max(categories.length, 1)
    const stacked = mode !== 'bar'
    const percent = mode === 'stacked100'
    let min = 0
    let max = 0
    const stacks = categories.map((_, index) => {
      const positives = series.filter((item) => item.numbers[index] > 0)
      const negatives = series.filter((item) => item.numbers[index] < 0)
      const sumAbs = series.reduce((total, item) => total + Math.abs(item.numbers[index]), 0)
      const scale = percent ? (sumAbs ? 100 / sumAbs : 0) : 1
      const posTotal = positives.reduce((total, item) => total + item.numbers[index], 0) * scale
      const negTotal = negatives.reduce((total, item) => total + item.numbers[index], 0) * scale
      if (stacked) {
        max = Math.max(max, posTotal)
        min = Math.min(min, negTotal)
      } else {
        series.forEach((item) => {
          max = Math.max(max, item.numbers[index])
          min = Math.min(min, item.numbers[index])
        })
      }
      return { scale }
    })
    const scale = percent ? { lo: min < 0 ? -100 : 0, hi: max > 0 ? 100 : 0, ticks: [], y: null } : linearScale(min, max)
    if (percent) {
      const plotTop = PAD.top
      const plotBottom = HEIGHT - PAD.bottom
      for (let value = scale.lo; value <= scale.hi; value += 25) scale.ticks.push(value)
      scale.y = (value) => plotBottom - ((value - scale.lo) / (scale.hi - scale.lo || 1)) * (plotBottom - plotTop)
    }
    axes(svg, scale, measure, currency, { percent })
    categoryLabels(svg, categories, slot)
    const zero = scale.y(0)
    const marks = el('g', { class: 'olap-marks' })
    const maxima = series.map((item) => item.numbers.reduce((best, value, index) => (Math.abs(value) > Math.abs(item.numbers[best]) ? index : best), 0))

    categories.forEach((_, index) => {
      const group = hitGroup(chart, series, index, PAD.left + slot * index + 1, slot - 2)
      if (stacked) {
        const width = Math.min(24, slot * 0.6)
        const x = PAD.left + slot * index + (slot - width) / 2
        let positiveTop = 0
        let negativeBottom = 0
        series.forEach((item) => {
          const value = item.numbers[index] * stacks[index].scale
          if (!value) return
          const from = value > 0 ? positiveTop : negativeBottom
          const to = from + value
          if (value > 0) positiveTop = to
          else negativeBottom = to
          const y0 = scale.y(from)
          const y1 = scale.y(to)
          // 2px surface gap between stacked segments, taken from the segment's baseline side.
          const gap = Math.min(2, Math.abs(y1 - y0))
          const base = value > 0 ? y0 - gap : y0 + gap
          group.append(el('path', { class: 'olap-bar', d: barPath(x, base, y1, width, 3), fill: item.color, 'data-series': item.key }))
        })
      } else {
        const gap = 2
        const inner = Math.min(24 * series.length + gap * (series.length - 1), slot * 0.78)
        const width = Math.max((inner - gap * (series.length - 1)) / Math.max(series.length, 1), 2)
        const start = PAD.left + slot * index + (slot - inner) / 2
        series.forEach((item, position) => {
          const value = item.numbers[index]
          if (!value) return
          const x = start + position * (width + gap)
          const end = scale.y(value)
          group.append(el('path', { class: 'olap-bar', d: barPath(x, zero, end, width), fill: item.color, 'data-series': item.key }))
          if (series.length <= 4 && maxima[position] === index && !percent) {
            const label = text(formatCompact(value, measure, currency), {
              class: 'olap-direct-label', x: x + width / 2, y: value > 0 ? end - 6 : end + 13, 'text-anchor': 'middle',
            })
            group.append(label)
          }
        })
      }
      marks.append(group)
    })
    svg.append(marks)
  }

  function renderLines(svg, chart, series, currency, area) {
    const { categories, measure } = chart
    const slot = (WIDTH - PAD.left - PAD.right) / Math.max(categories.length, 1)
    const values = series.flatMap((item) => item.numbers)
    const scale = linearScale(Math.min(0, ...values), Math.max(0, ...values))
    axes(svg, scale, measure, currency)
    categoryLabels(svg, categories, slot)
    const xOf = (index) => PAD.left + slot * index + slot / 2
    const zero = scale.y(0)
    const marks = el('g', { class: 'olap-marks' })
    series.forEach((item) => {
      const points = item.numbers.map((value, index) => [xOf(index), scale.y(value)])
      const path = points.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
      if (area && points.length) {
        const [firstX] = points[0]
        const [lastX] = points[points.length - 1]
        marks.append(el('path', { class: 'olap-area', d: `${path} L${lastX} ${zero} L${firstX} ${zero} Z`, fill: item.color, 'data-series': item.key }))
      }
      marks.append(el('path', { class: 'olap-line', d: path, stroke: item.color, pathLength: 1, 'data-series': item.key }))
      points.forEach(([x, y]) => {
        marks.append(el('circle', { class: 'olap-marker', cx: x, cy: y, r: 4, fill: item.color, stroke: SURFACE, 'stroke-width': 2, 'data-series': item.key }))
      })
      if (series.length <= 4 && points.length) {
        const [x, y] = points[points.length - 1]
        marks.append(text(formatCompact(item.numbers[item.numbers.length - 1], measure, currency), {
          class: 'olap-direct-label', x: Math.min(x + 8, WIDTH - 4), y: y + 4, 'text-anchor': x + 8 > WIDTH - 60 ? 'end' : 'start',
        }))
      }
    })
    svg.append(marks)
    const hits = el('g', { class: 'olap-hits' })
    categories.forEach((_, index) => hits.append(hitGroup(chart, series, index, PAD.left + slot * index, slot)))
    svg.append(hits)
  }

  function renderDonut(svg, chart, series, currency, panel) {
    const { categories, measure } = chart
    const totals = categories.map((category, index) => ({
      key: category.key, label: category.label,
      value: series.reduce((total, item) => total + Math.abs(item.numbers[index]), 0),
    })).filter((item) => item.value > 0)
    totals.sort((a, b) => b.value - a.value)
    let slices = totals
    if (totals.length > 6) {
      const rest = totals.slice(5)
      slices = [...totals.slice(0, 5), { key: OTHER_KEY, label: 'Λοιπά', value: rest.reduce((total, item) => total + item.value, 0) }]
    }
    // A folded "Λοιπά" row plus the donut's own tail must not become two grey slices.
    const others = slices.filter((item) => item.key === OTHER_KEY)
    if (others.length > 1) {
      slices = slices.filter((item) => item.key !== OTHER_KEY)
      slices.push({ key: OTHER_KEY, label: 'Λοιπά', value: others.reduce((total, item) => total + item.value, 0) })
    }
    const sum = slices.reduce((total, item) => total + item.value, 0)
    const cx = WIDTH / 2
    const cy = HEIGHT / 2
    const outer = 118
    const inner = 78
    let angle = -Math.PI / 2
    const group = el('g', { class: 'olap-marks' })
    slices.forEach((slice, index) => {
      const sweep = (slice.value / sum) * Math.PI * 2
      const end = angle + sweep
      const large = sweep > Math.PI ? 1 : 0
      const point = (radius, theta) => `${(cx + radius * Math.cos(theta)).toFixed(2)} ${(cy + radius * Math.sin(theta)).toFixed(2)}`
      const d = `M${point(outer, angle)} A${outer} ${outer} 0 ${large} 1 ${point(outer, end)} L${point(inner, end)} A${inner} ${inner} 0 ${large} 0 ${point(inner, angle)} Z`
      const color = slice.key === OTHER_KEY ? OTHER_COLOR : PALETTE[index % PALETTE.length]
      const share = Math.round((slice.value / sum) * 1000) / 10
      const hit = el('g', {
        class: 'olap-hit olap-slice', tabindex: 0, role: 'img', 'data-category-key': slice.key,
        'data-label': slice.label, 'data-value': slice.value, 'data-share': share,
        'aria-label': `${slice.label}: ${formatValue(slice.value, measure, currency)} (${share}%)`,
      })
      hit.append(el('path', { class: 'olap-donut-slice', d, fill: color, stroke: SURFACE, 'stroke-width': 2 }))
      if (sweep > 0.35) {
        const mid = angle + sweep / 2
        const labelRadius = outer + 22
        const x = cx + labelRadius * Math.cos(mid)
        const y = cy + labelRadius * Math.sin(mid)
        hit.append(text(`${share}%`, { class: 'olap-direct-label', x, y: y + 4, 'text-anchor': Math.cos(mid) < -0.1 ? 'end' : Math.cos(mid) > 0.1 ? 'start' : 'middle' }))
      }
      group.append(hit)
      angle = end
    })
    svg.append(group)
    svg.append(text(formatCompact(sum, measure, currency), { class: 'olap-hero', x: cx, y: cy + 2, 'text-anchor': 'middle' }))
    svg.append(text(measure.label, { class: 'olap-hero-label', x: cx, y: cy + 22, 'text-anchor': 'middle' }))
    renderLegend(panel, slices.map((slice, index) => ({ key: slice.key, label: slice.label, color: slice.key === OTHER_KEY ? OTHER_COLOR : PALETTE[index % PALETTE.length] })), false)
  }

  function renderHeatmap(svg, chart, series, currency, panel) {
    const { categories, measure } = chart
    const left = 170
    const top = 16
    const width = (WIDTH - left - PAD.right) / Math.max(categories.length, 1)
    const height = Math.min(34, Math.max(18, 300 / Math.max(series.length, 1)))
    const values = series.flatMap((item) => item.numbers)
    const hasNegative = values.some((value) => value < 0)
    const diverging = hasNegative && measure.signed
    const max = Math.max(...values.map(Math.abs), 0) || 1
    const colorOf = (value) => {
      if (diverging) {
        const t = value / max
        return t < 0 ? mixHex(DIVERGING[1], DIVERGING[0], -t) : mixHex(DIVERGING[1], DIVERGING[2], t)
      }
      return mixHex(SEQUENTIAL[0], SEQUENTIAL[1], Math.abs(value) / max)
    }
    const group = el('g', { class: 'olap-marks' })
    series.forEach((item, row) => {
      const y = top + row * height
      const label = item.label.length > 24 ? `${item.label.slice(0, 23)}…` : item.label
      svg.append(text(label, { class: 'olap-heat-row-label', x: left - 10, y: y + height / 2 + 4, 'text-anchor': 'end' }))
      item.numbers.forEach((value, column) => {
        const x = left + column * width
        const fill = colorOf(value)
        const hit = el('g', {
          class: 'olap-hit olap-cell-hit', tabindex: 0, role: 'img',
          'data-category-key': categories[column].key, 'data-series': item.key, 'data-label': `${item.label} · ${categories[column].label}`, 'data-value': value,
          'aria-label': `${item.label}, ${categories[column].label}: ${formatValue(value, measure, currency)}`,
        })
        hit.append(el('rect', { class: 'olap-heat-cell', x: x + 1, y: y + 1, width: Math.max(width - 2, 1), height: Math.max(height - 2, 1), rx: 4, fill }))
        if (width >= 62 && height >= 20 && value) {
          hit.append(text(formatCompact(value, measure, currency), {
            class: 'olap-heat-value', x: x + width / 2, y: y + height / 2 + 4, 'text-anchor': 'middle',
            fill: luminanceOf(fill) > 0.55 ? '#17211d' : '#fff',
          }))
        }
        group.append(hit)
      })
    })
    svg.append(group)
    const gridBottom = top + series.length * height
    const maxLabels = Math.floor((WIDTH - left - PAD.right) / 58)
    const every = Math.max(1, Math.ceil(categories.length / maxLabels))
    categories.forEach((category, column) => {
      if (column % every !== 0 && column !== categories.length - 1) return
      const label = category.label.length > 14 ? `${category.label.slice(0, 13)}…` : category.label
      svg.append(text(label, { class: 'chart-x-label olap-x-label', x: left + column * width + width / 2, y: gridBottom + 18 }))
    })
    // Scale legend under the grid: sequential or diverging, always with end labels.
    const legendY = gridBottom + 46
    const legendWidth = 180
    const legendX = left
    const gradientId = `olap-heat-gradient-${Math.random().toString(36).slice(2, 8)}`
    const stops = diverging
      ? [[0, DIVERGING[0]], [0.5, DIVERGING[1]], [1, DIVERGING[2]]]
      : [[0, SEQUENTIAL[0]], [1, SEQUENTIAL[1]]]
    svg.append(el('defs', {}, [el('linearGradient', { id: gradientId }, stops.map(([offset, color]) => el('stop', { offset, 'stop-color': color })))]))
    svg.append(el('rect', { x: legendX, y: legendY - 5, width: legendWidth, height: 8, rx: 4, fill: `url(#${gradientId})` }))
    svg.append(text(formatCompact(diverging ? -max : 0, measure, currency), { class: 'chart-y-label', x: legendX - 8, y: legendY + 3 }))
    svg.append(text(formatCompact(max, measure, currency), { class: 'chart-y-label olap-legend-end', x: legendX + legendWidth + 8, y: legendY + 3 }))
    svg.setAttribute('viewBox', `0 0 ${WIDTH} ${legendY + 16}`)
    panel.querySelector('[data-olap-legend]').hidden = true
  }

  /* ---------- legend ---------- */
  function renderLegend(panel, items, toggleable) {
    const legend = panel.querySelector('[data-olap-legend]')
    legend.replaceChildren()
    legend.hidden = items.length < 2
    const hidden = new Set((panel.dataset.hidden || '').split(' ').filter(Boolean))
    items.forEach((item) => {
      const button = document.createElement(toggleable ? 'button' : 'span')
      button.className = 'flow-legend-item olap-legend-item'
      if (toggleable) {
        button.type = 'button'
        button.dataset.olapToggle = item.key
        button.setAttribute('aria-pressed', String(!hidden.has(item.key)))
      }
      const dot = document.createElement('i')
      dot.className = 'flow-legend-dot'
      dot.style.background = item.color
      button.append(dot, item.label)
      legend.append(button)
    })
  }

  /* ---------- orchestration ---------- */
  function render(panel) {
    const chart = panel.chartData || (panel.chartData = readChart(panel))
    const stage = panel.querySelector('[data-olap-stage]')
    const currency = panel.dataset.currency
    const series = visibleSeries(panel, chart)
    const svg = el('svg', { class: `olap-chart olap-chart-${chart.type}`, viewBox: `0 0 ${WIDTH} ${HEIGHT}`, role: 'img', 'aria-label': `${chart.measure.label} ανά ${chart.axis_label}` })
    if (reducedMotion()) svg.classList.add('is-static')
    panel.dataset.chartType = chart.type
    if (chart.type !== 'donut' && chart.type !== 'heatmap') {
      renderLegend(panel, chart.series.map((item, index) => ({ key: item.key, label: item.label, color: seriesColor(item, index) })), true)
    }
    if (!series.length) {
      stage.replaceChildren(Object.assign(document.createElement('p'), { className: 'flow-empty', textContent: 'Όλες οι σειρές είναι κρυμμένες.' }))
      return
    }
    switch (chart.type) {
      case 'line': renderLines(svg, chart, series, currency, false); break
      case 'area': renderLines(svg, chart, series, currency, true); break
      case 'donut': renderDonut(svg, chart, series, currency, panel); break
      case 'heatmap': renderHeatmap(svg, chart, series, currency, panel); break
      default: renderBars(svg, chart, series, currency, chart.type)
    }
    stage.replaceChildren(svg)
  }

  function enhance(root) {
    if (!root?.querySelectorAll) return
    root.querySelectorAll('[data-olap-chart]:not([data-enhanced])').forEach((panel) => {
      panel.dataset.enhanced = 'true'
      render(panel)
    })
    const controls = root.querySelector?.('[data-report-controls]') || (root.matches?.('[data-report-controls]') ? root : null)
    if (controls) syncBuilder(controls)
  }

  /* Builder visibility follows the report type; row selects never repeat a dimension. */
  function syncBuilder(form) {
    const type = form.querySelector('[data-report-type]')?.value
    const builder = form.querySelector('[data-olap]')
    if (!builder) return
    builder.hidden = type !== 'olap'
    if (type === 'olap') {
      form.querySelectorAll('[data-period]').forEach((field) => { field.hidden = false })
      const asOf = form.querySelector('[data-as-of]')
      if (asOf) asOf.hidden = true
    }
    const rows = [...form.querySelectorAll('[data-olap-row]')]
    const column = form.querySelector('[data-olap-col]')
    const chosen = new Set([...rows.map((select) => select.value), column?.value].filter(Boolean))
    rows.concat(column ? [column] : []).forEach((select) => {
      select.querySelectorAll('option').forEach((option) => {
        option.disabled = Boolean(option.value) && option.value !== select.value && chosen.has(option.value)
      })
    })
    const measures = form.querySelectorAll('[name="measure"]')
    const checked = [...measures].filter((input) => input.checked)
    if (checked.length === 1) checked[0].disabled = true
    else measures.forEach((input) => { input.disabled = false })
  }

  document.addEventListener('change', (event) => {
    const form = event.target.closest('[data-report-controls]')
    if (!form) return
    if (event.target.matches('[data-report-type]') || event.target.closest('[data-olap]')) syncBuilder(form)
  })

  /* Presets fill the builder and run it; unspecified fields keep their current values. */
  function applyPreset(form, preset) {
    const rows = [...form.querySelectorAll('[data-olap-row]')]
    if (preset.row_dim) rows.forEach((select, index) => { select.value = preset.row_dim[index] || '' })
    if (preset.col_dim !== undefined) form.querySelector('[data-olap-col]').value = preset.col_dim
    if (preset.measure) form.querySelectorAll('[name="measure"]').forEach((input) => {
      input.disabled = false
      input.checked = preset.measure.includes(input.value)
    })
    if (preset.account_type) form.querySelectorAll('[name="account_type"]').forEach((input) => {
      input.checked = preset.account_type.includes(input.value)
    })
    if (preset.chart_type) {
      const radio = form.querySelector(`[name="chart_type"][value="${preset.chart_type}"]`)
      if (radio) radio.checked = true
    }
    if (preset.sort) form.querySelector('[name="sort"]').value = preset.sort
    if (preset.limit !== undefined) form.querySelector('[name="limit"]').value = preset.limit
    syncBuilder(form)
    form.requestSubmit()
  }

  document.addEventListener('click', (event) => {
    const preset = event.target.closest('[data-olap-preset]')
    if (preset) {
      applyPreset(preset.closest('form'), JSON.parse(preset.dataset.olapPreset))
      return
    }
    const toggle = event.target.closest('[data-olap-toggle]')
    if (toggle) {
      const panel = toggle.closest('[data-olap-chart]')
      const hidden = new Set((panel.dataset.hidden || '').split(' ').filter(Boolean))
      const key = toggle.dataset.olapToggle
      if (hidden.has(key)) hidden.delete(key)
      else hidden.add(key)
      panel.dataset.hidden = [...hidden].join(' ')
      hideTooltip()
      render(panel)
      return
    }
    const csv = event.target.closest('[data-olap-csv]')
    if (csv) {
      event.preventDefault()
      const form = csv.closest('form')
      const parameters = new URLSearchParams(new FormData(form))
      window.location.assign(`${csv.dataset.csvUrl}?${parameters}`)
    }
  })

  /* ---------- tooltip + table linking ---------- */
  function showTooltip(hit) {
    hideTooltip()
    const panel = hit.closest('[data-olap-chart]')
    const chart = panel.chartData
    const currency = panel.dataset.currency
    const tooltip = document.createElement('div')
    tooltip.className = 'flow-tooltip olap-tooltip'
    tooltip.setAttribute('role', 'tooltip')
    const title = document.createElement('strong')
    const list = document.createElement('dl')
    if (hit.dataset.value !== undefined) {
      title.textContent = hit.dataset.label
      const term = document.createElement('dt')
      term.textContent = chart.measure.label
      const value = document.createElement('dd')
      value.textContent = formatValue(hit.dataset.value, chart.measure, currency)
      list.append(term, value)
      if (hit.dataset.share) {
        const shareTerm = document.createElement('dt')
        shareTerm.textContent = 'Μερίδιο'
        const shareValue = document.createElement('dd')
        shareValue.textContent = `${hit.dataset.share}%`
        list.append(shareTerm, shareValue)
      }
    } else {
      const index = Number(hit.dataset.category)
      title.textContent = chart.categories[index].label
      const series = visibleSeries(panel, chart)
      let total = 0
      series.forEach((item) => {
        const term = document.createElement('dt')
        const dot = document.createElement('i')
        dot.className = 'flow-legend-dot'
        dot.style.background = item.color
        term.append(dot, item.label)
        const value = document.createElement('dd')
        const number = item.numbers[index]
        total += number
        value.textContent = formatValue(number, chart.measure, currency)
        if (number < 0) value.classList.add('negative')
        list.append(term, value)
      })
      if (series.length > 1) {
        const term = document.createElement('dt')
        term.className = 'is-net'
        term.textContent = 'Σύνολο'
        const value = document.createElement('dd')
        value.className = 'is-net'
        value.textContent = formatValue(total, chart.measure, currency)
        list.append(term, value)
      }
    }
    tooltip.append(title, list)
    document.body.append(tooltip)
    tooltipElement = tooltip
    const box = hit.getBoundingClientRect()
    const { width, height } = tooltip.getBoundingClientRect()
    const margin = 12
    let left = box.left + box.width / 2 - width / 2
    left = Math.max(margin, Math.min(left, window.innerWidth - width - margin))
    let top = box.top - height - margin
    if (top < margin) top = Math.min(box.bottom + margin, window.innerHeight - height - margin)
    tooltip.style.left = `${left}px`
    tooltip.style.top = `${top}px`
    highlightRow(panel, hit.dataset.categoryKey, true)
  }

  function hideTooltip() {
    tooltipElement?.remove()
    tooltipElement = undefined
    document.querySelectorAll('.olap-table tr.is-linked').forEach((row) => row.classList.remove('is-linked'))
  }

  function highlightRow(panel, key, on) {
    const table = panel.closest('.olap-report')?.querySelector('.olap-table')
    if (!table || !key) return
    table.querySelectorAll(`tr[data-olap-row="${CSS.escape(key)}"]`).forEach((row) => row.classList.toggle('is-linked', on))
  }

  document.addEventListener('mouseover', (event) => {
    const hit = event.target.closest?.('.olap-hit')
    if (!hit || hit.contains(event.relatedTarget)) return
    showTooltip(hit)
  })
  document.addEventListener('mouseout', (event) => {
    const hit = event.target.closest?.('.olap-hit')
    if (!hit || hit.contains(event.relatedTarget)) return
    hideTooltip()
  })
  document.addEventListener('focusin', (event) => {
    const hit = event.target.closest?.('.olap-hit')
    if (hit) showTooltip(hit)
  })
  document.addEventListener('focusout', (event) => {
    if (event.target.closest?.('.olap-hit')) hideTooltip()
  })
  window.addEventListener('scroll', hideTooltip, true)
  window.addEventListener('resize', hideTooltip)

  document.addEventListener('htmx:load', (event) => enhance(event.detail.elt))
  document.addEventListener('DOMContentLoaded', () => enhance(document))
  if (document.readyState !== 'loading') enhance(document)
})()
