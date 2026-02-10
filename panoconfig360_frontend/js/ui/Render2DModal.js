/**
 * Render2DModal.js
 * Modal para exibir render 2D
 */

export class Render2DModal {
  constructor() {
    this._container = null;
    this._img = null;
    this._status = null;
    this._downloadBtn = null;
    this._createModal();
  }

  _createModal() {
    // Container principal
    this._container = document.createElement('div');
    this._container.className = 'render-modal';
    this._container.style.display = 'none';

    // Content wrapper
    const content = document.createElement('div');
    content.className = 'render-modal-content';

    // Header
    const header = document.createElement('div');
    header.className = 'render-modal-header';

    const title = document.createElement('h3');
    title.textContent = 'Render 2D';

    const closeBtn = document.createElement('button');
    closeBtn.className = 'render-modal-close';
    closeBtn.innerHTML = '×';
    closeBtn.title = 'Fechar';
    closeBtn.onclick = () => this.hide();

    header.appendChild(title);
    header.appendChild(closeBtn);

    // Body
    const body = document.createElement('div');
    body.className = 'render-modal-body';

    // Status (loading/error)
    this._status = document.createElement('div');
    this._status.className = 'render-loading';
    this._status.textContent = 'Gerando render da combinação...';

    // Imagem
    this._img = document.createElement('img');
    this._img.className = 'render-preview-image';
    this._img.style.display = 'none';

    // Botão download
    this._downloadBtn = document.createElement('a');
    this._downloadBtn.className = 'render-download-btn';
    this._downloadBtn.textContent = 'Download';
    this._downloadBtn.download = 'render-2d.jpg';
    this._downloadBtn.style.display = 'none';

    body.appendChild(this._status);
    body.appendChild(this._img);
    body.appendChild(this._downloadBtn);

    content.appendChild(header);
    content.appendChild(body);
    this._container.appendChild(content);
    document.body.appendChild(this._container);

    // Fecha ao clicar fora
    this._container.onclick = (e) => {
      if (e.target === this._container) {
        this.hide();
      }
    };
  }

  show() {
    this._container.style.display = 'flex';
  }

  hide() {
    this._container.style.display = 'none';
  }

  showLoading() {
    this.show();
    this._status.className = 'render-loading';
    this._status.textContent = 'Gerando render da combinação...';
    this._status.style.display = 'block';
    this._img.style.display = 'none';
    this._downloadBtn.style.display = 'none';
  }

  showImage(url) {
    this.show();
    this._status.style.display = 'none';
    this._img.src = url;
    this._img.style.display = 'block';
    this._downloadBtn.href = url;
    this._downloadBtn.style.display = 'inline-block';
  }

  showError(message) {
    this.show();
    this._status.className = 'render-error';
    this._status.textContent = message || 'Erro ao gerar render';
    this._status.style.display = 'block';
    this._img.style.display = 'none';
    this._downloadBtn.style.display = 'none';
  }
}