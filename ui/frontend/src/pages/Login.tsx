import { useState, type FormEvent } from "react";
import { api, jsonBody } from "../api";
import type { User } from "../types";

export function Login({ onLogged }: { onLogged: (u: User) => void }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogged(await api<User>("/login", { method: "POST", body: jsonBody({ login, password }) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connexion impossible");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <div className="login-art" aria-hidden="true">
        <svg viewBox="0 0 400 400">
          {[0, 1, 2, 3, 4].map((i) => (
            <g key={i} className="login-lane" style={{ animationDelay: `${i * 0.6}s` }}>
              <path d={`M40 200 C120 200 140 ${80 + i * 60} 200 ${80 + i * 60} S280 200 360 200`} />
              <circle cx="200" cy={80 + i * 60} r="7" />
            </g>
          ))}
          <circle className="login-node" cx="40" cy="200" r="14" />
          <circle className="login-node login-node-end" cx="360" cy="200" r="14" />
        </svg>
      </div>
      <form className="login-card" onSubmit={submit}>
        <div className="brand brand-lg">
          <span className="brand-mark" aria-hidden="true" />
          <span>Revue PR <em>Calipso</em></span>
        </div>
        <h1>Suivi des analyses</h1>
        <p className="muted">Accès réservé à l’équipe. Le code relu ne quitte jamais l’infrastructure.</p>
        <label>
          Identifiant
          <input autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} required autoFocus />
        </label>
        <label>
          Mot de passe
          <input type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Connexion…" : "Se connecter"}</button>
      </form>
    </main>
  );
}
