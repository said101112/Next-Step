# ============================================================
# app/domain/company/tools/glassdoor_tool.py
# ============================================================
import logging
import asyncio
from app.domain.company.tools.web_tool import smart_search, high_precision_scrape

logger = logging.getLogger(__name__)

async def glassdoor_search(company_name: str) -> dict:
    """Récupère les notes, avis, et questions d'entretien depuis Glassdoor, Indeed, Rekrute, et d'autres sources RH."""
    logger.info(f"🌱 Reviews Tool — Recherche d'avis et culture multi-sources (Glassdoor, Indeed, Rekrute) pour {company_name}")
    try:
        q1 = f"{company_name} Glassdoor avis"
        q2 = f"{company_name} Indeed Maroc avis"
        q3 = f"{company_name} Rekrute entreprise"
        q4 = f"{company_name} questions entretien embauche"

        # Lancer les recherches en parallèle
        r1, r2, r3, r4 = await asyncio.gather(
            smart_search(q1, must_mention=company_name),
            smart_search(q2, must_mention=company_name),
            smart_search(q3, must_mention=company_name),
            smart_search(q4, must_mention=company_name)
        )
        all_results = r1 + r2 + r3 + r4

        # Filtrer et dédupliquer les URLs par domaine de confiance
        trusted_domains = ["glassdoor", "indeed", "rekrute", "hellowork", "stagiaires.ma", "linkedin"]

        target_urls = []
        for r in all_results:
            url = r["url"].lower()
            if any(domain in url for domain in trusted_domains) and r["url"] not in target_urls:
                target_urls.append(r["url"])

        scraped_contents = []
        # On va scraper les 3 meilleures sources RH trouvées (ex: Glassdoor, Indeed, Rekrute)
        urls_to_scrape = target_urls[:3]
        logger.info(f"🎯 Sources RH identifiées à scraper en parallèle: {urls_to_scrape}")

        scraping_tasks = [high_precision_scrape(url) for url in urls_to_scrape]
        if scraping_tasks:
            scraped_results = await asyncio.gather(*scraping_tasks)
            for url, content in zip(urls_to_scrape, scraped_results):
                if "just a moment" in content.lower() or "forbidden" in content.lower() or len(content.strip()) < 100:
                    logger.warning(f"⚠️ Scraping bloqué ou vide pour {url}, ignoré.")
                    continue
                scraped_contents.append(f"--- SOURCE RH: {url} ---\n{content}")

        # Combiner les snippets pour un fallback résilient
        all_snippets = []
        for r in all_results[:12]:
            if r.get("snippet"):
                all_snippets.append(f"[{r['url']}]: {r['snippet']}")

        return {
            "type": "glassdoor",  # Garder le type "glassdoor" pour compatibilité du graphe
            "company": company_name,
            "url": urls_to_scrape[0] if urls_to_scrape else (target_urls[0] if target_urls else None),
            "raw_text": "\n\n".join(scraped_contents) if scraped_contents else "Analyse basée sur les extraits web.",
            "interview_raw_text": "\n\n".join(scraped_contents) if scraped_contents else "Analyse basée sur les extraits web.",
            "search_snippets": all_snippets[:6],
            "interview_snippets": all_snippets[6:12]
        }
    except Exception as e:
        logger.error(f"❌ Erreur recherche avis multi-sources : {e}")
        return {"type": "glassdoor", "company": company_name, "raw_text": "Non disponible", "search_snippets": []}
