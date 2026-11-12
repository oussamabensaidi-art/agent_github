import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, jsonBody, setUnauthorizedHandler } from "./api";
import { Icon } from "./components/ui";
import { dateTime } from "./format";
import { HistoryPage } from "./pages/HistoryPage";
import { LivePage } from "./pages/LivePage";
import { Login } from "./pages/Login";
import { RunPage } from "./pages/RunPage";
import { StatsPage } from "./pages/StatsPage";
import { Link, navigate, useLocation } from "./router";
import type { AppConfig, User } from "./types";

function PublishingSwitch({ config, user, onChange }: { config: AppConfig; user: User; onChange: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const on = config.publishing.enabled;
  const admin = user.role === "admin";

  async function toggle() {
    setBusy(true);
    setError("");
    try {
      await api("/publishing", { method: "PUT", body: jsonBody({ enabled: !on }) });
      setConfirm(false);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "échec");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className={`switch ${on ? "switch-on" : "switch-off"}`} disabled={!admin}
        onClick={() => setConfirm(true)}
        title={admin ? "Interrupteur de publication" : "Réservé aux administrateurs"}>
        <span className="switch-track"><span className="switch-thumb" /></span>
        <span className="switch-text">
          <strong>{on ? "Publication active" : "Publication coupée"}</strong>
          <small>{config.publishing.updated_by ? `${config.publishing.updated_by} · ${dateTime(config.publishing.updated_at)}` : "valeur initiale"}</small>
        </span>
      </button>
      {/* Portail : la barre du haut (backdrop-filter) piégerait un élément `fixed`. */}
      {confirm && createPortal(
        <div className="modal-back" role="dialog" aria-modal="true" aria-labelledby="ks-title" onClick={() => setConfirm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className={`modal-icon ${on ? "tone-critical" : "tone-good"}`}><Icon name="power" size={22} /></div>
            <h2 id="ks-title">{on ? "Couper la publication ?" : "Réactiver la publication ?"}</h2>
            <p>
              {on
                ? "L’agent continuera d’analyser les PR et de tout journaliser, mais n’écrira plus rien sur GitHub (check, revue, statut) et n’enverra plus d’email. Effet immédiat, sans redéploiement."
                : "L’agent publiera à nouveau ses revues et statuts sur GitHub et enverra les alertes, dès la prochaine écriture."}
            </p>
            {error && <p className="form-error">{error}</p>}
            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setConfirm(false)}>Annuler</button>
              <button type="button" className={`btn ${on ? "btn-danger" : "btn-primary"}`} disabled={busy} onClick={toggle}>
                {on ? "Couper la publication" : "Réactiver"}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const loc = useLocation();

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    api<User>("/me").then(setUser).catch(() => setUser(null));
  }, []);

  const loadConfig = useCallback(() => {
    api<AppConfig>("/config").then(setConfig).catch(() => {});
  }, []);
  useEffect(() => {
    if (!user) return;
    loadConfig();
    const t = window.setInterval(loadConfig, 15000); // l'interrupteur peut être changé par un autre admin
    return () => window.clearInterval(t);
  }, [user, loadConfig]);

  if (user === undefined) return <div className="boot"><span className="spinner" /></div>;
  if (user === null) return <Login onLogged={(u) => { setUser(u); navigate("/", true); }} />;
  if (!config) return <div className="boot"><span className="spinner" /></div>;

  const runMatch = loc.path.match(/^\/runs\/([0-9a-f]{32})$/);
  const nav = [
    { to: "/", label: "En direct", active: loc.path === "/" },
    { to: "/historique", label: "Historique", active: loc.path === "/historique" || Boolean(runMatch) },
    { to: "/statistiques", label: "Statistiques", active: loc.path === "/statistiques" },
  ];

  async function logout() {
    await api("/logout", { method: "POST" }).catch(() => {});
    setUser(null);
  }

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span>Revue PR <em>Calipso</em></span>
        </Link>
        <nav className="nav">
          {nav.map((n) => <Link key={n.to} to={n.to} className={n.active ? "on" : ""}>{n.label}</Link>)}
        </nav>
        <div className="topbar-right">
          <div className="chips">
            {config.pilot_mode && <span className="chip" title="Les remarques de l'IA ne peuvent pas bloquer seules">Pilote · IA consultative</span>}
            {config.workers.length
              ? <span className="chip chip-mono" title={`${config.workers.length} worker(s) actif(s) · fournisseur ${config.provider}`}>{config.model}</span>
              : <span className="chip chip-alert" title="Aucun battement de cœur depuis 60 s">aucun worker actif</span>}
          </div>
          <PublishingSwitch config={config} user={user} onChange={loadConfig} />
          <div className="user">
            <span className="avatar" aria-hidden="true">{user.login.slice(0, 2).toUpperCase()}</span>
            <span className="user-name">{user.login}<small>{user.role}</small></span>
            <button type="button" className="icon-btn" onClick={logout} title="Se déconnecter" aria-label="Se déconnecter">
              <Icon name="logout" size={16} />
            </button>
          </div>
        </div>
      </header>

      {!config.publishing.enabled && (
        <div className="banner banner-critical" role="status">
          <Icon name="power" size={16} />
          <strong>Publication coupée.</strong> Les analyses continuent et sont journalisées, mais rien n’est écrit sur GitHub ni envoyé par email.
        </div>
      )}
      {config.demo_mode && (
        <div className="banner banner-demo" role="status">
          <Icon name="flask" size={16} />
          <strong>Mode démo.</strong> L’agent parle à un GitHub simulé : aucun vrai dépôt n’est connecté.
        </div>
      )}
      {config.dry_run && (
        <div className="banner banner-info" role="status"><Icon name="eye" size={16} /><strong>Lecture seule (DRY_RUN).</strong> Rien n’est publié.</div>
      )}
      {!config.store && (
        <div className="banner banner-critical" role="status"><Icon name="alert" size={16} />Journal d’événements non configuré : pas d’historique.</div>
      )}

      <main className="content">
        {runMatch ? <RunPage key={runMatch[1] + loc.search.toString()} runId={runMatch[1]} replay={loc.search.get("rejouer") === "1"} />
          : loc.path === "/historique" ? <HistoryPage />
            : loc.path === "/statistiques" ? <StatsPage />
              : <LivePage config={config} user={user} />}
      </main>
      <footer className="foot">
        <span>Règles <code>{config.rules_version}</code></span>
        <span>{config.concurrency} lot(s) en parallèle · check « {config.check_name} » ({config.auth_mode === "app" ? "GitHub App" : "jeton"})</span>
        <span>L’agent ne fusionne rien et ne modifie aucun code.</span>
      </footer>
    </div>
  );
}
