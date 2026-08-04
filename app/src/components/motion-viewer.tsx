import { Suspense, useEffect, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import type { Strings } from '../lib/i18n';
import type { QualityProfile } from '../lib/quality';
import { DRACO_PATH, asset } from '../lib/asset-url';

/**
 * Visor de movimiento.
 *
 * El pipeline hornea el movimiento del rig de Z-Biomechanics a transformaciones
 * de objeto, así que cada una de las 271 mallas del esqueleto trae su propia
 * animación. Blender emite una por malla en vez de una con 271 canales, así que
 * acá se reproducen TODAS a la vez sobre el mismo mixer — comparten duración.
 */

const DRACO = DRACO_PATH;

/**
 * El GLB de movimiento quedó en metros: las curvas de animación horneadas
 * conservan la escala original de Blender. Es el mismo factor que alinea
 * Z-Anatomy con BodyParts3D (ver pipeline/measure_registration.py).
 */
const MM_PER_UNIT = 968.3;

export interface MotionClip {
    key: string;
    es: string;
    en: string;
    file: string;
    bytes: number;
    frames: number;
    meshes: number;
}

export interface MotionCatalog {
    clips: MotionClip[];
    attribution: string;
}

export async function loadMotion(): Promise<MotionCatalog> {
    const r = await fetch(asset('anatomy/motion/catalog.json'));
    if (!r.ok) throw new Error(`motion/catalog.json: ${r.status}`);
    return (await r.json()) as MotionCatalog;
}

export async function motionAvailable(): Promise<boolean> {
    try {
        const r = await fetch(asset('anatomy/motion/catalog.json'));
        if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) return false;
        const b = (await r.json()) as Partial<MotionCatalog>;
        return Array.isArray(b.clips) && b.clips.length > 0;
    } catch {
        return false;
    }
}

const BONE = new THREE.MeshStandardMaterial({
    color: '#e6e0d0',
    roughness: 0.62,
    metalness: 0,
});

