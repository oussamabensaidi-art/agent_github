import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { RunMonitor } from "../components/RunMonitor";
import { Icon } from "../components/ui";
import { navigate } from "../router";
import { useLiveRun, useReplay } from "../runState";
import type { RunDetail } from "../types";

export function useRunDetail(runId: string | null, finished: boolean) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const load = useCallback(() => {
    if (!runId) return;
    api<RunDetail>(`/runs/${runId}`).then(setDetail).catch(() => setDetail(null));
  }, [runId]);
  useEffect(() => {
    setDetail(null);
    load();
  }, [load]);
  useEffect(() => {
    if (finished) load();
  }, [finished, load]);
  return detail;
}

export function RunPage({ runId, replay }: { runId: string; replay: boolean }) {
  const live = useLiveRun(runId, !replay);
  const player = useReplay(runId, replay);
  const view = replay ? player.view : live.view;
  const finished = !["queued", "running"].includes(live.view.status);
  const detail = useRunDetail(runId, finished);

  const controls = replay ? (
    <div className="player">
      <span className="player-badge"><Icon name="restart" size={13} /> Relecture</span>
      {player.playing
        ? <button type="button" className="btn btn-sm" onClick={player.pause}><Icon name="pause" size={14} /> Pause</button>
        : <button type="button" className="btn btn-sm btn-primary" onClick={player.play}><Icon name="play" size={14} /> Lire</button>}
      <button type="button" className="btn btn-sm btn-ghost" onClick={player.restart}><Icon name="restart" size={14} /> Début</button>
      <button type="button" className="btn btn-sm btn-ghost" onClick={player.seekEnd}><Icon name="end" size={14} /> Fin</button>
      <div className="seg seg-sm" role="group" aria-label="Vitesse">
        {[1, 4, 16].map((s) => (
          <button key={s} type="button" className={player.speed === s ? "on" : ""} onClick={() => player.setSpeed(s)}>×{s}</button>
        ))}
      </div>
      <div className="player-bar" aria-label="Progression"><span style={{ width: `${player.progress * 100}%` }} /></div>
      <button type="button" className="btn btn-sm btn-ghost" onClick={() => navigate(`/runs/${runId}`)}>Quitter la relecture</button>
    </div>
  ) : finished ? (
    <div className="player">
      <button type="button" className="btn btn-sm" onClick={() => navigate(`/runs/${runId}?rejouer=1`)}>
        <Icon name="play" size={14} /> Rejouer l’analyse
      </button>
      {detail?.run.pr_url && !detail.run.demo && (
        <a className="btn btn-sm btn-ghost" href={detail.run.pr_url} target="_blank" rel="noreferrer">
          <Icon name="external" size={14} /> PR sur GitHub
        </a>
      )}
    </div>
  ) : null;

  if (!replay && live.view.lastSeq < 0 && detail === null) {
    return <div className="page"><p className="muted pad">Chargement de l’analyse…</p></div>;
  }

  return (
    <div className="page">
      <RunMonitor view={view} live={!replay} connected={live.connected} stored={detail?.findings}
        canRate={!replay} header={controls}
        replayClock={replay ? view.lastTs : undefined} />
    </div>
  );
}
