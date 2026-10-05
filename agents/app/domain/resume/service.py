import asyncio
import json
import pymupdf
from langchain_core.prompts import ChatPromptTemplate
from fastapi import HTTPException
from .prompts import SYSTEM_PROMPT


def _pdf_text(pdf_content: bytes) -> str:
    with pymupdf.open(stream=pdf_content, filetype="pdf") as doc:
        # sort=True: reading order by position, so multi-column CVs don't interleave lines
        return "".join(page.get_text("text", sort=True) + "\n" for page in doc)


async def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Extracts text from a PDF byte stream (in a worker thread: parsing a large PDF must not
    block the other requests).
    """
    try:
        return await asyncio.to_thread(_pdf_text, pdf_content)
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")

import re
import logging
import unicodedata
from app.core.config import get_llm

logger = logging.getLogger(__name__)

from .schemas import ResumeParsedSchema, normalize_language_level

FRENCH_KEY_MAP = {
    "langues": "languages", "langue": "languages",
    "competences": "skills", "compétences": "skills", "competencies": "skills",
    "experiences": "experience", "expériences": "experience",
    "formations": "education", "formation": "education",
    "projets": "projects", "projet": "projects",
    "certificats": "certifications",
    "parascolaire": "extracurricular", "extrascolaire": "extracurricular",
    "informations personnelles": "personal",
}

def _normalize_keys(data: dict) -> dict:
    """Renames common French root keys to their English equivalents."""
    for fr_key, en_key in FRENCH_KEY_MAP.items():
        if fr_key in data and en_key not in data:
            data[en_key] = data.pop(fr_key)
    return data

def _normalize_language_levels(data: dict) -> dict:
    """Post-processes language entries to normalize level descriptors."""
    languages = data.get("languages", [])
    if isinstance(languages, list):
        for lang in languages:
            if isinstance(lang, dict):
                if "niveau" not in lang and "level" in lang:
                    lang["niveau"] = lang.pop("level")
                lang["niveau"] = normalize_language_level(lang.get("niveau"))
    return data

def _squash(text: object) -> str:
    """Lowercase, strip accents, keep letters/digits/#/+ only: 'Node.js' ~ 'NodeJS', line breaks ignored."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9#+]", "", text.lower())


def _grounded(value: object, source: str) -> bool:
    """True if the value (or one of its parts, e.g. 'DDD' in 'Domain-Driven Design (DDD)') is in the source."""
    raw = str(value or "")
    candidates = [raw] + re.split(r"[/(),;|]", raw)
    return any(len(s) >= 1 and s in source for s in (_squash(c) for c in candidates) if s)


# Common language names the model may translate (CV says "Anglais", model returns "English").
_LANGUAGE_ALIASES = {
    "english": "anglais", "anglais": "english", "french": "francais", "francais": "french",
    "arabic": "arabe", "arabe": "arabic", "spanish": "espagnol", "espagnol": "spanish",
    "german": "allemand", "allemand": "german", "italian": "italien", "italien": "italian",
    "portuguese": "portugais", "portugais": "portuguese", "chinese": "chinois", "chinois": "chinese",
}


