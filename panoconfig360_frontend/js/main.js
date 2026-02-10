import { ConfigLoader } from "./config/ConfigLoader.js";
import { Configurator } from "./core/Configurator.js";
import { ViewerManager } from "./viewer/ViewerManager.js";
import { RenderService } from "./services/RenderService.js";
import { UIController } from "./ui/UIController.js";
import { SceneSelector } from "./ui/SceneSelector.js";
import { Render2DModal } from "./ui/Render2DModal.js";

// ======================================================
// CONFIGURAÇÃO
// ======================================================
const CLIENT_ID = "monte-negro";
const VIEWER_CONTAINER_ID = "pano-config-api";

// ======================================================
// INSTÂNCIAS GLOBAIS
// ======================================================
let configLoader = null;
let configurator = null;
let viewerManager = null;
let renderService = null;
let uiController = null;
let sceneSelector = null;
let render2DModal = null;

let renderDebounceTimer = null;
let currentAbortController = null;

// ======================================================
// UTILITY FUNCTIONS
// ======================================================
function getBuildFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("build");
}

function updateUrl(build) {
  const url = new URL(window.location.href);
  url.searchParams.set("build", build);
  window.history.replaceState({}, "", url);
}

function isValidBuild(build) {
  return typeof build === "string" && /^[0-9a-z]{12}$/.test(build);
}

// ======================================================
// INICIALIZAÇÃO
// ======================================================
document.addEventListener("DOMContentLoaded", init);

async function init() {
  try {
    console.log("[Main] Iniciando aplicação...");

    // 1. Carrega configuração do cliente
    configLoader = new ConfigLoader(CLIENT_ID);
    await configLoader.load();

    // 2. Cria configurator
    configurator = new Configurator(configLoader);

    const buildFromUrl = getBuildFromUrl();

    if (isValidBuild(buildFromUrl)) {
      console.log(
        "[Main] Inicializando a partir da build da URL:",
        buildFromUrl,
      );
      configurator.initializeFromBuild(buildFromUrl);
    } else {
      configurator.initializeSelection();
    }

    // 4. Inicializa o viewer
    const viewerConfig = configLoader.getViewerConfig();
    viewerManager = new ViewerManager(VIEWER_CONTAINER_ID, viewerConfig);
    await viewerManager.initialize();

    // 5. Serviços
    renderService = new RenderService();
    render2DModal = new Render2DModal();

    // 6. Scene selector
    const scenes = configLoader.getSceneList();
    sceneSelector = new SceneSelector("scene-selector", handleSceneChange);
    sceneSelector.render(scenes, configurator.sceneId);

    // 7. UI
    uiController = new UIController(configurator, {
      onSelectionChange: handleSelectionChange,
      onFocusRequest: handleFocusRequest,
      onSave2Render: handleSave2Render,
      onToggleSceneSelector: handleToggleSceneSelector,
    });
    uiController.renderMainMenu();

    // 8. Carrega a cena inicial
    await loadCurrentScene();

    console.log("[Main] Aplicação iniciada com sucesso!");
  } catch (error) {
    console.error("[Main] Erro na inicialização:", error);
  }
}

// ======================================================
// HANDLERS
// ======================================================

// Carrega a cena atual baseada na seleção do configurator
async function loadCurrentScene() {
  // cancela request anterior
  if (currentAbortController) {
    currentAbortController.abort();
  }

  currentAbortController = new AbortController();

  try {
    const result = await renderService.renderCubemap(
      configLoader.clientId,
      configurator.sceneId,
      configurator.currentSelection,
      currentAbortController.signal,
    );

    if (!result?.tiles) return;

    await viewerManager.loadScene(result.tiles);
    updateUrl(result.build);
  } catch (err) {
    // ignora abort silenciosamente
    if (err.name === "AbortError") return;

    console.error("[Main] Erro ao carregar cena:", err);
  }
}

// Handler para mudança de seleção
async function handleSelectionChange() {
  clearTimeout(renderDebounceTimer);

  renderDebounceTimer = setTimeout(() => {
    loadCurrentScene();
  }, 180); // 150–220ms é o sweet spot
}

/**
 * Handler para foco em POI
 */
function handleFocusRequest(layerId) {
  console.log(`[Main] Foco solicitado: ${layerId}`);
  viewerManager.focusOn(layerId);
}

/**
 * Handler para mudança de cena
 */
async function handleSceneChange(sceneId) {
  console.log(`[Main] Mudando para cena: ${sceneId}`);

  // Troca a cena no configurator
  configurator.switchScene(sceneId);

  // Atualiza UI
  uiController.setConfigurator(configurator);

  // Fecha o seletor de cenas
  sceneSelector.hide();

  // Carrega a nova cena
  await loadCurrentScene();
}

/**
 * Handler para toggle do seletor de cenas
 */
function handleToggleSceneSelector() {
  sceneSelector.toggle();
}

/**
 * Handler para renderização 2D
 */
async function handleSave2Render() {
  const clientId = configLoader.clientId;
  const sceneId = configurator.sceneId;
  const selection = configurator.currentSelection;

  console.log("[Main] Solicitando render 2D...");

  // Mostra loading
  render2DModal.showLoading();

  try {
    const result = await renderService.render2D(clientId, sceneId, selection);
    console.log("[Main] Render 2D result:", result);

    // Mostra a imagem no modal
    if (result.url) {
      render2DModal.showImage(result.url);
    } else {
      render2DModal.showError("URL da imagem não retornada");
    }
  } catch (error) {
    console.error("[Main] Erro no render 2D:", error);
    render2DModal.showError("Erro ao gerar render: " + error.message);
  }
}
