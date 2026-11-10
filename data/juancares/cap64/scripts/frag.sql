with f(t) as (values
 ('silencio en mi ruido mental'),('la pastilla roja'),('luz de probador'),('esperanza perdida'),
 ('sitio de mi recreo'),('Parece que sin verte'),('alguien debe tirar del gatillo'),('buitre carroñero'),
 ('en Monfragüe buitres negros'),('Concreté la fecha de mi muerte'),('Razonar es siempre tan difícil'),
 ('las calles nunca llegan a volar'),('coche de papá'),('no logro distinguir el color'),('Dicen que no sale sola'),
 ('Si ella baila'),('ruido de mis tripas'),('Duérmete que ya se ha ido el sol'),('Quise hacer el mundo más feliz'),
 ('He muerto y he resucitado'),('resucité al tercer día'),('va a subir la madera'),('hoguera de una noche de San Juan'),
 ('flores amarillas'),('cepillo de dientes'),('minicentral'),('Tú en tu casa, nosotros en la hoguera'),('no come alpiste'))
select f.t, s.title, al.title as album, l.text, round(similarity(l.text,f.t)::numeric,2) sim
from f cross join lateral (select * from lines l where l.text % f.t or l.text ilike '%'||f.t||'%' order by similarity(l.text,f.t) desc limit 1) l
join songs s on s.id=l.song_id join albums al on al.id=s.album_id;
