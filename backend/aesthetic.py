"""Score esthétique automatique — MLP entraîné sur des embeddings CLIP
ViT-L/14 (christophschuhmann/improved-aesthetic-predictor, checkpoint
sac+logos+ava1-l14-linearMSE), échelle ~1-10 façon AVA. Réutilise
directement les embeddings que classifier.py calcule/cache déjà pour la
passe 1 — aucun calcul de modèle en plus, juste ce petit MLP par-dessus.

⚠️ Entraîné en partie sur SAC (Simulacra Aesthetic Captions, contenu
généré/artistique) en plus d'AVA (photographie) — plus proche du domaine
de cette bibliothèque (illustration stylisée) que NIMA classique
(uniquement photo), mais reste une hypothèse à vérifier sur des résultats
réels, pas une vérité établie."""

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

import classifier

MODEL_PATH = Path(__file__).parent.parent / "models" / "sac_logos_ava1-l14-linearMSE.pth"

_model = None


class _MLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(768, 1024), nn.Dropout(0.2),
            nn.Linear(1024, 128), nn.Dropout(0.2),
            nn.Linear(128, 64), nn.Dropout(0.1),
            nn.Linear(64, 16),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        return self.layers(x)


def _load_model():
    global _model
    if _model is not None:
        return
    m = _MLP()
    state = torch.load(MODEL_PATH, map_location=classifier.DEVICE)
    m.load_state_dict(state)
    m.to(classifier.DEVICE)
    m.eval()
    _model = m


def score_embedding(embedding: np.ndarray) -> float:
    """embedding doit déjà être normalisé L2 — exactement ce que produit
    classifier.image_embedding (même convention que le modèle d'origine)."""
    _load_model()
    with torch.no_grad():
        t = torch.from_numpy(np.array(embedding)).float().unsqueeze(0).to(classifier.DEVICE)
        score = _model(t).item()
    return round(score, 3)


def score_path(path: Path) -> float:
    st = path.stat()
    emb = classifier.image_embedding(path, st.st_mtime, st.st_size)
    return score_embedding(emb)
