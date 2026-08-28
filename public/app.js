const byId = (id) => document.getElementById(id);

async function loadMeta() {
  const indicator = byId("api-indicator");
  try {
    const response = await fetch("/api/v2/meta", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const meta = await response.json();
    byId("api-version").textContent = meta.api_version;
    byId("database-state").textContent = meta.database.configured ? "Подключена" : "Не подключена";
    byId("schema-range").textContent = `${meta.database.schema_min}–${meta.database.schema_max}`;
    indicator.textContent = `${meta.app_version} · API доступен`;
    indicator.className = "status ok";
  } catch (error) {
    indicator.textContent = "API недоступен";
    indicator.className = "status bad";
    console.error("meta request failed", error);
  }
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/assets/sw.js").catch(() => {});
}

loadMeta();

