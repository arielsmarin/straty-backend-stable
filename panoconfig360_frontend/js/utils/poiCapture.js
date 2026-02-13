export function enablePoiCapture(view, container) {
  const canvas = container.querySelector(".marzipano-canvas");

  if (!canvas) {
    console.warn("[POI Capture] canvas não encontrado");
    return;
  }

  function handleClick(e) {
    const rect = canvas.getBoundingClientRect();

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const coords = view.screenToCoordinates({ x, y });
    if (!coords) return;

    const yaw = Number(coords.yaw.toFixed(4));
    const pitch = Number(coords.pitch.toFixed(4));

    console.log(`🧭 yaw:${yaw} pitch:${pitch}`);
    console.log(`→ { yaw: ${yaw}, pitch: ${pitch} }`);
  }

  canvas.addEventListener("click", handleClick);

  console.log("[POI Capture] pronto para capturar coordenadas");

  return () => canvas.removeEventListener("click", handleClick);
}
