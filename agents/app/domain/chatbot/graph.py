# app/domain/chatbot/graph.py
r"""
GRAPHE LANGGRAPH — Interview Prep Agent

STRUCTURE :
                    START
                      │
                 router_node          ← lit request_type et décide
                /     |      \   \
   questions_node  interview  salary  free_chat
        │            _node    _node    _node
        │              │
        │         evaluator_node  ← seulement si session_complete=True
        │              │
                      END

CHAQUE NOEUD :
  - Reçoit le State complet
  - Retourne un dict avec SEULEMENT les champs modifiés
  - Ne modifie jamais directement le State
"""

import uuid
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from app.core.config import get_llm, get_llm_precise
from app.domain.chatbot.state import (
    InterviewPrepState, MessageTurn, QuestionItem,
    FeedbackResult, DimensionScore, SalaryResult,
)
from app.domain.chatbot.tools import (
    search_interview_questions,
    search_arena_questions,
    search_salary_data,
)
from app.domain.chatbot.prompts import (
    QUESTIONS_PROMPT_OFFER,
    QUESTIONS_PROMPT_ARENA,
    RECRUITER_PROMPT,
    EVALUATOR_PROMPT,
    SALARY_PROMPT,
    FREE_CHAT_PROMPT,
    SALARY_COACH_FREE_CHAT_PROMPT,
)

# cette ligne crée un "canal" de logs personnalisé pour ce fichier
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# NOEUD 0 — ROUTER
# Décide vers quel noeud aller selon request_type
# ═══════════════════════════════════════════════════════════════

def router_node(state: InterviewPrepState) -> dict:
    """
    Noeud de routage — ne fait rien, juste lit le state.
    La décision est dans router_edge (conditional edge).
    """
    logger.info(f"[ROUTER] request_type={state.request_type} mode={state.mode}")
    return {}   # ne modifie rien


def router_edge(state: InterviewPrepState) -> str:
    """
    Conditional edge — retourne le nom du prochain noeud.
    """
    mapping = {
        "generate_questions":  "questions_node",
        "ask_free":            "free_chat_node",
        "start_interview":     "interview_node",
        "continue_interview":  "interview_node",
        "end_interview":       "evaluator_node",
        "get_salary":          "salary_node",
    }
    destination = mapping.get(state.request_type, "questions_node")
    logger.info(f"[ROUTER] → {destination}")
    return destination


# ═══════════════════════════════════════════════════════════════
# NOEUD 1 — QUESTIONS
# Tab 1 : génère la liste de questions
# ═══════════════════════════════════════════════════════════════

