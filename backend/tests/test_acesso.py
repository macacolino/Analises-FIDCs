from fastapi.testclient import TestClient

from fidc.api.main import app


def test_sem_senha_fica_aberto(monkeypatch):
    monkeypatch.delenv("FIDC_SENHA", raising=False)
    assert TestClient(app).get("/healthz").status_code == 200
    assert TestClient(app).get("/api/dicionario").status_code == 200


def test_senha_unica(monkeypatch):
    monkeypatch.setenv("FIDC_SENHA", "teste-123")
    c = TestClient(app)
    assert c.get("/api/dicionario").status_code == 401
    r = c.get("/fundo/123", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=/fundo/123")
    assert c.get("/login").status_code == 200
    assert c.post("/login", data={"senha": "errada", "next": "/"}, follow_redirects=False).status_code == 401
    r = c.post("/login", data={"senha": "teste-123", "next": "//fora.com"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert c.get("/api/dicionario").status_code == 200
    monkeypatch.setenv("FIDC_SENHA", "outra")       # trocar a senha derruba a sessão
    assert c.get("/api/dicionario").status_code == 401


def test_feedback(monkeypatch, tmp_path):
    monkeypatch.delenv("FIDC_SENHA", raising=False)
    monkeypatch.delenv("FIDC_FEEDBACK_URL", raising=False)
    from fidc import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = TestClient(app)
    assert c.post("/api/feedback", json={"texto": "  "}).status_code == 400
    r = c.post("/api/feedback", json={"texto": "gráfico cortado", "nome": "Allan", "pagina": "/fundo/1"})
    assert r.json() == {"ok": True, "planilha": False}
    assert "gráfico cortado" in (tmp_path / "feedback.jsonl").read_text()
