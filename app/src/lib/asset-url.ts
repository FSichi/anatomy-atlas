/**
 * Rutas de assets, resueltas contra la base del despliegue.
 *
 * En GitHub Pages la app no vive en la raíz del dominio sino en
 * `/anatomy-atlas/`, así que cualquier ruta absoluta tipo `/anatomy/...` cae
 * fuera del sitio y devuelve 404. `import.meta.env.BASE_URL` trae esa base
 * (con barra final) y en desarrollo vale `/`, así que el mismo código sirve
 * para los dos casos.
 */

export function asset(path: string): string {
    return import.meta.env.BASE_URL + path.replace(/^\/+/, '');
}

/** Decodificador Draco autohospedado. */
export const DRACO_PATH = asset('draco/');

/** Reescribe una URL que vino dentro de un catálogo generado por el pipeline. */
export function fromCatalog(file: string): string {
    return asset(file);
}
