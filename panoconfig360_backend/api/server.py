# api/server.py
import os
import json
import logging
import shutil
import time
import tempfile
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Body, BackgroundTasks
from panoconfig360_backend.render.dynamic_stack import (
    load_config,
    build_string_from_selection,
    encode_index,
)
from panoconfig360_backend.render.split_faces_cubemap import process_cubemap
from panoconfig360_backend.render.stack_2d import render_stack_2d
from panoconfig360_backend.models.render_2d import Render2DRequest
from panoconfig360_backend.storage.storage_local import exists, upload_file
from panoconfig360_backend.render.scene_context import resolve_scene_context
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from panoconfig360_backend.utils.build_validation import validate_build_string
import re


# CONFIGURAÇÕES GLOBAIS
ROOT_DIR = Path(__file__).resolve().parents[1].parent
CLIENTS_ROOT = Path("panoconfig360_cache/clients")
LOCAL_CACHE_DIR = ROOT_DIR / "panoconfig360_cache"
FRONTEND_DIR = ROOT_DIR / "panoconfig360_frontend"
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
TILE_RE = re.compile(r"^[0-9a-z]+_[tblr]_\d+_\d+_\d+\.jpg$")

USE_MASK_STACK = True

if USE_MASK_STACK:
    from panoconfig360_backend.render.dynamic_stack_with_masks import stack_layers_image_only
else:
    from panoconfig360_backend.render.dynamic_stack import stack_layers_image_only

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

last_request_time = 0.0
lock = threading.Lock()
MIN_INTERVAL = 1.0
render_locks: dict[str, threading.Lock] = {}
render_locks_guard = threading.Lock()
active_background_renders: set[str] = set()
active_background_guard = threading.Lock()


def _get_render_lock(render_key: str) -> threading.Lock:
    with render_locks_guard:
        if render_key not in render_locks:
            render_locks[render_key] = threading.Lock()
        return render_locks[render_key]


def _upload_jpg_tiles(tmp_dir: str, tile_root: str) -> int:
    uploaded_count = 0

    for filename in os.listdir(tmp_dir):
        if not filename.lower().endswith(".jpg"):
            continue

        file_path = os.path.join(tmp_dir, filename)
        key = f"{tile_root}/{filename}"
        upload_file(file_path, key, "image/jpeg")
        uploaded_count += 1

    return uploaded_count


def _write_metadata_file(metadata_payload: dict, tmp_dir: str) -> str:
    meta_path = os.path.join(tmp_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f)
    return meta_path


def _render_remaining_lods(
    client_id: str,
    scene_id: str,
    selection: dict,
    build_str: str,
    tile_root: str,
    metadata_key: str,
):
    render_key = f"{client_id}:{scene_id}:{build_str}"

    try:
        start = time.monotonic()
        logging.info("🧵 Background LOD render iniciado para %s", render_key)

        project, _ = load_client_config(client_id)
        ctx = resolve_scene_context(project, scene_id)

        tmp_dir = tempfile.mkdtemp(prefix=f"{build_str}_bg_")
        try:
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
            )
            del stack_img

            uploaded_count = _upload_jpg_tiles(tmp_dir, tile_root)
            metadata_payload = {
                "client": client_id,
                "scene": scene_id,
                "build": build_str,
                "tileRoot": tile_root,
                "generated_at": int(time.time()),
                "status": "ready",
                "last_stage": "background_lods_done",
                "background_tiles_count": uploaded_count,
            }
            meta_path = _write_metadata_file(metadata_payload, tmp_dir)
            upload_file(meta_path, metadata_key, "application/json")
            logging.info(
                "✅ Background LOD render finalizado para %s com %s tiles.",
                render_key,
                uploaded_count,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        logging.exception("❌ Falha na geração de LODs em background para %s", render_key)
    finally:
        with active_background_guard:
            active_background_renders.discard(render_key)
        elapsed = time.monotonic() - start
        logging.info("⏱️ Background LOD render de %s terminou em %.2fs", render_key, elapsed)


def load_client_config(client_id: str):
    config_path = LOCAL_CACHE_DIR / "clients" / \
        client_id / f"{client_id}_cfg.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuração do cliente '{client_id}' não encontrada em {config_path}.")

    project, scenes, naming = load_config(config_path)
    project["scenes"] = scenes
    project["client_id"] = client_id

    return project, naming


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Iniciando backend STRATY")
    os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
    yield
    logging.info("🧹 Encerrando backend STRATY")


app = FastAPI(lifespan=lifespan)

