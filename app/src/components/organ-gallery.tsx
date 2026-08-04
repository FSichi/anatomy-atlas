import { Suspense, useEffect, useRef, useState } from 'react';
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { OrbitControls, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import {
    ORGAN_CATEGORIES,
    TISSUE_SWATCH,
    loadOrgans,
    type OrganCategory,
    type Organ,
    type OrganCatalog,
} from '../lib/organs';
import type { Strings } from '../lib/i18n';
import type { QualityProfile } from '../lib/quality';

/**
 * Galería de órganos: un órgano por vez, a máxima resolución.
 *
 * La oclusión ambiental viene horneada en los colores de vértice desde el
 * pipeline, así que el material sólo tiene que multiplicarla — sin luces
 * elaboradas ni post-proceso, el volumen ya está en la geometría.
 */

const DRACO = '/draco/';

const HIGHLIGHT = new THREE.MeshStandardMaterial({
    color: '#3ad0bb',
    emissive: '#137a6e',
    emissiveIntensity: 0.5,
    roughness: 0.3,
});

/**
 * Material de tejido.
 *
 * En calidad alta se cambia a MeshPhysicalMaterial: `clearcoat` da la película
 * húmeda que tiene una víscera fresca y `sheen` el rebote suave de superficie
 * traslúcida. Sin eso, un difuso plano se lee como plástico por más geometría
 * que tenga. No se usa `transmission` porque un órgano no es vidrio: lo
 * volvería transparente en vez de húmedo.
 */
function tissueMaterial(src: THREE.MeshStandardMaterial, physical: boolean) {
    if (!physical) {
        src.vertexColors = true;
        src.roughness = 0.42;
        src.metalness = 0;
        src.needsUpdate = true;
        return src;
    }
    const m = new THREE.MeshPhysicalMaterial({
        color: src.color,
        vertexColors: true,
        roughness: 0.38,
        metalness: 0,
        clearcoat: 0.45,
        clearcoatRoughness: 0.35,
        sheen: 0.5,
        sheenRoughness: 0.7,
        sheenColor: new THREE.Color('#e3a08c'),
        side: THREE.FrontSide,
    });
    return m;
}

function OrganMesh({
    organ,
    physical,
    selected,
    onPick,
}: {
    organ: Organ;
    physical: boolean;
    selected: string | null;
    onPick: (fma: string | null) => void;
}) {
    const { scene } = useGLTF(organ.file, DRACO);
    const [root] = useState(() => scene.clone(true));
    const base = useRef(new Map<string, THREE.Material>());

    useEffect(() => {
        base.current.clear();
        root.traverse(o => {
            const m = o as THREE.Mesh;
            if (!m.isMesh) return;
            const mat = tissueMaterial(m.material as THREE.MeshStandardMaterial, physical);
            base.current.set(m.uuid, mat);
            m.material = mat;
        });
    }, [root, physical]);

    useEffect(() => {
        root.traverse(o => {
            const m = o as THREE.Mesh;
            if (!m.isMesh) return;
            const original = base.current.get(m.uuid);
            if (original) m.material = m.name === selected ? HIGHLIGHT : original;
        });
    }, [root, selected]);

    return (
        <primitive
            object={root}
            onPointerDown={(e: ThreeEvent<PointerEvent>) => {
                const n = (e.object as THREE.Mesh).name;
                if (!n) return;
                e.stopPropagation();
                onPick(n);
            }}
        />
    );
}

function Spin({ on }: { on: boolean }) {
    const { scene } = useThree();
    useFrame((_, dt) => {
        if (on) scene.rotation.y += dt * 0.25;
    });
    return null;
}

function Frame({ radius }: { radius: number }) {
    const { camera } = useThree();
    const controls = useThree(s => s.controls) as { target: THREE.Vector3; update(): void; minDistance: number; maxDistance: number } | null;
    useEffect(() => {
        if (!controls) return;
        const d = radius * 3.2 + 40;
        camera.position.set(d * 0.18, d * 0.1, d);
        controls.target.set(0, 0, 0);
        controls.minDistance = radius * 0.5;
        controls.maxDistance = d * 3;
        controls.update();
    }, [radius, camera, controls]);
    return null;
}

export function OrganGallery({
    t,
    lang,
    profile,
}: {
    t: Strings;
    lang: string;
    profile: QualityProfile;
}) {
    const [catalog, setCatalog] = useState<OrganCatalog | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [cat, setCat] = useState<OrganCategory>('organ');
    const [activeKey, setActiveKey] = useState<string | null>(null);
    const [selected, setSelected] = useState<string | null>(null);
    const [spin, setSpin] = useState(false);

    useEffect(() => {
        loadOrgans()
            .then(c => {
                setCatalog(c);
                setActiveKey(c.organs[0]?.key ?? null);
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

    const inCat = catalog.organs.filter(o => o.cat === cat);
    const organ =
        inCat.find(o => o.key === activeKey) ?? inCat[0] ?? catalog.organs[0];
    const part = organ.structures.find(s => s.fma === selected);

    return (
        <div className="grid h-full grid-cols-[240px_1fr_300px] gap-5 p-5">
            {/* Biblioteca */}
            <aside className="panel flex min-h-0 flex-col overflow-hidden">
                <h2 className="eyebrow border-rule border-b px-4 py-3">{t.organLibrary}</h2>

                <div className="border-rule flex gap-1 border-b px-3 py-2">
                    {ORGAN_CATEGORIES.filter(c => catalog.organs.some(o => o.cat === c)).map(c => (
                        <button
                            key={c}
                            onClick={() => setCat(c)}
                            aria-pressed={cat === c}
                            className={`flex-1 rounded-full border px-2 py-1 font-sans text-[11px] transition-colors ${
                                cat === c
                                    ? 'border-clay bg-clay/12 text-clay-ink'
                                    : 'border-rule text-ink-soft hover:border-clay/50'
                            }`}
                        >
                            {t.organCats[c]}
                        </button>
                    ))}
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto py-1">
                    {catalog.organs.filter(o => o.cat === cat).map(o => {
                        const active = o.key === organ.key;
                        return (
                            <button
                                key={o.key}
                                onClick={() => {
                                    setActiveKey(o.key);
                                    setSelected(null);
                                }}
                                aria-pressed={active}
                                className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                                    active ? 'bg-clay/10' : 'hover:bg-sunk'
                                }`}
                            >
                                <span
                                    aria-hidden
                                    className="size-7 shrink-0 rounded-full"
                                    style={{
                                        background: `radial-gradient(circle at 32% 28%, ${
                                            TISSUE_SWATCH[o.structures[0]?.tissue] ?? '#b84a45'
                                        }, color-mix(in srgb, ${
                                            TISSUE_SWATCH[o.structures[0]?.tissue] ?? '#b84a45'
                                        } 55%, #000))`,
                                    }}
                                />
                                <span className="min-w-0 flex-1">
                                    <span
                                        className={`block truncate text-[14px] ${
                                            active ? 'text-clay-ink' : ''
                                        }`}
                                    >
                                        {lang === 'en' ? o.en : o.es}
                                    </span>
                                    <span className="text-ink-faint block font-sans text-[10.5px]">
                                        {o.system}
                                    </span>
                                </span>
                            </button>
                        );
                    })}
                </div>
            </aside>

            {/* Escenario */}
            <div
                className="panel relative overflow-hidden"
                style={{
                    background:
                        'radial-gradient(120% 90% at 50% 4%, var(--stage-from), var(--stage-to))',
                }}
            >
                <div className="stage-grid text-ink pointer-events-none absolute inset-0" />

                <Canvas
                    key={`${organ.key}-${profile.level}`}
                    camera={{ fov: 38, near: 0.5, far: 6000 }}
                    dpr={[1, profile.dpr]}
                    gl={{ antialias: profile.antialias, powerPreference: 'high-performance' }}
                    onPointerMissed={() => setSelected(null)}
                >
                    <ambientLight intensity={0.62} />
                    <hemisphereLight args={['#dbeaf5', '#2a1f18', 0.6]} />
                    <directionalLight position={[180, 140, 220]} intensity={1.55} />
                    <directionalLight position={[-160, 40, -140]} intensity={0.5} color="#9dbcd8" />
                    <directionalLight position={[0, -180, 60]} intensity={0.3} color="#ffd2b8" />

                    <Suspense fallback={null}>
                        <group rotation={[-Math.PI / 2, 0, 0]}>
                            <OrganMesh
                                organ={organ}
                                physical={profile.material === 'physical'}
                                selected={selected}
                                onPick={setSelected}
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
                    <Frame radius={organ.radius} />
                    <Spin on={spin} />
                </Canvas>

                <div className="text-ink-faint absolute bottom-4 left-5 font-mono text-[10.5px] tabular-nums">
                    {organ.tris.toLocaleString(lang)} {t.triangles} ·{' '}
                    {(organ.bytes / 1024 / 1024).toFixed(2)} MB
                </div>

                <label className="absolute right-5 bottom-4 flex cursor-pointer items-center gap-2 font-sans text-[11px]">
                    <span className="text-ink-faint">{t.autoRotate}</span>
                    <button
                        role="switch"
                        aria-checked={spin}
                        aria-label={t.autoRotate}
                        onClick={() => setSpin(v => !v)}
                        className={`relative h-[16px] w-[28px] rounded-full transition-colors ${
                            spin ? 'bg-clay' : 'bg-rule'
                        }`}
                    >
                        <span
                            className={`bg-surface absolute top-0.5 size-[12px] rounded-full shadow-sm transition-transform ${
                                spin ? 'translate-x-[14px]' : 'translate-x-0.5'
                            }`}
                        />
                    </button>
                </label>
            </div>

            {/* Ficha */}
            <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto">
                <section className="panel p-5">
                    <p className="eyebrow">{organ.system}</p>
                    <h1 className="mt-1.5 text-[26px] leading-[1.1] tracking-tight text-balance">
                        {lang === 'en' ? organ.en : organ.es}
                    </h1>
                    <p className="text-ink-soft border-rule mt-4 border-t pt-3 text-[12.5px] leading-relaxed">
                        {t.organPartsHint.replace('{n}', String(organ.structures.length))}
                    </p>
                </section>

                <section className="panel flex min-h-0 flex-col overflow-hidden">
                    <h2 className="eyebrow border-rule border-b px-4 py-2.5">{t.organParts}</h2>
                    <div className="min-h-0 overflow-y-auto">
                        {organ.structures.map(s => (
                            <button
                                key={s.fma}
                                onClick={() => setSelected(s.fma === selected ? null : s.fma)}
                                className={`flex w-full items-center gap-2.5 px-4 py-2 text-left transition-colors ${
                                    s.fma === selected ? 'bg-clay/10' : 'hover:bg-sunk'
                                }`}
                            >
                                <span
                                    aria-hidden
                                    className="size-2.5 shrink-0 rounded-[3px]"
                                    style={{ background: TISSUE_SWATCH[s.tissue] ?? '#999' }}
                                />
                                <span className="min-w-0 flex-1 truncate text-[12.5px]">
                                    {s.name}
                                </span>
                                <span className="text-ink-faint font-mono text-[9.5px] tabular-nums">
                                    {(s.faces / 1000).toFixed(0)}k
                                </span>
                            </button>
                        ))}
                    </div>
                </section>

                {part && (
                    <section className="panel p-4">
                        <p className="eyebrow">{t.structure}</p>
                        <p className="mt-1.5 text-[15px] leading-snug">{part.name}</p>
                        <p className="text-ink-faint mt-1 font-mono text-[10px]">{part.fma}</p>
                    </section>
                )}
            </aside>
        </div>
    );
}
