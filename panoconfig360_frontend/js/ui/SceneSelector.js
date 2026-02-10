/**
 * SceneSelector.js
 * Componente para seleção de cenas
 */

export class SceneSelector {
  constructor(containerId, onSceneChange) {
    this._onSceneChange = onSceneChange;
    this._scenes = [];
    this._activeSceneId = null;
    this._container = null;
    this._buttonsContainer = null;
    
    this._createContainer();
  }

  /**
   * Cria o container do seletor
   */
  _createContainer() {
    // Remove container existente se houver
    const existing = document.getElementById('scene-selector');
    if (existing) {
      existing.remove();
    }

    // Container principal
    this._container = document.createElement('div');
    this._container.id = 'scene-selector';
    this._container.className = 'scene-selector';

    // Header
    const header = document.createElement('div');
    header.className = 'scene-selector-header';

    const title = document.createElement('h3');
    title.textContent = 'Selecionar Cena';

    const closeBtn = document.createElement('button');
    closeBtn.className = 'scene-selector-close';
    closeBtn.innerHTML = '×';
    closeBtn.onclick = () => this.hide();

    header.appendChild(title);
    header.appendChild(closeBtn);

    // Container de botões
    this._buttonsContainer = document.createElement('div');
    this._buttonsContainer.id = 'scene-buttons';
    this._buttonsContainer.className = 'scene-buttons';

    this._container.appendChild(header);
    this._container.appendChild(this._buttonsContainer);
    document.body.appendChild(this._container);
  }

  /**
   * Renderiza os botões de cena
   */
  render(scenes, activeSceneId = null) {
    this._scenes = scenes;
    this._activeSceneId = activeSceneId || scenes[0]?.id;

    if (!this._buttonsContainer) return;

    this._buttonsContainer.innerHTML = '';

    scenes.forEach(scene => {
      const button = document.createElement('button');
      button.className = 'scene-button';
      button.textContent = scene.label;
      button.dataset.sceneId = scene.id;

      if (scene.id === this._activeSceneId) {
        button.classList.add('active');
      }

      button.onclick = () => this._handleSceneClick(scene.id);
      this._buttonsContainer.appendChild(button);
    });
  }

  /**
   * Manipula clique em cena
   */
  _handleSceneClick(sceneId) {
    if (sceneId === this._activeSceneId) {
      this.hide();
      return;
    }

    // Atualiza estado visual
    this._buttonsContainer.querySelectorAll('.scene-button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.sceneId === sceneId);
    });

    this._activeSceneId = sceneId;

    // Callback
    if (this._onSceneChange) {
      this._onSceneChange(sceneId);
    }
  }

  /**
   * Toggle visibilidade
   */
  toggle() {
    if (this._container.style.display === 'flex') {
      this.hide();
    } else {
      this.show();
    }
  }

  /**
   * Mostra o seletor
   */
  show() {
    if (this._container) {
      this._container.style.display = 'flex';
    }
  }

  /**
   * Esconde o seletor
   */
  hide() {
    if (this._container) {
      this._container.style.display = 'none';
    }
  }

  /**
   * Obtém a cena ativa
   */
  get activeSceneId() {
    return this._activeSceneId;
  }
}