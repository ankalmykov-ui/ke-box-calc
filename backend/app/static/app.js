const $ = id => document.getElementById(id);
const state = {
  mode: sessionStorage.getItem("boxcalc.mode") || "quick",
  order: [],
  previewOrders: [],
  previewMaterials: [],
  materials: [],
  labPreview: null,
  candidates: [],
  equipment: null,
  norms: null,
  result: null
};

const money = v => v == null ? "—" : new Intl.NumberFormat("ru-RU",{maximumFractionDigits:0}).format(v) + " ₽";
const num = (v,d=1) => v == null ? "—" : new Intl.NumberFormat("ru-RU",{maximumFractionDigits:d}).format(v);
const esc = s => String(s ?? "").replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));

async function api(url,opt){
  const r = await fetch(url,opt);
  const body = await r.text();
  let d;
  try { d = body ? JSON.parse(body) : {}; } catch { d = {detail: body || `HTTP ${r.status}`}; }
  if(!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
  return d;
}
function toast(msg,error=false){
  const t=$("toast"); t.textContent=msg; t.className="toast show"+(error?" error":"");
  clearTimeout(toast.timer); toast.timer=setTimeout(()=>t.className="toast",2600);
}
function persist(){
  sessionStorage.setItem("boxcalc.mode",state.mode);
  $("sessionHint").textContent=`Заказ: ${state.order.length} поз. · 1С: ${state.materials.length} · комп.: ${state.candidates.length}`;
}
function showView(name){
  document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===`view-${name}`));
  document.querySelectorAll(".nav-btn").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
  if(name==="result" && !state.result) renderResultEmpty();
}
function setMode(mode){
  state.mode=mode;
  $("quickModeBtn").classList.toggle("active",mode==="quick");
  $("engineerModeBtn").classList.toggle("active",mode==="engineer");
  document.body.classList.toggle("engineer-mode",mode==="engineer");
  document.querySelectorAll(".engineer-only").forEach(x=>x.classList.toggle("hidden",mode!=="engineer"));
  if(mode!=="engineer" && $("view-engineering").classList.contains("active")) showView("order");
  persist();
}
function syncProductType(){
  const isSheet=$("productType").value==="sheet";
  $("fefcoFields").classList.toggle("hidden",isSheet);
  $("sheetFields").classList.toggle("hidden",!isSheet);
}
function currentItem(){
  const isSheet=$("productType").value==="sheet";
  const item={
    code:$("itemCode").value.trim() || `ITEM-${state.order.length+1}`,
    product_type:isSheet?"sheet":"0201",
    quantity:+$("quantity").value,
    required_board_grade:$("boardGrade").value,
    profile:$("profile").value,
    colors:+$("colors").value || 0,
    die_cut:$("dieCut").checked,
    client:$("client").value.trim()||null,
    order_ref:$("orderRef").value.trim()||null,
    due_date:$("dueDate").value||null
  };
  if(isSheet){
    item.blank_length_mm=+$("blankLengthMm").value;
    item.blank_width_mm=+$("blankWidthMm").value;
  }else{
    item.length_mm=+$("lengthMm").value;
    item.width_mm=+$("widthMm").value;
    item.height_mm=+$("heightMm").value;
    const j=+$("jointMm").value, d=+$("caliperMm").value;
    if(j>0) item.manufacturer_joint_mm=j;
    if(d>0) item.caliper_mm=d;
  }
  return item;
}
function validateItem(x){
  if(!x.code) return "Не указан код позиции";
  if(!Number.isInteger(x.quantity)||x.quantity<=0) return "Количество должно быть целым и больше нуля";
  if(!x.required_board_grade) return "Не указана марка";
  if(!x.profile) return "Не указан профиль";
  if(x.product_type==="0201" && (!(x.length_mm>0)||!(x.width_mm>0)||!(x.height_mm>0))) return "Для FEFCO 0201 нужны L, B и H";
  if(x.product_type==="sheet" && (!(x.blank_length_mm>0)||!(x.blank_width_mm>0))) return "Для листа нужны длина и ширина заготовки";
  return null;
}
function resetResult(){
  state.result=null;
  renderResultEmpty();
  $("snapshotPreview").textContent="Сначала выполните расчёт.";
}
function addItem(){
  const x=currentItem(), err=validateItem(x);
  if(err){toast(err,true);return}
  state.order.push(x); resetResult(); renderOrder(); persist(); toast("Позиция добавлена");
}
function removeItem(i){ state.order.splice(i,1); resetResult(); renderOrder(); persist(); }
function renderOrder(){
  $("orderCount").textContent=state.order.length;
  const totalQty=state.order.reduce((s,x)=>s+(+x.quantity||0),0);
  $("orderSummary").textContent=state.order.length?`${state.order.length} поз. · ${new Intl.NumberFormat("ru-RU").format(totalQty)} шт`:"Пока нет изделий.";
  const el=$("orderTable");
  if(!state.order.length){el.className="table-wrap empty-state";el.innerHTML="Добавьте первое изделие или загрузите файл.";return}
  el.className="table-wrap";
  el.innerHTML=`<table class="data-table"><thead><tr><th>Код</th><th>Тип</th><th>Размер</th><th>Кол-во</th><th>Марка</th><th>Профиль</th><th>Клиент / заказ</th><th></th></tr></thead><tbody>${
    state.order.map((x,i)=>{
      const size=x.product_type==="sheet"?`${x.blank_length_mm}×${x.blank_width_mm}`:`${x.length_mm}×${x.width_mm}×${x.height_mm}`;
      return `<tr><td><b>${esc(x.code)}</b></td><td>${x.product_type==="sheet"?"Лист":"0201"}</td><td>${size}</td><td>${x.quantity}</td><td>${esc(x.required_board_grade)}</td><td>${esc(x.profile)}</td><td>${esc(x.client||"—")}<small>${x.order_ref?` · ${esc(x.order_ref)}`:""}</small></td><td class="actions"><button class="icon-btn" onclick="removeItem(${i})">Удалить</button></td></tr>`
    }).join("")
  }</tbody></table>`;
}
async function previewGeometry(){
  try{
    const x=currentItem();
    if(x.product_type==="sheet"){ $("geometryPreview").innerHTML=`Лист: <b>${x.blank_length_mm} × ${x.blank_width_mm} мм</b> · площадь ${num(x.blank_length_mm*x.blank_width_mm/1e6,4)} м²`; return; }
    const body={length_mm:x.length_mm,width_mm:x.width_mm,height_mm:x.height_mm,profile:x.profile};
    if(x.manufacturer_joint_mm) body.manufacturer_joint_override_mm=x.manufacturer_joint_mm;
    if(x.caliper_mm) body.caliper_override_mm=x.caliper_mm;
    const d=await api("/api/calc/fefco0201/profile",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const b=d.blank,p=d.panels||{};
    $("geometryPreview").innerHTML=`Заготовка <b>${b.length_mm} × ${b.width_mm} мм</b> · ${num(b.area_m2,4)} м²<br><span class="muted">Панели: ${[p.L1_mm,p.B1_mm,p.L2_mm,p.B2_mm].filter(v=>v!=null).join(" / ")||"см. расчёт"} мм</span>`;
  }catch(e){toast(e.message,true)}
}
function clearOrder(){
  state.order=[];state.previewOrders=[];resetResult();renderOrder();
  $("orderImportState").textContent="Файл не загружен.";$("applyOrdersBtn").disabled=true;
  persist();showView("order");toast("Заказ и результат очищены");
}

async function previewOrders(){
  try{
    const f=$("orderFile").files[0];if(!f) throw new Error("Выберите XLSX или CSV");
    const fd=new FormData();fd.append("file",f);
    const d=await api("/api/import/orders/preview",{method:"POST",body:fd});
    state.previewOrders=d.rows||[];
    $("applyOrdersBtn").disabled=!(d.stats?.rows_valid>0);
    $("orderImportState").innerHTML=`Строк: <b>${d.stats.rows_total}</b> · корректных: <b class="good">${d.stats.rows_valid}</b> · ошибок: <b class="${d.stats.rows_invalid?"bad":""}">${d.stats.rows_invalid}</b>`;
  }catch(e){toast(e.message,true)}
}
function applyOrders(){
  const rows=state.previewOrders.filter(x=>x.valid).map(x=>{
    const y={...x};delete y.valid;delete y.issues;delete y.row_number;return y;
  });
  state.order.push(...rows);resetResult();renderOrder();persist();toast(`Добавлено ${rows.length} поз.`);
}

function materialPayload(r){
  return {
    code_1c:r.code_1c,variant_1c:r.variant_1c||null,name:r.name,gsm:+r.gsm,price_rub_t:+r.price_rub_t,
    stock_kg:r.stock_kg==null?null:+r.stock_kg,procurement_status:r.procurement_status||"active",
    supplier:r.supplier||null,manufacturer:r.manufacturer||null,material_type:r.material_type||null,
    roll_width_mm:r.roll_width_mm==null?null:+r.roll_width_mm,price_date:r.price_date||null,stock_date:r.stock_date||null,
    technological_code:r.technological_code||null,color:r.color||null
  };
}
async function preview1C(){
  try{
    const f=$("onecFile").files[0];if(!f) throw new Error("Выберите файл 1С");
    const fd=new FormData();fd.append("file",f);
    const d=await api("/api/import/1c/materials/preview",{method:"POST",body:fd});
    state.previewMaterials=d.rows||[];
    $("apply1cBtn").disabled=!(d.stats?.rows_valid>0);
    $("onecState").innerHTML=`Корректных строк: <b class="good">${d.stats.rows_valid}</b> · замечаний: <b>${d.stats.issues}</b>`;
    renderMaterials(state.previewMaterials.slice(0,30),true);
  }catch(e){toast(e.message,true)}
}
function apply1C(){
  state.materials=state.previewMaterials
    .filter(r=>r.code_1c&&r.name&&+r.gsm>0&&+r.price_rub_t>0&&r.procurement_status!=="requires_classification")
    .map(materialPayload);
  $("materialsCount").textContent=`${state.materials.length} активно`;
  $("onecState").innerHTML=`<span class="good">В расчёте активно ${state.materials.length} материалов.</span>`;
  renderMaterials(state.materials,false);renderCompositionLayers();resetResult();persist();
  toast("Данные 1С применены к текущей сессии");
}
function renderMaterials(rows,preview=false){
  const el=$("materialsTable");
  if(!rows?.length){el.innerHTML="";return}
  el.innerHTML=rows.slice(0,40).map(r=>`<div class="mini-row"><div><b>${esc(r.code_1c)} · ${esc(r.name)}</b><small>${esc(r.material_type||"тип не указан")} · ${r.gsm} г/м² · рулон ${r.roll_width_mm??"—"} мм</small></div><div>${num(r.price_rub_t,0)} ₽/т<br><small>${esc(r.procurement_status||"")}</small></div></div>`).join("")+(rows.length>40?`<div class="muted">Показаны первые 40 из ${rows.length}</div>`:"");
}
async function previewLab(){
  try{
    const f=$("labFile").files[0];if(!f) throw new Error("Выберите лабораторный XLSX/CSV");
    const fd=new FormData();fd.append("file",f);
    const d=await api("/api/import/lab/preview",{method:"POST",body:fd});
    state.labPreview=d;$("labCount").textContent=`${d.stats.rows_valid} записей`;
    $("labState").innerHTML=`Распознано листов: <b>${d.stats.sheets_recognized}/${d.stats.sheets_total}</b> · записей: <b class="good">${d.stats.rows_valid}</b> · замечаний: <b>${d.stats.issues}</b><br><span class="muted">Preview готов. Сохранение истории будет подключено к PostgreSQL.</span>`;
  }catch(e){toast(e.message,true)}
}

function materialKey(m){return m.code_1c+(m.variant_1c?`::${m.variant_1c}`:"")}
function renderCompositionLayers(){
  const n=+$("layerCount").value||3, el=$("compositionLayers");
  const roles=n===5?["outer","medium_1","middle_liner","medium_2","inner"]:["outer","medium","inner"];
  const coeffs=n===5?[1,1.47,1,1.36,1]:[1,1.47,1];
  const opts=state.materials.length
    ?state.materials.map(m=>`<option value="${esc(materialKey(m))}">${esc(m.name)} · ${m.gsm} · ${m.roll_width_mm??"—"} мм</option>`).join("")
    :`<option value="">Сначала примените сырьё из 1С</option>`;
  el.innerHTML=roles.map((r,i)=>`<div class="layer-row"><div class="role">${r}</div><label>Материал<select id="layerMat${i}">${opts}</select></label><label>K гофрирования<input id="layerK${i}" type="number" step="0.001" value="${coeffs[i]}"></label></div>`).join("");
}
function addComposition(){
  const n=+$("layerCount").value||3, roles=n===5?["outer","medium_1","middle_liner","medium_2","inner"]:["outer","medium","inner"];
  if(!state.materials.length){toast("Сначала примените сырьё из 1С",true);return}
  const code=$("compCode").value.trim()||`COMP-${state.candidates.length+1}`;
  const layers=roles.map((r,i)=>({role:r,material_key:$(`layerMat${i}`).value,corrugation_coefficient:+$(`layerK${i}`).value||1}));
  if(layers.some(x=>!x.material_key)){toast("Выберите материал для каждого слоя",true);return}
  state.candidates.push({
    code,board_grade:$("compGrade").value,profile:$("compProfile").value,layers,status:"approved",
    evidence:"technologist_approved",strength_reserve_pct:+$("strengthReserve").value||0,lab_pass_count:+$("labPassCount").value||0
  });
  renderCompositions();resetResult();persist();toast("Композиция добавлена в сессию");
}
function removeComposition(i){state.candidates.splice(i,1);renderCompositions();resetResult();persist()}
function clearCompositions(){state.candidates=[];renderCompositions();resetResult();persist()}
function renderCompositions(){
  $("candidateCount").textContent=state.candidates.length;
  $("compositionList").innerHTML=state.candidates.length?state.candidates.map((c,i)=>`<div class="candidate-row"><div class="result-row-head"><div><b>${esc(c.code)}</b> · ${esc(c.board_grade)} / ${esc(c.profile)}<small class="muted"> · ${c.layers.length} сл.</small></div><button class="icon-btn" onclick="removeComposition(${i})">Удалить</button></div><div class="muted">${c.layers.map(x=>`${x.role}: ${esc(x.material_key)} ×${x.corrugation_coefficient}`).join(" · ")}</div></div>`).join(""):`<div class="inline-result muted">Сессионных утверждённых композиций пока нет. Без них стоимость сырья не рассчитывается.</div>`;
}

function getRates(){
  const out={};(state.equipment?.machines||[]).forEach(m=>{const v=+$(`rate_${m.code}`)?.value;if(v>0)out[m.code]=v});return out;
}
function rollWidths(){
  return $("rollWidths").value.split(/[,;\s]+/).map(Number).filter(x=>x>0);
}
async function calculateOrder(){
  try{
    if(!state.order.length) throw new Error("Добавьте хотя бы одну позицию");
    const payload={
      items:state.order,
      roll_widths_mm:rollWidths(),
      working_width_mm:+$("gaWidth").value||2100,
      max_streams:+$("maxStreams").value||5,
      other_waste_pct:+$("otherWaste").value||0,
      planning_horizon_days:+$("planningHorizon").value||1,
      materials:state.materials,
      candidates:state.candidates,
      machine_hourly_costs:getRates()
    };
    const d=await api("/api/calc/full",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    state.result=d;renderResult();showView("result");toast("Расчёт выполнен");
  }catch(e){toast(e.message,true)}
}
function renderResultEmpty(){
  $("resultEmpty").classList.remove("hidden");$("resultBody").classList.add("hidden");
  ["mItems","mArea","mMaterialCost","mTotalCost"].forEach(id=>$(id).textContent="—");
}
function strengthHTML(x){
  const s=x.strength;
  if(!s) return `<span class="muted">BCT — не применяется</span>`;
  const ect=s.normative_ect_kn_m ?? s.ect_min_kn_m;
  if(s.bct_estimated_kn==null) return `<span class="warn">Нормативный ECT: ${ect??"нет"} · Расчётный BCT: нет данных</span>`;
  return `<span>Нормативный ECT <b>${num(ect,2)} кН/м</b> · Расчётный BCT <b>${num(s.bct_estimated_kn,3)} кН</b> (${num(s.bct_estimated_kgf,1)} кгс)</span>${s.warning?`<div class="notice warn">${esc(s.warning)}</div>`:""}`;
}
function renderResult(){
  const d=state.result;if(!d){renderResultEmpty();return}
  $("resultEmpty").classList.add("hidden");$("resultBody").classList.remove("hidden");
  $("mItems").textContent=d.items.length;
  $("mArea").textContent=`${num(d.cost.net_order_area_m2,1)} м²`;
  $("mMaterialCost").textContent=money(d.cost.material_cost_rub);
  $("mTotalCost").textContent=money(d.cost.known_total_cost_rub);
  $("rollSource").textContent=d.roll_width_source==="1c_materials"?"ширины: из 1С":"ширины: вручную";
  $("resultItems").innerHTML=d.items.map(x=>{
    const size=x.product_type==="SHEET"?`${x.blank_length_mm}×${x.blank_width_mm}`:`${x.length_mm}×${x.width_mm}×${x.height_mm}`;
    return `<div class="result-row"><div class="result-row-head"><div><strong>${esc(x.code)}</strong> · ${esc(x.product_type)}</div><span class="pill">${esc(x.profile)} / ${esc(x.required_board_grade)}</span></div><div class="subgrid"><div class="kv"><span>Изделие</span><b>${size} мм</b></div><div class="kv"><span>Заготовка</span><b>${x.blank_length_mm}×${x.blank_width_mm} мм</b></div><div class="kv"><span>Площадь 1 шт.</span><b>${num(x.blank_area_m2,4)} м²</b></div><div class="kv"><span>Количество</span><b>${x.quantity} шт.</b></div></div><div class="notice good">${strengthHTML(x)}</div></div>`
  }).join("");

  $("layoutResults").innerHTML=d.corrugator.map(g=>`<div class="launch-card"><div class="launch-head"><div><strong>Профиль ${esc(g.profile)}</strong><div class="muted">${g.launches.length} запуск(а)</div></div></div>${g.launches.map((l,idx)=>layoutHTML(l,idx)).join("")}</div>`).join("");

  $("machineResults").innerHTML=d.processing.map(p=>machineHTML(p)).join("");
  const c=d.cost;
  $("costResults").innerHTML=`<div class="cost-cell"><span>Площадь заказа</span><strong>${num(c.net_order_area_m2,2)} м²</strong></div><div class="cost-cell"><span>Стоимость сырья</span><strong>${money(c.material_cost_rub)}</strong></div><div class="cost-cell"><span>Переработка</span><strong>${money(c.conversion_cost_rub)}</strong></div><div class="cost-cell"><span>Известная сумма</span><strong>${money(c.known_total_cost_rub)}</strong></div>`;
  if(c.notes?.length)$("costResults").insertAdjacentHTML("afterend",`<div class="inline-result muted">${c.notes.map(esc).join("<br>")}</div>`);
  $("snapshotPreview").textContent=JSON.stringify(d.snapshot,null,2);
}
function layoutHTML(l,idx){
  const alts=l.layout_alternatives||[];
  const comp=l.composition_selection;
  const compText=comp?.recommended
    ?`Композиция: ${esc(comp.recommended.candidate.code)} · сырьё ${money(comp.recommended.calculation.total_cost_rub)}`
    :`Композиция не выбрана${comp?` · допустимых ${comp.eligible_candidates}`:""}`;
  return `<div class="result-row"><div class="result-row-head"><div><b>Запуск ${idx+1}</b> · рулон ${l.roll_width_mm} мм · ${l.streams_total} руч.</div><span class="pill">${esc(l.target_board_grade||"—")}</span></div><div class="subgrid"><div class="kv"><span>Обрезь</span><b>${num(l.edge_trim_pct,2)}%</b></div><div class="kv"><span>Метраж</span><b>${num(l.run_length_m,1)} м</b></div><div class="kv"><span>Площадь полотна</span><b>${num(l.gross_board_area_m2,1)} м²</b></div><div class="kv"><span>Потери</span><b>${num(l.total_waste_m2,1)} м²</b></div></div><div class="notice ${comp?.recommended?"good":"warn"}">${compText}</div>${alts.length?`<div class="alts">${alts.map(v=>`<div class="alt-row ${v.is_recommended?"recommended":""}"><span>${v.is_recommended?'<b class="star">★</b>':"#"+v.rank}</span><span>${v.roll_width_mm} мм</span><span>${v.streams_total} руч.</span><span>${num(v.total_waste_m2,1)} м² потерь</span><span>${num(v.run_length_m,1)} м</span></div>`).join("")}</div>`:""}</div>`;
}
function machineHTML(p){
  const s=p.machine_selection;if(!s)return `<div class="machine-row"><b>${esc(p.code)}</b> · для листовой заготовки маршрут переработки не назначается.</div>`;
  const rec=s.recommended;
  return `<div class="machine-row"><div class="machine-head"><div><b>${esc(p.code)}</b><div class="muted">${rec?`Рекомендуется ${esc(rec.name)}${rec.model?` · ${esc(rec.model)}`:""}`:"Нет допустимой машины"}</div></div>${rec?`<span class="pill">${rec.estimated_speed_per_hour?num(rec.estimated_speed_per_hour,0)+" шт/ч":"скорость не откалибрована"}</span>`:""}</div>${rec?.warnings?.length?`<div class="notice warn">${rec.warnings.map(esc).join("<br>")}</div>`:""}${s.excluded?.length?`<div class="alts">${s.excluded.map(m=>`<div class="notice bad"><b>${esc(m.name)}</b>: ${m.reasons.map(esc).join("; ")}</div>`).join("")}</div>`:""}</div>`;
}

async function loadReferences(){
  try{
    const [mods,norms,equip]=await Promise.all([
      api("/api/modules"),api("/api/reference/board-grade-norms"),api("/api/reference/equipment")
    ]);
    $("apiState").textContent=`API ${mods.version}`;$("apiState").className="status-dot ok";
    state.norms=norms;state.equipment=equip;
    renderGradeOptions();renderNorms();renderEquipment();renderMachineRates();renderCompositionLayers();
  }catch(e){
    $("apiState").textContent="API недоступен";$("apiState").className="status-dot bad";toast(e.message,true);
  }
}
function gradeEntries(){
  const grades=state.norms?.grades||{};
  return Object.keys(grades);
}
function renderGradeOptions(){
  const opts=gradeEntries().map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join("");
  $("boardGrade").innerHTML=opts;$("compGrade").innerHTML=opts;
  if(gradeEntries().includes("T23.1"))$("boardGrade").value="T23.1";
}
function renderNorms(){
  const grades=state.norms?.grades||{};
  $("gradeNorms").innerHTML=Object.entries(grades).map(([g,v])=>`<div class="mini-row"><b>${esc(g)}</b><span>ECT ≥ <b>${num(v.ect_min,2)} кН/м</b></span></div>`).join("");
}
function formatSheet(m){
  const s=m.sheet||{};return `${s.min_a_mm??"—"}×${s.min_b_mm??"—"} → ${s.max_a_mm??"—"}×${s.max_b_mm??"—"} мм`;
}
function renderEquipment(){
  const ms=state.equipment?.machines||[];
  $("equipmentCards").innerHTML=ms.map(m=>{
    const sp=m.speed||{}, th=m.board_thickness_mm||{};
    const speed=sp.cruise_per_hour?`${num(sp.cruise_per_hour,0)} шт/ч`:sp.economic_min_per_hour?`${num(sp.economic_min_per_hour,0)}–${num(sp.economic_max_per_hour,0)} шт/ч (каталог)`:"—";
    return `<div class="machine-card"><div class="result-row-head"><div><h3>${esc(m.name)}</h3><div class="muted">${esc(m.model||"")}</div></div><span class="pill ${m.status==="passport_confirmed"?"":"warning"}">${esc(m.status)}</span></div><div class="spec-list"><div class="spec-line"><span>Формат</span><b>${formatSheet(m)}</b></div><div class="spec-line"><span>Толщина</span><b>${th.min??"—"}–${th.max??"—"} мм</b></div><div class="spec-line"><span>Цветов</span><b>${m.colors??"—"}</b></div><div class="spec-line"><span>Скорость</span><b>${speed}</b></div><div class="spec-line"><span>Профили</span><b>${(m.profiles||[]).join(", ")}</b></div></div><div class="machine-source">${esc(m.source||"")}</div></div>`
  }).join("");
}
function renderMachineRates(){
  $("machineRates").innerHTML=(state.equipment?.machines||[]).map(m=>`<label>${esc(m.name)}, ₽/ч<input id="rate_${m.code}" type="number" min="0" placeholder="не задано"></label>`).join("");
}

document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll(".nav-btn").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
  $("quickModeBtn").addEventListener("click",()=>setMode("quick"));
  $("engineerModeBtn").addEventListener("click",()=>setMode("engineer"));
  setMode(state.mode);syncProductType();renderOrder();renderCompositions();renderResultEmpty();loadReferences();persist();
  if("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(()=>{});
});