async def questions_node(state: InterviewPrepState) -> dict:
    """
    Génère les questions selon le mode.
    Mode offer  → cherche questions Glassdoor réelles + génère selon offre
    Mode arena  → génère selon domain/level/focus
    """
    logger.info(f"[QUESTIONS] mode={state.mode}")
    llm = get_llm_precise()

    if state.mode == "offer" and state.offer_context:
        offer   = state.offer_context.offer
        company = state.offer_context.company
        match   = state.offer_context.match

        # 1. Récupérer d'abord les questions connues de la base de données (seed)
        db_questions = company.known_questions if company.known_questions else []
        combined_questions = list(db_questions)

        # Si la base de données ne contient aucune question connue pour cette entreprise,
        # on fait une recherche en direct sur Tavily en fallback
        if not combined_questions:
            logger.info(f"[QUESTIONS] Aucune question en base pour {offer.company_name}. Lancement de Tavily...")
            web_questions = await search_interview_questions(
                offer.company_name, offer.job_title
            )
            for q in web_questions:
                if q not in combined_questions:
                    combined_questions.append(q)
        else:
            logger.info(f"[QUESTIONS] {len(combined_questions)} questions trouvées en base pour {offer.company_name}. Bypass de Tavily.")

        # 2. Construire le prompt avec tout le contexte
        prompt = QUESTIONS_PROMPT_OFFER.format(
            company=offer.company_name,
            role=offer.job_title,
            location=offer.location if offer.location else "Remote",
            contract_type=offer.contract_type if offer.contract_type else "Full-time",
            skills=", ".join(offer.required_skills),
            missing=", ".join(match.missing_skills),
            glassdoor_questions="\n".join(combined_questions) if combined_questions else "None found",
        )

    else:
        # Mode arena
        cfg = state.arena_config
        domain = cfg.domain if cfg else "Software"
        level  = cfg.level  if cfg else "junior"
        focus  = cfg.focus_areas if cfg else []

        # 1. Chercher des questions de référence
        ref_questions = await search_arena_questions(domain, level, focus)

        # 2. Construire le prompt arena
        prompt = QUESTIONS_PROMPT_ARENA.format(
            domain=domain,
            level=level,
            language=cfg.language if cfg else "en",
            focus=", ".join(focus) if focus else "auto-balanced",
            ref_questions="\n".join(ref_questions) if ref_questions else "",
        )

    # 3. Appeler le LLM → reçoit JSON
    messages = [
        SystemMessage(content="You are an expert interview coach. Return ONLY valid JSON, no markdown."),
        HumanMessage(content=prompt),
    ]

    try:
        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        # Nettoyer les backticks si présents
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        questions = [
            QuestionItem(
                id=str(uuid.uuid4()),
                question=q.get("question", ""),
                type=q.get("type", "behavioral"),
                source=q.get("source", "generated"),
                company_specific=q.get("company_specific", False),
                tip=q.get("tip", ""),
            )
            for q in data.get("questions", [])
        ]
        logger.info(f"[QUESTIONS] Generated {len(questions)} questions")
        return {"questions": questions}

    except Exception as e:
        logger.error(f"[QUESTIONS] Error: {e}")
        return {"error": str(e), "questions": []}


# ═══════════════════════════════════════════════════════════════
# NOEUD 2 — FREE CHAT
# Tab 1 : chat libre (l'user pose des questions à l'agent)
# ═══════════════════════════════════════════════════════════════

