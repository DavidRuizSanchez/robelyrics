# Temáticas que se descartan por norma

El keyword research trae el universo entero de cada asset. No todo lo que la
gente busca es algo que este sitio deba (o pueda) servir. Estas tres familias se
descartan **por defecto**, y el informe las lista igualmente marcadas como
descartadas: se ven, no se esconden.

Decidido con el usuario el 2026-08-02.

## 1. Descarga y piratería

Patrones: `descargar`, `torrent`, `mega`, `mediafire`, `utorrent`, `rar`,
`320 kbps`, `flac`, `mp3 gratis`, `disco completo`, `album completo`.

**Por qué**: es tráfico que el sitio no puede ni debe satisfacer. Perseguirlo
ensucia el perfil temático del dominio y atrae visitas que rebotan.

Volumen que se deja fuera en Agila: ~80/mes.

## 2. Merchandising

Patrones: `camiseta`, `camisetas`, `sudadera`, `taza`, `poster`, `tatuaje`,
`parche`, `chapa`.

**Por qué**: `reference_robelyrics_afiliados_legal` ya cerró que fabricar merch
propio queda descartado. Perseguir intención de compra que no se sirve es
prometer algo que no hay.

Matiz: **sí se puede hablar de la iconografía** de un disco (qué representa la
portada, de dónde sale un símbolo). Lo que no se hace es optimizar para la
intención transaccional.

Volumen que se deja fuera en Agila: ~130/mes.

## 3. Ediciones físicas y compra

Patrones: `vinilo`, `lp`, `cd`, `comprar`, `precio`, `dónde comprar`, `fnac`,
`amazon`, `segunda mano`.

**Por qué**: decisión del usuario. Es el bloque comercial más grande del research
(~230/mes en Agila) y se deja fuera a propósito.

Matiz: si algún día se documentan ediciones y reediciones como **dato del disco**
(tirada, sello, año de reedición), eso es contenido editorial legítimo y no cae
aquí. La frontera es la intención: describir una edición ≠ vender una edición.

---

## Cómo se cambia esto

Las tres familias viven en `EXCLUSIONES` dentro de
`scripts/diagnose_page.py`. Se desactivan por asset con `--incluir compra` (o la
familia que sea), y el informe deja constancia de que se incluyó algo que por
defecto no entra.

## Lo que NUNCA se descarta

- **Keywords de volumen 0 o sin dato.** La cola larga es donde vive el tráfico de
  letras, significados y acordes. Un `—` en volumen no es un cero.
- **Keywords en las que la página ya posiciona.** Aunque tengan poco volumen: si
  Google ya te ha puesto en la posición 8, ese es el trabajo más barato que hay.
