import { useEffect, useRef, useState } from 'react';
import {
    LAYER_KEYS,
    OVERVIEW,
    PEEL_ORDER,
    TISSUE_COLOR,
    buildSearchIndex,
    countBytes,
    countStructures,
    getView,
    loadCatalog,
    type AnatomyCatalog,
    type LayerKey,
    type SearchRow,
    type Term,
    type TermIndex,
} from './lib/catalog';
import { SOURCE_INFO, availableSources, type SourceId } from './lib/catalog';
import { LANGS, UI, type Lang } from './lib/i18n';
import { SettingsModal, type SourceMeta } from './components/settings-modal';
import * as THREE from 'three';
import {
    AXIS_SOURCE,
    AnatomyCanvas,
    type ClipAxis,
    type ClipState,
    type LayerState,
    type Stats,
} from './components/anatomy-canvas';
import { StructureBrowser } from './components/structure-browser';
import { readUrl, writeUrl } from './lib/url-state';

/**
 * Ficha de cada fuente para el modal. Los números salen del censo del pipeline
 * (`pipeline/out/zanatomy-census.txt`), no de estimaciones.
 */
const SOURCE_META: Record<string, SourceMeta> = {
    bodyparts3d: {
        id: 'bodyparts3d',
        structures: 936,
        megabytes: 21.6,
        strong: ['vasos 64', 'ontología FMA', 'regiones'],
        weak: ['sin articulaciones', 'sin inserciones'],
    },
    zanatomy: {
        id: 'zanatomy',
        structures: 2654,
        megabytes: 21.6,
        strong: ['articulaciones 410', 'inserciones 705', 'linfoide 159', 'músculos 670'],
        weak: ['vasos 22', 'sin piel'],
    },
    mix: {
        id: 'mix',
        structures: 2443,
        megabytes: 18.4,
        strong: ['vasos 65', 'articulaciones 410', 'inserciones 705', 'linfoide 159', 'piel'],
        weak: [],
    },
};

const INITIAL_LAYERS: Record<LayerKey, LayerState> = {
    skeletal: { visible: true, opacity: 1 },
    // Las inserciones tapan el hueso al que se adhieren: arrancan apagadas.
    joints: { visible: true, opacity: 1 },
    insertions: { visible: false, opacity: 1 },
    organs: { visible: true, opacity: 1 },
    lymphoid: { visible: true, opacity: 1 },
    vascular: { visible: true, opacity: 1 },
    nervous: { visible: true, opacity: 1 },
    muscular: { visible: true, opacity: 1 },
    skin: { visible: false, opacity: 0.3 },
};

