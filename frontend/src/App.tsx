import { useEffect, useState } from "react";
import MapPicker from "./components/MapPicker";
import Settings from "./components/Settings";
import InstallHint from "./components/InstallHint";
import {
  createMonitor,
  getNowcast,
  unsubscribe,
  type Intensity,
  type Nowcast,
} from "./api";
import {
  getExistingEndpoint,
  pushSupported,
  registerServiceWorker,
  subscribeToPush,
} from "./push";

// Curitiba como fallback caso a geolocalização seja negada.
const DEFAULT = { lat: -25.4284, lon: -49.2733 };

type LocationStatus = "idle" | "asking" | "granted" | "denied";

export default function App() {
  const [pos, setPos] = useState(DEFAULT);
  const [locStatus, setLocStatus] = useState<LocationStatus>("idle");
  const [minIntensity, setMinIntensity] = useState<Intensity>("moderada");
  const [radiusKm, setRadiusKm] = useState(50);
  const [monitoring, setMonitoring] = useState(false);
  const [nowcast, setNowcast] = useState<Nowcast | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (pushSupported()) registerServiceWorker().catch(() => {});
    getExistingEndpoint().then((e) => setMonitoring(!!e));
    requestLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function requestLocation() {
    if (!("geolocation" in navigator)) {
      setLocStatus("denied");
      return;
    }
    setLocStatus("asking");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos({ lat: p.coords.latitude, lon: p.coords.longitude });
        setLocStatus("granted");
      },
      () => setLocStatus("denied"), // permissão negada → mantém o local escolhido no mapa
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function enableMonitoring() {
    setError(null);
    if (!pushSupported()) {
      setError("Seu navegador não suporta notificações push. Instale o app na tela inicial.");
      return;
    }
    try {
      const subscription = await subscribeToPush();
      await createMonitor({
        lat: pos.lat,
        lon: pos.lon,
        min_intensity: minIntensity,
        alert_radius_km: radiusKm,
        subscription,
      });
      setMonitoring(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao ativar alertas");
    }
  }

  async function disableMonitoring() {
    const endpoint = await getExistingEndpoint();
    if (endpoint) await unsubscribe(endpoint);
    setMonitoring(false);
  }

  async function checkNow() {
    setError(null);
    try {
      setNowcast(await getNowcast(pos.lat, pos.lon, minIntensity, radiusKm));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao consultar");
    }
  }

  // Re-registra o monitor sempre que a config mudar (se já ativo).
  useEffect(() => {
    if (!monitoring) return;
    (async () => {
      const subscription = await subscribeToPush().catch(() => null);
      if (subscription) {
        await createMonitor({
          lat: pos.lat,
          lon: pos.lon,
          min_intensity: minIntensity,
          alert_radius_km: radiusKm,
          subscription,
        }).catch(() => {});
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pos.lat, pos.lon, minIntensity, radiusKm]);

  const approaching = nowcast?.cells.filter((c) => c.approaching) ?? [];

  return (
    <div className="app">
      <header>
        <h1>🌧️ StormWatch</h1>
        <p className="tagline">Avisamos quando a chuva está vindo até você.</p>
      </header>

      <InstallHint />

      {locStatus === "denied" && (
        <div className="banner">
          Não conseguimos sua localização. Toque no mapa para escolher o local a monitorar.
          <button type="button" onClick={requestLocation}>
            Tentar de novo
          </button>
        </div>
      )}

      <MapPicker lat={pos.lat} lon={pos.lon} onPick={(la, lo) => setPos({ lat: la, lon: lo })} />

      <div className="coords muted">
        Local: {pos.lat.toFixed(4)}, {pos.lon.toFixed(4)}
        {locStatus === "granted" && (
          <button className="link" type="button" onClick={requestLocation}>
            usar localização atual
          </button>
        )}
      </div>

      <Settings
        minIntensity={minIntensity}
        radiusKm={radiusKm}
        onChangeIntensity={setMinIntensity}
        onChangeRadius={setRadiusKm}
      />

      {error && <div className="banner banner--error">{error}</div>}

      <div className="actions">
        {monitoring ? (
          <button className="btn btn--secondary" type="button" onClick={disableMonitoring}>
            Desativar alertas
          </button>
        ) : (
          <button className="btn btn--primary" type="button" onClick={enableMonitoring}>
            Ativar alertas de chuva
          </button>
        )}
        <button className="btn btn--ghost" type="button" onClick={checkNow}>
          Ver situação agora
        </button>
      </div>

      {nowcast && (
        <section className="nowcast">
          {approaching.length === 0 ? (
            <p className="ok">☀️ Nenhuma chuva se aproximando do seu local.</p>
          ) : (
            <ul>
              {approaching.map((c, i) => (
                <li key={i} className={`cell cell--${c.intensity}`}>
                  <strong>
                    {c.intensity === "moderada"
                      ? "🌧️ Chuva moderada"
                      : c.intensity === "forte"
                      ? "⛈️ Chuva forte"
                      : "⛈️ Chuva muito forte"}
                  </strong>
                  <span>
                    {c.eta_minutes != null
                      ? `ETA ~${Math.round(c.eta_minutes)} min`
                      : "se aproximando"}{" "}
                    · {c.distance_km} km · {c.speed_kmh} km/h
                  </span>
                </li>
              ))}
            </ul>
          )}
          {nowcast.frame_time && (
            <small className="muted">
              Satélite GOES-19 · {new Date(nowcast.frame_time).toLocaleTimeString("pt-BR")}
            </small>
          )}
        </section>
      )}

      <footer className="muted">
        Não mostramos se vai chover hoje. Avisamos quando a chuva está vindo até você.
      </footer>
    </div>
  );
}
