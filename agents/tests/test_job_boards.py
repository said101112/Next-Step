"""Job-board scraping: shared helpers, LinkedIn URL/filters, the search flow (no network)."""
import asyncio

import pytest

from app.domain.job_boards import common, linkedin
from app.domain.job_boards.schemas import JobSearchRequest
from app.domain.job_boards.service import JobBoard, search_jobs


class TestSharedHelpers:
    def test_it_terms_are_whole_words(self):
        assert common._classify_it_offer({"title": "Fundraising specialist", "description": "email and training"}) == (False, [])
        is_it, terms = common._classify_it_offer({"title": "Développeur Python", "description": "APIs, AI"})
        assert is_it and "python" in terms and "ai" in terms

    def test_contract_type_is_whole_words(self):
        assert common.normalize_contract_type({"title": "Sales rep", "description": "international company"}) == "other"
        assert common.normalize_contract_type({"title": "Stage PFE - Data"}) == "internship"
        assert common.normalize_contract_type({"employment_type": "Full-time", "title": "Dev"}) == "full_time"

    @pytest.mark.parametrize("text, hours", [
        ("il y a 3 heures", 3), ("2 days ago", 48), ("Posted 1 week ago", 168), ("today", 0), ("", None),
    ])
    def test_relative_posting_age(self, text, hours):
        assert common.extract_relative_hours(text) == hours

    def test_duplicates_removed_and_limit_applied(self):
        jobs = [{"job_id": "1"}, {"job_id": "1"}, {"url": "u2"}, {"title": "t", "company": "c"}, {"job_id": "4"}]
        assert common._dedupe_jobs(jobs, limit=3) == [{"job_id": "1"}, {"url": "u2"}, {"title": "t", "company": "c"}]

    @pytest.mark.asyncio
    async def test_page_fetches_are_limited(self, monkeypatch):
        running = peak = 0

        class FakeFetcher:
            @staticmethod
            def get(url):
                nonlocal running, peak
                running += 1
                peak = max(peak, running)
                import time
                time.sleep(0.02)
                running -= 1
                return url

        monkeypatch.setattr(common, "_get_fetcher", lambda: FakeFetcher)
        pages = await asyncio.gather(*[common.fetch_page(f"u{i}") for i in range(20)])

        assert pages == [f"u{i}" for i in range(20)]
        assert peak <= common.FETCH_CONCURRENCY


class TestLinkedIn:
    def test_search_urls_are_encoded_and_paginated(self):
        urls = linkedin.build_search_urls(keywords="C# & .NET", location="Casablanca", limit=30, posted_window="24h")
        assert len(urls) >= 2
        assert "keywords=C%23+%26+.NET" in urls[0] and "f_TPR=r86400" in urls[0]

    @pytest.mark.parametrize("url, job_id", [
        ("https://www.linkedin.com/jobs/view/4012345678/", "4012345678"),
        ("https://ma.linkedin.com/jobs/view/developpeur-at-acme-4012345678", "4012345678"),
        ("https://www.linkedin.com/jobs/search?currentJobId=4012345678", "4012345678"),
        (None, None),
    ])
    def test_job_id(self, url, job_id):
        assert linkedin._extract_job_id(url) == job_id

    def test_filters(self):
        jobs = [
            {"job_id": "1", "is_it_offer": True, "normalized_contract_type": "internship"},
            {"job_id": "2", "is_it_offer": False, "normalized_contract_type": "internship"},
            {"job_id": "3", "is_it_offer": True, "normalized_contract_type": "cdi"},
        ]
        kept = linkedin.filter_jobs(jobs, it_only=True, limit=10, contract_types=["Internship"])
        assert [j["job_id"] for j in kept] == ["1"]


