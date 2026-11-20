const byId = (id) => document.getElementById(id)
const controls = ['segment', 'start', 'end'].map(byId)
const [segment, start, end] = controls
const download = byId('download')
const chart = byId('chart')
const reading = byId('reading')
const number = new Intl.NumberFormat('en-SG', { maximumFractionDigits: 2 })
const columns = [
  'period', 'n', 'medianSGD', 'raw', 'mix', 'hedonic',
  'basketCoverage', 'matchedStrata', 'modelN'
]
const lines = [
  { key: 'raw', title: 'Raw median', color: '#a54832', dash: [] },
  { key: 'mix', title: 'Fixed reference weights', color: '#156b61', dash: [8, 5] },
  { key: 'hedonic', title: 'Hedonic model', color: '#294c79', dash: [2, 5] }
]
let lab
let shown = []

function cells(container, records, render) {
  container.replaceChildren(...records.map(render))
}

function chartPlot() {
  const box = chart.getBoundingClientRect()
  if (!box.width || !shown.length) return
  const dpr = window.devicePixelRatio || 1
  chart.width = Math.round(box.width * dpr)
  chart.height = Math.round(box.height * dpr)
  const ctx = chart.getContext('2d')
  ctx.scale(dpr, dpr)
  const bounds = { x: 41, top: 20, y: box.height - 32, end: box.width - 12 }
  const numbers = shown.flatMap((p) => lines.map(({ key }) => p[key]).filter(Number.isFinite))
  const minimum = Math.floor((Math.min(100, ...numbers) - 4) / 10) * 10
  const maximum = Math.ceil((Math.max(100, ...numbers) + 4) / 10) * 10
  const y = (v) => bounds.y - (v - minimum) / (maximum - minimum) * (bounds.y - bounds.top)
  const x = (i) => bounds.x + (shown.length === 1 ? .5 : i / (shown.length - 1)) * (bounds.end - bounds.x)
  ctx.font = '12px Segoe UI, Arial, sans-serif'
  ctx.fillStyle = '#485f65'
  ctx.textAlign = 'right'
  const tick = Math.ceil((maximum - minimum) / 50) * 10
  for (let n = minimum; n <= maximum; n += tick) {
    ctx.strokeStyle = '#d6e1db'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(bounds.x, y(n))
    ctx.lineTo(bounds.end, y(n))
    ctx.stroke()
    ctx.fillText(n, bounds.x - 6, y(n) + 4)
  }
  const ticks = Math.min(shown.length - 1, Math.max(1, Math.floor((bounds.end - bounds.x) / 92)))
  ctx.textAlign = 'center'
  for (let i = 0; i <= ticks; i++) {
    const index = ticks ? Math.round(i * (shown.length - 1) / ticks) : 0
    const center = Math.max(36, Math.min(x(index), box.width - 36))
    ctx.fillText(shown[index].period, center, bounds.y + 23)
  }
  for (const { key, color, dash } of lines) {
    ctx.strokeStyle = color
    ctx.fillStyle = color
    ctx.setLineDash(dash)
    ctx.lineWidth = 3
    ctx.beginPath()
    let active = false
    for (let i = 0; i < shown.length; i++) {
      const value = shown[i][key]
      if (value == null) { active = false; continue }
      if (active) ctx.lineTo(x(i), y(value))
      else ctx.moveTo(x(i), y(value))
      active = true
    }
    ctx.stroke()
    if (shown.length === 1 && shown[0][key] != null) {
      ctx.beginPath()
      ctx.arc(x(0), y(shown[0][key]), 4, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

function render() {
  const series = lab.series[Number(segment.value)]
  shown = series.points.slice(Number(start.value), Number(end.value) + 1)
  const first = shown[0]
  const last = shown.at(-1)
  if (!first || !last) return
  reading.textContent = `${series.name}, ${first.period} to ${last.period}. ${number.format(last.n)} transactions in ${last.period}. Index base is 2017 Q1.`
  cells(byId('metrics'), lines, ({ key, title }) => {
    const panel = document.createElement('div')
    const value = document.createElement('strong')
    value.textContent = last[key] == null ? 'Unavailable' : number.format(last[key])
    panel.append(title, value)
    return panel
  })
  cells(byId('quarters'), shown, (point) => {
    const tr = document.createElement('tr')
    for (const key of ['period', 'n', 'medianSGD', 'raw', 'mix', 'hedonic', 'basketCoverage', 'modelN']) {
      const cell = document.createElement(key === 'period' ? 'th' : 'td')
      if (key === 'period') cell.scope = 'row'
      const value = point[key]
      cell.textContent = value == null ? '—' : key === 'basketCoverage'
        ? `${number.format(100 * value)}%` : typeof value === 'number' ? number.format(value) : value
      tr.append(cell)
    }
    return tr
  })
  chartPlot()
}

download.addEventListener('click', () => {
  const csv = [columns.join(','), ...shown.map((p) => columns.map((key) => p[key] ?? '').join(','))]
  const blob = new Blob([csv.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'hdb-index-comparison.csv'
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
})
start.addEventListener('change', () => {
  if (Number(start.value) > Number(end.value)) end.value = start.value
  render()
})
end.addEventListener('change', () => {
  if (Number(end.value) < Number(start.value)) start.value = end.value
  render()
})
segment.addEventListener('change', render)
new ResizeObserver(chartPlot).observe(chart)

try {
  const response = await fetch('./data.json')
  if (!response.ok) throw new Error('Snapshot unavailable')
  lab = await response.json()
  const points = lab.series[0].points
  cells(segment, lab.series, ({ name }) => new Option(name))
  for (const [index, option] of [...segment.options].entries()) option.value = index
  for (const control of [start, end]) cells(control, points, (p) => new Option(p.period))
  for (const control of [start, end]) {
    for (const [index, option] of [...control.options].entries()) option.value = index
  }
  start.value = Math.max(0, points.length - 17)
  end.value = points.length - 1
  for (const control of [...controls, download]) control.disabled = false
  byId('release').textContent = `${number.format(lab.sourceRowsIncluded)} transactions · 2017 Q1–${lab.through} · Version ${lab.version}`
  byId('hash').textContent = `Source CSV SHA-256: ${lab.sourceSHA256}`
  render()
} catch (error) {
  reading.textContent = 'The data snapshot could not be loaded. The methodology and original source remain available below.'
  console.error(error)
}
