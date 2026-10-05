# ============================================================
# agents/app/domain/sn_copilot/profile_tools.py
#
# Profile & CV Intelligence Tools for SN Executive AI Copilot:
#   - get_user_profile: Full user profile (backend Profile module)
#   - parse_cv_text: LLM-based CV text extraction
#   - match_cv_with_candidatures: CV-to-job scoring
# ============================================================
import json
import logging
from typing import Any, Dict, Optional

from app.core import backend_client
from app.core.config import get_llm
from app.domain.sn_copilot.tools import get_recent_candidatures
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

def _date(value: Any) -> str:
    return str(value or "")[:10]


def _by(key: str):
    """Sort key putting empty values last when sorting in descending order."""
    return lambda item: (item.get(key) is not None and item.get(key) != "", item.get(key) or "")


def to_sn_profile(dto: Dict[str, Any]) -> Dict[str, Any]:
    """Backend FullProfileDto (camelCase) → the profile shape the copilot's prompts use."""
    info = dto.get("personalInfo") or {}
    return {
        "personal_info": {
            "nom": info.get("nom") or "",
            "prenom": info.get("prenom") or "",
            "email": info.get("email") or "",
            "telephone": info.get("telephone") or "",
            "ville": info.get("ville") or "",
            "pays": info.get("pays") or "",
            "titre_poste": info.get("titrePoste") or "",
            "resume_professionnel": info.get("resumeProfessionnel") or "",
            "objectif": dto.get("objectif") or "",
            "niveau": dto.get("niveau") or "",
            "secteur": dto.get("secteur") or "",
            "linkedin": info.get("lienLinkedin") or "",
            "github": info.get("lienGithub") or "",
            "portfolio": info.get("lienPortfolio") or "",
        },
        "competences": sorted(
            (
                {"nom": c.get("nom") or "", "niveau": c.get("niveau") or 0, "type": c.get("typeCompetence") or "technique"}
                for c in dto.get("competences") or []
            ),
            key=lambda c: c["niveau"],
            reverse=True,
        ),
        "formations": sorted(
            (
                {
                    "etablissement": f.get("etablissement") or "",
                    "diplome": f.get("diplome") or "",
                    "annee": f.get("annee") or 0,
                    "annee_fin": f.get("anneeFin"),
                    "ville": f.get("ville") or "",
                    "specialisation": f.get("specialisation") or "",
                    "mention": f.get("mention") or "",
                }
                for f in dto.get("formations") or []
            ),
            key=lambda f: f["annee"],
            reverse=True,
        ),
        "experiences": sorted(
            (
                {
                    "entreprise": e.get("entreprise") or "",
                    "poste": e.get("poste") or "",
                    "date_debut": _date(e.get("dateDebut")),
                    "date_fin": _date(e.get("dateFin")) if e.get("dateFin") else "En cours",
                    "missions": e.get("missions") or "",
                    "ville": e.get("ville") or "",
                    "type_contrat": e.get("type") or "",
                    "taches": e.get("taches") or [],
                }
                for e in dto.get("experiences") or []
            ),
            key=_by("date_debut"),
            reverse=True,
        ),
        "projets": sorted(
            (
                {
                    "titre": pr.get("titreProjet") or "",
                    "description": pr.get("description") or "",
                    "technologies": pr.get("technologiesUtilisees") or "",
                    "date": _date(pr.get("dateRealisation")),
                    "lien": pr.get("lienProjet") or "",
                    "universitaire": bool(pr.get("isUniversity")),
                }
                for pr in dto.get("projets") or []
            ),
            key=_by("date"),
            reverse=True,
        ),
        "certifications": sorted(
            (
                {
                    "titre": c.get("titre") or "",
                    "organisation": c.get("organisation") or "",
                    "date": _date(c.get("dateObtention")),
                }
                for c in dto.get("certifications") or []
            ),
            key=_by("date"),
            reverse=True,
        ),
    }


_EMPTY_PROFILE: Dict[str, Any] = {
    "personal_info": {}, "competences": [], "formations": [], "experiences": [], "projets": [], "certifications": [],
}


async def get_user_profile(user_id: str) -> Dict[str, Any]:
    """
    The user's full profile, from the backend's Profile module (same source as the other
    agents). Read fresh on every call, so the copilot always sees the latest profile edits.
    """
    logger.info("[Tool:SN] get_user_profile — user_id=%s", user_id)
    try:
        result = await backend_client.get_full_profile(user_id)
    except backend_client.BackendError as e:
        logger.error("[Tool:SN] get_user_profile error: %s", e.message)
        return {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in _EMPTY_PROFILE.items()}
    if not result:
        return {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in _EMPTY_PROFILE.items()}

    profile = to_sn_profile(result.get("profile") or {})
    logger.info(
        "[Tool:SN] Profile loaded: %d competences, %d formations, %d experiences, %d projets, %d certifications",
        len(profile["competences"]), len(profile["formations"]), len(profile["experiences"]),
        len(profile["projets"]), len(profile["certifications"]),
    )
    return profile


