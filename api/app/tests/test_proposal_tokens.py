"""Los botones del correo de propuestas: el destino va dentro y no se cruzan con otros tokens."""
from __future__ import annotations

import pytest

from app.services.auth import (
    create_proposal_action_token,
    create_seo_opportunity_token,
    decode_proposal_action_token,
    decode_seo_opportunity_token,
)


def test_el_destino_viaja_dentro_del_token():
    data = decode_proposal_action_token(
        create_proposal_action_token(484, "merge", target="ficha:12"))
    assert data["action"] == "merge" and data["target"] == "ficha:12"
    assert data["proposal_id"] == 484


def test_fusionar_sin_destino_no_se_puede_ni_firmar():
    with pytest.raises(ValueError):
        create_proposal_action_token(484, "merge")


def test_una_accion_desconocida_no_se_firma():
    with pytest.raises(ValueError):
        create_proposal_action_token(484, "publish")


def test_los_tokens_no_se_cruzan_entre_circuitos():
    """Un token de «aplicar» del circuito SEO publica; uno de propuestas jamás."""
    seo = create_seo_opportunity_token([1], "apply")
    prop = create_proposal_action_token(1, "new")
    assert decode_proposal_action_token(seo) is None
    assert decode_seo_opportunity_token(prop) is None
