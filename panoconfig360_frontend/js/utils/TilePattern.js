/**
 // TilePattern.js
 // Padrão de URL para tiles do cubemap
 // Alinhado com o backend (split_faces_cubemap.py e server.py)
 //
 // Backend gera: cubemap/{client}/{scene}/tiles/{BUILD}/{BUILD}_{FACE}_{LOD}_{X}_{Y}.jpg

export const TILE_PATTERN = Object.freeze({
  template: "{BUILD}_{FACE}_{LOD}_{X}_{Y}.jpg",

  // Retorna o nome do arquivo de um tile específico
  getTileFilename(build, face, lod, x, y) {
    return `${build}_${face}_${lod}_${x}_${y}.jpg`;
  },

  // Retorna a URL local de um tile específico
  getLocalUrl(clientId, sceneId, build, face, lod, x, y) {
    return `/panoconfig360_cache/clients/${clientId}/cubemap/${sceneId}/tiles/${build}/${build}_${face}_${lod}_${x}_${y}.jpg`;
  },

  // Retorna o padrão Marzipano para tiles
  getMarzipanoPattern(clientId, sceneId, build) {
    return `/panoconfig360_cache/clients/${clientId}/cubemap/${sceneId}/tiles/${build}/${build}_{f}_{z}_{x}_{y}.jpg`;
  },

  // Retorna a URL canônica de um tile (face 0, LOD 0, x 0, y 0)
  getCanonicalUrl(clientId, sceneId, build) {
    return this.getLocalUrl(clientId, sceneId, build, "f", 0, 0, 0);
  },

 // Retorna o tile root usado no backend
  buildTileRoot(clientId, sceneId, build) {
    return `clients/${clientId}/cubemap/${sceneId}/tiles/${build}`;
  },
}); 

*/

/**
 * TilePattern desacoplado de storage.
 * Apenas resolve URLs com base no contrato retornado pela API.
 */

export const TilePattern = Object.freeze({
  getFilename(tiles, f, z, x, y) {
    return tiles.pattern
      .replace("{build}", tiles.build)
      .replace("{f}", f)
      .replace("{z}", z)
      .replace("{x}", x)
      .replace("{y}", y);
  },

  getUrl(tiles, f, z, x, y) {
    return `${tiles.baseUrl}/${tiles.tileRoot}/${this.getFilename(tiles, f, z, x, y)}`;
  },

  getCanonicalUrl(tiles) {
    return this.getUrl(tiles, "f", 0, 0, 0);
  },

  getMarzipanoPattern(tiles) {
    return `${tiles.baseUrl}/${tiles.tileRoot}/${tiles.pattern}`;
  },
});