class TestSearchFlow:
    def _board(self, urls):
        async def fetch(request, search_urls, limit):
            return [{"job_id": str(i), "title": f"Job {i}"} for i in range(5)]

        async def enrich(jobs, enabled):
            return [{**j, "enriched": enabled} for j in jobs]

        return JobBoard(
            name="Fake",
            build_urls=lambda request, limit: urls,
            fetch_listings=fetch,
            enrich=enrich,
            filter=lambda request, jobs: jobs[: request.limit],
            warnings=lambda request: ["best-effort"],
        )

    @pytest.mark.asyncio
    async def test_counts_details_and_warnings(self):
        result = await search_jobs(self._board(["u1"]), JobSearchRequest(keywords="dev", limit=2, fetch_details=False))
        assert (result["total_found"], result["total_returned"]) == (5, 2)
        assert result["jobs"][0]["enriched"] is False
        assert result["errors"] == ["best-effort"] and result["search_urls"] == ["u1"]

    @pytest.mark.asyncio
    async def test_details_stop_once_enough_offers_pass_the_filters(self):
        detailed: list[str] = []

        async def fetch(request, search_urls, limit):
            return [{"job_id": str(i), "is_it_offer": i % 2 == 0} for i in range(40)]

        async def enrich(jobs, enabled):
            detailed.extend(j["job_id"] for j in jobs)
            return jobs

        board = JobBoard(
            name="Fake", build_urls=lambda r, n: ["u"], fetch_listings=fetch, enrich=enrich,
            filter=lambda r, jobs: [j for j in jobs if j["is_it_offer"]][: r.limit],
        )
        result = await search_jobs(board, JobSearchRequest(keywords="dev", limit=3))

        assert result["total_returned"] == 3 and result["total_found"] == 40
        assert len(detailed) == 10  # one batch, not the 40 listings

    @pytest.mark.asyncio
    async def test_more_batches_when_filters_drop_offers(self):
        batches: list[int] = []

        async def fetch(request, search_urls, limit):
            return [{"job_id": str(i), "keep": i >= 25} for i in range(40)]

        async def enrich(jobs, enabled):
            batches.append(len(jobs))
            return jobs

        board = JobBoard(
            name="Fake", build_urls=lambda r, n: ["u"], fetch_listings=fetch, enrich=enrich,
            filter=lambda r, jobs: [j for j in jobs if j["keep"]][: r.limit],
        )
        result = await search_jobs(board, JobSearchRequest(keywords="dev", limit=3))

        assert result["total_returned"] == 3
        assert batches == [10, 10, 10]

    @pytest.mark.asyncio
    async def test_no_search_url_stops_early(self):
        result = await search_jobs(self._board([]), JobSearchRequest(keywords="dev"))
        assert result["jobs"] == [] and "No Fake search URL" in result["errors"][0]


class _Page:
    def __init__(self, status=200, html="<html><div class='job'>Dev</div></html>"):
        self.status = status
        self.html_content = html


class TestFetchDiagnostics:
    @pytest.mark.parametrize("page, expected", [
        (_Page(), None),
        (_Page(status=403), "blocked by the site (HTTP 403)"),
        (_Page(status=429), "blocked by the site (HTTP 429)"),
        (_Page(status=500), "HTTP 500"),
        (_Page(html="<title>Just a moment...</title>"), "anti-bot page returned (just a moment...)"),
        (_Page(html="<div id='px-captcha'></div>"), "anti-bot page returned (captcha)"),
    ])
    def test_problem_detection(self, page, expected):
        assert common.detect_fetch_problem(page) == expected

    @pytest.mark.asyncio
    async def test_blocked_board_explains_why_it_found_nothing(self, monkeypatch):
        class BlockedFetcher:
            @staticmethod
            def get(url):
                return _Page(status=403, html="")

        monkeypatch.setattr(common, "_get_fetcher", lambda: BlockedFetcher)

        async def fetch(request, search_urls, limit):
            await common.fetch_page(search_urls[0])
            return []

        async def enrich(jobs, enabled):
            return jobs

        board = JobBoard(name="Indeed", build_urls=lambda r, n: ["u"], fetch_listings=fetch, enrich=enrich,
                         filter=lambda r, jobs: jobs)
        result = await search_jobs(board, JobSearchRequest(keywords="dev"))

        assert result["jobs"] == []
        assert result["errors"] == [
            "Indeed returned no listings: blocked by the site (HTTP 403). Showing cached offers for this provider."
        ]

    @pytest.mark.asyncio
    async def test_failing_board_returns_a_warning_instead_of_raising(self, monkeypatch):
        class DownFetcher:
            @staticmethod
            def get(url):
                raise ConnectionError("boom")

        monkeypatch.setattr(common, "_get_fetcher", lambda: DownFetcher)

        async def fetch(request, search_urls, limit):
            return [*await common.fetch_page(search_urls[0])]

        board = JobBoard(name="Glassdoor", build_urls=lambda r, n: ["u"], fetch_listings=fetch,
                         enrich=lambda jobs, enabled: jobs, filter=lambda r, jobs: jobs)
        result = await search_jobs(board, JobSearchRequest(keywords="dev"))

        assert result["jobs"] == [] and result["search_urls"] == ["u"]
        assert result["errors"] == [
            "Glassdoor returned no listings: request failed (ConnectionError). Showing cached offers for this provider."
        ]

    @pytest.mark.asyncio
    async def test_empty_but_healthy_board_adds_no_warning(self):
        async def fetch(request, search_urls, limit):
            return []

        async def enrich(jobs, enabled):
            return jobs

        board = JobBoard(name="LinkedIn", build_urls=lambda r, n: ["u"], fetch_listings=fetch, enrich=enrich,
                         filter=lambda r, jobs: jobs)
        result = await search_jobs(board, JobSearchRequest(keywords="dev"))
        assert result["errors"] == []


