"""Tavily/Gemini discovery stays grounded without calling either service."""

from __future__ import annotations

from app.engines import discovery


def _row(url: str, skill: str) -> dict:
    return {
        "title": "Grounded Python course",
        "provider": "Example Academy",
        "url": url,
        "description": "A Python course.",
        "level": "beginner",
        "hours": 8,
        "hours_stated": True,
        "cost": "free",
        "format": "interactive",
        "teaches": [{"skill": skill, "strength": 0.9}],
        "requires": [],
    }


def test_discovery_rejects_url_not_returned_by_tavily(goal_spec):
    row = _row("https://made-up.example/python", goal_spec.skills[0].id)
    assert discovery._to_course(
        row,
        {skill.id for skill in goal_spec.skills},
        {"https://search-result.example/python"},
    ) is None


def test_discovery_uses_search_evidence_and_cache(goal_spec, tmp_path, monkeypatch):
    class FakeTavily:
        calls: list[dict] = []

        def search(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "results": [
                    {
                        "title": "Python tutorial",
                        "url": "https://search-result.example/python",
                        "content": "An 8 hour Python tutorial.",
                    }
                ]
            }

    fake = FakeTavily()
    cache = tmp_path / "resources"
    cache.mkdir()
    monkeypatch.setattr(discovery, "RESOURCE_CACHE", cache)
    monkeypatch.setattr(discovery, "available", lambda: True)
    monkeypatch.setattr(discovery, "_get_client", lambda: fake)
    monkeypatch.setattr(discovery.llm, "available", lambda: True)

    def collect(system, prompt, *args, **kwargs):
        assert "Tavily search results" in prompt
        assert "https://search-result.example/python" in prompt
        return {
            "resources": [
                _row("https://search-result.example/python", goal_spec.skills[0].id),
                _row("https://invented.example/python", goal_spec.skills[0].id),
            ]
        }

    monkeypatch.setattr(discovery.llm, "collect", collect)

    first = discovery.find(goal_spec, goal_spec.skills[:1], budget="free")
    second = discovery.find(goal_spec, goal_spec.skills[:1], budget="free")

    assert [course.url for course in first] == ["https://search-result.example/python"]
    assert [course.url for course in second] == ["https://search-result.example/python"]
    assert len(fake.calls) == 1
    assert fake.calls[0]["search_depth"] == "basic"
    # One skill per query. A batch-wide query asked for five topics at once and
    # came back with pages about their overlap - vendor overviews of the general
    # subject - rather than anything that teaches a particular skill.
    assert goal_spec.skills[0].name in fake.calls[0]["query"]
    assert goal_spec.skills[1].name not in fake.calls[0]["query"]


def test_every_skill_gets_its_own_search_and_a_place_in_the_prompt(goal_spec, tmp_path, monkeypatch):
    """A noisier skill must not crowd its neighbours out of the labelling prompt."""

    class FakeTavily:
        def __init__(self):
            self.queries: list[str] = []

        def search(self, **kwargs):
            query = kwargs["query"]
            self.queries.append(query)
            slug = query.split()[0].lower()
            return {
                "results": [
                    {"title": f"{slug} {rank}", "url": f"https://example.test/{slug}/{rank}",
                     "content": "A course."}
                    for rank in range(discovery.MAX_RESULTS)
                ]
            }

    fake = FakeTavily()
    cache = tmp_path / "resources"
    cache.mkdir()
    monkeypatch.setattr(discovery, "RESOURCE_CACHE", cache)
    monkeypatch.setattr(discovery, "available", lambda: True)
    monkeypatch.setattr(discovery, "_get_client", lambda: fake)
    monkeypatch.setattr(discovery.llm, "available", lambda: True)

    prompts: list[str] = []
    monkeypatch.setattr(discovery.llm, "collect",
                        lambda system, prompt, *a, **k: prompts.append(prompt) or {"resources": []})

    skills = goal_spec.skills
    discovery.find(goal_spec, skills, budget="free")

    assert len(fake.queries) == len(skills)
    # Each skill contributes PER_SKILL sources, so none is squeezed out by a
    # skill whose search happened to return more.
    for skill in skills[:discovery.BATCH]:
        slug = skill.name.split()[0].lower()
        assert f"https://example.test/{slug}/0" in prompts[0]
        assert f"https://example.test/{slug}/{discovery.PER_SKILL}" not in prompts[0]
