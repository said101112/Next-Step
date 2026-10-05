# ============================================================
# agents/app/domain/sn_copilot/graph.py
#
# SN Copilot (Smart Navigator) - BCG Executive AI Advisor
# Uses LLM + direct PostgreSQL tools to retrieve, mutate,
# postuler, and suggest strategic questions.
# Full profile awareness + CV upload + matching.
# ============================================================
import json
import logging
import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.core.config import get_llm
from app.domain.sn_copilot.tools import (
    get_recent_candidatures,
    update_candidature_status,
    create_candidature,
    get_candidature_stats,
    get_pending_follow_ups,
)
from app.domain.sn_copilot.profile_tools import (
    get_user_profile,
    build_profile_summary,
    parse_cv_text,
    match_cv_with_candidatures,
)

logger = logging.getLogger(__name__)

BCG_SYSTEM_PROMPT = """Tu es **SN** (Smart Navigator), le copilote exécutif de carrière NextStep, inspiré par les standards des grands cabinets de conseil en stratégie (BCG, McKinsey).

RÈGLES D'OR DE COMMUNICATION (STYLE BCG EXECUTIVE BRIEFING) :
1. **CONCIS, COURT ET PERCUTANT** :
   - Fais des réponses COURTES et DIRECTES (viser entre 35 et 80 mots au total).
   - AUCUN long paragraphe, AUCUN remplissage, AUCUN verbiage théorique.
   - Va directement à l'essentiel : conclusion/point clé d'abord, puis 2 à 3 puces actionnables concrètes, puis 1 phrase de recommandation exécutive.
2. **ADAPTATION STRICTE SELON L'INTENTION** :
   - **Salutation simple** ("hello", "bonjour", "ça va ?") : Exactement 1 ou 2 phrases brèves et engageantes. Ne récite JAMAIS la liste des candidatures si l'utilisateur a simplement dit bonjour.
   - **Demande de candidatures** : 1 phrase récapitulative, 3 ou 4 puces courtes résumant les postes clés (- **Entreprise** : rôle et priorité), et 1 recommandation d'une ligne.
   - **Conseil (entretien, pitch, relance...)** : 2 à 3 puces méthodologiques percutantes et applicables immédiatement, sans détour.
3. **ZÉRO JARGON TECHNIQUE** :
   - Ne mentionne jamais de termes techniques (PostgreSQL, SQL, base de données, backend, JSON, API, fetch, endpoint).
   - Utilise toujours le vocabulaire métier : "vos candidatures", "votre pipeline", "vos opportunités".
4. **FORMAT PROPRE** :
   - STRICTEMENT AUCUN TABLEAU avec barres verticales (|).
   - STRICTEMENT AUCUNE CITATION (>).
   - Puces aérées (- **Mot-clé** : explication concise).
5. **SUGGESTIONS DE SUIVI** :
   - Termine systématiquement par EXACTEMENT 3 suggestions de questions courtes (maximum 7 mots par suggestion) dans un bloc JSON final :
```json
{
  "suggestions": [
    "Première question courte",
    "Deuxième question courte",
    "Troisième question courte"
  ]
}
```
"""


def _clean_markdown_response(text: str) -> str:
    """Strip ugly ASCII pipe tables and format as clean text if an LLM produced one."""
    if not text:
        return ""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip markdown table borders like |---|---|
        if re.match(r"^\|?[\s\-:|]+\|?$", stripped):
            continue
        # Catch and reformat table rows like | 1 | Deloitte | ... |
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|") if c.strip()]
            if not cells:
                continue
            # Skip header row
            if any(h in cells[0].lower() or (len(cells) > 1 and h in cells[1].lower()) for h in ["#", "entreprise", "poste", "date", "statut", "canal"]):
                continue
            if len(cells) >= 2:
                company = cells[1] if len(cells) > 2 and cells[0].isdigit() else cells[0]
                role = cells[2] if len(cells) > 2 and cells[0].isdigit() else cells[1]
                statut = cells[4] if len(cells) > 4 else (cells[3] if len(cells) > 3 else "")
                statut_clean = statut.replace("_", " ") if statut else ""
                cleaned_lines.append(f"- **{company}** : {role}" + (f" ({statut_clean})" if statut_clean else ""))
            continue
        # Remove blockquote '>' prefix
        if stripped.startswith(">"):
            stripped = re.sub(r"^>\s*", "", stripped)
            cleaned_lines.append(stripped)
            continue

        cleaned_lines.append(line)

    res = "\n".join(cleaned_lines).strip()
    # Normalize multiple blank lines
    res = re.sub(r"\n{3,}", "\n\n", res)
    return res


