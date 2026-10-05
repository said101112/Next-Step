from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class TypeContrat(str, Enum):
    CDI = "CDI"
    CDD = "CDD"
    STAGE = "Stage"
    PFA = "PFA"
    PFE = "PFE"
    ALTERNANCE = "Alternance"
    FREELANCE = "Freelance"

class AnalyzedOffer(BaseModel):
    """
    Modèle Pydantic représentant une offre d'emploi analysée.
    Utilisé pour garantir la structure de sortie de l'Agent 1 (Offer Analyzer).
    """
    titre: str = Field(..., description="Intitulé exact du poste")
    entreprise: Optional[str] = Field(None, description="Nom de l'entreprise qui recrute")
    type_contrat: Optional[TypeContrat] = Field(None, description="Type de contrat proposé")
    localisation: Optional[str] = Field(None, description="Localisation du poste (Ville, Télétravail, etc.)")
    competences_requises: List[str] = Field(
        default_factory=list,
        description="Liste des compétences techniques et soft skills obligatoires"
    )
    competences_souhaitees: List[str] = Field(
        default_factory=list,
        description="Liste des compétences bonus ou 'atouts'"
    )
    keywords_ats: List[str] = Field(
        default_factory=list,
        description="10 à 20 mots-clés stratégiques pour l'optimisation ATS (technos, frameworks, outils)"
    )
    annees_experience: Optional[str] = Field(
        None,
        description="Nombre d'années d'expérience minimum requis (ex: '3', '5+', '2-3')"
    )
    niveau_etudes: Optional[str] = Field(
        None,
        description="Niveau de diplôme attendu (ex: Bac+5, Master)"
    )
    mode_travail: Optional[str] = Field(
        None,
        description="Mode de travail (Remote, Hybride, On-site)"
    )
    description_poste: str = Field(
        ...,
        description="Résumé de la mission en 2 ou 3 phrases synthétiques"
    )