async def free_chat_node(state: InterviewPrepState) -> dict:
    """
    Répond aux questions libres de l'utilisateur dans le tab Questions ou dans le tab Salary Coach.
    Ex: 'Comment répondre à la Q2 ?' / 'Quelles questions sur Kafka ?'
    """
    logger.info(f"[FREE_CHAT] Answering free question. chat_type={state.chat_type}")
    llm = get_llm(temperature=0.5)

    if state.chat_type == "salary":
        db_min = 0
        db_max = 0
        db_target = 0
        currency = "MAD"
        contract_type = "Full-time"
        job_title = "Software Engineer"
        location = "Morocco"

        if state.offer_context:
            o = state.offer_context.offer
            c = state.offer_context.company
            job_title = o.job_title
            location = o.location if o.location else "Morocco"
            db_min = c.salary_min
            db_max = c.salary_max
            db_target = int(c.salary_min + (c.salary_max - c.salary_min) * 0.8) if c.salary_max > c.salary_min else c.salary_min
            currency = c.currency if c.currency else "MAD"

            # Détection et normalisation robuste du type de contrat stage/PFE/PFA
            raw_contract = (o.contract_type or "").lower()
            title_lower = (o.job_title or "").lower()
            if "stage" in raw_contract or "pfe" in raw_contract or "pfa" in raw_contract or "intern" in raw_contract or \
               "stage" in title_lower or "pfe" in title_lower or "pfa" in title_lower or "intern" in title_lower or "stagiaire" in title_lower:
                contract_type = "stage"
            else:
                contract_type = o.contract_type if o.contract_type else "Full-time"
        elif state.arena_config:
            cfg = state.arena_config
            domain_name = cfg.domain if cfg else "Software Engineer"
            level_name  = cfg.level.capitalize() if cfg else ""
            job_title = f"{level_name} {domain_name} Engineer" if "Engineer" not in domain_name else f"{level_name} {domain_name}"
            location  = "Morocco"

            # Détection et normalisation robuste du type de contrat stage/PFE/PFA
            title_lower = job_title.lower()
            if "stage" in title_lower or "pfe" in title_lower or "pfa" in title_lower or "intern" in title_lower or "stagiaire" in title_lower:
                contract_type = "stage"
            else:
                contract_type = "Full-time"

            if state.salary:
                db_min = state.salary.range_min
                db_max = state.salary.range_max
                currency = state.salary.currency
                db_target = state.salary.your_target

        system = SALARY_COACH_FREE_CHAT_PROMPT.format(
            job_title=job_title,
            location=location,
            contract_type=contract_type,
            db_min=db_min,
            db_max=db_max,
            currency=currency,
            db_target=db_target
        )
    else:
        # Construire le contexte classique
        ctx = ""
        if state.offer_context:
            o = state.offer_context.offer
            c = state.offer_context.company
            ctx = (
                f"Company: {o.company_name}\n"
                f"Role: {o.job_title}\n"
                f"Summary: {c.company_summary}\n"
                f"Required skills: {', '.join(o.required_skills)}\n"
            )
        system = FREE_CHAT_PROMPT.format(context=ctx)

    # Historique des 6 derniers messages
    lc_messages = [SystemMessage(content=system)]
    for turn in state.messages[-6:]:
        if turn.role == "user":
            lc_messages.append(HumanMessage(content=turn.content))
        else:
            lc_messages.append(AIMessage(content=turn.content))

    lc_messages.append(HumanMessage(content=state.user_input))

    try:
        response = await llm.ainvoke(lc_messages)
        new_turn = MessageTurn(role="ai", content=response.content)

        # Ajouter le message user + la réponse AI à l'historique
        user_turn = MessageTurn(role="user", content=state.user_input)
        updated_messages = state.messages + [user_turn, new_turn]

        return {"messages": updated_messages}

    except Exception as e:
        logger.error(f"[FREE_CHAT] Error: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# NOEUD 3 — INTERVIEW (Recruteur IA)
# Tab 2 : mock interview — l'IA joue le recruteur
# ═══════════════════════════════════════════════════════════════

async def interview_node(state: InterviewPrepState) -> dict:
    """
    Gère la session mock interview.
    - start_interview → message d'ouverture du recruteur
    - continue_interview → réponse au message de l'user
    """
    logger.info(f"[INTERVIEW] request_type={state.request_type}")
    llm = get_llm(temperature=0.6)

    # 1. Déterminer la langue une seule fois
    lang = "English"  # Fallback par défaut
    if state.arena_config and state.arena_config.language:
        lang = state.arena_config.language

    # 2. Construire le prompt recruteur selon le mode
    if state.mode == "offer" and state.offer_context:
        o = state.offer_context.offer
        c = state.offer_context.company
        m = state.offer_context.match
        msg_count = len(state.messages)
        system = RECRUITER_PROMPT.format(
            company=o.company_name,
            role=o.job_title,
            location=o.location if o.location else "Remote",
            contract_type=o.contract_type if o.contract_type else "Full-time",
            culture=c.company_summary if c.company_summary else "innovative and professional",
            skills=", ".join(o.required_skills[:6]),
            difficulty=c.interview_difficulty,
            language=lang,
            duration=state.arena_config.duration_minutes if state.arena_config else 20,
            missing_skills=", ".join(m.missing_skills) if m.missing_skills else "None identified",
            strengths=", ".join(m.strengths) if m.strengths else "Highly qualified candidate",
            salary_min=c.salary_min,
            salary_max=c.salary_max,
            salary_currency=c.currency if c.currency else "USD",
            msg_count=msg_count,
        )
    else:
        cfg = state.arena_config
        system = RECRUITER_PROMPT.format(
            company="a leading company",
            role=f"{cfg.level if cfg else 'mid'} {cfg.domain if cfg else 'Software'} engineer",
            location="Remote",
            contract_type="Full-time",
            culture="innovative and collaborative",
            skills=", ".join(cfg.focus_areas[:6]) if cfg and cfg.focus_areas else "core skills",
            difficulty="medium",
            language=lang,
            duration=cfg.duration_minutes if cfg else 20,
            missing_skills="None",
            strengths="Motivated professional",
            salary_min=50000,
            salary_max=120000,
            salary_currency="USD",
            msg_count=len(state.messages),
        )

    # Construire les messages LangChain
    lc_messages = [SystemMessage(content=system)]
    for turn in state.messages:
        if turn.role == "user":
            lc_messages.append(HumanMessage(content=turn.content))
        else:
            lc_messages.append(AIMessage(content=turn.content))

    # Si l'user a envoyé un message, l'ajouter
    if state.user_input and state.request_type == "continue_interview":
        lc_messages.append(HumanMessage(content=state.user_input))

    try:
        response = await llm.ainvoke(lc_messages)
        ai_turn = MessageTurn(role="ai", content=response.content)

        updated = list(state.messages)
        if state.user_input and state.request_type == "continue_interview":
            updated.append(MessageTurn(role="user", content=state.user_input))
        updated.append(ai_turn)

        return {"messages": updated}

    except Exception as e:
        logger.error(f"[INTERVIEW] Error: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# NOEUD 4 — EVALUATOR
# Tab 2 : appelé quand la session se termine
# ═══════════════════════════════════════════════════════════════

async def evaluator_node(state: InterviewPrepState) -> dict:
    """
    Analyse tout le transcript et génère le feedback + score.
    Appelé seulement quand request_type = 'end_interview'.
    """
    logger.info("[EVALUATOR] Evaluating session")
    llm = get_llm_precise()

    # Construire le transcript
    transcript = "\n\n".join([
        f"{'RECRUITER' if t.role == 'ai' else 'CANDIDATE'}: {t.content}"
        for t in state.messages
    ])

    ctx = ""
    if state.mode == "offer" and state.offer_context:
        o = state.offer_context.offer
        ctx = f"Role: {o.job_title} at {o.company_name}"
    elif state.arena_config:
        cfg = state.arena_config
        ctx = f"Domain: {cfg.domain}, Level: {cfg.level}"

    prompt = EVALUATOR_PROMPT.format(context=ctx, transcript=transcript)

    lc_messages = [
        SystemMessage(content="You are an expert interview evaluator. Return ONLY valid JSON."),
        HumanMessage(content=prompt),
    ]

    try:
        response = await llm.ainvoke(lc_messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        feedback = FeedbackResult(
            global_score=data.get("global_score", 0),
            dimensions=[DimensionScore(**d) for d in data.get("dimensions", [])],
            strengths=data.get("strengths", []),
            improvements=data.get("improvements", []),
            best_answer=data.get("best_answer", ""),
            worst_answer=data.get("worst_answer", ""),
            coaching_tips=data.get("coaching_tips", []),
        )
        logger.info(f"[EVALUATOR] Score: {feedback.global_score}")
        return {"feedback": feedback, "session_complete": True}

    except Exception as e:
        logger.error(f"[EVALUATOR] Error: {e}")
        return {"error": str(e), "session_complete": True}


# ═══════════════════════════════════════════════════════════════
# NOEUD 5 — SALARY
# Tab 3 : coach salaire + argumentaire négociation
# ═══════════════════════════════════════════════════════════════

async def salary_node(state: InterviewPrepState) -> dict:
    """
    Génère l'analyse salariale et le script de négociation.
    Fonctionne en mode offer (données entreprise) et arena (marché général).
    """
    logger.info(f"[SALARY] mode={state.mode}")
    llm = get_llm_precise()

    # Déterminer job_title + location
    db_min = 0
    db_max = 0
    db_target = 0
    currency = "MAD"

    if state.mode == "offer" and state.offer_context:
        o = state.offer_context.offer
        c = state.offer_context.company
        job_title = o.job_title
        location  = o.location if o.location else "Mountain View, CA"
        db_min = c.salary_min
        db_max = c.salary_max
        db_target = int(c.salary_min + (c.salary_max - c.salary_min) * 0.8) if c.salary_max > c.salary_min else c.salary_min
        currency = c.currency if c.currency else "USD"

        # Détection et normalisation robuste du type de contrat stage/PFE/PFA
        raw_contract = (o.contract_type or "").lower()
        title_lower = (o.job_title or "").lower()
        if "stage" in raw_contract or "pfe" in raw_contract or "pfa" in raw_contract or "intern" in raw_contract or \
           "stage" in title_lower or "pfe" in title_lower or "pfa" in title_lower or "intern" in title_lower or "stagiaire" in title_lower:
            contract_type = "stage"
        else:
            contract_type = o.contract_type if o.contract_type else "Full-time"

        extra = (
            f"Company: {o.company_name}\n"
            f"Contract Type: {contract_type}\n"
            f"Candidate strengths: {', '.join(state.offer_context.match.strengths)}\n"
        )
    else:
        cfg = state.arena_config
        domain_name = cfg.domain if cfg else "Software Engineer"
        level_name  = cfg.level.capitalize() if cfg else ""
        job_title = f"{level_name} {domain_name} Engineer" if "Engineer" not in domain_name else f"{level_name} {domain_name}"
        location  = "Morocco"
        db_min = 150000 if cfg and cfg.level == "senior" else (90000 if cfg and cfg.level == "mid" else 50000)
        db_max = 300000 if cfg and cfg.level == "senior" else (180000 if cfg and cfg.level == "mid" else 90000)
        db_target = int(db_min + (db_max - db_min) * 0.75)
        currency = "MAD"
        extra = ""

    # Recherche données marché
    market_data = await search_salary_data(job_title, location)

    lang = "en"
    if state.arena_config and state.arena_config.language:
        lang = state.arena_config.language

    prompt = SALARY_PROMPT.format(
        job_title=job_title,
        location=location,
        extra_context=extra,
        market_raw="\n".join(market_data.get("raw_data", [])),
        currency=currency,
        db_min=db_min,
        db_max=db_max,
        db_target=db_target,
        language=lang,
    )

    lc_messages = [
        SystemMessage(content="You are a salary negotiation expert. Return ONLY valid JSON."),
        HumanMessage(content=prompt),
    ]

    try:
        response = await llm.ainvoke(lc_messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        salary = SalaryResult(
            range_min=data.get("range_min", 0),
            range_max=data.get("range_max", 0),
            currency=data.get("currency", "MAD"),
            your_target=data.get("your_target", 0),
            confidence_level=data.get("confidence_level", "medium"),
            market_sources=data.get("market_sources", []),
            negotiation_script=data.get("negotiation_script", []),
        )
        logger.info(f"[SALARY] Range: {salary.range_min}–{salary.range_max}")
        return {"salary": salary}

    except Exception as e:
        logger.error(f"[SALARY] Error: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# COMPILATION DU GRAPHE
# ═══════════════════════════════════════════════════════════════

def build_graph():
    """
    Construit et compile le graphe LangGraph.
    Appelé une seule fois au démarrage de l'app.

    STRUCTURE DES EDGES :
      START → router_node
      router_node → [conditional] → questions/free_chat/interview/evaluator/salary
      Tous les noeuds → END
    """
    builder = StateGraph(InterviewPrepState)

    # ── Ajouter les noeuds ─────────────────────────────────
    builder.add_node("router_node",    router_node)
    builder.add_node("questions_node", questions_node)
    builder.add_node("free_chat_node", free_chat_node)
    builder.add_node("interview_node", interview_node)
    builder.add_node("evaluator_node", evaluator_node)
    builder.add_node("salary_node",    salary_node)

    # ── Edge de départ ─────────────────────────────────────
    builder.add_edge(START, "router_node")

    # ── Conditional edge depuis router ─────────────────────
    builder.add_conditional_edges(
        "router_node",
        router_edge,
        {
            "questions_node":  "questions_node",
            "free_chat_node":  "free_chat_node",
            "interview_node":  "interview_node",
            "evaluator_node":  "evaluator_node",
            "salary_node":     "salary_node",
        }
    )

    # ── Tous les noeuds terminaux → END ────────────────────
    builder.add_edge("questions_node", END)
    builder.add_edge("free_chat_node", END)
    builder.add_edge("interview_node", END)
    builder.add_edge("evaluator_node", END)
    builder.add_edge("salary_node",    END)

    graph = builder.compile()
    logger.info("✅ LangGraph compiled successfully")
    return graph


# Instance singleton — importée par le router FastAPI
interview_graph = build_graph()




#C'est une exécution du "One-shot" par message
#Pattern Router Vs Pattern Pipeline
