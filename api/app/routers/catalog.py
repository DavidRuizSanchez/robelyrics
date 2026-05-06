"""Endpoints de navegación del catálogo: artistas → discos → canciones."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Line, Song, SongInterpretation, User
from app.db.session import get_db
from app.services.auth import get_current_user

router = APIRouter(tags=["catalog"])


class ArtistOut(BaseModel):
    slug: str
    name: str
    active_years: str | None = None


class AlbumOut(BaseModel):
    slug: str
    title: str
    year: int
    kind: str
    cover_url: str | None = None


class TrackOut(BaseModel):
    slug: str
    title: str
    track_number: int | None
    has_interpretation: bool
    youtube_id: str | None = None


class AlbumDetailOut(AlbumOut):
    artist: ArtistOut
    tracks: list[TrackOut]


class LineOut(BaseModel):
    line_index: int
    stanza_index: int
    text: str
    start_seconds: int | None = None


class SongDetailOut(BaseModel):
    slug: str
    title: str
    track_number: int | None
    artist: ArtistOut
    album: AlbumOut
    lines: list[LineOut]
    interpretation: dict | None
    interpretation_confidence: str | None
    youtube_id: str | None = None


@router.get("/artists", response_model=list[ArtistOut])
def list_artists(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ArtistOut]:
    rows = db.query(Artist).order_by(Artist.slug).all()
    return [ArtistOut(slug=a.slug, name=a.name, active_years=a.active_years) for a in rows]


@router.get("/artists/{slug}/albums", response_model=list[AlbumOut])
def list_albums(
    slug: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[AlbumOut]:
    artist = db.query(Artist).filter(Artist.slug == slug).first()
    if not artist:
        raise HTTPException(status_code=404, detail="artist not found")
    rows = (
        db.query(Album)
        .filter(Album.artist_id == artist.id)
        .order_by(Album.year, Album.id)
        .all()
    )
    return [
        AlbumOut(slug=a.slug, title=a.title, year=a.year, kind=a.kind, cover_url=a.cover_url)
        for a in rows
    ]


@router.get("/albums/{slug}", response_model=AlbumDetailOut)
def album_detail(
    slug: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlbumDetailOut:
    album = db.query(Album).filter(Album.slug == slug).first()
    if not album:
        raise HTTPException(status_code=404, detail="album not found")
    songs = (
        db.query(Song)
        .filter(Song.album_id == album.id)
        .order_by(Song.track_number.nulls_last(), Song.id)
        .all()
    )
    artist = album.artist
    return AlbumDetailOut(
        slug=album.slug,
        title=album.title,
        year=album.year,
        kind=album.kind,
        cover_url=album.cover_url,
        artist=ArtistOut(slug=artist.slug, name=artist.name, active_years=artist.active_years),
        tracks=[
            TrackOut(
                slug=s.slug,
                title=s.title,
                track_number=s.track_number,
                has_interpretation=s.interpretation is not None,
                youtube_id=s.youtube_id,
            )
            for s in songs
        ],
    )


@router.get("/songs/{slug}", response_model=SongDetailOut)
def song_detail(
    slug: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SongDetailOut:
    song = db.query(Song).filter(Song.slug == slug).first()
    if not song:
        raise HTTPException(status_code=404, detail="song not found")
    album = song.album
    artist = album.artist
    lines = (
        db.query(Line)
        .filter(Line.song_id == song.id)
        .order_by(Line.line_index)
        .all()
    )
    interp = song.interpretation
    return SongDetailOut(
        slug=song.slug,
        title=song.title,
        track_number=song.track_number,
        artist=ArtistOut(slug=artist.slug, name=artist.name, active_years=artist.active_years),
        album=AlbumOut(
            slug=album.slug,
            title=album.title,
            year=album.year,
            kind=album.kind,
            cover_url=album.cover_url,
        ),
        lines=[
            LineOut(
                line_index=l.line_index,
                stanza_index=l.stanza_index,
                text=l.text,
                start_seconds=l.start_seconds,
            )
            for l in lines
        ],
        interpretation=interp.payload if interp else None,
        interpretation_confidence=interp.confidence if interp else None,
        youtube_id=song.youtube_id,
    )