def build_profile_summary(profile: Dict[str, Any]) -> str:
    """
    Build a concise text summary of the user profile for LLM injection.
    Keeps it compact to minimize token usage while maximizing context.
    """
    pi = profile.get("personal_info", {})
    parts = []

    # Identity
    name = f"{pi.get('prenom', '')} {pi.get('nom', '')}".strip()
    if name:
        parts.append(f"Nom : {name}")
    if pi.get("titre_poste"):
        parts.append(f"Titre : {pi['titre_poste']}")
    if pi.get("ville") or pi.get("pays"):
        loc = ", ".join(filter(None, [pi.get("ville"), pi.get("pays")]))
        parts.append(f"Localisation : {loc}")
    if pi.get("objectif"):
        parts.append(f"Objectif : {pi['objectif']}")
    if pi.get("secteur"):
        parts.append(f"Secteur : {pi['secteur']}")
    if pi.get("niveau"):
        parts.append(f"Niveau : {pi['niveau']}")
    if pi.get("resume_professionnel"):
        parts.append(f"Résumé : {pi['resume_professionnel'][:200]}")
    if pi.get("linkedin"):
        parts.append(f"LinkedIn : {pi['linkedin']}")
    if pi.get("github"):
        parts.append(f"GitHub : {pi['github']}")

    # Competences
    comps = profile.get("competences", [])
    if comps:
        tech = [c["nom"] for c in comps if c.get("type") in ("technique", "hard", None, "")]
        soft = [c["nom"] for c in comps if c.get("type") in ("soft", "transversale")]
        if tech:
            parts.append(f"Compétences techniques : {', '.join(tech[:15])}")
        if soft:
            parts.append(f"Compétences transversales : {', '.join(soft[:10])}")

    # Formations
    forms = profile.get("formations", [])
    if forms:
        form_lines = []
        for f in forms[:3]:
            line = f"{f.get('diplome', '')} — {f.get('etablissement', '')}"
            if f.get("specialisation"):
                line += f" ({f['specialisation']})"
            if f.get("annee"):
                line += f" [{f['annee']}]"
            form_lines.append(line)
        parts.append(f"Formations : {' | '.join(form_lines)}")

    # Experiences
    exps = profile.get("experiences", [])
    if exps:
        exp_lines = []
        for e in exps[:4]:
            line = f"{e.get('poste', '')} chez {e.get('entreprise', '')}"
            if e.get("date_debut"):
                line += f" ({e['date_debut']} → {e.get('date_fin', 'En cours')})"
            exp_lines.append(line)
        parts.append(f"Expériences : {' | '.join(exp_lines)}")

    # Projets
    projs = profile.get("projets", [])
    if projs:
        proj_lines = [p.get("titre", "") for p in projs[:5] if p.get("titre")]
        if proj_lines:
            parts.append(f"Projets : {', '.join(proj_lines)}")

    # Certifications
    certs = profile.get("certifications", [])
    if certs:
        cert_lines = [f"{c.get('titre', '')} ({c.get('organisation', '')})" for c in certs[:5]]
        parts.append(f"Certifications : {', '.join(cert_lines)}")

    return "\n".join(parts) if parts else "Profil non renseigné."