def _detect_intent(user_text: str) -> Dict[str, Any]:
    """Lightweight rule-based intent and entity extractor to complement LLM."""
    t = user_text.lower().strip()
    words = t.split()

    # 0. CV Upload detection — text starting with [CV_UPLOAD] marker, [CV_UPLOAD_BASE64], or very long text (>200 words)
    if t.startswith("[cv_upload]") or t.startswith("[cv_upload_base64") or t.startswith("voici mon cv"):
        cv_text = user_text
        if t.startswith("[cv_upload]"):
            cv_text = user_text[len("[CV_UPLOAD]"):].strip()
        elif t.startswith("[cv_upload_base64"):
            cv_text = user_text
        return {"intent": "cv_analysis", "cv_text": cv_text}

    # 0b. CV Matching intent
    cv_match_triggers = [
        "match", "matching", "compatib", "correspond", "adéquation", "adequation",
        "mon cv match", "cv match", "compare mon cv", "comparer cv",
        "compatible avec", "matcher", "score de match",
        "analyse la compatibilité", "analyse la compatibilite",
    ]
    if any(trigger in t for trigger in cv_match_triggers) and any(w in t for w in ["cv", "profil", "candidature", "candidatures", "offre", "offres", "poste"]):
        return {"intent": "cv_matching"}

    # 0c. Profile summary intent
    profile_triggers = [
        "mon profil", "résume-moi", "resume-moi", "résumé de moi", "resume de moi",
        "qui suis-je", "qui suis je", "parle-moi de moi", "parle moi de moi",
        "mes compétences", "mes competences", "mes formations", "mes expériences",
        "mes experiences", "mes projets", "mes certifications",
        "connais-tu mon profil", "connais tu mon profil", "tu connais moi",
        "ce que tu sais de moi", "ce que tu connais de moi",
        "donner résumé", "donner resume", "résumer profil", "resumer profil",
    ]
    if any(trigger in t for trigger in profile_triggers):
        return {"intent": "profile_summary"}

    # 0d. Long text detection as potential CV paste (>200 words and looks like CV content)
    if len(words) > 200 and any(kw in t for kw in ["expérience", "experience", "formation", "compétence", "competence", "stage", "projet", "diplôme", "diplome"]):
        return {"intent": "cv_analysis", "cv_text": user_text}

    # 1. Greetings / Salutations (e.g. "hello", "bonjour", "salut", "ça va")
    greeting_pattern = r"^(?:bonjour|bonsoir|salut|hello|hey|hi|coucou|yo|hola|good\s+morning|good\s+afternoon|comment\s+(?:vas-tu|allez-vous|tu\s+vas|ça\s+va|ca\s+va)|ça\s+va|ca\s+va)[\s!.,?a-zA-Z0-9]*$"
    if re.match(greeting_pattern, t) or (len(words) <= 3 and any(w in ["hello", "bonjour", "salut", "bonsoir", "coucou", "hey", "hi", "yo"] for w in words) and not any(k in t for k in ["candidature", "statut", "entretien", "offre", "postule"])):
        return {"intent": "greeting"}

    # 2. Identity / Capabilities / Help (e.g. "qui es-tu", "tu peux faire quoi")
    capability_triggers = [
        "qui es-tu", "qui tu es", "tu es qui", "c'est quoi sn", "qui est sn",
        "que peux-tu faire", "tu peux faire quoi", "qu'est-ce que tu peux faire",
        "comment tu peux m'aider", "quelles sont tes fonctionnalités", "quelles sont tes fonctionnalites"
    ]
    if any(q in t for q in capability_triggers) or (len(words) <= 2 and any(h in t for h in ["aide", "aide-moi", "help"])):
        return {"intent": "capabilities"}

    # 3. Thanks / Farewell (e.g. "merci", "au revoir")
    if any(m in t for m in ["merci beaucoup", "merci bien", "super merci", "merci sn", "merci pour ton aide"]) or (len(words) <= 2 and t in ["merci", "thanks", "thx", "au revoir", "bonne journée", "bonne journee", "bonne soirée", "bonne soiree", "à bientôt", "a bientot", "bye"]):
        return {"intent": "farewell"}

    # 4. Status update (Check before stats to avoid matching 'statut')
    status_keywords = ["entretien", "refus", "accept", "envoy", "relance", "attente", "test tech"]
    if any(action in t for action in ["passe", "mets", "met", "change", "modifie", "update"]) and any(s in t for s in status_keywords):
        target_status = "ENTRETIEN_PROPOSE"
        if "entretien" in t:
            target_status = "ENTRETIEN_PROPOSE"
        elif "accept" in t:
            target_status = "ACCEPTE"
        elif "refus" in t:
            target_status = "REFUSE"
        elif "relance" in t:
            target_status = "RELANCE_NECESSAIRE"
        elif "attente" in t:
            target_status = "EN_ATTENTE"
        elif "test" in t:
            target_status = "TEST_TECHNIQUE"

        clean = re.sub(
            r"\b(passe|mets|met|change|modifie|update|le|la|les|en|statut|de|pour|candidature|entretien|refuse|refusé|refus|accepte|accepté|relance|attente|test|tech)\b",
            "",
            t
        ).strip()
        words_clean = clean.split()
        company_query = words_clean[0] if words_clean else ""
        return {"intent": "update_status", "company": company_query, "status": target_status}

    # 5. Apply / Postuler / Ajouter une candidature
    apply_patterns = [
        "postule chez", "postuler chez", "postule pour", "postuler pour",
        "j'ai postulé", "jai postule", "ajoute une candidature", "ajouter une candidature",
        "nouvelle candidature", "nouveau candidature", "enregistre ma candidature", "enregistrer ma candidature",
        "crée une candidature", "creer une candidature", "créer une candidature",
        "j'ai candidaté", "jai candidate", "candidature chez", "candidater chez",
        "ajoute candidature", "ajouter candidature", "créer candidature", "creer candidature"
    ]
    if any(v in t for v in apply_patterns) or (
        ("candidature" in t or "condidature" in t or "postul" in t) and any(v in t for v in ["ajoute", "ajouter", "nouvelle", "nouveau", "créer", "creer", "enregistre", "enregistrer"])
    ):
        return {"intent": "postuler"}

    # 6. Candidatures list / check / pipeline
    has_cand_noun = any(w in t for w in ["candidature", "candidatures", "postulé", "postulée", "postulee", "pipeline", "dossier", "opportunité", "opportunités"])
    has_retrieval_trigger = any(v in t for v in [
        "affiche", "afficher", "donne", "donner", "liste", "lister", "voir", "montre", "montrer",
        "consulter", "mes", "combien", "derniere", "dernière", "dernier", "derniers", "recent", "récent",
        "recupere", "récupère", "last", "etat", "état", "où en sont", "ou en sont"
    ])
    if has_cand_noun and (has_retrieval_trigger or len(words) <= 3):
        limit = 10
        match_num = re.search(r"\b(\d+)\b", t)
        if match_num:
            try:
                limit = int(match_num.group(1))
            except Exception:
                limit = 10
        return {"intent": "get_candidatures", "limit": limit}

    # 7. Stats / metrics
    if re.search(r"\b(stats|statistiques|statistique|métriques|métrique|taux|conversion|bilan|synthèse)\b", t):
        return {"intent": "get_stats"}

    # 8. Follow ups / Relances
    if any(k in t for k in ["relance", "relances", "sans réponse", "sans reponse", "stagnante", "stagnantes", "priorité", "priorités"]):
        return {"intent": "get_follow_ups"}

    # 9. Note addition
    if "note" in t and any(v in t for v in ["ajoute", "note", "écris", "mets"]):
        parts = t.split("note", 1)
        return {"intent": "add_note", "raw": parts[1].strip()}

    return {"intent": "general"}


