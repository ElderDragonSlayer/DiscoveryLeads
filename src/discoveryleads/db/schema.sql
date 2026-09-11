-- Primeira migracao do DiscoveryLeads. Na Fatia Dia 1 substitui o Alembic, e
-- amanha vira a migracao 0001 sem mudar nada. Subconjunto das secoes 4.1, 4.2
-- e 4.3 da spec, com os nomes de la.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY,
    nome            TEXT NOT NULL,
    endereco        TEXT,
    cidade          TEXT,
    uf              TEXT,
    lat             REAL,
    lng             REAL,
    telefone_e164   TEXT,
    categoria       TEXT,
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_identities (
    tipo     TEXT NOT NULL,
    valor    TEXT NOT NULL,
    lead_id  INTEGER NOT NULL REFERENCES leads(id),
    PRIMARY KEY (tipo, valor)
);

CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY,
    lead_id      INTEGER NOT NULL REFERENCES leads(id),
    tipo         TEXT NOT NULL,
    valor        TEXT,
    fonte        TEXT NOT NULL,
    coletor      TEXT NOT NULL,
    versao       INTEGER NOT NULL,
    confianca    REAL NOT NULL,
    observado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_signals_lead_tipo
    ON signals(lead_id, tipo, observado_em DESC);

-- Principio 2: signals e append-only, e o banco garante sozinho.
CREATE TRIGGER IF NOT EXISTS signals_sem_update BEFORE UPDATE ON signals
BEGIN
    SELECT RAISE(ABORT, 'signals e append-only: UPDATE proibido');
END;
CREATE TRIGGER IF NOT EXISTS signals_sem_delete BEFORE DELETE ON signals
BEGIN
    SELECT RAISE(ABORT, 'signals e append-only: DELETE proibido');
END;

-- A visao atual de um lead: a ultima observacao de cada tipo.
CREATE VIEW IF NOT EXISTS v_signals_atuais AS
SELECT s.*
FROM signals s
WHERE s.id = (
    SELECT s2.id
    FROM signals s2
    WHERE s2.lead_id = s.lead_id AND s2.tipo = s.tipo
    ORDER BY s2.observado_em DESC, s2.id DESC
    LIMIT 1
);
