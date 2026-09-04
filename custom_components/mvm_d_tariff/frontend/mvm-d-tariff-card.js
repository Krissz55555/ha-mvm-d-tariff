class MvmDTariffForecastCard extends HTMLElement {
  setConfig(config) {
    this.config = {
      title: "D tarifa – Mai ár-előrejelzés",
      ...config,
    };
    if (!this.config.entity) {
      throw new Error("Válassz egy D tarifa Mai előrejelzett ár entitást.");
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  getGridOptions() {
    return {
      rows: 5,
      columns: 12,
      min_rows: 4,
      min_columns: 6,
    };
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass?.states || {}).find((entityId) => {
      const state = hass.states[entityId];
      return entityId.startsWith("sensor.") && Array.isArray(state?.attributes?.forecast);
    });
    return {
      entity: entity || "sensor.d_tarifa_mai_elorejelzett_ar",
      title: "D tarifa – Mai ár-előrejelzés",
    };
  }

  _render() {
    if (!this.config || !this._hass) return;

    const stateObj = this._hass.states[this.config.entity];
    if (!stateObj) {
      this.innerHTML = this._cardShell(`
        <div class="empty">Az entitás nem található: <b>${this._escape(this.config.entity)}</b></div>
      `);
      return;
    }

    const forecast = Array.isArray(stateObj.attributes.forecast)
      ? stateObj.attributes.forecast
      : [];

    if (!forecast.length) {
      this.innerHTML = this._cardShell(`
        <div class="empty">A teljes napi DAM előrejelzés még nem érhető el.</div>
      `);
      return;
    }

    const points = forecast
      .map((item) => ({
        time: new Date(item.start),
        price: Number(item.price_huf_kwh),
      }))
      .filter((item) => Number.isFinite(item.time.getTime()) && Number.isFinite(item.price));

    if (!points.length) {
      this.innerHTML = this._cardShell(`<div class="empty">Nincs megjeleníthető forecast adat.</div>`);
      return;
    }

    const prices = points.map((p) => p.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const avg = prices.reduce((sum, value) => sum + value, 0) / prices.length;
    const current = Number(stateObj.state);

    const width = 1000;
    const height = 360;
    const left = 58;
    const right = 18;
    const top = 20;
    const bottom = 46;
    const plotW = width - left - right;
    const plotH = height - top - bottom;

    const rangePad = Math.max((max - min) * 0.12, 5);
    const yMin = min - rangePad;
    const yMax = max + rangePad;

    const dayStart = new Date(points[0].time);
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(dayStart);
    dayEnd.setDate(dayEnd.getDate() + 1);
    const dayMs = dayEnd.getTime() - dayStart.getTime();

    const x = (date) => left + ((date.getTime() - dayStart.getTime()) / dayMs) * plotW;
    const y = (price) => top + ((yMax - price) / (yMax - yMin)) * plotH;

    const path = points
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.time).toFixed(1)},${y(p.price).toFixed(1)}`)
      .join(" ");

    const yTicks = 5;
    let grid = "";
    for (let i = 0; i <= yTicks; i += 1) {
      const value = yMin + ((yMax - yMin) * i) / yTicks;
      const yy = y(value);
      grid += `<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" class="grid" />`;
      grid += `<text x="${left-10}" y="${yy+4}" class="ylabel">${value.toFixed(0)}</text>`;
    }

    let xLabels = "";
    for (let hour = 0; hour <= 24; hour += 3) {
      const date = new Date(dayStart.getTime() + (dayMs * hour) / 24);
      const xx = x(date);
      xLabels += `<line x1="${xx}" y1="${top}" x2="${xx}" y2="${height-bottom}" class="vgrid" />`;
      xLabels += `<text x="${xx}" y="${height-bottom+28}" class="xlabel">${String(hour).padStart(2, "0")}:00</text>`;
    }

    const now = new Date();
    const nowInside = now >= dayStart && now < dayEnd;
    const nowLine = nowInside
      ? `<line x1="${x(now)}" y1="${top}" x2="${x(now)}" y2="${height-bottom}" class="now" />`
      : "";

    const avgLine = `<line x1="${left}" y1="${y(avg)}" x2="${width-right}" y2="${y(avg)}" class="avg" />`;

    const forecastDate = stateObj.attributes.forecast_date || "";
    const fallback = stateObj.attributes.fallback === true;
    const statusText = fallback ? "cache/fallback adat" : "day-ahead (DAM) adat";

    this.innerHTML = this._cardShell(`
      <div class="summary">
        <div><span>Aktuális</span><strong>${Number.isFinite(current) ? current.toFixed(2) : "–"}<small>Ft/kWh</small></strong></div>
        <div><span>Minimum</span><strong>${min.toFixed(2)}<small>Ft/kWh</small></strong></div>
        <div><span>Átlag</span><strong>${avg.toFixed(2)}<small>Ft/kWh</small></strong></div>
        <div><span>Maximum</span><strong>${max.toFixed(2)}<small>Ft/kWh</small></strong></div>
      </div>
      <div class="chart-wrap">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="D tarifa teljes napi előrejelzés">
          ${grid}
          ${xLabels}
          ${avgLine}
          ${nowLine}
          <path d="${path}" class="price-line" />
          <text x="${left}" y="14" class="axis-title">Ft/kWh</text>
        </svg>
      </div>
      <div class="footer">
        <span>${this._escape(forecastDate)}</span>
        <span>${points.length} időszak · ${statusText}</span>
      </div>
    `);
  }

  _cardShell(content) {
    const title = this._escape(this.config?.title || "D tarifa – Mai ár-előrejelzés");
    return `
      <ha-card>
        <style>
          ha-card { padding: 18px; overflow: hidden; }
          .title { font-size: 20px; font-weight: 500; margin-bottom: 14px; }
          .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); gap: 8px; margin-bottom: 10px; }
          .summary div { background: var(--secondary-background-color); border-radius: 10px; padding: 9px 10px; min-width: 0; }
          .summary span { display: block; color: var(--secondary-text-color); font-size: 12px; margin-bottom: 4px; }
          .summary strong { display: flex; align-items: baseline; gap: 5px; font-size: 14px; line-height: 1.15; white-space: nowrap; }
          .summary small { color: var(--secondary-text-color); font-size: 10px; font-weight: 500; }
          .chart-wrap { width: 100%; overflow: hidden; }
          svg { width: 100%; height: auto; display: block; }
          .grid { stroke: var(--divider-color); stroke-width: 1; }
          .vgrid { stroke: var(--divider-color); stroke-width: 0.7; opacity: 0.55; }
          .ylabel { fill: var(--secondary-text-color); font-size: 12px; text-anchor: end; }
          .xlabel { fill: var(--secondary-text-color); font-size: 12px; text-anchor: middle; }
          .axis-title { fill: var(--secondary-text-color); font-size: 12px; }
          .price-line { fill: none; stroke: var(--primary-color); stroke-width: 4; stroke-linejoin: round; stroke-linecap: round; }
          .now { stroke: var(--error-color, #db4437); stroke-width: 2; stroke-dasharray: 7 5; }
          .avg { stroke: var(--secondary-text-color); stroke-width: 1.5; stroke-dasharray: 5 5; opacity: 0.8; }
          .footer { display: flex; justify-content: space-between; gap: 12px; color: var(--secondary-text-color); font-size: 12px; margin-top: 2px; flex-wrap: wrap; }
          .empty { color: var(--secondary-text-color); padding: 24px 4px; }
          @media (max-width: 600px) {
            ha-card { padding: 14px; }
            .summary { grid-template-columns: repeat(2, minmax(0,1fr)); }
            .title { font-size: 18px; }
          }
        </style>
        <div class="title">${title}</div>
        ${content}
      </ha-card>
    `;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
}

if (!customElements.get("mvm-d-tariff-forecast-card")) {
  customElements.define("mvm-d-tariff-forecast-card", MvmDTariffForecastCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "mvm-d-tariff-forecast-card")) {
  window.customCards.push({
    type: "mvm-d-tariff-forecast-card",
    name: "MVM D tarifa – Napi ár-előrejelzés",
    description: "A teljes napi D tarifa day-ahead (DAM) előrejelzés megjelenítése.",
    preview: true,
    documentationURL: "https://github.com/Krissz55555/ha-mvm-d-tariff",
    getEntitySuggestion: (hass, entityId) => {
      const state = hass.states?.[entityId];
      if (!state || !Array.isArray(state.attributes?.forecast)) return null;
      return {
        config: {
          type: "custom:mvm-d-tariff-forecast-card",
          entity: entityId,
          title: "D tarifa – Mai ár-előrejelzés",
        },
      };
    },
  });
}
