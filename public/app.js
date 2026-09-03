const byId = (id) => document.getElementById(id);
const number = (value, digits = 2) => Number(value || 0).toLocaleString("ru-RU", { maximumFractionDigits: digits });
const money = (value) => value == null ? "нет цены" : `${number(value)} ₽`;

const requestJson = async (url, options = {}) => {
  const response = await fetch(url, { ...options, headers: { Accept: "application/json", "Content-Type": "application/json", ...(options.headers || {}) } });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
};

async function loadMeta() {
  try {
    const meta = await requestJson("/api/v2/meta");
    byId("api-indicator").textContent = `${meta.app_version} · база подключена`;
    byId("api-indicator").className = "status ok";
  } catch {
    byId("api-indicator").textContent = "Сервис недоступен";
    byId("api-indicator").className = "status bad";
  }
}

function renumberPositions() {
  const cards = [...document.querySelectorAll(".position-card")];
  cards.forEach((card, index) => {
    card.querySelector(".position-number").textContent = index + 1;
    card.querySelector(".remove-position").hidden = cards.length === 1;
    card.querySelector('[name="code"]').placeholder = `BOX-${String(index + 1).padStart(3, "0")}`;
  });
}

function addPosition() {
  const fragment = byId("position-template").content.cloneNode(true);
  fragment.querySelector(".remove-position").addEventListener("click", (event) => {
    event.currentTarget.closest(".position-card").remove();
    renumberPositions();
  });
  byId("positions").append(fragment);
  renumberPositions();
}

function readPositions() {
  return [...document.querySelectorAll(".position-card")].map((card, index) => {
    const values = {};
    card.querySelectorAll("input, select").forEach((field) => { values[field.name] = field.value; });
    for (const key of ["length_mm", "width_mm", "height_mm", "quantity", "technological_trim_mm"]) values[key] = Number(values[key]);
    values.code = values.code.trim() || `BOX-${String(index + 1).padStart(3, "0")}`;
    return values;
  });
}

const layerLabel = (role) => ({ outer: "Внешний", fluting: "Гофрирующий", inner: "Внутренний" }[role] || role);

function renderOption(option, index) {
  const composition = option.composition;
  const label = option.is_recommended ? "Рекомендуемый" : option.is_preliminary_leader ? "Предварительный лидер" : `Вариант ${index + 1}`;
  return `<article class="option-card ${index === 0 ? "featured" : ""}">
    <div class="option-head"><div><span class="rank">${label}</span><h3>Рулон ${option.roll_width_mm} мм · ${option.streams_total} руч.</h3></div><strong>${money(composition.materials_cost_rub)}</strong></div>
    <div class="metrics">
      <div><small>Обрезь</small><strong>${number(option.edge_trim_percent)}%</strong></div>
      <div><small>Потери всего</small><strong>${number(option.total_waste_m2)} м²</strong></div>
      <div><small>Метраж</small><strong>${number(option.run_length_m)} м</strong></div>
      <div><small>Поперечный рез</small><strong>${option.crosscut_lengths_mm.join(" / ")} мм</strong></div>
    </div>
    <div class="layout-lines">${option.items.map(item => `<span>${item.code}: ${item.streams} руч. · ${item.produced_quantity} шт.${item.overproduction_quantity ? ` (+${item.overproduction_quantity})` : ""}</span>`).join("")}</div>
    <div class="layers-table">${composition.layers.map(layer => `<div><span>${layerLabel(layer.role)}</span><strong>${layer.name}</strong><small>${number(layer.grammage_g_m2)} г/м² · ${number(layer.required_kg, 3)} кг · ${number(layer.price_rub_kg)} ₽/кг · ${money(layer.cost_rub)}</small></div>`).join("")}</div>
    ${(option.missing || []).map(message => `<p class="warning">${message}</p>`).join("")}
  </article>`;
}

function renderResult(answer) {
  const target = byId("calculation-result");
  const geometry = answer.items.map(item => `<div class="geometry-row"><strong>${item.code}</strong><span>заготовка ${item.geometry.blank_length_mm}×${item.geometry.blank_width_mm} мм</span><span>гофра по H · поворот запрещён</span><span>BCT ${item.strength.calculated_kn == null ? "не рассчитан" : `${number(item.strength.calculated_kn, 3)} кН`}</span></div>`).join("");
  const launches = answer.launches.map(launch => `<section class="launch"><div class="launch-title"><p class="eyebrow">Запуск ${launch.launch_number}</p><h2>Профиль ${launch.profile}</h2></div>${launch.options.length ? launch.options.map(renderOption).join("") : '<p class="message bad">Для запуска нет полного набора сырья одной ширины.</p>'}</section>`).join("");
  target.className = "calculation-output";
  target.innerHTML = `<div class="result-status ${answer.recommendation_available ? "verified" : "preliminary"}"><strong>${answer.recommendation_available ? "Оптимальный производственный вариант найден" : "Предварительный подбор выполнен"}</strong><span>${answer.recommendation_available ? "Все обязательные данные подтверждены." : "Раскрой и цена рассчитаны по складу; марку композиции ещё должен подтвердить технолог."}</span></div><section class="geometry"><h2>Заготовки</h2>${geometry}</section>${launches}${(answer.unplanned || []).map(row => `<p class="message bad">${row.code}: ${row.reason}</p>`).join("")}`;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

byId("order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  button.textContent = "Подбираю варианты…";
  try {
    const answer = await requestJson("/api/v2/calculations/auto", { method: "POST", body: JSON.stringify({ items: readPositions() }) });
    renderResult(answer);
  } catch (error) {
    byId("calculation-result").className = "result-placeholder bad";
    byId("calculation-result").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Рассчитать автоматически";
  }
});

async function loadMaterials() {
  try {
    const { items } = await requestJson("/api/v2/materials");
    const total = items.reduce((sum, item) => sum + Number(item.balance_kg), 0);
    const unclassified = items.filter(item => item.classification_status !== "approved").length;
    byId("warehouse-summary").innerHTML = `<strong>${items.length} позиций · ${number(total, 1)} кг</strong><span>${unclassified} позиций требуют классификации</span>`;
    byId("materials-list").innerHTML = items.map(item => `<div class="material-row"><span>${item.name}<small>${item.width_mm} мм · ${number(item.grammage_g_m2)} г/м²</small></span><strong>${number(item.balance_kg, 3)} кг</strong></div>`).join("");
  } catch (error) {
    byId("warehouse-summary").textContent = error.message;
  }
}

byId("add-position").addEventListener("click", addPosition);
byId("refresh-materials").addEventListener("click", loadMaterials);
addPosition();
loadMeta();
loadMaterials();
