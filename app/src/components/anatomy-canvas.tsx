import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { OrbitControls, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

/** Sólo lo que usamos de OrbitControls, para no acoplarnos a three-stdlib. */
interface Controls {
    target: THREE.Vector3;
    minDistance: number;
    maxDistance: number;
    update(): void;
}

/**
 * Encuadra un objeto de la escena.
 *
 * Devuelve el centro del objeto en coordenadas de mundo y el radio de su esfera
 * envolvente, para poder llevar la cámara ahí. Es lo que permite "ir a los pies"
 * sin depender del centro de la región.
 */
function focusOf(obj: THREE.Object3D) {
    const box = new THREE.Box3().setFromObject(obj);
    if (box.isEmpty()) return null;
    const center = box.getCenter(new THREE.Vector3());
    const radius = box.getSize(new THREE.Vector3()).length() / 2;
    return { center, radius };
}
import { LAYER_KEYS, framing, type LayerChunk, type LayerKey, type View } from '../lib/catalog';

/**
 * Escena anatómica.
 *
 * Detalles que no son obvios:
 * - BodyParts3D es Z-up en milímetros; three.js es Y-up. De ahí la rotación del grupo.
 * - No se usa <Environment> de drei: descarga un HDRI de un CDN externo y suspende
 *   la escena entera si esa request no llega.
 * - El decodificador Draco está autohospedado en /draco.
 */

const DRACO = '/draco/';

export interface LayerState {
    visible: boolean;
    opacity: number;
}

const HIGHLIGHT = new THREE.MeshStandardMaterial({
    color: '#31c9b4',
    emissive: '#12786c',
    emissiveIntensity: 0.55,
    roughness: 0.34,
    metalness: 0,
});

function Layer({
    chunk,
    state,
    selected,
    isolate,
    clipPlanes,
    onPick,
}: {
    chunk: LayerChunk;
    state: LayerState;
    selected: string | null;
    isolate: Set<string>;
    clipPlanes: THREE.Plane[];
    onPick: (fma: string, point: THREE.Vector3) => void;
}) {
    const { scene } = useGLTF(chunk.file, DRACO);
    // Clonar una vez: useGLTF cachea el original y varias vistas lo comparten.
    const [root] = useState(() => scene.clone(true));
    const base = useRef(new Map<string, THREE.Material>());

    useEffect(() => {
        root.traverse(o => {
            const m = o as THREE.Mesh;
            if (m.isMesh && !base.current.has(m.uuid)) {
                base.current.set(m.uuid, m.material as THREE.Material);
            }
        });
    }, [root]);

    // El material es compartido por toda la capa: alcanza con tocarlo una vez.
    useEffect(() => {
        const done = new Set<THREE.Material>();
        root.traverse(o => {
            const m = o as THREE.Mesh;
            if (!m.isMesh) return;
            const mat = base.current.get(m.uuid) as THREE.MeshStandardMaterial | undefined;
            if (!mat || done.has(mat)) return;
            done.add(mat);
            mat.transparent = state.opacity < 1;
            mat.opacity = state.opacity;
            mat.depthWrite = state.opacity > 0.95;
            mat.side = THREE.DoubleSide;
            mat.clippingPlanes = clipPlanes.length ? clipPlanes : null;
            mat.clipShadows = true;
            mat.needsUpdate = true;
        });
    }, [root, state.opacity, clipPlanes]);

    useEffect(() => {
        root.traverse(o => {
            const m = o as THREE.Mesh;
            if (!m.isMesh) return;
            const original = base.current.get(m.uuid);
            if (!original) return;
            m.material = m.name === selected ? HIGHLIGHT : original;
            // `isolate` vacío = sin aislamiento. Con contenido, sólo esas piezas.
            m.visible = isolate.size === 0 || isolate.has(m.name);
        });
    }, [root, selected, isolate]);

    if (!state.visible) return null;

    return (
        <primitive
            object={root}
            onPointerDown={(e: ThreeEvent<PointerEvent>) => {
                const name = (e.object as THREE.Mesh).name;
                if (!name) return;
                e.stopPropagation();
                // e.point es el punto exacto de intersección en coordenadas de
                // mundo — y como la geometría está en milímetros sin escalar,
                // sirve directo para medir.
                onPick(name, e.point.clone());
            }}
        />
    );
}

/**
 * Lleva la cámara al encuadre de la vista activa.
 *
 * Las regiones comparten origen global para poder mostrarse juntas, así que
 * cada una está desplazada respecto del centro del cuerpo. Sin esto, el zoom
 * apunta al origen y la región se va de cuadro.
 */
function Framer({
    view,
    nonce,
    focusTarget,
}: {
    view: View;
    nonce: number;
    focusTarget: string | null;
}) {
    const { camera, scene } = useThree();
    const controls = useThree(s => s.controls) as Controls | null;
    const anim = useRef<{
        from: THREE.Vector3;
        toPos: THREE.Vector3;
        fromT: THREE.Vector3;
        toT: THREE.Vector3;
        t: number;
    } | null>(null);

    /** Los límites siempre son generosos: la navegación es libre, no un carril. */
    function fly(target: THREE.Vector3, radius: number) {
        if (!controls) return;
        const dist = radius * 3.1 + 90;
        const dir = camera.position.clone().sub(controls.target).normalize();
        if (dir.lengthSq() < 0.01) dir.set(0.12, 0.06, 1).normalize();

        anim.current = {
            from: camera.position.clone(),
            toPos: target.clone().addScaledVector(dir, dist),
            fromT: controls.target.clone(),
            toT: target.clone(),
            t: 0,
        };
        controls.minDistance = 8;
        controls.maxDistance = 9000;
    }

    // Cambio de región: encuadrar la región entera.
    useEffect(() => {
        if (!controls) return;
        const { center, radius } = framing(view.bounds);
        // El grupo está rotado -90° en X: (x, y, z) del dataset → (x, z, -y) en escena.
        fly(new THREE.Vector3(center[0], center[2], -center[1]), radius);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [view.key, nonce, controls]);

    // Enfocar una estructura concreta: así se llega a los pies, a un dedo o al
    // hueso temporal sin pelear con el centro de la región.
    useEffect(() => {
        if (!focusTarget || !controls) return;
        const obj = scene.getObjectByName(focusTarget);
        if (!obj) return;
        const f = focusOf(obj);
        if (f) fly(f.center, Math.max(f.radius, 14));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [focusTarget, controls]);

    useFrame((_, delta) => {
        const a = anim.current;
        if (!a || !controls) return;
        a.t = Math.min(1, a.t + delta * 2.4);
        // easeOutCubic: arranca rápido y asienta, en vez de frenar de golpe
        const e = 1 - Math.pow(1 - a.t, 3);
        camera.position.lerpVectors(a.from, a.toPos, e);
        controls.target.lerpVectors(a.fromT, a.toT, e);
        controls.update();
        if (a.t >= 1) anim.current = null;
    });

    return null;
}

/* ── Corte anatómico ──────────────────────────────────────────────── */

/**
 * Planos anatómicos, expresados en coordenadas de escena.
 *
 * El grupo está rotado -90° en X, así que el dataset (x, y, z) cae en escena
 * como (x, z, -y). Por eso:
 *   sagital    (izq/der)      → eje X del dataset  → X de escena
 *   coronal    (delante/atrás)→ eje Y del dataset  → -Z de escena
 *   axial      (arriba/abajo) → eje Z del dataset  → Y de escena
 */
export type ClipAxis = 'sagittal' | 'coronal' | 'axial';

const AXIS_NORMAL: Record<ClipAxis, THREE.Vector3> = {
    sagittal: new THREE.Vector3(-1, 0, 0),
    coronal: new THREE.Vector3(0, 0, 1),
    axial: new THREE.Vector3(0, -1, 0),
};

/** Índice del eje del dataset que corresponde a cada plano anatómico. */
export const AXIS_SOURCE: Record<ClipAxis, 0 | 1 | 2> = {
    sagittal: 0,
    coronal: 1,
    axial: 2,
};

export interface ClipState {
    enabled: boolean;
    axis: ClipAxis;
    /** Posición del corte, en milímetros del dataset. */
    at: number;
    flipped: boolean;
}

/** Traduce el corte a un plano de three.js en coordenadas de mundo. */
export function makeClipPlane(clip: ClipState): THREE.Plane[] {
    if (!clip.enabled) return [];
    const n = AXIS_NORMAL[clip.axis].clone();
    if (clip.flipped) n.negate();

    // La constante del plano es la distancia al origen a lo largo de la normal.
    // El punto de corte en escena depende del eje del dataset que representa.
    const scenePoint = new THREE.Vector3();
    if (clip.axis === 'sagittal') scenePoint.set(clip.at, 0, 0);
    if (clip.axis === 'coronal') scenePoint.set(0, 0, -clip.at);
    if (clip.axis === 'axial') scenePoint.set(0, clip.at, 0);

    return [new THREE.Plane().setFromNormalAndCoplanarPoint(n, scenePoint)];
}

function ClipEnabler({ on }: { on: boolean }) {
    const { gl } = useThree();
    useEffect(() => {
        gl.localClippingEnabled = on;
    }, [gl, on]);
    return null;
}

/* ── Medición ─────────────────────────────────────────────────────── */

/** Dibuja la regla entre dos puntos y proyecta su centro para la etiqueta. */
function MeasureLine({
    points,
    onLabel,
}: {
    points: THREE.Vector3[];
    onLabel: (p: { x: number; y: number } | null) => void;
}) {
    const { camera, size } = useThree();
    const geo = useRef(new THREE.BufferGeometry());
    const mid = useRef(new THREE.Vector3());

    useEffect(() => {
        geo.current.setFromPoints(points.length === 2 ? points : []);
    }, [points]);

    useFrame(() => {
        if (points.length !== 2) return onLabel(null);
        mid.current.copy(points[0]).add(points[1]).multiplyScalar(0.5).project(camera);
        onLabel({
            x: ((mid.current.x + 1) / 2) * size.width,
            y: ((1 - mid.current.y) / 2) * size.height,
        });
    });

    if (points.length !== 2) return null;

    return (
        <>
            <line>
                <primitive object={geo.current} attach="geometry" />
                <lineBasicMaterial color="#31c9b4" depthTest={false} />
            </line>
            {points.map((p, i) => (
                <mesh key={i} position={p}>
                    <sphereGeometry args={[4, 12, 12]} />
                    <meshBasicMaterial color="#31c9b4" depthTest={false} />
                </mesh>
            ))}
        </>
    );
}

export interface Stats {
    fps: number;
    tris: number;
    calls: number;
}

function StatsProbe({ onSample }: { onSample: (s: Stats) => void }) {
    const { gl } = useThree();
    const frames = useRef(0);
    const last = useRef(performance.now());

    useFrame(() => {
        frames.current += 1;
        const now = performance.now();
        if (now - last.current < 500) return;
        onSample({
            fps: Math.round((frames.current * 1000) / (now - last.current)),
            tris: gl.info.render.triangles,
            calls: gl.info.render.calls,
        });
        frames.current = 0;
        last.current = now;
    });
    return null;
}

/** Proyecta la estructura seleccionada a coordenadas de pantalla, para la línea guía. */
function Tracker({
    selected,
    onMove,
}: {
    selected: string | null;
    onMove: (p: { x: number; y: number } | null) => void;
}) {
    const { scene, camera, size } = useThree();
    const v = useRef(new THREE.Vector3());

    useFrame(() => {
        if (!selected) return onMove(null);
        const obj = scene.getObjectByName(selected);
        if (!obj) return onMove(null);
        const geo = (obj as THREE.Mesh).geometry;
        if (!geo) return onMove(null);
        if (!geo.boundingSphere) geo.computeBoundingSphere();
        v.current.copy(geo.boundingSphere!.center).applyMatrix4(obj.matrixWorld);
        v.current.project(camera);
        onMove({
            x: ((v.current.x + 1) / 2) * size.width,
            y: ((1 - v.current.y) / 2) * size.height,
        });
    });
    return null;
}

export interface AnatomyCanvasProps {
    view: View;
    layers: Record<LayerKey, LayerState>;
    selected: string | null;
    /** Vacío = mostrar todo. Con contenido, sólo esas estructuras. */
    isolate: Set<string>;
    resetNonce: number;
    /** FMA a enfocar con la cámara; cambia por referencia para re-disparar. */
    focusTarget: string | null;
    clip: ClipState;
    measuring: boolean;
    measurePoints: THREE.Vector3[];
    onPick: (fma: string | null) => void;
    onMeasure: (p: THREE.Vector3) => void;
    onStats: (s: Stats) => void;
    onAnchor: (p: { x: number; y: number } | null) => void;
    onMeasureLabel: (p: { x: number; y: number } | null) => void;
    onReady: () => void;
}

function Ready({ onReady }: { onReady: () => void }) {
    useEffect(onReady, [onReady]);
    return null;
}

export function AnatomyCanvas({
    view,
    layers,
    selected,
    isolate,
    resetNonce,
    focusTarget,
    clip,
    measuring,
    measurePoints,
    onPick,
    onMeasure,
    onStats,
    onAnchor,
    onMeasureLabel,
    onReady,
}: AnatomyCanvasProps) {
    const clipPlanes = useMemo(() => makeClipPlane(clip), [clip]);

    return (
        <Canvas
            camera={{ position: [0, 0, 2600], fov: 40, near: 1, far: 12000 }}
            dpr={[1, 2]}
            gl={{ antialias: true, powerPreference: 'high-performance' }}
            onPointerMissed={() => onPick(null)}
        >
            <ambientLight intensity={0.72} />
            <hemisphereLight args={['#cfe3f2', '#2a2118', 0.5]} />
            <directionalLight position={[240, 200, 300]} intensity={1.7} />
            <directionalLight position={[-220, -60, -200]} intensity={0.55} color="#93b6d6" />
            <directionalLight position={[0, -260, 80]} intensity={0.32} color="#ffd9c2" />

            <StatsProbe onSample={onStats} />
            <Tracker selected={selected} onMove={onAnchor} />
            <ClipEnabler on={clip.enabled} />
            <MeasureLine points={measurePoints} onLabel={onMeasureLabel} />

            <group rotation={[-Math.PI / 2, 0, 0]}>
                <Suspense fallback={null}>
                    {LAYER_KEYS.filter(k => view.layers[k]).map(k => (
                        <Layer
                            key={view.layers[k]!.file}
                            chunk={view.layers[k]!}
                            state={layers[k]}
                            selected={selected}
                            isolate={isolate}
                            clipPlanes={clipPlanes}
                            onPick={(fma, point) => {
                                if (measuring) onMeasure(point);
                                else onPick(fma);
                            }}
                        />
                    ))}
                    <Ready onReady={onReady} />
                </Suspense>
            </group>

            {/* zoomToCursor: la rueda acerca hacia donde apunta el puntero, no
                hacia el centro de la región. Es lo que permite bajar a los pies
                sin quedar atado al eje del modelo. */}
            <OrbitControls
                makeDefault
                enableDamping
                dampingFactor={0.075}
                enablePan
                zoomToCursor
                screenSpacePanning
                panSpeed={1.1}
                zoomSpeed={0.9}
            />
            <Framer view={view} nonce={resetNonce} focusTarget={focusTarget} />
        </Canvas>
    );
}
