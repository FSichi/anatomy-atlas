# Atlas anatómico por capas — cuerpo completo

**→ [fsichi.github.io/anatomy-atlas](https://fsichi.github.io/anatomy-atlas/)**

Hecho con ♥ por [Facundo Sichi](https://github.com/FSichi).

Atlas anatómico web con capas reales (piel / vasos / músculos / huesos /
nervios / órganos), donde **cada estructura es un objeto identificable con su
ID de la ontología FMA**, no una malla indivisible.

## Cobertura: cuerpo entero

**936 estructuras** repartidas en 7 regiones y 6 capas. Total en disco: **21,6 MB**.

| Región | Huesos | Órganos | Vasos | Nervios | Músculos | Total | Peso |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cabeza | 26 | 32 | 0 | 99 | 52 | 211 | 2,86 MB |
| Cuello | 15 | 2 | 6 | 0 | 52 | 75 | 2,61 MB |
| Tórax | 53 | 9 | 34 | 0 | 18 | 114 | 2,75 MB |
| Abdomen | 13 | 30 | 13 | 0 | 31 | 89 | 2,60 MB |
| Espalda | 12 | 0 | 0 | 0 | 59 | 71 | 2,61 MB |
| Miembro superior | 66 | 1 | 12 | 0 | 105 | 184 | 2,83 MB |
| Miembro inferior | 66 | 4 | 0 | 0 | 120 | 190 | 2,74 MB |

Cada región carga ~900.000 triángulos en ~2,7 MB. La vista de cuerpo entero
(LOD bajo) son 488.000 triángulos en **2,6 MB, cargados en 180 ms**.

## Nomenclatura

`terms.json` une cada FMA ID con **Terminologia Anatomica 2**, el estándar
internacional oficial, vía Z-Anatomy. Cobertura: **79% con nombre en español**
(el resto conserva el inglés de BodyParts3D), más latín, francés, portugués,
italiano y farsi — soporte multiidioma esencialmente gratis.

Los ordinales se re-adjuntan como numeral romano según convención clínica
(`ninth thoracic vertebra` → `Vértebra torácica IX`) y la lateralidad concuerda
en género con el núcleo del término (`Arteria … derecha`, `Músculo … derecho`).

## Resultados medidos

Sobre NVIDIA RTX 3070, 1280×720, `EXT_disjoint_timer_query_webgl2`:

| Métrica | Valor |
|---|---|
| Carga completa (red + descompresión Draco) | **312 ms** |
| Tiempo de GPU por cuadro @1080p | **0,85 ms** (5% del presupuesto de 60 FPS) |
| Tiempo de GPU por cuadro @4K | **1,09 ms** |
| Draw calls | 100 |
| STL crudo → GLB+Draco | 307,3 MB → 2,95 MB (**104×**) |

Para dimensionar: el sitio de referencia que motivó esto carga **un solo
órgano** (un `heart.glb` generado con IA, malla única indivisible) en 3,2 MB.
Acá entran 102 estructuras nombradas y navegables en menos espacio.

> Las cifras de GPU son de una placa de escritorio de gama alta. Un GPU móvil
> de gama media es del orden de 15–25× más lento para esta carga, lo que deja
> ~1 M de triángulos al borde de los 60 FPS. De ahí que el presupuesto móvil
> deba rondar los 300 k y el LOD dependa del dispositivo.

## Hallazgos que cambian el plan

1. **Las capas salen gratis de la ontología.** Los sistemas raíz de FMA
   (`integumentary`, `cardiovascular`, `muscular`, `skeletal`, `nervous`) son
   hijos directos de `human body` y particionan las estructuras **sin
   solapamiento**. La capa es una consulta al grafo, no una clasificación manual.

2. **No hay nervios periféricos en BodyParts3D.** Su "sistema nervioso" es
   99% sistema nervioso central: giros, tálamo, hipocampo, ventrículos, cuerpo
   calloso, cerebelo. Cero intercostales, frénico, vago o plexo braquial.

   Z-Anatomy **sí los tiene**: 306 estructuras de sistema nervioso periférico
   (95 pares craneales + 206 nervios espinales), verificado abriendo su
   `Startup.blend` con `bpy`. Ojo con la búsqueda por palabra clave: Z-Anatomy
   no usa "nerve" en los nombres, así que un grep ingenuo reporta cero.

   Lo que **ningún dataset abierto resuelve** es el árbol vascular: Z-Anatomy
   tiene 60 mallas cardiovasculares contra las 64 de BodyParts3D. Esa carencia
   es real y no se compra gratis.

3. **La piel es una malla de cuerpo entero** (75,7 MB, `FMA7163`), no
   descompuesta por región. Se recorta geométricamente por planos — que es
   además lo que se necesita para el efecto de "pelado".

4. **Los STL son triangle soup.** Vértices = exactamente 3 × caras, sin aristas
   compartidas. Sin soldar los vértices primero, la decimación por colapso de
   aristas no puede hacer nada: se quedaba en 48% cuando el objetivo era 11%.
   Es el paso que decide todo el presupuesto de geometría.

5. **La cobertura de mallas es parcial**: 934 STL para 1523 estructuras
   nombradas (~61%). No todo lo que tiene nombre tiene geometría.

## Estructura

```
pipeline/                     proceso offline (Python)
  analyze_fma.py              jerarquía FMA -> las capas
  analyze_coverage.py         región x capa x mallas disponibles
  download_all.py             descarga paralela y reanudable (1,25 GB)
  build_fullbody.py           STL -> soldado -> decimado -> GLB -> Draco -> hash
  build_terms.py              FMA -> Terminologia Anatomica 2 (7 idiomas)
  inspect_zanatomy.py         qué hay dentro del .blend de Z-Anatomy (vía bpy)

app/                          la app (Vite + React 19 + Tailwind 4 + R3F)
  src/lib/                    catalog.ts · i18n.ts · url-state.ts
  src/components/             anatomy-canvas.tsx · structure-browser.tsx
  public/anatomy/             37 GLB con hash + catalog.json + terms.json

snapshots/                    verificación visual del pipeline
```

Sin backend: la app lee JSON y GLB estáticos. Cinco dependencias de runtime.

## Cómo correrlo

```bash
pnpm --dir app install
```

```bash
pnpm --dir app dev
```

Regenerar los assets (requiere Python 3.11+ con `trimesh`, `fast-simplification`,
`shapely`, `requests`, `numpy`, y los STL descargados con `download_all.py`):

```bash
BP3D_RAW=/ruta/a/bp3d-raw python pipeline/build_fullbody.py
```

## Qué hace la app

- **8 vistas** — cuerpo entero y 7 regiones, con vuelo de cámara entre ellas.
- **6 capas** con interruptor y opacidad; clic en el nombre pela hasta esa capa.
- **Explorador** de las estructuras de la región activa, con filtro por capa y
  aislamiento múltiple.
- **Buscador** (`Ctrl+K`) sobre las 928 estructuras, en español, inglés y latín.
- **Corte anatómico** en los tres planos (sagital, coronal, axial).
- **Medición en milímetros reales** — la geometría está en mm de un cuerpo real,
  así que la distancia entre dos puntos es una medida anatómica, no una unidad
  arbitraria.
- **Estado en la URL**: `?region=head&fma=FMA50801&layers=skeletal,nervous`
  reproduce exactamente la misma vista.

## Notas de implementación

- **Nombres con hash de contenido.** Los GLB se sirven con
  `Cache-Control: immutable`, lo que exige que el nombre cambie con el
  contenido. Sin eso el navegador sirve geometría vieja indefinidamente.
- **Sin `<Environment>` de drei.** Descarga un HDRI de un CDN externo y suspende
  la escena entera si esa request no llega. La iluminación es con luces explícitas.
- **`include_normals=True` es obligatorio** al exportar desde trimesh: sin
  `NORMAL` en el glTF, un material PBR se sombrea plano.
- **El banco de medición no usa R3F.** En entornos sin compositing,
  `requestAnimationFrame` no dispara y `ResizeObserver` tampoco, así que el
  `<Canvas>` de R3F nunca llega a montarse. `app/bench` arma la escena con
  three.js puro, tamaño explícito y cuadros dibujados a mano.
- **`gl.finish()` no basta para medir GPU** bajo ANGLE/D3D11: da tiempos
  idénticos a 0,9 MP y 8,3 MP porque sólo mide submisión de comandos en CPU.
  Hay que usar `EXT_disjoint_timer_query_webgl2`.

## Autor

**Facundo Sichi** — [@FSichi](https://github.com/FSichi)

Diseñé y construí este proyecto de punta a punta: el pipeline de datos que
convierte anatomía escaneada en assets web, el visor 3D, el sistema de diseño
y el despliegue.

Lo que me interesaba resolver no era mostrar un modelo 3D, sino algo más
difícil: que **cada estructura sea un objeto real y consultable**, no una malla
indivisible. De ahí sale todo lo demás — que puedas aislar el oblicuo externo
derecho, leer su nombre en latín, medir su longitud en milímetros del cuerpo
que se escaneó, y compartir esa vista exacta en un link.

Si te sirve para enseñar, estudiar o construir algo encima, adelante. Y si algo
está mal —que en anatomía es probable— abrí un issue.

## Licencia de los datos

Geometría: **BodyParts3D**, © The Database Center for Life Science, bajo
[CC BY-SA 2.1 Japan](https://creativecommons.org/licenses/by-sa/2.1/jp/deed.en).

Es copyleft: el uso comercial está permitido, pero las mallas derivadas —y las
de este pipeline lo son, porque se deciman y recortan— deben publicarse bajo la
misma licencia. El código del proyecto no se contagia; es obra separada.
