function pollRunStatus(jobId, targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;
  const tick = async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}/status`);
      const data = await res.json();
      el.textContent = JSON.stringify(data, null, 2);
      if (data.status === "COMPLETED" || data.status === "FAILED") return;
      setTimeout(tick, 2000);
    } catch (err) {
      el.textContent = String(err);
    }
  };
  tick();
}
