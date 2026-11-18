-- Menciones de las 24 candidatas fuera de la fuente 1756 (paso 3 del plan del 10-11-2026).
-- Solo lectura. Patrón: regex POSIX sobre unaccent(lower(texto)), con \m \M de palabra.
-- Los nombres de pila sueltos (María, Pedro, Raúl…) solo se buscan con contexto.
with p(id, nombre, patron) as (values
 ('E-018','Mariño','\mmarin[oh]o?\M.{0,40}(alcalde|rocco)|(alcalde|rocco).{0,40}\mmarin[oh]o?\M'),
 ('E-019','Cándido Cabrera','\mcandido cabrera\M'),
 ('E-020','Elia Blanco','\melia (maria )?blanco\M'),
 ('E-028','José Luis Díaz','\mjose luis diaz\M'),
 ('E-029','Fernando Pizarro','\mfernando pizarro\M'),
 ('E-030','José Antonio Hernández','\mjose antonio hernandez\M'),
 ('E-031','Enrique Tornero','\menrique tornero\M|\mtornero\M'),
 ('E-032','Virgilio','\mvirgilio\M'),
 ('E-037','Juano','\mjuano\M'),
 ('E-039','Paco Dóniga','\mdonig?ca\M|\mpaco donig'),
 ('E-040','Ángel (primer batería)','\mangel\M.{0,60}bater|bater.{0,60}\mangel\M'),
 ('E-046','Cholo','\mcholo\M'),
 ('E-047','Paramio','\mparamio\M'),
 ('E-048','Javi Génesis','\mjavi (gomez|genesis)\M|\mbar genesis\M'),
 ('E-049','Belén (corista)','\mbelen\M.{0,80}(coro|corista)|(coro|corista).{0,80}\mbelen\M'),
 ('E-050','María (corista)','\mmaria\M.{0,80}(coro|corista)|(coro|corista).{0,80}\mmaria\M'),
 ('E-051','Marcos Peral','\mmarcos peral\M'),
 ('E-052','Pedro (Simetría)','\mpedro\M.{0,80}simetria|simetria.{0,80}\mpedro\M'),
 ('E-053','Félix (Gibson)','\mfelix\M.{0,80}(gibson|les paul|escarlata)|(gibson|les paul|escarlata).{0,80}\mfelix\M'),
 ('E-055','Susi Iglesias','\msusi iglesias\M|\msusi\M.{0,60}buitre|buitre.{0,60}\msusi\M'),
 ('E-056','Gustavo (buitre)','\mgustavo\M.{0,80}buitre|buitre.{0,80}\mgustavo\M'),
 ('E-057','Cori','\mcorisco\M|\mcori\M'),
 ('E-060','Raúl (mánager)','\mraul\M.{0,60}(manager|representante)|(manager|representante).{0,60}\mraul\M'),
 ('E-068','Jesús Mateos Brea','\mmateos brea\M|\mmural de brea\M|\mjesus mateos\M')
),
fuentes as (
  select p.id, s.id sid, s.kind, s.author
  from p join interpretation_sources s
    on s.id <> 1756 and unaccent(lower(coalesce(s.content_clean,'') || ' ' || coalesce(s.title,''))) ~ p.patron
),
fichas as (
  select p.id, c.entity_type || ':' || c.slug ref, c.published
  from p join seo_content c on unaccent(lower(c.body_md)) ~ p.patron
),
posts_ as (
  select p.id, po.slug, po.status from p join posts po on unaccent(lower(po.body_md)) ~ p.patron
)
select p.id, p.nombre,
  (select count(*) from fuentes f where f.id=p.id) n_fuentes,
  (select string_agg(distinct f.kind, ',') from fuentes f where f.id=p.id) kinds,
  (select string_agg(f.sid::text, ',' order by f.sid) from fuentes f where f.id=p.id) source_ids,
  (select string_agg(ref, ',' order by ref) from fichas x where x.id=p.id and x.published) fichas_publicadas,
  (select string_agg(slug, ',' order by slug) from posts_ x where x.id=p.id and x.status='published') posts_publicados
from p order by p.id;
