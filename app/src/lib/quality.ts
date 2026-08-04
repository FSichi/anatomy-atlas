/**
 * Presets de calidad.
 *
 * El objetivo es que la app sea usable en un celular sin renunciar a la máxima
 * calidad en una máquina que la aguante. Por defecto se detecta: pedirle a
 * alguien que elija su nivel gráfico antes de ver nada es mal reparto de
 * trabajo — si el usuario quiere decidir, el control está en Configuración.
 *
 * Qué controla cada nivel, en orden de impacto real medido:
 *   1. pixelRatio — el más pesado con diferencia; renderizar a 2x cuadruplica
 *      los píxeles y el sombreado es proporcional a eso
 *   2. antialias — MSAA cuesta memoria de framebuffer y ancho de banda
 *   3. material  — `physical` con transmisión hace que el tejido se vea
 *      translúcido en vez de plástico, pero suma un pase de refracción
 *   4. maxTris   — techo para decidir qué nivel de detalle pedir
 */

export const QUALITY_LEVELS = ['low', 'medium', 'high'] as const;
export type QualityLevel = (typeof QUALITY_LEVELS)[number];
export type QualitySetting = QualityLevel | 'auto';

export interface QualityProfile {
    level: QualityLevel;
    /** Tope de devicePixelRatio. */
    dpr: number;
    antialias: boolean;
    /** `physical` habilita translucidez de tejido; `standard` es el barato. */
    material: 'standard' | 'physical';
    /** Techo de triángulos por escena, para elegir nivel de detalle. */
    maxTris: number;
    /** Suavizado de la órbita: en equipos lentos el amortiguado se siente pegajoso. */
    damping: number;
}

export const PROFILES: Record<QualityLevel, QualityProfile> = {
    low: {
        level: 'low',
        dpr: 1,
        antialias: false,
        material: 'standard',
        maxTris: 350_000,
        damping: 0.12,
    },
    medium: {
        level: 'medium',
        dpr: 1.5,
        antialias: true,
        material: 'standard',
        maxTris: 1_000_000,
        damping: 0.09,
    },
    high: {
        level: 'high',
        dpr: 2,
        antialias: true,
        material: 'physical',
        maxTris: 3_000_000,
        damping: 0.075,
    },
};

/**
 * Detección automática.
 *
 * No hay una API que diga "esta GPU es rápida", así que se combinan señales
 * baratas y se peca de conservador: es mejor arrancar en medio en una máquina
 * potente (y que el usuario suba) que arrancar en alto en un celular y que la
 * primera impresión sea un tirón.
 */
/**
 * Cache de la detección.
 *
 * Sin esto, cada llamada crea un `<canvas>` y pide un contexto WebGL sólo para
 * leer el nombre de la GPU. Los navegadores limitan los contextos vivos (unos
 * 16) y al pasarse descartan los más viejos — incluido el del visor, que se
 * quedaba en negro. El hardware no cambia durante la sesión: se mide una vez.
 */
let cached: QualityLevel | null = null;

export function detectQuality(): QualityLevel {
    if (cached) return cached;
    cached = detect();
    return cached;
}

function detect(): QualityLevel {
    if (typeof navigator === 'undefined') return 'medium';

    const coarse = matchMedia('(pointer: coarse)').matches;
    const cores = navigator.hardwareConcurrency ?? 4;
    const mem = (navigator as unknown as { deviceMemory?: number }).deviceMemory ?? 4;

    // El nombre del renderer es la señal más directa cuando está disponible.
    let renderer = '';
    try {
        const cv = document.createElement('canvas');
        const gl = cv.getContext('webgl2') ?? cv.getContext('webgl');
        const dbg = gl?.getExtension('WEBGL_debug_renderer_info');
        if (gl && dbg) {
            renderer = String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) ?? '');
        }
        // Devolver el contexto de inmediato: es de un solo uso.
        gl?.getExtension('WEBGL_lose_context')?.loseContext();
    } catch {
        /* algunos navegadores lo bloquean por privacidad: se ignora */
    }

    const low = /adreno [1-5]|mali-[tg][ -]?[1-6]|powervr|apple a[789]|swiftshader|llvmpipe/i;
    const strong = /rtx|radeon rx|arc a|apple m[1-9]|geforce gtx 1[6-9]|adreno 7[0-9][0-9]/i;

    if (low.test(renderer)) return 'low';
    if (strong.test(renderer) && !coarse) return 'high';

    if (coarse) return cores >= 8 && mem >= 6 ? 'medium' : 'low';
    if (cores >= 8 && mem >= 8) return 'high';
    if (cores >= 4) return 'medium';
    return 'low';
}

const STORAGE_KEY = 'atlas:quality';

export function readQualitySetting(): QualitySetting {
    try {
        const v = localStorage.getItem(STORAGE_KEY);
        if (v === 'auto' || (QUALITY_LEVELS as readonly string[]).includes(v ?? '')) {
            return v as QualitySetting;
        }
    } catch {
        /* modo privado sin almacenamiento */
    }
    return 'auto';
}

export function writeQualitySetting(v: QualitySetting) {
    try {
        localStorage.setItem(STORAGE_KEY, v);
    } catch {
        /* sin almacenamiento: la elección dura lo que la sesión */
    }
}

export function resolveProfile(setting: QualitySetting): QualityProfile {
    return PROFILES[setting === 'auto' ? detectQuality() : setting];
}
