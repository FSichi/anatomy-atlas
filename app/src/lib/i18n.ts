/**
 * Cadenas de interfaz. Diccionario tipado propio en vez de una librería: sólo
 * hay dos idiomas de UI y `es` tipado como `Strings` ya hace que falte una
 * clave rompa la compilación.
 *
 * Los nombres anatómicos NO viven acá — vienen de terms.json, que trae la
 * nomenclatura oficial en siete idiomas.
 */

export interface Strings {
    brand: string;
    regions: Record<string, string>;
    layers: Record<string, string>;
    dissection: string;
    peel: string;
    peelHint: string;
    structure: string;
    emptySelection: string;
    search: string;
    searchPlaceholder: string;
    noResults: string;
    theme: string;
    language: string;
    reset: string;
    hint: string;
    loading: string;
    error: string;
    structures: string;
    triangles: string;
    transferred: string;
    isolate: string;
    showAll: string;
    browser: string;
    filterPlaceholder: string;
    allLayers: string;
    focus: string;
    andMore: string;
    section: string;
    planes: Record<ClipAxisKey, string>;
    flipSide: string;
    measure: string;
    measureOff: string;
    measureHint: string;
    measureResult: string;
    settings: string;
    close: string;
    dataSource: string;
    dataSourceHint: string;
    notGenerated: string;
    sources: Record<SourceKey, string>;
    sourceDesc: Record<SourceKey, string>;
    panels: string;
    browserToggleHint: string;
    modeAtlas: string;
    modeOrgans: string;
    organLibrary: string;
    organParts: string;
    organPartsHint: string;
    autoRotate: string;
    tools: string;
    lockSelection: string;
    unlockSelection: string;
    keyboardHint: string;
    quality: string;
    qualityHint: string;
    qualityAuto: string;
    qualityLevels: Record<'low' | 'medium' | 'high', string>;
    tissueWet: string;
    tissueFlat: string;
}

type ClipAxisKey = 'sagittal' | 'coronal' | 'axial';
type SourceKey = 'bodyparts3d' | 'zanatomy' | 'mix';

const es: Strings = {
    brand: 'Atlas',
    regions: {
        label: 'Región',
        overview: 'Cuerpo entero',
        head: 'Cabeza',
        neck: 'Cuello',
        thorax: 'Tórax',
        abdomen: 'Abdomen',
        back: 'Espalda',
        upperlimb: 'Miembro superior',
        lowerlimb: 'Miembro inferior',
    },
    layers: {
        skeletal: 'Huesos',
        joints: 'Articulaciones',
        insertions: 'Inserciones',
        lymphoid: 'Linfoide',
        organs: 'Órganos',
        vascular: 'Vasos',
        nervous: 'Nervios',
        muscular: 'Músculos',
        skin: 'Piel',
    },
    dissection: 'Disección',
    peel: 'Pelar hasta esta capa',
    peelHint: 'Clic en el nombre de una capa para pelar hasta ahí.',
    structure: 'Estructura',
    emptySelection: 'Hacé clic en cualquier estructura para identificarla.',
    search: 'Buscar estructura',
    searchPlaceholder: 'Nombre en español, inglés o latín…',
    noResults: 'Sin resultados',
    theme: 'Cambiar tema',
    language: 'Idioma',
    reset: 'Reencuadrar',
    hint: 'Arrastrá para rotar · rueda para zoom · clic para identificar',
    loading: 'Descomprimiendo geometría',
    error: 'No se pudo cargar la anatomía',
    structures: 'estructuras',
    triangles: 'triángulos',
    transferred: 'transferidos',
    isolate: 'Aislar',
    showAll: 'Ver todo',
    browser: 'Estructuras del modelo',
    filterPlaceholder: 'Filtrar…',
    allLayers: 'Todas',
    focus: 'Enfocar',
    andMore: '+{n} más — refiná el filtro para verlas',
    section: 'Corte anatómico',
    planes: { sagittal: 'Sagital', coronal: 'Coronal', axial: 'Axial' },
    flipSide: 'Invertir el lado que se conserva',
    measure: 'Medición',
    measureOff: 'Activá la medición y marcá dos puntos sobre el modelo.',
    measureHint: 'Marcá dos puntos. El tercer clic reinicia.',
    measureResult: '{mm} mm · {cm} cm',
    settings: 'Configuración',
    close: 'Cerrar',
    dataSource: 'Fuente de datos anatómicos',
    dataSourceHint:
        'Las dos fuentes son el mismo cuerpo escaneado: se superponen con menos de 2 mm de error, así que se pueden combinar sin deformar nada.',
    notGenerated: 'sin generar',
    sources: {
        bodyparts3d: 'BodyParts3D',
        zanatomy: 'Z-Anatomy',
        mix: 'Combinada',
    },
    sourceDesc: {
        bodyparts3d:
            'La base original. Ontología FMA con identificadores estables y la mejor cobertura vascular disponible.',
        zanatomy:
            'Derivada de la anterior y muy expandida. Suma articulaciones, inserciones musculares y sistema linfoide.',
        mix: 'Lo mejor de ambas: los vasos y la ontología de BodyParts3D con las articulaciones e inserciones de Z-Anatomy.',
    },
    modeAtlas: 'Atlas',
    modeOrgans: 'Órganos',
    organLibrary: 'Biblioteca de órganos',
    organParts: 'Piezas',
    organPartsHint: 'Este órgano se compone de {n} estructuras reales y separables. Hacé clic en cualquiera para aislarla.',
    autoRotate: 'Girar',
    tools: 'Herramientas',
    lockSelection: 'Bloquear la selección',
    unlockSelection: 'Desbloquear la selección',
    keyboardHint: 'Flechas para orbitar · Shift + flechas para desplazar · + y − para acercar',
    quality: 'Calidad',
    qualityHint: 'Automático detecta el equipo y elige por vos; ahora está en {level}. Bajalo si el modelo se mueve a tirones.',
    qualityAuto: 'Automático',
    qualityLevels: { low: 'Baja', medium: 'Media', high: 'Alta' },
    tissueWet: 'tejido húmedo',
    tissueFlat: 'tejido mate',
    panels: 'Paneles',
    browserToggleHint: 'El listado navegable de todo lo que hay en la región. Apagalo para dejar la escena más despejada.',
};

