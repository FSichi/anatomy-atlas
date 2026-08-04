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
import { OrganGallery } from './components/organ-gallery';
import { DissectionPanel } from './components/dissection-panel';
import { organsAvailable } from './lib/organs';
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
    const [showBrowser, setShowBrowser] = useState(true);
    const [mode, setMode] = useState<'atlas' | 'organs'>('atlas');
    const [hasOrgans, setHasOrgans] = useState(false);

    useEffect(() => {
        organsAvailable().then(setHasOrgans);
    }, []);

    // Posiciones reales de la ficha y del escenario, para trazar la referencia.
    const cardRef = useRef<HTMLElement>(null);
    const stageRef = useRef<HTMLElement>(null);
    const [cardRect, setCardRect] = useState<DOMRect | null>(null);
    const [stageRect, setStageRect] = useState<DOMRect | null>(null);

    useEffect(() => {
        const measure = () => {
            setCardRect(cardRef.current?.getBoundingClientRect() ?? null);
            setStageRect(stageRef.current?.getBoundingClientRect() ?? null);
        };
        measure();
        addEventListener('resize', measure);
        const id = setInterval(measure, 400);
        return () => {
            removeEventListener('resize', measure);
            clearInterval(id);
        };
    }, []);

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

    /**
     * Geometría de la línea de referencia. Se calcula contra la posición real
     * de la ficha en pantalla, no contra un margen fijo: la ficha cambia de alto
     * según lo seleccionado, y una coordenada hardcodeada la deja apuntando a
     * cualquier lado. Se omite si la estructura queda detrás de la ficha.
     */
    const term: Term | undefined = selected ? terms[selected] : undefined;
    const name = term ? ((term[lang as keyof Term] as string) ?? term.en) : selected;

    let leader: {
        x: number;
        y: number;
        elbow: number;
        cardX: number;
        cardY: number;
    } | null = null;

    if (anchor && selected && term && cardRect && stageRect) {
        const cardX = cardRect.left - stageRect.left;
        const cardY = cardRect.top - stageRect.top + 26;
        const elbow = cardX - 28;
        // Si la estructura quedó a la derecha del codo, la línea se cruzaría
        // sobre sí misma: mejor no dibujarla.
        if (anchor.x + 26 < elbow) {
            leader = { x: anchor.x, y: anchor.y, elbow, cardX, cardY };
        }
    }

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

                {hasOrgans && (
                    <div className="border-rule flex gap-0.5 rounded-full border p-0.5">
                        {(['atlas', 'organs'] as const).map(m => (
                            <button
                                key={m}
                                onClick={() => setMode(m)}
                                aria-pressed={mode === m}
                                className={`rounded-full px-3 py-1 font-sans text-[12px] transition-colors ${
                                    mode === m
                                        ? 'bg-clay text-paper'
                                        : 'text-ink-soft hover:text-ink'
                                }`}
                            >
                                {m === 'atlas' ? t.modeAtlas : t.modeOrgans}
                            </button>
                        ))}
                    </div>
                )}

                <nav
                    className={`ms-auto flex flex-wrap gap-0.5 ${mode === 'organs' ? 'invisible' : ''}`}
                    aria-label={t.regions.label}
                    aria-hidden={mode === 'organs'}
                >
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
            {mode === 'organs' ? (
                <main className="min-h-0 flex-1">
                    <OrganGallery t={t} lang={lang} />
                </main>
            ) : (
            <main
                ref={stageRef}
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

                {/* Línea de referencia: la convención de las láminas anatómicas.
                    Va en codo desde la estructura hasta el borde de la ficha —
                    una línea que termina en el vacío no señala nada. */}
                {leader && (
                    <svg className="pointer-events-none absolute inset-0 h-full w-full">
                        <circle
                            cx={leader.x}
                            cy={leader.y}
                            r="13"
                            fill="none"
                            stroke="var(--clay)"
                            strokeWidth="1.2"
                        />
                        <polyline
                            points={[
                                `${leader.x + 13},${leader.y}`,
                                `${leader.elbow},${leader.y}`,
                                `${leader.elbow},${leader.cardY}`,
                                `${leader.cardX},${leader.cardY}`,
                            ].join(' ')}
                            fill="none"
                            stroke="var(--clay)"
                            strokeWidth="1"
                            strokeDasharray="3 3"
                            opacity="0.75"
                        />
                        <circle cx={leader.cardX} cy={leader.cardY} r="2.5" fill="var(--clay)" />
                    </svg>
                )}

                <DissectionPanel
                    t={t}
                    view={view}
                    layers={layers}
                    clip={clip}
                    clipMin={clipMin}
                    clipMax={clipMax}
                    clipAt={clipAt}
                    measuring={measuring}
                    measureMm={measureMm}
                    onLayer={setLayer}
                    onPeel={peelTo}
                    onClip={patch => setClip(c => ({ ...c, ...patch }))}
                    onMeasuring={v => {
                        setMeasuring(v);
                        if (!v) setMeasurePoints([]);
                    }}
                />
                {/* Columna derecha: ficha arriba, explorador abajo */}
                <div className="absolute top-7 right-7 bottom-7 flex w-[322px] flex-col gap-4">
                <section
                    ref={cardRef}
                    className="panel shrink-0 p-5"
                    aria-live="polite"
                    aria-label={t.structure}
                >
                    <h2 className="eyebrow mb-3.5">{t.structure}</h2>

                    {selected && term ? (
                        <>
                            <p className="text-[21px] leading-[1.2] text-balance">{name}</p>
                            {term.la && (
                                <p className="text-clay-ink mt-1.5 text-[14px] italic">{term.la}</p>
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

                {showBrowser && (
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
                )}
                </div>

                {/* Métricas */}
                <div className="text-ink-faint absolute bottom-6 left-7 grid gap-0.5 font-mono text-[10.5px] tabular-nums">
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
                <div className="pointer-events-none absolute right-[344px] bottom-6 left-[300px] flex flex-col items-center gap-1">
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
            </main>
            )}

            {/* Fuera del escenario: el modal tiene que abrirse en los dos modos. */}
            <SettingsModal
                open={settingsOpen}
                t={t}
                lang={lang}
                source={source}
                available={sources}
                meta={SOURCE_META}
                showBrowser={showBrowser}
                onPick={s => {
                    setSource(s);
                    setSettingsOpen(false);
                }}
                onToggleBrowser={setShowBrowser}
                onClose={() => setSettingsOpen(false)}
            />

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
