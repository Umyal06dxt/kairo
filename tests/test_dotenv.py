import os

from kairo.cli import load_dotenv


def test_load_dotenv(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# c\nA_KEY=abc\nexport B_KEY="quoted val"\nC_KEY=\'x\'\nEXISTING=new\n\nbad line\n')
    for k in ["A_KEY", "B_KEY", "C_KEY"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EXISTING", "old")
    load_dotenv(str(f))
    assert os.environ["A_KEY"] == "abc" and os.environ["B_KEY"] == "quoted val"
    assert os.environ["C_KEY"] == "x" and os.environ["EXISTING"] == "old"


def test_load_dotenv_missing_file_is_noop(tmp_path):
    load_dotenv(str(tmp_path / "nope"))
