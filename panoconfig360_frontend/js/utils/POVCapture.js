export function enablePOVCapture(view, container) {
  if (!container) {
    console.warn("sem container");
    return;
  }

  console.log("[POI Capture] pronto — clique e arraste");

  const handlePointerDown = (event) => {
    const rect = container.getBoundingClientRect();

    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    const coords = view.screenToCoordinates({ x, y });
    if (!coords) return;

    console.log("📍 POV:", {
      yaw: Number(coords.yaw.toFixed(5)),
      pitch: Number(coords.pitch.toFixed(5)),
    });
  };

  container.addEventListener("pointerdown", handlePointerDown);

  return () => container.removeEventListener("pointerdown", handlePointerDown);
}
