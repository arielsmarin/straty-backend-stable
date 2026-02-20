# api/server.py
import os
import json
import logging
import shutil
import time
import tempfile
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from panoconfig360_backend.render.dynamic_stack import (
    _validate_config,
    build_string_from_selection,
)
from panoconfig360_backend.render.split_faces_cubemap import (
    process_cubemap,
    process_cubemap_to_memory,
    configure_pyvips_concurrency,
)
from panoconfig360_backend.models.render_2d import Render2DRequest
from panoconfig360_backend.storage.factory import (
    append_jsonl,
    exists,
    get_json,
    read_jsonl_slice,
    upload_file,
    get_public_url,
    upload_tiles_parallel,
)
from panoconfig360_backend.storage.tile_upload_queue import TileUploadQueue
from panoconfig360_backend.render.scene_context import resolve_scene_context
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from panoconfig360_backend.utils.build_validation import validate_build_string, validate_safe_id
from panoconfig360_backend.storage import storage_r2
from botocore.exceptions import ClientError
import re


logger = logging.getLogger(__name__)

# CONFIGURAÇÕES GLOBAIS
ROOT_DIR = Path(__file__).resolve().parents[1].parent
CLIENTS_ROOT = Path("panoconfig360_cache/clients")
LOCAL_CACHE_DIR = ROOT_DIR / "panoconfig360_cache"
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
CLIENT_CONFIG_BUCKET = os.getenv("R2_CONFIG_BUCKET", "panoconfig360")
TILE_RE = re.compile(r"^[0-9a-z]+_[fblrud]_\d+_\d+_\d+\.jpg$")
TILE_ROOT_RE = re.compile(
    r"^clients/[a-z0-9\-]+/cubemap/[a-z0-9\-]+/tiles/[0-9a-z]+$")

USE_MASK_STACK = True

if USE_MASK_STACK:
    from panoconfig360_backend.render.dynamic_stack_with_masks import stack_layers_image_only
else:
    from panoconfig360_backend.render.dynamic_stack import stack_layers_image_only

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

last_request_time = 0.0
lock = threading.Lock()
MIN_INTERVAL = 1.0
MAX_RENDER_LOCKS = 256
DEFAULT_TILES_TOTAL = 48
render_locks: OrderedDict[str, threading.Lock] = OrderedDict()
render_locks_guard = threading.Lock()
active_background_renders: set[str] = set()
active_background_guard = threading.Lock()
BUILD_STATUS: dict[str, dict] = {}
BUILD_LOCK = threading.Lock()
BUILD_STATUS_LOCK = BUILD_LOCK


def _get_render_lock(render_key: str) -> threading.Lock:
    with render_locks_guard:
        if render_key in render_locks:
            render_locks.move_to_end(render_key)
            return render_locks[render_key]
        new_lock = threading.Lock()
        render_locks[render_key] = new_lock
        while len(render_locks) > MAX_RENDER_LOCKS:
            render_locks.popitem(last=False)
        return new_lock


def _write_metadata_file(metadata_payload: dict, tmp_dir: str) -> str:
    meta_path = os.path.join(tmp_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f)
    return meta_path


def _tile_state_event_writer(tile_root: str, build_str: str):
    events_key = f"{tile_root}/tile_events.ndjson"

    def _writer(filename: str, state: str, lod: int):
        append_jsonl(
            events_key,
            {
                "filename": filename,
                "build": build_str,
                "state": state,
                "lod": lod,
                "ts": int(time.time() * 1000),
            },
        )

    return _writer


def _tiles_base_url() -> str:
    return get_public_url("").rstrip("/")


def _default_build_state() -> dict:
    return {
        "status": "processing",
        "tiles_uploaded": 0,
        "tiles_total": DEFAULT_TILES_TOTAL,
        "progress": 0.0,
        "percent_complete": 0.0,
        "faces_ready": False,
        "tiles_ready": False,
        "lod_ready": -1,
        "error": None,
    }


