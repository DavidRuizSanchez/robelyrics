"""Criba de las 77 personas del cap. 64 (paso 2 del plan del 10-11-2026).

Cada persona queda en una de estas categorías, con el motivo por escrito:
  ya_tiene_ficha       → se analiza aparte (qué aporta el vídeo a su ficha)
  candidata            → escena o figura pública con papel propio en la historia
  identificar_antes    → papel propio, pero el nombre sale dudoso de Whisper
  a_la_ficha_de_robe   → familia o gente privada: sin ficha propia
  contexto             → aparece, pero su papel en esta historia es tangencial

Uso: python criba_personas.py <dir_cap64>
"""
import csv
import sys
from pathlib import Path

BASE = Path(sys.argv[1])

ESCENA, PUBLICA, PRIVADA, AJENA = "escena", "figura pública", "privada", "ajena"

CRIBA = {
    # --- con ficha en la BD
    **{e: ("ya_tiene_ficha", "escena", "Tiene ficha: se analiza qué aporta el vídeo (paso 4).")
       for e in ("E-001", "E-041", "E-042", "E-043", "E-044", "E-045", "E-058",
                 "E-063", "E-064", "E-065", "E-066", "E-069")},
    # --- familia y gente privada
    "E-002": ("a_la_ficha_de_robe", PRIVADA, "Padre de Robe; persona privada."),
    "E-003": ("a_la_ficha_de_robe", PRIVADA, "Madre de Robe; persona privada."),
    "E-004": ("a_la_ficha_de_robe", PRIVADA, "Hermano de Robe; privado y con grafía insegura."),
    "E-005": ("a_la_ficha_de_robe", PRIVADA, "Hermana de Robe; el vídeo no da un nombre legible."),
    "E-006": ("a_la_ficha_de_robe", PRIVADA, "Firma un comunicado; el vídeo no dice el parentesco."),
    "E-008": ("a_la_ficha_de_robe", PRIVADA, "Matrona que asistió su nacimiento: dato de la biografía de Robe."),
    "E-009": ("a_la_ficha_de_robe", PRIVADA, "Profesor que le enseñó guitarra en La Salle: dato de la biografía."),
    "E-010": ("a_la_ficha_de_robe", PRIVADA, "Compañero de colegio; papel menor (imprenta)."),
    "E-021": ("a_la_ficha_de_robe", PRIVADA, "Amiga de Elia Blanco; papel anecdótico."),
    "E-022": ("a_la_ficha_de_robe", PRIVADA, "Amigo de Robe en los repuestos; solo nombre de pila."),
    "E-034": ("a_la_ficha_de_robe", PRIVADA, "Socio del padre en el taller; privado."),
    "E-035": ("a_la_ficha_de_robe", PRIVADA, "Compañero de taller de Robe; privado (entrevistado)."),
    "E-036": ("a_la_ficha_de_robe", PRIVADA, "Empresario para el que repartía Robe: dato de la biografía."),
    # --- contexto
    "E-007": ("contexto", AJENA, "Narrador del documental: la voz es nuestra, no se nombra."),
    "E-011": ("contexto", AJENA, "Futbolista; el bloque va del padre de Robe y la peña."),
    "E-012": ("contexto", AJENA, "Futbolista; contexto de la calle de Plasencia."),
    "E-013": ("contexto", AJENA, "Futbolista; contexto de la calle de Plasencia."),
    "E-014": ("contexto", PRIVADA, "Directivo de la peña del padre; nombre sin verificar."),
    "E-015": ("contexto", PRIVADA, "Mujer de un directivo de la peña."),
    "E-016": ("contexto", PRIVADA, "Portero premiado por la peña."),
    "E-017": ("contexto", AJENA, "Presidente del Atlético en una foto de la peña."),
    "E-024": ("contexto", PUBLICA, "Delegado de la SER en 1989; papel puntual."),
    "E-025": ("contexto", PUBLICA, "Presidente de la Junta: aparece en una canción improvisada. Nodo JSON-LD por Wikidata, sin ficha."),
    "E-026": ("contexto", PUBLICA, "Entregó la Medalla de Extremadura: es un dato del premio, no de él."),
    "E-027": ("contexto", PUBLICA, "Presidente de la Junta en la campaña de 2020; papel puntual."),
    "E-033": ("contexto", PUBLICA, "Director de periódico entrevistado sobre el caso Dover; testigo, no protagonista."),
    "E-061": ("contexto", PUBLICA, "Director del Teatro Alcázar; papel puntual."),
    "E-062": ("contexto", PUBLICA, "Directora del Palacio de Congresos; papel puntual."),
    "E-070": ("contexto", AJENA, "Poeta citado en una respuesta pública."),
    "E-071": ("contexto", AJENA, "Influencia (versiones de Dosis Letal): ficha posible, pero no sale de este vídeo."),
    "E-072": ("contexto", AJENA, "Influencia: ficha posible, pero no sale de este vídeo."),
    "E-073": ("contexto", AJENA, "Concierto anterior del Consejo de la Juventud."),
    "E-074": ("contexto", AJENA, "Contexto político."),
    "E-075": ("contexto", AJENA, "Contexto político."),
    "E-076": ("contexto", AJENA, "Contexto histórico."),
    "E-077": ("contexto", AJENA, "Contexto histórico."),
    # --- nombre dudoso
    "E-023": ("identificar_antes", PUBLICA, "Primer teniente de alcalde en 1989; apellido dudoso (Whisper)."),
    "E-038": ("identificar_antes", ESCENA, "Miembros de Dosis Letal; nombres ininteligibles."),
    "E-054": ("identificar_antes", ESCENA, "Nombre dudoso; [HIPÓTESIS] que sea Luis «von Fanta», que ya tiene ficha."),
    "E-059": ("identificar_antes", PUBLICA, "Programador de radio y jurado del concurso Yamaha; apellido dudoso."),
    "E-067": ("identificar_antes", ESCENA, "Fotógrafo de un disco de Robe; apellido dudoso."),
    # --- candidatas: escena
    "E-037": ("candidata", ESCENA, "Cantante de Dosis Letal y de los primeros ensayos de Extremoduro."),
    "E-039": ("candidata", ESCENA, "Bajista de Dosis Letal, Indecisión Momentánea y Orquesta Escarlata; técnico de los primeros Extremoduro; entrevistado."),
    "E-040": ("candidata", ESCENA, "Primer batería de Extremoduro; entrevistado. Sin apellido: la ficha depende de identificarlo."),
    "E-046": ("candidata", ESCENA, "Secretario del Colectivo de Músicos de Plasencia."),
    "E-047": ("candidata", ESCENA, "Dueño de La Cuadra, punto de la escena rock de Plasencia."),
    "E-048": ("candidata", ESCENA, "Dueño del Tertulia y del Génesis; Robe fue camarero en sus bares."),
    "E-049": ("candidata", ESCENA, "Corista de Extremoduro en varios discos; entrevistada."),
    "E-050": ("candidata", ESCENA, "Corista de Extremoduro en varios discos."),
    "E-051": ("candidata", ESCENA, "Músico del Tertulia; Belén y María le hacían los coros."),
    "E-052": ("candidata", ESCENA, "Socio de Robe en el Bar Simetría; solo nombre de pila."),
    "E-053": ("candidata", ESCENA, "Vendió a Robe su Gibson Les Paul; solo nombre de pila."),
    "E-055": ("candidata", ESCENA, "Coautora del buitre y la bellota del primer disco; entrevistada."),
    "E-056": ("candidata", ESCENA, "Autor de la idea del buitre del primer disco; apellido dudoso."),
    "E-057": ("candidata", ESCENA, "Intermediario con los colaboradores del primer disco."),
    "E-060": ("candidata", ESCENA, "Mánager de Extremoduro en 1995; solo nombre de pila."),
    "E-068": ("candidata", ESCENA, "Autor del mural de Puerto de Béjar sobre Robe y Chinato."),
    # --- candidatas: figuras públicas
    "E-018": ("candidata", PUBLICA, "Alcalde que autorizó los ensayos en la Casa de la Salud."),
    "E-019": ("candidata", PUBLICA, "Alcalde que negó el concierto para financiar el primer disco."),
    "E-020": ("candidata", PUBLICA, "Concejala y luego alcaldesa; gestionó el concierto de la COPE y la vuelta de 2008; entrevistada."),
    "E-028": ("candidata", PUBLICA, "Alcalde del caso Dover (2000) y de la «censura previa» de letras."),
    "E-029": ("candidata", PUBLICA, "Alcalde que autorizó los ensayos de 2017 en el Teatro Alcázar."),
    "E-030": ("candidata", PUBLICA, "Teniente de alcalde; gestionó la calle y los ensayos de 2017."),
    "E-031": ("candidata", PUBLICA, "Concejal que impulsó la vuelta de Extremoduro en 2008."),
    "E-032": ("candidata", PUBLICA, "Presidente del Consejo Local de la Juventud que inauguró su sede con Extremoduro (1987); entrevistado."),
}

personas = [r for r in csv.DictReader(open(BASE / "entidades_cap64.csv", encoding="utf-8"))
            if r["tipo"] == "Persona"]
faltan = [r["id"] for r in personas if r["id"] not in CRIBA]
sobran = [e for e in CRIBA if e not in {r["id"] for r in personas}]
assert not faltan and not sobran, (faltan, sobran)

salida = BASE / "analisis_personas" / "criba_personas.csv"
with open(salida, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "entidad", "decision", "grupo", "motivo", "en_bd", "slug_bd", "minutos"])
    for r in personas:
        decision, grupo, motivo = CRIBA[r["id"]]
        w.writerow([r["id"], r["entidad"], decision, grupo, motivo, r["en_bd"], r["slug_bd"], r["minutos"]])

from collections import Counter
print(Counter(v[0] for v in CRIBA.values()))
print(Counter((v[0], v[1]) for v in CRIBA.values() if v[0] == "candidata"))
