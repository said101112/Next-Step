# ============================================================
# agents/tests/test_sn_copilot.py
#
# Unit tests for SN Copilot intent detection and agent flow
# ============================================================
import pytest
from unittest.mock import patch, AsyncMock
from app.domain.sn_copilot.graph import _detect_intent, run_sn_agent


def test_detect_intent_10_candidatures():
    intent = _detect_intent("donner les last candidature 10 il recupere")
    assert intent["intent"] == "get_candidatures"
    assert intent["limit"] == 10

    intent_fr = _detect_intent("affiche mes 5 dernieres candidatures")
    assert intent_fr["intent"] == "get_candidatures"
    assert intent_fr["limit"] == 5


def test_detect_intent_update_status():
    intent = _detect_intent("passe Doctolib en entretien")
    assert intent["intent"] == "update_status"
    assert intent["company"] == "doctolib"
    assert intent["status"] == "ENTRETIEN_PROPOSE"

    intent_refuse = _detect_intent("change le statut de Google en refuse")
    assert intent_refuse["intent"] == "update_status"
    assert intent_refuse["status"] == "REFUSE"


def test_detect_intent_stats():
    intent = _detect_intent("affiche mes statistiques de conversion")
    assert intent["intent"] == "get_stats"


def test_detect_intent_follow_ups():
    intent = _detect_intent("quelles sont les relances prioritaires ?")
    assert intent["intent"] == "get_follow_ups"


def test_detect_intent_postuler():
    intent = _detect_intent("postule chez Stripe pour Développeur Backend")
    assert intent["intent"] == "postuler"


@pytest.mark.asyncio
async def test_run_sn_agent_get_10_candidatures():
    mock_cands = [
        {
            "id": f"uuid-{i}",
            "id_offre": None,
            "entreprise": f"Company {i}",
            "role": f"Engineer {i}",
            "statut": "ENVOYE",
            "channel": "EMAIL",
            "application_date": "2026-09-01",
            "has_response": False,
            "response_status": "EN_ATTENTE",
            "notes": "",
            "response_summary": None,
            "recommended_action": None,
            "follow_up_needed": False,
        }
        for i in range(10)
    ]

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AsyncMock(content="""Bonjour Jean, voici vos 10 candidatures analysées avec succès.
```json
{
  "suggestions": [
    "Quelles sont mes relances prioritaires ?",
    "Afficher mes statistiques de conversion"
  ]
}
```""")

    with patch("app.domain.sn_copilot.graph.get_recent_candidatures", new_callable=AsyncMock) as mock_get, \
         patch("app.domain.sn_copilot.graph.get_llm", return_value=mock_llm), \
         patch("app.domain.sn_copilot.graph.get_user_profile", new_callable=AsyncMock) as mock_profile:
        mock_get.return_value = mock_cands
        mock_profile.return_value = {
            "personal_info": {"prenom": "Jean", "nom": "Test"},
            "competences": [], "formations": [], "experiences": [],
            "projets": [], "certifications": [],
        }

        res = await run_sn_agent(
            user_id="test-user-123",
            user_message="donner les last candidature 10",
            user_name="Jean"
        )

        assert "markdown_text" in res
        assert len(res["cards"]) == 10
        assert len(res["actions_performed"]) >= 1
        assert len(res["follow_up_suggestions"]) == 2


def test_detect_intent_greeting():
    for g in ["hello", "bonjour", "salut", "bonsoir !", "coucou", "hey", "ça va ?", "ca va"]:
        intent = _detect_intent(g)
        assert intent["intent"] == "greeting", f"Failed for greeting: {g}"


def test_detect_intent_capabilities():
    for c in ["qui es-tu ?", "tu peux faire quoi ?", "qu'est-ce que tu peux faire", "c'est quoi sn"]:
        intent = _detect_intent(c)
        assert intent["intent"] == "capabilities", f"Failed for capability query: {c}"