def _extract_candidature_info(user_text: str) -> Dict[str, Any]:
    """
    Extract company name, job role, and channel from user text.
    Handles French/English natural phrasing:
    'j'ai postulé chez Xcelerit via linkedin pour le poste Software Engineer Intern'
    'ajoute candidature chez Google au poste SWE'
    """
    t = user_text.strip()
    tl = t.lower()

    # Detect channel
    channel = "WEBSITE"
    if any(k in tl for k in ["linkedin", "linkdeen", "linkdin", "linkid"]):
        channel = "LINKEDIN"
    elif "indeed" in tl:
        channel = "INDEED"
    elif any(k in tl for k in ["email", "mail", "courriel"]):
        channel = "EMAIL"
    elif any(k in tl for k in ["watsap", "whatsapp", "whatsap", "wsp"]):
        channel = "AUTRE"
    elif any(k in tl for k in ["site", "carriere", "career"]):
        channel = "WEBSITE"

    # Strip conversational noise from end of message
    clean = re.sub(
        r"(?i)\b(?:tu\s+peux\s+(?:enregistrer|l['’]enregistrer|ajouter|mettre)|peux-?tu\s+(?:enregistrer|l['’]enregistrer|ajouter)|enregistre[\s\-]le|enregistre\s+svp|dans\s+la\s+plateforme|sur\s+la\s+plateforme|dans\s+l['’]application|merci|svp|s['’]il\s+te\s+pla[iî]t)\b.*$",
        "",
        t
    ).strip()

    company = ""
    role = ""

    # Pattern 1: (chez|pour|à|a|dans) <Company> [via ...] (pour le poste [de]|au poste [de]|en tant que|comme|poste [:-]) <Role>
    m1 = re.search(
        r"(?i)(?:chez|pour|à|\ba\b|dans|auprès\s+de|aupres\s+de)\s+([A-Za-z0-9\s&._+\'-]+?)(?:\s+via\s+[A-Za-z0-9\s]+)?\s+(?:pour\s+le\s+poste\s+(?:de\s+)?|au\s+poste\s+(?:de\s+)?|en\s+tant\s+que\s+|comme\s+|poste\s*[:\-]?\s*)(.+)$",
        clean
    )
    if m1:
        company = m1.group(1).strip()
        role = m1.group(2).strip()
    else:
        # Pattern 2: separate extraction
        m_comp = re.search(r"(?i)(?:chez|pour|à|\ba\b|dans|auprès\s+de|aupres\s+de)\s+([A-Za-z0-9\s&._+\'-]+?)(?:\s+via|\s+pour|\s+en|\s+comme|\s+au\s+poste|\s+poste|\s*$|,)", clean)
        if m_comp:
            company = m_comp.group(1).strip()
        m_role = re.search(r"(?i)(?:poste\s*[:\-]?\s*|en\s+tant\s+que\s+|comme\s+|pour\s+le\s+poste\s+(?:de\s+)?)([A-Za-z0-9\s&._+\'-]+?)(?:\s+chez|\s+via|\s*$|,)", clean)
        if m_role:
            role = m_role.group(1).strip()

    # Clean company of trailing channel/noise
    company = re.sub(r"(?i)\s+via\s+.*$", "", company).strip()
    company = re.sub(r"(?i)\b(?:linkdeen|linkedin|indeed|email|site|watsap|whatsapp)\b.*$", "", company).strip()

    # Clean role of trailing noise
    role = re.sub(r"(?i)\b(?:tu\s+peux.*|dans\s+la\s+plateforme.*|sur\s+.*|merci.*)$", "", role).strip()

    return {
        "company": company,
        "role": role or "Poste non précisé",
        "channel": channel
    }


