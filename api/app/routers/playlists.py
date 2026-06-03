"""Listas de reproducción de la zona privada.

Dos sabores:
  - Manuales: el usuario crea listas y les añade canciones (persisten en BD).
  - Por estado de ánimo: se generan al vuelo con embeddings sobre la letra
    completa de cada canción (lyrics_full_v1). No se persisten.

Todo exige sesión (get_current_user). Las pistas se devuelven listas para el
reproductor flotante (video_id + título + slugs para enlazar a la canción).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Playlist, PlaylistItem, Song, User
from app.db.session import get_db
from app.services.auth import get_current_user
from app.services.embeddings import get_embedder
from app.services.retrieval import search_lyrics_full_for_song_ids

router = APIRouter(prefix="/playlists", tags=["playlists"])


class TrackOut(BaseModel):
    video_id: str
    title: str
    artist: str
    artist_slug: str
    album_slug: str
    song_slug: str
    song_id: int | None = None


class MoodIn(BaseModel):
    mood: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=18, ge=3, le=40)


class MoodOut(BaseModel):
    mood: str
    tracks: list[TrackOut]


class PlaylistOut(BaseModel):
    id: int
    name: str
    track_count: int


class PlaylistDetailOut(BaseModel):
    id: int
    name: str
    tracks: list[TrackOut]


class CreatePlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AddSongIn(BaseModel):
    song_id: int


def _track(song: Song) -> TrackOut | None:
    """Construye una pista reproducible; None si la canción no tiene vídeo."""
    if not song.youtube_id:
        return None
    album = song.album
    artist = album.artist
    return TrackOut(
        video_id=song.youtube_id,
        title=song.title,
        artist=artist.name,
        artist_slug=artist.slug,
        album_slug=album.slug,
        song_slug=song.slug,
        song_id=song.id,
    )


# --------------------------------------------------------------------------- #
# Estado de ánimo (embeddings)


@router.post("/mood", response_model=MoodOut)
def mood_playlist(
    body: MoodIn,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MoodOut:
    """Genera una cola a partir de una frase de estado de ánimo (p.ej. "tengo
    ganas de caña", "estoy de bajón"). Busca semánticamente sobre la letra
    completa de cada canción y ordena por cercanía."""
    embedder = get_embedder()
    qv = embedder.embed_one(body.mood.strip())
    scores = search_lyrics_full_for_song_ids(
        qv, k=body.limit * 3, score_threshold=0.18
    )
    if not scores:
        return MoodOut(mood=body.mood, tracks=[])

    ordered_ids = sorted(scores, key=lambda s: scores[s], reverse=True)
    songs = {s.id: s for s in db.query(Song).filter(Song.id.in_(ordered_ids)).all()}
    tracks: list[TrackOut] = []
    for sid in ordered_ids:
        song = songs.get(sid)
        if not song:
            continue
        t = _track(song)
        if t:
            tracks.append(t)
        if len(tracks) >= body.limit:
            break
    return MoodOut(mood=body.mood, tracks=tracks)


# --------------------------------------------------------------------------- #
# Listas manuales (CRUD)


@router.get("", response_model=list[PlaylistOut])
def list_playlists(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaylistOut]:
    rows = (
        db.query(Playlist)
        .filter(Playlist.user_id == user.id)
        .order_by(Playlist.created_at.desc())
        .all()
    )
    return [
        PlaylistOut(id=p.id, name=p.name, track_count=len(p.items)) for p in rows
    ]


@router.post("", response_model=PlaylistOut)
def create_playlist(
    body: CreatePlaylistIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaylistOut:
    pl = Playlist(user_id=user.id, name=body.name.strip())
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return PlaylistOut(id=pl.id, name=pl.name, track_count=0)


def _owned_playlist(db: Session, user: User, playlist_id: int) -> Playlist:
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.user_id == user.id)
        .first()
    )
    if not pl:
        raise HTTPException(status_code=404, detail="lista no encontrada")
    return pl


@router.get("/{playlist_id}", response_model=PlaylistDetailOut)
def get_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaylistDetailOut:
    pl = _owned_playlist(db, user, playlist_id)
    tracks = [t for it in pl.items if (t := _track(it.song))]
    return PlaylistDetailOut(id=pl.id, name=pl.name, tracks=tracks)


@router.delete("/{playlist_id}", status_code=204)
def delete_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    pl = _owned_playlist(db, user, playlist_id)
    db.delete(pl)
    db.commit()


@router.post("/{playlist_id}/songs", response_model=PlaylistDetailOut)
def add_song(
    playlist_id: int,
    body: AddSongIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaylistDetailOut:
    pl = _owned_playlist(db, user, playlist_id)
    song = db.query(Song).filter(Song.id == body.song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="canción no encontrada")
    exists = any(it.song_id == song.id for it in pl.items)
    if not exists:
        next_pos = (max((it.position for it in pl.items), default=-1)) + 1
        db.add(PlaylistItem(playlist_id=pl.id, song_id=song.id, position=next_pos))
        db.commit()
        db.refresh(pl)
    tracks = [t for it in pl.items if (t := _track(it.song))]
    return PlaylistDetailOut(id=pl.id, name=pl.name, tracks=tracks)


@router.delete("/{playlist_id}/songs/{song_id}", response_model=PlaylistDetailOut)
def remove_song(
    playlist_id: int,
    song_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaylistDetailOut:
    pl = _owned_playlist(db, user, playlist_id)
    item = (
        db.query(PlaylistItem)
        .filter(PlaylistItem.playlist_id == pl.id, PlaylistItem.song_id == song_id)
        .first()
    )
    if item:
        db.delete(item)
        db.commit()
        db.refresh(pl)
    tracks = [t for it in pl.items if (t := _track(it.song))]
    return PlaylistDetailOut(id=pl.id, name=pl.name, tracks=tracks)
