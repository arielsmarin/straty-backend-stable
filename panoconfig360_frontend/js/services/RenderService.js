export class RenderService {
  constructor(baseUrl = "") {
    this._baseUrl = baseUrl;
  }

  async renderCubemap(clientId, sceneId, selection, signal) {
    const response = await fetch(`${this._baseUrl}/api/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client: clientId, scene: sceneId, selection }),
      signal,
    });

    if (!response.ok) {
      if (response.status === 429) {
        throw new Error("Muitas requisições — aguarde um instante.");
      }

      const err = await response.json();
      throw new Error(err.detail || "Erro render");
    }

    return await response.json();
  }
}
