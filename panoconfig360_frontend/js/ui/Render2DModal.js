/**
 * Render2DModal.js
 * Modal completo com:
 * - Render 2D
 * - Especificações
 * - Contact Form
 * - Compartilhamento Social
 * - QR Code
 */

export class Render2DModal {
  constructor() {
    this._container = null;
    this._img = null;
    this._specificationsContainer = null;
    this._qrContainer = null;
    this._contactForm = null;
    this._shareLink = null;

    this._createModal();
  }

  /* ===============================
     CREATE MODAL
  =============================== */

  _createModal() {
    this._container = document.createElement("div");
    this._container.className = "render-modal";
    this._container.style.display = "none";

    const content = document.createElement("div");
    content.className = "render-modal-content";

    /* ================= HEADER ================= */

    const header = document.createElement("div");
    header.className = "render-modal-header";

    const title = document.createElement("h3");
    title.textContent = "Combinação Renderizada";

    const closeBtn = document.createElement("button");
    closeBtn.innerHTML = "×";
    closeBtn.onclick = () => this.hide();

    header.appendChild(title);
    header.appendChild(closeBtn);

    /* ================= BODY ================= */

    const body = document.createElement("div");
    body.className = "render-modal-body-grid";

    /* ===== LEFT - IMAGE ===== */

    const left = document.createElement("div");
    left.className = "render-column";

    this._img = document.createElement("img");
    this._img.className = "render-preview-image";

    left.appendChild(this._img);

    /* ===== CENTER - SPECIFICATIONS ===== */

    const center = document.createElement("div");
    center.className = "render-column";

    const specsTitle = document.createElement("h4");
    specsTitle.textContent = "Materiais escolhidos";

    this._specificationsContainer = document.createElement("div");
    this._specificationsContainer.className = "specifications-container";

    center.appendChild(specsTitle);
    center.appendChild(this._specificationsContainer);

    /* ===== RIGHT - CONTACT + SHARE ===== */

    const right = document.createElement("div");
    right.className = "render-column";

    const contactTitle = document.createElement("h4");
    contactTitle.textContent = "Contact Info";

    this._contactForm = this._createContactForm();

    const qrTitle = document.createElement("h4");
    qrTitle.textContent = "Scan QR Code";

    this._qrContainer = document.createElement("div");
    this._qrContainer.className = "qr-container";

    const shareButtons = this._createShareButtons();

    right.appendChild(contactTitle);
    right.appendChild(this._contactForm);
    right.appendChild(qrTitle);
    right.appendChild(this._qrContainer);
    right.appendChild(shareButtons);

    /* ================= APPEND ================= */

    body.appendChild(left);
    body.appendChild(center);
    body.appendChild(right);

    content.appendChild(header);
    content.appendChild(body);

    this._container.appendChild(content);
    document.body.appendChild(this._container);
  }

  /* ===============================
     CONTACT FORM
  =============================== */

  _createContactForm() {
    const form = document.createElement("form");
    form.className = "contact-form";

    const nameInput = document.createElement("input");
    nameInput.placeholder = "Name *";
    nameInput.required = true;

    const emailInput = document.createElement("input");
    emailInput.placeholder = "Email *";
    emailInput.type = "email";
    emailInput.required = true;

    const submitBtn = document.createElement("button");
    submitBtn.textContent = "Send";
    submitBtn.type = "submit";

    form.appendChild(nameInput);
    form.appendChild(emailInput);
    form.appendChild(submitBtn);

    form.onsubmit = (e) => {
      e.preventDefault();

      if (!this._shareLink) return;

      const subject = encodeURIComponent("Your Design");
      const body = encodeURIComponent(
        `Hello ${nameInput.value},\n\nHere is your design:\n${this._shareLink}`,
      );

      window.location.href = `mailto:${emailInput.value}?subject=${subject}&body=${body}`;
    };

    return form;
  }

  /* ===============================
     SHARE BUTTONS
  =============================== */

