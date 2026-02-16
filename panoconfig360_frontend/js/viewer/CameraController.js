/**
 * CameraController.js
 * Controlador de câmera com animação suave entre POIs
 */

export const CAMERA_POIS = {
  //POV Gourmet
  gourmet_backsplash: { yaw: 3.3, pitch: 0.03 },
  gourmet_island: { yaw: -3.1, pitch: 0.16 },
  gourmet_table: { yaw: 0.03, pitch: 0.28 },
  gourmet_barbecue: { yaw: 2.83, pitch: -0.022 },
  gourmet_countertop: { yaw: 3.1, pitch: 0.1 },

  //POV Livingroom
  living_wall_panel: { yaw: 1.5, pitch: 0.1 },
  living_bed_panel: { yaw: 1.2, pitch: 0.3 },
  living_base_bed: { yaw: 1.1, pitch: 0.4 },
  living_floor: { yaw: 1, pitch: 0.75 },
  
  //POV Bathroom
  bath_countertop: { yaw: 2.35, pitch: 0.5 },
  bath_box: { yaw: 0, pitch: 0 },
  bath_floor: { yaw: 0.2, pitch: 1.1 },

  //POV Kitchen
  kitchen_backsplash: { yaw: -1.55, pitch: 0 },
  kitchen_island: { yaw: -1.55, pitch: 0.5 },
  kitchen_countertop: { yaw: -2.5, pitch: 0.2 },

  //POV Pool
  pool: { yaw: 0.5, pitch: 1.2 },
};

export function CreateCameraController(view) {
  console.log("[CameraController] Módulo carregado");

  let currentAnimation = null;

  const PITCH_MIN = -Math.PI / 2 + 0.1;
  const PITCH_MAX = Math.PI / 2 - 0.1;
  const FOV_MIN = (45 * Math.PI) / 180;
  const FOV_MAX = (90 * Math.PI) / 180;

  // Intercepta métodos do view para aplicar limites
  const originalSetPitch = view.setPitch.bind(view);
  view.setPitch = (pitch) => {
    originalSetPitch(clampPitch(pitch));
  };

  const originalSetFov = view.setFov.bind(view);
  view.setFov = (fov) => {
    originalSetFov(clampFov(fov));
  };

  function getState() {
    return {
      yaw: view.yaw(),
      pitch: view.pitch(),
      fov: view.fov(),
    };
  }

  function restore(state) {
    if (!state) return;
    view.setYaw(state.yaw);
    view.setPitch(state.pitch);
    view.setFov(state.fov);
  }

  function shortestAngleDifference(a, b) {
    let diff = b - a;
    while (diff > Math.PI) diff -= 2 * Math.PI;
    while (diff < -Math.PI) diff += 2 * Math.PI;
    return diff;
  }

  function clampPitch(pitch) {
    return Math.min(Math.max(pitch, PITCH_MIN), PITCH_MAX);
  }

  function clampFov(fov) {
    return Math.min(Math.max(fov, FOV_MIN), FOV_MAX);
  }

  function normalizeId(id) {
    return id?.toLowerCase().replace(/-/g, "_");
  }

  function focusOn(key) {
    const poi = CAMERA_POIS[normalizeId(key)];

    if (!poi) {
      console.warn(`[CameraController] POI "${key}" não encontrado.`);
      return;
    }

    const startYaw = view.yaw();
    const startPitch = view.pitch();
    const targetYaw = poi.yaw;
    const targetPitch = clampPitch(poi.pitch);

    const duration = 1200;
    const startTime = performance.now();

    if (currentAnimation) cancelAnimationFrame(currentAnimation);

    const yawDelta = shortestAngleDifference(startYaw, targetYaw);
    const pitchDelta = targetPitch - startPitch;

    function animate() {
      const now = performance.now();
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;

      const newYaw = startYaw + yawDelta * ease;
      const newPitch = clampPitch(startPitch + pitchDelta * ease);

      view.setYaw(newYaw);
      view.setPitch(newPitch);

      if (t < 1) currentAnimation = requestAnimationFrame(animate);
    }

    currentAnimation = requestAnimationFrame(animate);
  }

  view.addEventListener("change", () => {
    const state = {
      yaw: view.yaw(),
      pitch: view.pitch(),
      fov: view.fov(),
    };

    localStorage.setItem("pano-camera-state", JSON.stringify(state));
  });

  // Corrige FOV inicial
  view.setFov(FOV_MAX);

  return { focusOn, getState, restore };
}
