const stages = ["Idle", "AnomalyDetected", "RootCauseAnalysis", "MitigationDrafting", "SandboxedVerification", "FinalDeploy"];
const elements = {
  button: document.querySelector("#crisis-button"),
  status: document.querySelector("#connection-status"),
  dot: document.querySelector("#connection-dot"),
  thoughtStream: document.querySelector("#thought-stream"),
  sandbox: document.querySelector("#sandbox-output"),
  incident: document.querySelector("#incident-status"),
};

function updateTelemetry(reading) {
  document.querySelector("#vibration").textContent = reading.vibration_mm_s.toFixed(2);
  document.querySelector("#flow").textContent = reading.volumetric_flow_m3_h.toFixed(2);
  document.querySelector("#temperature").textContent = reading.temperature_c.toFixed(1);
  document.querySelector("#pressure").textContent = reading.pressure_bar.toFixed(1);
}

function markStage(stage) {
  const active = stages.indexOf(stage);
  document.querySelectorAll("#matrix li").forEach((item, index) => {
    item.classList.toggle("active", index === active);
    item.classList.toggle("complete", index < active);
  });
}

function appendThought(transition, timestamp) {
  const thought = transition.thought;
  const row = document.createElement("div");
  row.className = "log-item";
  row.innerHTML = `<span class="log-time">${new Date(timestamp).toLocaleTimeString()}</span><strong>${transition.stage}</strong><br>${thought.summary}<br><small>${thought.evidence.join(" · ")}</small>`;
  elements.thoughtStream.prepend(row);
}

function consume(event) {
  if (event.event === "telemetry.reading" || event.event === "telemetry.crisis_injected") updateTelemetry(event.payload);
  if (event.event === "graph.transition") {
    markStage(event.payload.stage);
    appendThought(event.payload, event.timestamp);
  }
  if (event.event === "sandbox.output") {
    const result = event.payload.result;
    elements.sandbox.textContent = `$ ${result.execution_mode} sandbox\nexit: ${result.exit_code}\n\n${result.stdout || result.stderr}`;
  }
  if (event.event === "incident.created") elements.incident.textContent = `Critical incident ${event.payload.incident_id} is running for ${event.payload.asset_id}.`;
  if (event.event === "incident.completed" || event.event === "incident.failed") {
    elements.incident.textContent = event.payload.report || `Incident failed: ${event.payload.error}`;
    elements.button.disabled = false;
    elements.button.textContent = "Trigger Crisis";
  }
}

function connect() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${location.host}/ws/live`);
  socket.onopen = () => {
    elements.status.textContent = "Live stream connected";
    elements.dot.classList.add("online");
    socket.send("dashboard-online");
  };
  socket.onmessage = ({ data }) => consume(JSON.parse(data));
  socket.onclose = () => {
    elements.status.textContent = "Reconnecting";
    elements.dot.classList.remove("online");
    setTimeout(connect, 1500);
  };
}

elements.button.addEventListener("click", async () => {
  elements.button.disabled = true;
  elements.button.textContent = "Injecting…";
  try {
    const response = await fetch("/trigger-crisis", { method: "POST" });
    if (!response.ok) throw new Error(`Crisis request failed: ${response.status}`);
  } catch (error) {
    elements.incident.textContent = error.message;
    elements.button.disabled = false;
    elements.button.textContent = "Trigger Crisis";
  }
});

fetch("/api/telemetry/latest").then((response) => response.json()).then((readings) => readings[0] && updateTelemetry(readings[0])).catch(() => {});
connect();
