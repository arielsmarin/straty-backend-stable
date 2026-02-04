/**
 * main.js
 * Ponto de entrada da aplicação - Orquestrador principal
 */

import { ConfigLoader } from './config/ConfigLoader.js';
import { Configurator } from './core/Configurator.js';
import { ViewerManager } from './viewer/ViewerManager.js';
import { RenderService } from './services/RenderService.js';
import { UIController } from './ui/UIController.js';
import { SceneSelector } from './ui/SceneSelector.js';

// ======================================================
// CONFIGURAÇÃO
// ======================================================
const CLIENT_ID = 'monte-negro';
const VIEWER_CONTAINER_ID = 'pano-config-api';

// ======================================================
// INSTÂNCIAS GLOBAIS
// ======================================================
let configLoader = null;
let configurator = null;
let viewerManager = null;
let renderService = null;
let uiController = null;
let sceneSelector = null;

// ======================================================
// INICIALIZAÇÃO
// ======================================================
document.addEventListener('DOMContentLoaded', init);

async function init() {
  try {
    console.log('[Main] Iniciando aplicação...');

    // 1. Carrega configuração do cliente
    configLoader = new ConfigLoader(CLIENT_ID);
    await configLoader.load();

    // 2. Cria o configurator
    configurator = new Configurator(configLoader);
    configurator.initializeSelection();

    // 3. Inicializa o viewer
    const viewerConfig = configLoader.getViewerConfig();
    viewerManager = new ViewerManager(VIEWER_CONTAINER_ID, viewerConfig);
    viewerManager.initialize();

    // 4. Cria o serviço de render
    renderService = new RenderService();

    // 5. Cria o seletor de cenas
    const scenes = configLoader.getSceneList();
    sceneSelector = new SceneSelector('scene-selector', handleSceneChange);
    sceneSelector.render(scenes, configLoader.currentSceneId);

    // 6. Cria o controlador de UI
    uiController = new UIController(configurator, {
      onSelectionChange: handleSelectionChange,
      onFocusRequest: handleFocusRequest,
      onSave2Render: handleSave2Render,
      onToggleSceneSelector: toggleSceneSelector
    });
    uiController.renderMainMenu();

    // 7. Carrega a cena inicial
    await loadCurrentScene(false);

    console.log('[Main] Aplicação iniciada com sucesso!');

  } catch (error) {
    console.error('[Main] Erro na inicialização:', error);
  }
}

// ======================================================
// HANDLERS
// ======================================================

/**
 * Carrega a cena atual no viewer
 * @param {boolean} preserveView - Se deve manter a posição da câmera
 */
async function loadCurrentScene(preserveView = true) {
  const clientId = configLoader.clientId;
  const sceneId = configurator.sceneId;
  const selection = configurator.currentSelection;

  console.log(`[Main] Carregando cena: ${sceneId}`);

  try {
    // Solicita renderização ao backend
    const result = await renderService.renderCubemap(clientId, sceneId, selection);
    console.log('[Main] Render result:', result);

    // Carrega os tiles no viewer
    await viewerManager.loadScene(clientId, sceneId, result.build, preserveView);

  } catch (error) {
    console.error('[Main] Erro ao carregar cena:', error);
  }
}

/**
 * Handler para mudança de seleção (material)
 */
async function handleSelectionChange(selection) {
  console.log('[Main] Seleção alterada:', selection);
  
  // Atualiza o viewer mantendo a câmera
  await loadCurrentScene(true);
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
  
  // Carrega a nova cena (não preserva câmera pois é outra cena)
  await loadCurrentScene(false);
}

/**
 * Toggle do seletor de cenas
 */
function toggleSceneSelector() {
  sceneSelector.toggle();
}

/**
 * Handler para renderização 2D
 */
async function handleSave2Render() {
  const clientId = configLoader.clientId;
  const sceneId = configurator.sceneId;
  const selection = configurator.currentSelection;

  console.log('[Main] Solicitando render 2D...');

  // Mostra modal de loading
  showRenderModal('loading');

  try {
    const result = await renderService.render2D(clientId, sceneId, selection);
    console.log('[Main] Render 2D result:', result);

    // Mostra a imagem no modal
    if (result.url) {
      showRenderModal('success', result.url);
    }

  } catch (error) {
    console.error('[Main] Erro no render 2D:', error);
    showRenderModal('error', null, error.message);
  }
}

/**
 * Mostra o modal de renderização
 */
function showRenderModal(state, imageUrl = null, errorMessage = null) {
  // Remove modal existente se houver
  let modal = document.getElementById('render-modal');
  if (modal) {
    modal.remove();
  }

  // Cria o modal
  modal = document.createElement('div');
  modal.id = 'render-modal';
  modal.className = 'render-modal';

  const content = document.createElement('div');
  content.className = 'render-modal-content';

  // Header com botão fechar
  const header = document.createElement('div');
  header.className = 'render-modal-header';
  
  const title = document.createElement('h3');
  title.textContent = 'Renderização 2D';
  
  const closeBtn = document.createElement('button');
  closeBtn.className = 'render-modal-close';
  closeBtn.textContent = '×';
  closeBtn.onclick = () => modal.remove();
  
  header.append(title, closeBtn);
  content.appendChild(header);

  // Body
  const body = document.createElement('div');
  body.className = 'render-modal-body';

  if (state === 'loading') {
    body.innerHTML = '<div class="render-loading">Gerando imagem...</div>';
  } else if (state === 'success' && imageUrl) {
    const img = document.createElement('img');
    img.src = imageUrl;
    img.className = 'render-preview-image';
    img.alt = 'Renderização 2D';
    
    const downloadBtn = document.createElement('a');
    downloadBtn.href = imageUrl;
    downloadBtn.download = 'render-2d.jpg';
    downloadBtn.className = 'render-download-btn';
    downloadBtn.textContent = 'Download';
    
    body.append(img, downloadBtn);
  } else if (state === 'error') {
    body.innerHTML = `<div class="render-error">Erro: ${errorMessage || 'Falha na renderização'}</div>`;
  }

  content.appendChild(body);
  modal.appendChild(content);

  // Fecha ao clicar fora
  modal.onclick = (e) => {
    if (e.target === modal) modal.remove();
  };

  document.body.appendChild(modal);
}