def _set_build_status(build: str, status: str, **extra):
    with BUILD_LOCK:
        current = dict(BUILD_STATUS.get(build, _default_build_state()))
        current.update({"status": status, **extra})
        if "progress" in current and "percent_complete" not in extra:
            current["percent_complete"] = current["progress"]
        BUILD_STATUS[build] = current


def _increment_build_tiles_uploaded(build: str):
    with BUILD_LOCK:
        current = dict(BUILD_STATUS.get(build, _default_build_state()))
        current["tiles_uploaded"] = current.get("tiles_uploaded", 0) + 1
        tiles_total = max(0, int(current.get("tiles_total", 0)))
        if tiles_total > 0:
            current["tiles_uploaded"] = min(current["tiles_uploaded"], tiles_total)
            current["progress"] = current["tiles_uploaded"] / tiles_total
            current["percent_complete"] = current["progress"]
        BUILD_STATUS[build] = current


_TILE_WORKERS = int(os.getenv("TILE_WORKERS", "4"))


def _render_build_background(
    client_id: str,
    scene_id: str,
    selection: dict,
    build_str: str,
    tile_root: str,
    metadata_key: str,
    min_lod: int = 0,
):
    render_key = f"{client_id}:{scene_id}:{build_str}"
    total_start = time.monotonic()
    _set_build_status(
        build_str,
        "processing",
        started_at=int(time.time()),
        tiles_uploaded=0,
        tiles_total=DEFAULT_TILES_TOTAL,
        progress=0.0,
        error=None,
    )

    try:
        project, _ = load_client_config(client_id)
        ctx = resolve_scene_context(project, scene_id)
        cpu_start = time.monotonic()
        stack_start = time.monotonic()
        stack_img = stack_layers_image_only(
            scene_id=scene_id,
            layers=ctx["layers"],
            selection=selection,
            assets_root=ctx["assets_root"],
        )
        logging.info("Tempo stack: %.2fs", time.monotonic() - stack_start)
        tiles_with_lod = process_cubemap_to_memory(
            stack_img,
            tile_size=512,
            build=build_str,
            min_lod=min_lod,
        )
        del stack_img
        cpu_elapsed = time.monotonic() - cpu_start
        logging.info("⏱️ Tempo render CPU (%s): %.2fs",
                     render_key, cpu_elapsed)

        tiles = [(f"{tile_root}/{filename}", tile_bytes)
                 for filename, tile_bytes, _ in tiles_with_lod]
        tiles_total = len(tiles)
        _set_build_status(
            build_str,
            "uploading",
            tile_root=tile_root,
            tiles_uploaded=0,
            tiles_total=tiles_total,
            progress=0.0,
            error=None,
        )
        upload_start = time.monotonic()
        upload_tiles_parallel(
            tiles,
            max_workers=25,
            on_tile_uploaded=lambda _: _increment_build_tiles_uploaded(build_str),
        )
        upload_elapsed = time.monotonic() - upload_start
        logging.info("⏱️ Tempo upload total (%s): %.2fs",
                     render_key, upload_elapsed)

        metadata_payload = {
            "client": client_id,
            "scene": scene_id,
            "build": build_str,
            "tileRoot": tile_root,
            "generated_at": int(time.time()),
            "status": "ready",
            "tiles_count": len(tiles),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(metadata_payload, tmp)
            tmp_path = tmp.name
        try:
            upload_file(tmp_path, metadata_key, "application/json")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        _set_build_status(
            build_str,
            "completed",
            tile_root=tile_root,
            completed_at=int(time.time()),
            faces_ready=True,
            tiles_ready=True,
            lod_ready=1,
            tiles_count=tiles_total,
            tiles_uploaded=tiles_total,
            tiles_total=tiles_total,
            progress=1.0,
            percent_complete=1.0,
            error=None,
        )
    except Exception as exc:
        logging.exception(
            "❌ Falha no pipeline em background para %s", render_key)
        _set_build_status(build_str, "error", error=str(
            exc), failed_at=int(time.time()))
    finally:
        total_elapsed = time.monotonic() - total_start
        logging.info("⏱️ Tempo total pipeline (%s): %.2fs",
                     render_key, total_elapsed)
        with active_background_guard:
            active_background_renders.discard(render_key)


def _render_remaining_lods(
    client_id: str,
    scene_id: str,
    selection: dict,
    build_str: str,
    tile_root: str,
    metadata_key: str,
    stack_img=None,
):
    render_key = f"{client_id}:{scene_id}:{build_str}"

    try:
        start = time.monotonic()
        logging.info("🧵 Background LOD render iniciado para %s", render_key)

        # Reuse the stacked image if provided; otherwise re-stack
        if stack_img is None:
            project, _ = load_client_config(client_id)
            ctx = resolve_scene_context(project, scene_id)

        tmp_dir = tempfile.mkdtemp(prefix=f"{build_str}_bg_")
        uploader = None
        try:
            uploader = TileUploadQueue(
                tile_root=tile_root,
                upload_fn=upload_file,
                workers=4,
                on_state_change=_tile_state_event_writer(tile_root, build_str),
            )
            uploader.start()

            stack_img = stack_layers_image_only(
                scene_id=scene_id,
                layers=ctx["layers"],
                selection=selection,
                assets_root=ctx["assets_root"],
            )

            process_cubemap(
                stack_img,
                tmp_dir,
                tile_size=512,
                build=build_str,
                min_lod=1,
                on_tile_ready=uploader.enqueue,
            )
            del stack_img
            uploader.close_and_wait()
            uploaded_count = uploader.uploaded_count
            metadata_payload = {
                "client": client_id,
                "scene": scene_id,
                "build": build_str,
                "tileRoot": tile_root,
                "generated_at": int(time.time()),
                "status": "ready",
                "last_stage": "background_lods_done",
                "background_tiles_count": uploaded_count,
                "tile_state_counts": {
                    "generated": 0,
                    "uploading": 0,
                    "uploaded": 0,
                    "fading-in": 0,
                    "visible": len(uploader.states),
                },
            }
            meta_path = _write_metadata_file(metadata_payload, tmp_dir)
            upload_file(meta_path, metadata_key, "application/json")
            logging.info(
                "✅ Background LOD render finalizado para %s com %s tiles.",
                render_key,
                uploaded_count,
            )
        finally:
            if uploader is not None:
                try:
                    uploader.close_and_wait()
                except Exception:
                    logging.exception(
                        "❌ Erro ao encerrar fila de upload em background (%s)", render_key)
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        logging.exception(
            "❌ Falha na geração de LODs em background para %s", render_key)
    finally:
        with active_background_guard:
            active_background_renders.discard(render_key)
        elapsed = time.monotonic() - start
        logging.info(
            "⏱️ Background LOD render de %s terminou em %.2fs", render_key, elapsed)


def load_client_config(client_id: str):
    validate_safe_id(client_id, "client_id")
    key = f"clients/{client_id}/{client_id}_cfg.json"
    logger.info("Loading client config from R2: %s", key)

    s3_client = storage_r2.s3_client
    if s3_client is None:
        raise RuntimeError("R2 client not initialized")

    try:
        response = s3_client.get_object(
            Bucket=CLIENT_CONFIG_BUCKET,
            Key=key,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            logger.error("Client config not found in R2: %s", key)
            raise ValueError(
                f"Configuração do cliente '{client_id}' não encontrada no R2 ({key})"
            ) from exc
        raise

    data = response["Body"].read()

    try:
        project = json.loads(data)
    except json.JSONDecodeError as e:
        logging.error(
            "❌ Config JSON inválido para client '%s': %s", client_id, e)
        raise ValueError(
            f"Configuração do cliente '{client_id}' contém JSON inválido: {e}")

    try:
        _validate_config(project)
    except ValueError as exc:
        raise ValueError(
            f"Configuração inválida para cliente '{client_id}': {exc}"
        ) from exc

    scenes = project.get("scenes")
    if not scenes:
        scenes = {
            "default": {
                "scene_index": 0,
                "layers": project.get("layers", []),
                "base_image": project.get("base_image"),
            }
        }
    naming = project.get("naming", {})

    if not scenes:
        logging.error(
            "❌ Config do client '%s' não possui scenes definidas", client_id)
        raise ValueError(
            f"Configuração do cliente '{client_id}' não possui scenes definidas")

    project["scenes"] = scenes
    project["client_id"] = client_id

    return project, naming


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Iniciando backend STRATY")
    os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
    # Must run at startup so libvips reads VIPS_CONCURRENCY before render operations.
    configure_pyvips_concurrency()
    yield
    logging.info("🧹 Encerrando backend STRATY")


app = FastAPI(lifespan=lifespan)

# CORS middleware
# Render env var (sem espaços):
# CORS_ORIGINS=https://stratyconfig.pages.dev,http://127.0.0.1:5500,http://localhost:5500
raw_origins = os.getenv("CORS_ORIGINS", "")
origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

if not origins:
    logger.warning(
        "CORS_ORIGINS está vazio; nenhuma origem estará autorizada para CORS."
    )

logger.info("CORS allowed origins: %s", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/render", response_model=None)
def render_cubemap(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    request: Request = None
):
    origin = request.headers.get("origin") if request else None
    logging.info(f"🌐 Requisição recebida de origem: {origin}")

    # ======================================================
    # ⏱️ RATE LIMIT
    # ======================================================
    now = time.monotonic()
    with lock:
        global last_request_time
        if now - last_request_time < MIN_INTERVAL:
            raise HTTPException(
                status_code=429,
                detail="Muitas requisições — aguarde um instante."
            )
        last_request_time = now

    # ======================================================
    # ✅ VALIDAÇÕES
    # ======================================================
    client_id = payload.get("client")
    scene_id = payload.get("scene")
    selection = payload.get("selection")

    if not client_id:
        raise HTTPException(400, "client ausente no payload")
    if not scene_id:
        raise HTTPException(400, "scene ausente no payload")
    if not selection or not isinstance(selection, dict):
        raise HTTPException(400, "selection ausente ou inválida")

    client_id = validate_safe_id(client_id, "client")
    scene_id = validate_safe_id(scene_id, "scene")

    # ======================================================
    # 📦 CARREGA CONFIG
    # ======================================================
    try:
        project, _ = load_client_config(client_id)
    except FileNotFoundError as e:
        logging.warning("❌ Config não encontrado: %s", e)
        raise HTTPException(
            404, f"Config não encontrado para cliente '{client_id}'.")
    except ValueError as e:
        logging.warning("❌ Config inválido: %s", e)
        raise HTTPException(
            422, f"Config inválido para cliente '{client_id}'.")
        logging.error(
            "❌ Config não encontrada para client '%s': %s", client_id, e)
        raise HTTPException(
            404, f"Configuração do cliente não encontrada: {e}")
    except ValueError as e:
        logging.error("❌ Config inválida para client '%s': %s", client_id, e)
        raise HTTPException(400, f"Configuração do cliente inválida: {e}")
    except Exception as e:
        logging.exception(
            "❌ Falha inesperada ao carregar config do client '%s'", client_id)
        raise HTTPException(500, "Erro interno ao carregar configuração")

    # ======================================================
    # 🎬 RESOLVE CENA
    # ======================================================
    try:
        ctx = resolve_scene_context(project, scene_id)
    except Exception as e:
        logging.exception("❌ Cena inválida")
        raise HTTPException(400, f"Cena inválida: {e}")

    scene_layers = ctx["layers"]
    assets_root = ctx["assets_root"]
    scene_index = ctx["scene_index"]

    # ======================================================
    # 🧮 BUILD STRING (SEM PROCESSAR IMAGEM)
    # ======================================================

    build_str = build_string_from_selection(
        scene_index, scene_layers, selection)

    logging.info(f"🔑 Build string: {build_str} ({len(build_str)} chars)")

    # ======================================================
    # 🔍 VERIFICA CACHE
    # ======================================================
    tile_root = f"clients/{client_id}/cubemap/{scene_id}/tiles/{build_str}"
    metadata_key = f"{tile_root}/metadata.json"
    render_key = f"{client_id}:{scene_id}:{build_str}"

    cache_exists = exists(metadata_key)
    logging.info(f"🔍 Cache check: {metadata_key} → exists={cache_exists}")

    if cache_exists:
        logging.info(f"✅ Cache hit: {build_str}")

        tiles = {
            "baseUrl": _tiles_base_url(),
            "tileRoot": tile_root,
            "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
            "build": build_str,
        }

        return {
            "status": "cached",
            "build": build_str,
            "tiles": tiles,
        }

    # ======================================================
    # 🏗️ CACHE MISS: AGENDA PROCESSAMENTO EM BACKGROUND E RETORNA 202
    # ======================================================
    render_lock = _get_render_lock(render_key)
    with render_lock:
        if exists(metadata_key):
            tiles = {
                "baseUrl": _tiles_base_url(),
                "tileRoot": tile_root,
                "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
                "build": build_str,
            }
            return {
                "status": "cached",
                "build": build_str,
                "tiles": tiles,
            }

        with active_background_guard:
            already_processing = render_key in active_background_renders
            if not already_processing:
                active_background_renders.add(render_key)
                _set_build_status(
                    build_str,
                    "processing",
                    tile_root=tile_root,
                    tiles_uploaded=0,
                    tiles_total=DEFAULT_TILES_TOTAL,
                    progress=0.0,
                    percent_complete=0.0,
                    faces_ready=False,
                    tiles_ready=False,
                    lod_ready=-1,
                    error=None,
                )
                min_lod_for_background = 0
                try:
                    stack_img = stack_layers_image_only(
                        scene_id=scene_id,
                        layers=scene_layers,
                        selection=selection,
                        assets_root=assets_root,
                    )
                    lod0_tiles_with_lod = process_cubemap_to_memory(
                        stack_img,
                        tile_size=512,
                        build=build_str,
                        min_lod=0,
                        max_lod=0,
                    )
                    del stack_img
                    lod0_tiles = [
                        (f"{tile_root}/{filename}", tile_bytes)
                        for filename, tile_bytes, _ in lod0_tiles_with_lod
                    ]
                    lod0_total = len(lod0_tiles)
                    if lod0_total > 0:
                        _set_build_status(
                            build_str,
                            "uploading",
                            tile_root=tile_root,
                            tiles_uploaded=0,
                            tiles_total=max(DEFAULT_TILES_TOTAL, lod0_total),
                            progress=0.0,
                            percent_complete=0.0,
                            faces_ready=False,
                            tiles_ready=False,
                            lod_ready=-1,
                            error=None,
                        )
                        upload_tiles_parallel(
                            lod0_tiles,
                            max_workers=8,
                            on_tile_uploaded=lambda _: _increment_build_tiles_uploaded(build_str),
                        )
                        _set_build_status(
                            build_str,
                            "processing",
                            tile_root=tile_root,
                            faces_ready=True,
                            tiles_ready=True,
                            lod_ready=0,
                            error=None,
                        )
                        min_lod_for_background = 1
                except Exception:
                    logging.exception("⚠️ Falha no upload síncrono de LOD0 para %s", render_key)
                    _set_build_status(
                        build_str,
                        "processing",
                        tile_root=tile_root,
                        faces_ready=False,
                        tiles_ready=False,
                        lod_ready=-1,
                        error="lod0_sync_failed",
                    )
                background_tasks.add_task(
                    _render_build_background,
                    client_id,
                    scene_id,
                    selection,
                    build_str,
                    tile_root,
                    metadata_key,
                    min_lod_for_background,
                )
                logging.info("🧵 Background task agendada para %s", render_key)

    tiles = {
        "baseUrl": _tiles_base_url(),
        "tileRoot": tile_root,
        "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
        "build": build_str,
    }
    return JSONResponse(
        status_code=202,
        content={"status": "processing", "build": build_str, "tiles": tiles},
    )


@app.get("/api/render/events")
def render_tile_events(tile_root: str, cursor: int = 0, limit: int = 200):
    if not TILE_ROOT_RE.match(tile_root):
        raise HTTPException(status_code=400, detail="tile_root inválido")

    if cursor < 0:
        raise HTTPException(status_code=400, detail="cursor inválido")

    limit = max(1, min(limit, 500))
    events_key = f"{tile_root}/tile_events.ndjson"
    events, next_cursor = read_jsonl_slice(
        events_key, cursor=cursor, limit=limit)

    # Check if render is complete by reading metadata status
    metadata_key = f"{tile_root}/metadata.json"
    completed = False
    try:
        metadata = get_json(metadata_key)
        completed = metadata.get("status") == "ready"
    except FileNotFoundError:
        completed = False
    except (json.JSONDecodeError, IOError) as e:
        logging.warning(
            "⚠️ Failed to read metadata for completion check: %s", e)
        completed = False

    return {
        "status": "success",
        "data": {
            "events": events,
            "cursor": next_cursor,
            "hasMore": len(events) >= limit,
            "completed": completed,
        },
    }


@app.get("/api/status/{build}")
def render_status(build: str, client: str = "", scene: str = ""):
    build_str = None
    tile_root = None
    metadata_key = None

    try:
        build_str = validate_build_string(build)
    except HTTPException:
        return {"status": "idle"}

    try:
        if client and scene:
            client_id = validate_safe_id(client, "client")
            scene_id = validate_safe_id(scene, "scene")
            tile_root = f"clients/{client_id}/cubemap/{scene_id}/tiles/{build_str}"
            metadata_key = f"{tile_root}/metadata.json"
    except HTTPException:
        metadata_key = None

    if metadata_key is not None:
        try:
            metadata = get_json(metadata_key)
            if metadata.get("status") == "ready":
                _set_build_status(build_str, "completed", tile_root=tile_root, progress=1.0)
        except FileNotFoundError:
            pass
        except Exception:
            logging.exception(
                "❌ Falha ao consultar metadata para status (%s)", build_str)
            _set_build_status(build_str, "error", error="metadata_read_error")

    with BUILD_LOCK:
        state = dict(BUILD_STATUS.get(build_str, {}))

    if not state:
        return {"status": "idle"}

    status = state.get("status", "idle")
    status_map = {"done": "completed", "failed": "error"}
    response = {"build": build_str, "status": status_map.get(status, status)}

    for key in ("tiles_uploaded", "tiles_total", "progress", "percent_complete", "faces_ready", "tiles_ready", "lod_ready"):
        if key in state:
            response[key] = state[key]
    if state.get("error") is not None:
        response["error"] = state.get("error")
    return response


# RENDER 2D SIMPLES (SEM CACHE DE TILES, APENAS IMAGEM FINAL)

@app.post("/api/render2d")
def render_2d(payload: Render2DRequest):
    client_id = validate_safe_id(payload.client, "client")
    scene_id = validate_safe_id(payload.scene, "scene")
    selection = payload.selection

    logging.info(f"🖼️ Render 2D: client={client_id}, scene={scene_id}")

    try:
        project, _ = load_client_config(client_id)
    except FileNotFoundError as e:
        logging.warning("❌ Config não encontrado: %s", e)
        raise HTTPException(
            404, f"Config não encontrado para cliente '{client_id}'.")
    except ValueError as e:
        logging.warning("❌ Config inválido: %s", e)
        raise HTTPException(
            422, f"Config inválido para cliente '{client_id}'.")
        logging.error(
            "❌ Config não encontrada para client '%s': %s", client_id, e)
        raise HTTPException(
            404, f"Configuração do cliente não encontrada: {e}")
    except ValueError as e:
        logging.error("❌ Config inválida para client '%s': %s", client_id, e)
        raise HTTPException(400, f"Configuração do cliente inválida: {e}")
    except Exception as e:
        logging.exception(
            "❌ Falha inesperada ao carregar config do client '%s'", client_id)
        raise HTTPException(500, "Erro interno ao carregar configuração")

    try:
        ctx = resolve_scene_context(project, scene_id)
    except Exception as e:
        logging.exception("❌ Cena inválida")
        raise HTTPException(400, f"Cena inválida: {e}")

    scene_layers = ctx["layers"]
    assets_root = ctx["assets_root"]
    scene_index = ctx["scene_index"]

    build_str = build_string_from_selection(
        scene_index, scene_layers, selection)

    logging.info(f"🔑 Build string 2D: {build_str} ({len(build_str)} chars)")

    cdn_key = f"clients/{client_id}/renders/{scene_id}/2d_{build_str}.jpg"

    cache_exists = exists(cdn_key)
    logging.info(f"🔍 Cache 2D check: {cdn_key} → exists={cache_exists}")

    if cache_exists:
        logging.info(f"✅ Cache 2D hit: {build_str}")
        return {
            "status": "cached",
            "client": client_id,
            "scene": scene_id,
            "build": build_str,
            "url": get_public_url(cdn_key),
        }

    # 🏗️ PROCESSA IMAGEM 2D (USANDO STACK COM MASKS)

    logging.info("🏗️ Cache 2D miss — iniciando processamento...")

    start = time.monotonic()

    output_path = None

    try:
        img = stack_layers_image_only(
            scene_id=scene_id,
            layers=scene_layers,
            selection=selection,
            assets_root=assets_root,
            asset_prefix="2d_",
        )

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            output_path = tmp.name

        img.save(output_path, "JPEG", quality=80, subsampling=0)
        upload_file(output_path, cdn_key, "image/jpeg")

        return {
            "status": "generated",
            "client": client_id,
            "scene": scene_id,
            "build": build_str,
            "url": get_public_url(cdn_key),
        }

    except FileNotFoundError as e:
        logging.error("❌ Asset não encontrado no render 2D: %s", e)
        raise HTTPException(
            status_code=404,
            detail=f"Asset não encontrado: {e}",
        )

    except Exception as e:
        logging.exception("❌ Erro inesperado no render 2D")
        raise HTTPException(
            status_code=500,
            detail="Erro interno no render 2D",
        )

    finally:
        if output_path is not None and os.path.exists(output_path):
            os.remove(output_path)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "panoconfig360-backend", "version": "0.0.1"}


@app.get("/panoconfig360_cache/cubemap/{client_id}/{scene_id}/tiles/{build}/{filename}")
def get_tile(client_id: str, scene_id: str, build: str, filename: str):

    # valida IDs para prevenir path traversal
    client_id = validate_safe_id(client_id, "client_id")
    scene_id = validate_safe_id(scene_id, "scene_id")

    # valida build
    build = validate_build_string(build)

    # valida filename estritamente
    if not TILE_RE.match(filename):
        raise HTTPException(400, "Tile inválido")

    # filename deve começar com build correto
    if not filename.startswith(build + "_"):
        raise HTTPException(400, "Tile não pertence à build")

    # caminho isolado por tenant e cena
    tile_path = (
        LOCAL_CACHE_DIR
        / "clients"
        / client_id
        / "cubemap"
        / scene_id
        / "tiles"
        / build
        / filename
    )

    if not tile_path.exists():
        raise HTTPException(404, "Tile não encontrado")

    return FileResponse(
        tile_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