def ground_in_source(data: dict, source_text: str) -> dict:
    """
    Removes everything the model returned that does not appear in the source text
    (hallucinations). Only verifiable facts are checked: names of skills, languages,
    companies, schools, projects, certifications, and contact details/links.
    """
    source = _squash(source_text)
    source_digits = re.sub(r"\D", "", source_text or "")
    dropped: dict = {}

    def keep(section: str, items: list, test) -> list:
        kept = [item for item in items if test(item)]
        removed = [item for item in items if not test(item)]
        if removed:
            dropped[section] = [str(i.get("nom") or i.get("titre") or i.get("entreprise") or i.get("etablissement") or "?") for i in removed]
        return kept

    personal = data.get("personal") or {}
    for field in ("nom", "prenom", "ville", "pays", "titrePoste"):
        if personal.get(field) and not _grounded(personal[field], source):
            dropped.setdefault("personal", []).append(field)
            personal[field] = ""
    if personal.get("email") and _squash(personal["email"]) not in source:
        dropped.setdefault("personal", []).append("email")
        personal["email"] = ""
    phone_digits = re.sub(r"\D", "", personal.get("telephone") or "")
    if phone_digits and phone_digits[-8:] not in source_digits:
        dropped.setdefault("personal", []).append("telephone")
        personal["telephone"] = ""
    for field in ("lienLinkedin", "lienGithub", "lienPortfolio"):
        url = personal.get(field)
        if url and _squash(re.sub(r"^https?://(www\.)?", "", url)) not in source:
            dropped.setdefault("personal", []).append(field)
            personal[field] = None
    summary = _squash(personal.get("resumeProfessionnel"))
    if summary and summary[:40] not in source:
        dropped.setdefault("personal", []).append("resumeProfessionnel (not in CV)")
        personal["resumeProfessionnel"] = ""
    data["personal"] = personal

    seen: set = set()

    def new_skill(skill: dict) -> bool:
        key = _squash(skill.get("nom"))
        if not key or key in seen:
            return False
        seen.add(key)
        return True

    data["skills"] = [s for s in keep("skills", data.get("skills", []), lambda s: _grounded(s.get("nom"), source)) if new_skill(s)]
    for skill in data["skills"]:
        skill["typeCompetence"] = "Soft Skill" if "soft" in str(skill.get("typeCompetence", "")).lower() else "Technical"

    def language_ok(lang: dict) -> bool:
        name = _squash(lang.get("nom"))
        return _grounded(lang.get("nom"), source) or _LANGUAGE_ALIASES.get(name, "\0") in source

    data["languages"] = keep("languages", data.get("languages", []), language_ok)
    data["experience"] = keep("experience", data.get("experience", []),
                              lambda e: _grounded(e.get("entreprise"), source) or _grounded(e.get("poste"), source))
    data["education"] = keep("education", data.get("education", []),
                             lambda e: _grounded(e.get("etablissement"), source) or _grounded(e.get("diplome"), source))
    data["projects"] = keep("projects", data.get("projects", []), lambda p: _grounded(p.get("titre"), source))
    data["extracurricular"] = keep("extracurricular", data.get("extracurricular", []),
                                   lambda x: _grounded(x.get("titre"), source) or _grounded(x.get("organisation"), source))
    data["certifications"] = keep("certifications", data.get("certifications", []), lambda c: _grounded(c.get("titre"), source))

    if dropped:
        logger.warning("CV import: removed items not found in the CV text (hallucinations): %s", dropped)
    return data


REQUIRED_SECTIONS = ("personal", "experience", "education", "projects",
                     "extracurricular", "certifications", "skills", "languages")


def _coerce_list_items(data: dict) -> dict:
    """Accepts skills/languages returned as plain strings ("Python") as well as objects."""
    for key in ("skills", "languages"):
        items = data.get(key)
        if isinstance(items, list):
            data[key] = [{"nom": i} if isinstance(i, str) else i for i in items if isinstance(i, (str, dict))]
    return data


async def parse_cv_with_ai(cv_text: str) -> dict:
    """
    Sends the CV text to the LLM and returns a structured JSON matching ResumeParsedSchema.
    Uses the stable JSON Mode of Groq for extraction, followed by Pydantic validation for perfect typing.
    """
    llm = get_llm(temperature=0.0, agent_name="resume")
    if hasattr(llm, "bind"):
        llm = llm.bind(response_format={"type": "json_object"})

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "Voici le texte du CV à parser :\n\n{cv_text}")
    ])

    chain = prompt | llm

    try:
        response = await chain.ainvoke({"cv_text": cv_text})
        logger.info(f"🚀 RAW LLM RESPONSE:\n{response.content}\n====================")

        # 1. Nettoyage et parsing robuste de la chaîne JSON
        parsed_data = _coerce_list_items(_normalize_keys(clean_and_parse_json(response.content)))

        # A truncated answer (token limit) can still be valid JSON with only "personal":
        # fail loudly instead of importing a profile with every section silently empty.
        missing = [k for k in REQUIRED_SECTIONS if k not in parsed_data]
        if missing:
            raise ValueError(f"Réponse IA incomplète (sections manquantes : {', '.join(missing)})")

        # 2. Validation (tous les champs sont optionnels : pas de repli sur des données non vérifiées)
        result = ResumeParsedSchema(**parsed_data).model_dump()

        # 3. Suppression de tout ce qui n'apparaît pas dans le CV (hallucinations)
        result = ground_in_source(result, cv_text)

        # 4. Niveaux de langue (un niveau absent reste vide)
        return _normalize_language_levels(result)

    except Exception as e:
        logger.error(f"❌ Erreur critique lors de l'appel ou du parsing du CV : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur d'analyse du CV : {str(e)}")

