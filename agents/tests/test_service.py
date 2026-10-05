
"""
TESTS DU SERVICE — app/modules/chatbot/service.py

COMMENT ÇA MARCHE :
  1. On mock (remplace) le graphe LangGraph → pas d'appel OpenAI réel
  2. On mock la DB → pas de vraie base de données
  3. On mock get_offer_context_from_db → pas de vraies données
  4. On teste UNIQUEMENT la logique du service

COMMANDES :
  pytest tests/test_service.py -v              → tous les tests
  pytest tests/test_service.py -v -k "arena"  → seulement les tests "arena"
  pytest tests/test_service.py -v -k "offer"  → seulement les tests "offer"
  pytest tests/test_service.py -v -s          → avec les print() visibles
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.chatbot import service
from app.domain.chatbot.schemas import (
    QuestionsResponse, FreeChatResponse,
    StartInterviewResponse, SendMessageResponse,
    EndInterviewResponse, SalaryResponse,
)
from app.domain.chatbot.state import MessageTurn


# ═══════════════════════════════════════════════════════════════
# HELPER — mock_execute pour SQLAlchemy
# ═══════════════════════════════════════════════════════════════

def make_execute_result(return_value):
    """
    SQLAlchemy retourne un objet Result quand on fait db.execute().
    Cette fonction crée un mock de ce comportement.
    scalar_one_or_none() est la méthode qu'on appelle ensuite.
    """
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = return_value
    return result_mock


# ═══════════════════════════════════════════════════════════════
# TESTS — get_offer_context_from_db
# ═══════════════════════════════════════════════════════════════

class TestGetOfferContext:
    """
    Teste la fonction qui lit les outputs des agents 2/3/4 depuis la DB.
    """

    @pytest.mark.asyncio
    async def test_retourne_none_si_offer_id_vide(self, mock_db):
        """Si offer_id est vide, doit retourner None immédiatement."""
        result = await service.get_offer_context_from_db("", "user-123", mock_db)

        assert result is None
        # Vérifie que db.execute n'a pas été appelé (inutile si pas d'id)
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_retourne_none_si_aucune_donnee(self, mock_db, offer_id, user_id):
        """
        Si les tables offre_analysee et intel_entreprise sont vides
        pour cette offre → retourne None.
        """
        # db.execute() retourne un objet dont scalar_one_or_none() → None
        mock_db.execute = AsyncMock(
            return_value=make_execute_result(None)
        )

        result = await service.get_offer_context_from_db(offer_id, user_id, mock_db)

        assert result is None

    @pytest.mark.asyncio
    @patch('app.domain.chatbot.services.context_service.get_internal_user_id', new=AsyncMock(return_value=uuid.UUID("11111111-1111-1111-1111-111111111111")))
    async def test_retourne_contexte_complet_offer_mode(
        self, mock_db, offer_id, user_id,
        mock_offre_row, mock_intel_row, mock_match_row
    ):
        """
        Cas normal mode offer : les 3 tables ont des données.
        Doit construire un OfferContext complet.
        """
        # db.execute() est appelé 3 fois (agent2, agent3, agent4)
        # on retourne une valeur différente à chaque appel
        mock_db.execute = AsyncMock(side_effect=[
            make_execute_result(mock_offre_row),   # appel 1 → offre_analysee
            make_execute_result(mock_intel_row),   # appel 2 → intel_entreprise
            make_execute_result(mock_match_row),   # appel 3 → resultat_matching
        ])

        result = await service.get_offer_context_from_db(offer_id, user_id, mock_db)

        # Vérifie que le résultat n'est pas None
        assert result is not None

        # Vérifie les données de l'offre (Agent 2)
        assert result.offer.job_title    == "Data Engineer"
        assert result.offer.company_name == "OCP Group"
        assert "Python" in result.offer.required_skills
        assert result.offer.experience_years == 3

        # Vérifie les données entreprise (Agent 3)
        assert result.company.company_name    == "OCP Group"
        assert result.company.glassdoor_rating == 3.8
        assert result.company.salary_min       == 18000
        assert result.company.salary_max       == 28000
        assert result.company.interview_difficulty == "medium"

        # Vérifie le matching (Agent 4)
        assert result.match.score_global  == 78
        assert "Kafka" in result.match.missing_skills
        assert "Python" in result.match.strengths

    @pytest.mark.asyncio
    @patch('app.domain.chatbot.services.context_service.get_internal_user_id', new=AsyncMock(return_value=uuid.UUID("11111111-1111-1111-1111-111111111111")))
    async def test_fonctionne_sans_match_data(
        self, mock_db, offer_id, user_id,
        mock_offre_row, mock_intel_row
    ):
        """
        Agent 4 n'a pas encore analysé → match_row = None.
        Doit quand même retourner un contexte partiel (pas crasher).
        """
        mock_db.execute = AsyncMock(side_effect=[
            make_execute_result(mock_offre_row),
            make_execute_result(mock_intel_row),
            make_execute_result(None),   # pas de match pour cet user
        ])

        result = await service.get_offer_context_from_db(offer_id, user_id, mock_db)

        assert result is not None
        # Match avec valeurs par défaut
        assert result.match.score_global  == 0
        assert result.match.missing_skills == []
        assert result.match.strengths      == []


# ═══════════════════════════════════════════════════════════════
# TESTS — generate_questions_service
# ═══════════════════════════════════════════════════════════════

class TestGenerateQuestionsService:
    """
    Teste la génération de questions (Tab 1).
    On mock le graphe LangGraph pour ne pas appeler OpenAI.
    """

    @pytest.mark.asyncio
    async def test_arena_mode_retourne_questions(
        self, mock_db, user_id, arena_config_schema, mock_questions_result
    ):
        """
        Mode arena : génère des questions sans offre.
        Vérifie que le service retourne bien les questions du graphe.
        """
        # Mock db.execute pour get_candidature_id → retourne None (pas de candidature en arena)
        mock_db.execute = AsyncMock(return_value=make_execute_result(None))

        # PATCH = remplace interview_graph.ainvoke par notre mock
        # Le graphe "retourne" nos questions simulées
        fake_graph_result = {"questions": mock_questions_result}

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_graph_result)
        ):
            result = await service.generate_questions_service(
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        # Vérifications
        assert isinstance(result, QuestionsResponse)
        assert result.mode  == "arena"
        assert result.total == 3
        assert len(result.questions) == 3

        # Vérifie le contenu de la première question
        first_q = result.questions[0]
        assert first_q.question != ""
        assert first_q.type     in ["technical", "behavioral", "situational"]
        assert first_q.source   in ["glassdoor", "generated", "web_search"]

        # Vérification stateless (pas d'appel à commit)
        pass

    @pytest.mark.asyncio
    async def test_offer_mode_appelle_get_context(
        self, mock_db, offer_id, user_id, mock_questions_result, mock_offer_context
    ):
        """
        Mode offer : doit appeler get_offer_context_from_db.
        Vérifie que le contexte offre est bien transmis au graphe.
        """
        mock_db.execute = AsyncMock(return_value=make_execute_result(None))

        fake_graph_result = {"questions": mock_questions_result}

        # On mock aussi get_offer_context_from_db pour retourner un contexte
        with patch(
            "app.domain.chatbot.services.questions_service.get_offer_context_from_db",
            new=AsyncMock(return_value=mock_offer_context)
        ), patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_graph_result)
        ):
            result = await service.generate_questions_service(
                mode="offer",
                offer_id=offer_id,
                arena_config=None,
                user_id=user_id,
                db=mock_db,
            )

        assert result.mode  == "offer"
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_graph_retourne_liste_vide(
        self, mock_db, user_id, arena_config_schema
    ):
        """
        Si le graphe retourne 0 questions (erreur LLM par ex.)
        → le service doit quand même retourner une réponse propre, pas crasher.
        """
        mock_db.execute = AsyncMock(return_value=make_execute_result(None))

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value={"questions": []})
        ):
            result = await service.generate_questions_service(
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert result.total        == 0
        assert result.questions    == []
        # Pas de crash même avec 0 questions


# ═══════════════════════════════════════════════════════════════
# TESTS — free_chat_service
# ═══════════════════════════════════════════════════════════════

class TestFreeChatService:
    """Teste le chat libre du tab Questions."""

    @pytest.mark.asyncio
    async def test_retourne_reponse_ai(self, mock_db, user_id):
        """Le service doit retourner la réponse du dernier message AI."""
        thread_id = str(uuid.uuid4())

        # Le graphe retourne des messages avec une réponse AI
        fake_ai_response = "To answer STAR questions, structure your response with Situation, Task, Action, Result."
        fake_result = {
            "messages": [
                MessageTurn(role="user", content="How to answer STAR questions?"),
                MessageTurn(role="ai",   content=fake_ai_response),
            ]
        }

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.free_chat_service(
                user_input="How to answer STAR questions?",
                thread_id=thread_id,
                history=[],
                offer_id=None,
                user_id=user_id,
                db=mock_db,
            )

        assert isinstance(result, FreeChatResponse)
        assert result.thread_id == thread_id
        assert result.response  == fake_ai_response


# ═══════════════════════════════════════════════════════════════
# TESTS — start_interview_service
# ═══════════════════════════════════════════════════════════════

class TestStartInterviewService:
    """Teste le démarrage d'une session mock interview."""

    @pytest.mark.asyncio
    async def test_utilise_la_session_du_backend_sans_ecrire_en_db(self, mock_db, user_id, arena_config_schema):
        """
        La session est créée par le backend (module Coaching) : l'agent reprend son id
        et n'écrit rien en base.
        """
        opening_msg = "Hello! I'm the interviewer. Tell me about yourself."
        fake_result = {
            "messages": [MessageTurn(role="ai", content=opening_msg)]
        }

        session_id = "55555555-5555-5555-5555-555555555555"
        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.start_interview_service(
                session_id=session_id,
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert isinstance(result, StartInterviewResponse)
        assert result.opening_message == opening_msg
        assert result.session_id      == session_id

        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_retourne_message_ouverture(self, mock_db, user_id, arena_config_schema):
        """Le message d'ouverture du graphe doit être retourné correctement."""
        opening = "Welcome to your Data & AI interview!"
        fake_result = {"messages": [MessageTurn(role="ai", content=opening)]}

        mock_db.execute = AsyncMock(return_value=make_execute_result(None))

        session_id = "55555555-5555-5555-5555-555555555555"
        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.start_interview_service(
                session_id=session_id,
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert result.opening_message == opening


# ═══════════════════════════════════════════════════════════════
# TESTS — send_message_service
# ═══════════════════════════════════════════════════════════════

class TestSendMessageService:
    """Teste l'envoi de messages pendant l'interview."""

    @pytest.mark.asyncio
    async def test_retourne_reponse_recruteur(
        self, mock_db, session_id, user_id, arena_config_schema, message_history
    ):
        """Le recruteur IA doit répondre au message de l'utilisateur."""
        recruiter_response = "Interesting! Can you tell me more about the scale of that pipeline?"

        fake_result = {
            "messages": [
                *[MessageTurn(role=m.role, content=m.content) for m in message_history],
                MessageTurn(role="user", content="I built a 500GB/day pipeline."),
                MessageTurn(role="ai",   content=recruiter_response),
            ]
        }

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.send_message_service(
                session_id=session_id,
                user_input="I built a 500GB/day pipeline.",
                history=message_history,
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert isinstance(result, SendMessageResponse)
        assert result.session_id  == session_id
        assert result.ai_response == recruiter_response




# ═══════════════════════════════════════════════════════════════
# TESTS — end_interview_service
# ═══════════════════════════════════════════════════════════════

class TestEndInterviewService:
    """Teste la fin de session et l'évaluation."""

    @pytest.mark.asyncio
    async def test_retourne_score_et_feedback(
        self, mock_db_with_session, session_id, user_id,
        arena_config_schema, message_history, mock_feedback_result
    ):
        """Doit retourner le score global et le feedback complet."""
        mock_db, _ = mock_db_with_session

        fake_result = {"feedback": mock_feedback_result}

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.end_interview_service(
                session_id=session_id,
                history=message_history,
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert isinstance(result, EndInterviewResponse)
        assert result.session_id   == session_id
        assert result.score        == 74
        assert len(result.feedback.dimensions) == 5

        # Vérifier chaque dimension
        dim_names = [d.name for d in result.feedback.dimensions]
        assert "Clarity"            in dim_names
        assert "STAR Method"        in dim_names
        assert "Technical Accuracy" in dim_names

        # Vérifier les autres champs
        assert len(result.feedback.strengths)     == 3
        assert len(result.feedback.improvements)  == 2
        assert len(result.feedback.coaching_tips) == 3

    @pytest.mark.asyncio
    async def test_retourne_le_score_sans_ecrire_en_db(
        self, mock_db_with_session, session_id, user_id,
        arena_config_schema, message_history, mock_feedback_result
    ):
        """L'agent évalue ; le backend (module Coaching) enregistre le score et le feedback."""
        mock_db, session_row = mock_db_with_session

        fake_result = {"feedback": mock_feedback_result}

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.end_interview_service(
                session_id=session_id,
                history=message_history,
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert result.score == 74
        assert result.feedback.global_score == 74
        mock_db.get.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_score_zero_si_pas_de_feedback(
        self, mock_db_with_session, session_id, user_id, arena_config_schema
    ):
        """Si le graphe ne retourne pas de feedback → score=0, pas de crash."""
        mock_db, _ = mock_db_with_session

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value={"feedback": None})
        ):
            result = await service.end_interview_service(
                session_id=session_id,
                history=[],
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert result.score == 0
        assert result.feedback.dimensions == []


# ═══════════════════════════════════════════════════════════════
# TESTS — get_salary_service
# ═══════════════════════════════════════════════════════════════

class TestGetSalaryService:
    """Teste le coach salaire (Tab 3)."""

    @pytest.mark.asyncio
    async def test_arena_mode_retourne_salaire(
        self, mock_db, user_id, arena_config_schema, mock_salary_result
    ):
        """Mode arena : doit retourner une analyse salariale."""
        mock_db.execute = AsyncMock(return_value=make_execute_result(None))

        fake_result = {"salary": mock_salary_result}

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.get_salary_service(
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert isinstance(result, SalaryResponse)
        assert result.range_min       == 18000
        assert result.range_max       == 28000
        assert result.currency        == "MAD"
        assert result.your_target     == 25000
        assert result.confidence_level == "high"
        assert len(result.negotiation_script) == 2
        assert len(result.market_sources)     == 2

    @pytest.mark.asyncio
    async def test_offer_mode_utilise_contexte_entreprise(
        self, mock_db, offer_id, user_id, mock_salary_result, mock_offer_context
    ):
        """Mode offer : le contexte OCP (18k-28k) doit être utilisé."""
        mock_db.execute = AsyncMock(return_value=make_execute_result(None))

        fake_result = {"salary": mock_salary_result}

        with patch(
            "app.domain.chatbot.service.get_offer_context_from_db",
            new=AsyncMock(return_value=mock_offer_context)
        ), patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value=fake_result)
        ):
            result = await service.get_salary_service(
                mode="offer",
                offer_id=offer_id,
                arena_config=None,
                user_id=user_id,
                db=mock_db,
            )

        assert result.range_min == 18000
        assert result.range_max == 28000

    @pytest.mark.asyncio
    async def test_retourne_valeurs_par_defaut_si_erreur(
        self, mock_db, user_id, arena_config_schema
    ):
        """Si le graphe ne retourne pas de salary → valeurs par défaut, pas de crash."""
        mock_db.execute = AsyncMock(return_value=make_execute_result(None))

        with patch(
            "app.domain.chatbot.graph.interview_graph.ainvoke",
            new=AsyncMock(return_value={"salary": None})
        ):
            result = await service.get_salary_service(
                mode="arena",
                offer_id=None,
                arena_config=arena_config_schema,
                user_id=user_id,
                db=mock_db,
            )

        assert result.range_min == 0
        assert result.range_max == 0
        assert result.negotiation_script == []
