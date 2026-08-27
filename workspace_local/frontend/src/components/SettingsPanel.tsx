import { useEffect, useState } from "react";
import { getSettings, putSettings } from "../api/client";

interface SettingsPanelProps {
  onClose: () => void;
}

export default function SettingsPanel({ onClose }: SettingsPanelProps) {
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSettings()
      .then((settings) => setModel(settings.model))
      .catch(() => setModel(""));
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      await putSettings(model);
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.35)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "10vh",
      }}
    >
      <div style={{ background: "white", padding: "1.5rem", borderRadius: "8px", width: "420px" }}>
        <h2 style={{ marginTop: 0 }}>Settings</h2>
        <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>
          OpenRouter model
        </label>
        <input
          type="text"
          value={model}
          onChange={(event) => setModel(event.target.value)}
          placeholder="e.g. openai/gpt-4o-mini"
          style={{ width: "100%", padding: "0.5rem", boxSizing: "border-box" }}
        />
        <p style={{ fontSize: "0.8rem", color: "#666" }}>
          The OpenRouter API key is not entered here — set OPENROUTER_API_KEY in
          workspace_local/backend/.env.
        </p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
          <button onClick={onClose}>Cancel</button>
          <button onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
