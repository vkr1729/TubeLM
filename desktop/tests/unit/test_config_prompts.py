from config import load_category_prompt
import paths


def test_user_prompt_override_wins(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    (bundled / "summary").mkdir(parents=True)
    (user / "summary").mkdir(parents=True)
    (bundled / "summary" / "tech.md").write_text("Bundled prompt")
    (user / "summary" / "tech.md").write_text("User prompt")

    monkeypatch.setattr(paths, "get_prompts_dir", lambda: bundled)
    monkeypatch.setattr(paths, "get_user_prompts_dir", lambda: user)

    assert load_category_prompt("tech", "summary") == "User prompt"


def test_invalid_category_falls_back_to_tech(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    (bundled / "summary").mkdir(parents=True)
    (bundled / "summary" / "tech.md").write_text("Tech default")

    monkeypatch.setattr(paths, "get_prompts_dir", lambda: bundled)
    monkeypatch.setattr(paths, "get_user_prompts_dir", lambda: user)

    assert load_category_prompt("unknown", "summary") == "Tech default"
