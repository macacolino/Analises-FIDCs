import sqlite3
import time

from fidc import appdb, config, persistencia


class Resp:
    def __init__(self, status=200, content=b"", js=None):
        self.status_code, self.content, self._js, self.text = status, content, js, ""

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise persistencia.httpx.HTTPStatusError("x", request=None, response=None)


def test_salva_e_restaura(monkeypatch, tmp_path):
    guardado = {}

    def get(url, headers=None, timeout=None):
        if "metadata" in url:
            return Resp(js={"access_token": "t", "expires_in": 3600})
        return Resp(content=guardado["obj"]) if "obj" in guardado else Resp(404)

    def post(url, content=None, headers=None, timeout=None):
        guardado["obj"] = content
        return Resp()

    monkeypatch.setattr(persistencia.httpx, "get", get)
    monkeypatch.setattr(persistencia.httpx, "post", post)
    monkeypatch.setenv("FIDC_BUCKET", "teste")
    monkeypatch.setattr(config, "APP_DB_PATH", tmp_path / "app.sqlite")
    persistencia.ESTADO.update(bloqueado=False, erro=None)

    assert persistencia.baixar() == "vazio"
    with appdb.session() as s:                       # leitura não envia
        s.execute("SELECT count(*) FROM lista").fetchone()
    time.sleep(0.3)
    assert "obj" not in guardado
    with appdb.session() as s:
        s.execute("INSERT INTO lista (cnpj, tipo) VALUES ('123', 'carteira')")
    for _ in range(50):
        if "obj" in guardado:
            break
        time.sleep(0.1)
    assert "obj" in guardado

    (tmp_path / "app.sqlite").unlink()               # instância nova: disco vazio
    assert persistencia.baixar() == "restaurado"
    assert sqlite3.connect(tmp_path / "app.sqlite").execute("SELECT cnpj FROM lista").fetchall() == [("123",)]


def test_erro_ao_baixar_bloqueia_envio(monkeypatch, tmp_path):
    monkeypatch.setattr(persistencia.httpx, "get", lambda *a, **k: Resp(403) if "metadata" not in a[0]
                        else Resp(js={"access_token": "t", "expires_in": 3600}))
    enviados = []
    monkeypatch.setattr(persistencia.httpx, "post", lambda *a, **k: enviados.append(1) or Resp())
    monkeypatch.setenv("FIDC_BUCKET", "teste")
    monkeypatch.setattr(config, "APP_DB_PATH", tmp_path / "app.sqlite")
    persistencia.ESTADO.update(bloqueado=False, erro=None)
    assert persistencia.baixar() == "erro"
    with appdb.session() as s:
        s.execute("INSERT INTO lista (cnpj, tipo) VALUES ('1', 'watchlist')")
    time.sleep(0.3)
    assert enviados == []
    persistencia.ESTADO.update(bloqueado=False, erro=None)