def clean_and_parse_json(raw_content: str) -> dict:
    """
    Cleans the AI response and parses it as JSON.
    Supports comments stripping, trailing commas, and non-strict control characters.
    """
    if not raw_content:
        raise ValueError("L'IA a retourné une réponse vide.")

    # Enlever les commentaires de type // s'ils existent
    text_clean = re.sub(r'(?<!:)\/\/.*$', '', raw_content, flags=re.MULTILINE)

    # Extraire le bloc JSON des backticks markdown si présent
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text_clean, re.IGNORECASE)
    if match:
        json_str = match.group(1).strip()
    else:
        start = text_clean.find("{")
        end = text_clean.rfind("}")
        if start != -1 and end != -1:
            json_str = text_clean[start:end+1].strip()
        else:
            json_str = text_clean.strip()

    try:
        # Essai initial en mode non-strict (permet les sauts de ligne dans les chaînes, etc.)
        return json.loads(json_str, strict=False)
    except Exception as e:
        # Tentative de nettoyage des virgules traînantes devant une fermeture d'objet ou tableau
        json_str_repaired = re.sub(r',\s*([\]}])', r'\1', json_str)
        try:
            return json.loads(json_str_repaired, strict=False)
        except Exception as e2:
            # Si tout échoue, on log l'erreur et le contenu brut pour débugger
            logger.error(f"❌ Échec critique du parsing JSON du CV. Erreur originale : {e}. Erreur réparation : {e2}")
            logger.error(f"Contenu brut reçu de l'IA : \n{raw_content}")
            raise ValueError(f"Format JSON invalide même après extraction. Erreur : {str(e2)}")

async def parse_linkedin_with_ai(url: str = None, raw_text: str = None) -> dict:
    """
    Parses LinkedIn profile data using LLM.
    If raw_text is provided, it is parsed directly using parse_cv_with_ai.
    If only url is provided, we extract name and search for public details, or construct a clean empty profile if no data is found.
    """
    import re
    import logging
    # On utilise les fonctions déjà présentes dans le scope global
    from app.domain.company.tools.web_tool import smart_search
    from app.domain.resume.schemas import ResumeParsedSchema

    logger = logging.getLogger(__name__)

    # --- Logique Globale Wrapper ---
    try:
        if raw_text and raw_text.strip():
            logger.info("Parsing copy-pasted LinkedIn raw text...")
            return await parse_cv_with_ai(raw_text)

        if not url or not url.strip():
            raise HTTPException(status_code=400, detail="Veuillez fournir une URL LinkedIn ou le texte brut du profil.")

        logger.info(f"Importing LinkedIn profile from URL: {url}")

        # 1. Extract name from URL
        name = ""
        match = re.search(r"linkedin\.com/in/([^/\?#]+)", url, re.IGNORECASE)
        if match:
            slug = match.group(1)
            slug_clean = re.sub(r'-[0-9a-zA-Z]+$', '', slug)
            if len(slug_clean) < 3:
                slug_clean = slug
            name = " ".join([part.capitalize() for part in slug_clean.split("-") if part])

        if not name:
            name = "Utilisateur LinkedIn"

        parts = name.split(" ")
        prenom = parts[0]
        nom = " ".join(parts[1:]) if len(parts) > 1 else ""

        # 2. Try searching public info
        scraped_text = ""
        try:
            logger.info(f"Searching public info for: {name}")
            # On ajoute un timeout implicite via le smart_search qui utilise httpx
            search_results = await smart_search(f"{name} site:linkedin.com/in/")
            snippets = []
            for r in search_results:
                snippets.append(f"{r.get('title', '')}: {r.get('snippet', '')}")
            scraped_text = "\n".join(snippets)
        except Exception as search_err:
            logger.warning(f"Failed searching public info for {name}: {search_err}")

        # 3. LLM Completion
        llm = get_llm(temperature=0.0, agent_name="resume")
        if hasattr(llm, "bind"):
            llm = llm.bind(response_format={"type": "json_object"})

        system_prompt = f"""
Ta tâche est d'extraire les informations d'un profil LinkedIn à partir des snippets publics fournis.
Nom extrait : {prenom} {nom}
Lien : {url}

IMPORTANT : Ne simule pas d'infos. Si vide, laisse vide.
Retourne un JSON valide respectant le schéma ResumeParsedSchema.
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", f"Snippets trouvés :\n{scraped_text}\n\nGénère le profil JSON.")
        ])

        chain = prompt | llm
        response = await chain.ainvoke({})
        parsed_data = clean_and_parse_json(response.content)

        # Merge mandatory info
        if "personal" not in parsed_data: parsed_data["personal"] = {}
        parsed_data["personal"]["prenom"] = parsed_data["personal"].get("prenom") or prenom
        parsed_data["personal"]["nom"] = parsed_data["personal"].get("nom") or nom
        parsed_data["personal"]["linkedinUrl"] = url

        # Validation Pydantic
        try:
            return ResumeParsedSchema(**parsed_data).model_dump()
        except Exception:
            return parsed_data

    except Exception as e:
        logger.error(f"❌ Erreur critique Import LinkedIn : {e}")
        # Toujours retourner un objet valide pour éviter le crash 500 du frontend
        return {
            "personal": {"nom": nom if 'nom' in locals() else "", "prenom": prenom if 'prenom' in locals() else "Utilisateur", "email": "", "telephone": "", "ville": "", "pays": "", "titrePoste": "", "resumeProfessionnel": ""},
            "experience": [], "education": [], "projects": [], "extracurricular": [], "certifications": [], "skills": [], "languages": []
        }
