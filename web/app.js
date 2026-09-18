(function () {
  const data = PROWL_DATA; // chronological, 2006-Q1 .. latest
  const root = document.querySelector('.viz-root');
  const cs = getComputedStyle(root);
  const v = (name) => cs.getPropertyValue(name).trim();

  const SERIES_COLORS = [v('--series-1'), v('--series-2'), v('--series-3'), v('--series-4')];
  const STATUS = {
    WATCH: { color: v('--status-neutral'), label: 'Watch' },
    STALKING: { color: v('--status-warning'), label: 'Stalking' },
    GET_READY: { color: v('--status-serious'), label: 'Get ready' },
    OPPORTUNITY: { color: v('--status-good'), label: 'Opportunity' },
  };

  const tooltip = document.getElementById('tooltip');
  const fmt = (n, d = 1) => (n === null || n === undefined || Number.isNaN(n)) ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const fmtInt = (n) => (n === null || n === undefined) ? '—' : Math.round(n).toLocaleString();

  // ---------- stat row ----------
  function renderStats() {
    const latest = data[data.length - 1];
    const prevYear = data[data.length - 5];
    const el = document.getElementById('statRow');
    const sig = STATUS[latest.prowl_signal] || STATUS.WATCH;
    el.innerHTML = `
      <div class="stat-tile"><div class="label">Latest quarter</div><div class="value">${latest.quarter}</div></div>
      <div class="stat-tile"><div class="label">Price index (All)</div><div class="value">${fmt(latest.price_all)}</div></div>
      <div class="stat-tile"><div class="label">YoY price change</div><div class="value">${fmt(latest.price_all_yoy_pct)}%</div></div>
      <div class="stat-tile"><div class="label">Prowl signal</div><div class="value small"><span class="badge ${latest.prowl_signal ? latest.prowl_signal.toLowerCase() : 'neutral'}"><span class="dot" style="background:${sig.color}"></span>${sig.label}</span></div></div>
    `;
  }

  // ---------- shared SVG chart scaffold ----------
  function buildScales(seriesArrays, width, height, marginL, marginR, marginT, marginB) {
    const n = data.length;
    const allVals = seriesArrays.flat().filter((x) => x !== null && x !== undefined);
    let min = Math.min(...allVals), max = Math.max(...allVals);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.08;
    min -= pad; max += pad;
    const x = (i) => marginL + (i / (n - 1)) * (width - marginL - marginR);
    const y = (val) => (height - marginB) - ((val - min) / (max - min)) * (height - marginT - marginB);
    return { x, y, min, max, n };
  }

  function pathFor(arr, x, y) {
    let d = '';
    let started = false;
    arr.forEach((val, i) => {
      if (val === null || val === undefined) { started = false; return; }
      d += (started ? 'L' : 'M') + x(i).toFixed(2) + ',' + y(val).toFixed(2) + ' ';
      started = true;
    });
    return d.trim();
  }

  function yearTicks() {
    // one tick per Q1 of every 2 years
    const ticks = [];
    data.forEach((d, i) => {
      const [year, q] = d.quarter.split('-Q');
      if (q === '1' && Number(year) % 2 === 0) ticks.push({ i, label: year });
    });
    return ticks;
  }

  function svgEl(tag, attrs) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([k, val]) => el.setAttribute(k, val));
    return el;
  }

  // ---------- line chart with hover crosshair ----------
  function renderLineChart(container, seriesDefs, opts) {
    const width = 960, height = opts.height || 280;
    const marginL = 42, marginR = 10, marginT = 10, marginB = opts.stripData ? 46 : 26;
    const seriesArrays = seriesDefs.map((s) => data.map((d) => d[s.key]));
    const { x, y, min, max, n } = buildScales(seriesArrays, width, height, marginL, marginR, marginT, marginB);

    const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': opts.ariaLabel || '' });

    // gridlines (4 horizontal)
    const gridCount = 4;
    for (let g = 0; g <= gridCount; g++) {
      const val = min + (g / gridCount) * (max - min);
      const gy = y(val);
      svg.appendChild(svgEl('line', { x1: marginL, x2: width - marginR, y1: gy.toFixed(2), y2: gy.toFixed(2), class: 'gridline' }));
      const lbl = svgEl('text', { x: marginL - 8, y: (gy + 3).toFixed(2), 'text-anchor': 'end', class: 'axis-label' });
      lbl.textContent = fmt(val, 0);
      svg.appendChild(lbl);
    }

    // baseline
    svg.appendChild(svgEl('line', { x1: marginL, x2: width - marginR, y1: (height - marginB).toFixed(2), y2: (height - marginB).toFixed(2), class: 'baseline' }));

    // x ticks
    yearTicks().forEach(({ i, label }) => {
      const tx = x(i);
      const lbl = svgEl('text', { x: tx.toFixed(2), y: height - marginB + 16, 'text-anchor': 'middle', class: 'axis-label' });
      lbl.textContent = label;
      svg.appendChild(lbl);
    });

    // series lines
    seriesDefs.forEach((s, si) => {
      const arr = seriesArrays[si];
      svg.appendChild(svgEl('path', { d: pathFor(arr, x, y), fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    });

    // status strip
    if (opts.stripData) {
      const stripY = height - marginB + 24;
      const stripH = 10;
      const bw = (width - marginL - marginR) / n;
      data.forEach((d, i) => {
        const st = STATUS[d.prowl_signal] || STATUS.WATCH;
        svg.appendChild(svgEl('rect', {
          x: (marginL + i * bw).toFixed(2), y: stripY, width: Math.max(bw - 0.5, 0.5), height: stripH,
          fill: st.color, opacity: d.prowl_signal === 'WATCH' || !d.prowl_signal ? 0.35 : 0.95, rx: 1,
        }));
      });
    }

    // hover overlay
    const hoverLine = svgEl('line', { x1: 0, x2: 0, y1: marginT, y2: height - marginB, stroke: v('--text-muted'), 'stroke-width': 1, 'stroke-dasharray': '3,3', opacity: 0 });
    svg.appendChild(hoverLine);
    const dots = seriesDefs.map((s) => {
      const c = svgEl('circle', { r: 3.5, fill: s.color, stroke: v('--surface-1'), 'stroke-width': 1.5, opacity: 0 });
      svg.appendChild(c);
      return c;
    });

    const overlay = svgEl('rect', { x: marginL, y: marginT, width: width - marginL - marginR, height: height - marginT - marginB, fill: 'transparent', style: 'pointer-events: all;' });
    svg.appendChild(overlay);

    function nearestIndex(clientX) {
      const rect = container.querySelector('svg').getBoundingClientRect();
      const relX = ((clientX - rect.left) / rect.width) * width;
      const i = Math.round(((relX - marginL) / (width - marginL - marginR)) * (n - 1));
      return Math.max(0, Math.min(n - 1, i));
    }

    overlay.addEventListener('mousemove', (e) => {
      const i = nearestIndex(e.clientX);
      const px = x(i);
      hoverLine.setAttribute('x1', px); hoverLine.setAttribute('x2', px); hoverLine.setAttribute('opacity', 1);
      let rows = '';
      seriesDefs.forEach((s, si) => {
        const val = seriesArrays[si][i];
        dots[si].setAttribute('cx', px);
        dots[si].setAttribute('cy', val !== null && val !== undefined ? y(val) : -999);
        dots[si].setAttribute('opacity', val !== null && val !== undefined ? 1 : 0);
        rows += `<div class="row"><span><span class="swatch" style="background:${s.color}"></span>${s.label}</span><span>${fmt(val, opts.decimals ?? 1)}${opts.suffix || ''}</span></div>`;
      });
      if (opts.stripData) {
        const sig = STATUS[data[i].prowl_signal] || STATUS.WATCH;
        rows += `<div class="row"><span><span class="swatch" style="background:${sig.color}"></span>Signal</span><span>${sig.label}</span></div>`;
      }
      tooltip.innerHTML = `<div style="font-weight:600;margin-bottom:4px;">${data[i].quarter}</div>${rows}`;
      tooltip.style.left = e.clientX + 'px';
      tooltip.style.top = e.clientY + 'px';
      tooltip.classList.add('visible');
    });
    overlay.addEventListener('mouseleave', () => {
      hoverLine.setAttribute('opacity', 0);
      dots.forEach((d) => d.setAttribute('opacity', 0));
      tooltip.classList.remove('visible');
    });

    container.innerHTML = '';
    container.appendChild(svg);
  }

  // ---------- bar chart ----------
  function renderBarChart(container, key, opts) {
    const width = 960, height = 220;
    const marginL = 46, marginR = 10, marginT = 10, marginB = 26;
    const arr = data.map((d) => d[key]);
    const max = Math.max(...arr.filter((x) => x !== null));
    const n = data.length;
    const y = (val) => (height - marginB) - (val / max) * (height - marginT - marginB);
    const bw = (width - marginL - marginR) / n;

    const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}` });
    const gridCount = 3;
    for (let g = 0; g <= gridCount; g++) {
      const val = (g / gridCount) * max;
      const gy = y(val);
      svg.appendChild(svgEl('line', { x1: marginL, x2: width - marginR, y1: gy.toFixed(2), y2: gy.toFixed(2), class: 'gridline' }));
      const lbl = svgEl('text', { x: marginL - 8, y: (gy + 3).toFixed(2), 'text-anchor': 'end', class: 'axis-label' });
      lbl.textContent = fmtInt(val);
      svg.appendChild(lbl);
    }
    svg.appendChild(svgEl('line', { x1: marginL, x2: width - marginR, y1: (height - marginB).toFixed(2), y2: (height - marginB).toFixed(2), class: 'baseline' }));
    yearTicks().forEach(({ i, label }) => {
      const tx = marginL + i * bw;
      const lbl = svgEl('text', { x: tx.toFixed(2), y: height - marginB + 16, 'text-anchor': 'middle', class: 'axis-label' });
      lbl.textContent = label;
      svg.appendChild(lbl);
    });

    const bars = [];
    data.forEach((d, i) => {
      const val = arr[i] || 0;
      const bx = marginL + i * bw;
      const by = y(val);
      const rect = svgEl('rect', { x: (bx + 0.4).toFixed(2), y: by.toFixed(2), width: Math.max(bw - 0.8, 0.5), height: (height - marginB - by).toFixed(2), fill: v('--series-1'), opacity: 0.85 });
      svg.appendChild(rect);
      bars.push(rect);
    });

    const overlay = svgEl('rect', { x: marginL, y: marginT, width: width - marginL - marginR, height: height - marginT - marginB, fill: 'transparent', style: 'pointer-events: all;' });
    svg.appendChild(overlay);
    overlay.addEventListener('mousemove', (e) => {
      const rect = container.querySelector('svg').getBoundingClientRect();
      const relX = ((e.clientX - rect.left) / rect.width) * width;
      const i = Math.max(0, Math.min(n - 1, Math.floor((relX - marginL) / bw)));
      bars.forEach((b, bi) => b.setAttribute('opacity', bi === i ? 1 : 0.85));
      tooltip.innerHTML = `<div style="font-weight:600;margin-bottom:4px;">${data[i].quarter}</div><div class="row"><span>Units transacted</span><span>${fmtInt(arr[i])}</span></div>`;
      tooltip.style.left = e.clientX + 'px';
      tooltip.style.top = e.clientY + 'px';
      tooltip.classList.add('visible');
    });
    overlay.addEventListener('mouseleave', () => {
      bars.forEach((b) => b.setAttribute('opacity', 0.85));
      tooltip.classList.remove('visible');
    });

    container.innerHTML = '';
    container.appendChild(svg);
  }

  // ---------- legends ----------
  function renderLegend(el, items) {
    el.innerHTML = items.map((it) => `<span class="item"><span class="swatch" style="background:${it.color}"></span>${it.label}</span>`).join('');
  }

  // ---------- data table ----------
  function renderTable() {
    const cols = [
      ['quarter', 'Quarter'], ['price_all', 'Price'], ['price_all_yoy_pct', 'Price YoY%'],
      ['rent_nonlanded', 'Rent (NL)'], ['price_rent_divergence_yoy_pts', 'Divergence'],
      ['txn_total', 'Txn vol'], ['prowl_signal', 'Signal'],
    ];
    let html = '<table class="data-table"><thead><tr>' + cols.map((c) => `<th>${c[1]}</th>`).join('') + '</tr></thead><tbody>';
    for (let i = data.length - 1; i >= 0; i--) {
      const d = data[i];
      html += '<tr>' + cols.map(([k]) => {
        if (k === 'quarter' || k === 'prowl_signal') return `<td>${d[k] || ''}</td>`;
        return `<td>${fmt(d[k])}</td>`;
      }).join('') + '</tr>';
    }
    html += '</tbody></table>';
    document.getElementById('tableWrap').innerHTML = html;
  }

  // ---------- wire it up ----------
  renderStats();

  renderLegend(document.getElementById('legendPrice'), [
    { color: SERIES_COLORS[0], label: 'All Residential' },
    { color: SERIES_COLORS[1], label: 'Core Central Region' },
    { color: SERIES_COLORS[2], label: 'Rest of Central Region' },
    { color: SERIES_COLORS[3], label: 'Outside Central Region' },
  ]);
  renderLegend(document.getElementById('legendSignal'), Object.values(STATUS).map((s) => ({ color: s.color, label: s.label })));
  renderLineChart(document.getElementById('chartPrice'), [
    { key: 'price_all', label: 'All Residential', color: SERIES_COLORS[0] },
    { key: 'price_ccr', label: 'CCR', color: SERIES_COLORS[1] },
    { key: 'price_rcr', label: 'RCR', color: SERIES_COLORS[2] },
    { key: 'price_ocr', label: 'OCR', color: SERIES_COLORS[3] },
  ], { height: 300, stripData: true, ariaLabel: 'Price index by market segment, 2006 to 2026' });

  renderLegend(document.getElementById('legendRent'), [
    { color: SERIES_COLORS[0], label: 'Non-Landed price index' },
    { color: SERIES_COLORS[1], label: 'Non-Landed rent index' },
  ]);
  renderLineChart(document.getElementById('chartRent'), [
    { key: 'price_nonlanded', label: 'Price (Non-Landed)', color: SERIES_COLORS[0] },
    { key: 'rent_nonlanded', label: 'Rent (Non-Landed)', color: SERIES_COLORS[1] },
  ], { height: 260, ariaLabel: 'Non-landed price versus rent index, 2006 to 2026' });

  renderBarChart(document.getElementById('chartLiquidity'), 'txn_total', {});

  renderTable();
})();

