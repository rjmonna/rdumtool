'use strict';

const status = document.querySelector('#status');
const commandStatus = document.querySelector('#command-status');
let busy = false;

function renderMetrics(id, fields) {
  const container = document.querySelector(id);
  container.replaceChildren();
  for (const [label, value] of fields) {
    const metric = document.createElement('div');
    metric.className = 'metric';
    const name = document.createElement('span');
    const reading = document.createElement('strong');
    name.textContent = label;
    reading.textContent = value;
    metric.append(name, reading);
    container.append(metric);
  }
}

function render(data) {
  const d = data.measurements;
  const model = data.device_type;
  document.querySelector('#model').textContent = `— ${model}`;
  document.querySelectorAll('[data-models]').forEach(element => {
    element.hidden = !element.dataset.models.split(' ').includes(model);
  });
  renderMetrics('#measurements', [
    ['Voltage', `${d.volts.toFixed(model === 'UM25C' ? 3 : 2)} V`],
    ['Current', `${d.amps.toFixed(model === 'UM25C' ? 4 : 3)} A`],
    ['Power', `${d.watts.toFixed(3)} W`], ['Resistance', `${d.resistance.toFixed(1)} Ω`],
    ['Data +', `${d.data_line_positive_volts.toFixed(2)} V`],
    ['Data −', `${d.data_line_negative_volts.toFixed(2)} V`],
  ]);
  renderMetrics('#details', [
    ['Temperature', `${d.temp_c} °C / ${d.temp_f} °F`],
    ['Charging mode', ['Unknown / Normal', 'Quick Charge 2.0', 'Quick Charge 3.0', 'Apple 2.4 A', 'Apple 2.1 A', 'Apple 1.0 A', 'Apple 0.5 A', 'DCP 1.5 A', 'Samsung'][d.charging_mode] ?? `Unknown (${d.charging_mode})`],
    ['Recording', d.recording ? 'On' : 'Off'],
    ['Recorded capacity', `${d.record_amphours.toFixed(3)} Ah`],
    ['Recorded energy', `${d.record_watthours.toFixed(3)} Wh`],
    ['Recorded time', `${d.record_seconds} s`],
    ['Threshold', `${d.record_threshold.toFixed(2)} A`],
    ['Screen', `${d.screen_selected}`], ['Brightness', `${d.screen_brightness} / 5`],
    ['Screen timeout', d.screen_timeout ? `${d.screen_timeout} min` : 'Off'],
  ]);
  const groups = document.querySelector('#groups');
  groups.replaceChildren();
  d.data_groups.forEach((group, index) => {
    const row = document.createElement('tr');
    [index === d.data_group_selected ? `${index} (selected)` : index,
      group.amp_hours.toFixed(3), group.watt_hours.toFixed(3)].forEach(value => {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    });
    groups.append(row);
  });
  status.textContent = `Updated ${new Date(d.collection_time * 1000).toLocaleTimeString()}`;
}

async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function refresh() {
  if (busy) return;
  busy = true;
  try {
    render(await request('/api/status'));
  } catch (error) {
    status.textContent = `Read failed: ${error.message}`;
  } finally {
    busy = false;
  }
}

async function command(name, value) {
  if (busy) {
    commandStatus.textContent = 'Device is busy. Try again.';
    return;
  }
  busy = true;
  commandStatus.textContent = 'Sending command...';
  try {
    await request('/api/command', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: name, value}),
    });
    commandStatus.textContent = 'Command sent (device does not acknowledge commands).';
  } catch (error) {
    commandStatus.textContent = `Command failed: ${error.message}`;
  } finally {
    busy = false;
  }
  await refresh();
}

document.querySelectorAll('button[data-command]').forEach(button => {
  button.addEventListener('click', () => {
    if (button.id === 'clear-group' && !confirm('Clear the current data group?')) return;
    command(button.dataset.command, true);
  });
});
document.querySelectorAll('#settings form').forEach(form => {
  form.addEventListener('submit', event => {
    event.preventDefault();
    const input = form.querySelector('input');
    if (!input.value || !input.reportValidity()) {
      commandStatus.textContent = 'Enter a valid value.';
      return;
    }
    command(input.name, Number(input.value));
  });
});
refresh();
setInterval(refresh, 2000);
