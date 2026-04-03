import { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [health, setHealth] = useState<string | null>(null);

  useEffect(() => {
    const base = import.meta.env.VITE_API_URL ?? "/api";
    fetch(`${base.replace(/\/$/, "")}/health`)
      .then((r) => r.json())
      .then((j) => setHealth(JSON.stringify(j)))
      .catch(() => setHealth("unavailable (start BFF)"));
  }, []);

  return (
    <div className="app">
      <h1>theoffice</h1>
      <p>BFF /health: {health ?? "…"}</p>
    </div>
  );
}

export default App;
