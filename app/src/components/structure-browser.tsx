import { useMemo, useState } from 'react';
import {
    LAYER_KEYS,
    TISSUE_COLOR,
    type LayerKey,
    type Term,
    type TermIndex,
    type View,
} from '../lib/catalog';
import type { UI } from '../lib/i18n';

/**
 * Explorador de estructuras de la vista activa.
 *
 * Lista todo lo que hay para ver en la región en la que estás, con búsqueda y
 * filtro por capa. Un clic selecciona y enfoca; la casilla suma a la selección
 * múltiple, y con algo marcado el visor muestra sólo eso.
 */

type Strings = (typeof UI)['es'];

export interface BrowserRow {
    fma: string;
    layer: LayerKey;
    label: string;
    latin?: string;
    haystack: string;
}

export function buildRows(view: View, terms: TermIndex, lang: string): BrowserRow[] {
    const rows: BrowserRow[] = [];
    const seen = new Set<string>();

    for (const key of LAYER_KEYS) {
        for (const s of view.layers[key]?.structures ?? []) {
            if (seen.has(s.fma)) continue;
            seen.add(s.fma);
            const t: Term | undefined = terms[s.fma];
            const label = (t?.[lang as keyof Term] as string) || t?.en || s.name;
            rows.push({
                fma: s.fma,
                layer: key,
                label,
                latin: t?.la,
                haystack: [label, t?.en, t?.la, s.name].filter(Boolean).join(' ').toLowerCase(),
            });
        }
    }
    return rows.sort((a, b) => a.label.localeCompare(b.label, lang));
}

export function StructureBrowser({
    view,
    terms,
    lang,
    t,
    selected,
    picked,
    onSelect,
    onTogglePick,
    onClearPicks,
}: {
    view: View;
    terms: TermIndex;
    lang: string;
    t: Strings;
    selected: string | null;
    picked: Set<string>;
    onSelect: (fma: string) => void;
    onTogglePick: (fma: string) => void;
    onClearPicks: () => void;
}) {
    const [query, setQuery] = useState('');
    const [layerFilter, setLayerFilter] = useState<LayerKey | null>(null);

    const rows = useMemo(() => buildRows(view, terms, lang), [view, terms, lang]);

    const present = LAYER_KEYS.filter(k => view.layers[k]?.structures?.length);

    const filtered = rows.filter(r => {
        if (layerFilter && r.layer !== layerFilter) return false;
        const q = query.trim().toLowerCase();
        return !q || r.haystack.includes(q);
    });

    // El cuerpo entero tiene 928 estructuras; pintarlas todas mete casi mil
    // nodos con casilla en el DOM y se nota al desplazar. Se recorta y se avisa
    // cuántas quedaron fuera — nunca truncar en silencio.
    const CAP = 120;
    const shown = filtered.slice(0, CAP);
    const hidden = filtered.length - shown.length;

    return (
        <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden" aria-label={t.browser}>
            <div className="border-rule flex items-center gap-2 border-b px-4 py-2.5">
                <h2 className="eyebrow flex-1">{t.browser}</h2>
                <span className="text-ink-faint font-mono text-[10px] tabular-nums">
                    {filtered.length}
                </span>
                {picked.size > 0 && (
                    <button
                        onClick={onClearPicks}
                        className="text-clay-ink font-sans text-[10px] underline underline-offset-2"
                    >
                        {t.showAll}
                    </button>
                )}
            </div>

            <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder={t.filterPlaceholder}
                aria-label={t.browser}
                className="border-rule border-b bg-transparent px-4 py-2 text-[12.5px] outline-none"
            />

            <div className="border-rule flex flex-wrap gap-1 border-b px-3 py-2">
                <FilterChip active={!layerFilter} onClick={() => setLayerFilter(null)}>
                    {t.allLayers}
                </FilterChip>
                {present.map(k => (
                    <FilterChip
                        key={k}
                        active={layerFilter === k}
                        color={TISSUE_COLOR[k]}
                        onClick={() => setLayerFilter(layerFilter === k ? null : k)}
                    >
                        {t.layers[k]}
                    </FilterChip>
                ))}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
                {shown.map(r => {
                    const isPicked = picked.has(r.fma);
                    return (
                        <div
                            key={r.fma}
                            className={`hover:bg-sunk group flex items-center gap-2 px-3 py-1.5 ${
                                selected === r.fma ? 'bg-clay/10' : ''
                            }`}
                        >
                            <input
                                type="checkbox"
                                checked={isPicked}
                                onChange={() => onTogglePick(r.fma)}
                                aria-label={`${t.isolate}: ${r.label}`}
                                className="accent-clay size-3 shrink-0 cursor-pointer"
                            />
                            <span
                                className="size-2 shrink-0 rounded-[2px]"
                                style={{ background: TISSUE_COLOR[r.layer] }}
                                aria-hidden
                            />
                            <button
                                onClick={() => onSelect(r.fma)}
                                className="min-w-0 flex-1 text-left"
                                title={r.latin}
                            >
                                <span
                                    className={`block truncate text-[12.5px] ${
                                        selected === r.fma ? 'text-clay-ink' : ''
                                    }`}
                                >
                                    {r.label}
                                </span>
                            </button>
                        </div>
                    );
                })}

                {hidden > 0 && (
                    <p className="text-ink-faint px-4 py-3 text-center text-[11px]">
                        {t.andMore.replace('{n}', String(hidden))}
                    </p>
                )}

                {!filtered.length && (
                    <p className="text-ink-faint px-4 py-6 text-center text-[12px]">
                        {t.noResults}
                    </p>
                )}
            </div>
        </section>
    );
}

function FilterChip({
    active,
    color,
    onClick,
    children,
}: {
    active?: boolean;
    color?: string;
    onClick: () => void;
    children: React.ReactNode;
}) {
    return (
        <button
            onClick={onClick}
            aria-pressed={active}
            className={`flex items-center gap-1.5 rounded-full border px-2 py-[3px] font-sans text-[10.5px] transition-colors ${
                active
                    ? 'border-clay bg-clay/12 text-clay-ink'
                    : 'border-rule text-ink-soft hover:border-clay/50'
            }`}
        >
            {color && (
                <span
                    className="size-1.5 rounded-[1px]"
                    style={{ background: color }}
                    aria-hidden
                />
            )}
            {children}
        </button>
    );
}
