/**
 * UIController.js
 * Controlador da interface de usuário (menus e submenus)
 */

export class UIController {
  constructor(configurator, callbacks = {}) {
    this._configurator = configurator;
    this._onSelectionChange = callbacks.onSelectionChange;
    this._onFocusRequest = callbacks.onFocusRequest;
    this._onSave2Render = callbacks.onSave2Render;
    this._onToggleSceneSelector = callbacks.onToggleSceneSelector;

    this._activeLayerId = null;

    this._menuContainer = document.getElementById("menu-elements");
    this._submenuContainer = document.getElementById("submenu-materials");
    this._save2RenderButton = document.getElementById("save-2render");

    this._submenuPreviewImg = null;
    this._submenuPreviewLabel = null;
    this._submenuTileList = null;

    this._createSceneToggleButton();
    this._bindSave2RenderButton();
  }

  /**
   * Cria botão para abrir seletor de cenas
   */
  _createSceneToggleButton() {
    const container = document.querySelector('.ui-container');
    if (!container) return;

    // Verifica se já existe
    if (document.getElementById('scene-toggle-btn')) return;

    const btn = document.createElement('button');
    btn.id = 'scene-toggle-btn';
    btn.className = 'scene-toggle-btn';
    btn.textContent = 'Trocar Cena';
    btn.onclick = () => {
      if (this._onToggleSceneSelector) {
        this._onToggleSceneSelector();
      }
    };

    // Insere no início do container
    container.insertBefore(btn, container.firstChild);
  }

  /**
   * Atualiza o configurator (ao trocar de cena)
   */
  setConfigurator(configurator) {
    this._configurator = configurator;
    this._activeLayerId = null;
    this.closeSubmenu();
    this.renderMainMenu();
  }

  /**
   * Renderiza o menu principal
   */
  renderMainMenu() {
    if (!this._menuContainer) return;
    
    this._menuContainer.innerHTML = "";

    const layers = this._configurator.layers;
    const selection = this._configurator.currentSelection;

    layers.forEach((layer) => {
      const selectedId = selection[layer.id];
      const selectedItem = layer.items.find((i) => i.id === selectedId);

      const card = document.createElement("div");
      card.className = "menu-item";
      card.onclick = () => {
        if (this._onFocusRequest) {
          this._onFocusRequest(layer.id);
        }
        this._toggleSubmenu(layer.id);
      };

      const thumb = document.createElement("img");
      thumb.className = "menu-item-thumbnail";
      thumb.src = selectedItem?.thumbnail || "";
      thumb.alt = selectedItem?.label || "";

      const text = document.createElement("div");
      text.className = "menu-item-text";

      const title = document.createElement("div");
      title.className = "menu-item-title";
      title.textContent = layer.label;

      const subtitle = document.createElement("div");
      subtitle.className = "menu-item-subtitle";
      subtitle.textContent = selectedItem?.label || "";

      const arrow = document.createElement("div");
      arrow.className = "menu-item-arrow";
      arrow.textContent = "›";

      text.append(title, subtitle);
      card.append(thumb, text, arrow);
      this._menuContainer.appendChild(card);
    });
  }

  /**
   * Toggle do submenu
   */
  _toggleSubmenu(layerId) {
    if (this._activeLayerId === layerId) {
      this.closeSubmenu();
      return;
    }

    this._activeLayerId = layerId;
    this._renderSubmenu();
  }

  /**
   * Fecha o submenu
   */
  closeSubmenu() {
    this._activeLayerId = null;
    
    if (this._submenuContainer) {
      this._submenuContainer.classList.remove("active");
      this._submenuContainer.innerHTML = "";
    }

    this._submenuPreviewImg = null;
    this._submenuPreviewLabel = null;
    this._submenuTileList = null;
  }

  /**
   * Renderiza o submenu
   */
  _renderSubmenu() {
    const layers = this._configurator.layers;
    const layer = layers.find((l) => l.id === this._activeLayerId);
    
    if (!layer || !this._submenuContainer) return;

    this._submenuContainer.classList.add("submenu-panel", "active");
    this._submenuContainer.innerHTML = "";

    // Header
    const header = document.createElement("div");
    header.className = "submenu-header";

    const back = document.createElement("div");
    back.className = "submenu-back";
    back.textContent = "‹";
    back.onclick = () => this.closeSubmenu();

    const title = document.createElement("div");
    title.className = "submenu-title";
    title.textContent = layer.label;

    header.append(back, title);
    this._submenuContainer.appendChild(header);

    // Body
    const body = document.createElement("div");
    body.className = "submenu-body";

    const selection = this._configurator.currentSelection;
    const selectedId = selection[layer.id];
    const selectedItem = layer.items.find((i) => i.id === selectedId);

    // Preview principal
    if (selectedItem) {
      const preview = document.createElement("div");
      preview.className = "submenu-main-preview";

      const img = document.createElement("img");
      img.src = selectedItem.thumbnail || "";
      img.alt = selectedItem.label;

      const label = document.createElement("div");
      label.className = "submenu-main-label";
      label.textContent = selectedItem.label;

      this._submenuPreviewImg = img;
      this._submenuPreviewLabel = label;

      preview.append(img, label);
      body.appendChild(preview);
    }

    // Lista de materiais
    const list = document.createElement("div");
    list.className = "tile-list";
    this._submenuTileList = list;

    layer.items.forEach((item) => {
      const isBase = item.file === null;

      const tile = document.createElement("div");
      tile.className = "tile";
      tile.dataset.itemId = item.id;

      if (item.id === selectedId) {
        tile.classList.add("active");
      }

      if (isBase) {
        tile.classList.add("tile-base");
      }

      const img = document.createElement("img");
      img.src = item.thumbnail || "";
      img.alt = item.label;

      const label = document.createElement("div");
      label.className = "tile-label";
      label.textContent = item.label;

      tile.onclick = () => {
        this._selectItem(layer.id, item.id);
      };

      tile.append(img, label);
      list.appendChild(tile);
    });

    body.appendChild(list);
    this._submenuContainer.appendChild(body);
  }

  /**
   * Seleciona um item
   */
  _selectItem(layerId, itemId) {
    this._configurator.updateSelection(layerId, itemId);

    const layers = this._configurator.layers;
    const layer = layers.find((l) => l.id === layerId);
    const item = layer?.items.find((i) => i.id === itemId);

    // Atualiza preview
    if (item && this._submenuPreviewImg && this._submenuPreviewLabel) {
      this._submenuPreviewImg.src = item.thumbnail || "";
      this._submenuPreviewImg.alt = item.label;
      this._submenuPreviewLabel.textContent = item.label;
    }

    // Atualiza estado ativo
    if (this._submenuTileList) {
      this._submenuTileList.querySelectorAll(".tile").forEach((tile) => {
        tile.classList.toggle("active", tile.dataset.itemId === itemId);
      });
    }

    this.renderMainMenu();
    
    if (this._onSelectionChange) {
      this._onSelectionChange(this._configurator.currentSelection);
    }
  }

  /**
   * Bind do botão de renderizar
   */
  _bindSave2RenderButton() {
    if (!this._save2RenderButton) return;

    this._save2RenderButton.onclick = () => {
      if (this._onSave2Render) {
        this._onSave2Render();
      }
    };
  }
}