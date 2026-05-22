"""Pipeline de publicación en Instagram (@entreinterioresrobe).

Consume la tabla `news_items` (cualquier policy: Instagram usa todo el corpus
de noticias) y la cola `instagram_queue`. Selecciona temas del día, los
prepara (comentario editorial, verso de Robe, imagen) y los publica vía la
Graph API de Meta.
"""
