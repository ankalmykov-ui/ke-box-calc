const byId = (id) => document.getElementById(id);

async function loadMeta() {
  const indicator = byId("api-indicator");
  try {
    const response = await fetch("/api/v2/meta", { headers: { Accept: "application/json" } });
    const meta = await response.json();
    if (!response.ok) {
      const code = [meta.error_type, meta.missing_module].filter(Boolean).join(": ");
      throw new Error(code || `HTTP ${response.status}`);
    }
    byId("api-version").textContent = meta.api_version;
    byId("database-state").textContent = meta.database.configured ? "Подключена" : "Не подключена";
    byId("schema-range").textContent = `${meta.database.schema_min}–${meta.database.schema_max}`;
    indicator.textContent = `${meta.app_version} · API доступен`;
    indicator.className = "status ok";
  } catch (error) {
    indicator.textContent = `API недоступен · ${error.message}`;
    indicator.className = "status bad";
    console.error("meta request failed", error);
  }
}

let materials = [];

const requestJson = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: { Accept: "application/json", "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
};

const number = (value, digits = 2) => Number(value || 0).toLocaleString("ru-RU", { maximumFractionDigits: digits });

async function loadMaterials() {
  const list = byId("materials-list");
  try {
    const payload = await requestJson("/api/v2/materials");
    materials = payload.items;
    list.innerHTML = materials.length ? materials.map((item) => `
      <div class="material-row">
        <div><strong>${item.name}</strong><small>${number(item.grammage_g_m2)} г/м² · ${item.width_mm} мм</small></div>
        <div><strong>${number(item.balance_kg, 3)} кг</strong><small>${item.price_rub_kg == null ? "Цена не задана" : `${number(item.price_rub_kg)} ₽/кг`}</small></div>
      </div>`).join("") : '<p class="muted">Сырьё пока не добавлено.</p>';
    const options = materials.map((item) => `<option value="${item.id}">${item.name} · ${item.width_mm} мм</option>`).join("");
    byId("layer-selects").innerHTML = ["Внешний слой", "Флютинг", "Внутренний слой"].map((label) => `<label>${label}<select name="material_id" required>${options}</select></label>`).join("");
  } catch (error) {
    list.innerHTML = `<p class="message bad">${error.message}</p>`;
  }
}

byId("material-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = byId("material-message");
  const values = Object.fromEntries(new FormData(event.currentTarget));
  for (const key of ["grammage_g_m2", "width_mm", "quantity_kg", "price_rub_kg"]) {
    if (values[key] !== "") values[key] = Number(values[key]); else values[key] = null;
  }
  try {
    await requestJson("/api/v2/materials", { method: "POST", body: JSON.stringify(values) });
    message.textContent = "Сырьё добавлено отдельным складским движением.";
    message.className = "message ok";
    await loadMaterials();
  } catch (error) {
    message.textContent = error.message;
    message.className = "message bad";
  }
});

byId("calculation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = byId("calculation-result");
  const data = new FormData(event.currentTarget);
  const payload = Object.fromEntries(data);
  payload.material_ids = data.getAll("material_id");
  for (const key of ["length_mm", "width_mm", "height_mm", "quantity", "technological_trim_mm"]) payload[key] = Number(payload[key]);
  try {
    const answer = await requestJson("/api/v2/calculations/first-variant", { method: "POST", body: JSON.stringify(payload) });
    if (answer.status === "blocked") {
      result.innerHTML = `<h3>Вариант заблокирован</h3><p>${answer.reason}</p>`;
      result.className = "result bad";
      return;
    }
    result.innerHTML = `
      <div class="result-grid">
        <div><small>Статус</small><strong>${answer.status}</strong></div>
        <div><small>Ручьи</small><strong>${answer.geometry.lanes}</strong></div>
        <div><small>Обрезь</small><strong>${number(answer.geometry.trim_percent)}%</strong></div>
        <div><small>Погонные метры</small><strong>${number(answer.geometry.run_length_m)} м</strong></div>
        <div><small>Сырьё</small><strong>${number(answer.cost.materials_total_rub)} ₽</strong></div>
        <div><small>На короб</small><strong>${number(answer.cost.per_box_rub)} ₽</strong></div>
      </div>
      <p>${answer.strength.message}</p>
      ${(answer.missing || []).map((item) => `<p class="warning">${item}</p>`).join("")}`;
    result.className = answer.cost.complete ? "result ok" : "result warning-box";
  } catch (error) {
    result.textContent = error.message;
    result.className = "result bad";
  }
});

byId("refresh-materials").addEventListener("click", loadMaterials);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

loadMeta();
loadMaterials();