class TestGlassdoorLocation:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        from app.domain.job_boards import glassdoor
        glassdoor._LOCATION_CACHE.clear()
        yield
        glassdoor._LOCATION_CACHE.clear()

    def test_large_result_page_mentioning_captcha_is_not_a_block(self):
        page = _Page(html="<script>recaptcha</script>" + "x" * 200_000)
        assert common.detect_fetch_problem(page) is None

    def test_search_urls_keep_the_location_out_of_the_keywords(self):
        from app.domain.job_boards import glassdoor
        urls = glassdoor.build_search_urls(keywords="software engineer", location="Casablanca", limit=5)
        assert urls == ["https://www.glassdoor.com/Job/jobs.htm?sc.keyword=software+engineer"]

    @pytest.mark.asyncio
    async def test_known_location_is_searched_by_id(self, monkeypatch):
        from app.domain.job_boards import glassdoor
        fetched: list[str] = []

        async def fake_fetch(url):
            fetched.append(url)
            if "autocomplete" in url:
                return _Page(html='<html><body>[{"locationId":3935929,"locationType":"C","label":"Casablanca"}]</body></html>')
            return _Page(html="<html></html>")

        monkeypatch.setattr(glassdoor, "fetch_page", fake_fetch)
        urls = glassdoor.build_search_urls(keywords="dev", location="Casablanca", limit=5)
        await glassdoor.fetch_listing_jobs(urls, limit=5, location="Casablanca")
        await glassdoor.fetch_listing_jobs(urls, limit=5, location="casablanca")  # cached

        assert sum("autocomplete" in u for u in fetched) == 1
        assert [u for u in fetched if "autocomplete" not in u] == [
            "https://www.glassdoor.com/Job/jobs.htm?sc.keyword=dev&locT=C&locId=3935929",
        ] * 2
        assert glassdoor.location_was_resolved("Casablanca")

    @pytest.mark.asyncio
    async def test_unknown_location_falls_back_to_keywords_and_warns(self, monkeypatch):
        from app.domain.job_boards import glassdoor
        from app.domain.job_boards.service import GLASSDOOR
        from app.domain.job_boards.schemas import GlassdoorJobSearchRequest
        fetched: list[str] = []

        async def fake_fetch(url):
            fetched.append(url)
            return _Page(html="<html><body>[]</body></html>")

        monkeypatch.setattr(glassdoor, "fetch_page", fake_fetch)
        result = await search_jobs(GLASSDOOR, GlassdoorJobSearchRequest(keywords="dev", location="Atlantis", limit=5))

        assert "https://www.glassdoor.com/Job/jobs.htm?sc.keyword=dev+Atlantis" in fetched
        assert any("does not recognise the location 'Atlantis'" in w for w in result["errors"])


def test_reposted_job_under_another_id_is_deduplicated():
    jobs = [
        {"job_id": "a", "title": "AD Software Engineer", "company": "Stellantis", "location": "Casablanca"},
        {"job_id": "b", "title": "AD  Software Engineer", "company": "stellantis", "location": "Casablanca"},
        {"job_id": "c", "title": "AD Software Engineer", "company": "Stellantis", "location": "Rabat"},
    ]
    assert [j["job_id"] for j in common._dedupe_jobs(jobs, limit=10)] == ["a", "c"]
