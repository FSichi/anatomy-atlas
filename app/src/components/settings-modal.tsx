import { SOURCE_INFO, type SourceId } from '../lib/catalog';
import type { Strings } from '../lib/i18n';

/**
 * Modal de configuración. Hoy sólo elige la fuente de datos anatómicos, que es
 * la decisión con más impacto: cambia qué estructuras existen en el modelo.
 */

export interface SourceMeta {
    id: SourceId;
    structures: number;
    megabytes: number;
    /** Puntos fuertes y flojos, para que la elección sea informada. */
    strong: string[];
    weak: string[];
}

export function SettingsModal({
    open,
    t,
    lang,
    source,
    available,
    meta,
    showBrowser,
    onPick,
    onToggleBrowser,
    onClose,
}: {
    open: boolean;
    t: Strings;
    lang: string;
    source: SourceId;
    available: SourceId[];
    meta: Record<string, SourceMeta | undefined>;
    showBrowser: boolean;
    onPick: (s: SourceId) => void;
    onToggleBrowser: (v: boolean) => void;
    onClose: () => void;
}) {
    if (!open) return null;

    // En español el decimal va con coma: "18,4 MB", no "18.4 MB".
    const mb = (n: number) => n.toLocaleString(lang, { minimumFractionDigits: 1 });

    return (
        <div
            className="scrim fixed inset-0 z-50 grid place-items-center px-6"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-label={t.settings}
        >
            <div
                className="sheet w-[620px] max-w-full overflow-hidden"
                onClick={e => e.stopPropagation()}
            >
                <div className="border-rule flex items-baseline gap-3 border-b px-5 py-3.5">
                    <h2 className="flex-1 font-sans text-[15px] font-semibold">{t.settings}</h2>
                    <button
                        onClick={onClose}
                        className="text-ink-soft hover:text-ink font-sans text-[12px]"
                    >
                        {t.close}
                    </button>
                </div>

                <div className="px-5 py-4">
                    <h3 className="eyebrow">{t.dataSource}</h3>
                    <p className="text-ink-soft mt-1.5 text-[12.5px] leading-relaxed">
                        {t.dataSourceHint}
                    </p>

                    <div className="mt-4 grid gap-2">
                        {(Object.keys(SOURCE_INFO) as SourceId[]).map(id => {
                            const enabled = available.includes(id);
                            const m = meta[id];
                            const active = source === id;
                            return (
                                <button
                                    key={id}
                                    disabled={!enabled}
                                    onClick={() => onPick(id)}
                                    aria-pressed={active}
                                    className={`rounded-lg border p-3 text-left transition-colors ${
                                        active
                                            ? 'border-clay bg-clay/8'
                                            : enabled
                                              ? 'border-rule hover:border-clay/50'
                                              : 'border-rule opacity-45'
                                    }`}
                                >
                                    <div className="flex items-baseline gap-2">
                                        <span className="font-sans text-[13.5px] font-medium">
                                            {t.sources[id]}
                                        </span>
                                        {m && (
                                            <span className="text-ink-faint font-mono text-[10.5px] tabular-nums">
                                                {m.structures.toLocaleString(lang)} ·{' '}
                                                {mb(m.megabytes)} MB
                                            </span>
                                        )}
                                        {!enabled && (
                                            <span className="text-ink-faint ms-auto font-sans text-[10.5px]">
                                                {t.notGenerated}
                                            </span>
                                        )}
                                    </div>

                                    <p className="text-ink-soft mt-1 text-[12px] leading-relaxed">
                                        {t.sourceDesc[id]}
                                    </p>

                                    {m && (
                                        <div className="mt-2.5 flex flex-wrap gap-1">
                                            {m.strong.map(s => (
                                                <span
                                                    key={s}
                                                    className="rounded-[4px] border px-1.5 py-0.5 font-mono text-[10px]"
                                                    style={{
                                                        color: 'var(--good)',
                                                        background: 'var(--good-bg)',
                                                        borderColor: 'var(--good-line)',
                                                    }}
                                                >
                                                    + {s}
                                                </span>
                                            ))}
                                            {m.weak.map(s => (
                                                <span
                                                    key={s}
                                                    className="border-rule bg-sunk text-ink-faint rounded-[4px] border px-1.5 py-0.5 font-mono text-[10px]"
                                                >
                                                    − {s}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    <h3 className="eyebrow border-rule mt-5 border-t pt-4">{t.panels}</h3>
                    <label className="mt-2.5 flex cursor-pointer items-center gap-3">
                        <span className="flex-1">
                            <span className="block font-sans text-[13px]">{t.browser}</span>
                            <span className="text-ink-soft block text-[12px] leading-relaxed">
                                {t.browserToggleHint}
                            </span>
                        </span>
                        <button
                            role="switch"
                            aria-checked={showBrowser}
                            aria-label={t.browser}
                            onClick={() => onToggleBrowser(!showBrowser)}
                            className={`relative h-[18px] w-[32px] shrink-0 rounded-full transition-colors ${
                                showBrowser ? 'bg-clay' : 'bg-rule'
                            }`}
                        >
                            <span
                                className={`bg-surface absolute top-0.5 size-[14px] rounded-full shadow-sm transition-transform ${
                                    showBrowser ? 'translate-x-[16px]' : 'translate-x-0.5'
                                }`}
                            />
                        </button>
                    </label>

                    <p className="text-ink-faint border-rule mt-5 border-t pt-3 text-[11px] leading-relaxed">
                        {SOURCE_INFO[source].attribution}
                    </p>
                </div>
            </div>
        </div>
    );
}
