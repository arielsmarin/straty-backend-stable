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

  /**
   * Fetch the current build status from /api/status/{buildId}.
   * Returns { status: "processing"|"completed"|"unknown", lod_ready: number }
   */
  async fetchBuildStatus(buildId, signal) {
    const response = await fetch(`${this._baseUrl}/api/status/${buildId}`, {
      signal,
    });
    if (!response.ok) {
      throw new Error(`Status request failed: ${response.status}`);
    }
    return await response.json();
  }

  /**
   * Poll /api/status/{buildId} until lod_ready >= requiredLod or status == "completed".
   * Uses exponential backoff: 1s → 2s → 4s → 8s → 10s (max).
   * Returns the final status object.
   */
  async waitForLod(buildId, requiredLod, signal) {
    let delay = 1000;
    const maxDelay = 10000;

    while (true) {
      if (signal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }

      try {
        const status = await this.fetchBuildStatus(buildId, signal);
        if (
          status.status === "completed" ||
          (typeof status.lod_ready === "number" && status.lod_ready >= requiredLod)
        ) {
          return status;
        }
      } catch (err) {
        if (err.name === "AbortError") throw err;
        // ignore transient errors, retry
      }

      await new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, delay);
        if (signal) {
          signal.addEventListener("abort", () => {
            clearTimeout(timer);
            reject(new DOMException("Aborted", "AbortError"));
          }, { once: true });
        }
      });

      delay = Math.min(delay * 2, maxDelay);
    }
  }

  async render2D(clientId, sceneId, selection) {
    const response = await fetch("/api/render2d", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        client: clientId,
        scene: sceneId,
        selection: selection,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || "Erro no render 2D");
    }

    return await response.json();
  }
}
