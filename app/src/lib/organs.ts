/**
 * Galería de órganos: cada órgano es un GLB propio, a máxima resolución.
 *
 * Es un catálogo aparte del atlas por capas a propósito. El atlas decima al
 * ~22% para que un cuerpo entero entre en presupuesto; acá se mira un órgano
 * solo y ese presupuesto no aplica, así que se sirve la malla completa con la
 * oclusión ambiental ya horneada en los colores de vértice.
 */

export const ORGAN_CATEGORIES = ['organ', 'bone', 'muscle'] as const;
export type OrganCategory = (typeof ORGAN_CATEGORIES)[number];

export interface OrganPart {
    fma: string;
    tissue: string;
    faces: number;
    name: string;
}

export interface Organ {
    key: string;
    es: string;
    en: string;
    system: string;
    /** organ | bone | muscle — agrupa la biblioteca. */
    cat: OrganCategory;
    file: string;
    bytes: number;
    tris: number;
    radius: number;
    structures: OrganPart[];
    missing: string[];
}

export interface OrganCatalog {
    organs: Organ[];
    attribution: string;
}

/** Color del punto en la lista; el mismo que usa el pipeline por tejido. */
export const TISSUE_SWATCH: Record<string, string> = {
    muscle: '#b84a45',
    vessel: '#ad2930',
    vein: '#5c5c8c',
    neural: '#ccbdae',
    gut: '#cc8f73',
    gland: '#a86b61',
    airway: '#bdb8b3',
    bile: '#9ea15c',
    urinary: '#b36657',
    sense: '#d9d7d4',
    bone: '#e6e0cc',
    muscle_belly: '#ad423d',
};

export async function loadOrgans(): Promise<OrganCatalog> {
    const r = await fetch('/anatomy/organs/catalog.json');
    if (!r.ok) throw new Error(`organs/catalog.json: ${r.status}`);
    return (await r.json()) as OrganCatalog;
}

/** Si el pipeline de órganos no corrió, la app sigue funcionando sin la galería. */
export async function organsAvailable(): Promise<boolean> {
    try {
        const r = await fetch('/anatomy/organs/catalog.json');
        if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) return false;
        const body = (await r.json()) as Partial<OrganCatalog>;
        return Array.isArray(body.organs) && body.organs.length > 0;
    } catch {
        return false;
    }
}