  _createShareButtons() {
    const container = document.createElement("div");
    container.className = "share-buttons";

    const createBtn = (label, getUrl) => {
      const btn = document.createElement("button");
      btn.textContent = label;
      btn.onclick = () => {
        if (!this._shareLink) return;
        window.open(getUrl(this._shareLink), "_blank");
      };
      return btn;
    };

    container.appendChild(
      createBtn(
        "WhatsApp",
        (link) => `https://wa.me/?text=${encodeURIComponent(link)}`,
      ),
    );

    container.appendChild(
      createBtn(
        "Twitter",
        (link) =>
          `https://twitter.com/intent/tweet?text=${encodeURIComponent(link)}`,
      ),
    );

    container.appendChild(
      createBtn(
        "Email",
        (link) => `mailto:?subject=My Design&body=${encodeURIComponent(link)}`,
      ),
    );

    return container;
  }

  /* ===============================
     SPECIFICATIONS RENDER
  =============================== */

  setSpecifications(specs) {
    this._specificationsContainer.innerHTML = "";

    specs.forEach((spec) => {
      const item = document.createElement("div");
      item.className = "spec-item";

      const icon = document.createElement("img");
      icon.src = spec.icon;
      icon.className = "spec-icon";

      const label = document.createElement("div");
      label.innerHTML = `<strong>${spec.category}</strong><br>${spec.name}`;

      item.appendChild(icon);
      item.appendChild(label);

      this._specificationsContainer.appendChild(item);
    });
  }

  /* ===============================
     QR CODE
  =============================== */

  generateQRCode(link) {
    this._qrContainer.innerHTML = "";

    if (!window.QRCode) {
      console.error("QRCode library not loaded");
      return;
    }

    new window.QRCode(this._qrContainer, {
      text: link,
      width: 150,
      height: 150,
    });
  }

  /* ===============================
     PUBLIC METHODS
  =============================== */

  show(imageUrl, specs, shareLink) {
    this._img.src = imageUrl;
    this._shareLink = shareLink;

    this.setSpecifications(specs);
    this.generateQRCode(shareLink);

    this._container.style.display = "flex";
  }

  hide() {
    this._container.style.display = "none";
  }

  /* ===============================
   COMPATIBILITY METHODS
=============================== */

  showLoading() {
    this._container.style.display = "flex";

    // Esconde conteúdo
    this._img.style.display = "none";
    this._specificationsContainer.style.display = "none";
    this._qrContainer.style.display = "none";

    // Mostra mensagem de loading
    if (!this._loadingMsg) {
      this._loadingMsg = document.createElement("div");
      this._loadingMsg.className = "render-loading";
      this._loadingMsg.textContent = "Gerando render da combinação...";
      this._container
        .querySelector(".render-column")
        .appendChild(this._loadingMsg);
    }

    this._loadingMsg.style.display = "block";
  }

  showImage(url, specs = null, shareLink = null) {
    this._container.style.display = "flex";

    // Esconde loading
    if (this._loadingMsg) {
      this._loadingMsg.style.display = "none";
    }

    // Mostra imagem
    this._img.src = url;
    this._img.style.display = "block";

    // Se não vier specs, não renderiza nada
    if (specs && specs.length) {
      this._specificationsContainer.style.display = "block";
      this.setSpecifications(specs);
    } else {
      this._specificationsContainer.style.display = "none";
    }

    // Se não vier shareLink, gera automaticamente
    if (!shareLink) {
      shareLink = window.location.href;
    }

    this._shareLink = shareLink;
    this._qrContainer.style.display = "block";
    this.generateQRCode(shareLink);
  }

  showError(message = "Erro ao gerar render") {
    this._container.style.display = "flex";

    if (this._loadingMsg) {
      this._loadingMsg.style.display = "none";
    }

    this._img.style.display = "none";
    this._specificationsContainer.style.display = "none";
    this._qrContainer.style.display = "none";

    if (!this._errorMsg) {
      this._errorMsg = document.createElement("div");
      this._errorMsg.className = "render-error";
      this._container
        .querySelector(".render-column")
        .appendChild(this._errorMsg);
    }

    this._errorMsg.textContent = message;
    this._errorMsg.style.display = "block";
  }
}
