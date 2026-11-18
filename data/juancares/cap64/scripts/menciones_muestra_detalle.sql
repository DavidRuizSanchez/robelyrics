-- Detalle (autor + fragmento) de las menciones de la muestra de 10. Solo lectura.
with p(id,nombre,patron) as (values
 ('E-020','Elia Blanco','\melia (maria )?blanco\M'),
 ('E-028','José Luis Díaz','\mjose luis diaz\M'),
 ('E-037','Juano','\mjuano\M'),
 ('E-039','Paco Dóniga','\mdonig?ca\M|\mpaco donig'),
 ('E-040','Ángel (primer batería)','\mangel\M.{0,60}bater|bater.{0,60}\mangel\M'),
 ('E-047','Paramio','\mparamio\M'),
 ('E-048','Javi Génesis','\mjavi (gomez|genesis)\M|\mbar genesis\M'),
 ('E-049','Belén (corista)','\mbelen\M.{0,80}(coro|corista)|(coro|corista).{0,80}\mbelen\M'),
 ('E-055','Susi Iglesias','\msusi iglesias\M|\msusi\M.{0,60}buitre|buitre.{0,60}\msusi\M'),
 ('E-068','Jesús Mateos Brea','\mmateos brea\M|\mmural de brea\M|\mjesus mateos\M')
)
select p.id, s.id, s.kind, coalesce(s.author,''), left(coalesce(s.title,''),70),
 regexp_replace(substring(unaccent(lower(coalesce(s.content_clean,''))) from '.{0,160}(?:'||p.patron||').{0,160}'),'\s+',' ','g')
from p join interpretation_sources s on s.id<>1756 and unaccent(lower(coalesce(s.content_clean,'')||' '||coalesce(s.title,''))) ~ p.patron order by 1,2;
