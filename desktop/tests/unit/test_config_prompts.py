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


def test_load_config_tts_settings(monkeypatch):
    from config import load_config
    monkeypatch.setenv("TTS_VOICE", "en-US-AndrewMultilingualNeural")
    monkeypatch.setenv("TTS_RATE", "+5%")
    cfg = load_config()
    assert cfg.tts_voice == "en-US-AndrewMultilingualNeural"
    assert cfg.tts_rate == "+5%"


def test_load_config_tts_defaults(monkeypatch):
    from config import load_config
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.delenv("TTS_RATE", raising=False)
    cfg = load_config()
    assert cfg.tts_voice == "en-US-BrianMultilingualNeural"
    assert cfg.tts_rate == "+0%"
