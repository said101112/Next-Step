# ============================================================
# app/domain/company/tools/linkedin_tool.py
# ============================================================
import logging
from app.domain.company.tools.web_tool import smart_search

logger = logging.getLogger(__name__)

async def linkedin_company_search(company_name: str) -> dict:
    """
    Récupère la page LinkedIn officielle de l'entreprise via recherche ciblée.
    """
    logger.info(f"🔗 LinkedIn Tool — Recherche du lien LinkedIn pour {company_name}")
    try:
        results = await smart_search(f"{company_name} LinkedIn company", must_mention=company_name)
        for r in results:
            url = r.get("url", "")
            if "linkedin.com/company/" in url:
                # Extraire la partie propre de l'URL (sans query params)
                if "?" in url:
                    url = url.split("?")[0]
                logger.info(f"✅ LinkedIn trouvé : {url}")
                return {"type": "linkedin", "company": company_name, "url": url}
    except Exception as e:
        logger.error(f"❌ Erreur recherche LinkedIn : {e}")

    return {"type": "linkedin", "company": company_name, "url": f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}"}