function Skeleton({
    clip,
    playing,
    speed,
    onDuration,
    onTime,
    seekTo,
}: {
    clip: MotionClip;
    playing: boolean;
    speed: number;
    onDuration: (d: number) => void;
    onTime: (t: number) => void;
    seekTo: number | null;
}) {
    const { scene, animations } = useGLTF(clip.file, DRACO);
    const [root] = useState(() => scene.clone(true));
    const mixer = useRef<THREE.AnimationMixer | null>(null);

    useEffect(() => {
        root.traverse(o => {
            const m = o as THREE.Mesh;
            if (m.isMesh) m.material = BONE;
        });

        const mx = new THREE.AnimationMixer(root);
        let longest = 0;
        for (const a of animations) {
            mx.clipAction(a).play();
            longest = Math.max(longest, a.duration);
        }
        mixer.current = mx;
        onDuration(longest);

        return () => {
            mx.stopAllAction();
            mixer.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [root, animations]);

    // Arrastrar la línea de tiempo: se fija el tiempo con delta 0.
    useEffect(() => {
        if (seekTo === null || !mixer.current) return;
        mixer.current.setTime(seekTo);
    }, [seekTo]);

    useFrame((_, dt) => {
        const mx = mixer.current;
        if (!mx) return;
        if (playing) mx.update(dt * speed);
        onTime(mx.time);
    });

    return <primitive object={root} />;
}

function Frame() {
    const { camera } = useThree();
    const controls = useThree(s => s.controls) as
        | { target: THREE.Vector3; update(): void; minDistance: number; maxDistance: number }
        | null;
    useEffect(() => {
        if (!controls) return;
        // Tras escalar, el esqueleto mide ~1740 mm; se apunta a media altura
        // y se mira de frente y algo elevado.
        controls.target.set(0, 870, 0);
        camera.position.set(500, 1050, 2400);
        controls.minDistance = 200;
        controls.maxDistance = 9000;
        controls.update();
    }, [camera, controls]);
    return null;
}

export function MotionViewer({
    t,
    lang,
    profile,
}: {
    t: Strings;
    lang: string;
    profile: QualityProfile;
}) {
    const [catalog, setCatalog] = useState<MotionCatalog | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [key, setKey] = useState<string | null>(null);
    const [playing, setPlaying] = useState(true);
    const [speed, setSpeed] = useState(1);
    const [duration, setDuration] = useState(0);
    const [time, setTime] = useState(0);
    const [seekTo, setSeekTo] = useState<number | null>(null);

    useEffect(() => {
        loadMotion()
            .then(c => {
                setCatalog(c);
                setKey(c.clips[0]?.key ?? null);
            })
            .catch(e => setError(String(e?.message ?? e)));
    }, []);

    if (error) {
        return (
            <div className="grid h-full place-items-center px-6 text-center">
                <p className="text-ink-faint font-mono text-xs">{error}</p>
            </div>
        );
    }
    if (!catalog) {
        return (
            <div className="grid h-full place-items-center">
                <span className="bg-clay size-2 animate-ping rounded-full" />
            </div>
        );
    }

    const clip = catalog.clips.find(c => c.key === key) ?? catalog.clips[0];
    const pct = duration ? Math.min(100, (time % duration) / duration * 100) : 0;

    return (
        // Igual que la galería: en chico va el modelo arriba y la lista de
        // clips debajo, en una sola columna.
        <div className="grid h-full auto-rows-min grid-cols-1 gap-3 overflow-y-auto p-3 lg:auto-rows-auto lg:grid-cols-[240px_1fr] lg:gap-5 lg:overflow-hidden lg:p-5">
            <aside className="panel order-2 flex max-h-[42svh] min-h-0 flex-col overflow-hidden lg:order-none lg:max-h-none">
                <h2 className="eyebrow border-rule border-b px-4 py-3">{t.motionClips}</h2>
                <div className="min-h-0 flex-1 overflow-y-auto py-1">
                    {catalog.clips.map(c => (
                        <button
                            key={c.key}
                            onClick={() => {
                                setKey(c.key);
                                setTime(0);
                                setSeekTo(0);
                            }}
                            aria-pressed={c.key === clip.key}
                            className={`flex w-full items-baseline gap-2 px-4 py-2.5 text-left transition-colors ${
                                c.key === clip.key ? 'bg-clay/10' : 'hover:bg-sunk'
                            }`}
                        >
                            <span
                                className={`flex-1 text-[14px] ${
                                    c.key === clip.key ? 'text-clay-ink' : ''
                                }`}
                            >
                                {lang === 'en' ? c.en : c.es}
                            </span>
                            <span className="text-ink-faint font-mono text-[10px] tabular-nums">
                                {(c.bytes / 1024 / 1024).toFixed(1)} MB
                            </span>
                        </button>
                    ))}
                </div>
                <p className="text-ink-faint border-rule border-t px-4 py-3 font-sans text-[10.5px] leading-relaxed">
                    {t.motionHint.replace('{n}', String(clip.meshes))}
                </p>
            </aside>

            <div
                className="panel relative order-1 h-[52svh] overflow-hidden lg:order-none lg:h-auto"
                style={{
                    background:
                        'radial-gradient(120% 90% at 50% 4%, var(--stage-from), var(--stage-to))',
                }}
            >
                <div className="stage-grid text-ink pointer-events-none absolute inset-0" />

                {/* La key sólo depende del antialias, que es un parámetro de
                    creación del contexto. Antes incluía el clip y el nivel, así
                    que cada cambio remontaba el Canvas y pedía un contexto WebGL
                    nuevo; el navegador mantiene ~16 y descartaba los viejos —
                    de ahí los "Context Lost" en cadena. El dpr sí es reactivo. */}
                <Canvas
                    key={profile.antialias ? 'aa' : 'noaa'}
                    camera={{ fov: 40, near: 1, far: 20000 }}
                    dpr={[1, profile.dpr]}
                    gl={{ antialias: profile.antialias, powerPreference: 'high-performance' }}
                >
                    <ambientLight intensity={0.66} />
                    <hemisphereLight args={['#dbeaf5', '#2a1f18', 0.55]} />
                    <directionalLight position={[900, 1600, 1400]} intensity={1.6} />
                    <directionalLight position={[-800, 600, -900]} intensity={0.5} color="#9dbcd8" />

                    <Suspense fallback={null}>
                        {/* Sin rotación: el exportador de Blender salió con
                            export_yup, así que el GLB ya está en Y-up — rotarlo
                            otra vez lo acostaba.

                            La escala va acá y no en el pipeline: las curvas de
                            animación horneadas sobrescriben la transformación
                            de cada objeto en el primer cuadro, así que escalar
                            los objetos antes de exportar no tenía efecto. Un
                            grupo padre sí escala todo, animación incluida. */}
                        <group scale={MM_PER_UNIT}>
                            <Skeleton
                                key={clip.file}
                                clip={clip}
                                playing={playing}
                                speed={speed}
                                onDuration={setDuration}
                                onTime={setTime}
                                seekTo={seekTo}
                            />
                        </group>
                    </Suspense>

                    <OrbitControls
                        makeDefault
                        enableDamping
                        dampingFactor={profile.damping}
                        enablePan
                        zoomToCursor
                    />
                    <Frame />
                </Canvas>

                {/* Transporte */}
                <div className="panel absolute right-2 bottom-2 left-2 flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5 lg:right-6 lg:bottom-6 lg:left-6 lg:flex-nowrap lg:gap-4 lg:px-4 lg:py-3">
                    <button
                        onClick={() => setPlaying(p => !p)}
                        aria-label={playing ? t.pause : t.play}
                        className="border-rule hover:border-clay hover:text-clay-ink grid size-9 shrink-0 place-items-center rounded-full border transition-colors"
                    >
                        {playing ? '❚❚' : '▶'}
                    </button>

                    <input
                        type="range"
                        min={0}
                        max={1000}
                        value={pct * 10}
                        onChange={e => {
                            const v = (Number(e.target.value) / 1000) * duration;
                            setPlaying(false);
                            setSeekTo(v);
                        }}
                        aria-label={t.timeline}
                        className="accent-clay h-1 flex-1 cursor-pointer"
                    />

                    <span className="text-ink-faint w-16 shrink-0 text-right font-mono text-[10.5px] tabular-nums">
                        {(time % (duration || 1)).toFixed(1)}s
                    </span>

                    <div className="border-rule flex shrink-0 gap-0.5 rounded-full border p-0.5">
                        {[0.25, 0.5, 1].map(s => (
                            <button
                                key={s}
                                onClick={() => setSpeed(s)}
                                aria-pressed={speed === s}
                                className={`rounded-full px-2.5 py-0.5 font-mono text-[10.5px] transition-colors ${
                                    speed === s
                                        ? 'bg-clay text-paper'
                                        : 'text-ink-soft hover:text-ink'
                                }`}
                            >
                                {s}×
                            </button>
                        ))}
                    </div>
                </div>

                <p className="text-ink-faint pointer-events-none absolute top-5 left-6 font-mono text-[10.5px]">
                    {clip.meshes} {t.structures} · {clip.frames} {t.motionFrames}
                </p>
            </div>
        </div>
    );
}