@pytest.mark.asyncio
async def test_run_sn_agent_greeting_no_unsolicited_cards():
    mock_cands = [
        {"entreprise": "Deloitte", "role": "Stagiaire", "statut": "ENVOYE"}
    ]
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AsyncMock(content="""Bonjour Said ! Ravi de vous retrouver. Comment puis-je vous accompagner aujourd'hui ?
```json
{
  "suggestions": [
    "Afficher mes candidatures en cours",
    "Quelles sont les relances prioritaires ?",
    "Comment préparer mon prochain entretien ?"
  ]
}
```""")

    with patch("app.domain.sn_copilot.graph.get_recent_candidatures", new_callable=AsyncMock) as mock_get, \
         patch("app.domain.sn_copilot.graph.get_llm", return_value=mock_llm), \
         patch("app.domain.sn_copilot.graph.get_user_profile", new_callable=AsyncMock) as mock_profile:
        mock_get.return_value = mock_cands
        mock_profile.return_value = {
            "personal_info": {"prenom": "Said", "nom": "Nichan"},
            "competences": [], "formations": [], "experiences": [],
            "projets": [], "certifications": [],
        }

        res = await run_sn_agent(
            user_id="test-user-123",
            user_message="hello",
            user_name="Said"
        )

        assert "markdown_text" in res
        # Greetings must NOT dump cards or actions badges
        assert res["cards"] == []
        assert res["actions_performed"] == []
        assert len(res["follow_up_suggestions"]) == 3
        assert "Bonjour Said" in res["markdown_text"]


def test_detect_intent_profile_summary():
    """Profile intent should fire for profile/resume queries."""
    for q in [
        "résume mon profil",
        "mon profil",
        "qui suis-je",
        "mes compétences",
        "mes formations",
        "mes expériences",
        "ce que tu connais de moi",
        "parle-moi de moi",
    ]:
        intent = _detect_intent(q)
        assert intent["intent"] == "profile_summary", f"Failed for: {q}"


def test_detect_intent_cv_analysis():
    """CV analysis intent should fire for CV upload markers."""
    intent = _detect_intent("[CV_UPLOAD] Said Nichan, Data Engineer, Python, SQL, etc...")
    assert intent["intent"] == "cv_analysis"
    assert "cv_text" in intent

    intent2 = _detect_intent("voici mon cv Said Nichan ingenieur data 5 ans experience")
    assert intent2["intent"] == "cv_analysis"


def test_detect_intent_cv_matching():
    """CV matching intent should fire for compatibility queries."""
    for q in [
        "match mon cv avec mes candidatures",
        "analyse la compatibilité de mon profil avec mes candidatures",
        "mon profil est compatible avec quelles offres",
        "matcher mon cv",
        "score de match candidatures",
    ]:
        intent = _detect_intent(q)
        assert intent["intent"] == "cv_matching", f"Failed for: {q}"


@pytest.mark.asyncio
async def test_run_sn_agent_profile_summary():
    """Profile summary intent should return profile-related actions."""
    mock_profile = {
        "personal_info": {
            "prenom": "Said", "nom": "Nichan", "email": "said@test.com",
            "titre_poste": "Data Engineer", "ville": "Casablanca", "pays": "Maroc",
            "objectif": "Stage PFE", "secteur": "Tech", "niveau": "Bac+5",
            "resume_professionnel": "", "linkedin": "", "github": "", "portfolio": "",
            "profile_score": 75, "telephone": "",
        },
        "competences": [
            {"nom": "Python", "niveau": 4, "type": "technique"},
            {"nom": "SQL", "niveau": 3, "type": "technique"},
        ],
        "formations": [
            {"etablissement": "ENSA", "diplome": "Ingénieur", "annee": 2026,
             "annee_fin": None, "ville": "Khouribga", "specialisation": "Data", "mention": ""},
        ],
        "experiences": [],
        "projets": [{"titre": "NextStep", "description": "Platform", "technologies": "Angular, .NET", "date": "", "lien": "", "universitaire": True}],
        "certifications": [],
    }
    mock_cands = [{"entreprise": "BCG", "role": "AI Intern", "statut": "ENVOYE"}]

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AsyncMock(content="""Voici votre profil Said :
- **Data Engineer** basé à Casablanca
- Compétences : Python, SQL
- Formation : Ingénieur ENSA (Data)
```json
{"suggestions": ["Matcher CV et candidatures", "Afficher candidatures", "Mes compétences clés"]}
```""")

    with patch("app.domain.sn_copilot.graph.get_recent_candidatures", new_callable=AsyncMock) as mock_get, \
         patch("app.domain.sn_copilot.graph.get_llm", return_value=mock_llm), \
         patch("app.domain.sn_copilot.graph.get_user_profile", new_callable=AsyncMock) as mock_prof:
        mock_get.return_value = mock_cands
        mock_prof.return_value = mock_profile

        res = await run_sn_agent(
            user_id="test-user-123",
            user_message="résume mon profil",
            user_name="Said Nichan"
        )

        assert "markdown_text" in res
        assert any("profil" in a.lower() for a in res["actions_performed"])
        assert res["cards"] == []
        assert len(res["follow_up_suggestions"]) == 3
