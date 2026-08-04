/**
 * Estado compartible en la URL.
 *
 * El objetivo es didáctico: un profesor manda un link y el alumno abre
 * exactamente la misma vista. Se escribe con replaceState para no llenar el
 * historial con cada clic.
 */

import type { LayerKey } from './catalog';

export interface UrlState {
    region: string;
    fma: string | null;
    lang: string;
    theme: 'dark' | 'light';
    /** Capas visibles; ausente = las por defecto. */
    layers: LayerKey[] | null;
    clip: { axis: string; at: number; flipped: boolean } | null;
}

export function readUrl(): Partial<UrlState> {
    const p = new URLSearchParams(location.search);
    const out: Partial<UrlState> = {};

    const region = p.get('region');
    if (region) out.region = region;

    const fma = p.get('fma');
    if (fma) out.fma = fma;

    const lang = p.get('lang');
    if (lang === 'es' || lang === 'en') out.lang = lang;

    const theme = p.get('theme');
    if (theme === 'dark' || theme === 'light') out.theme = theme;

    const layers = p.get('layers');
    if (layers) out.layers = layers.split(',').filter(Boolean) as LayerKey[];

    const clip = p.get('clip');
    if (clip) {
        // formato: eje:posicion:invertido  ej. axial:1200:0
        const [axis, at, flipped] = clip.split(':');
        if (axis && at && Number.isFinite(Number(at))) {
            out.clip = { axis, at: Number(at), flipped: flipped === '1' };
        }
    }

    return out;
}

export function writeUrl(state: UrlState) {
    const p = new URLSearchParams();
    p.set('region', state.region);
    if (state.fma) p.set('fma', state.fma);
    p.set('lang', state.lang);
    p.set('theme', state.theme);
    if (state.layers) p.set('layers', state.layers.join(','));
    if (state.clip) {
        p.set('clip', `${state.clip.axis}:${Math.round(state.clip.at)}:${state.clip.flipped ? 1 : 0}`);
    }

    const next = `${location.pathname}?${p.toString()}`;
    if (next !== location.pathname + location.search) {
        history.replaceState(null, '', next);
    }
}