const en: Strings = {
    brand: 'Atlas',
    regions: {
        label: 'Region',
        overview: 'Whole body',
        head: 'Head',
        neck: 'Neck',
        thorax: 'Thorax',
        abdomen: 'Abdomen',
        back: 'Back',
        upperlimb: 'Upper limb',
        lowerlimb: 'Lower limb',
    },
    layers: {
        skeletal: 'Bones',
        joints: 'Joints',
        insertions: 'Insertions',
        lymphoid: 'Lymphoid',
        organs: 'Organs',
        vascular: 'Vessels',
        nervous: 'Nerves',
        muscular: 'Muscles',
        skin: 'Skin',
    },
    dissection: 'Dissection',
    peel: 'Peel to this layer',
    peelHint: 'Click a layer name to peel down to it.',
    structure: 'Structure',
    emptySelection: 'Click any structure to identify it.',
    search: 'Search structure',
    searchPlaceholder: 'Name in English, Spanish or Latin…',
    noResults: 'No results',
    theme: 'Toggle theme',
    language: 'Language',
    reset: 'Reframe',
    hint: 'Drag to rotate · scroll to zoom · click to identify',
    loading: 'Decompressing geometry',
    error: 'Anatomy could not be loaded',
    structures: 'structures',
    triangles: 'triangles',
    transferred: 'transferred',
    isolate: 'Isolate',
    showAll: 'Show all',
    browser: 'Model structures',
    filterPlaceholder: 'Filter…',
    allLayers: 'All',
    focus: 'Focus',
    andMore: '+{n} more — narrow the filter to see them',
    section: 'Cross-section',
    planes: { sagittal: 'Sagittal', coronal: 'Coronal', axial: 'Axial' },
    flipSide: 'Flip which side is kept',
    measure: 'Measurement',
    measureOff: 'Turn measurement on and mark two points on the model.',
    measureHint: 'Mark two points. A third click starts over.',
    measureResult: '{mm} mm · {cm} cm',
    settings: 'Settings',
    close: 'Close',
    dataSource: 'Anatomical data source',
    dataSourceHint:
        'Both sources are the same scanned body: they register to within 2 mm, so they can be combined without distorting anything.',
    notGenerated: 'not generated',
    sources: {
        bodyparts3d: 'BodyParts3D',
        zanatomy: 'Z-Anatomy',
        mix: 'Combined',
    },
    sourceDesc: {
        bodyparts3d:
            'The original base. FMA ontology with stable identifiers and the best vascular coverage available.',
        zanatomy:
            'Derived from it and heavily expanded. Adds joints, muscle insertions and the lymphoid system.',
        mix: 'The best of both: vessels and ontology from BodyParts3D, joints and insertions from Z-Anatomy.',
    },
    modeAtlas: 'Atlas',
    modeOrgans: 'Organs',
    organLibrary: 'Organ library',
    organParts: 'Parts',
    organPartsHint: 'This organ is made of {n} real, separable structures. Click any of them to isolate it.',
    autoRotate: 'Spin',
    tools: 'Tools',
    lockSelection: 'Lock selection',
    unlockSelection: 'Unlock selection',
    keyboardHint: 'Arrows to orbit · Shift + arrows to pan · + and − to zoom',
    quality: 'Quality',
    qualityHint: 'Auto detects your device and picks for you; right now it is {level}. Lower it if the model stutters.',
    qualityAuto: 'Auto',
    qualityLevels: { low: 'Low', medium: 'Medium', high: 'High' },
    tissueWet: 'wet tissue',
    tissueFlat: 'matte tissue',
    panels: 'Panels',
    browserToggleHint: 'The browsable list of everything in the region. Turn it off for a clearer scene.',
};

export const UI = { es, en };

export type Lang = keyof typeof UI;

export const LANGS: Lang[] = ['es', 'en'];