async def run_sn_agent(
    user_id: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main entry point for SN Copilot.
    Executes database operations and formats response with executive consulting tone.
    Full profile awareness + CV analysis + matching.
    """
    logger.info("[SN:Agent] Starting chat for user_id=%s, message='%s'", user_id, user_message)

    intent_info = _detect_intent(user_message)
    intent = intent_info.get("intent", "general")
    actions_performed: List[str] = []
    cards: List[Dict[str, Any]] = []
    context_data: Dict[str, Any] = {}

    # ── 0. Pre-fetch profile + candidatures in parallel ──
    import asyncio
    profile_task = asyncio.create_task(get_user_profile(user_id))
    cands_task = asyncio.create_task(get_recent_candidatures(user_id, limit=10))
    user_profile, baseline_cands = await asyncio.gather(profile_task, cands_task)

    context_data["candidatures"] = baseline_cands
    context_data["total_enregistrees"] = len(baseline_cands)

    # Build profile summary for injection
    profile_summary_text = build_profile_summary(user_profile)

    # ── 1. Tool execution & card selection based strictly on intent ──
    if intent == "get_candidatures":
        limit = intent_info.get("limit", 10)
        selected_cands = baseline_cands[:limit]
        actions_performed.append(f"📋 Consultation de vos {len(selected_cands)} candidatures actives")
        cards = selected_cands

    elif intent == "update_status":
        company = intent_info.get("company", "")
        status = intent_info.get("status", "ENTRETIEN_PROPOSE")
        res = await update_candidature_status(user_id, company, status)
        if res.get("status") == "success":
            actions_performed.append(f"✨ Statut actualisé : {res.get('entreprise')} → {res.get('new_status')}")
            cards = await get_recent_candidatures(user_id, limit=10)
            context_data["candidatures"] = cards
        else:
            actions_performed.append(f"⚠️ {res.get('message', 'Échec de la mise à jour')}")
            cards = baseline_cands
        context_data["update_result"] = res

    elif intent == "get_stats":
        stats = await get_candidature_stats(user_id)
        actions_performed.append("📊 Analyse de performance du pipeline")
        context_data["stats"] = stats

    elif intent == "get_follow_ups":
        follow_ups = await get_pending_follow_ups(user_id)
        if follow_ups:
            actions_performed.append(f"🎯 {len(follow_ups)} relance(s) prioritaire(s) sélectionnée(s)")
            cards = follow_ups
        else:
            cards = []
        context_data["follow_ups"] = follow_ups

    elif intent == "postuler":
        info = _extract_candidature_info(user_message)
        company = info.get("company")
        role = info.get("role", "Poste non précisé")
        channel = info.get("channel", "WEBSITE")

        if company:
            res = await create_candidature(user_id, company, role, channel=channel)
            if res.get("status") == "success":
                actions_performed.append(f"🚀 Candidature enregistrée chez {company} ({role})")
                all_cands = await get_recent_candidatures(user_id, limit=10)
                context_data["candidatures"] = all_cands
                context_data["create_result"] = res
                new_card = {
                    "id": res.get("id"),
                    "idOffre": "",
                    "entreprise": company,
                    "role": role,
                    "statut": "ENVOYE",
                    "channel": channel,
                }
                cards = [new_card] + [c for c in all_cands if str(c.get("id")) != str(res.get("id"))]
            else:
                actions_performed.append("⚠️ Erreur lors de l'enregistrement de la candidature")
                context_data["create_result"] = res
        else:
            actions_performed.append("📝 Prêt pour l'enregistrement de candidature")
            context_data["create_result"] = {
                "status": "ready_to_add",
                "message": "Précisez simplement le nom de l'entreprise et l'intitulé du poste."
            }

    elif intent == "profile_summary":
        actions_performed.append("👤 Consultation de votre profil complet")
        context_data["profile_detail"] = user_profile

    elif intent == "cv_analysis":
        cv_text = intent_info.get("cv_text", user_message)
        actions_performed.append("📄 Analyse de votre CV en cours...")
        cv_parsed = await parse_cv_text(cv_text)
        context_data["cv_parsed"] = cv_parsed
        if not cv_parsed.get("error"):
            nb_skills = len(cv_parsed.get("competences", []))
            if nb_skills > 0:
                actions_performed.append(f"✅ CV analysé : {nb_skills} compétences détectées")
            else:
                profile_skills = len(user_profile.get("competences", []))
                if profile_skills > 0:
                    actions_performed.append(f"✅ CV & Profil analysés ({profile_skills} compétences mobilisées)")
                else:
                    actions_performed.append("✅ CV analysé avec succès")
        else:
            profile_skills = len(user_profile.get("competences", []))
            if profile_skills > 0:
                actions_performed.append(f"✅ Profil analysé : {profile_skills} compétences mobilisées")
            else:
                actions_performed.append("✅ Analyse de profil effectuée")

    elif intent == "cv_matching":
        actions_performed.append("🎯 Analyse de compatibilité CV ↔ Candidatures...")
        matching_result = await match_cv_with_candidatures(user_id, profile=user_profile)
        context_data["matching_result"] = matching_result
        if not matching_result.get("error"):
            nb = len(matching_result.get("matches", []))
            actions_performed.append(f"✅ {nb} candidature(s) évaluée(s)")

    # ── 2. Context preparation & Prompting ──
    first_name = user_name.split()[0] if user_name else "Said"
    active_cands = context_data.get("candidatures", baseline_cands)
    cands_summary = [
        {"entreprise": c["entreprise"], "role": c["role"], "statut": c["statut"]}
        for c in active_cands
    ]

    # Build intent-specific context addendum
    extra_context = ""
    if intent == "profile_summary":
        extra_context = f"\n\nDONNÉES PROFIL COMPLÈTES À RÉSUMER :\n{profile_summary_text}"
    elif intent == "postuler" and "create_result" in context_data:
        cr = context_data["create_result"]
        if cr.get("status") == "success":
            extra_context = (
                f"\n\nCONFIRMATION CANDIDATURE ENREGISTRÉE EN BASE DE DONNÉES :\n"
                f"- Entreprise : {cr.get('entreprise')}\n"
                f"- Poste : {cr.get('poste')}\n"
                f"- Statut initial : {cr.get('statut', 'ENVOYE')} (Envoyé)\n"
                f"- Canal : {cr.get('channel', 'WEBSITE')}\n"
                f"Confirme clairement et succinctement (style BCG) que la candidature a été enregistrée avec succès dans son pipeline."
            )
        elif cr.get("status") == "ready_to_add":
            extra_context = (
                "\n\nDEMANDE D'ENREGISTREMENT DE CANDIDATURE :\n"
                "Demande poliment à l'utilisateur de préciser le nom de l'entreprise et l'intitulé du poste."
            )
        else:
            extra_context = f"\n\nERREUR CRÉATION CANDIDATURE : {cr.get('message')}"
    elif intent == "cv_analysis" and "cv_parsed" in context_data:
        cv_p = context_data["cv_parsed"]
        if not cv_p.get("error"):
            extra_context = f"\n\nRÉSULTAT ANALYSE CV :\n{json.dumps(cv_p, ensure_ascii=False)[:2000]}"
        else:
            extra_context = f"\n\nERREUR ANALYSE CV : {cv_p.get('error')}"
    elif intent == "cv_matching" and "matching_result" in context_data:
        mr = context_data["matching_result"]
        if not mr.get("error"):
            extra_context = f"\n\nRÉSULTAT MATCHING CV ↔ CANDIDATURES :\n{json.dumps(mr, ensure_ascii=False)[:2500]}"
        else:
            extra_context = f"\n\nERREUR MATCHING : {mr.get('error')}"

    prompt_content = f"""Message de l'utilisateur : "{user_message[:500]}"
Intention détectée : {intent}

PROFIL COMPLET DU CANDIDAT :
{profile_summary_text}

CANDIDATURES ACTIVES ({len(active_cands)}) :
{json.dumps(cands_summary, ensure_ascii=False)}
{extra_context}

CONSIGNES STRICTES DE RÉDACTION (STYLE BCG EXECUTIVE BRIEFING) :
- SOIS COURT, PRÉCIS ET PERCUTANT (longueur totale visée : 35 à 80 mots maximum).
- ZÉRO REMPLISSAGE, zéro bavardage, va droit au but.
- Si salutation ("hello", "bonjour") : Exactement 1 ou 2 phrases cordiales et directes. Ne donne AUCUNE liste de candidatures.
- Si demande de profil/résumé : Résume le profil de manière structurée avec puces : compétences clés, formation, expérience, objectif.
- Si analyse de CV : Donne les points forts et axes d'amélioration du CV en puces percutantes.
- Si matching CV/candidatures : Présente le classement avec scores (emoji 🟢🟡🔴) et recommandation prioritaire.
- Si demande de candidatures : 1 phrase récapitulative, 3 ou 4 puces concises résumant les postes clés (- **Entreprise** : rôle et statut), et 1 recommandation d'action en une phrase.
- Si question de conseil (pitch, entretien, relance...) : Réponds en 2 ou 3 puces directes avec actions concrètes et 1 conseil exécutif immédiat.
- AUCUN tableau Markdown (|), AUCUNE citation (>).
- Termine TOUJOURS par EXACTEMENT 3 suggestions de questions courtes (max 7 mots par question) dans un bloc JSON :
```json
{{
  "suggestions": [
    "Question courte 1",
    "Question courte 2",
    "Question courte 3"
  ]
}}
```
"""

    if intent == "greeting":
        default_suggestions = [
            "Résumer mon profil",
            "Afficher mes candidatures",
            "Préparer un entretien"
        ]
    elif intent == "capabilities":
        default_suggestions = [
            "Résumer mon profil",
            "Matcher CV et candidatures",
            "Mes relances prioritaires"
        ]
    elif intent == "profile_summary":
        default_suggestions = [
            "Matcher CV et candidatures",
            "Afficher mes candidatures",
            "Mes compétences clés"
        ]
    elif intent in ("cv_analysis", "cv_matching"):
        default_suggestions = [
            "Afficher mes candidatures",
            "Résumer mon profil",
            "Relances prioritaires"
        ]
    elif intent == "get_stats":
        default_suggestions = [
            "Optimiser mes relances",
            "Afficher mes candidatures",
            "Matcher mon profil"
        ]
    else:
        default_suggestions = [
            "Résumer mon profil",
            "Matcher CV et candidatures",
            "Statistiques pipeline"
        ]

    try:
        llm = get_llm(temperature=0.2, agent_name="default")
        messages = [
            SystemMessage(content=BCG_SYSTEM_PROMPT),
        ]

        # Inject multi-turn conversation history for context continuity
        if history:
            for h in history[-6:]:
                role = h.get("role", "")
                content = h.get("content", "")
                if not content:
                    continue
                if role in ["user", "human"]:
                    messages.append(HumanMessage(content=content))
                elif role in ["assistant", "ai", "sn"]:
                    clean_hist = re.sub(r"```json[\s\S]*?```", "", content).strip()
                    if clean_hist:
                        messages.append(AIMessage(content=clean_hist))

        # Current user turn
        messages.append(HumanMessage(content=prompt_content))

        llm_response = await llm.ainvoke(messages)
        if hasattr(llm_response, "content"):
            if isinstance(llm_response.content, list):
                raw_text = "".join(
                    (item.get("text", "") if isinstance(item, dict) else str(item))
                    for item in llm_response.content
                )
            else:
                raw_text = str(llm_response.content or "")
        else:
            raw_text = str(llm_response or "")

        # Extract suggestions JSON if present
        suggestions = default_suggestions
        if "```json" in raw_text:
            parts = raw_text.split("```json")
            text_part = parts[0].strip()
            json_part = parts[1].split("```")[0].strip()
            try:
                parsed_json = json.loads(json_part)
                if isinstance(parsed_json, dict) and "suggestions" in parsed_json:
                    extracted = [str(s).strip() for s in parsed_json["suggestions"] if s]
                    if extracted:
                        suggestions = extracted[:3]
            except Exception as e:
                logger.warning("Failed to parse suggestions json: %s", e)
            markdown_output = text_part
        elif "```" in raw_text:
            parts = raw_text.split("```")
            markdown_output = parts[0].strip()
        else:
            markdown_output = raw_text.strip()

    except Exception as e:
        logger.warning("[SN:Agent] LLM failed, using deterministic executive template: %s", e)
        if intent == "greeting":
            markdown_output = f"Bonjour {first_name} ! Comment puis-je vous accompagner aujourd'hui dans vos opportunités ?"
            suggestions = [
                "Résumer mon profil",
                "Afficher mes candidatures",
                "Préparer un entretien"
            ]
        elif intent == "capabilities":
            markdown_output = (
                f"Bonjour {first_name} ! En tant que copilote exécutif SN, je vous aide à :\n"
                "- **Piloter votre pipeline** : Consultation et état d'avancement en direct.\n"
                "- **Analyser votre profil** : Résumé compétences, formations, expériences.\n"
                "- **Matcher votre CV** : Compatibilité avec vos candidatures actives.\n"
                "- **Préparer vos entretiens** : Pitchs percutants et conseils stratégiques."
            )
            suggestions = [
                "Résumer mon profil",
                "Matcher CV et candidatures",
                "Mes relances prioritaires"
            ]
        elif intent == "farewell":
            markdown_output = f"Avec plaisir, {first_name} ! Je reste à vos côtés pour faire avancer vos démarches."
            suggestions = [
                "Résumer mon profil",
                "Préparer un pitch",
                "Mes métriques clés"
            ]
        elif intent == "profile_summary":
            markdown_output = f"Voici le résumé de votre profil :\n{profile_summary_text}"
            suggestions = [
                "Matcher CV et candidatures",
                "Afficher mes candidatures",
                "Mes compétences clés"
            ]
        elif intent == "cv_analysis":
            markdown_output = "J'ai bien reçu votre CV. Malheureusement, je n'ai pas pu l'analyser en détail pour le moment. Réessayez en collant le texte de votre CV."
            suggestions = [
                "Résumer mon profil",
                "Afficher mes candidatures",
                "Matcher CV et candidatures"
            ]
        elif intent == "cv_matching":
            markdown_output = "L'analyse de compatibilité n'a pas pu être effectuée. Vérifiez que votre profil est à jour."
            suggestions = [
                "Résumer mon profil",
                "Afficher mes candidatures",
                "Mes compétences clés"
            ]
        elif intent == "get_candidatures":
            cands = context_data.get("candidatures", baseline_cands)
            lines = [f"Voici l'état de votre pipeline (**{len(cands)} candidatures actives**) :"]
            for c in cands[:4]:
                lines.append(f"- **{c['entreprise']}** : {c['role']} — {c['statut'].replace('_', ' ').title()}")
            lines.append("\n💡 **Recommandation :** Priorisez le suivi des candidatures en attente cette semaine.")
            markdown_output = "\n".join(lines)
            suggestions = [
                "Relances prioritaires",
                "Matcher mon profil",
                "Statistiques pipeline"
            ]
        elif intent == "get_stats" and "stats" in context_data:
            s = context_data["stats"]
            markdown_output = (
                f"Synthèse de votre pipeline :\n"
                f"- **Candidatures** : {s['total']} envoyées | **Entretiens** : {s['entretiens']} (`{s['taux_entretien']}`)\n"
                f"- **En attente** : {s['en_attente']} | **Offres** : {s['acceptees']}\n\n"
                f"💡 **Recommandation :** Accélérez le suivi actif des dossiers en attente."
            )
            suggestions = [
                "Afficher mes candidatures",
                "Quelles relances prioritaires ?",
                "Matcher mon profil"
            ]
        elif intent == "update_status" and "update_result" in context_data:
            up = context_data["update_result"]
            markdown_output = (
                f"Mise à jour enregistrée avec succès :\n"
                f"- **{up.get('entreprise')}** : statut passé à `{up.get('new_status')}`."
            )
            suggestions = [
                f"Préparer l'entretien {up.get('entreprise')}",
                "Afficher mes candidatures",
                "Ajouter une note"
            ]
        elif intent == "postuler" and "create_result" in context_data:
            cr = context_data["create_result"]
            if cr.get("status") == "success":
                markdown_output = (
                    f"Votre candidature chez **{cr.get('entreprise')}** pour le poste **{cr.get('poste')}** a été enregistrée avec succès.\n\n"
                    f"- **Statut** : `Envoyé`\n"
                    f"- **Canal** : `{cr.get('channel', 'WEBSITE')}`\n\n"
                    f"💡 **Recommandation :** Votre dossier est disponible sur votre tableau de bord des candidatures."
                )
                suggestions = [
                    f"Relancer {cr.get('entreprise')}",
                    "Afficher mes candidatures",
                    "Préparer un entretien"
                ]
            else:
                markdown_output = cr.get("message", "Veuillez préciser le nom de l'entreprise et l'intitulé du poste.")
                suggestions = [
                    "Ajouter une candidature",
                    "Afficher mes candidatures",
                    "Résumer mon profil"
                ]
        else:
            markdown_output = f"Bonjour {first_name}, je suis à votre entière disposition pour faire progresser vos candidatures."
            suggestions = default_suggestions

    clean_text = _clean_markdown_response(markdown_output)

    return {
        "markdown_text": clean_text,
        "actions_performed": actions_performed,
        "cards": cards,
        "follow_up_suggestions": suggestions[:3],
    }
