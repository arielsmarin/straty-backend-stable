/**
 * SceneSelector.js
 * Componente para seleção de cenas
 */

export class SceneSelector {
  constructor(containerId, onSceneChange) {
    this._container = document.getElementById(containerId);
    this._onSceneChange = onSceneChange;
    this._scenes = [];
    this._activeSceneId = null;
    this._isVisible = false;
    
    this._init();
  }

  /**
   * Inicializa o container se não existir
   */
  _init() {
    if (!this._container) {
      // Cria o container
      this._container = document.createElement('div');
      this._container.id = 'scene-selector';
      this._container.className = 'scene-selector';
      document.body.appendChild(this._container);
    }
    
    this._container.style.display = 'none';
  }

  /**
   * Renderiza os botões de cena
   */
  render(scenes, activeSceneId = null) {
    this._scenes = scenes;
    this._activeSceneId = activeSceneId || scenes[0]?.id;

    this._container.innerHTML = '';

    // Header com título e botão fechar
    const header = document.createElement('div');
    header.className = 'scene-selector-header';
    
    const title = document.createElement('h3');
    title.textContent = 'Selecione a Cena';
    
    const closeBtn = document.createElement('button');
    closeBtn.className = 'scene-selector-close';
    closeBtn.textContent = '×';
    closeBtn.onclick = () => this.hide();
    
    header.append(title, closeBtn);
    this._container.appendChild(header);

    // Container dos botões
    const buttonsContainer = document.createElement('div');
    buttonsContainer.className = 'scene-buttons';

    scenes.forEach(scene => {
      const button = document.createElement('button');
      button.className = 'scene-button';
      button.textContent = scene.label;
      button.dataset.sceneId = scene.id;

      if (scene.id === this._activeSceneId) {
        button.classList.add('active');
      }

      button.onclick = () => this._handleSceneClick(scene.id);
      buttonsContainer.appendChild(button);
    });

    this._container.appendChild(buttonsContainer);
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
    this._container.querySelectorAll('.scene-button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.sceneId === sceneId);
    });

    this._activeSceneId = sceneId;

    // Callback
    if (this._onSceneChange) {
      this._onSceneChange(sceneId);
    }
  }

  /**
   * Mostra o seletor
   */
  show() {
    if (this._container) {
      this._container.style.display = 'flex';
      this._isVisible = true;
    }
  }

  /**
   * Esconde o seletor
   */
  hide() {
    if (this._container) {
      this._container.style.display = 'none';
      this._isVisible = false;
    }
  }

  /**
   * Toggle visibilidade
   */
  toggle() {
    if (this._isVisible) {
      this.hide();
    } else {
      this.show();
    }
  }

  /**
   * Obtém a cena ativa
   */
  get activeSceneId() {
    return this._activeSceneId;
  }

  /**
   * Verifica se está visível
   */
  get isVisible() {
    return this._isVisible;
  }
}