async def parse_cv_text(cv_text: str) -> Dict[str, Any]:
    """
    Use LLM to extract structured data from raw CV text pasted/uploaded by the user.
    Returns a structured dict with skills, experiences, education, certifications, summary.
    """
    # ── Handle base64 encoded PDF/Doc upload ──
    if "[cv_upload_base64:" in cv_text.lower():
        try:
            import base64
            from app.domain.resume.service import extract_text_from_pdf
            b64_str = cv_text.split("]", 1)[1].strip()
            if "base64," in b64_str:
                b64_str = b64_str.split("base64,")[1].strip()
            pdf_bytes = base64.b64decode(b64_str)
            cv_extracted = (await extract_text_from_pdf(pdf_bytes)).strip()
            if len(cv_extracted) > 30:
                cv_text = cv_extracted
                logger.info("[Tool:SN] PyMuPDF successfully extracted %d chars from PDF CV", len(cv_text))
        except Exception as e:
            logger.error("[Tool:SN] PyMuPDF PDF extraction error: %s", e)

    logger.info("[Tool:SN] parse_cv_text — analyzing %d chars of CV text", len(cv_text))

    if len(cv_text.strip()) < 50:
        return {"error": "Texte trop court pour être un CV valide."}

    extraction_prompt = f"""Analyse ce CV et extrais les informations clés en JSON structuré.

CV :
\"\"\"
{cv_text[:4000]}
\"\"\"

Retourne UNIQUEMENT un objet JSON valide avec cette structure :
{{
  "nom": "Nom complet",
  "titre": "Titre professionnel actuel",
  "resume": "Résumé professionnel en 1-2 phrases",
  "competences": ["skill1", "skill2", ...],
  "experiences": [
    {{"entreprise": "...", "poste": "...", "duree": "..."}}
  ],
  "formations": [
    {{"diplome": "...", "etablissement": "...", "annee": "..."}}
  ],
  "certifications": ["cert1", "cert2"],
  "langues": ["langue1", "langue2"],
  "points_forts": ["point1", "point2", "point3"]
}}
"""

    try:
        llm = get_llm(temperature=0.1, agent_name="default")
        response = await llm.ainvoke([
            SystemMessage(content="Tu es un expert en analyse de CV. Extrais les données structurées. Réponds UNIQUEMENT en JSON valide, sans texte supplémentaire."),
            HumanMessage(content=extraction_prompt),
        ])

        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            raw = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in raw)

        # Extract JSON from response
        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        parsed = json.loads(raw)
        logger.info("[Tool:SN] CV parsed successfully: %d skills, %d experiences",
                     len(parsed.get("competences", [])), len(parsed.get("experiences", [])))
        return parsed

    except json.JSONDecodeError as e:
        logger.warning("[Tool:SN] parse_cv_text JSON decode error: %s", e)
        return {"error": "Impossible de parser le CV. Format invalide.", "raw": raw[:500]}
    except Exception as e:
        logger.error("[Tool:SN] parse_cv_text error: %s", e)
        return {"error": str(e)}


async def match_cv_with_candidatures(
    user_id: str,
    cv_data: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Match user CV/profile against active candidatures using LLM scoring.
    Uses either uploaded CV data or the user's stored profile.
    Returns ranked candidatures with match scores and recommendations.
    """
    logger.info("[Tool:SN] match_cv_with_candidatures — user_id=%s", user_id)

    # Get profile if not provided
    if not profile:
        profile = await get_user_profile(user_id)

    # Get candidatures with offer details
    candidatures = await get_recent_candidatures(user_id, limit=20)
    if not candidatures:
        return {"error": "Aucune candidature active trouvée.", "matches": []}

    # Build candidate profile text
    if cv_data and not cv_data.get("error"):
        candidate_text = json.dumps(cv_data, ensure_ascii=False)
        source = "CV uploadé"
    else:
        candidate_text = build_profile_summary(profile)
        source = "profil enregistré"

    # Build candidatures summary for matching
    cand_lines = []
    for i, c in enumerate(candidatures):
        cand_lines.append(
            f"{i+1}. {c['entreprise']} — {c['role']} (statut: {c['statut']}, canal: {c['channel']})"
        )
    cands_text = "\n".join(cand_lines)

    matching_prompt = f"""Analyse la compatibilité entre ce profil candidat et ses candidatures actives.

PROFIL CANDIDAT (source: {source}) :
{candidate_text[:3000]}

CANDIDATURES ACTIVES :
{cands_text}

Pour chaque candidature, évalue la compatibilité sur 100 et donne une recommandation courte.

Retourne UNIQUEMENT un JSON valide :
{{
  "matches": [
    {{
      "rang": 1,
      "entreprise": "...",
      "role": "...",
      "score": 85,
      "points_forts": ["compétence1 alignée", "expérience pertinente"],
      "lacunes": ["compétence manquante"],
      "recommandation": "Action recommandée en 1 phrase"
    }}
  ],
  "conseil_global": "Conseil stratégique global en 1-2 phrases"
}}

Classe par score décroissant. Sois réaliste et précis dans les scores.
"""

    try:
        llm = get_llm(temperature=0.2, agent_name="default")
        response = await llm.ainvoke([
            SystemMessage(content="Tu es un expert en recrutement et matching emploi. Évalue la compatibilité candidat-poste de manière réaliste. Réponds UNIQUEMENT en JSON valide."),
            HumanMessage(content=matching_prompt),
        ])

        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            raw = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in raw)

        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        result = json.loads(raw)
        logger.info("[Tool:SN] Matching complete: %d candidatures scored", len(result.get("matches", [])))
        return result

    except json.JSONDecodeError:
        logger.warning("[Tool:SN] match_cv_with_candidatures JSON error")
        return {"error": "Analyse de matching impossible.", "matches": []}
    except Exception as e:
        logger.error("[Tool:SN] match_cv_with_candidatures error: %s", e)
        return {"error": str(e), "matches": []}
