// Configuração de intensidade mínima e distância de alerta.

import type { Intensity } from "../api";

interface Props {
  minIntensity: Intensity;
  radiusKm: number;
  onChangeIntensity: (v: Intensity) => void;
  onChangeRadius: (v: number) => void;
}

const OPTIONS: { value: Intensity; label: string; hint: string }[] = [
  { value: "moderada", label: "🌧️ Moderada", hint: "≥ 2,5 mm/h" },
  { value: "forte", label: "⛈️ Forte", hint: "≥ 10 mm/h" },
  { value: "muito_forte", label: "⛈️ Muito forte", hint: "≥ 50 mm/h" },
];

export default function Settings({
  minIntensity,
  radiusKm,
  onChangeIntensity,
  onChangeRadius,
}: Props) {
  return (
    <div className="settings">
      <fieldset>
        <legend>Avisar a partir de</legend>
        <div className="intensity-options">
          {OPTIONS.map((o) => (
            <button
              key={o.value}
              className={`chip ${minIntensity === o.value ? "chip--active" : ""}`}
              onClick={() => onChangeIntensity(o.value)}
              type="button"
            >
              <span>{o.label}</span>
              <small>{o.hint}</small>
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>
          Distância de alerta: <strong>{radiusKm} km</strong>
        </legend>
        <input
          type="range"
          min={5}
          max={150}
          step={5}
          value={radiusKm}
          onChange={(e) => onChangeRadius(Number(e.target.value))}
        />
        <small className="muted">
          Avisamos quando a chuva estiver a menos de {radiusKm} km e se aproximando.
        </small>
      </fieldset>
    </div>
  );
}