app.mount("/panoconfig360_cache",
          StaticFiles(directory=LOCAL_CACHE_DIR), name="panoconfig360_cache")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


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

    # ======================================================
    # 📦 CARREGA CONFIG
    # ======================================================
    try:
        project, _ = load_client_config(client_id)
    except Exception as e:
        logging.exception("❌ Falha ao carregar config")
        raise HTTPException(500, f"Erro ao carregar config: {e}")

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
            "baseUrl": "/panoconfig360_cache",
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
    # 🏗️ PROCESSA IMAGEM (SÓ SE NÃO TEM CACHE) - FASE 1 (LOD 0)
    # ======================================================
    render_lock = _get_render_lock(render_key)
    with render_lock:
        if exists(metadata_key):
            tiles = {
                "baseUrl": "/panoconfig360_cache",
                "tileRoot": tile_root,
                "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
                "build": build_str,
            }
            return {
                "status": "cached",
                "build": build_str,
                "tiles": tiles,
            }

        logging.info("🏗️ Cache miss — iniciando processamento LOD0 para %s", render_key)
        start = time.monotonic()
        tmp_dir = tempfile.mkdtemp(prefix=f"{build_str}_lod0_")
        logging.info(f"📁 Temp dir: {tmp_dir}")

        try:
            stack_img = stack_layers_image_only(
                scene_id=scene_id,
                layers=scene_layers,
                selection=selection,
                assets_root=assets_root,
            )

            process_cubemap(
                stack_img,
                tmp_dir,
                tile_size=512,
                build=build_str,
                max_lod=0,
            )
            del stack_img

            lod0_uploaded = _upload_jpg_tiles(tmp_dir, tile_root)
            metadata_payload = {
                "client": client_id,
                "scene": scene_id,
                "build": build_str,
                "tileRoot": tile_root,
                "generated_at": int(time.time()),
                "status": "processing",
                "last_stage": "lod0_ready",
                "lod0_tiles_count": lod0_uploaded,
            }
            meta_path = _write_metadata_file(metadata_payload, tmp_dir)
            upload_file(meta_path, metadata_key, "application/json")

            elapsed = time.monotonic() - start
            logging.info("✅ LOD0 pronto para %s em %.2fs (%s tiles)", render_key, elapsed, lod0_uploaded)
        except Exception as e:
            logging.exception("❌ Erro no render LOD0")
            raise HTTPException(500, f"Erro interno: {e}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logging.info(f"🧹 Temp removido: {tmp_dir}")

    with active_background_guard:
        if render_key not in active_background_renders:
            background_tasks.add_task(
                _render_remaining_lods,
                client_id,
                scene_id,
                selection,
                build_str,
                tile_root,
                metadata_key,
            )
            active_background_renders.add(render_key)
            logging.info("🧵 Background task agendada para LODs > 0 (%s)", render_key)

    tiles = {
        "baseUrl": "/panoconfig360_cache",
        "tileRoot": tile_root,
        "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
        "build": build_str,
    }

    return {
        "status": "generated",
        "client": client_id,
        "scene": scene_id,
        "build": build_str,
        "tiles": tiles,
    }


# RENDER 2D SIMPLES (SEM CACHE DE TILES, APENAS IMAGEM FINAL)

@app.post("/api/render2d")
def render_2d(payload: Render2DRequest):
    client_id = payload.client
    scene_id = payload.scene
    selection = payload.selection

    logging.info(f"🖼️ Render 2D: client={client_id}, scene={scene_id}")

    try:
        project, _ = load_client_config(client_id)
    except Exception as e:
        logging.exception("❌ Falha ao carregar config")
        raise HTTPException(500, f"Erro ao carregar config: {e}")

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
            "url": f"/panoconfig360_cache/{cdn_key}"
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
            "url": f"/panoconfig360_cache/{cdn_key}",
        }

    except FileNotFoundError as e:
        logging.error(str(e))
        return {
            "status": "error",
            "type": "missing_asset",
            "message": str(e),
        }

    except Exception as e:
        logging.exception("❌ Erro inesperado no render 2D")
        raise HTTPException(
            status_code=500,
            detail="Erro interno no render 2D",
        )

    finally:
        if output_path is not None and os.path.exists(output_path):
            os.remove(output_path)


@app.get("/")
def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "index.html não encontrado")
    return FileResponse(index_path)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "panoconfig360-backend", "version": "0.0.1"}


@app.get("/panoconfig360_cache/cubemap/{client_id}/{scene_id}/tiles/{build}/{filename}")
def get_tile(client_id: str, scene_id: str, build: str, filename: str):

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
