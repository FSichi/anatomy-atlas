import * as THREE from 'three';

/**
 * Planos anatómicos de corte.
 *
 * Vive fuera de anatomy-canvas.tsx porque exportar constantes desde un módulo
 * de componentes rompe el Fast Refresh de Vite: al tocar el archivo, React
 * Refresh no puede saber si la constante cambió y descarta el módulo entero.
 *
 * El grupo de la escena está rotado −90° en X, así que el dataset (x, y, z)
 * cae en escena como (x, z, −y). De ahí la correspondencia:
 *   sagital  (izq/der)       → eje X del dataset → X de escena
 *   coronal  (delante/atrás) → eje Y del dataset → −Z de escena
 *   axial    (arriba/abajo)  → eje Z del dataset → Y de escena
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

    const scenePoint = new THREE.Vector3();
    if (clip.axis === 'sagittal') scenePoint.set(clip.at, 0, 0);
    if (clip.axis === 'coronal') scenePoint.set(0, 0, -clip.at);
    if (clip.axis === 'axial') scenePoint.set(0, clip.at, 0);

    return [new THREE.Plane().setFromNormalAndCoplanarPoint(n, scenePoint)];
}
