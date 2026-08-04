/**
 * Catálogo anatómico. Son archivos estáticos generados por /pipeline: no hay
 * backend. Los GLB llevan hash de contenido en el nombre, así que el catálogo
 * es la única fuente de URLs.
 */

export const LAYER_KEYS = [
    'skeletal',
    'organs',
    'vascular',
    'nervous',
    'muscular',
    'skin',
] as const;

export type LayerKey = (typeof LAYER_KEYS)[number];

/** De la más profunda a la más superficial: define el orden del pelado. */
export const PEEL_ORDER: LayerKey[] = [
    'skeletal',
    'organs',
    'vascular',
    'nervous',
    'muscular',
    'skin',
];

export const TISSUE_COLOR: Record<LayerKey, string> = {
    skeletal: '#ddd6c0',
    organs: '#b8736a',
    vascular: '#b0262e',
    nervous: '#e3c65f',
    muscular: '#b23f3a',
    skin: '#e0b394',
};

export interface StructureRef {
    fma: string;
    name: string;
    faces: number;
}

export interface LayerChunk {
    file: string;
    bytes: number;
    tris: number;
    structures?: StructureRef[];
}

export interface Bounds {
    min: [number, number, number];
    max: [number, number, number];
}

export interface RegionEntry {
    key: string;
    label: string;
    layers: Partial<Record<LayerKey, LayerChunk>>;
    bounds: Bounds;
}

export interface AnatomyCatalog {
    layers: { key: LayerKey; label: string }[];
    regions: RegionEntry[];
    overview: { layers: Partial<Record<LayerKey, LayerChunk>>; bounds: Bounds };
    attribution: string;
}

/** Nomenclatura multilingüe (Terminologia Anatomica 2), indexada por FMA id. */
export interface Term {
    en: string;
    es?: string;
    la?: string;
    fr?: string;
    pt?: string;
    it?: string;
    ta2?: string;
    side?: 'left' | 'right';
}

export type TermIndex = Record<string, Term>;

export const OVERVIEW = 'overview';

/** Una vista es una región concreta o el cuerpo entero: misma forma para ambas. */
export interface View {
    key: string;
    label: string;
    layers: Partial<Record<LayerKey, LayerChunk>>;
    bounds: Bounds;
}

export function getView(catalog: AnatomyCatalog, key: string): View {
    if (key === OVERVIEW) {
        return { key: OVERVIEW, label: 'Cuerpo entero', ...catalog.overview };
    }
    const region = catalog.regions.find(r => r.key === key);
    if (!region) return getView(catalog, OVERVIEW);
    return { key: region.key, label: region.label, layers: region.layers, bounds: region.bounds };
}

/**
 * Centro y radio de una vista.
 *
 * Esto es lo que arregla el encuadre: todas las regiones comparten un mismo
 * origen global (para que encajen entre sí), así que la cabeza tiene su centro
 * en Z ≈ +718 mm. Sin apuntar la cámara acá, el zoom se va hacia la cadera y la
 * región se escapa de cuadro.
 */
export function framing(bounds: Bounds) {
    const center: [number, number, number] = [
        (bounds.min[0] + bounds.max[0]) / 2,
        (bounds.min[1] + bounds.max[1]) / 2,
        (bounds.min[2] + bounds.max[2]) / 2,
    ];
    const size = [
        bounds.max[0] - bounds.min[0],
        bounds.max[1] - bounds.min[1],
        bounds.max[2] - bounds.min[2],
    ];
    return { center, radius: Math.max(...size) / 2 };
}

export function countStructures(view: View) {
    return LAYER_KEYS.reduce((n, k) => n + (view.layers[k]?.structures?.length ?? 0), 0);
}

export function countBytes(view: View) {
    return LAYER_KEYS.reduce((n, k) => n + (view.layers[k]?.bytes ?? 0), 0);
}

/** Índice plano para el buscador: estructura → capa y región. */
export interface SearchRow {
    fma: string;
    layer: LayerKey;
    region: string;
    regionLabel: string;
    label: string;
    haystack: string;
}

export function buildSearchIndex(
    catalog: AnatomyCatalog,
    terms: TermIndex,
    lang: string
): SearchRow[] {
    const rows: SearchRow[] = [];
    const seen = new Set<string>();

    for (const region of catalog.regions) {
        for (const key of LAYER_KEYS) {
            for (const s of region.layers[key]?.structures ?? []) {
                if (seen.has(s.fma)) continue;
                seen.add(s.fma);
                const t = terms[s.fma];
                const label = (t && (t[lang as keyof Term] as string)) || t?.en || s.name;
                rows.push({
                    fma: s.fma,
                    layer: key,
                    region: region.key,
                    regionLabel: region.label,
                    label,
                    haystack: [label, t?.en, t?.la, s.name, s.fma]
                        .filter(Boolean)
                        .join(' ')
                        .toLowerCase(),
                });
            }
        }
    }
    return rows;
}

export async function loadCatalog(): Promise<[AnatomyCatalog, TermIndex]> {
    const [catalog, terms] = await Promise.all([
        fetch('/anatomy/catalog.json').then(r => {
            if (!r.ok) throw new Error(`catalog.json: ${r.status}`);
            return r.json() as Promise<AnatomyCatalog>;
        }),
        fetch('/anatomy/terms.json').then(r => {
            if (!r.ok) throw new Error(`terms.json: ${r.status}`);
            return r.json() as Promise<TermIndex>;
        }),
    ]);
    return [catalog, terms];
}
