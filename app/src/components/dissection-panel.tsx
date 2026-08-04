import { useState } from 'react';
import { PEEL_ORDER, TISSUE_COLOR, type LayerKey, type View } from '../lib/catalog';
import { AXIS_SOURCE, type ClipAxis, type ClipState } from '../lib/clipping';
import type { LayerState } from './anatomy-canvas';
import type { Strings } from '../lib/i18n';

/**
 * Panel de disección.
 *
 * Las capas son lo que se toca todo el tiempo y quedan siempre a la vista. El
 * corte y la medición son herramientas ocasionales: tenerlas desplegadas
 * permanentemente hacía que el panel compitiera con el modelo por atención.
 */

export function DissectionPanel({
    t,
    view,
    layers,
    clip,
    clipMin,
    clipMax,
    clipAt,
    measuring,
    measureMm,
    onLayer,
    onPeel,
    onClip,
    onMeasuring,
}: {
    t: Strings;
    view: View;
    layers: Record<LayerKey, LayerState>;
    clip: ClipState;
    clipMin: number;
    clipMax: number;
    clipAt: number;
    measuring: boolean;
    measureMm: number | null;
    onLayer: (k: LayerKey, patch: Partial<LayerState>) => void;
    onPeel: (depth: number) => void;
    onClip: (patch: Partial<ClipState>) => void;
    onMeasuring: (v: boolean) => void;
}) {
    const [toolsOpen, setToolsOpen] = useState(false);
    const present = [...PEEL_ORDER].reverse().filter(k => view.layers[k]);
    const toolsActive = clip.enabled || measuring;

    return (
        // Sin posicionamiento propio: lo ubica el contenedor, que es quien sabe
        // si estamos en escritorio (panel flotante) o en móvil (hoja inferior).
        <section className="panel w-full overflow-hidden">
            <header className="border-rule flex items-baseline gap-2 border-b px-5 py-3.5">
                <h2 className="eyebrow flex-1">{t.dissection}</h2>
                <span className="text-ink-faint font-mono text-[10px] tabular-nums">
                    {present.length}
                </span>
            </header>

            <div className="px-5 py-2">
                {present.map(k => {
                    const chunk = view.layers[k]!;
                    const on = layers[k].visible;
                    return (
                        <div key={k} className="border-rule/50 border-b py-2.5 last:border-0">
                            <div className="flex items-center gap-3">
                                <span
                                    aria-hidden
                                    className="size-3 shrink-0 rounded-[3px]"
                                    style={{ background: TISSUE_COLOR[k] }}
                                />
                                <button
                                    onClick={() => onPeel(PEEL_ORDER.indexOf(k))}
                                    title={t.peel}
                                    className="hover:text-clay-ink flex-1 text-left font-sans text-[13px] transition-colors"
                                >
                                    {t.layers[k]}
                                </button>
                                <span className="text-ink-faint font-mono text-[10px] tabular-nums">
                                    {chunk.structures?.length ?? '—'}
                                </span>
                                <Switch
                                    checked={on}
                                    onChange={v => onLayer(k, { visible: v })}
                                    label={t.layers[k]}
                                />
                            </div>

                            {/* La opacidad sólo aparece si la capa está encendida:
                                un control deshabilitado ocupa lo mismo y no sirve. */}
                            {on && (
                                <input
                                    type="range"
                                    min={8}
                                    max={100}
                                    value={layers[k].opacity * 100}
                                    onChange={e => onLayer(k, { opacity: Number(e.target.value) / 100 })}
                                    aria-label={`${t.layers[k]} — opacidad`}
                                    className="accent-clay mt-2 h-[3px] w-full cursor-pointer"
                                />
                            )}
                        </div>
                    );
                })}
            </div>

            <p className="text-ink-faint border-rule border-t px-5 py-2.5 font-sans text-[10.5px] leading-relaxed">
                {t.peelHint}
            </p>

            {/* Herramientas ocasionales, plegadas por defecto */}
            <button
                onClick={() => setToolsOpen(v => !v)}
                aria-expanded={toolsOpen}
                className="border-rule hover:bg-sunk flex w-full items-center gap-2 border-t px-5 py-3 text-left transition-colors"
            >
                <span className="eyebrow flex-1">{t.tools}</span>
                {toolsActive && !toolsOpen && (
                    <span className="bg-clay size-1.5 rounded-full" aria-hidden />
                )}
                <span className="text-ink-faint font-mono text-[10px]">
                    {toolsOpen ? '−' : '+'}
                </span>
            </button>

            {toolsOpen && (
                <div className="border-rule border-t px-5 py-4">
                    {/* Corte */}
                    <div className="flex items-center gap-2">
                        <h3 className="eyebrow flex-1">{t.section}</h3>
                        <Switch
                            checked={clip.enabled}
                            onChange={v => onClip({ enabled: v })}
                            label={t.section}
                        />
                    </div>

                    {clip.enabled && (
                        <>
                            <div className="mt-2.5 flex gap-1">
                                {(['sagittal', 'coronal', 'axial'] as ClipAxis[]).map(a => (
                                    <button
                                        key={a}
                                        onClick={() =>
                                            onClip({
                                                axis: a,
                                                at: Math.round(
                                                    (view.bounds.min[AXIS_SOURCE[a]] +
                                                        view.bounds.max[AXIS_SOURCE[a]]) / 2
                                                ),
                                            })
                                        }
                                        aria-pressed={clip.axis === a}
                                        className={`flex-1 rounded-md border px-1 py-1.5 font-sans text-[10.5px] transition-colors ${
                                            clip.axis === a
                                                ? 'border-clay bg-clay/12 text-clay-ink'
                                                : 'border-rule text-ink-soft hover:border-clay/50'
                                        }`}
                                    >
                                        {t.planes[a]}
                                    </button>
                                ))}
                            </div>
                            <input
                                type="range"
                                min={clipMin}
                                max={clipMax}
                                value={clipAt}
                                onChange={e => onClip({ at: Number(e.target.value) })}
                                aria-label={t.section}
                                className="accent-clay mt-2.5 h-[3px] w-full cursor-pointer"
                            />
                            <button
                                onClick={() => onClip({ flipped: !clip.flipped })}
                                className="text-ink-faint hover:text-clay-ink mt-2 font-sans text-[10.5px] underline underline-offset-2"
                            >
                                {t.flipSide}
                            </button>
                        </>
                    )}

                    {/* Medición */}
                    <div className="border-rule mt-4 flex items-center gap-2 border-t pt-4">
                        <h3 className="eyebrow flex-1">{t.measure}</h3>
                        <Switch
                            checked={measuring}
                            onChange={onMeasuring}
                            label={t.measure}
                        />
                    </div>
                    <p className="text-ink-faint mt-1.5 font-sans text-[10.5px] leading-relaxed">
                        {measureMm
                            ? t.measureResult
                                  .replace('{mm}', measureMm.toFixed(1))
                                  .replace('{cm}', (measureMm / 10).toFixed(1))
                            : measuring
                              ? t.measureHint
                              : t.measureOff}
                    </p>
                </div>
            )}
        </section>
    );
}

function Switch({
    checked,
    disabled,
    onChange,
    label,
}: {
    checked: boolean;
    disabled?: boolean;
    onChange: (v: boolean) => void;
    label: string;
}) {
    return (
        <button
            role="switch"
            aria-checked={checked}
            aria-label={label}
            disabled={disabled}
            onClick={() => onChange(!checked)}
            className={`relative h-[18px] w-[32px] shrink-0 rounded-full transition-colors disabled:cursor-default ${
                checked ? 'bg-clay' : 'bg-rule'
            }`}
        >
            <span
                className={`bg-surface absolute top-0.5 size-[14px] rounded-full shadow-sm transition-transform ${
                    checked ? 'translate-x-[16px]' : 'translate-x-0.5'
                }`}
            />
        </button>
    );
}
