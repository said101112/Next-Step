# ============================================================
# app/domain/company/tools/salary_tool.py
# ============================================================
import logging
import asyncio
from typing import Optional
from app.domain.company.tools.web_tool import smart_search, high_precision_scrape

logger = logging.getLogger(__name__)

async def salary_data_search(company_name: str, job_title: str, location: Optional[str] = None) -> dict:
    """
    Récupère les fourchettes de salaires pour un poste depuis Levels.fyi, Indeed, Rekrute, et Glassdoor.
    """
    logger.info(f"💰 Salary Tool — Recherche de salaires multi-sources pour {company_name} - {job_title}")

    q1 = f"{company_name} {job_title} salaire"
    if location:
        q1 += f" {location}"
    q2 = f"{company_name} Indeed salaires"
    q3 = f"site:rekrute.com \"{company_name}\" salaires"
    q4 = f"{company_name} levels.fyi"

    try:
        results_q1, results_q2, results_q3, results_q4 = await asyncio.gather(
            smart_search(q1, must_mention=company_name),
            smart_search(q2, must_mention=company_name),
            smart_search(q3, must_mention=company_name),
            smart_search(q4, must_mention=company_name)
        )

        all_results = results_q1 + results_q2 + results_q3 + results_q4

        # Priorités de domaine pour éviter les blocages de Glassdoor et obtenir des infos marocaines locales
        priority_domains = ["levels.fyi", "rekrute", "indeed", "stagiaires.ma", "glassdoor"]

        salary_urls = []
        for domain in priority_domains:
            for r in all_results:
                url = r["url"].lower()
                if domain in url and r["url"] not in salary_urls:
                    salary_urls.append(r["url"])

        if not salary_urls and all_results:
            salary_urls = [all_results[0]["url"]]

        scraped_contents = []
        urls_scraped = salary_urls[:3]  # Scraper les 3 meilleures sources de salaires en parallèle
        logger.info(f"🎯 Sources salaires identifiées à scraper en parallèle: {urls_scraped}")

        scraping_tasks = [high_precision_scrape(url) for url in urls_scraped]
        if scraping_tasks:
            scraped_results = await asyncio.gather(*scraping_tasks)
            for url, content in zip(urls_scraped, scraped_results):
                if "just a moment" in content.lower() or "forbidden" in content.lower() or len(content.strip()) < 100:
                    logger.warning(f"⚠️ Scraping bloqué ou vide pour {url}, ignoré.")
                    continue
                scraped_contents.append(f"--- SOURCE SALAIRE: {url} ---\n{content}")

        return {
            "type": "salaries",
            "company": company_name,
            "job": job_title,
            "scraped_salary_pages": scraped_contents,
            "search_snippets": [r.get("snippet", "") for r in all_results[:8]]
        }
    except Exception as e:
        logger.error(f"❌ Erreur recherche salaires : {e}")
        return {"type": "salaries", "company": company_name, "job": job_title, "error": str(e)}
