from resume_engine.ui.services import prompt_service


def test_prompt_versioning_and_rollback():
    prompt_service.ensure_defaults()
    v = prompt_service.create_version("resume_generation", "version-a-content", actor="test", activate=True)
    assert v["status"] == "ACTIVE"
    v2 = prompt_service.create_version("resume_generation", "version-b-content", actor="test", activate=True)
    assert v2["status"] == "ACTIVE"
    rolled = prompt_service.rollback_prompt("resume_generation", v["version"], actor="test")
    assert rolled["version"] == v["version"]
    assert rolled["status"] == "ACTIVE"