export default function App() {
    const [catalog, setCatalog] = useState<AnatomyCatalog | null>(null);
    const [terms, setTerms] = useState<TermIndex>({});
    const [error, setError] = useState<string | null>(null);

    const [lang, setLang] = useState<Lang>('es');
    const [dark, setDark] = useState(true);
    const [viewKey, setViewKey] = useState(OVERVIEW);
    const [layers, setLayers] = useState(INITIAL_LAYERS);
    const [selected, setSelected] = useState<string | null>(null);
    /** Vacío = ver todo. Con contenido, el visor muestra sólo esas estructuras. */
    const [picked, setPicked] = useState<Set<string>>(new Set());
    const [focusTarget, setFocusTarget] = useState<string | null>(null);
    const [stats, setStats] = useState<Stats>({ fps: 0, tris: 0, calls: 0 });
    const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
    const [resetNonce, setResetNonce] = useState(0);
    const [ready, setReady] = useState(false);
    const [query, setQuery] = useState('');
    const [searchOpen, setSearchOpen] = useState(false);

    const [clip, setClip] = useState<ClipState>({
        enabled: false,
        axis: 'axial',
        at: 0,
        flipped: false,
    });
    const [measuring, setMeasuring] = useState(false);
    const [measurePoints, setMeasurePoints] = useState<THREE.Vector3[]>([]);
    const [measureLabel, setMeasureLabel] = useState<{ x: number; y: number } | null>(null);

    const [source, setSource] = useState<SourceId>('bodyparts3d');
    const [sources, setSources] = useState<SourceId[]>([]);
    const [settingsOpen, setSettingsOpen] = useState(false);

    const t = UI[lang];

    useEffect(() => {
        availableSources().then(setSources);
    }, []);

    // La URL manda al abrir: un link compartido tiene que reproducir la vista.
    const bootstrapped = useRef(false);
    useEffect(() => {
        if (bootstrapped.current) return;
        bootstrapped.current = true;
        const u = readUrl();
        if (u.region) setViewKey(u.region);
        if (u.fma) setSelected(u.fma);
        if (u.lang) setLang(u.lang as Lang);
        if (u.theme) setDark(u.theme === 'dark');
        if (u.layers) {
            setLayers(prev => {
                const next = { ...prev };
                for (const k of Object.keys(next) as LayerKey[]) {
                    next[k] = { ...next[k], visible: u.layers!.includes(k) };
                }
                return next;
            });
        }
        if (u.clip) {
            setClip({
                enabled: true,
                axis: u.clip.axis as ClipAxis,
                at: u.clip.at,
                flipped: u.clip.flipped,
            });
        }
    }, []);

    useEffect(() => {
        document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    }, [dark]);

    // Reflejar el estado en la URL para que la vista sea compartible.
    useEffect(() => {
        if (!bootstrapped.current) return;
        writeUrl({
            region: viewKey,
            fma: selected,
            lang,
            theme: dark ? 'dark' : 'light',
            layers: (Object.keys(layers) as LayerKey[]).filter(k => layers[k].visible),
            clip: clip.enabled
                ? { axis: clip.axis, at: clip.at, flipped: clip.flipped }
                : null,
        });
    }, [viewKey, selected, lang, dark, layers, clip]);

    useEffect(() => {
        let cancelled = false;
        setCatalog(null);
        setReady(false);
        setSelected(null);
        loadCatalog(source)
            .then(([c, tm]) => {
                if (cancelled) return;
                setCatalog(c);
                setTerms(tm);
            })
            .catch(e => !cancelled && setError(String(e?.message ?? e)));
        return () => {
            cancelled = true;
        };
    }, [source]);

    // Ctrl/Cmd+K abre el buscador; Escape limpia la selección.
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                setSearchOpen(v => !v);
            }
            if (e.key === 'Escape') {
                setSearchOpen(false);
                setSelected(null);
                setPicked(new Set());
            }
        };
        addEventListener('keydown', onKey);
        return () => removeEventListener('keydown', onKey);
    }, []);

    if (error) {
        return (
            <Centered>
                <p className="text-lg">Anatomía no disponible</p>
                <p className="text-ink-faint mt-2 font-mono text-xs">{error}</p>
            </Centered>
        );
    }
    if (!catalog) {
        return (
            <Centered>
                <Pulse label={UI.es.loading} />
            </Centered>
        );
    }

    const view = getView(catalog, viewKey);
    const available = LAYER_KEYS.filter(k => view.layers[k]);

    // Rango del corte según la región activa, en milímetros del dataset.
    const axisIdx = AXIS_SOURCE[clip.axis];
    const clipMin = Math.round(view.bounds.min[axisIdx]);
    const clipMax = Math.round(view.bounds.max[axisIdx]);
    const clipAt = Math.min(clipMax, Math.max(clipMin, clip.at));

    const measureMm =
        measurePoints.length === 2 ? measurePoints[0].distanceTo(measurePoints[1]) : null;
    const term: Term | undefined = selected ? terms[selected] : undefined;
    const name = term ? ((term[lang as keyof Term] as string) ?? term.en) : selected;

    const layerOf = available.find(k => view.layers[k]?.structures?.some(s => s.fma === selected));

    const index = buildSearchIndex(catalog, terms, lang);
    const results: SearchRow[] =
        query.trim().length < 2
            ? []
            : index.filter(r => r.haystack.includes(query.trim().toLowerCase())).slice(0, 40);

    const setLayer = (k: LayerKey, patch: Partial<LayerState>) =>
        setLayers(prev => ({ ...prev, [k]: { ...prev[k], ...patch } }));

    const peelTo = (depth: number) =>
        setLayers(prev => {
            const next = { ...prev };
            PEEL_ORDER.forEach((k, i) => {
                next[k] = { ...prev[k], visible: i <= depth };
            });
            return next;
        });

    const goTo = (row: SearchRow) => {
        setViewKey(row.region);
        setSelected(row.fma);
        setSearchOpen(false);
        setQuery('');
        setLayers(prev => ({ ...prev, [row.layer]: { ...prev[row.layer], visible: true } }));
        // La geometría de la región tarda en llegar: enfocar recién cuando esté.
        setTimeout(() => setFocusTarget(row.fma), 700);
    };

    /** Seleccionar desde el explorador: identifica y lleva la cámara a la pieza. */
    const selectAndFocus = (fma: string) => {
        setSelected(fma);
        setFocusTarget(fma);
    };

    const togglePick = (fma: string) =>
        setPicked(prev => {
            const next = new Set(prev);
            if (next.has(fma)) next.delete(fma);
            else next.add(fma);
            return next;
        });

    /** Tercer clic reinicia: medir siempre es entre dos puntos. */
    const addMeasurePoint = (p: THREE.Vector3) =>
        setMeasurePoints(prev => (prev.length >= 2 ? [p] : [...prev, p]));

    return (
        <div className="flex h-full flex-col">
            {/* ── Barra superior ─────────────────────────────────── */}
            <header className="border-rule bg-paper z-30 flex flex-wrap items-center gap-x-5 gap-y-2 border-b px-5 py-3">
                <div className="flex items-baseline gap-2">
                    <span className="bg-clay size-2.5 -translate-y-px rounded-[3px]" aria-hidden />
                    <span className="font-sans text-[15px] font-semibold tracking-tight">
                        {t.brand}
                    </span>
                    <span className="text-ink-faint font-mono text-[9.5px] tracking-[0.08em] uppercase">
                        anatómico
                    </span>
                </div>

                <nav className="ms-auto flex flex-wrap gap-0.5" aria-label={t.regions.label}>
                    <Chip active={viewKey === OVERVIEW} onClick={() => setViewKey(OVERVIEW)}>
                        {t.regions.overview}
                    </Chip>
                    {catalog.regions.map(r => (
                        <Chip
                            key={r.key}
                            active={viewKey === r.key}
                            onClick={() => setViewKey(r.key)}
                        >
                            {t.regions[r.key] ?? r.label}
                        </Chip>
                    ))}
                </nav>

                <div className="flex items-center gap-1">
                    <IconBtn label={t.search} onClick={() => setSearchOpen(true)}>
                        ⌕
                    </IconBtn>
                    <IconBtn
                        label={t.language}
                        onClick={() => setLang(LANGS[(LANGS.indexOf(lang) + 1) % LANGS.length])}
                    >
                        <span className="font-sans text-[10px] font-semibold uppercase">{lang}</span>
                    </IconBtn>
                    <IconBtn label={t.theme} onClick={() => setDark(v => !v)}>
                        ◐
                    </IconBtn>
                    <IconBtn label={t.settings} onClick={() => setSettingsOpen(true)}>
                        ⚙
                    </IconBtn>
                </div>
            </header>

            {/* ── Escenario ──────────────────────────────────────── */}
            <main
                className="relative flex-1 overflow-hidden"
                style={{
                    background:
                        'radial-gradient(120% 78% at 50% 6%, var(--stage-from), var(--stage-to))',
                }}
            >
                <div className="stage-grid text-ink pointer-events-none absolute inset-0" />

                <AnatomyCanvas
                    view={view}
                    layers={layers}
                    selected={selected}
                    isolate={picked}
                    resetNonce={resetNonce}
                    focusTarget={focusTarget}
                    clip={{ ...clip, at: clipAt }}
                    measuring={measuring}
                    measurePoints={measurePoints}
                    onPick={setSelected}
                    onMeasure={addMeasurePoint}
                    onStats={setStats}
                    onAnchor={setAnchor}
                    onMeasureLabel={setMeasureLabel}
                    onReady={() => setReady(true)}
                />

                {!ready && (
                    <div className="pointer-events-none absolute inset-0 grid place-items-center">
                        <Pulse label={t.loading} />
                    </div>
                )}

                {/* Línea de referencia: la convención de las láminas anatómicas */}
                {anchor && selected && (
                    <svg className="pointer-events-none absolute inset-0 h-full w-full">
                        <circle
                            cx={anchor.x}
                            cy={anchor.y}
                            r="13"
                            fill="none"
                            stroke="var(--clay)"
                            strokeWidth="1.2"
                        />
                        <line
                            x1={anchor.x + 13}
                            y1={anchor.y}
                            x2="calc(100% - 330px)"
                            y2={anchor.y}
                            stroke="var(--clay)"
                            strokeWidth="1"
                            strokeDasharray="3 3"
                            opacity="0.7"
                        />
                    </svg>
                )}

                {/* Pila de disección */}
                <section
                    className="panel absolute top-6 left-6 w-[238px] p-4"
                    aria-label={t.dissection}
                >
                    <h2 className="eyebrow mb-3">{t.dissection}</h2>

                    <div className="flex flex-col">
                        {[...PEEL_ORDER].reverse().map((k, i) => {
                            const chunk = view.layers[k];
                            const n = chunk?.structures?.length;
                            return (
                                <div
                                    key={k}
                                    className={`border-rule/60 py-1.5 ${i > 0 ? 'border-t' : ''} ${
                                        chunk ? '' : 'opacity-40'
                                    }`}
                                >
                                    <div className="flex items-center gap-2.5">
                                        <span
                                            className="size-2.5 shrink-0 rounded-[3px]"
                                            style={{ background: TISSUE_COLOR[k] }}
                                            aria-hidden
                                        />
                                        <button
                                            onClick={() => peelTo(PEEL_ORDER.indexOf(k))}
                                            disabled={!chunk}
                                            title={t.peel}
                                            className="hover:text-clay-ink flex-1 text-left font-sans text-[12.5px] transition-colors disabled:cursor-default"
                                        >
                                            {t.layers[k]}
                                        </button>
                                        <span className="text-ink-faint font-mono text-[10.5px] tabular-nums">
                                            {n ?? '—'}
                                        </span>
                                        <Switch
                                            checked={Boolean(chunk) && layers[k].visible}
                                            disabled={!chunk}
                                            onChange={v => setLayer(k, { visible: v })}
                                            label={t.layers[k]}
                                        />
                                    </div>
                                    <input
                                        type="range"
                                        min={8}
                                        max={100}
                                        value={layers[k].opacity * 100}
                                        disabled={!chunk || !layers[k].visible}
                                        onChange={e =>
                                            setLayer(k, { opacity: Number(e.target.value) / 100 })
                                        }
                                        aria-label={`${t.layers[k]} — opacidad`}
                                        className="accent-clay mt-1.5 h-1 w-full cursor-pointer disabled:cursor-default disabled:opacity-30"
                                    />
                                </div>
                            );
                        })}
                    </div>

                    {/* El pelado ya no es una fila de botones que desborda: se pela
                        haciendo clic en el nombre de la capa, arriba. */}
                    <p className="border-rule text-ink-faint mt-3 border-t pt-2.5 font-sans text-[10.5px] leading-relaxed">
                        {t.peelHint}
                    </p>

                    {/* ── Corte anatómico ── */}
                    <div className="border-rule mt-3 border-t pt-3">
                        <div className="mb-2 flex items-center gap-2">
                            <h3 className="eyebrow flex-1">{t.section}</h3>
                            <Switch
                                checked={clip.enabled}
                                onChange={v => setClip(c => ({ ...c, enabled: v }))}
                                label={t.section}
                            />
                        </div>

                        {clip.enabled && (
                            <>
                                <div className="flex gap-1">
                                    {(['sagittal', 'coronal', 'axial'] as ClipAxis[]).map(a => (
                                        <button
                                            key={a}
                                            onClick={() =>
                                                setClip(c => ({
                                                    ...c,
                                                    axis: a,
                                                    at: Math.round(
                                                        (view.bounds.min[AXIS_SOURCE[a]] +
                                                            view.bounds.max[AXIS_SOURCE[a]]) /
                                                            2
                                                    ),
                                                }))
                                            }
                                            aria-pressed={clip.axis === a}
                                            className={`flex-1 rounded-md border px-1 py-1 font-sans text-[10px] transition-colors ${
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
                                    onChange={e =>
                                        setClip(c => ({ ...c, at: Number(e.target.value) }))
                                    }
                                    aria-label={t.section}
                                    className="accent-clay mt-2 h-1 w-full cursor-pointer"
                                />
                                <button
                                    onClick={() => setClip(c => ({ ...c, flipped: !c.flipped }))}
                                    className="text-ink-faint hover:text-clay-ink mt-1 font-sans text-[10px] underline underline-offset-2"
                                >
                                    {t.flipSide}
                                </button>
                            </>
                        )}
                    </div>

                    {/* ── Medición ── */}
                    <div className="border-rule mt-3 border-t pt-3">
                        <div className="flex items-center gap-2">
                            <h3 className="eyebrow flex-1">{t.measure}</h3>
                            <Switch
                                checked={measuring}
                                onChange={v => {
                                    setMeasuring(v);
                                    if (!v) setMeasurePoints([]);
                                }}
                                label={t.measure}
                            />
                        </div>
                        <p className="text-ink-faint mt-1.5 font-sans text-[10px] leading-relaxed">
                            {measureMm
                                ? t.measureResult
                                      .replace('{mm}', measureMm.toFixed(1))
                                      .replace('{cm}', (measureMm / 10).toFixed(1))
                                : measuring
                                  ? t.measureHint
                                  : t.measureOff}
                        </p>
                    </div>
                </section>

                {/* Columna derecha: ficha arriba, explorador abajo */}
                <div className="absolute top-6 right-6 bottom-6 flex w-[300px] flex-col gap-3">
                <section
                    className="panel shrink-0 p-4"
                    aria-live="polite"
                    aria-label={t.structure}
                >
                    <h2 className="eyebrow mb-3">{t.structure}</h2>

                    {selected && term ? (
                        <>
                            <p className="text-[19px] leading-[1.24] text-balance">{name}</p>
                            {term.la && (
                                <p className="text-clay-ink mt-1 text-[13.5px] italic">{term.la}</p>
                            )}

                            <div className="mt-3 flex flex-wrap gap-1.5">
                                <Tag accent>{selected}</Tag>
                                {layerOf && <Tag>{t.layers[layerOf]}</Tag>}
                                {term.ta2 && <Tag>TA2 {term.ta2}</Tag>}
                            </div>

                            <div className="border-rule mt-3 grid gap-1 border-t pt-3">
                                {(['en', 'la', 'pt', 'fr', 'it'] as const)
                                    .filter(l => l !== lang && term[l])
                                    .slice(0, 4)
                                    .map(l => (
                                        <div
                                            key={l}
                                            className="grid grid-cols-[24px_1fr] gap-2 text-[12px]"
                                        >
                                            <code className="text-ink-faint font-mono text-[9.5px] uppercase">
                                                {l}
                                            </code>
                                            <span className={l === 'la' ? 'italic' : ''}>
                                                {term[l]}
                                            </span>
                                        </div>
                                    ))}
                            </div>

                            <div className="mt-3 flex gap-1.5">
                                <button
                                    onClick={() => setFocusTarget(selected)}
                                    className="border-rule hover:border-clay hover:text-clay-ink text-ink-soft flex-1 rounded-md border px-2 py-1.5 font-sans text-[11px] transition-colors"
                                >
                                    {t.focus}
                                </button>
                                <button
                                    onClick={() => togglePick(selected)}
                                    className={`flex-1 rounded-md border px-2 py-1.5 font-sans text-[11px] transition-colors ${
                                        picked.has(selected)
                                            ? 'bg-clay border-clay text-paper'
                                            : 'border-rule hover:border-clay hover:text-clay-ink text-ink-soft'
                                    }`}
                                >
                                    {picked.has(selected) ? t.showAll : t.isolate}
                                </button>
                            </div>
                        </>
                    ) : (
                        <p className="text-ink-faint text-[12.5px] leading-relaxed">
                            {t.emptySelection}
                        </p>
                    )}
                </section>

                <StructureBrowser
                    view={view}
                    terms={terms}
                    lang={lang}
                    t={t}
                    selected={selected}
                    picked={picked}
                    onSelect={selectAndFocus}
                    onTogglePick={togglePick}
                    onClearPicks={() => setPicked(new Set())}
                />
                </div>

                {/* Métricas */}
                <div className="text-ink-faint absolute bottom-5 left-6 grid gap-0.5 font-mono text-[10.5px] tabular-nums">
                    <div>
                        <b className="text-ink-soft font-medium">
                            {countStructures(view).toLocaleString(lang)}
                        </b>{' '}
                        {t.structures} ·{' '}
                        <b className="text-ink-soft font-medium">
                            {stats.tris.toLocaleString(lang)}
                        </b>{' '}
                        {t.triangles}
                    </div>
                    <div>
                        <b className="text-ink-soft font-medium">
                            {(countBytes(view) / 1024 / 1024).toFixed(2)} MB
                        </b>{' '}
                        {t.transferred} ·{' '}
                        <b className="text-ink-soft font-medium">{stats.fps}</b> FPS
                    </div>
                </div>

                {/* Pista de navegación: centrada entre los dos paneles, para
                    no chocar con la columna derecha. */}
                <div className="pointer-events-none absolute right-[318px] bottom-5 left-[262px] flex flex-col items-center gap-1">
                    <p className="text-ink-faint text-center font-sans text-[11px]">{t.hint}</p>
                    <button
                        onClick={() => setResetNonce(n => n + 1)}
                        className="text-ink-faint hover:text-clay-ink pointer-events-auto font-sans text-[11px] underline underline-offset-2 transition-colors"
                    >
                        {t.reset}
                    </button>
                </div>

                {/* Etiqueta de la medición, sobre el punto medio de la regla */}
                {measureLabel && measureMm && (
                    <div
                        className="border-clay bg-paper text-clay-ink pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-md border px-2 py-1 font-mono text-[11px] tabular-nums shadow-sm"
                        style={{ left: measureLabel.x, top: measureLabel.y }}
                    >
                        {measureMm.toFixed(1)} mm
                    </div>
                )}

                {/* Buscador */}
                {searchOpen && (
                    <div
                        className="absolute inset-0 z-40 grid place-items-start justify-center bg-black/25 pt-[14vh]"
                        onClick={() => setSearchOpen(false)}
                    >
                        <div
                            className="panel w-[520px] max-w-[92vw] overflow-hidden p-0"
                            onClick={e => e.stopPropagation()}
                        >
                            <input
                                autoFocus
                                value={query}
                                onChange={e => setQuery(e.target.value)}
                                placeholder={t.searchPlaceholder}
                                aria-label={t.search}
                                className="border-rule w-full border-b bg-transparent px-4 py-3 text-[14px] outline-none"
                            />
                            <div className="max-h-[46vh] overflow-y-auto">
                                {results.map(r => (
                                    <button
                                        key={r.fma}
                                        onClick={() => goTo(r)}
                                        className="hover:bg-sunk flex w-full items-baseline gap-3 px-4 py-2 text-left"
                                    >
                                        <span
                                            className="size-2 shrink-0 translate-y-px rounded-[2px]"
                                            style={{ background: TISSUE_COLOR[r.layer] }}
                                        />
                                        <span className="flex-1 text-[13px]">{r.label}</span>
                                        <span className="text-ink-faint font-sans text-[10px]">
                                            {t.regions[r.region] ?? r.regionLabel}
                                        </span>
                                    </button>
                                ))}
                                {query.trim().length >= 2 && !results.length && (
                                    <p className="text-ink-faint px-4 py-6 text-center text-[12.5px]">
                                        {t.noResults}
                                    </p>
                                )}
                            </div>
                        </div>
                    </div>
                )}
                <SettingsModal
                    open={settingsOpen}
                    t={t}
                    lang={lang}
                    source={source}
                    available={sources}
                    meta={SOURCE_META}
                    onPick={s => {
                        setSource(s);
                        setSettingsOpen(false);
                    }}
                    onClose={() => setSettingsOpen(false)}
                />
            </main>

            <footer className="border-rule text-ink-faint border-t px-5 py-2 text-[10.5px]">
                {SOURCE_INFO[source].attribution}
            </footer>
        </div>
    );
}

/* ── Piezas de interfaz ─────────────────────────────────────────── */

function Chip({
    active,
    onClick,
    children,
}: {
    active?: boolean;
    onClick: () => void;
    children: React.ReactNode;
}) {
    return (
        <button
            onClick={onClick}
            aria-pressed={active}
            className={`rounded-full px-3 py-1.5 font-sans text-[12.5px] transition-colors ${
                active ? 'bg-clay text-paper' : 'text-ink-soft hover:bg-sunk hover:text-ink'
            }`}
        >
            {children}
        </button>
    );
}

function IconBtn({
    label,
    onClick,
    children,
}: {
    label: string;
    onClick: () => void;
    children: React.ReactNode;
}) {
    return (
        <button
            onClick={onClick}
            title={label}
            aria-label={label}
            className="border-rule bg-surface text-ink-soft hover:border-clay hover:text-clay-ink grid size-8 place-items-center rounded-lg border transition-colors"
        >
            {children}
        </button>
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
            className={`relative h-[17px] w-[30px] shrink-0 rounded-full transition-colors disabled:cursor-default ${
                checked ? 'bg-clay' : 'bg-rule'
            }`}
        >
            <span
                className={`bg-surface absolute top-0.5 size-[13px] rounded-full shadow-sm transition-transform ${
                    checked ? 'translate-x-[15px]' : 'translate-x-0.5'
                }`}
            />
        </button>
    );
}

function Tag({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
    return (
        <span
            className={`rounded-[5px] border px-1.5 py-0.5 font-mono text-[9.5px] tracking-wide ${
                accent
                    ? 'border-clay/35 bg-clay/12 text-clay-ink'
                    : 'border-rule/70 bg-sunk text-ink-soft'
            }`}
        >
            {children}
        </span>
    );
}

function Centered({ children }: { children: React.ReactNode }) {
    return <div className="grid h-full place-items-center px-6 text-center">{children}</div>;
}

function Pulse({ label }: { label: string }) {
    return (
        <div className="flex items-center gap-2.5">
            <span className="bg-clay size-2 animate-ping rounded-full" />
            <span className="text-ink-faint font-sans text-[12.5px]">{label}…</span>
        </div>
    );
}
