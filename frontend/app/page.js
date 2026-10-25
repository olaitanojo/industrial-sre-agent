"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const stages = ["Idle", "AnomalyDetected", "RootCauseAnalysis", "MitigationDrafting", "SandboxedVerification", "FinalDeploy"];
const apiUrl = process.env.NEXT_PUBLIC_API_URL;
const wsUrl = process.env.NEXT_PUBLIC_WS_URL;

function safeNumber(value, precision) {
  return typeof value === "number" ? value.toFixed(precision) : "--";
}

export default function Dashboard() {
  const [connected, setConnected] = useState(false);
  const [telemetry, setTelemetry] = useState({});
  const [activeStage, setActiveStage] = useState(-1);
  const [thoughts, setThoughts] = useState([]);
  const [sandbox, setSandbox] = useState("Waiting for verification output…");
  const [incident, setIncident] = useState("No active incident.");
  const [isInjecting, setIsInjecting] = useState(false);

  const receive = useCallback((message) => {
    const { event, payload, timestamp } = message;
    if (event === "telemetry.reading" || event === "telemetry.crisis_injected") setTelemetry(payload);
    if (event === "graph.transition") {
      setActiveStage(stages.indexOf(payload.stage));
      setThoughts((previous) => [{
        time: new Date(timestamp).toLocaleTimeString(),
        stage: payload.stage,
        summary: payload.thought.summary,
        evidence: payload.thought.evidence
      }, ...previous].slice(0, 30));
    }
    if (event === "sandbox.output") {
      const result = payload.result;
      setSandbox(`$ ${result.execution_mode} sandbox\nexit: ${result.exit_code ?? "unavailable"}\n\n${result.stdout || result.stderr}`);
    }
    if (event === "incident.created") setIncident(`Critical incident ${payload.incident_id} is running for ${payload.asset_id}.`);
    if (event === "incident.completed" || event === "incident.failed") {
      setIncident(payload.report || `Incident failed: ${payload.error}`);
      setIsInjecting(false);
    }
  }, []);

  useEffect(() => {
    if (!apiUrl || !wsUrl) {
      return undefined;
    }
    fetch(`${apiUrl}/api/telemetry/latest`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`Telemetry request failed: ${response.status}`)))
      .then((readings) => readings[0] && setTelemetry(readings[0]))
      .catch((error) => setIncident(error.message));

    let socket;
    let reconnectTimer;
    const connect = () => {
      socket = new WebSocket(`${wsUrl}/ws/live`);
      socket.onopen = () => {
        setConnected(true);
        socket.send("dashboard-online");
      };
      socket.onmessage = ({ data }) => receive(JSON.parse(data));
      socket.onclose = () => {
        setConnected(false);
        reconnectTimer = window.setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [receive]);

  const injectCrisis = async () => {
    setIsInjecting(true);
    try {
      const response = await fetch("/api/trigger-crisis", { method: "POST" });
      if (!response.ok) throw new Error(`Crisis request failed: ${response.status}`);
    } catch (error) {
      setIncident(error.message);
      setIsInjecting(false);
    }
  };

  const metrics = useMemo(() => [
    ["Vibration", safeNumber(telemetry.vibration_mm_s, 2), "mm/s"],
    ["Flow", safeNumber(telemetry.volumetric_flow_m3_h, 2), "m³/h"],
    ["Temperature", safeNumber(telemetry.temperature_c, 1), "°C"],
    ["Pressure", safeNumber(telemetry.pressure_bar, 1), "bar"]
  ], [telemetry]);
  const incidentDisplay = !apiUrl || !wsUrl ? "Production API endpoints are not configured." : incident;

  return (
    <main>
      <header>
        <div><p className="eyebrow">CONTROL PLANE / REFINERY SIMULATION</p><h1>Autonomous Industrial SRE Agent</h1></div>
        <div className="connection"><span className={connected ? "dot online" : "dot"} /><span>{connected ? "Live stream connected" : "Reconnecting"}</span></div>
      </header>
      <section className="hero panel">
        <div><p className="eyebrow">CHAOS ENGINEERING</p><h2>Exercise the remediation loop</h2><p>Injects a critical pump anomaly and streams every structured remediation transition.</p></div>
        <button onClick={injectCrisis} disabled={isInjecting}>{isInjecting ? "Injecting…" : "Trigger Crisis"}</button>
      </section>
      <section className="metrics">
        {metrics.map(([name, value, unit]) => <article className="panel metric" key={name}><span>{name}</span><strong>{value}</strong><small>{unit}</small></article>)}
      </section>
      <section className="grid">
        <article className="panel"><p className="eyebrow">CYCLIC LANGGRAPH EXECUTION</p><ol className="matrix">{stages.map((stage, index) => <li className={index === activeStage ? "active" : index < activeStage ? "complete" : ""} key={stage}>{stage.replace(/([A-Z])/g, " $1").trim()}</li>)}</ol></article>
        <article className="panel"><p className="eyebrow">AGENT THOUGHT STREAM</p><div className="log">{thoughts.map((thought, index) => <div className="logItem" key={`${thought.time}-${index}`}><span>{thought.time}</span><strong>{thought.stage}</strong><br />{thought.summary}<br /><small>{thought.evidence.join(" · ")}</small></div>)}</div></article>
      </section>
      <section className="grid">
        <article className="panel"><p className="eyebrow">SANDBOX TERMINAL</p><pre>{sandbox}</pre></article>
        <article className="panel"><p className="eyebrow">INCIDENT STATUS</p><div className="incident">{incidentDisplay}</div></article>
      </section>
    </main>
  );
}
