const statusEl = document.querySelector("#status");
const outputEl = document.querySelector("#output");
const clientsEl = document.querySelector("#clients");

function tenantHeader() {
  const tenant = document.querySelector("#tenant").value.trim();
  return tenant ? { "X-Tenant-ID": tenant } : {};
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...tenantHeader(),
    ...(options.headers || {}),
  };
  try {
    const response = await fetch(`/api${path}`, { ...options, headers });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail =
        payload?.detail?.error || payload?.error || `HTTP ${response.status}`;
      throw new Error(detail);
    }
    if (!payload || payload.status !== "success") {
      throw new Error("Resposta inválida do backend");
    }
    return payload.data;
  } catch (error) {
    statusEl.textContent = `Erro: ${error.message}`;
    throw error;
  }
}

function toObj(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  for (const key of Object.keys(data)) {
    if (
      [
        "client_id",
        "scene_index",
        "build_order",
        "item_index",
        "layer_db_id",
      ].includes(key)
    ) {
      data[key] = Number(data[key]);
    }
  }
  return data;
}

async function loadClients() {
  const clients = await api("/clients");
  clientsEl.textContent = JSON.stringify(clients, null, 2);
}

document
  .querySelector("#client-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/clients", {
      method: "POST",
      body: JSON.stringify(toObj(event.target)),
    });
    statusEl.textContent = "Cliente criado.";
    event.target.reset();
    await loadClients();
  });

document
  .querySelector("#scene-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    const { client_id, ...payload } = toObj(event.target);
    await api(`/clients/${client_id}/scenes`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    statusEl.textContent = "Cena criada.";
    event.target.reset();
  });

document
  .querySelector("#layer-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    const { client_id, scene_index, ...payload } = toObj(event.target);
    await api(`/clients/${client_id}/scenes/${scene_index}/layers`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    statusEl.textContent = "Layer criado.";
    event.target.reset();
  });

document
  .querySelector("#material-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    const { layer_db_id, ...payload } = toObj(event.target);
    await api(`/layers/${layer_db_id}/materials`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    statusEl.textContent = "Material criado.";
    event.target.reset();
  });

document
  .querySelector("#export-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    const { client_id } = toObj(event.target);
    const data = await api(`/clients/${client_id}/config`);
    outputEl.textContent = JSON.stringify(data, null, 2);
  });

loadClients().catch(() => {});
